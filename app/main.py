from pathlib import Path
import time
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .router import parse_file
from .models import DocumentResult
from .utils import safe_name, sha256_file
from .writers import write_outputs

app=FastAPI(title='ParseAnything',version='1.1.0')
BASE=Path(__file__).resolve().parent.parent
UPLOADS=BASE/'uploads'; OUTPUTS=BASE/'outputs'
UPLOADS.mkdir(exist_ok=True); OUTPUTS.mkdir(exist_ok=True)
STATIC=Path(__file__).resolve().parent/'static'
MAX_UPLOAD_BYTES=50*1024*1024
app.mount('/static',StaticFiles(directory=STATIC),name='static')

@app.get('/',include_in_schema=False)
def home(): return FileResponse(STATIC/'index.html')

@app.get('/health')
def health(): return {'status':'ok','service':'ParseAnything'}

@app.post('/parse',response_model=DocumentResult)
async def parse_endpoint(file: UploadFile=File(...), save: bool=True):
    name=safe_name(file.filename or 'upload.bin'); path=UPLOADS/name
    data=await file.read()
    if len(data)>MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413,detail={'code':'FILE_TOO_LARGE','message':'This file is larger than 50 MB.'})
    path.write_bytes(data)
    started=time.time()
    try:
        fmt,(pages,blocks,md,errors,status)=parse_file(str(path))
        result=DocumentResult(filename=name,format=fmt,pages=pages,status=status,errors=errors,blocks=blocks,markdown=md)
        payload=result.model_dump(mode='json')
        payload['metadata']={'sha256':sha256_file(str(path)),'processing_seconds':round(time.time()-started,3)}
        if save:
            write_outputs(path.stem,OUTPUTS,payload,md,blocks,title=name)
        return result
    except Exception as e:
        raise HTTPException(status_code=422,detail={'code':'PARSE_FAILED','message':str(e)})
