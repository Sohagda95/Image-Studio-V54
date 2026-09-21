
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter, ImageDraw
import json, math

DEFAULT_SPOT_COLORS={
    "White":(255,255,255),"Black":(20,20,20),"Red":(220,35,35),
    "Blue":(35,85,210),"Green":(35,150,80),"Yellow":(245,220,0),
    "Orange":(245,125,20),"Magenta":(220,0,130),"Cyan":(0,180,210)
}

def alpha_channel(im):
    return im.convert("RGBA").getchannel("A")

def make_spot_channel(im, color, min_alpha=8):
    a=alpha_channel(im).point(lambda p: 0 if p<min_alpha else p)
    layer=Image.new("RGBA",im.size,tuple(color)+(0,))
    layer.putalpha(a)
    return layer

def derive_preview_channels(im, mode="Spot", max_colors=6):
    # Practical preview channels from quantization. This is not a calibrated ICC/RIP separation.
    rgba=im.convert("RGBA")
    if mode.upper()=="CMYK":
        cmyk=rgba.convert("RGB").convert("CMYK")
        names=["C","M","Y","K"]
        channels={}
        for i,n in enumerate(names):
            channels[n]=cmyk.getchannel(i).convert("L")
        return channels
    q=rgba.convert("RGB").quantize(colors=max(2,min(16,max_colors)),method=Image.Quantize.MEDIANCUT)
    pal=q.getpalette()
    channels={}
    # Use luminance masks for representative palette entries.
    used=sorted(set(q.getdata()))
    for idx in used[:max_colors]:
        rgb=tuple(pal[idx*3:idx*3+3])
        mask=q.point(lambda p: 255 if p==idx else 0).convert("L")
        channels[f"Spot_{idx:02d}"]=mask
    return channels

def export_multi_channel(channels, out_dir, dpi=300):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    manifest={"format":"ImageStudioFilmSet","version":"V14","dpi":dpi,"channels":[]}
    for name,mask in channels.items():
        safe="".join(c if c.isalnum() or c in "-_" else "_" for c in str(name))
        p=out/f"{safe}.png"
        alpha_channel(mask).save(p,"PNG",dpi=(dpi,dpi))
        manifest["channels"].append({"name":name,"file":p.name})
    (out/"filmset.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest

def add_registration_to_sheet(sheet, margin=25):
    out=sheet.convert("RGBA").copy(); d=ImageDraw.Draw(out)
    w,h=out.size
    for x,y in [(margin,margin),(w-margin,margin),(w-margin,h-margin),(margin,h-margin)]:
        d.line((x-18,y,x+18,y),fill=(0,0,0,255),width=2)
        d.line((x,y-18,x,y+18),fill=(0,0,0,255),width=2)
        d.ellipse((x-4,y-4,x+4,y+4),outline=(0,0,0,255),width=2)
    return out

def make_contact_sheet(channels, columns=2, gap=35):
    if not channels: return None
    items=list(channels.items()); maxw=max(m.width for _,m in items); maxh=max(m.height for _,m in items)
    rows=math.ceil(len(items)/columns)
    sheet=Image.new("RGBA",(columns*maxw+(columns+1)*gap,rows*(maxh+45)+(rows+1)*gap),(245,245,245,255))
    d=ImageDraw.Draw(sheet)
    for i,(name,mask) in enumerate(items):
        x=gap+(i%columns)*maxw; y=gap+(i//columns)*(maxh+45)+35
        m=alpha_channel(mask)
        tile=Image.new("RGBA",m.size,(0,0,0,255)); tile.putalpha(m)
        sheet.alpha_composite(tile,(x,y)); d.text((x,y-25),name,fill=(0,0,0,255))
    return add_registration_to_sheet(sheet)

def quad_from_margins(size, margin_ratio=.08):
    w,h=size; mx=int(w*margin_ratio); my=int(h*margin_ratio)
    return [(mx,my),(w-mx,my),(w-mx,h-my),(mx,h-my)]
