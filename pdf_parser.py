from __future__ import annotations
import io, re
from collections import defaultdict
import fitz
import pdfplumber
from PIL import Image
import pytesseract
from pytesseract import Output
from .models import Block, BoundingBox
from .utils import clamp


def _looks_like_heading(text: str, size: float, page_height: float) -> bool:
    t = text.strip()
    if not t: return False
    words = t.split()
    return size >= 14 or (len(words) <= 12 and t.isupper())


def _column_order(blocks, page_width):
    # Simple robust heuristic: detect a strong two-column split using x centers.
    if len(blocks) < 4:
        return sorted(blocks, key=lambda b: (b['bbox'][1], b['bbox'][0]))
    xs = sorted([(b['bbox'][0] + b['bbox'][2]) / 2 for b in blocks])
    gaps = [(xs[i+1]-xs[i], i) for i in range(len(xs)-1)]
    gap, idx = max(gaps, default=(0,0))
    if gap > page_width * 0.18:
        split = (xs[idx] + xs[idx+1]) / 2
        left = [b for b in blocks if ((b['bbox'][0]+b['bbox'][2])/2) < split]
        right = [b for b in blocks if ((b['bbox'][0]+b['bbox'][2])/2) >= split]
        # Avoid false columns when one side has almost everything.
        if min(len(left), len(right)) >= 2:
            return sorted(left, key=lambda b:(b['bbox'][1],b['bbox'][0])) + sorted(right, key=lambda b:(b['bbox'][1],b['bbox'][0]))
    return sorted(blocks, key=lambda b:(b['bbox'][1],b['bbox'][0]))


def _ocr_page(page, dpi=160):
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes('png')))
    data = pytesseract.image_to_data(img, output_type=Output.DICT)
    groups = defaultdict(list)
    for i, txt in enumerate(data['text']):
        txt = txt.strip()
        if not txt: continue
        try: conf = float(data['conf'][i]) / 100.0
        except: conf = 0.0
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        groups[key].append((txt, data['left'][i], data['top'][i], data['width'][i], data['height'][i], conf))
    sx = page.rect.width / img.width
    sy = page.rect.height / img.height
    blocks=[]
    for vals in groups.values():
        text=' '.join(v[0] for v in vals)
        x1=min(v[1] for v in vals)*sx; y1=min(v[2] for v in vals)*sy
        x2=max(v[1]+v[3] for v in vals)*sx; y2=max(v[2]+v[4] for v in vals)*sy
        conf=sum(v[5] for v in vals)/len(vals)
        blocks.append({'text':text,'bbox':(x1,y1,x2,y2),'confidence':clamp(conf),'type':'paragraph'})
    return blocks


