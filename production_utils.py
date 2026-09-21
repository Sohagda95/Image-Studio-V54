
from PIL import Image, ImageDraw, ImageOps, ImageFilter
import math

def add_registration_marks(canvas, margin=50, mark_size=18):
    out=canvas.convert("RGBA").copy()
    d=ImageDraw.Draw(out)
    w,h=out.size
    points=[(margin,margin),(w-margin,margin),(margin,h-margin),(w-margin,h-margin),
            (w//2,margin),(w//2,h-margin),(margin,h//2),(w-margin,h//2)]
    for x,y in points:
        d.line((x-mark_size,y,x+mark_size,y),fill=(0,0,0,255),width=1)
        d.line((x,y-mark_size,x,y+mark_size),fill=(0,0,0,255),width=1)
        d.ellipse((x-5,y-5,x+5,y+5),outline=(0,0,0,255),width=1)
    return out

def safe_crop_to_artwork(mask, padding=0):
    box=mask.getbbox()
    if not box:
        return mask.copy()
    l,t,r,b=box
    l=max(0,l-padding); t=max(0,t-padding)
    r=min(mask.width,r+padding); b=min(mask.height,b+padding)
    return mask.crop((l,t,r,b))

def ink_density(mask):
    m=mask.convert("L")
    data=list(m.getdata())
    return sum(data)/(255*len(data)) if data else 0

def estimated_ink_area(mask, dpi=300):
    density=ink_density(mask)
    area_in2=(mask.width/dpi)*(mask.height/dpi)
    return density*area_in2

def separations_summary(names, masks, dpi):
    rows=[]
    for n,m in zip(names,masks):
        rows.append({
            "channel": n,
            "coverage_percent": round(ink_density(m)*100,2),
            "estimated_ink_area_in2": round(estimated_ink_area(m,dpi),3)
        })
    return rows
