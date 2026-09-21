from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
import datetime, json, zipfile, re, shutil, hashlib

APP_VERSION='V30'


def safe_name(value: str) -> str:
    s=re.sub(r'[^A-Za-z0-9._-]+','_',str(value).strip())
    return s.strip('._') or 'artwork'


def read_dpi(im):
    d=im.info.get('dpi',(72,72))
    try:return float(d[0]),float(d[1])
    except:return 72.0,72.0


def inspect_output_source(path, target_dpi=300):
    p=Path(path)
    with Image.open(p) as im:
        dx,dy=read_dpi(im)
        return {'path':str(p),'name':p.stem,'format':im.format or p.suffix.lstrip('.').upper(),
                'width_px':im.width,'height_px':im.height,'dpi_x':dx,'dpi_y':dy,
                'estimated_width_mm':round(im.width/target_dpi*25.4,2),
                'estimated_height_mm':round(im.height/target_dpi*25.4,2),
                'alpha': 'A' in im.getbands()}


def save_png(im,path,dpi=300):
    im.save(path,'PNG',dpi=(dpi,dpi))


def save_tiff(im,path,dpi=300):
    im.save(path,'TIFF',compression='tiff_lzw',dpi=(dpi,dpi))


def make_contact_sheet(images, labels=None, columns=2, gap=20, margin=24, bg=(245,245,245,255)):
    if not images:return None
    thumbs=[]
    for im in images:
        x=im.convert('RGBA').copy(); x.thumbnail((720,520),Image.Resampling.LANCZOS); thumbs.append(x)
    cell_w=max(x.width for x in thumbs); cell_h=max(x.height for x in thumbs)+32
    rows=(len(thumbs)+columns-1)//columns
    out=Image.new('RGBA',(margin*2+columns*cell_w+(columns-1)*gap, margin*2+rows*cell_h+(rows-1)*gap),bg)
    d=ImageDraw.Draw(out)
    for i,x in enumerate(thumbs):
        col=i%columns; row=i//columns
        xx=margin+col*(cell_w+gap)+(cell_w-x.width)//2
        yy=margin+row*(cell_h+gap)
        out.alpha_composite(x,(xx,yy))
        if labels:
            d.text((margin+col*(cell_w+gap),yy+x.height+6),str(labels[i]),fill=(20,20,20,255))
    return out


def export_zip(zip_path, root_dir, files):
    zpath=Path(zip_path); zpath.parent.mkdir(parents=True,exist_ok=True)
    root=Path(root_dir)
    with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
        for f in files:
            p=Path(f)
            if p.exists():
                try: arc=p.relative_to(root).as_posix()
                except ValueError: arc=p.name
                z.write(p,arc)
    return str(zpath)


def build_export_manifest(source, output_dir, settings, outputs, channel_outputs=None, validation=None):
    p=Path(source); root=Path(output_dir)
    return {'app':'Image Studio','version':APP_VERSION,
            'created':datetime.datetime.now().isoformat(timespec='seconds'),
            'source':inspect_output_source(source, int(settings.get('dpi',300))),
            'settings':settings,
            'validation':validation or {},
            'outputs':[str(Path(x).relative_to(root)) if Path(x).exists() and root in Path(x).parents else str(x) for x in outputs],
            'channels':channel_outputs or []}


def export_artwork_package(source, output_root, settings, validate_fn=None,
                           channel_builder=None, underbase_builder=None, halftone_builder=None,
                           contact_builder=None):
    source=Path(source); root=Path(output_root); root.mkdir(parents=True,exist_ok=True)
    stem=safe_name(settings.get('prefix') or source.stem)
    jobdir=root/stem; jobdir.mkdir(parents=True,exist_ok=True)
    dpi=int(settings.get('dpi',300)); fmt=settings.get('format','PNG').upper()
    outputs=[]; channel_outputs=[]
    im=Image.open(source).convert('RGBA')
    if settings.get('trim_alpha',True) and 'A' in im.getbands():
        bbox=im.getchannel('A').getbbox()
        if bbox: im=im.crop(bbox)
    if settings.get('max_side',12000):
        mx=int(settings.get('max_side',12000))
        if max(im.size)>mx:
            scale=mx/max(im.size); im=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.LANCZOS)
    master=jobdir/f'{stem}_master.{"tif" if fmt=="TIFF" else "png"}'
    if fmt=='TIFF': save_tiff(im,master,dpi)
    else: save_png(im,master,dpi)
    outputs.append(master)

    channels=[]
    if channel_builder:
        mode=settings.get('separation','Spot')
        if mode=='CMYK':
            masks,names=channel_builder(im,'CMYK',int(settings.get('colors',6)),float(settings.get('tolerance',18)))
        else:
            masks,names=channel_builder(im,'Spot',int(settings.get('colors',6)),float(settings.get('tolerance',18)))
        chdir=jobdir/'channels'; chdir.mkdir(exist_ok=True)
        for name,mask in zip(names,masks):
            cp=chdir/f'{stem}_{safe_name(name)}.png'; save_png(mask.convert('L'),cp,dpi); outputs.append(cp); channel_outputs.append({'name':name,'file':str(cp.relative_to(jobdir))})
            channels.append((name,mask))
    if settings.get('underbase') and underbase_builder:
        ub=underbase_builder(im,settings.get('underbase_mode','adaptive'),8,int(settings.get('underbase_strength',95)),int(settings.get('choke',1)))
        up=jobdir/f'{stem}_UNDERBASE.png'; save_png(ub,up,dpi); outputs.append(up); channel_outputs.append({'name':'Underbase','file':str(up.relative_to(jobdir))}); channels.append(('Underbase',ub))
    if settings.get('halftone') and halftone_builder and channels:
        hdir=jobdir/'halftone'; hdir.mkdir(exist_ok=True)
        for name,mask in channels:
            hp=hdir/f'{stem}_{safe_name(name)}_halftone.png'; hm=halftone_builder(mask,int(settings.get('cell',8)),int(settings.get('angle',45))); save_png(hm,hp,dpi); outputs.append(hp)
    if settings.get('contact_sheet') and channels:
        cs=contact_builder([m.convert('L') for _,m in channels],[n for n,_ in channels]); cp=jobdir/f'{stem}_channel_contact_sheet.png'; save_png(cs.convert('RGBA'),cp,dpi); outputs.append(cp)
    validation=validate_fn(source,dpi) if validate_fn else {}
    manifest=build_export_manifest(source,jobdir,settings,outputs,channel_outputs,validation)
    mp=jobdir/f'{stem}_export_manifest.json'; mp.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8'); outputs.append(mp)
    if settings.get('package_zip',True):
        zp=root/f'{stem}_Production_Package.zip'; export_zip(zp,jobdir,outputs); outputs.append(zp)
    return manifest, [str(x) for x in outputs], str(jobdir)
