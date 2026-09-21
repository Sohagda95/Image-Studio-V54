"""V50 Performance & Large Artwork Engine.
Memory-aware image sizing, tiling estimates, optimized previews and workload diagnostics.
No GPU is assumed; optional GPU backends are detected only.
"""
from pathlib import Path
import datetime, json, math, os, platform, sys, importlib.util
from PIL import Image

SCHEMA='ImageStudio.V50.Performance.1'

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def module_available(name):
    try: return bool(importlib.util.find_spec(name))
    except Exception: return False

def image_info(path):
    p=Path(path)
    with Image.open(p) as im:
        w,h=im.size; mode=im.mode; bands=len(im.getbands())
        pixels=w*h
        # Conservative uncompressed working-set estimate; Pillow may use more.
        bytes_per_pixel=max(1,bands)
        raw=pixels*bytes_per_pixel
        return {'path':str(p),'width':w,'height':h,'mode':mode,'bands':bands,'pixels':pixels,
                'megapixels':round(pixels/1_000_000,3),'estimated_raw_mb':round(raw/1024**2,2),
                'format':im.format or p.suffix.lstrip('.').upper()}

def estimate_working_set(path, copies=3):
    info=image_info(path)
    # Source + output + temporary processing buffers.
    mb=info['estimated_raw_mb']*max(1,int(copies))
    return {'estimated_working_set_mb':round(mb,2),'copies':max(1,int(copies)),'image':info}

def recommend_tile_size(path, available_mb=2048, safety=0.55):
    info=image_info(path); budget=max(64,float(available_mb))*1024**2*max(.1,min(.9,float(safety)))
    bpp=max(1,info['bands']); copies=3
    max_pixels=max(1,int(budget/(bpp*copies)))
    side=max(64,int(math.sqrt(max_pixels)))
    side=min(side,2048)
    side=max(64,side//64*64)
    return {'recommended_tile':side,'budget_mb':round(budget/1024**2,1),'estimated_tile_mb':round(side*side*bpp*copies/1024**2,2),'reason':'Keeps several working buffers within the configured memory budget.'}

def resize_for_print(path, max_side=12000, resample=Image.Resampling.LANCZOS):
    im=Image.open(path).convert('RGBA')
    w,h=im.size
    if max(w,h)<=max_side: return im
    scale=max_side/max(w,h)
    return im.resize((max(1,round(w*scale)),max(1,round(h*scale))),resample)

def make_preview(path, max_side=1600, out_path=None):
    im=resize_for_print(path,max_side)
    if out_path:
        p=Path(out_path); p.parent.mkdir(parents=True,exist_ok=True); im.save(p,'PNG',optimize=True)
        return p
    return im

def system_resources():
    mem_mb=None
    try:
        if Path('/proc/meminfo').exists():
            for line in Path('/proc/meminfo').read_text().splitlines():
                if line.startswith('MemTotal:'):
                    mem_mb=int(line.split()[1])//1024; break
    except Exception: pass
    return {'schema':SCHEMA,'generated_at':now(),'python':sys.version,'platform':platform.platform(),
            'machine':platform.machine(),'cpu_count':os.cpu_count(),'ram_mb':mem_mb,
            'numpy':module_available('numpy'),'cv2':module_available('cv2'),'torch':module_available('torch'),'cupy':module_available('cupy')}

def workload_report(path, available_mb=None):
    info=image_info(path)
    if available_mb is None: available_mb=system_resources().get('ram_mb') or 2048
    return {'schema':SCHEMA,'generated_at':now(),'image':info,
            'working_set':estimate_working_set(path),
            'tile_plan':recommend_tile_size(path,available_mb),
            'system':system_resources()}

def save_report(report,path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8'); return p

def self_test(root):
    root=Path(root); root.mkdir(parents=True,exist_ok=True); checks=[]
    sample=root/'sample.png'
    Image.new('RGBA',(4000,3000),(20,30,40,255)).save(sample)
    try:
        inf=image_info(sample); checks.append(('Large image inspection','PASS' if inf['width']==4000 else 'FAIL'))
        ws=estimate_working_set(sample); checks.append(('Memory estimate','PASS' if ws['estimated_working_set_mb']>0 else 'FAIL'))
        plan=recommend_tile_size(sample,1024); checks.append(('Tile planning','PASS' if plan['recommended_tile']>=64 else 'FAIL'))
        out=root/'preview.png'; make_preview(sample,800,out); checks.append(('Optimized preview','PASS' if out.exists() else 'FAIL'))
        save_report(workload_report(sample,1024),root/'performance_report.json'); checks.append(('Report export','PASS'))
    except Exception as e: checks.append(('V50 self-test','FAIL:'+str(e)))
    return checks
