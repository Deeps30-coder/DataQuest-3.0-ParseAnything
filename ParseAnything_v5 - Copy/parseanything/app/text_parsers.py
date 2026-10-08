"""Readers for plain text, Markdown, CSV, HTML, RTF and email files.

Every reader returns (blocks, errors). The blocks use the same types as the
other readers, so they are written to Markdown, HTML and JSON the same way.
"""
import csv
import email
import io
import re
import tempfile
from email import policy
from html.parser import HTMLParser
from pathlib import Path

from .models import Block
from .utils import safe_name

TABLE_SEPARATOR = re.compile(r'^:?-{3,}:?$')
SKIP_TAGS = {'script', 'style', 'head', 'nav', 'noscript', 'title'}
TEXT_TAGS = {
    'h1': 'heading', 'h2': 'heading', 'h3': 'heading',
    'h4': 'heading', 'h5': 'heading', 'h6': 'heading',
    'p': 'paragraph', 'blockquote': 'paragraph', 'pre': 'paragraph',
    'dt': 'paragraph', 'dd': 'paragraph',
    'li': 'list', 'figcaption': 'caption',
    'footer': 'footer', 'aside': 'footnote',
}


def read_text(path):
    """Read a text file, trying the common encodings in turn."""
    raw = Path(path).read_bytes()
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1')


def _clean(text):
    return ' '.join(text.split())


def _block(block_id, kind, text='', confidence=0.97, source='text', **metadata):
    return Block(id=block_id, type=kind, page=1, text=text, confidence=confidence,
                 source=source, metadata=metadata)


def _table_block(block_id, rows, source):
    return Block(id=block_id, type='table', page=1, text='', confidence=0.97,
                 source=source, metadata={'rows': rows})


def _paragraph_blocks(text, prefix, source):
    blocks = []
    for para in re.split(r'\n\s*\n', text.replace('\r\n', '\n')):
        cleaned = '\n'.join(line.strip() for line in para.strip().split('\n')).strip()
        if cleaned:
            blocks.append(_block(f'{prefix}_{len(blocks) + 1}', 'paragraph', cleaned, source=source))
    return blocks


# ---------- Plain text ----------

def parse_txt(path):
    return _paragraph_blocks(read_text(path), 'txt', 'txt'), []


# ---------- Markdown ----------

def parse_markdown(path):
    lines = read_text(path).replace('\r\n', '\n').split('\n')
    blocks = []
    pending = []   # lines of a paragraph that is still open
    code = None    # lines inside a ``` fence, or None when not in a fence

    def add(kind, text, **metadata):
        blocks.append(_block(f'md_{len(blocks) + 1}', kind, text, source='markdown', **metadata))

    def flush():
        if pending:
            add('paragraph', ' '.join(p.strip() for p in pending))
            pending.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        i += 1

        if code is not None:
            if stripped.startswith('```'):
                add('paragraph', '\n'.join(code))
                code = None
            else:
                code.append(line)
            continue
        if stripped.startswith('```'):
            flush()
            code = []
            continue
        if not stripped:
            flush()
            continue

        if stripped.startswith('$$'):
            flush()
            if stripped != '$$' and stripped.endswith('$$') and len(stripped) > 4:
                add('equation', stripped[2:-2].strip())
            else:
                eq = []
                while i < len(lines) and lines[i].strip() != '$$':
                    eq.append(lines[i].strip())
                    i += 1
                i += 1  # skip the closing $$
                add('equation', '\n'.join(eq).strip())
            continue

        heading = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if heading:
            flush()
            add('heading', heading.group(2).strip(), level=len(heading.group(1)))
            continue

        image = re.match(r'^!\[([^\]]*)\]\(([^)]*)\)', stripped)
        if image:
            flush()
            add('figure', image.group(1).strip() or 'Image', src=image.group(2))
            continue

        if stripped.startswith('|'):
            flush()
            rows = []
            j = i - 1
            while j < len(lines) and lines[j].strip().startswith('|'):
                cells = [c.strip() for c in lines[j].strip().strip('|').split('|')]
                if not all(TABLE_SEPARATOR.match(c) for c in cells):
                    rows.append(cells)
                j += 1
            i = j
            if rows:
                blocks.append(_table_block(f'md_{len(blocks) + 1}', rows, 'markdown'))
            continue

        item = re.match(r'^([-*+]|\d+[.)])\s+(.*)$', stripped)
        if item:
            flush()
            add('list', item.group(2).strip())
            continue

        pending.append(line)

    if code:
        add('paragraph', '\n'.join(code))
    flush()
    return blocks, []


