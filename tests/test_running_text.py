from app.models import Block, BoundingBox
from app.pdf_parser import _mark_running_text


def _b(page, y, text):
    return Block(id=f'p{page}_{y}', type='paragraph', page=page, text=text, confidence=0.98,
                 source='pdf_text', bbox=BoundingBox(x1=50, y1=y, x2=500, y2=y + 12))


def test_repeated_top_and_bottom_lines_are_tagged():
    heights = {1: 800, 2: 800, 3: 800}
    blocks = []
    for page in (1, 2, 3):
        blocks.append(_b(page, 10, 'ACME Corp Annual Report'))
        blocks.append(_b(page, 770, f'Page {page} of 3'))
        blocks.append(_b(page, 300, f'Body text on page {page} with real content.'))
    out = _mark_running_text(blocks, heights)
    types = [b.type for b in out]
    assert types.count('header') == 3
    assert types.count('footer') == 3
    assert types.count('paragraph') == 3


def test_short_documents_are_left_alone():
    heights = {1: 800, 2: 800}
    blocks = [_b(1, 10, 'Title'), _b(2, 10, 'Title')]
    assert [b.type for b in _mark_running_text(blocks, heights)] == ['paragraph', 'paragraph']
