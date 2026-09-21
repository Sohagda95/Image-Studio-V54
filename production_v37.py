from __future__ import annotations
from pathlib import Path
import json, datetime, math
from PIL import Image, ImageFilter, ImageEnhance, ImageOps, ImageChops, ImageStat

APP_VERSION='V37'

def _clamp(v,a=0,b=255): return max(a,min(b,int(v)))

def _odd(n):
    n=max(1,int(n)); return n if n%2 else n+1

def create_shadow_mask(im, strength=55, blur=25, threshold=110):
    """Heuristic mask for broad dark regions; useful for guiding reconstruction, not semantic AI."""
    rgb=im.convert('RGB'); y=ImageOps.grayscale(rgb)
    low=y.filter(ImageFilter.GaussianBlur(_odd(blur)))
    med=ImageStat.Stat(low).mean[0]
    # darker-than-local-background regions become candidates
    def px(v):
        delta=max(0, (med - v) - max(0,100-int(threshold)))
        return _clamp(delta*max(0.1,float(strength)/45.0)*3.0)
    mask=low.point(px)
    return mask.filter(ImageFilter.GaussianBlur(max(0,blur//4)))

def expand_mask(mask, pixels=3):
    p=max(0,int(pixels));
    if p<=0:return mask
    size=2*p+1
    if size%2==0:size+=1
    return mask.filter(ImageFilter.MaxFilter(size))

def soften_mask(mask, radius=2.0):
    return mask.filter(ImageFilter.GaussianBlur(float(radius))) if radius>0 else mask

def cv2_inpaint(im, mask, method='telea', radius=3):
    try:
        import cv2, numpy as np
    except Exception:
        return None, 'opencv_unavailable'
    rgb=im.convert('RGB'); arr=np.array(rgb)[:,:,::-1]
    m=np.array(mask.convert('L'))
    flag=cv2.INPAINT_NS if method.lower()=='ns' else cv2.INPAINT_TELEA
    out=cv2.inpaint(arr,m,max(1,float(radius)),flag)
    return Image.fromarray(out[:,:,::-1]).convert('RGBA'), 'opencv_'+method.lower()

def texture_fill(im, mask, radius=18, mix=0.72):
    """Deterministic non-generative fallback: blurred local color reconstruction."""
    rgba=im.convert('RGBA'); rgb=rgba.convert('RGB')
    soft=rgb.filter(ImageFilter.GaussianBlur(max(2,int(radius))))
    # Preserve local structure by combining blurred base with a mild sharpened source.
    detail=rgb.filter(ImageFilter.UnsharpMask(radius=1.2,percent=80,threshold=4))
    fill=Image.blend(soft,detail,max(0,min(1,float(mix))))
    out=Image.composite(fill,rgb,mask.convert('L'))
    return Image.merge('RGBA',(*out.split(),rgba.getchannel('A')))

def reconstruct_v37(im, mask=None, backend='Auto', method='Telea', radius=3,
                     mask_expand=2, mask_soften=2.0, texture_mix=0.72,
                     auto_shadow_mask=False, shadow_strength=55):
    src=im.convert('RGBA')
    if mask is None:
        mask=create_shadow_mask(src,strength=shadow_strength) if auto_shadow_mask else Image.new('L',src.size,0)
    else:
        mask=mask.convert('L').resize(src.size)
    mask=expand_mask(mask,mask_expand); mask=soften_mask(mask,mask_soften)
    backend=backend.lower()
    used='texture_fallback'
    result=None
    if backend in ('auto','opencv','telea','ns'):
        chosen='ns' if backend=='ns' or method.lower()=='ns' else 'telea'
        result,used=cv2_inpaint(src,mask,chosen,radius)
        if result is not None:
            # restore alpha exactly
            result=Image.merge('RGBA',(*result.convert('RGB').split(),src.getchannel('A')))
    if result is None:
        result=texture_fill(src,mask,radius=max(6,int(radius*5)),mix=texture_mix)
        used='texture_fallback'
    return result,mask,used

def confidence_report(before,after,mask,backend,settings):
    b=before.convert('RGB'); a=after.convert('RGB').resize(b.size)
    d=ImageChops.difference(b,a); st=ImageStat.Stat(d)
    mask=mask.convert('L').resize(b.size)
    mp=mask.load(); changed=0; area=0; weighted=0.0
    dp=d.convert('L').load();
    for y in range(b.height):
        for x in range(b.width):
            m=mp[x,y]/255.0
            if m>0.02:
                area+=1; weighted+=dp[x,y]*m
            if dp[x,y]>8: changed+=1
    total=b.width*b.height
    mean_mask_delta=(weighted/area) if area else 0
    coverage=area/total*100
    changed_pct=changed/total*100
    # Conservative heuristic confidence: high when repaired area is modest and change is localized.
    confidence=max(0,min(100,100 - min(55,coverage*1.2) - min(35,max(0,mean_mask_delta-18)*0.9)))
    return {'app':'Image Studio','version':APP_VERSION,'created':datetime.datetime.now().isoformat(timespec='seconds'),
            'mode':'optional_backend_mask_reconstruction','backend':backend,'settings':settings,
            'source_size':[b.width,b.height],'mask_coverage_pct':round(coverage,3),
            'mean_repair_delta':round(mean_mask_delta,3),'changed_pixels_over_8_pct':round(changed_pct,3),
            'heuristic_confidence_pct':round(confidence,2),
            'limitations':['Confidence is a heuristic diagnostic, not a model probability.',
                           'OpenCV Telea/Navier-Stokes are classical inpainting, not generative AI.',
                           'Texture fallback does not invent semantic content.']}

def export_v37(before,after,mask,out_path,settings,backend,dpi=300):
    out=Path(out_path); out.parent.mkdir(parents=True,exist_ok=True)
    after.save(out,'PNG',dpi=(int(dpi),int(dpi)))
    mask_path=out.with_name(out.stem+'_repair_mask.png'); mask.save(mask_path)
    rep=confidence_report(before,after,mask,backend,settings)
    Path(out.with_name(out.stem+'_v37_report.json')).write_text(json.dumps(rep,indent=2,ensure_ascii=False),encoding='utf-8')
    return rep,mask_path