# ---------- CSV ----------

def parse_csv(path):
    text = read_text(path)
    rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text))]
    while rows and not any(rows[-1]):
        rows.pop()
    if not rows:
        return [], [{'code': 'EMPTY_FILE', 'message': 'This CSV file has no rows.'}]
    block = _block('csv_1', 'spreadsheet', '', confidence=0.99, source='csv',
                   sheet=Path(path).stem, rows=rows)
    return [block], []


# ---------- HTML ----------

def _span(value):
    try:
        return max(1, min(1000, int(value)))
    except (TypeError, ValueError):
        return 1


class _HtmlCollector(HTMLParser):
    """Walks an HTML page and collects headings, paragraphs, lists, tables and images in order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []     # (kind, text, extra) tuples, in page order
        self.skip = 0       # depth inside script, style and similar tags
        self.kind = None    # kind of the text block being collected
        self.kind_tag = None
        self.buf = []
        self.tables = []    # stack of tables (for nested tables)
        self.cell = None    # the cell being collected, if any

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if self.skip:
            return
        attrs = dict(attrs)
        if tag in TEXT_TAGS:
            self._flush()
            self.kind, self.kind_tag = TEXT_TAGS[tag], tag
        elif tag == 'table':
            self._flush()
            self.tables.append({'rows': [], 'row': None})
        elif tag == 'tr' and self.tables:
            self.tables[-1]['row'] = []
        elif tag in ('td', 'th') and self.tables:
            if self.tables[-1]['row'] is None:
                self.tables[-1]['row'] = []
            self.cell = {'buf': [], 'rowspan': _span(attrs.get('rowspan')),
                         'colspan': _span(attrs.get('colspan'))}
        elif tag == 'br':
            self._text('\n')
        elif tag == 'img':
            self._flush()
            alt = (attrs.get('alt') or '').strip() or 'Image'
            self.items.append(('figure', alt, {'src': attrs.get('src', '')}))

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == self.kind_tag:
            self._flush()
        elif tag in ('td', 'th') and self.cell is not None and self.tables:
            self.tables[-1]['row'].append({
                'text': _clean(''.join(self.cell['buf'])),
                'rowspan': self.cell['rowspan'],
                'colspan': self.cell['colspan'],
            })
            self.cell = None
        elif tag == 'tr' and self.tables and self.tables[-1]['row'] is not None:
            self.tables[-1]['rows'].append(self.tables[-1]['row'])
            self.tables[-1]['row'] = None
        elif tag == 'table' and self.tables:
            table = self.tables.pop()
            if table['rows']:
                self.items.append(('table', '', {'cells': table['rows']}))

    def handle_data(self, data):
        if not self.skip:
            self._text(data)

    def _text(self, text):
        if self.cell is not None:
            self.cell['buf'].append(text)
            return
        if self.kind is None:
            if not text.strip():
                return
            self.kind, self.kind_tag = 'paragraph', None
        self.buf.append(text)

    def _flush(self):
        text = _clean(''.join(self.buf))
        if text and self.kind:
            self.items.append((self.kind, text, {}))
        self.buf = []
        self.kind = None
        self.kind_tag = None

    def close(self):
        super().close()
        self._flush()


def html_blocks(html_text, source='html', prefix='h'):
    """Turn HTML text into blocks. Table cells keep their rowspan and colspan."""
    collector = _HtmlCollector()
    collector.feed(html_text)
    collector.close()

    blocks = []
    for i, (kind, text, extra) in enumerate(collector.items, 1):
        block_id = f'{prefix}_{i}'
        if kind == 'table':
            cells = extra['cells']
            rows = [[c['text'] for c in row] for row in cells]
            blocks.append(Block(id=block_id, type='table', page=1, text='', confidence=0.97,
                                source=source, metadata={'rows': rows, 'cells': cells}))
        elif kind == 'figure':
            blocks.append(Block(id=block_id, type='figure', page=1, text=text, confidence=0.9,
                                source=source, metadata={'src': extra.get('src', '')}))
        else:
            blocks.append(Block(id=block_id, type=kind, page=1, text=text, confidence=0.97,
                                source=source))
    return blocks


def parse_html_file(path):
    return html_blocks(read_text(path), source='html'), []


# ---------- RTF (basic) ----------

def parse_rtf(path):
    """A basic RTF reader: keeps the words and paragraph breaks, drops formatting."""
    text = read_text(path)
    text = re.sub(r'\{\\\*[^{}]*\}', ' ', text)                                   # ignorable groups
    text = re.sub(r'\{\\(?:fonttbl|colortbl|stylesheet|info|pict)(?:[^{}]|\{[^{}]*\})*\}', ' ', text)
    text = re.sub(r"\\'([0-9a-fA-F]{2})",
                  lambda m: bytes.fromhex(m.group(1)).decode('cp1252', errors='replace'), text)
    text = re.sub(r'\\(?:par|line|row)\b ?', '\n', text)
    text = re.sub(r'\\tab\b ?', '\t', text)
    text = re.sub(r'\\[a-zA-Z]+-?\d* ?', '', text)                               # control words
    text = re.sub(r'\\([{}\\])', r'\1', text)                                    # escaped symbols
    text = re.sub(r'[{}]', '', text)

    blocks = []
    for line in text.split('\n'):
        cleaned = line.strip()
        if cleaned:
            blocks.append(_block(f'rtf_{len(blocks) + 1}', 'paragraph', cleaned, source='rtf'))
    return blocks, []


# ---------- Email ----------

def parse_email(path, parse_child):
    """Read an .eml email: its header, its body, and every attachment.

    parse_child(path) reads one file with the normal rules and returns
    (format, (pages, blocks, markdown, errors, status)). Attachments can
    hold emails too, so this is called recursively.
    """
    message = email.message_from_bytes(Path(path).read_bytes(), policy=policy.default)
    blocks, errors = [], []

    def add(kind, text, **metadata):
        blocks.append(_block(f'eml_{len(blocks) + 1}', kind, text, source='email', **metadata))

    subject = str(message.get('subject', '') or '').strip()
    if subject:
        add('heading', subject)
    for label in ('from', 'to', 'cc', 'date'):
        value = message.get(label)
        if value:
            add('paragraph', f'{label.capitalize()}: {str(value).strip()}')

    body = message.get_body(preferencelist=('plain', 'html'))
    if body is not None:
        content = body.get_content()
        if body.get_content_type() == 'text/html':
            blocks.extend(html_blocks(content, source='email', prefix='eml_html'))
        else:
            blocks.extend(_paragraph_blocks(content, 'eml_body', 'email'))

    attachments = list(message.iter_attachments())
    if attachments:
        with tempfile.TemporaryDirectory() as folder:
            for number, part in enumerate(attachments, 1):
                name = part.get_filename() or f'attachment_{number}'
                target = Path(folder) / f'{number}_{safe_name(name) or "file"}'
                target.write_bytes(part.get_payload(decode=True) or b'')
                try:
                    _, (_pages, child_blocks, _md, child_errors, _status) = parse_child(str(target))
                except Exception as exc:
                    errors.append({'code': 'ATTACHMENT_FAILED', 'attachment': name,
                                   'message': f'Could not read attachment "{name}": {exc}'})
                    add('footnote', f'Attachment "{name}" could not be read.')
                    continue

                add('heading', f'Attachment: {name}')
                for child in child_blocks:
                    blocks.append(child.model_copy(update={
                        'id': f'att{number}_{child.id}',
                        'metadata': {**child.metadata, 'attachment': name},
                    }))
                errors.extend({**err, 'attachment': name} for err in child_errors)

    return blocks, errors
