from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json, math, datetime

APP_VERSION = "V21"

class LayoutError(ValueError):
    pass

def mm_to_px(mm: float, dpi: int) -> int:
    return max(1, int(round(float(mm) * dpi / 25.4)))

def _safe_name(name: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in name).strip('_') or 'artwork'

def _registration_mark(size, stroke=2):
    w,h=size
    layer=Image.new('RGBA', size, (0,0,0,0)); d=ImageDraw.Draw(layer)
    r=max(8,min(24,int(min(w,h)*0.025))); cx,cy=w//2,h//2
    d.line((cx-r,cy,cx+r,cy), fill=(0,0,0,255), width=stroke)
    d.line((cx,cy-r,cx,cy+r), fill=(0,0,0,255), width=stroke)
    d.ellipse((cx-5,cy-5,cx+5,cy+5), outline=(0,0,0,255), width=stroke)
    return layer

def _corner_marks(canvas, margin, stroke=2):
    layer=Image.new('RGBA',canvas,(0,0,0,0)); d=ImageDraw.Draw(layer)
    w,h=canvas; L=max(15,int(min(w,h)*0.012)); m=max(8,margin)
    for x,y in [(m,m),(w-m,m),(w-m,h-m),(m,h-m)]:
        d.line((x-L,y,x+L,y),fill=(0,0,0,255),width=stroke)
        d.line((x,y-L,x,y+L),fill=(0,0,0,255),width=stroke)
        d.ellipse((x-4,y-4,x+4,y+4),outline=(0,0,0,255),width=stroke)
    return layer

def _label(draw, xy, text, font=None):
    try: draw.text(xy,text,fill=(0,0,0,255),font=font)
    except Exception: draw.text(xy,text,fill=(0,0,0,255))

def make_print_sheet(im: Image.Image, sheet_width_mm=330, sheet_height_mm=480, dpi=300,
                     copies=1, gap_mm=5, margin_mm=8, rotate=False,
                     show_marks=True, labels=True, background='white'):
    if im is None: raise LayoutError('No artwork supplied.')
    dpi=int(dpi); copies=int(copies)
    if copies < 1: raise LayoutError('Copies must be at least 1.')
    W,H=mm_to_px(sheet_width_mm,dpi),mm_to_px(sheet_height_mm,dpi)
    margin=mm_to_px(margin_mm,dpi); gap=mm_to_px(gap_mm,dpi)
    if W<=2*margin or H<=2*margin: raise LayoutError('Sheet is smaller than margins.')
    art=im.convert('RGBA')
    if rotate: art=art.rotate(90,expand=True,resample=Image.Resampling.BICUBIC)
    avail_w,avail_h=W-2*margin,H-2*margin
    cols=max(1,int((avail_w+gap)/(art.width+gap)))
    rows=max(1,int((avail_h+gap)/(art.height+gap)))
    per_page=cols*rows
    pages=math.ceil(copies/per_page)
    results=[]
    for page in range(pages):
        bg=(255,255,255,255) if background=='white' else (0,0,0,0)
        sheet=Image.new('RGBA',(W,H),bg)
        count=min(per_page,copies-page*per_page)
        d=ImageDraw.Draw(sheet)
        placed=[]
        for i in range(count):
            col=i%cols; row=i//cols
            x=margin+col*(art.width+gap); y=margin+row*(art.height+gap)
            if x+art.width>W-margin or y+art.height>H-margin: continue
            sheet.alpha_composite(art,(x,y)); placed.append((x,y,art.width,art.height))
            if show_marks:
                rm=_registration_mark((art.width,art.height)); sheet.alpha_composite(rm,(x,y))
            if labels:
                _label(d,(x,y+art.height+2),f'#{page*per_page+i+1}')
        if show_marks: sheet.alpha_composite(_corner_marks((W,H),margin))
        results.append((sheet,placed))
    return results, {'sheet_px':[W,H],'dpi':dpi,'columns':cols,'rows':rows,'per_page':per_page,'pages':pages,
                     'placed_total':copies,'gap_mm':gap_mm,'margin_mm':margin_mm,'rotated':bool(rotate)}

def save_layout_package(im, out_dir, **kwargs):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    pages,meta=make_print_sheet(im,**kwargs)
    outputs=[]
    for i,(sheet,_) in enumerate(pages,1):
        p=out/f'print_sheet_{i:02d}.png'; sheet.save(p,'PNG',dpi=(meta['dpi'],meta['dpi'])); outputs.append(p.name)
    manifest={'app':'Image Studio','version':APP_VERSION,'created':datetime.datetime.now().isoformat(timespec='seconds'),
              'options':kwargs,'layout':meta,'outputs':outputs}
    (out/'layout_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest

DEFAULT_PRESETS={
    'A4 300dpi': {'sheet_width_mm':210,'sheet_height_mm':297,'dpi':300,'gap_mm':5,'margin_mm':8},
    'A3 300dpi': {'sheet_width_mm':297,'sheet_height_mm':420,'dpi':300,'gap_mm':5,'margin_mm':10},
    '12x18 in 300dpi': {'sheet_width_mm':304.8,'sheet_height_mm':457.2,'dpi':300,'gap_mm':5,'margin_mm':8},
    '13x19 in 300dpi': {'sheet_width_mm':330.2,'sheet_height_mm':482.6,'dpi':300,'gap_mm':5,'margin_mm':8},
}

def save_preset(path, name, settings):
    p=Path(path); data={}
    if p.exists():
        try: data=json.loads(p.read_text(encoding='utf-8'))
        except Exception: data={}
    data[name]=settings
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(data,indent=2),encoding='utf-8')
    return p
