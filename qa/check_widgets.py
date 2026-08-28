#!/usr/bin/env python3
"""Fail when a view uses a field widget the field's type does not support.

Odoo does not raise on this. It logs a browser-console warning —
"The widget: badge don't support the type integer" — and renders the field
with the default widget instead. Nothing fails, so it survives.

That happened here twenty-three times, and the warning was the smaller
half. Those views also passed `options="{'classes': {...}}"` colour maps,
and Odoo's badge widget has no `classes` option at all: its only supported
option is `color_field`, with colour otherwise coming from `decoration-*`.
So every colour map was silently ignored and every badge rendered grey,
exactly as if it had been written correctly.

Exits non-zero listing whatever is mismatched.
"""
import glob
import re
import sys

#: widget -> field types Odoo's implementation actually accepts
SUPPORTED = {
    'badge': {'selection', 'many2one', 'char'},
    'statinfo': {'integer', 'float', 'monetary'},
    'percentage': {'float', 'integer'},
    'email': {'char'},
    'url': {'char'},
}

#: widgets this addon defines, and what they widen
LOCAL = {
    'git_badge': {'selection', 'many2one', 'char', 'integer', 'float', 'boolean'},
    'git_diff_viewer': {'text'},
}

FIELD_DEF = re.compile(r'\n    (\w+) = fields\.(\w+)')
VIEW_FIELD = re.compile(r'<field\b[^>]*\bname="(\w+)"[^>]*\bwidget="(\w+)"[^>]*>|'
                        r'<field\b[^>]*\bwidget="(\w+)"[^>]*\bname="(\w+)"[^>]*>')

types = {}
for path in glob.glob('*/models/*.py'):
    for match in FIELD_DEF.finditer(open(path).read()):
        types[match.group(1)] = match.group(2).lower()

problems = []
checked = 0
for path in glob.glob('*/views/*.xml'):
    for number, line in enumerate(open(path), 1):
        for match in VIEW_FIELD.finditer(line):
            name = match.group(1) or match.group(4)
            widget = match.group(2) or match.group(3)
            allowed = LOCAL.get(widget) or SUPPORTED.get(widget)
            if not allowed or name not in types:
                continue
            checked += 1
            if types[name] not in allowed:
                problems.append(
                    f'{path}:{number} widget="{widget}" on {name} '
                    f'({types[name]}) — supports {sorted(allowed)}')

if problems:
    print('field widgets used on unsupported types:', file=sys.stderr)
    for problem in problems:
        print(f'  {problem}', file=sys.stderr)
    sys.exit(1)
print(f'field widgets OK ({checked} checked)')
