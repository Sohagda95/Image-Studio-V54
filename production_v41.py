"""V41 Project Archive & Version Control.
Lightweight local project history for artwork-production jobs. Uses file snapshots,
SHA-256 manifests and ZIP archives; it does not alter source artwork or provide
binary diffing.
"""
from pathlib import Path
import hashlib, json, shutil, zipfile, datetime

SCHEMA='ImageStudio.V41.ProjectArchive.1'

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def file_info(path, root=None):
    p=Path(path); rel=str(p.relative_to(root)) if root else p.name
    return {'path':rel,'name':p.name,'size_bytes':p.stat().st_size,'sha256':sha256_file(p)}

def create_project(project_dir, name='Untitled Project', notes='', tags=None):
    root=Path(project_dir); root.mkdir(parents=True,exist_ok=True)
    (root/'snapshots').mkdir(exist_ok=True); (root/'archives').mkdir(exist_ok=True)
    manifest={'schema':SCHEMA,'project_name':name,'created_at':datetime.datetime.now().isoformat(timespec='seconds'),
              'updated_at':datetime.datetime.now().isoformat(timespec='seconds'),'notes':notes,'tags':tags or [],'versions':[]}
    save_manifest(manifest,root); return manifest

def manifest_path(root): return Path(root)/'project_manifest.json'

def load_manifest(root):
    p=manifest_path(root)
    if not p.exists(): return create_project(root)
    return json.loads(p.read_text(encoding='utf-8'))

def save_manifest(manifest,root):
    manifest['updated_at']=datetime.datetime.now().isoformat(timespec='seconds')
    manifest_path(root).write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')

def add_snapshot(root, source_files, label='Snapshot', notes='', settings=None, copy_sources=True):
    root=Path(root); m=load_manifest(root)
    nums=[int(v.get('version',0)) for v in m.get('versions',[]) if str(v.get('version','')).isdigit()]
    ver=(max(nums)+1) if nums else 1
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    snap=root/'snapshots'/f'v{ver:03d}_{stamp}'
    snap.mkdir(parents=True,exist_ok=True)
    records=[]
    for src in source_files:
        p=Path(src)
        if not p.exists() or not p.is_file(): continue
        dest=snap/'source' / p.name
        dest.parent.mkdir(parents=True,exist_ok=True)
        if copy_sources: shutil.copy2(p,dest); target=dest
        else: target=p
        records.append(file_info(target, snap if copy_sources else None))
    rec={'version':ver,'label':label,'created_at':datetime.datetime.now().isoformat(timespec='seconds'),
         'notes':notes,'settings':settings or {},'snapshot_dir':str(snap.relative_to(root)),'files':records}
    m.setdefault('versions',[]).append(rec); save_manifest(m,root); return rec

def list_versions(root): return load_manifest(root).get('versions',[])

def restore_snapshot(root, version, output_dir):
    root=Path(root); m=load_manifest(root)
    rec=next((v for v in m.get('versions',[]) if int(v.get('version',-1))==int(version)),None)
    if not rec: raise ValueError('Version not found')
    src=root/rec['snapshot_dir']/'source'; out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    copied=[]
    if src.exists():
        for p in src.iterdir():
            if p.is_file(): shutil.copy2(p,out/p.name); copied.append(str(out/p.name))
    return {'version':version,'output_dir':str(out),'files':copied}

def compare_versions(root, a, b):
    vs={int(v['version']):v for v in load_manifest(root).get('versions',[])}
    if int(a) not in vs or int(b) not in vs: raise ValueError('Both versions must exist')
    A={x['name']:x for x in vs[int(a)].get('files',[])}; B={x['name']:x for x in vs[int(b)].get('files',[])}
    names=sorted(set(A)|set(B)); changes=[]
    for n in names:
        if n not in A: changes.append({'file':n,'change':'added'})
        elif n not in B: changes.append({'file':n,'change':'removed'})
        elif A[n].get('sha256')!=B[n].get('sha256'): changes.append({'file':n,'change':'modified','from':A[n].get('sha256'),'to':B[n].get('sha256')})
        else: changes.append({'file':n,'change':'unchanged'})
    return {'schema':SCHEMA,'version_a':int(a),'version_b':int(b),'changes':changes}

def archive_project(root, output_zip=None):
    root=Path(root); m=load_manifest(root)
    if output_zip is None: output_zip=root/'archives'/f"{root.name}_archive_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    output_zip=Path(output_zip); output_zip.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output_zip,'w',zipfile.ZIP_DEFLATED) as z:
        for p in root.rglob('*'):
            if p.is_file() and p != output_zip: z.write(p,p.relative_to(root))
    return output_zip

def export_version_report(root, output):
    m=load_manifest(root); p=Path(output); p.write_text(json.dumps(m,indent=2,ensure_ascii=False),encoding='utf-8'); return p
