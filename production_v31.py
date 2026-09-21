from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw
import json, datetime, math, hashlib

APP_VERSION='V31'


def read_dpi(im):
    d=im.info.get('dpi',(72,72))
    try:return float(d[0]),float(d[1])
    except:return 72.0,72.0


def _bbox_area(im):
    if 'A' in im.getbands():
        b=im.getchannel('A').getbbox()
    else:
        # approximate visible artwork from non-near-white pixels
        rgb=im.convert('RGB')
        px=rgb.load(); xs=[]; ys=[]
        for y in range(0,rgb.height,max(1,rgb.height//600)):
            for x in range(0,rgb.width,max(1,rgb.width//600)):
                r,g,b=px[x,y]
                if min(r,g,b)<245:
                    xs.append(x); ys.append(y)
        b=(min(xs),min(ys),max(xs)+1,max(ys)+1) if xs else None
    return b


def analyze_artwork(path, target_dpi=300):
    p=Path(path)
    with Image.open(p) as im:
        dx,dy=read_dpi(im); w,h=im.size; b=_bbox_area(im)
        full=w*h; visible=(b[2]-b[0])*(b[3]-b[1]) if b else 0
        alpha_area=0; alpha_coverage=1.0
        if 'A' in im.getbands():
            a=im.getchannel('A'); hist=a.histogram(); alpha_area=sum(i*c for i,c in enumerate(hist))/255.0
            alpha_coverage=alpha_area/full if full else 0
        print_w=w/target_dpi*25.4; print_h=h/target_dpi*25.4
        return {
            'path':str(p),'name':p.stem,'format':im.format or p.suffix.upper().lstrip('.'),
            'width_px':w,'height_px':h,'dpi_x':dx,'dpi_y':dy,
            'target_dpi':target_dpi,'print_width_mm':round(print_w,2),'print_height_mm':round(print_h,2),
            'print_width_in':round(w/target_dpi,3),'print_height_in':round(h/target_dpi,3),
            'bbox':list(b) if b else None,'bbox_coverage_pct':round(visible/full*100,2) if full else 0,
            'alpha': 'A' in im.getbands(),'alpha_coverage_pct':round(alpha_coverage*100,2),
            'megapixels':round(full/1e6,3),'file_bytes':p.stat().st_size,
            'dpi_ok': dx>=target_dpi and dy>=target_dpi,
            'usable_at_target_dpi': bool(w>=target_dpi*1.0 and h>=target_dpi*1.0)
        }


def mask_coverage(mask):
    m=mask.convert('L'); hist=m.histogram(); total=m.width*m.height
    weighted=sum(i*c for i,c in enumerate(hist))/255.0
    return round(weighted/total*100,3) if total else 0.0


def estimate_channel_coverage(masks, names):
    return [{'channel':str(n),'coverage_pct':mask_coverage(m)} for n,m in zip(names,masks)]


def build_print_intelligence(path, channel_masks=None, channel_names=None, target_dpi=300, sheet_mm=None, garment='Black'):
    rec=analyze_artwork(path,target_dpi)
    out={'app':'Image Studio','version':APP_VERSION,'created':datetime.datetime.now().isoformat(timespec='seconds'),
         'artwork':rec,'garment':garment,'channel_coverage':[],'sheet':None,'warnings':[]}
    if channel_masks and channel_names:
        out['channel_coverage']=estimate_channel_coverage(channel_masks,channel_names)
    if sheet_mm:
        sw,sh=sheet_mm; aw,ah=rec['print_width_mm'],rec['print_height_mm']
        fit_x=max(0,int((sw)/(aw or 1))); fit_y=max(0,int((sh)/(ah or 1))); fit=max(0,fit_x*fit_y)
        used=fit*aw*ah; sheet_area=sw*sh
        out['sheet']={'width_mm':sw,'height_mm':sh,'max_rectangular_copies':fit,'estimated_artwork_area_mm2':round(aw*ah,2),'estimated_utilization_pct':round(used/sheet_area*100,2) if sheet_area else 0,'estimated_waste_pct':round(max(0,100-used/sheet_area*100),2) if sheet_area else 0}
    if rec['dpi_x']<target_dpi or rec['dpi_y']<target_dpi: out['warnings'].append('Embedded DPI is below target; physical print size at target DPI may be smaller than expected.')
    if rec['alpha'] and rec['alpha_coverage_pct']<1: out['warnings'].append('Artwork has sparse transparency; check edge quality before separation.')
    if rec['bbox_coverage_pct']<25: out['warnings'].append('Large empty canvas detected; trimming transparent/empty margins may improve gang-sheet efficiency.')
    if not out['channel_coverage']: out['warnings'].append('Channel coverage was not calculated because no separated masks were supplied.')
    return out


def garment_proof(im, garment='Black'):
    colors={'Black':(20,20,20,255),'White':(245,245,245,255),'Navy':(22,35,65,255),'Red':(110,25,30,255),'Royal Blue':(25,55,135,255),'Dark Gray':(55,55,60,255)}
    bg=colors.get(garment,(20,20,20,255)); x=im.convert('RGBA');
    if 'A' in x.getbands():
        base=Image.new('RGBA',x.size,bg); base.alpha_composite(x); return base
    base=Image.new('RGBA',x.size,bg); base.alpha_composite(x.convert('RGBA')); return base


def registration_overlay(size, marks=12):
    w,h=size; out=Image.new('RGBA',(w,h),(0,0,0,0)); d=ImageDraw.Draw(out); s=max(8,min(40,int(min(w,h)*0.025)))
    pts=[(s,s),(w-s,s),(s,h-s),(w-s,h-s),(w//2,s),(w//2,h-s),(s,h//2),(w-s,h//2)]
    for x,y in pts:
        d.line((x-s//2,y,x+s//2,y),fill=(255,0,255,255),width=2); d.line((x,y-s//2,x,y+s//2),fill=(255,0,255,255),width=2)
        d.ellipse((x-3,y-3,x+3,y+3),outline=(255,255,255,255),width=1)
    return out


def save_intelligence_report(path, report):
    p=Path(path); p.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8'); return str(p)
