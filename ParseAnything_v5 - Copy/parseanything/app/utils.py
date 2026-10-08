import os, re, hashlib
from pathlib import Path

def safe_name(name: str) -> str:
    name = Path(name).name
    return re.sub(r'[^A-Za-z0-9._-]+', '_', name)

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def clamp(v: float, lo=0.0, hi=1.0) -> float:
    return max(lo, min(hi, v))
