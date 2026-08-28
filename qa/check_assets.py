#!/usr/bin/env python3
"""Verify every static asset this addon references actually exists.

Two separate sources of truth, both of which have silently broken here:

1. The manifest's `assets` bundles. A missing path is not a build error in
   Odoo — it logs "Could not get content for <path>" to the browser console
   and serves the page unstyled. That shipped once already.

2. Paths hardcoded as string literals in JS and loaded at runtime with
   loadJS/loadCSS. The manifest never mentions these, so a manifest-only
   check reports "asset files OK" while the file is gone. This is how the
   diff viewer ran for its whole life with no syntax highlighting: the
   library it needed was simply never fetched, and nothing said so.

Exits non-zero listing whatever is missing.
"""
import ast
import glob
import os
import re
import sys

PROBLEMS = []
CHECKED = 0


def manifest_assets():
    """Paths declared in each addon's manifest `assets` bundles."""
    global CHECKED
    for manifest in glob.glob('*/__manifest__.py'):
        raw = open(manifest).read()
        data = ast.literal_eval(raw[raw.index('{'):])
        for bundle, entries in (data.get('assets') or {}).items():
            for entry in entries:
                path = entry[0] if isinstance(entry, (list, tuple)) else entry
                if '*' in path:          # globs are Odoo's problem, not ours
                    continue
                CHECKED += 1
                if not os.path.isfile(path):
                    PROBLEMS.append(f'{manifest} [{bundle}] -> {path}')


#: loadJS("/dw_git/static/..."), loadCSS('/dw_git/static/...'), and the
#: module-level constants that feed them
ASSET_LITERAL = re.compile(r'["\'](/(\w+)/static/[^"\']+\.(?:js|css))["\']')


def runtime_assets():
    """Paths hardcoded in JS and fetched at runtime."""
    global CHECKED
    for js in glob.glob('*/static/src/**/*.js', recursive=True):
        source = open(js).read()
        for match in ASSET_LITERAL.finditer(source):
            url = match.group(1)
            on_disk = url.lstrip('/')          # /dw_git/static/x -> dw_git/static/x
            CHECKED += 1
            if not os.path.isfile(on_disk):
                line = source[:match.start()].count('\n') + 1
                PROBLEMS.append(f'{js}:{line} loads {url} which does not exist')


manifest_assets()
runtime_assets()

if PROBLEMS:
    print('assets referenced but absent:', file=sys.stderr)
    for problem in PROBLEMS:
        print(f'  {problem}', file=sys.stderr)
    sys.exit(1)
print(f'asset files OK ({CHECKED} references checked)')
