from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from PIL import Image
import hashlib, json, datetime, zipfile

APP_VERSION='V23'

@dataclass
class ValidationIssue:
    severity:str
    message:str
    path:str=''

@dataclass
class ArtworkRecord:
    path:str
    name:str
    width_px:int
    height_px:int
    dpi_x:float
    dpi_y:float
    width_mm_at_dpi:float
    height_mm_at_dpi:float
    alpha:bool
    alpha_bbox:tuple|None
    sha256:str
    duplicate_of:str=''


def read_dpi(im):
    d=im.info.get('dpi',(72,72))
    try:return float(d[0]),float(d[1])
    except:return 72.0,72.0

def alpha_bbox(im, threshold=4):
    if 'A' not in im.getbands(): return None
    return im.getchannel('A').point(lambda p:255 if p>threshold else 0).getbbox()

def file_sha256(path, chunk=1024*1024):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while True:
            b=f.read(chunk)
            if not b:break
            h.update(b)
    return h.hexdigest()

def inspect_artwork(path, target_dpi=300, alpha_threshold=4):
    p=Path(path)
    if not p.exists(): raise FileNotFoundError(str(p))
    with Image.open(p) as im:
        dpi_x,dpi_y=read_dpi(im); bbox=alpha_bbox(im,alpha_threshold)
        mmw=im.width/target_dpi*25.4; mmh=im.height/target_dpi*25.4
        return ArtworkRecord(str(p),p.stem,im.width,im.height,dpi_x,dpi_y,mmw,mmh,'A' in im.getbands(),bbox,file_sha256(p))

def validate_artworks(paths, target_dpi=300, min_dpi=150, max_width_mm=1000, max_height_mm=1000, alpha_threshold=4):
    issues=[]; records=[]; hashes={}
    for path in paths:
        try:r=inspect_artwork(path,target_dpi,alpha_threshold)
        except Exception as e:
            issues.append(ValidationIssue('ERROR',f'Cannot read artwork: {e}',str(path))); continue
        records.append(r)
        if r.dpi_x < min_dpi or r.dpi_y < min_dpi:
            issues.append(ValidationIssue('WARNING',f'Embedded DPI is {r.dpi_x:g}×{r.dpi_y:g}; below recommended minimum {min_dpi} DPI.',r.path))
        if r.width_mm_at_dpi>max_width_mm or r.height_mm_at_dpi>max_height_mm:
            issues.append(ValidationIssue('ERROR',f'Artwork exceeds maximum estimated size {max_width_mm:g}×{max_height_mm:g} mm at {target_dpi} DPI.',r.path))
        if not r.alpha:
            issues.append(ValidationIssue('INFO','No alpha channel; transparent-margin trimming may not remove a background.',r.path))
        if r.sha256 in hashes:
            r.duplicate_of=hashes[r.sha256]
            issues.append(ValidationIssue('WARNING',f'Duplicate file content detected: same SHA-256 as {r.duplicate_of}.',r.path))
        else: hashes[r.sha256]=r.path
    return records,issues

def validate_job(specs, sheet_width_mm, sheet_height_mm, dpi, margin_mm, gap_mm):
    issues=[]
    usable_w=sheet_width_mm-2*margin_mm; usable_h=sheet_height_mm-2*margin_mm
    if sheet_width_mm<=0 or sheet_height_mm<=0: issues.append(ValidationIssue('ERROR','Sheet dimensions must be positive.'))
    if margin_mm*2>=sheet_width_mm or margin_mm*2>=sheet_height_mm: issues.append(ValidationIssue('ERROR','Margins leave no usable sheet area.'))
    if gap_mm<0: issues.append(ValidationIssue('ERROR','Gap cannot be negative.'))
    if dpi<72 or dpi>1200: issues.append(ValidationIssue('WARNING','Unusual DPI selected; confirm your production workflow.'))
    for s in specs:
        if s.width_mm>usable_w and s.width_mm>usable_h: issues.append(ValidationIssue('ERROR',f'{s.name} width {s.width_mm:g} mm is larger than both usable sheet dimensions.'))
        if s.quantity<1: issues.append(ValidationIssue('ERROR',f'{s.name} has invalid quantity.'))
    return issues

def save_preset(path, name, settings):
    payload={'version':APP_VERSION,'name':name,'saved_at':datetime.datetime.now().isoformat(timespec='seconds'),'settings':settings}
    Path(path).write_text(json.dumps(payload,indent=2),encoding='utf-8')

def load_preset(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def make_job_report(records, issues, layout=None):
    errors=sum(i.severity=='ERROR' for i in issues); warnings=sum(i.severity=='WARNING' for i in issues)
    return {'version':APP_VERSION,'created':datetime.datetime.now().isoformat(timespec='seconds'),'summary':{'files':len(records),'errors':errors,'warnings':warnings,'ok':errors==0},'artworks':[asdict(r) for r in records],'issues':[asdict(i) for i in issues],'layout':layout or {}}

def export_report(path, report):
    Path(path).write_text(json.dumps(report,indent=2),encoding='utf-8')

def package_job(out_zip, files, report, preset=None):
    out=Path(out_zip); out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix('.report.json'); export_report(tmp,report)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(tmp,tmp.name)
        if preset: z.writestr('preset.json',json.dumps(preset,indent=2))
        for f in files:
            p=Path(f)
            if p.exists(): z.write(p,'artwork/'+p.name)
    tmp.unlink(missing_ok=True)
    return str(out)
