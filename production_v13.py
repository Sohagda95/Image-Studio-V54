
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw
import math, json

ANGLE_PRESETS={
    "Classic CMYK": {"C":15,"M":75,"Y":0,"K":45},
    "Screen Print": {"C":22.5,"M":67.5,"Y":0,"K":45},
    "Dark Garment": {"White":0,"C":22.5,"M":67.5,"Y":0,"K":45},
}

def normalize_channel(im):
    if im.mode=="L": return im
    return im.convert("RGBA").getchannel("A")

def export_channels(channels, output_dir, dpi=300, prefix="channel"):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    manifest={"dpi":dpi,"channels":[]}
    for name,im in channels.items():
        safe="".join(c if c.isalnum() or c in "-_" else "_" for c in str(name))
        p=out/f"{prefix}_{safe}.png"
        normalize_channel(im).save(p,format="PNG",dpi=(dpi,dpi))
        manifest["channels"].append({"name":name,"file":str(p)})
    (out/"channels_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest

def angle_preview(channels, angles):
    if not channels: return None
    w,h=next(iter(channels.values())).size
    sheet=Image.new("RGBA",(w,h),(255,255,255,255))
    # lightweight visualization of assigned screen angles
    draw=ImageDraw.Draw(sheet)
    y=12
    for name in channels:
        angle=angles.get(name,45)
        draw.text((12,y),f"{name}: {angle}°",fill=(0,0,0,255))
        y+=18
    return sheet

def build_separation_manifest(channels, angles, dpi=300, garment="Black"):
    return {
        "version":"V13",
        "dpi":dpi,
        "garment":garment,
        "channels":[{"name":n,"screen_angle":angles.get(n,45)} for n in channels],
        "validation_note":"Preview metadata; validate screening and trapping on target RIP."
    }

class CancellableQueue:
    def __init__(self):
        self.cancelled=False
        self.jobs=[]
    def cancel(self): self.cancelled=True
    def run(self, callback=None):
        results=[]
        for i,job in enumerate(self.jobs):
            if self.cancelled: break
            try:
                value=job()
                results.append((i,True,value))
                if callback: callback(i+1,len(self.jobs))
            except Exception as e:
                results.append((i,False,str(e)))
        return results
