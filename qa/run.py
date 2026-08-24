#!/usr/bin/env python3
"""OdooGit browser QA — pure Python entry point (no shell scripts).

Usage:
    python3 qa/run.py                     # seed data (idempotent) + run all flows
    python3 qa/run.py qa/flows/04_*.yaml  # run specific flow(s) only
    QA_BASE_URL=http://staging:8069 python3 qa/run.py

Executes declarative YAML flows (see qa/README.md) via the agent-browser CLI.
Exit code 0 = all flows passed.

Parses the tiny YAML subset used by flows (nested maps, lists of maps/scalars)
without external libraries.
"""
import json
import os
import subprocess
import sys
import time

BASE_URL = os.environ.get('QA_BASE_URL', 'http://localhost:8069').rstrip('/')
QA_USER = os.environ.get('QA_USER', 'admin')
QA_PASS = os.environ.get('QA_PASS', 'admin')
QA_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(QA_DIR, 'output')


# ---------------------------------------------------------------- seeding
def seed():
    """Seed realistic data inside the odoo container (idempotent)."""
    if os.environ.get('QA_SKIP_SEED'):
        print('SEED: skipped (QA_SKIP_SEED set)')
        return
    try:
        subprocess.run(['docker', 'compose', 'version'], capture_output=True,
                       check=True, cwd=os.path.dirname(QA_DIR))
    except Exception:
        print('SEED: docker compose unavailable, skipping (set QA_SKIP_SEED=1 to silence)')
        return
    root = os.path.dirname(QA_DIR)
    subprocess.run(['docker', 'compose', 'cp', os.path.join(QA_DIR, 'seed.py'),
                    'odoo:/tmp/qa-seed.py'], check=True, cwd=root)
    p = subprocess.run(
        ['docker', 'compose', 'exec', '-T', 'odoo', 'bash', '-c',
         'odoo shell -d odoo --db_host=postgres --db_user=odoo '
         '--db_password=odoo --no-http < /tmp/qa-seed.py'],
        capture_output=True, text=True, cwd=root)
    for line in (p.stdout + p.stderr).splitlines():
        if 'SEED' in line:
            print(line.strip())


# ---------------------------------------------------------------- YAML subset
def _scalar(v):
    v = v.strip()
    if v in ('true', 'True'):
        return True
    if v in ('false', 'False'):
        return False
    if v and v[0] in '"\'' and v[-1] == v[0]:
        return v[1:-1]
    if v.replace('.', '', 1).isdigit():
        return float(v) if '.' in v else int(v)
    return v


def parse_yaml(path):
    """Line-based parser for the flow schema: maps + lists of maps/scalars."""
    lines = []
    for raw in open(path).read().splitlines():
        no_comment = raw.split(' #')[0].rstrip() if not raw.lstrip().startswith('#') else ''
        if no_comment.strip():
            lines.append(no_comment)

    def parse_block(idx, indent):
        """Return (value, next_idx) for the block starting at lines[idx]."""
        # detect list vs map
        if idx >= len(lines):
            return {}, idx
        first = lines[idx]
        first_indent = len(first) - len(first.lstrip())
        if first.lstrip().startswith('- '):
            # LIST
            items = []
            while idx < len(lines):
                line = lines[idx]
                ind = len(line) - len(line.lstrip())
                s = line.lstrip()
                if ind < first_indent or not s.startswith('- '):
                    break
                if ind > first_indent:
                    break
                # item line: '- key: value' or '- scalar'
                item_content = s[2:].strip()
                if ':' in item_content and not item_content.startswith(('"', "'")):
                    # dict item: first key inline
                    key, _, val = item_content.partition(':')
                    d = {}
                    if val.strip():
                        d[key.strip()] = _scalar(val)
                    else:
                        # value is nested block
                        sub, idx2 = parse_block(idx + 1, _indent_of(idx + 1))
                        d[key.strip()] = sub
                        idx = idx2
                        items.append(d)
                        continue
                    # continuation keys at deeper indent
                    idx += 1
                    while idx < len(lines):
                        l2 = lines[idx]
                        i2 = len(l2) - len(l2.lstrip())
                        s2 = l2.strip()
                        if i2 <= first_indent or s2.startswith('- '):
                            break
                        k2, _, v2 = s2.partition(':')
                        d[k2.strip()] = _scalar(v2)
                        idx += 1
                    items.append(d)
                else:
                    items.append(_scalar(item_content))
                    idx += 1
            return items, idx
        # MAP
        m = {}
        while idx < len(lines):
            line = lines[idx]
            ind = len(line) - len(line.lstrip())
            s = line.strip()
            if ind < indent or s.startswith('- '):
                break
            key, _, val = s.partition(':')
            key = key.strip()
            val = val.strip()
            if val:
                m[key] = _scalar(val)
                idx += 1
            else:
                sub, idx = parse_block(idx + 1, _indent_of(idx + 1))
                m[key] = sub
        return m, idx

    def _indent_of(i):
        if i >= len(lines):
            return 999
        return len(lines[i]) - len(lines[i].lstrip())

    val, _ = parse_block(0, 0)
    return val


