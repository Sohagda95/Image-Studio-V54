from __future__ import annotations
from pathlib import Path
import json, hashlib, datetime
from PIL import Image, ImageOps

APP_VERSION='V26'
IMAGE_EXTS={'.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'}

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def sha256(path, chunk=1024*1024):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(chunk),b''): h.update(b)
    return h.hexdigest()

def average_hash(path, size=16):
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im).convert('L').resize((size,size))
        px=list(im.getdata()); avg=sum(px)/len(px)
        bits=''.join('1' if p>=avg else '0' for p in px)
        return hex(int(bits,2))[2:].zfill((size*size+3)//4)

def image_info(path):
    p=Path(path); st=p.stat()
    with Image.open(p) as im:
        dpi=im.info.get('dpi',(0,0)); dpi_x=float(dpi[0] or 0) if isinstance(dpi,(tuple,list)) else 0
        dpi_y=float(dpi[1] or 0) if isinstance(dpi,(tuple,list)) else dpi_x
        alpha=im.mode in ('RGBA','LA') or ('transparency' in im.info)
        return {'path':str(p.resolve()),'name':p.name,'stem':p.stem,'suffix':p.suffix.lower(),'bytes':st.st_size,
                'width_px':im.width,'height_px':im.height,'mode':im.mode,'alpha':alpha,
                'dpi_x':round(dpi_x,2),'dpi_y':round(dpi_y,2),'modified':datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds'),
                'sha256':sha256(p),'ahash':average_hash(p)}

def scan_folder(root, recursive=True):
    root=Path(root); it=root.rglob('*') if recursive else root.glob('*')
    out=[]
    for p in it:
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            try: out.append(image_info(p))
            except Exception: pass
    return sorted(out,key=lambda x:x['name'].lower())

def scan_paths(paths, recursive=True):
    files=[]
    for raw in paths:
        p=Path(raw)
        if p.is_dir(): files.extend(scan_folder(p,recursive))
        elif p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            try: files.append(image_info(p))
            except Exception: pass
    # exact duplicates by SHA are collapsed in display, but preserved as duplicate groups
    return files

def duplicate_groups(items, near=True):
    exact={}
    for x in items: exact.setdefault(x['sha256'],[]).append(x['path'])
    exact=[v for v in exact.values() if len(v)>1]
    near_groups=[]
    if near:
        buckets={}
        for x in items: buckets.setdefault(x['ahash'],[]).append(x['path'])
        near_groups=[v for v in buckets.values() if len(v)>1]
    return {'exact':exact,'near':near_groups}

def save_library(path, items, favorites=None):
    Path(path).write_text(json.dumps({'version':APP_VERSION,'saved_at':now(),'items':items,'favorites':sorted(favorites or [])},indent=2,ensure_ascii=False),encoding='utf-8')

def load_library(path):
    d=json.loads(Path(path).read_text(encoding='utf-8'))
    return d.get('items',[]), set(d.get('favorites',[]))

def make_library_report(items):
    dups=duplicate_groups(items)
    total=sum(x.get('bytes',0) for x in items)
    return {'version':APP_VERSION,'generated_at':now(),'count':len(items),'total_bytes':total,'total_mb':round(total/1048576,2),
            'favorites':0,'exact_duplicate_groups':len(dups['exact']),'near_duplicate_groups':len(dups['near']),'duplicates':dups}
