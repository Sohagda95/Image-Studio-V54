from __future__ import annotations
import json, os, hashlib, shutil, zipfile
from pathlib import Path
from datetime import datetime

APP_VERSION='V54'
SCHEMA='ImageStudio.V54.ProjectManager.1'

def now(): return datetime.now().isoformat(timespec='seconds')

def data_root(base=None):
    if base: p=Path(base)
    elif os.name=='nt': p=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'Image Studio'
    else: p=Path.home()/'.config'/'Image Studio'
    p.mkdir(parents=True,exist_ok=True); return p

def registry_path(base=None): return data_root(base)/'projects_v54.json'

def _load(base=None):
    p=registry_path(base)
    try: d=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'schema':SCHEMA,'projects':[]}
    except Exception: d={'schema':SCHEMA,'projects':[]}
    d.setdefault('projects',[]); d['schema']=SCHEMA; return d

def _save(d,base=None):
    p=registry_path(base); tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8'); os.replace(tmp,p); return p

def project_id(name, folder):
    seed=f'{name}|{Path(folder).resolve()}'.encode(); return 'PRJ-'+hashlib.sha256(seed).hexdigest()[:10].upper()

def create_project_record(name, folder, client='', order_id='', job_id='', tags='', notes='', base=None):
    folder=str(Path(folder).expanduser().resolve()); Path(folder).mkdir(parents=True,exist_ok=True)
    d=_load(base); pid=project_id(name,folder)
    existing=next((x for x in d['projects'] if x['project_id']==pid),None)
    if existing: return existing
    rec={'project_id':pid,'name':name.strip() or Path(folder).name,'folder':folder,'client':client.strip(),'order_id':order_id.strip(),'job_id':job_id.strip(),'tags':tags.strip(),'notes':notes,'status':'Active','created_at':now(),'updated_at':now()}
    d['projects'].append(rec); _save(d,base); return rec

def list_projects(base=None, query=''):
    rows=_load(base)['projects']; q=query.strip().lower()
    if q: rows=[r for r in rows if q in json.dumps(r,ensure_ascii=False).lower()]
    return sorted(rows,key=lambda x:x.get('updated_at',''),reverse=True)

def update_project(project_id_value, updates, base=None):
    d=_load(base)
    for r in d['projects']:
        if r['project_id']==project_id_value:
            for k,v in updates.items():
                if k in r and k not in {'project_id','created_at'}: r[k]=str(v)
            r['updated_at']=now(); _save(d,base); return r
    raise KeyError(project_id_value)

def remove_project(project_id_value, base=None):
    d=_load(base); before=len(d['projects']); d['projects']=[r for r in d['projects'] if r['project_id']!=project_id_value]
    if len(d['projects'])==before: raise KeyError(project_id_value)
    _save(d,base); return True

def folder_stats(folder):
    p=Path(folder); files=[]; total=0
    if not p.exists(): return {'exists':False,'files':0,'bytes':0,'png':0,'tiff':0,'zip':0}
    for f in p.rglob('*'):
        if f.is_file():
            try: total+=f.stat().st_size; files.append(f)
            except OSError: pass
    ext={x.suffix.lower().lstrip('.') for x in files}
    return {'exists':True,'files':len(files),'bytes':total,'png':sum(f.suffix.lower()=='.png' for f in files),'tiff':sum(f.suffix.lower() in ('.tif','.tiff') for f in files),'zip':sum(f.suffix.lower()=='.zip' for f in files),'has_manifest':any(f.name in ('manifest.json','workflow_manifest.json','project_manifest.json') for f in files)}

def project_summary(rec):
    s=folder_stats(rec['folder']); out=dict(rec); out['folder_stats']=s; return out

def archive_project_bundle(project_id_value, output, base=None):
    rec=next((r for r in _load(base)['projects'] if r['project_id']==project_id_value),None)
    if not rec: raise KeyError(project_id_value)
    root=Path(rec['folder']); out=Path(output); out.parent.mkdir(parents=True,exist_ok=True)
    if not root.exists(): raise FileNotFoundError(root)
    manifest={'schema':SCHEMA,'created_at':now(),'project':rec,'folder_stats':folder_stats(root),'files':[]}
    for f in root.rglob('*'):
        if f.is_file() and f != out:
            rel=f.relative_to(root).as_posix()
            try: h=hashlib.sha256(f.read_bytes()).hexdigest(); size=f.stat().st_size
            except Exception: continue
            manifest['files'].append({'path':rel,'bytes':size,'sha256':h})
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('project_manifest_v54.json',json.dumps(manifest,indent=2,ensure_ascii=False))
        for item in manifest['files']:
            z.write(root/item['path'], 'project/'+item['path'])
    return out

def export_registry(output, base=None):
    p=Path(output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(_load(base),indent=2,ensure_ascii=False),encoding='utf-8'); return p

def self_test(base=None):
    root=Path(base or (Path.cwd()/'v54_self_test')); root.mkdir(parents=True,exist_ok=True); work=root/'demo'; work.mkdir(exist_ok=True)
    (work/'artwork.txt').write_text('demo',encoding='utf-8')
    results=[]
    try:
        r=create_project_record('Demo Project',work,client='Test Client',job_id='JOB-V54',base=root/'data'); results.append({'test':'Create/register','status':'PASS' if r['project_id'] else 'FAIL'})
        results.append({'test':'Search/list','status':'PASS' if list_projects(root/'data','demo') else 'FAIL'})
        s=project_summary(r); results.append({'test':'Folder stats','status':'PASS' if s['folder_stats']['files']==1 else 'FAIL'})
        archive=archive_project_bundle(r['project_id'],root/'archive.zip',root/'data'); results.append({'test':'Project archive','status':'PASS' if archive.exists() and archive.stat().st_size>0 else 'FAIL'})
        export=export_registry(root/'registry.json',root/'data'); results.append({'test':'Registry export','status':'PASS' if export.exists() else 'FAIL'})
    except Exception as e: results.append({'test':'V54 exception','status':'FAIL','detail':repr(e)})
    return {'schema':SCHEMA,'timestamp':now(),'results':results,'summary':{'passed':sum(x['status']=='PASS' for x in results),'failed':sum(x['status']=='FAIL' for x in results)}}
