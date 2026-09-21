from __future__ import annotations
import os, sys, json, shutil, platform, subprocess, hashlib
from pathlib import Path
from datetime import datetime

APP_NAME = 'Image Studio'
APP_VERSION = 'V51'
SCHEMA = 'ImageStudio.V51.Installation.1'

def now(): return datetime.now().isoformat(timespec='seconds')

def app_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def user_data_dir():
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base / APP_NAME

def initialize_data_dirs(base=None):
    root = Path(base) if base else user_data_dir()
    dirs = {k: root / k for k in ('projects','jobs','outputs','logs','backups','reports','temp')}
    for p in dirs.values(): p.mkdir(parents=True, exist_ok=True)
    manifest = root / 'installation.json'
    if not manifest.exists():
        manifest.write_text(json.dumps({'schema':SCHEMA,'app':APP_NAME,'version':APP_VERSION,'created_at':now()}, indent=2), encoding='utf-8')
    return {'root':root, **dirs}

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def environment_report():
    return {
        'schema':SCHEMA,'app':APP_NAME,'version':APP_VERSION,'timestamp':now(),
        'python':sys.version,'python_executable':sys.executable,
        'platform':platform.platform(),'machine':platform.machine(),'processor':platform.processor(),
        'frozen':bool(getattr(sys,'frozen',False)), 'cwd':str(Path.cwd()),
        'root':str(app_root()), 'user_data':str(user_data_dir())
    }

def dependency_report():
    names=['PySide6','PIL','numpy','cv2','rembg','pytesseract','torch','cupy']
    out={}
    for n in names:
        try:
            m=__import__(n)
            out[n]={'available':True,'version':getattr(m,'__version__','unknown')}
        except Exception as e: out[n]={'available':False,'error':str(e)}
    return out

def verify_installation(base=None):
    d=initialize_data_dirs(base)
    required=[d['root'],d['projects'],d['jobs'],d['outputs'],d['logs'],d['backups'],d['reports'],d['temp']]
    results=[]
    for p in required:
        ok=p.exists() and p.is_dir(); results.append({'status':'PASS' if ok else 'FAIL','name':f'Directory: {p.name}','detail':str(p)})
    test=d['temp']/'write_test.tmp'
    try:
        test.write_text('Image Studio V51 write test', encoding='utf-8'); ok=test.read_text(encoding='utf-8')=='Image Studio V51 write test'; test.unlink(missing_ok=True)
        results.append({'status':'PASS' if ok else 'FAIL','name':'Write/read test','detail':'Application data directory is writable.'})
    except Exception as e: results.append({'status':'FAIL','name':'Write/read test','detail':str(e)})
    dep=dependency_report()
    for n,v in dep.items():
        status='PASS' if v['available'] else ('WARNING' if n in {'PySide6','rembg','numpy','cv2','pytesseract','torch','cupy'} else 'FAIL')
        results.append({'status':status,'name':f'Dependency: {n}','detail':v.get('version') if v['available'] else v.get('error','missing')})
    return {'schema':SCHEMA,'timestamp':now(),'environment':environment_report(),'dependencies':dep,'results':results,
            'summary':{'passed':sum(x['status']=='PASS' for x in results),'warnings':sum(x['status']=='WARNING' for x in results),'failed':sum(x['status']=='FAIL' for x in results)}}

def save_report(report, path):
    p=Path(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8'); return p

def create_portable_manifest(path=None):
    d=initialize_data_dirs()
    m={'schema':SCHEMA,'created_at':now(),'app':APP_NAME,'version':APP_VERSION,'data_root':str(d['root']), 'environment':environment_report()}
    return save_report(m, path or d['root']/'portable_manifest.json')