# ---------------------------------------------------------------- CLI wrapper
AB = os.environ.get('AGENT_BROWSER_BIN', 'agent-browser')


def ab(session, *args, timeout=30):
    cmd = [AB, '--session', session, *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def ab_json(session, *args, timeout=30):
    rc, out = ab(session, *args, '--json', timeout=timeout)
    try:
        return rc, json.loads(out)
    except Exception:
        return rc, {'success': False, 'raw': out}


def ab_eval(session, expr, timeout=30):
    """Evaluate JS, return the clean result via --json."""
    rc, data = ab_json(session, 'eval', expr, timeout=timeout)
    if rc != 0 or not data.get('success'):
        return None, data.get('error') or data.get('raw', '')
    return data.get('data', {}).get('result'), None


def _retry(fn, attempts=20, delay=0.5):
    """Retry fn until it returns truthy or attempts exhausted."""
    for _ in range(attempts):
        try:
            if fn():
                return True
        except FlowError:
            pass
        time.sleep(delay)
    return False


# ---------------------------------------------------------------- steps
class FlowError(Exception):
    pass


def run_step(step, session, ctx, flow_name, idx):
    def fail(msg):
        raise FlowError(msg)

    if 'open' in step:
        rc, out = ab(session, 'open', BASE_URL + step['open'] if step['open'].startswith('/') else step['open'], timeout=45)
        if rc != 0:
            fail(f'open failed: {out[:200]}')
    elif 'wait' in step:
        time.sleep(float(step['wait']) / 1000.0)
    elif 'wait_text' in step:
        deadline = time.time() + 15
        ok = False
        while time.time() < deadline:
            rc, data = ab_json(session, 'find', 'text', step['wait_text'])
            if rc == 0 and data.get('success'):
                ok = True
                break
            time.sleep(0.5)
        if not ok:
            fail(f'text not found: {step["wait_text"]!r}')
    elif 'wait_load' in step:
        rc, out = ab(session, 'wait', '--load', 'networkidle', timeout=45)
        if rc != 0:
            fail(f'wait_load failed: {out[:200]}')
    elif 'fill_label' in step:
        value = {'$USER': QA_USER, '$PASS': QA_PASS}.get(step.get('value', ''), step.get('value', ''))

        def do_fill():
            rc, out = ab(session, 'find', 'label', step['fill_label'], 'fill', value, timeout=30)
            if rc != 0:
                raise FlowError(f'fill_label {step["fill_label"]!r}: {out[:120]}')
            return True
        if not _retry(do_fill):
            fail(f'fill_label {step["fill_label"]!r}: element never appeared')
    elif 'fill_placeholder' in step:
        def do_fillp():
            rc, out = ab(session, 'find', 'placeholder', step['fill_placeholder'], 'fill', step.get('value', ''), timeout=30)
            if rc != 0:
                raise FlowError(f'fill_placeholder: {out[:120]}')
            return True
        if not _retry(do_fillp):
            fail(f'fill_placeholder {step["fill_placeholder"]!r}: element never appeared')
    elif 'press' in step:
        rc, out = ab(session, 'press', step['press'], timeout=15)
        if rc != 0:
            fail(f'press failed: {out[:200]}')
    elif 'click_text' in step:
        def do_click():
            rc, out = ab(session, 'find', 'text', step['click_text'], 'click', timeout=30)
            if rc != 0:
                raise FlowError(f'click_text: {out[:120]}')
            return True
        if not _retry(do_click):
            fail(f'click_text {step["click_text"]!r}: element never appeared')
    elif 'click_row' in step:
        # snapshot, find the ref whose line contains the text, click that ref
        def do_click_row():
            rc, out = ab(session, 'snapshot', '-i', '-c', timeout=45)
            if rc != 0 or 'ref=e' not in out:
                raise FlowError('snapshot unavailable')
            for line in out.splitlines():
                if step['click_row'] in line:
                    import re as _re
                    m = _re.search(r'ref=(e\d+)', line)
                    if m:
                        rc2, out2 = ab(session, 'click', '@' + m.group(1), timeout=30)
                        if rc2 == 0:
                            return True
            raise FlowError('row not found yet')
        if not _retry(do_click_row, attempts=12):
            fail(f'click_row {step["click_row"]!r}: row never appeared')
    elif 'click_role' in step:
        extra = ('--name', step['name']) if step.get('name') else ()
        rc, out = ab(session, 'find', 'role', step['click_role'], 'click', *extra, timeout=30)
        if rc != 0:
            fail(f'click_role failed: {out[:200]}')
    elif 'assert_url' in step:
        rc, out = ab(session, 'get', 'url', timeout=15)
        url = out.strip().splitlines()[-1]
        import fnmatch
        if not fnmatch.fnmatch(url, step['assert_url']):
            fail(f'url {url!r} !~ {step["assert_url"]!r}')
    elif 'assert_text' in step:
        def has_text():
            txt, err = ab_eval(session, 'document.body.innerText')
            return err is None and txt and step['assert_text'] in txt
        if not _retry(has_text, attempts=24):
            fail(f'text not on page: {step["assert_text"]!r}')
    elif 'assert_no_text' in step:
        txt, err = ab_eval(session, 'document.body.innerText')
        if err is None and txt and step['assert_no_text'] in txt:
            fail(f'unexpected text on page: {step["assert_no_text"]!r}')
    elif 'assert_eval' in step:
        def check():
            res, err = ab_eval(session, step['assert_eval'])
            return err is None and res in (True, 1, 'true', '1')
        if not _retry(check, attempts=10):
            res, err = ab_eval(session, step['assert_eval'])
            fail(f'assert_eval false: {step["assert_eval"]!r} -> {res!r} {err or ""}')
    elif 'eval' in step:
        ab_eval(session, step['eval'], timeout=45)
    elif 'console_clean' in step and step['console_clean']:
        rc, out = ab(session, 'console', timeout=30)
        new_lines = [l for l in out.splitlines() if l not in ctx['console_seen']]
        ctx['console_seen'].update(out.splitlines())
        errors = [l for l in new_lines if '[error]' in l]
        if errors:
            fail('console errors:\n    ' + '\n    '.join(errors[:5]))
    elif 'screenshot' in step:
        os.makedirs(OUT_DIR, exist_ok=True)
        ab(session, 'screenshot', os.path.join(OUT_DIR, f'{flow_name}__{step["screenshot"]}'), timeout=45)
    elif 'snapshot' in step and step['snapshot']:
        def has_refs():
            rc, out = ab(session, 'snapshot', '-i', '-c', timeout=45)
            return 'ref=e' in out
        if not _retry(has_refs, attempts=10):
            fail('snapshot has no interactive elements')
    elif 'sleep_console_mark' in step:
        rc, out = ab(session, 'console', timeout=30)
        ctx['console_seen'].update(out.splitlines())
    else:
        fail(f'unknown step: {step}')


def run_flow(path):
    flow = parse_yaml(path)
    name = flow.get('name', os.path.basename(path))
    session = flow.get('session', 'qa-odoo')
    steps = flow.get('steps', [])
    print(f'\n=== {name} (session={session}, {len(steps)} steps) ===')
    ctx = {'console_seen': set()}
    failures = []
    ab(session, 'close')
    time.sleep(2)  # daemon needs a beat after close before relaunch
    base = os.path.splitext(os.path.basename(path))[0]
    for idx, step in enumerate(steps, 1):
        label = next(iter(step)) if isinstance(step, dict) else str(step)
        try:
            run_step(step, session, ctx, base, idx)
            print(f'  ok   {idx:02d} {label}')
        except FlowError as e:
            if step.get('optional'):
                print(f'  warn {idx:02d} {label}: {e}')
            else:
                print(f'  FAIL {idx:02d} {label}: {e}')
                failures.append(f'{name} step {idx:02d} ({label}): {e}')
                os.makedirs(OUT_DIR, exist_ok=True)
                ab(session, 'screenshot', os.path.join(OUT_DIR, f'{base}__FAIL_{idx:02d}.png'), timeout=30)
    ab(session, 'close')
    return failures


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    targets = sys.argv[1:]
    if not targets:
        seed()  # full-suite run: ensure data exists first
        flows_dir = os.path.join(QA_DIR, 'flows')
        targets = sorted(os.path.join(flows_dir, f) for f in os.listdir(flows_dir) if f.endswith('.yaml'))
    all_fail = []
    for t in targets:
        all_fail += run_flow(t)
    print('\n' + '=' * 46)
    if all_fail:
        print(f'RESULT: FAIL ({len(all_fail)} failure(s))')
        for f in all_fail:
            print(f'  - {f}')
        sys.exit(1)
    print('RESULT: ALL FLOWS PASSED')


if __name__ == '__main__':
    main()
