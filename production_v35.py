from __future__ import annotations
from pathlib import Path
import json, datetime, math
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageEnhance, ImageOps

APP_VERSION='V35'
GARMENTS={
    'Black':(18,18,20),'White':(245,245,242),'Navy':(20,34,65),'Red':(135,22,25),
    'Royal Blue':(32,67,145),'Dark Gray':(58,60,64),'Forest Green':(30,72,48)
}

def _morph(mask, px, mode='choke'):
    px=max(0,int(px))
    if px<=0:return mask.convert('L')
    n=max(3,px*2+1); n += (n%2==0)
    return mask.convert('L').filter(ImageFilter.MinFilter(n) if mode=='choke' else ImageFilter.MaxFilter(n))

def build_underbase_v35(im, mode='adaptive', threshold=12, strength=100, choke=1, spread=0, highlight_protection=15, smooth=0.6):
    rgba=im.convert('RGBA'); alpha=rgba.getchannel('A'); gray=ImageOps.grayscale(rgba)
    t=max(0,min(255,int(threshold))); s=max(0,min(100,int(strength))); hp=max(0,min(100,int(highlight_protection)))
    if mode=='solid':
        u=alpha.point(lambda p: 255 if p>t else 0)
    elif mode=='luma':
        inv=ImageOps.invert(gray)
        u=ImageChops.multiply(alpha,inv).point(lambda p:int(p*s/100))
    else:
        inv=ImageOps.invert(gray).point(lambda p:int(p*s/100))
        solid=alpha.point(lambda p:255 if p>t else 0)
        u=ImageChops.lighter(ImageChops.multiply(alpha,inv),solid)
        if hp:
            # Protect bright artwork regions from unnecessary white ink.
            protect=gray.point(lambda p: 255 if p >= 255-hp*2.55 else 0)
            u=ImageChops.subtract(u,ImageChops.multiply(u,protect))
    if smooth>0: u=u.filter(ImageFilter.GaussianBlur(float(smooth)))
    if choke: u=_morph(u,choke,'choke')
    if spread: u=_morph(u,spread,'spread')
    return u

def coverage(mask):
    m=mask.convert('L'); hist=m.histogram(); total=max(1,m.width*m.height)
    weighted=sum(i*c for i,c in enumerate(hist))/(255*total)
    solid=sum(hist[200:])/total
    return {'mean_coverage_pct':round(weighted*100,3),'solid_coverage_pct':round(solid*100,3),'pixels':total}

def preview_underbase(im, mask, garment='Black', opacity=1.0):
    rgb=GARMENTS.get(garment,GARMENTS['Black']); base=Image.new('RGBA',im.size,(*rgb,255))
    white=Image.new('RGBA',im.size,(250,250,250,255)); a=mask.convert('L').point(lambda p:int(p*max(0,min(1,float(opacity)))))
    white.putalpha(a); base=Image.alpha_composite(base,white)
    # Artwork sits over the underbase, preserving its alpha.
    art=im.convert('RGBA'); art.putalpha(ImageChops.multiply(art.getchannel('A'),Image.new('L',im.size,230)))
    return Image.alpha_composite(base,art)

def compare_underbases(im, modes, settings):
    out=[]
    for mode in modes:
        m=build_underbase_v35(im,mode=mode,**settings); out.append({'mode':mode,'mask':m,'stats':coverage(m)})
    return out

def underbase_report(items, garment, settings):
    return {'app':'Image Studio','version':APP_VERSION,'created':datetime.datetime.now().isoformat(timespec='seconds'),
            'mode':'dark_garment_underbase_preview','garment':garment,'settings':settings,
            'modes':[{'mode':x['mode'],'stats':x['stats']} for x in items],
            'notes':['Underbase is an engineering preview/mask generator.','Choke/spread values are pixel-domain operations; they are not calibrated to mesh count, ink deposit or RIP trapping.']}

def export_underbase_set(im, modes, out_dir, garment, settings, dpi=300):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); items=compare_underbases(im,modes,settings)
    for x in items:
        name=x['mode']; x['mask'].save(out/f'underbase_{name}.png','PNG',dpi=(int(dpi),int(dpi)))
        preview_underbase(im,x['mask'],garment).save(out/f'proof_{name}_{garment.replace(" ","_")}.png','PNG',dpi=(int(dpi),int(dpi)))
    rep=underbase_report(items,garment,settings); (out/'underbase_manifest.json').write_text(json.dumps(rep,indent=2,ensure_ascii=False),encoding='utf-8')
    return items,rep
