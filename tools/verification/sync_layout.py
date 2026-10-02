"""Check or write Git ignore rules derived from the active layout."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from tools.paths import LAYOUT, Layout

_START = '# BEGIN SIMVLTANEA layout (python3 -m tools.verification.sync_layout --write)'
_END = '# END SIMVLTANEA layout'


def ignore_block(layout: Layout) -> str:
    lines = [_START, '/' + layout.relative('generated') + '/*']
    lines += ['!/' + path for path in sorted(layout.policy_paths('allowed_lane_placeholders'))]
    lines += ['/' + path + '/' for path in sorted(layout.policy_paths('proof_output_directories'))]
    raw = layout.relative('archive') + '/raw'
    lines += ['/' + raw + '/*', '!/' + raw + '/README.md', '!/' + raw + '/.gitkeep', _END]
    return '\n'.join(lines) + '\n'


def expected_ignore(text: str, layout: Layout) -> str:
    if _START not in text:
        return text.rstrip() + '\n\n' + ignore_block(layout)
    start = text.index(_START)
    end = text.index(_END, start) + len(_END)
    if text[end:end+1] == '\n':
        end += 1
    return text[:start] + ignore_block(layout) + text[end:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Update derived ignore rules')
    args = parser.parse_args(argv)
    ignore_path = LAYOUT.root / '.gitignore'
    actual = ignore_path.read_text() if ignore_path.exists() else ''
    expected = expected_ignore(actual, LAYOUT)
    naming_path = LAYOUT.path('config') / 'lint' / 'ls-lint.yml'
    naming = naming_path.read_text()
    head = naming.split('ignore:', 1)[0]
    # Resolve the docs rule through its configured role as well.
    for topic in ('plans', 'provenance'):
        head = re.sub(r'(?m)^  [^\n]+/' + topic + ':', '  ' + LAYOUT.relative('docs') + '/' + topic + ':', head)
    expected_naming = head + 'ignore:\n' + ''.join(
        '  - ' + json.dumps(LAYOUT.expand(item)) + '\n' for item in LAYOUT.lint['ignore'])
    markdown_path = LAYOUT.path('config') / 'lint' / 'markdownlintignore'
    markdown = markdown_path.read_text()
    expected_markdown = '# CLI exclusions resolved from the active layout manifest.\n' + ''.join(
        LAYOUT.expand(item) + '\n' for item in LAYOUT.lint['markdown_ignore'])
    differences = [(ignore_path, actual, expected), (naming_path, naming, expected_naming),
                   (markdown_path, markdown, expected_markdown)]
    editor_path = LAYOUT.root / '.vscode' / 'settings.json'
    if editor_path.is_file():
        editor = editor_path.read_text()
        settings = json.loads(editor)
        settings['markdownlint.configFile'] = './' + LAYOUT.relative('config') + '/lint/markdownlint.json'
        differences.append((editor_path, editor, json.dumps(settings, indent=2) + '\n'))
    changed = [entry for entry in differences if entry[1] != entry[2]]
    if not changed:
        print('layout ignore and naming rules ok')
        return 0
    if args.write:
        for path, _, content in changed:
            path.write_text(content)
        print('layout ignore and naming rules updated')
        return 0
    print('derived layout rules differ; run python3 -m tools.verification.sync_layout --write')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
