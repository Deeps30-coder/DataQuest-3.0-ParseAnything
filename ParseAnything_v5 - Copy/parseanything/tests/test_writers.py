import json

from app.models import Block
from app.text_parsers import html_blocks
from app.writers import to_html, write_outputs


def test_html_output_keeps_spans():
    blocks = html_blocks('<table><tr><td colspan="2">Total</td></tr></table>')
    page = to_html(blocks)
    assert 'colspan="2"' in page
    assert '<table>' in page


def test_header_and_footer_are_left_out_of_html():
    blocks = [
        Block(id='h1', type='header', page=1, text='Running header', confidence=0.9),
        Block(id='p1', type='paragraph', page=1, text='Body text', confidence=0.9),
    ]
    page = to_html(blocks)
    assert 'Running header' not in page
    assert 'Body text' in page


def test_write_outputs_creates_three_files(tmp_path):
    blocks = [Block(id='p1', type='paragraph', page=1, text='Hi', confidence=0.9)]
    write_outputs('doc', tmp_path, {'filename': 'doc.txt'}, '# Hi', blocks, title='doc.txt')
    assert json.loads((tmp_path / 'doc.json').read_text(encoding='utf-8'))['filename'] == 'doc.txt'
    assert (tmp_path / 'doc.md').read_text(encoding='utf-8') == '# Hi'
    assert '<p' in (tmp_path / 'doc.html').read_text(encoding='utf-8')