def _mark_running_text(blocks, heights):
    """Tag short text that repeats at the top or bottom of most pages as a header or footer."""
    pages = len(heights)
    if pages < 3:
        return blocks

    def key(text):
        return re.sub(r'\d+', '#', re.sub(r'\s+', ' ', text.lower())).strip()

    zone = []
    for b in blocks:
        if b.type in ('table', 'figure') or b.bbox is None or not b.text.strip():
            continue
        if len(b.text.split()) > 12:
            continue
        h = heights.get(b.page)
        if not h:
            continue
        if b.bbox.y2 <= h * 0.08:
            zone.append((b, 'header'))
        elif b.bbox.y1 >= h * 0.92:
            zone.append((b, 'footer'))

    seen = defaultdict(set)
    for b, where in zone:
        seen[(key(b.text), where)].add(b.page)
    needed = max(2, -(-pages // 2))  # at least half of the pages, rounded up
    for b, where in zone:
        if len(seen[(key(b.text), where)]) >= needed:
            b.type = where
    return blocks


def parse_pdf(path: str):
    doc = fitz.open(path)
    blocks=[]; errors=[]
    try:
        with pdfplumber.open(path) as plumber:
            table_by_page={}
            for pi, p in enumerate(plumber.pages, start=1):
                try: table_by_page[pi]=p.extract_tables() or []
                except Exception as e: table_by_page[pi]=[]
    except Exception as e:
        table_by_page={}; errors.append({'code':'TABLE_ENGINE_ERROR','message':str(e)})

    heights={}
    for pidx, page in enumerate(doc, start=1):
        heights[pidx]=page.rect.height
        page_blocks=[]
        text_blocks=page.get_text('dict').get('blocks', [])
        meaningful=0
        for b in text_blocks:
            if b.get('type') != 0: continue
            lines=b.get('lines',[])
            text='\n'.join(''.join(s.get('text','') for s in ln.get('spans',[])) for ln in lines).strip()
            if not text: continue
            meaningful += len(text)
            bbox=tuple(b['bbox'])
            max_size=max((s.get('size',0) for ln in lines for s in ln.get('spans',[])), default=0)
            typ='heading' if _looks_like_heading(text,max_size,page.rect.height) else ('list' if re.match(r'^\s*(?:[-*•]|\d+[.)])\s+',text) else 'paragraph')
            page_blocks.append({'text':text,'bbox':bbox,'confidence':0.98,'type':typ})

        if meaningful < 20:
            try:
                page_blocks=_ocr_page(page)
            except Exception as e:
                errors.append({'code':'OCR_FAILED','page':pidx,'message':str(e)})
                page_blocks=[]

        page_blocks=_column_order(page_blocks,page.rect.width)
        for j,b in enumerate(page_blocks,1):
            blocks.append(Block(id=f'p{pidx}_b{j}',type=b['type'],page=pidx,text=b['text'],bbox=BoundingBox(x1=b['bbox'][0],y1=b['bbox'][1],x2=b['bbox'][2],y2=b['bbox'][3]),confidence=b['confidence'],source='pdf_text' if meaningful>=20 else 'ocr'))

        # Add tables as structured blocks. Coordinates are best-effort page-level metadata.
        for ti, table in enumerate(table_by_page.get(pidx, []),1):
            if not table: continue
            rows=[]
            for row in table:
                rows.append([c.strip() if isinstance(c,str) else '' for c in (row or [])])
            blocks.append(Block(id=f'p{pidx}_t{ti}',type='table',page=pidx,text='',confidence=0.90,source='pdfplumber',metadata={'rows':rows}))

        # Images/figures are recorded even when semantic understanding is unavailable.
        if page.get_images(full=True):
            blocks.append(Block(id=f'p{pidx}_fig1',type='figure',page=pidx,text='[Embedded figure/image detected]',confidence=0.75,source='pdf_image_detection',status='ambiguous',metadata={'image_count':len(page.get_images(full=True))}))

    blocks = _mark_running_text(blocks, heights)
    md = blocks_to_markdown(blocks)
    status='partial' if errors or any(b.status!='ok' for b in blocks) else 'success'
    return len(doc), blocks, md, errors, status


def _table_md(out, rows):
    if not rows:
        return
    width = max(len(r) for r in rows)
    clean = [[str(c).replace('|', '\\|').replace('\n', ' ') for c in r] + [''] * (width - len(r)) for r in rows]
    out.append('| ' + ' | '.join(clean[0]) + ' |')
    out.append('| ' + ' | '.join(['---'] * width) + ' |')
    for r in clean[1:]:
        out.append('| ' + ' | '.join(r) + ' |')
    out.append('')


def blocks_to_markdown(blocks):
    out = []; last_page = None
    for b in sorted(blocks, key=lambda x: (x.page, x.bbox.y1 if x.bbox else 1e9, x.bbox.x1 if x.bbox else 1e9)):
        if b.type in ('header', 'footer'):
            continue  # running headers and footers stay out of the body
        if b.type == 'spreadsheet':
            out.append(f"\n### Sheet: {b.metadata.get('sheet', 'Untitled')}\n")
            _table_md(out, b.metadata.get('rows', []))
            continue
        if b.page != last_page:
            out.append(f'\n## Page {b.page}\n'); last_page = b.page
        if b.type == 'heading':
            out.append(f'### {b.text}\n')
        elif b.type == 'list':
            out.append(f'- {b.text}\n')
        elif b.type == 'table':
            _table_md(out, b.metadata.get('rows', []))
        elif b.type == 'figure':
            out.append(f'*[Figure: {b.text or "image"}]*\n')
        elif b.type == 'caption':
            out.append(f'*{b.text}*\n')
        elif b.type == 'equation':
            out.append(f'$$\n{b.text}\n$$\n')
        elif b.type == 'footnote':
            out.append(f'> {b.text}\n')
        else:
            out.append(f'{b.text}\n')
    return '\n'.join(out)
