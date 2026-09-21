from __future__ import annotations
from pathlib import Path
import json, datetime, math
from PIL import Image, ImageFilter, ImageEnhance, ImageOps, ImageChops, ImageStat

APP_VERSION='V36'

def _clamp(v,a=0,b=255): return max(a,min(b,int(v)))

def luminance(im):
    return ImageOps.grayscale(im.convert('RGB'))

def estimate_print_bbox(im, threshold=12):
    rgba=im.convert('RGBA'); a=rgba.getchannel('A')
    if a.getextrema()[0] < 250:
        return a.point(lambda p:255 if p>threshold else 0).getbbox()
    # For opaque mockups, find content away from the dominant border color.
    rgb=rgba.convert('RGB'); px=rgb.load(); w,h=rgb.size
    samples=[px[0,0],px[w-1,0],px[0,h-1],px[w-1,h-1]]
    bg=tuple(sum(s[i] for s in samples)//len(samples) for i in range(3))
    mask=Image.new('L',(w,h),0); mp=mask.load()
    for y in range(h):
        for x in range(w):
            c=px[x,y]; d=sum((c[i]-bg[i])**2 for i in range(3))**0.5
            if d>threshold: mp[x,y]=255
    return mask.filter(ImageFilter.MaxFilter(5)).getbbox()

def illumination_correct(im, strength=70, blur_radius=35, preserve_texture=80):
    """Heuristic low-frequency lighting/shadow correction; not AI inpainting."""
    rgba=im.convert('RGBA'); rgb=rgba.convert('RGB')
    y=luminance(rgb)
    r=max(3,int(blur_radius)); r += (r%2==0)
    low=y.filter(ImageFilter.GaussianBlur(r))
    # normalize luminance toward its median to reduce broad shadows/folds
    med=ImageStat.Stat(low).median[0] if hasattr(ImageStat.Stat(low),'median') else ImageStat.Stat(low).mean[0]
    low_px=low.load(); y_px=y.load(); out=Image.new('RGB',rgb.size); op=out.load()
    s=max(0,min(100,strength))/100.0
    pt=max(0,min(100,preserve_texture))/100.0
    for yy in range(rgb.height):
        for xx in range(rgb.width):
            lv=max(8,low_px[xx,yy]); factor=(med/lv)
            factor=1+(factor-1)*s
            old=y_px[xx,yy]
            corrected=_clamp(old*factor)
            # preserve high-frequency texture/details
            detail=old-max(0,min(255,low_px[xx,yy]))
            corrected=_clamp(corrected*(1-pt*0.18)+ (corrected+detail*pt*0.18))
            op[xx,yy]=rgb.getpixel((xx,yy))
            rr,gg,bb=op[xx,yy]
            ratio=corrected/max(1,old)
            op[xx,yy]=(_clamp(rr*ratio),_clamp(gg*ratio),_clamp(bb*ratio))
    return Image.merge('RGBA',(*out.split(),rgba.getchannel('A')))

def color_cleanup(im, saturation=8, contrast=4, warmth=0):
    rgba=im.convert('RGBA'); rgb=rgba.convert('RGB')
    rgb=ImageEnhance.Color(rgb).enhance(1+saturation/100)
    rgb=ImageEnhance.Contrast(rgb).enhance(1+contrast/100)
    if warmth:
        r,g,b=rgb.split(); delta=abs(int(warmth))
        if warmth>0:
            r=r.point(lambda p:_clamp(p+delta)); b=b.point(lambda p:_clamp(p-delta))
        else:
            r=r.point(lambda p:_clamp(p-delta)); b=b.point(lambda p:_clamp(p+delta))
        rgb=Image.merge('RGB',(r,g,b))
    return Image.merge('RGBA',(*rgb.split(),rgba.getchannel('A')))

def edge_repair(im, radius=1.2, alpha_cleanup=True):
    rgba=im.convert('RGBA'); rgb=rgba.convert('RGB')
    # Conservative detail recovery rather than inventing pixels.
    rgb=rgb.filter(ImageFilter.UnsharpMask(radius=float(radius),percent=115,threshold=3))
    a=rgba.getchannel('A')
    if alpha_cleanup:
        a=a.filter(ImageFilter.MedianFilter(3))
        a=a.filter(ImageFilter.GaussianBlur(0.35))
    return Image.merge('RGBA',(*rgb.split(),a))

def reconstruct_v36(im, shadow_strength=65, blur_radius=35, texture_preserve=80,
                     saturation=5, contrast=3, warmth=0, edge_radius=1.2,
                     crop_to_print_area=False):
    x=im.convert('RGBA')
    if crop_to_print_area:
        box=estimate_print_bbox(x)
        if box and box[2]>box[0] and box[3]>box[1]: x=x.crop(box)
    x=illumination_correct(x,shadow_strength,blur_radius,texture_preserve)
    x=color_cleanup(x,saturation,contrast,warmth)
    x=edge_repair(x,edge_radius,True)
    return x

def difference_stats(before,after):
    a=before.convert('RGB'); b=after.convert('RGB').resize(a.size)
    d=ImageChops.difference(a,b); stat=ImageStat.Stat(d)
    mean=sum(stat.mean)/3
    extrema=d.getextrema(); maxd=max(e[1] for e in extrema)
    changed=sum(1 for v in d.convert('L').getdata() if v>8)/(a.width*a.height)*100
    return {'mean_absolute_channel_delta':round(mean,3),'max_channel_delta':int(maxd),'changed_pixels_over_8_pct':round(changed,3)}

def reconstruction_report(before,after,settings):
    box=estimate_print_bbox(before)
    return {'app':'Image Studio','version':APP_VERSION,'created':datetime.datetime.now().isoformat(timespec='seconds'),
            'mode':'smart_cleanup_reconstruction_preview','settings':settings,
            'source_size':[before.width,before.height],'output_size':[after.width,after.height],
            'print_area_bbox':list(box) if box else None,'difference':difference_stats(before,after),
            'notes':['Heuristic low-frequency illumination correction, color cleanup and conservative edge repair.',
                     'This is not generative inpainting or trained garment-aware reconstruction.']}

def export_reconstruction(before,after,out_path,settings,dpi=300):
    out=Path(out_path); out.parent.mkdir(parents=True,exist_ok=True)
    after.save(out,'PNG',dpi=(int(dpi),int(dpi)))
    rep=reconstruction_report(before,after,settings)
    Path(out.with_name(out.stem+'_v36_report.json')).write_text(json.dumps(rep,indent=2,ensure_ascii=False),encoding='utf-8')
    return rep
