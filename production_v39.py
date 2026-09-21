"""V39 Text & Typography Production Lab.
Heuristic text-region detection with optional pytesseract OCR, typography-safe-area checks,
outline/expand previews, and print-oriented cleanup. OCR is optional and results are not guaranteed editable font matches.
"""
from pathlib import Path
import json, math
from PIL import Image, ImageFilter, ImageOps, ImageEnhance, ImageDraw

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

try:
    import pytesseract
    HAS_TESS = True
except Exception:
    HAS_TESS = False


def _gray(im):
    return np.array(ImageOps.grayscale(im.convert('RGBA'))) if HAS_CV2 else None


def detect_text_regions(im, min_area=40, max_area_ratio=0.18, min_aspect=0.15, max_aspect=18.0,
                        threshold=150, merge_px=3):
    """Detect likely text-like connected regions. Heuristic; not semantic text detection."""
    w, h = im.size
    if not HAS_CV2:
        return [], {'backend': 'fallback', 'detected': 0, 'semantic_text_detection': False}
    g = _gray(im)
    # Use both dark-on-light and light-on-dark binary maps, then merge boxes.
    boxes=[]
    for inv in (False, True):
        bw = cv2.threshold(g, int(threshold), 255, cv2.THRESH_BINARY_INV if not inv else cv2.THRESH_BINARY)[1]
        k = np.ones((max(1,merge_px), max(1,merge_px)), np.uint8)
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, k)
        contours,_ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            x,y,ww,hh = cv2.boundingRect(c); area=ww*hh
            if area < min_area or area > w*h*max_area_ratio: continue
            ar=ww/max(1,hh)
            if ar < min_aspect or ar > max_aspect: continue
            fill=cv2.contourArea(c)/max(1,area)
            if fill < 0.04: continue
            boxes.append([x,y,ww,hh])
    # NMS/merge overlapping boxes.
    boxes=sorted(boxes,key=lambda b:b[2]*b[3], reverse=True)
    kept=[]
    def iou(a,b):
        ax1,ay1,ax2,ay2=a[0],a[1],a[0]+a[2],a[1]+a[3]
        bx1,by1,bx2,by2=b[0],b[1],b[0]+b[2],b[1]+b[3]
        ix1,iy1=max(ax1,bx1),max(ay1,by1); ix2,iy2=min(ax2,bx2),min(ay2,by2)
        inter=max(0,ix2-ix1)*max(0,iy2-iy1)
        return inter/max(1,a[2]*a[3]+b[2]*b[3]-inter)
    for b in boxes:
        if all(iou(b,k)<0.45 for k in kept): kept.append(b)
    kept=sorted(kept,key=lambda b:(b[1],b[0]))
    return kept, {'backend':'opencv-contours','detected':len(kept),'semantic_text_detection':False}


def ocr_text(im, psm=6, lang='eng'):
    if not HAS_TESS:
        return {'available':False,'text':'','data':[],'note':'pytesseract is not installed.'}
    try:
        data=pytesseract.image_to_data(im.convert('RGB'),config=f'--psm {int(psm)}',lang=lang,output_type=pytesseract.Output.DICT)
        rows=[]; words=[]
        for i,t in enumerate(data.get('text',[])):
            t=(t or '').strip(); conf=float(data['conf'][i]) if str(data['conf'][i]).strip() not in ('','-1') else -1
            if t and conf>=0:
                row={'text':t,'confidence':round(conf,1),'box':[int(data['left'][i]),int(data['top'][i]),int(data['width'][i]),int(data['height'][i])]}
                rows.append(row); words.append(t)
        return {'available':True,'text':' '.join(words),'data':rows,'note':'OCR text is informational; font identity/editability is not reconstructed.'}
    except Exception as e:
        return {'available':True,'text':'','data':[],'note':f'OCR failed: {e}'}


def typography_mask(im, regions):
    m=Image.new('L',im.size,0); d=ImageDraw.Draw(m)
    for x,y,w,h in regions: d.rectangle((x,y,x+w-1,y+h-1),fill=255)
    return m


def outline_preview(im, regions, width=2):
    base=im.convert('RGBA').copy(); layer=Image.new('RGBA',base.size,(0,0,0,0)); d=ImageDraw.Draw(layer)
    width=max(1,int(width))
    for x,y,w,h in regions:
        for i in range(width): d.rectangle((x-i,y-i,x+w+i,y+h+i),outline=(255,210,40,230),width=1)
    return Image.alpha_composite(base,layer)


def expand_mask(mask, px=2, soften=1.0):
    m=mask.convert('L'); px=max(0,int(px))
    if HAS_CV2 and px:
        k=np.ones((px*2+1,px*2+1),np.uint8); a=np.array(m)
        a=cv2.dilate(a,k,iterations=1); m=Image.fromarray(a,'L')
    elif px:
        m=m.filter(ImageFilter.MaxFilter(px*2+1))
    if soften>0: m=m.filter(ImageFilter.GaussianBlur(float(soften)))
    return m


def cleanup_text_regions(im, regions, denoise=1.0, contrast=1.0, sharp=1.1):
    x=im.convert('RGBA')
    if denoise>0: x=x.filter(ImageFilter.MedianFilter(3))
    x=ImageEnhance.Contrast(x).enhance(float(contrast))
    x=ImageEnhance.Sharpness(x).enhance(float(sharp))
    return x


def safe_area_report(im, regions, margin_pct=5.0, min_font_px=12):
    w,h=im.size; mx=w*margin_pct/100; my=h*margin_pct/100
    safe=(mx,my,w-mx,h-my)
    issues=[]
    for i,(x,y,rw,rh) in enumerate(regions,1):
        if x<mx or y<my or x+rw>w-mx or y+rh>h-my:
            issues.append({'region':i,'issue':'outside_safe_area','box':[x,y,rw,rh]})
        if min(rw,rh)<min_font_px:
            issues.append({'region':i,'issue':'very_small_region','box':[x,y,rw,rh]})
    return {'safe_area_px':[round(v,2) for v in safe],'margin_percent':margin_pct,'issues':issues,'issue_count':len(issues)}


def typography_report(im, regions, ocr, settings, backend_meta):
    safe=safe_area_report(im,regions,settings.get('safe_margin_pct',5),settings.get('min_region_px',12))
    areas=sum(w*h for _,_,w,h in regions); total=im.width*im.height
    return {'version':'V39','source_size':[im.width,im.height],'regions':regions,'region_count':len(regions),
            'region_area_percent':round(100*areas/max(1,total),3),'ocr':ocr,'safe_area':safe,
            'settings':settings,'backend':backend_meta,
            'limitations':'Region detection is heuristic. OCR is optional and does not identify or recreate the original font.'}


def export_typography_package(im, cleaned, mask, overlay, report, out_path, dpi=300):
    p=Path(out_path); p.parent.mkdir(parents=True,exist_ok=True); base=p.with_suffix('')
    cleaned.save(base.with_name(base.name+'_cleaned.png'),'PNG',dpi=(dpi,dpi))
    mask.save(base.with_name(base.name+'_text_mask.png'),'PNG',dpi=(dpi,dpi))
    overlay.save(base.with_name(base.name+'_overlay.png'),'PNG',dpi=(dpi,dpi))
    rp=base.with_name(base.name+'_v39_report.json'); rp.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return rp
