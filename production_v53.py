from __future__ import annotations
import json, os, zipfile, hashlib, platform, shutil
from pathlib import Path
from datetime import datetime

APP_VERSION='V53'
SCHEMA='ImageStudio.V53.ProfileWorkspace.2'
LICENSE_ENABLED=False  # License/activation intentionally disabled for this release.
DEFAULT_PROFILE={'schema':SCHEMA,'display_name':'','company':'','email':'','role':'Print Production','phone':'','notes':'','updated_at':None}

def now(): return datetime.now().isoformat(timespec='seconds')

def data_root(base=None):
    if base: p=Path(base)
    elif os.name=='nt': p=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'Image Studio'
    else: p=Path.home()/'.config'/'Image Studio'
    p.mkdir(parents=True,exist_ok=True); return p

def profile_path(base=None): return data_root(base)/'profile_v53.json'

def load_profile(base=None):
    p=profile_path(base)
    try: d=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    except Exception: d={}
    out=DEFAULT_PROFILE.copy(); out.update(d); out['schema']=SCHEMA; return out

def save_profile(profile,base=None):
    out=DEFAULT_PROFILE.copy(); out.update(profile); out['schema']=SCHEMA; out['updated_at']=now()
    p=profile_path(base); p.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8'); return p

def system_fingerprint():
    return {'platform':platform.platform(),'python':platform.python_version(),'machine':platform.machine(),'processor':platform.processor()[:120]}

def _add_file(z,path,arc):
    p=Path(path)
    if p.exists() and p.is_file(): z.write(p,arc)

def create_workspace_bundle(output,base=None,extra_paths=None,include_databases=True):
    out=Path(output); out.parent.mkdir(parents=True,exist_ok=True); root=data_root(base)
    files=[]
    # License/activation data is intentionally excluded while licensing is disabled.
    for p in (profile_path(base),root/'settings_v52.json',root/'presets_v52.json'):
        if p.exists(): files.append((p,'config/'+p.name))
    if include_databases:
        for p in [Path.home()/'ImageStudio'/'jobs_v42.sqlite',Path.home()/'ImageStudio'/'production_jobs.db']:
            if p.exists(): files.append((p,'databases/'+p.name))
    for x in extra_paths or []:
        p=Path(x)
        if p.is_file(): files.append((p,'extra/'+p.name))
    manifest={'schema':SCHEMA,'created_at':now(),'app_version':APP_VERSION,'license_enabled':False,'system':system_fingerprint(),'files':[{'archive':a,'source':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p,a in files]}
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('workspace_manifest.json',json.dumps(manifest,indent=2,ensure_ascii=False))
        for p,a in files: _add_file(z,p,a)
    return out

def inspect_workspace_bundle(source):
    with zipfile.ZipFile(source,'r') as z:
        names=z.namelist()
        if 'workspace_manifest.json' not in names: raise ValueError('Missing workspace manifest')
        m=json.loads(z.read('workspace_manifest.json').decode('utf-8'))
        bad=[]
        for item in m.get('files',[]):
            if item['archive'] not in names: bad.append(item['archive']); continue
            if hashlib.sha256(z.read(item['archive'])).hexdigest()!=item['sha256']: bad.append(item['archive'])
        return {'valid':not bad,'files':len(m.get('files',[])),'missing_or_corrupt':bad,'manifest':m}

def restore_workspace_bundle(source,output_dir,overwrite=False):
    check=inspect_workspace_bundle(source)
    if not check['valid']: raise ValueError('Workspace bundle failed integrity check')
    dest=Path(output_dir); dest.mkdir(parents=True,exist_ok=True); restored=[]
    with zipfile.ZipFile(source,'r') as z:
        for item in check['manifest'].get('files',[]):
            target=dest/item['archive']; target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists() and not overwrite: continue
            with z.open(item['archive']) as src, target.open('wb') as dst: shutil.copyfileobj(src,dst)
            restored.append(str(target))
    return restored

# Compatibility surface: licensing remains deliberately disabled.
def license_status(*args,**kwargs):
    return {'active':False,'enabled':False,'plan':'','reason':'License/activation is disabled in this release'}

def activate_license(*args,**kwargs):
    raise RuntimeError('License/activation is disabled in this release')

def make_demo_license(*args,**kwargs):
    raise RuntimeError('License/activation is disabled in this release')

def validate_license(*args,**kwargs):
    return {'valid':False,'enabled':False,'plan':'','reason':'License/activation is disabled in this release'}

def self_test(base=None):
    root=Path(base or (Path.cwd()/'v53_self_test')); root.mkdir(parents=True,exist_ok=True)
    results=[]
    try:
        save_profile({'display_name':'Test User','company':'Test Shop'},root)
        results.append({'status':'PASS' if load_profile(root)['display_name']=='Test User' else 'FAIL','test':'Profile round-trip'})
        results.append({'status':'PASS' if not license_status(root)['active'] and not license_status(root)['enabled'] else 'FAIL','test':'License disabled'})
        bundle=root/'workspace.zip'; create_workspace_bundle(bundle,root,include_databases=False)
        results.append({'status':'PASS' if inspect_workspace_bundle(bundle)['valid'] else 'FAIL','test':'Workspace bundle integrity'})
        out=root/'restore'; restored=restore_workspace_bundle(bundle,out)
        results.append({'status':'PASS' if restored else 'FAIL','test':'Workspace restore'})
    except Exception as e: results.append({'status':'FAIL','test':'V53 exception','detail':repr(e)})
    return {'schema':SCHEMA,'timestamp':now(),'results':results,'summary':{'passed':sum(x['status']=='PASS' for x in results),'failed':sum(x['status']=='FAIL' for x in results)}}
