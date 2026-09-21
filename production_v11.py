
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter, ImageEnhance, ImageOps
import json

def solid_color_channel(im, color, strength=1.0):
    a=im.convert("RGBA").getchannel("A")
    if strength < 1:
        a=a.point(lambda p:int(p*strength))
    layer=Image.new("RGBA",im.size,tuple(color)+(0,))
    layer.putalpha(a)
    return layer

def channel_preview(channels, garment=(18,18,18)):
    base=Image.new("RGBA", next(iter(channels.values())).size, tuple(garment)+(255,))
    for name,im in channels.items():
        if isinstance(im,tuple): continue
        base=Image.alpha_composite(base,im.convert("RGBA"))
    return base

def alpha_morph(im, pixels=1, mode="choke"):
    rgba=im.convert("RGBA")
    a=rgba.getchannel("A")
    size=max(3,abs(int(pixels))*2+1)
    if mode=="choke":
        na=a.filter(ImageFilter.MinFilter(size))
    else:
        na=a.filter(ImageFilter.MaxFilter(size))
    rgba.putalpha(na)
    return rgba

def apply_trap(base, over, pixels=1):
    # Simple overprint/trapping approximation for preview; production RIP verification required.
    expanded=alpha_morph(base,pixels,"spread")
    return Image.alpha_composite(expanded,over.convert("RGBA"))

def build_underbase(im, strength=0.9, choke=1, mode="adaptive"):
    rgba=im.convert("RGBA")
    a=rgba.getchannel("A")
    if mode.lower()=="solid":
        a=Image.new("L",rgba.size,int(255*strength))
    elif mode.lower()=="luma":
        rgb=rgba.convert("RGB")
        l=rgb.convert("L")
        a=ImageOps.invert(l).point(lambda p:int(p*strength))
    else:
        a=a.point(lambda p:int(p*strength))
    out=Image.new("RGBA",rgba.size,(255,255,255,0))
    if choke: a= a.filter(ImageFilter.MinFilter(max(3,choke*2+1)))
    out.putalpha(a)
    return out

def generate_spot_channels(im, colors, levels=4):
    # Quantized spot-color preview. Not a calibrated ICC/RIP separation.
    rgb=im.convert("RGB")
    pal=rgb.quantize(colors=max(2,min(256,int(levels))),method=Image.Quantize.MEDIANCUT)
    pal=pal.convert("RGBA")
    return {"Spot %02d"%(i+1): pal for i in range(1)}
