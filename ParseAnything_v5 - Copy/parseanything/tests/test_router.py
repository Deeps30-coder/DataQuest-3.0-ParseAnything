import pytest
from app.router import SUPPORTED, parse_file


def test_supported_formats():
    for ext in ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.png', '.jpg', '.jpeg', '.tif', '.bmp']:
        assert ext in SUPPORTED


def test_unsupported_extension_is_rejected(tmp_path):
    f = tmp_path / 'notes.xyz'
    f.write_text('hello')
    with pytest.raises(ValueError):
        parse_file(str(f))


def test_content_that_does_not_match_extension_is_rejected(tmp_path):
    f = tmp_path / 'fake.pdf'
    f.write_text('this is plain text, not a PDF')
    with pytest.raises(ValueError):
        parse_file(str(f))


from app.models import Block
from app.router import is_scanned

def _b(page, source):
    return Block(id=f'p{page}_b1', type='paragraph', page=page, text='x', confidence=0.9, source=source)

def test_scanned_when_most_pages_use_ocr():
    blocks = [_b(1, 'ocr'), _b(2, 'ocr'), _b(3, 'pdf_text')]
    assert is_scanned(blocks) is True

def test_unscanned_when_text_layer_is_used():
    blocks = [_b(1, 'pdf_text'), _b(2, 'pdf_text'), _b(3, 'ocr')]
    assert is_scanned(blocks) is False
