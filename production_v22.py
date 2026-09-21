from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from PIL import Image, ImageDraw
import json, math, datetime

APP_VERSION = "V22"

class PackingError(ValueError):
    pass

@dataclass
class ItemSpec:
    path: str
    name: str
    quantity: int = 1
    width_mm: float = 100.0
    allow_rotate: bool = True

@dataclass
class Placement:
    index: int
    name: str
    copy: int
    x: int
    y: int
    w: int
    h: int
    rotated: bool


def mm_to_px(mm, dpi):
    return max(1, int(round(float(mm) * int(dpi) / 25.4)))


def _safe(s):
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(s)).strip('_') or 'artwork'


def trim_transparent(im, alpha_threshold=4):
    """Crop transparent margins. If no meaningful alpha exists, keep the full image."""
    im = im.convert('RGBA')
    a = im.getchannel('A')
    bbox = a.point(lambda p: 255 if p > alpha_threshold else 0).getbbox()
    return im.crop(bbox) if bbox else im


def prepare_item(spec: ItemSpec, dpi=300, alpha_threshold=4):
    p = Path(spec.path)
    if not p.exists():
        raise PackingError(f'File not found: {p}')
    im = trim_transparent(Image.open(p), alpha_threshold)
    target_w = mm_to_px(spec.width_mm, dpi)
    if target_w < 1:
        raise PackingError(f'Invalid width for {spec.name}')
    scale = target_w / max(1, im.width)
    target_h = max(1, int(round(im.height * scale)))
    im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
    return im


def _pack_shelves(items, sheet_w, sheet_h, margin, gap):
    """Deterministic shelf packing with optional 90° rotation and alpha-trimmed bounds."""
    usable_w, usable_h = sheet_w - 2*margin, sheet_h - 2*margin
    if usable_w <= 0 or usable_h <= 0:
        raise PackingError('Sheet is smaller than the requested margins.')
    placements=[]
    x=margin; y=margin; row_h=0
    for idx, spec, im in items:
        candidates=[(im,False)]
        if spec.allow_rotate and im.width != im.height:
            candidates.append((im.rotate(90,expand=True),True))
        # Prefer orientation that fits current row and wastes less row height.
        candidates.sort(key=lambda t: (0 if x+t[0].width <= sheet_w-margin and y+t[0].height <= sheet_h-margin else 1,
                                       max(row_h,t[0].height)-row_h,
                                       t[0].width))
        placed=False
        for candidate,rot in candidates:
            cw,ch=candidate.size
            if x+cw <= sheet_w-margin and y+ch <= sheet_h-margin:
                placements.append((idx,spec,im,x,y,cw,ch,rot))
                x += cw + gap; row_h=max(row_h,ch); placed=True; break
        if not placed:
            y += row_h + gap; x=margin; row_h=0
            for candidate,rot in candidates:
                cw,ch=candidate.size
                if x+cw <= sheet_w-margin and y+ch <= sheet_h-margin:
                    placements.append((idx,spec,im,x,y,cw,ch,rot)); x += cw+gap; row_h=max(row_h,ch); placed=True; break
        if not placed:
            raise PackingError(f'Artwork does not fit on sheet: {spec.name}. Reduce width or quantity.')
    return placements


def pack_designs(specs, sheet_width_mm=330.2, sheet_height_mm=482.6, dpi=300,
                 margin_mm=8, gap_mm=5, background='white', alpha_threshold=4):
    dpi=int(dpi); W=mm_to_px(sheet_width_mm,dpi); H=mm_to_px(sheet_height_mm,dpi)
    margin=mm_to_px(margin_mm,dpi); gap=mm_to_px(gap_mm,dpi)
    expanded=[]; cache={}
    copy_counter={}
    for idx,spec in enumerate(specs):
        q=max(1,int(spec.quantity)); copy_counter[idx]=q
        key=(spec.path,float(spec.width_mm),dpi,alpha_threshold)
        if key not in cache: cache[key]=prepare_item(spec,dpi,alpha_threshold)
        for _ in range(q): expanded.append((idx,spec,cache[key]))
    # Larger areas first makes the shelf pack substantially less wasteful than input order.
    expanded.sort(key=lambda x: x[2].width*x[2].height, reverse=True)
    pages=[]; placements_all=[]; remaining=list(expanded); page_no=1
    while remaining:
        # Pack as many as possible, preserving original spec references.
        current=[]
        # Greedy attempt; if an item fails on an empty page it is genuinely too large.
        for entry in list(remaining):
            try:
                test=_pack_shelves(current+[entry],W,H,margin,gap)
                current.append(entry)
            except PackingError:
                if not current:
                    _,bad,im=entry
                    raise PackingError(f'{bad.name} ({bad.width_mm:g} mm wide) is too large for the selected sheet.')
        if not current: break
        selected_ids={id(e) for e in current}
        remaining=[e for e in remaining if id(e) not in selected_ids]
        placements=_pack_shelves(current,W,H,margin,gap)
        pages.append((current,placements)); page_no+=1
    return pages, {'sheet_px':[W,H], 'dpi':dpi, 'margin_mm':margin_mm, 'gap_mm':gap_mm,
                   'pages':len(pages), 'designs':len(specs), 'copies':sum(max(1,int(s.quantity)) for s in specs),
                   'alpha_trim':True}


