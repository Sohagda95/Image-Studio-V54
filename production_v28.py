from __future__ import annotations
from pathlib import Path
import copy, datetime

APP_VERSION='V28'

V28_PRESETS={
    'Dark Garment 6-Color': {
        'mode':'Spot','colors':6,'cleanup':True,'reconstruct':True,'cutout':False,
        'underbase':True,'choke':1,'halftone':True,'cell':8,'angle':45,'target_dpi':300,'min_dpi':150
    },
    'Light Garment CMYK': {
        'mode':'CMYK','colors':4,'cleanup':True,'reconstruct':False,'cutout':False,
        'underbase':False,'choke':0,'halftone':True,'cell':8,'angle':22,'target_dpi':300,'min_dpi':150
    },
    'Production Proof': {
        'mode':'Spot','colors':8,'cleanup':True,'reconstruct':True,'cutout':False,
        'underbase':True,'choke':1,'halftone':False,'cell':8,'angle':45,'target_dpi':300,'min_dpi':150
    },
    'Fast Preview': {
        'mode':'Spot','colors':4,'cleanup':False,'reconstruct':False,'cutout':False,
        'underbase':False,'choke':0,'halftone':False,'cell':10,'angle':45,'target_dpi':150,'min_dpi':72
    },
}

def normalize_job(job, preset=None):
    x=copy.deepcopy(job)
    x.setdefault('name',Path(x.get('source','job')).stem or 'Job')
    x.setdefault('source','')
    opts=dict(x.get('options',{}))
    if preset:
        for k,v in preset.items(): opts.setdefault(k,v)
    x['options']=opts
    x['preset']=x.get('preset') or ''
    return x

def apply_preset_to_job(job,preset):
    x=normalize_job(job)
    x['options'].update(copy.deepcopy(preset))
    return x

def queue_from_library_items(items,preset):
    out=[]
    for item in items:
        out.append({'name':Path(item['path']).stem,'source':item['path'],'options':copy.deepcopy(preset),'preset':'Dark Garment 6-Color'})
    return out

def estimate_job_stats(job):
    p=Path(job.get('source',''))
    if not p.exists(): return {'exists':False}
    try:
        from PIL import Image
        with Image.open(p) as im:
            dpi=im.info.get('dpi',(0,0)); dx=float(dpi[0] or 0) if isinstance(dpi,(tuple,list)) else float(dpi or 0); dy=float(dpi[1] or 0) if isinstance(dpi,(tuple,list)) else dx
            target=float(job.get('options',{}).get('target_dpi',300) or 300)
            return {'exists':True,'width_px':im.width,'height_px':im.height,'dpi_x':dx,'dpi_y':dy,'print_width_in':round(im.width/target,2),'print_height_in':round(im.height/target,2),'megapixels':round(im.width*im.height/1e6,2)}
    except Exception as e: return {'exists':True,'error':str(e)}

def make_job_summary(jobs):
    return {'version':APP_VERSION,'generated_at':datetime.datetime.now().isoformat(timespec='seconds'),'jobs':len(jobs),'stats':[estimate_job_stats(j) for j in jobs]}
