
from PIL import Image

def has_rembg():
    try:
        import rembg  # noqa
        return True
    except Exception:
        return False

def rembg_cutout(image: Image.Image):
    try:
        from rembg import remove
        return remove(image.convert("RGBA"))
    except Exception as e:
        raise RuntimeError("rembg/onnxruntime is not installed or its model is unavailable.") from e

def cutout(image, use_ai=True):
    if use_ai and has_rembg():
        return rembg_cutout(image)
    return None
