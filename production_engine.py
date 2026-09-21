
from pathlib import Path
from PIL import Image, ImageFilter
import json, datetime

def alpha_cleanup(im, threshold=8, feather=1):
    rgba=im.convert("RGBA"); a=rgba.getchannel("A")
    a=a.point(lambda p: 0 if p < threshold else p)
    if feather: a=a.filter(ImageFilter.GaussianBlur(feather))
    rgba.putalpha(a); return rgba

def flatten_on_garment(im, garment="Black"):
    colors={"Black":(18,18,18),"White":(245,245,245),"Navy":(20,32,65),
            "Red":(125,25,28),"Royal Blue":(30,70,150),"Dark Gray":(55,55,55)}
    bg=Image.new("RGBA", im.size, colors.get(garment,colors["Black"])+(255,))
    return Image.alpha_composite(bg,im.convert("RGBA"))

def export_tiff(im,path,dpi=300):
    im.save(path,format="TIFF",compression="tiff_lzw",dpi=(dpi,dpi))
def export_png(im,path): im.save(path,format="PNG",optimize=True)
def export_jpeg(im,path,quality=95): im.convert("RGB").save(path,format="JPEG",quality=quality,subsampling=0)

def save_preset(path,name,settings):
    Path(path).write_text(json.dumps({"name":name,"version":"V9","settings":settings},
                                     indent=2,ensure_ascii=False),encoding="utf-8")