def render_page(current, packed, sheet_size, dpi, background='white', show_labels=True, show_marks=False):
    W,H=sheet_size
    bg=(255,255,255,255) if background=='white' else (0,0,0,0)
    sheet=Image.new('RGBA',(W,H),bg)
    draw=ImageDraw.Draw(sheet)
    per_design_copy={}
    for idx,spec,im,x,y,w,h,rot in packed:
        use=im.rotate(90,expand=True,resample=Image.Resampling.BICUBIC) if rot else im
        sheet.alpha_composite(use,(x,y))
        per_design_copy[idx]=per_design_copy.get(idx,0)+1
        if show_labels:
            txt=f'{spec.name} #{per_design_copy[idx]}'
            draw.rectangle((x,max(0,y-22),min(W,x+max(w,180)),y),fill=(255,255,255,230))
            draw.text((x+4,max(0,y-20)),txt,fill=(0,0,0,255))
        if show_marks:
            cx,cy=x+w//2,y+h//2; r=max(5,min(18,min(w,h)//30))
            draw.line((cx-r,cy,cx+r,cy),fill=(0,0,0,255),width=2)
            draw.line((cx,cy-r,cx,cy+r),fill=(0,0,0,255),width=2)
    return sheet


def calculate_utilization(packed, sheet_size, margin, gap=0):
    W,H=sheet_size; usable=max(1,(W-2*margin)*(H-2*margin))
    used=sum(p[5]*p[6] for p in packed)
    return {'used_px2':used,'usable_px2':usable,'utilization_percent':round(100*used/usable,2),
            'waste_percent':round(max(0,100-used/usable*100),2)}


def export_gang_package(specs, out_dir, sheet_width_mm=330.2, sheet_height_mm=482.6, dpi=300,
                        margin_mm=8, gap_mm=5, background='white', show_labels=True,
                        show_marks=False, alpha_threshold=4):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    pages,meta=pack_designs(specs,sheet_width_mm,sheet_height_mm,dpi,margin_mm,gap_mm,background,alpha_threshold)
    W,H=meta['sheet_px']; margin=mm_to_px(margin_mm,dpi)
    outputs=[]; page_stats=[]
    for n,(current,packed) in enumerate(pages,1):
        sheet=render_page(current,packed,(W,H),dpi,background,show_labels,show_marks)
        p=out/f'gang_sheet_{n:02d}.png'; sheet.save(p,'PNG',dpi=(dpi,dpi)); outputs.append(p.name)
        page_stats.append(calculate_utilization(packed,(W,H),margin,gap_mm))
    manifest={'app':'Image Studio','version':APP_VERSION,'created':datetime.datetime.now().isoformat(timespec='seconds'),
              'options':{'sheet_width_mm':sheet_width_mm,'sheet_height_mm':sheet_height_mm,'dpi':dpi,'margin_mm':margin_mm,
                         'gap_mm':gap_mm,'background':background,'show_labels':show_labels,'show_marks':show_marks,
                         'alpha_threshold':alpha_threshold},
              'designs':[asdict(s) for s in specs], 'layout':meta, 'page_stats':page_stats, 'outputs':outputs}
    (out/'gang_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest

class JobQueue:
    """Small persistent queue for repeatable gang-sheet exports."""
    def __init__(self): self.jobs=[]
    def add(self,name,specs,settings): self.jobs.append({'name':name,'specs':[asdict(s) for s in specs],'settings':settings,'status':'queued'})
    def to_json(self,path): Path(path).write_text(json.dumps({'version':APP_VERSION,'jobs':self.jobs},indent=2),encoding='utf-8')
    def load_json(self,path): self.jobs=json.loads(Path(path).read_text(encoding='utf-8')).get('jobs',[]); return self.jobs
