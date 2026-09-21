from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw
import json, datetime, math

APP_VERSION = 'V32'

# Small, dependency-free color-management helpers. These are reference/preview calculations,
# not ICC profile transforms or RIP calibration.
def srgb_to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def rgb_to_xyz(rgb):
    r,g,b = [srgb_to_linear(float(v)) for v in rgb]
    return (
        r*0.4124564 + g*0.3575761 + b*0.1804375,
        r*0.2126729 + g*0.7151522 + b*0.0721750,
        r*0.0193339 + g*0.1191922 + b*0.9503041,
    )

def xyz_to_lab(xyz):
    x,y,z = xyz
    x /= 0.95047; y /= 1.00000; z /= 1.08883
    def f(t):
        return t ** (1/3) if t > 0.008856451679 else 7.787037*t + 16/116
    fx,fy,fz = f(x),f(y),f(z)
    return (116*fy-16, 500*(fx-fy), 200*(fy-fz))

def rgb_to_lab(rgb):
    return xyz_to_lab(rgb_to_xyz(rgb))

def delta_e76(a,b):
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))

def hex_to_rgb(value: str):
    s=value.strip().lstrip('#')
    if len(s)==3: s=''.join(ch*2 for ch in s)
    if len(s)!=6 or any(ch not in '0123456789abcdefABCDEF' for ch in s):
        raise ValueError('Use a valid HEX color such as #FF6600')
    return tuple(int(s[i:i+2],16) for i in (0,2,4))

def rgb_to_hex(rgb):
    return '#%02X%02X%02X' % tuple(max(0,min(255,int(v))) for v in rgb)

def palette_distance_report(palette, reference_rgb):
    ref_lab=rgb_to_lab(reference_rgb)
    rows=[]
    for i,c in enumerate(palette,1):
        lab=rgb_to_lab(c)
        rows.append({'index':i,'rgb':list(c),'hex':rgb_to_hex(c),'lab':[round(v,3) for v in lab],
                     'delta_e76':round(delta_e76(lab,ref_lab),3)})
    rows.sort(key=lambda r:r['delta_e76'])
    return rows

def sample_palette(im, count=8):
    # Deterministic median-cut palette from Pillow; alpha is composited over white for sampling.
    x=im.convert('RGBA')
    bg=Image.new('RGBA',x.size,(255,255,255,255)); bg.alpha_composite(x)
    q=bg.convert('RGB').quantize(colors=max(2,min(32,int(count))), method=Image.Quantize.MEDIANCUT)
    pal=q.getpalette()[:count*3]
    return [tuple(pal[i:i+3]) for i in range(0,len(pal),3) if len(pal[i:i+3])==3]

def spot_mask(im, reference_rgb, tolerance=12, alpha_only=True):
    from PIL import Image
    src=im.convert('RGBA')
    ref=rgb_to_lab(reference_rgb)
    out=Image.new('L',src.size,0)
    sp=src.load(); op=out.load()
    for y in range(src.height):
        for x in range(src.width):
            r,g,b,a=sp[x,y]
            if alpha_only and a==0: continue
            de=delta_e76(rgb_to_lab((r,g,b)),ref)
            if de <= tolerance:
                op[x,y]=a if alpha_only else 255
    return out

def mask_stats(mask):
    m=mask.convert('L'); hist=m.histogram(); total=m.width*m.height
    weighted=sum(i*c for i,c in enumerate(hist))/255.0
    hard=sum(hist[1:])
    return {'width_px':m.width,'height_px':m.height,'soft_coverage_pct':round(weighted/total*100,3) if total else 0,
            'nonzero_pixel_pct':round(hard/total*100,3) if total else 0}

def separation_diagnostics(masks, names):
    rows=[]
    for name,mask in zip(names,masks):
        s=mask_stats(mask)
        rows.append({'channel':str(name),**s})
    overlaps=[]
    for i in range(len(masks)):
        for j in range(i+1,len(masks)):
            a=masks[i].convert('L'); b=masks[j].convert('L')
            count=0; total=a.width*a.height
            ap=a.load(); bp=b.load()
            for y in range(a.height):
                for x in range(a.width):
                    if ap[x,y] and bp[x,y]: count += 1
            overlaps.append({'a':str(names[i]),'b':str(names[j]),'overlap_pct':round(count/total*100,3) if total else 0})
    return {'channels':rows,'pairwise_overlap':overlaps}

def make_lab_report(path, reference_rgb=None, palette=None, masks=None, names=None, tolerance=12):
    p=Path(path)
    report={'app':'Image Studio','version':APP_VERSION,'created':datetime.datetime.now().isoformat(timespec='seconds'),
            'reference':None,'palette':[],'separation_diagnostics':None,'notes':[
                'LAB/Delta-E values use sRGB + D65/2° reference math.',
                'This is a preview/diagnostic tool, not an ICC color-management engine or calibrated RIP.'
            ]}
    if reference_rgb is not None:
        lab=rgb_to_lab(reference_rgb)
        report['reference']={'rgb':list(reference_rgb),'hex':rgb_to_hex(reference_rgb),'lab':[round(v,3) for v in lab],'tolerance_delta_e76':tolerance}
    if palette is not None and reference_rgb is not None: report['palette']=palette_distance_report(palette,reference_rgb)
    if masks is not None and names is not None: report['separation_diagnostics']=separation_diagnostics(masks,names)
    p.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report
