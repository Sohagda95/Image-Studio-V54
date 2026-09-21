
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import json, math, datetime

INK_COLORS={
    "White":(255,255,255),"Black":(20,20,20),"Cyan":(0,180,210),
    "Magenta":(220,0,130),"Yellow":(245,220,0),"Red":(220,35,35),
    "Royal Blue":(35,85,210),"Green":(35,150,80),"Orange":(245,125,20)
}

def ink_proof(channels, garment=(20,20,20), ink_map=None):
    if not channels: return None
    size=next(iter(channels.values())).size
    base=Image.new("RGBA",size,tuple(garment)+(255,))
    ink_map=ink_map or {}
    for name,ch in channels.items():
        color=ink_map.get(name, INK_COLORS.get(name,(255,255,255)))
        a=ch.convert("RGBA").getchannel("A")
        layer=Image.new("RGBA",size,tuple(color)+(0,)); layer.putalpha(a)
        base=Image.alpha_composite(base,layer)
    return base

def registration_marks(size, margin=30, length=24, stroke=2):
    w,h=size
    layer=Image.new("RGBA",(w,h),(0,0,0,0))
    d=ImageDraw.Draw(layer)
    pts=[(margin,margin),(w-margin,margin),(w-margin,h-margin),(margin,h-margin)]
    for x,y in pts:
        d.line((x-length,y,x+length,y),fill=(0,0,0,255),width=stroke)
        d.line((x,y-length,x,y+length),fill=(0,0,0,255),width=stroke)
        d.ellipse((x-5,y-5,x+5,y+5),outline=(0,0,0,255),width=stroke)
    return layer

def film_sheet(channels, spacing=40, margin=60, show_marks=True):
    if not channels: return None
    items=list(channels.items())
    maxw=max(im.width for _,im in items)
    maxh=max(im.height for _,im in items)
    cols=min(2,len(items)); rows=math.ceil(len(items)/cols)
    sheet=Image.new("RGBA",(cols*maxw+(cols+1)*spacing,rows*maxh+(rows+1)*spacing+80),(255,255,255,255))
    d=ImageDraw.Draw(sheet)
    for i,(name,im) in enumerate(items):
        x=spacing+(i%cols)*maxw; y=spacing+(i//cols)*maxh+40
        # black positive film preview
        a=im.convert("RGBA").getchannel("A")
        film=Image.new("RGBA",im.size,(0,0,0,255)); film.putalpha(a)
        sheet.alpha_composite(film,(x,y))
        d.text((x,y-28),str(name),fill=(0,0,0,255))
        if show_marks:
            sheet.alpha_composite(registration_marks(im.size), (x,y))
    return sheet

class JobQueue:
    def __init__(self):
        self.jobs=[]
    def add(self,name,func):
        self.jobs.append({"name":name,"func":func,"status":"queued"})
    def run(self):
        results=[]
        for job in self.jobs:
            job["status"]="running"
            try:
                value=job["func"](); job["status"]="done"
                results.append((job["name"],True,value))
            except Exception as e:
                job["status"]="error"; results.append((job["name"],False,str(e)))
        return results
