"""Writes a result as Markdown, JSON and HTML files."""
import html as html_lib
import json
from pathlib import Path


def _e(value):
    return html_lib.escape('' if value is None else str(value), quote=True)


def _table_html(block):
    cells = block.metadata.get('cells')
    if cells:
        rows = []
        for row in cells:
            tds = []
            for c in row:
                attrs = ''
                if c['rowspan'] > 1:
                    attrs += f' rowspan="{c["rowspan"]}"'
                if c['colspan'] > 1:
                    attrs += f' colspan="{c["colspan"]}"'
                tds.append(f'<td{attrs}>{_e(c["text"])}</td>')
            rows.append('  <tr>' + ''.join(tds) + '</tr>')
    else:
        rows = ['  <tr>' + ''.join(f'<td>{_e(c)}</td>' for c in row) + '</tr>'
                for row in block.metadata.get('rows', [])]
    return '<table>\n' + '\n'.join(rows) + '\n</table>'


def to_html(blocks, title='ParseAnything result'):
    parts = []
    for b in blocks:
        if b.type in ('header', 'footer'):
            continue
        attrs = f' data-id="{_e(b.id)}" data-page="{b.page}" data-confidence="{b.confidence:.2f}"'
        if b.type == 'heading':
            parts.append(f'<h2{attrs}>{_e(b.text)}</h2>')
        elif b.type == 'table':
            parts.append(f'<div{attrs}>{_table_html(b)}</div>')
        elif b.type == 'spreadsheet':
            sheet = b.metadata.get('sheet', 'Untitled')
            parts.append(f'<h3>Sheet: {_e(sheet)}</h3>\n<div{attrs}>{_table_html(b)}</div>')
        elif b.type == 'figure':
            parts.append(f'<figure{attrs}><figcaption>{_e(b.text or "Figure")}</figcaption></figure>')
        elif b.type == 'caption':
            parts.append(f'<p class="caption"{attrs}><em>{_e(b.text)}</em></p>')
        elif b.type == 'equation':
            parts.append(f'<p class="equation"{attrs}>\\[{_e(b.text)}\\]</p>')
        elif b.type == 'footnote':
            parts.append(f'<aside{attrs}>{_e(b.text)}</aside>')
        elif b.type == 'list':
            parts.append(f'<p class="list-item"{attrs}>&bull; {_e(b.text)}</p>')
        else:
            parts.append(f'<p{attrs}>{_e(b.text)}</p>')

    body = '\n'.join(parts)
    return ('<!DOCTYPE html>\n<html lang="en">\n<head><meta charset="utf-8">'
            f'<title>{_e(title)}</title></head>\n<body>\n{body}\n</body>\n</html>\n')


def write_outputs(stem, out_dir, payload, markdown, blocks, title=None):
    """Save the .json, .md and .html versions of one result."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f'{stem}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / f'{stem}.md').write_text(markdown, encoding='utf-8')
    (out / f'{stem}.html').write_text(to_html(blocks, title or stem), encoding='utf-8')
