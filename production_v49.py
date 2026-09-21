"""V49 Stability, Error Recovery & Safe Operations.
Provides crash-safe helpers, SQLite backup/restore, atomic JSON writes,
retry/quarantine utilities, environment diagnostics and recovery bundles.
"""
from pathlib import Path
import datetime, json, os, shutil, sqlite3, tempfile, time, traceback, zipfile, platform, sys, importlib.util

SCHEMA='ImageStudio.V49.StabilityRecovery.1'

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def atomic_write_text(path, text, encoding='utf-8'):
    p=Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=p.name+'.', suffix='.tmp', dir=str(p.parent))
    try:
        with os.fdopen(fd,'w',encoding=encoding) as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p); return p
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise

def atomic_write_json(path, payload):
    return atomic_write_text(path,json.dumps(payload,indent=2,ensure_ascii=False))

def safe_copy(src,dst):
    s=Path(src); d=Path(dst); d.parent.mkdir(parents=True,exist_ok=True)
    tmp=d.with_name(d.name+'.copying')
    shutil.copy2(s,tmp); os.replace(tmp,d); return d

def backup_sqlite(db_path, backup_path):
    src=Path(db_path); dst=Path(backup_path); dst.parent.mkdir(parents=True,exist_ok=True)
    if not src.exists(): raise FileNotFoundError(str(src))
    tmp=dst.with_name(dst.name+'.tmp')
    con=sqlite3.connect(str(src)); out=sqlite3.connect(str(tmp))
    try:
        con.backup(out); out.commit()
    finally:
        out.close(); con.close()
    os.replace(tmp,dst); return dst

def verify_sqlite(db_path):
    con=sqlite3.connect(str(db_path));
    try: row=con.execute('PRAGMA integrity_check').fetchone()
    finally: con.close()
    return bool(row and row[0]=='ok'), row[0] if row else ''

def restore_sqlite(backup_path, db_path, make_backup=True):
    ok,msg=verify_sqlite(backup_path)
    if not ok: raise ValueError('Backup failed integrity check: '+msg)
    target=Path(db_path)
    if make_backup and target.exists(): backup_sqlite(target,target.with_suffix(target.suffix+'.pre_restore.bak'))
    return safe_copy(backup_path,target)

def log_error(log_path, context, exc):
    p=Path(log_path); p.parent.mkdir(parents=True,exist_ok=True)
    entry={'timestamp':now(),'context':context,'error':str(exc),'type':type(exc).__name__,'traceback':traceback.format_exc()}
    with p.open('a',encoding='utf-8') as f: f.write(json.dumps(entry,ensure_ascii=False)+'\n')
    return entry

def retry(operation, attempts=3, delay=0.4, on_error=None):
    last=None
    for n in range(1,max(1,int(attempts))+1):
        try: return operation()
        except Exception as e:
            last=e
            if on_error: on_error(n,e)
            if n<attempts: time.sleep(delay*(2**(n-1)))
    raise last

def quarantine(path, quarantine_dir, reason='failed'):
    src=Path(path)
    if not src.exists(): return None
    q=Path(quarantine_dir); q.mkdir(parents=True,exist_ok=True)
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dst=q/f'{src.stem}_{stamp}_{reason}{src.suffix}'
    shutil.move(str(src),str(dst)); return dst

def environment_report():
    mods=['PIL','PySide6','rembg','cv2','pytesseract','numpy']
    return {'schema':SCHEMA,'generated_at':now(),'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),'modules':{m:bool(importlib.util.find_spec(m)) for m in mods}}

def recovery_bundle(output_dir, db_path=None, log_path=None, extra_paths=None):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    env=environment_report(); atomic_write_json(out/'environment.json',env)
    included=[]
    if db_path and Path(db_path).exists():
        bp=out/'database_backup.sqlite'; backup_sqlite(db_path,bp); included.append(bp.name)
    if log_path and Path(log_path).exists():
        safe_copy(log_path,out/'error_log.jsonl'); included.append('error_log.jsonl')
    for item in extra_paths or []:
        p=Path(item)
        if p.exists() and p.is_file(): safe_copy(p,out/p.name); included.append(p.name)
    manifest={'schema':SCHEMA,'created_at':now(),'files':included,'environment':'environment.json'}
    atomic_write_json(out/'recovery_manifest.json',manifest)
    z=out.with_suffix('.zip')
    with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as arc:
        for p in out.rglob('*'):
            if p.is_file() and p != z: arc.write(p,p.relative_to(out))
    return z

def self_test(root):
    root=Path(root); root.mkdir(parents=True,exist_ok=True); checks=[]
    try:
        p=atomic_write_json(root/'atomic.json',{'ok':True}); checks.append(('Atomic JSON','PASS' if p.exists() else 'FAIL'))
        db=root/'test.sqlite'; c=sqlite3.connect(db); c.execute('CREATE TABLE t(x)'); c.execute('INSERT INTO t VALUES(1)'); c.commit(); c.close()
        b=backup_sqlite(db,root/'backup.sqlite'); ok,msg=verify_sqlite(b); checks.append(('SQLite backup/integrity','PASS' if ok else 'FAIL:'+msg))
        restore_sqlite(b,root/'restored.sqlite',make_backup=False); ok2,msg2=verify_sqlite(root/'restored.sqlite'); checks.append(('SQLite restore','PASS' if ok2 else 'FAIL:'+msg2))
        n=[0]
        def op():
            n[0]+=1
            if n[0]<2: raise RuntimeError('transient test')
            return True
        retry(op,attempts=3); checks.append(('Retry/recovery','PASS'))
        atomic_write_json(root/'env.json',environment_report()); checks.append(('Environment diagnostics','PASS'))
    except Exception as e: checks.append(('V49 self-test','FAIL:'+str(e)))
    return checks
