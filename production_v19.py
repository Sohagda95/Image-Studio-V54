
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageFilter
import json, datetime, traceback

class ProductionPipeline:
    """Non-destructive orchestration layer for the artwork-to-film workflow."""
    STEPS=("source","cutout","dewarp","reconstruct","cleanup","separation","underbase","film")

    def __init__(self):
        self.images={}
        self.metadata={"version":"V19","created":datetime.datetime.now().isoformat(timespec="seconds"),
                       "completed":[],"warnings":[]}

    def put(self,name,image):
        self.images[name]=image.copy()
        if name not in self.metadata["completed"]:
            self.metadata["completed"].append(name)

    def get(self,name):
        return self.images.get(name)

    def snapshot(self):
        return {"steps":list(self.images.keys()),"metadata":self.metadata}

    def save_manifest(self,path):
        Path(path).write_text(json.dumps(self.snapshot(),indent=2,ensure_ascii=False),encoding="utf-8")

def prepare_separation_source(im, target_dpi=300):
    x=im.convert("RGBA")
    x.info["dpi"]=(target_dpi,target_dpi)
    return x

def make_print_ready(im, max_side=12000):
    x=im.convert("RGBA")
    scale=min(1.0,max_side/max(x.size))
    if scale<1:
        x=x.resize((int(x.width*scale),int(x.height*scale)),Image.Resampling.LANCZOS)
    # Keep alpha intact; final RIP-specific screening remains downstream.
    return x

def validation_report(im, dpi=300):
    w,h=im.size
    return {
        "width_px":w,"height_px":h,"dpi_target":dpi,
        "has_alpha":im.mode in ("RGBA","LA"),
        "large_image_warning":max(w,h)>12000,
        "minimum_recommended_pixels":True if min(w,h)>=1000 else False,
        "notes":["Validate final output on target RIP/printer before production."]
    }
