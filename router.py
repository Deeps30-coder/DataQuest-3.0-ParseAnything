"""Finds the right reader for each uploaded file.

Files are checked by their contents as well as their name. Old Word, Excel and
PowerPoint files are converted to the newer format with LibreOffice first, when
it is installed. Emails are read recursively, so attachments follow the same rules.
"""
import shutil
import subprocess
import zipfile
from pathlib import Path

from .pdf_parser import parse_pdf, blocks_to_markdown
from .office_parser import parse_docx, parse_xlsx, parse_pptx
from .image_parser import parse_image
from .text_parsers import (parse_txt, parse_markdown, parse_csv, parse_html_file,
                           parse_rtf, parse_email)

MAX_DEPTH = 3
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.heic'}
MODERN_EXTS = {'.pdf', '.docx', '.xlsx', '.pptx'}
LEGACY_EXTS = {'.doc': 'docx', '.xls': 'xlsx', '.ppt': 'pptx'}
TEXT_READERS = {
    '.txt': parse_txt, '.md': parse_markdown, '.markdown': parse_markdown,
    '.csv': parse_csv, '.html': parse_html_file, '.htm': parse_html_file,
    '.rtf': parse_rtf, '.eml': parse_email,
}
SUPPORTED = MODERN_EXTS | IMAGE_EXTS | set(LEGACY_EXTS) | set(TEXT_READERS)

READERS = {'docx': parse_docx, 'xlsx': parse_xlsx, 'pptx': parse_pptx}
HEIC_BRANDS = {b'heic', b'heix', b'hevc', b'heim', b'mif1', b'msf1'}


def sniff(path):
    """Look at the first bytes of a file to guess its real type."""
    with open(path, 'rb') as f:
        head = f.read(12)
    if head.startswith(b'%PDF'):
        return 'pdf'
    if head.startswith(b'\x89PNG') or head[:3] == b'\xff\xd8\xff' or head[:4] in (b'II*\x00', b'MM\x00*') or head[:2] == b'BM':
        return 'image'
    if head[4:8] == b'ftyp' and head[8:12] in HEIC_BRANDS:
        return 'image'
    if head.startswith(b'PK\x03\x04'):
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            return None
        if 'word/document.xml' in names:
            return 'docx'
        if 'xl/workbook.xml' in names:
            return 'xlsx'
        if 'ppt/presentation.xml' in names:
            return 'pptx'
        return None
    if head.startswith(b'\xd0\xcf\x11\xe0'):
        return 'legacy'  # old .doc, .xls or .ppt (all share this header)
    return None


def is_scanned(blocks):
    """A PDF counts as scanned when most of its pages had to be read with OCR."""
    ocr_pages = {b.page for b in blocks if b.source == 'ocr'}
    text_pages = {b.page for b in blocks if b.source == 'pdf_text'}
    return len(ocr_pages) > len(text_pages)


def convert_legacy(path, target):
    """Convert an old Office file to the newer format using LibreOffice."""
    exe = shutil.which('soffice') or shutil.which('libreoffice')
    if not exe:
        raise ValueError(
            'Old Office files (.doc, .xls, .ppt) need LibreOffice installed on the server. '
            'Save the file as .docx, .xlsx or .pptx and upload that instead.'
        )
    outdir = Path(path).parent / 'converted'
    outdir.mkdir(exist_ok=True)
    try:
        subprocess.run(
            [exe, '--headless', '--convert-to', target, '--outdir', str(outdir), str(path)],
            capture_output=True, timeout=180, check=False,
        )
    except subprocess.TimeoutExpired:
        raise ValueError('Converting this old file took too long. Try saving it as a newer format first.')
    out = outdir / (Path(path).stem + '.' + target)
    if not out.exists():
        raise ValueError('LibreOffice could not convert this file. Try saving it as a newer format first.')
    return str(out)


def _read_text_file(path, ext, depth):
    head = Path(path).read_bytes()[:4096]
    if b'\x00' in head:
        raise ValueError(f'This file is named {ext} but does not look like a text file.')
    if ext == '.rtf' and not head.lstrip().startswith(b'{\\rtf'):
        raise ValueError('This file is named .rtf but is not an RTF file.')

    if ext == '.eml':
        blocks, errors = parse_email(path, lambda child: parse_file(child, depth + 1))
    else:
        blocks, errors = TEXT_READERS[ext](path)

    markdown = blocks_to_markdown(blocks)
    status = 'partial' if errors else 'success'
    return ext[1:], (1, blocks, markdown, errors, status)


def parse_file(path, depth=0):
    """Read one file. Returns (format, (pages, blocks, markdown, errors, status))."""
    if depth > MAX_DEPTH:
        raise ValueError('Files are nested too deeply, for example emails inside emails.')

    ext = Path(path).suffix.lower()
    if ext == '.msg':
        raise ValueError('Outlook .msg files are not supported yet. Save the email as .eml and upload that instead.')
    if ext not in SUPPORTED:
        raise ValueError(f'Sorry, {ext or "this file type"} is not supported yet.')

    if ext in TEXT_READERS:
        return _read_text_file(path, ext, depth)

    found = sniff(path)
    if found is None:
        raise ValueError('Could not read this file. It may be damaged or in a format that is not supported.')

    if found == 'legacy':
        if ext not in LEGACY_EXTS:
            raise ValueError(f'This is an old Office file, but it is named {ext}. Check the file name and try again.')
        target = LEGACY_EXTS[ext]
        return ext[1:], READERS[target](convert_legacy(path, target))

    expected = 'image' if ext in IMAGE_EXTS else ext[1:]
    if found != expected:
        raise ValueError(
            f'The file contents look like a {found.upper()} file, but it is named {ext}. '
            'Check the file type and try again.'
        )

    if found == 'pdf':
        pages, blocks, markdown, errors, status = parse_pdf(path)
        label = 'scanned_pdf' if is_scanned(blocks) else 'unscanned_pdf'
        return label, (pages, blocks, markdown, errors, status)
    if found == 'image':
        return ext[1:], parse_image(path)
    return ext[1:], READERS[found](path)
