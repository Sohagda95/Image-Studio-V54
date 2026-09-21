
from __future__ import annotations
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np

def detect_artwork_bbox(im, threshold=18, pad=8):
    """Heuristic print-area detector based on edge/contrast energy."""
    rgb=np.asarray(im.convert("RGB")).astype(np.float32)
    gray=rgb.mean(axis=2)
    gx=np.abs(np.diff(gray,axis=1,prepend=gray[:,:1]))
    gy=np.abs(np.diff(gray,axis=0,prepend=gray[:1,:]))
    energy=gx+gy
    mask=energy>np.percentile(energy,92)
    ys,xs=np.where(mask)
    if len(xs)<20:
        return (0,0,im.width,im.height)
    x0=max(0,int(xs.min())-pad); x1=min(im.width,int(xs.max())+pad+1)
    y0=max(0,int(ys.min())-pad); y1=min(im.height,int(ys.max())+pad+1)
    return (x0,y0,x1,y1)

def reconstruct_print_area(im, bbox=None, shadow_strength=.35):
    """Approximate flattening of low-frequency lighting; preserves alpha."""
    x=im.convert("RGBA")
    crop=x.crop(bbox) if bbox else x
    rgb=np.asarray(crop.convert("RGB")).astype(np.float32)
    blur=np.asarray(crop.convert("RGB").filter(ImageFilter.GaussianBlur(22))).astype(np.float32)
    low=blur.mean(axis=2,keepdims=True)
    target=np.median(low)
    corrected=np.clip(rgb+(target-low)*shadow_strength,0,255)
    out=Image.fromarray(corrected.astype(np.uint8),"RGB").convert("RGBA")
    out.putalpha(crop.getchannel("A"))
    return out

def ai_upscale_optional(im, scale=2):
    """Uses Real-ESRGAN if installed; otherwise returns a high-quality Lanczos upscale."""
    try:
        # Optional integration point. Different Real-ESRGAN distributions expose different APIs.
        from realesrgan import RealESRGAN
        import torch
        model=RealESRGAN(torch.device("cuda" if torch.cuda.is_available() else "cpu"),scale=scale)
        model.load_weights("weights/RealESRGAN_x%d.pth"%scale,download=True)
        return model.predict(im.convert("RGB"))
    except Exception:
        return im.resize((im.width*scale,im.height*scale),Image.Resampling.LANCZOS)

def estimate_print_area_score(im):
    bbox=detect_artwork_bbox(im)
    area=(bbox[2]-bbox[0])*(bbox[3]-bbox[1])
    return {"bbox":bbox,"area_px":area,"coverage_percent":round(area/(im.width*im.height)*100,2)}
