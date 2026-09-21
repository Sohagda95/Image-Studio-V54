from __future__ import annotations
from pathlib import Path
import json, math, datetime
from PIL import Image, ImageDraw, ImageFilter
from production_v33 import make_spot_channels, DEFAULT_SPOT_LIBRARY

APP_VERSION='V34'

DOT_SHAPES=('circle','square','diamond','line')

def lpi_to_cell_px(output_dpi:int, lpi:float)->float:
    lpi=max(1.0,float(lpi)); return float(output_dpi)/lpi

def _dot_geometry(draw, box, amount, shape):
    x0,y0,x1,y1=box
    cx=(x0+x1)/2; cy=(y0+y1)/2
    amount=max(0.0,min(1.0,float(amount)))
    if shape=='square':
        w=(x1-x0)*amount; h=(y1-y0)*amount
        draw.rectangle((cx-w/2,cy-h/2,cx+w/2,cy+h/2),fill=255)
    elif shape=='diamond':
        w=(x1-x0)*amount/2; h=(y1-y0)*amount/2
        draw.polygon([(cx,cy-h),(cx+w,cy),(cx,cy+h),(cx-w,cy)],fill=255)
    elif shape=='line':
        w=(x1-x0)*amount
        draw.line((cx-w/2,cy,cx+w/2,cy),fill=255,width=max(1,int((y1-y0)*0.16)))
    else:
        r=min(x1-x0,y1-y0)*amount/2
        draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill=255)

def halftone_channel(mask:Image.Image, cell_px:float=8.0, angle:float=22.5, shape='circle', density:float=1.0, film_positive=True):
    """Engineering halftone preview. It rotates the grayscale mask, samples each cell and draws a dot."""
    src=mask.convert('L')
    cell=max(2.0,float(cell_px)); density=max(0.0,min(1.0,float(density)))
    pad=int(math.ceil(cell*2))
    work=src.rotate(float(angle),resample=Image.Resampling.BICUBIC,expand=True,fillcolor=0)
    out=Image.new('L',work.size,0); d=ImageDraw.Draw(out)
    step=max(2,int(round(cell)))
    pix=work.load(); w,h=work.size
    for y in range(0,h,step):
        for x in range(0,w,step):
            sx=min(w-1,x+step//2); sy=min(h-1,y+step//2)
            # mask is coverage: 255 = ink. Use local mean for smoother dots.
            x2=min(w,x+step); y2=min(h,y+step)
            total=0; n=0
            for yy in range(y,y2,max(1,step//3)):
                for xx in range(x,x2,max(1,step//3)):
                    total+=pix[xx,yy]; n+=1
            cov=(total/n/255.0 if n else 0.0)*density
            if cov>0.01:
                _dot_geometry(d,(x,y,min(x+step,w),min(y+step,h)),cov,shape)
    out=out.rotate(-float(angle),resample=Image.Resampling.BICUBIC,expand=False)
    if out.size!=src.size:
        # Center-crop to original dimensions after expanded rotations.
        left=max(0,(out.width-src.width)//2); top=max(0,(out.height-src.height)//2)
        out=out.crop((left,top,left+src.width,top+src.height))
    out=out.filter(ImageFilter.GaussianBlur(0.18))
    return out

def simulate_film(halftone:Image.Image, density:float=1.0, positive=True):
    d=max(0.05,min(2.0,float(density)))
    x=halftone.convert('L')
    if positive:
        # Black ink marks on transparent/white film simulation.
        x=x.point(lambda v:int(max(0,min(255,255-v*d))))
    else:
        x=x.point(lambda v:int(max(0,min(255,v*d))))
    return x

def halftone_contact_sheet(items, cell=320, columns=3):
    cols=max(1,int(columns)); rows=max(1,math.ceil(len(items)/cols))
    sheet=Image.new('RGB',(cols*cell,rows*cell),(35,35,38)); d=ImageDraw.Draw(sheet)
    for i,item in enumerate(items):
        x=(i%cols)*cell; y=(i//cols)*cell
        thumb=item['image'].convert('L').copy(); thumb.thumbnail((cell-20,cell-48),Image.Resampling.LANCZOS)
        preview=Image.new('RGB',thumb.size,(255,255,255)); preview.paste((0,0,0),(0,0,thumb.width,thumb.height),thumb)
        sheet.paste(preview,(x+10,y+10)); d.text((x+10,y+cell-30),str(item['name']),fill=(240,240,240))
    return sheet

def halftone_report(items, output_dpi, lpi, angle, shape, density, film_density):
    return {
        'app':'Image Studio','version':APP_VERSION,
        'created':datetime.datetime.now().isoformat(timespec='seconds'),
        'mode':'engineering_halftone_preview',
        'settings':{'output_dpi':int(output_dpi),'lpi':float(lpi),'cell_px':round(lpi_to_cell_px(output_dpi,lpi),3),'angle':float(angle),'dot_shape':shape,'dot_density':float(density),'film_density':float(film_density)},
        'channels':[{'name':x['name'],'size':list(x['image'].size),'coverage_pct':round(float(x.get('coverage_pct',0)),3)} for x in items],
        'notes':['Rotated-cell halftone is an engineering preview/export generator.','Not calibrated to mesh count, exposure, ink deposit, dot gain or RIP screening parameters.']
    }

def export_halftone_set(channels, out_dir, output_dpi=300, lpi=45, angle=22.5, shape='circle', density=1.0, film_density=1.0):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    cell=lpi_to_cell_px(output_dpi,lpi); items=[]
    for ch in channels:
        ht=halftone_channel(ch['mask'],cell,angle,shape,density,True)
        film=simulate_film(ht,film_density,True)
        name=''.join(c if c.isalnum() or c in '-_.' else '_' for c in ch['name']).strip('_') or 'channel'
        p=out/f'{name}_halftone.png'; film.save(p,'PNG',dpi=(int(output_dpi),int(output_dpi)))
        items.append({'name':ch['name'],'image':film,'coverage_pct':sum(1 for v in film.getdata() if v<128)/(film.width*film.height)*100})
    sheet=halftone_contact_sheet(items)
    sheet_path=out/'halftone_contact_sheet.png'; sheet.save(sheet_path,'PNG',dpi=(int(output_dpi),int(output_dpi)))
    report=halftone_report(items,output_dpi,lpi,angle,shape,density,film_density)
    (out/'halftone_manifest.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return items, report
