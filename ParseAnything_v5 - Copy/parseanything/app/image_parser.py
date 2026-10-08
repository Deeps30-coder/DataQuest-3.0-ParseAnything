from PIL import Image, UnidentifiedImageError
import pytesseract
from pytesseract import Output
from .models import Block, BoundingBox
from .utils import clamp

def open_image(path):
    """Open an image. HEIC phone photos need the pillow-heif package."""
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    try:
        return Image.open(path).convert('RGB')
    except UnidentifiedImageError as exc:
        raise ValueError('Could not open this image. HEIC photos need the pillow-heif package installed.') from exc


def parse_image(path):
    img=open_image(path)
    data=pytesseract.image_to_data(img,output_type=Output.DICT)
    lines={}
    for i,t in enumerate(data['text']):
        t=t.strip()
        if not t: continue
        key=(data['block_num'][i],data['par_num'][i],data['line_num'][i])
        lines.setdefault(key,[]).append(i)
    blocks=[]
    for n,idxs in enumerate(lines.values(),1):
        text=' '.join(data['text'][i].strip() for i in idxs)
        x1=min(data['left'][i] for i in idxs); y1=min(data['top'][i] for i in idxs)
        x2=max(data['left'][i]+data['width'][i] for i in idxs); y2=max(data['top'][i]+data['height'][i] for i in idxs)
        conf=sum(float(data['conf'][i]) for i in idxs if float(data['conf'][i])>=0)/len(idxs)/100
        status='ok' if conf>=0.75 else 'ambiguous'
        blocks.append(Block(id=f'p1_b{n}',type='paragraph',page=1,text=text,bbox=BoundingBox(x1=x1,y1=y1,x2=x2,y2=y2),confidence=clamp(conf),source='tesseract',status=status))
    md='\n\n'.join(b.text for b in blocks)
    return 1,blocks,md,[],'partial' if any(b.status!='ok' for b in blocks) else 'success'
