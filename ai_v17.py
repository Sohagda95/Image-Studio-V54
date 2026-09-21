
from __future__ import annotations
from PIL import Image, ImageFilter, ImageEnhance, ImageChops
import numpy as np

def has_rembg():
    try:
        import rembg
        return True
    except Exception:
        return False

def ai_subject_cutout(im):
    if not has_rembg():
        raise RuntimeError("Optional AI backend is not installed. Run install_optional_ai.bat.")
    from rembg import remove
    return remove(im.convert("RGBA"))

def remove_soft_shadows(im, strength=0.35):
    rgba=im.convert("RGBA")
    rgb=rgba.convert("RGB")
    arr=np.asarray(rgb).astype(np.float32)
    blur=np.asarray(rgb.filter(ImageFilter.GaussianBlur(18))).astype(np.float32)
    # Normalize low-frequency illumination while retaining local artwork contrast.
    corrected=np.clip(arr + (arr.mean(axis=2,keepdims=True)-blur.mean(axis=2,keepdims=True))*strength,0,255)
    out=Image.fromarray(corrected.astype(np.uint8),"RGB").convert("RGBA")
    out.putalpha(rgba.getchannel("A"))
    return out

def artwork_cleanup(im, contrast=1.12, sharp=1.15):
    x=im.convert("RGBA")
    rgb=ImageEnhance.Contrast(x.convert("RGB")).enhance(contrast)
    rgb=ImageEnhance.Sharpness(rgb).enhance(sharp)
    out=rgb.convert("RGBA")
    out.putalpha(x.getchannel("A"))
    return out

def white_balance(im):
    x=im.convert("RGBA")
    rgb=np.asarray(x.convert("RGB")).astype(np.float32)
    mean=rgb.reshape(-1,3).mean(axis=0)
    target=mean.mean()
    gain=target/(mean+1e-6)
    rgb=np.clip(rgb*gain,0,255)
    out=Image.fromarray(rgb.astype(np.uint8),"RGB").convert("RGBA")
    out.putalpha(x.getchannel("A"))
    return out
