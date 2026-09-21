"""V44 Smart Production Workflow orchestrator.
Deterministic local workflow: preflight -> cleanup -> print-ready -> QC -> package.
Optional stages are intentionally conservative and never claim calibrated RIP/ICC output.
"""
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import json, datetime, hashlib, zipfile, shutil

SCHEMA='ImageStudio.V44.SmartWorkflow.1'
STAGES=['preflight','cleanup','print_ready','qc','package']

def now(): return datetime.datetime.now().isoformat(timespec='seconds')
def sha256(path):
    h=hashlib.sha256();
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def preflight(path, target_dpi=300, max_side=12000):
    p=Path(path)
    if not p.exists(): return {'status':'FAIL','errors':['Source file does not exist'],'warnings':[]}
    try: im=Image.open(p); im.load()
    except Exception as e: return {'status':'FAIL','errors':[f'Cannot open image: {e}'],'warnings':[]}
    errors=[]; warnings=[]
    if im.width<100 or im.height<100: warnings.append('Very small raster dimensions.')
    if max(im.size)>max_side: warnings.append(f'Longest side exceeds {max_side}px; output will be bounded.')
    if im.mode not in ('RGBA','LA'): warnings.append(f'Image mode is {im.mode}; transparency may be absent.')
    dpi=im.info.get('dpi',(72,72)); effective=dpi[0] if isinstance(dpi,tuple) else dpi
    if effective < target_dpi: warnings.append(f'Embedded DPI {effective:g} is below target {target_dpi}.')
    return {'status':'FAIL' if errors else ('WARNING' if warnings else 'PASS'),'errors':errors,'warnings':warnings,
            'width':im.width,'height':im.height,'mode':im.mode,'embedded_dpi':effective,'target_dpi':target_dpi}

def cleanup(im, strength=0.35):
    rgba=im.convert('RGBA')
    rgb=rgba.convert('RGB')
    rgb=ImageOps.autocontrast(rgb, cutoff=max(0,min(3,int(strength*3))))
    rgb=ImageEnhance.Contrast(rgb).enhance(1.0+0.12*strength)
    rgb=rgb.filter(ImageFilter.UnsharpMask(radius=1.0,percent=int(55+35*strength),threshold=3))
    out=rgb.convert('RGBA')
    if 'A' in rgba.getbands(): out.putalpha(rgba.getchannel('A'))
    return out

def print_ready(im, max_side=12000):
    out=im.copy(); m=max(out.size)
    if m>max_side:
        s=max_side/m; out=out.resize((max(1,round(out.width*s)),max(1,round(out.height*s))),Image.Resampling.LANCZOS)
    return out

def save_png(im,path,dpi=300):
    Path(path).parent.mkdir(parents=True,exist_ok=True); im.save(path,'PNG',dpi=(dpi,dpi)); return path

def run_workflow(source, output_dir, options=None, progress=None, cancel=None):
    options=options or {}; out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    src=Path(source); manifest={'schema':SCHEMA,'started_at':now(),'source':str(src.resolve()),'source_sha256':sha256(src) if src.exists() else '',
        'options':options,'stages':[],'status':'RUNNING'}
    def emit(p,msg):
        if progress: progress(p,msg)
    def stop():
        if cancel and cancel(): raise RuntimeError('Workflow cancelled')
    def stage(name,pct,fn):
        stop(); emit(pct,f'Running {name.replace("_"," ").title()}…'); t=now()
        try: r=fn(); manifest['stages'].append({'stage':name,'started_at':t,'finished_at':now(),'status':'PASS','result':r}); return r
        except Exception as e:
            manifest['stages'].append({'stage':name,'started_at':t,'finished_at':now(),'status':'FAIL','error':str(e)}); raise
    pf=stage('preflight',10,lambda:preflight(src,options.get('target_dpi',300),options.get('max_side',12000)))
    if pf['status']=='FAIL': raise RuntimeError('; '.join(pf['errors']))
    im=Image.open(src).convert('RGBA')
    cleaned=cleanup(im,options.get('cleanup_strength',0.35))
    stage('cleanup',35,lambda: {'width':cleaned.width,'height':cleaned.height,'mode':cleaned.mode})
    clean_path=out/'01_cleanup.png'; save_png(cleaned,clean_path,options.get('target_dpi',300))
    ready=print_ready(cleaned,options.get('max_side',12000))
    stage('print_ready',55,lambda: {'width':ready.width,'height':ready.height,'mode':ready.mode})
    ready_path=out/'02_print_ready.png'; save_png(ready,ready_path,options.get('target_dpi',300))
    qc=stage('qc',72,lambda:preflight(ready_path,options.get('target_dpi',300),options.get('max_side',12000)))
    report={'workflow':SCHEMA,'qc':qc,'source':str(src),'output':str(out)}
    qc_path=out/'03_qc_report.json'; qc_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    def package():
        files=[clean_path,ready_path,qc_path]
        man=out/'workflow_manifest.json'; man.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8'); files.append(man)
        zip_path=out/'production_package.zip'
        with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
            for f in files: z.write(f,f.name)
        return {'package':str(zip_path),'files':[f.name for f in files]}
    pkg=stage('package',90,package)
    manifest['status']='COMPLETE'; manifest['finished_at']=now(); manifest['package']=pkg
    (out/'workflow_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    emit(100,'Workflow complete.')
    return manifest
