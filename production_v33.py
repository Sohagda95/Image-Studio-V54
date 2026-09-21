from __future__ import annotations
from pathlib import Path
import json, datetime, math
from PIL import Image, ImageFilter, ImageChops
from production_v32 import rgb_to_lab, delta_e76, hex_to_rgb, rgb_to_hex, spot_mask, mask_stats

APP_VERSION='V33'
DEFAULT_SPOT_LIBRARY={
    'White':'#FFFFFF','Black':'#000000','Warm Red':'#E32636','Process Blue':'#0066CC',
    'Bright Yellow':'#FFD400','Green':'#18A558','Orange':'#FF7A00','Magenta':'#D81B60',
    'Purple':'#6A35A8','Royal Blue':'#2454A6'
}

def load_spot_library(path):
    p=Path(path)
    if p.exists():
        data=json.loads(p.read_text(encoding='utf-8'))
        return {str(k):str(v) for k,v in data.items()}
    return dict(DEFAULT_SPOT_LIBRARY)

def save_spot_library(path, library):
    Path(path).write_text(json.dumps(library,indent=2,ensure_ascii=False),encoding='utf-8')

def make_spot_channels(im, spots, tolerance=12):
    channels=[]
    for name, hx in spots.items():
        rgb=hex_to_rgb(hx)
        m=spot_mask(im,rgb,tolerance,True)
        channels.append({'name':str(name),'hex':rgb_to_hex(rgb),'rgb':list(rgb),'mask':m,'stats':mask_stats(m)})
    return channels

def overlap_matrix(channels):
    out=[]
    for i,a in enumerate(channels):
        for j,b in enumerate(channels):
            if j<=i: continue
            aa=a['mask'].convert('L'); bb=b['mask'].convert('L')
            if aa.size!=bb.size: continue
            total=aa.width*aa.height; count=0; weighted=0.0
            ap,bp=aa.load(),bb.load()
            for y in range(aa.height):
                for x in range(aa.width):
                    av,bv=ap[x,y],bp[x,y]
                    if av and bv:
                        count+=1; weighted += min(av,bv)/255.0
            out.append({'a':a['name'],'b':b['name'],'hard_overlap_pct':round(count/total*100,3) if total else 0,
                        'soft_overlap_pct':round(weighted/total*100,3) if total else 0})
    return out

def exclusive_knockout_channels(channels, priority='order'):
    # Each channel keeps only pixels not already occupied by earlier channels.
    used=Image.new('L',channels[0]['mask'].size,0) if channels else None
    out=[]
    for ch in channels:
        m=ch['mask'].convert('L')
        if used is None: break
        exclusive=ImageChops.subtract(m,used)
        out.append({'name':ch['name'],'hex':ch['hex'],'mask':exclusive,'stats':mask_stats(exclusive)})
        used=ImageChops.lighter(used,m)
    return out

def trap_mask(mask, pixels=1, direction='expand'):
    p=max(0,int(pixels))
    if p==0: return mask.convert('L')
    # Pillow MaxFilter/MinFilter requires odd kernel sizes.
    k=2*p+1
    return mask.convert('L').filter(ImageFilter.MaxFilter(k) if direction=='expand' else ImageFilter.MinFilter(k))

def trapping_diagnostics(channels, trap_pixels=1):
    rows=[]
    for ch in channels:
        expanded=trap_mask(ch['mask'],trap_pixels,'expand')
        original=ch['mask'].convert('L')
        added=ImageChops.subtract(expanded,original)
        s=mask_stats(added)
        rows.append({'channel':ch['name'],'trap_pixels':int(trap_pixels),'added_coverage_pct':s['soft_coverage_pct']})
    return rows

def channel_contact_sheet(channels, cell=240, columns=3):
    cols=max(1,int(columns)); rows=max(1,math.ceil(len(channels)/cols))
    sheet=Image.new('RGB',(cols*cell,rows*cell),(35,35,38))
    from PIL import ImageDraw
    d=ImageDraw.Draw(sheet)
    for i,ch in enumerate(channels):
        x=(i%cols)*cell; y=(i//cols)*cell
        thumb=ch['mask'].convert('L').copy(); thumb.thumbnail((cell-20,cell-45),Image.Resampling.LANCZOS)
        px=Image.new('RGB',(thumb.width,thumb.height),(255,255,255)); px.paste((0,0,0),(0,0,thumb.width,thumb.height),thumb)
        sheet.paste(px,(x+10,y+10)); d.text((x+10,y+cell-28),f"{ch['name']}  {ch['hex']}",fill=(240,240,240))
    return sheet

def separation_report(channels, tolerance=12, trap_pixels=1):
    return {
        'app':'Image Studio','version':APP_VERSION,
        'created':datetime.datetime.now().isoformat(timespec='seconds'),
        'notes':['Named spot channels are generated with sRGB/D65 LAB Delta-E76 matching.','Knockout and trapping are engineering previews; not calibrated RIP separations.'],
        'channels':[{'name':c['name'],'hex':c['hex'],'stats':c['stats']} for c in channels],
        'overlap':overlap_matrix(channels),
        'knockout':[{'name':c['name'],'stats':c['stats']} for c in exclusive_knockout_channels(channels)],
        'trapping':trapping_diagnostics(channels,trap_pixels),
        'settings':{'delta_e76_tolerance':int(tolerance),'trap_pixels':int(trap_pixels)}
    }

def save_separation_report(path, report):
    Path(path).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
