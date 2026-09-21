"""V38 Vectorization & Raster-to-Print Lab.
Deterministic raster cleanup and vector-style reconstruction; not OCR/font recognition.
"""
from pathlib import Path
import json, math
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    import cv2
    import numpy as np
    HAS_CV2=True
except Exception:
    HAS_CV2=False


def cleanup_raster(im, smooth=1.0, sharpen=1.1, antialias=True):
    x=im.convert('RGBA')
    if smooth>0:
        radius=max(0.1,float(smooth))
        x=x.filter(ImageFilter.GaussianBlur(radius))
    if antialias:
        x=x.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=2))
    x=ImageEnhance.Sharpness(x).enhance(max(.1,float(sharpen)))
    return x


def quantize_regions(im, colors=8):
    colors=max(2,min(32,int(colors)))
    rgba=im.convert('RGBA')
    rgb=rgba.convert('RGB').quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert('RGB')
    pal=rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    palette=pal.getpalette()[:colors*3]
    cols=[tuple(palette[i:i+3]) for i in range(0,len(palette),3)]
    return rgb, cols


def _rgb_hex(c): return '#%02X%02X%02X'%tuple(int(v) for v in c[:3])


def raster_to_svg(im, colors=8, simplify=2.0, min_area=20, preserve_alpha=True):
    """Convert quantized color regions to SVG paths when OpenCV is available.
    Falls back to an SVG embedding of the cleaned raster if contours are unavailable.
    """
    src=im.convert('RGBA')
    q, palette=quantize_regions(src, colors)
    w,h=src.size
    if not HAS_CV2:
        import base64, io
        bio=io.BytesIO(); src.save(bio,'PNG')
        b64=base64.b64encode(bio.getvalue()).decode('ascii')
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><image width="{w}" height="{h}" href="data:image/png;base64,{b64}"/></svg>'
        return svg, {'backend':'embedded-raster','regions':0,'vectorized':False}
    arr=np.array(q.convert('RGB'))
    alpha=np.array(src.getchannel('A'))
    paths=[]; region_count=0
    for color in palette:
        mask=np.all(arr==np.array(color,dtype=np.uint8),axis=2).astype(np.uint8)*255
        if preserve_alpha:
            mask=np.minimum(mask,alpha)
        if int(mask.sum())<max(1,int(min_area))*255: continue
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area=cv2.contourArea(cnt)
            if area < float(min_area): continue
            eps=max(0.1,float(simplify))
            approx=cv2.approxPolyDP(cnt,eps,True)
            if len(approx)<3: continue
            pts=approx.reshape(-1,2)
            d='M '+' L '.join(f'{int(x)} {int(y)}' for x,y in pts)+' Z'
            paths.append(f'<path d="{d}" fill="{_rgb_hex(color)}"/>')
            region_count+=1
    svg='\n'.join([f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">']+paths+['</svg>'])
    return svg, {'backend':'opencv-contours','regions':region_count,'vectorized':True,'palette':[list(c) for c in palette]}


def edge_mask(im, threshold=80, close=1):
    rgba=im.convert('RGBA')
    gray=ImageOps.grayscale(rgba)
    if HAS_CV2:
        a=np.array(gray)
        edges=cv2.Canny(a,int(threshold),min(255,int(threshold*2)))
        if close>0:
            k=np.ones((int(close)*2+1,int(close)*2+1),np.uint8)
            edges=cv2.morphologyEx(edges,cv2.MORPH_CLOSE,k)
        return Image.fromarray(edges,'L')
    return gray.filter(ImageFilter.FIND_EDGES).point(lambda p:255 if p>=threshold else 0)


def transparent_background(im, tolerance=8):
    x=im.convert('RGBA'); p=x.load(); w,h=x.size
    samples=[p[0,0][:3],p[w-1,0][:3],p[0,h-1][:3],p[w-1,h-1][:3]]
    for y in range(h):
        for xx in range(w):
            c=p[xx,y][:3]
            d=min(sum((c[i]-s[i])**2 for i in range(3))**0.5 for s in samples)
            if d<=tolerance: p[xx,y]=(*c,0)
    return x


def vector_report(src, cleaned, svg_meta, settings):
    a=src.convert('RGB'); b=cleaned.convert('RGB')
    import statistics
    dif=[]
    for x,y in zip(a.getdata(),b.getdata()): dif.append(sum(abs(int(x[i])-int(y[i])) for i in range(3))/3)
    return {
        'version':'V38','source_size':[src.width,src.height],
        'cleaned_size':[cleaned.width,cleaned.height],
        'mean_channel_change':round(statistics.fmean(dif),3) if dif else 0,
        'svg':svg_meta,'settings':settings,
        'backend_note':'OpenCV contours when available; otherwise SVG embeds the raster. This is vector-style reconstruction, not semantic logo/text recognition.'
    }


def export_vector_package(src, cleaned, svg_text, out_path, report, edge=None):
    p=Path(out_path); p.parent.mkdir(parents=True,exist_ok=True)
    if p.suffix.lower()=='.svg': p.write_text(svg_text,encoding='utf-8'); base=p.with_suffix('')
    else:
        cleaned.save(p,'PNG',dpi=(300,300)); base=p.with_suffix('')
        base.with_suffix('.svg').write_text(svg_text,encoding='utf-8')
    cleaned.save(base.with_name(base.name+'_cleaned.png'),'PNG',dpi=(300,300))
    if edge is not None: edge.save(base.with_name(base.name+'_edges.png'),'PNG')
    rp=base.with_name(base.name+'_v38_report.json'); rp.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return rp
