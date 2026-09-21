from __future__ import annotations
from pathlib import Path
import json, datetime, time, hashlib
from production_v20 import ProductionJob, Cancelled
from production_v23 import validate_artworks

APP_VERSION='V25'

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def file_sha256(path, chunk=1024*1024):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(chunk),b''): h.update(b)
    return h.hexdigest()

def dir_stats(root):
    files=0; total=0
    root=Path(root)
    if root.exists():
        for p in root.rglob('*'):
            if p.is_file(): files+=1; total+=p.stat().st_size
    return {'files':files,'bytes':total,'mb':round(total/1048576,2)}

def validate_one(source, target_dpi=300, min_dpi=150):
    recs, issues=validate_artworks([str(source)], int(target_dpi), int(min_dpi))
    return recs, issues

class ProductionQueueManager:
    """V25 queue orchestration: preflight, retry metadata, per-job logs and statistics."""
    def __init__(self, jobs, root, progress=lambda *a:None, cancelled=lambda:False, paused=lambda:False,
                 target_dpi=300, min_dpi=150, preflight=True):
        self.jobs=list(jobs); self.root=Path(root); self.progress=progress
        self.cancelled=cancelled; self.paused=paused; self.target_dpi=target_dpi; self.min_dpi=min_dpi; self.preflight=preflight
        self.session_id=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_path=self.root/f'queue_{self.session_id}.json'
        self.logs=[]
    def _write(self):
        self.root.mkdir(parents=True,exist_ok=True)
        payload={'version':APP_VERSION,'session_id':self.session_id,'updated_at':now(),'jobs':self.logs}
        self.log_path.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    def _gate(self):
        while self.paused():
            if self.cancelled(): raise Cancelled()
            time.sleep(.15)
        if self.cancelled(): raise Cancelled()
    def run(self):
        self.root.mkdir(parents=True,exist_ok=True)
        total=max(1,len(self.jobs)); results=[]; completed=0
        for idx,spec in enumerate(self.jobs,1):
            self._gate()
            name=str(spec.get('name') or f'Job_{idx:03d}')
            src=Path(spec.get('source',''))
            rec={'name':name,'source':str(src),'status':'queued','started_at':now()}
            t0=time.perf_counter()
            self.progress(int((idx-1)/total*100),f'Preflight {idx}/{total}: {name}')
            try:
                if not src.exists():
                    rec.update(status='error',error='Source file not found')
                elif self.preflight:
                    rs, issues=validate_one(src,self.target_dpi,self.min_dpi)
                    errors=[i for i in issues if i.severity=='ERROR']
                    warnings=[i for i in issues if i.severity=='WARNING']
                    rec['preflight']={'errors':len(errors),'warnings':len(warnings), 'issues':[i.message for i in issues]}
                    if errors:
                        rec.update(status='preflight_error',error='Preflight validation failed')
                if rec['status'] in ('queued',):
                    out=self.root/name
                    if out.exists(): out=self.root/(name+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
                    def cb(p,m):
                        self._gate(); overall=int(((idx-1)+(p/100))/total*100); self.progress(overall,f'{name}: {m}'); return False
                    job=ProductionJob(str(src),str(out),spec.get('options',{}),progress=cb,cancelled=self.cancelled)
                    zp,manifest=job.run(); self._gate()
                    rec.update(status='complete',output=str(out),package=str(zp),
                               manifest_summary={'steps':len(manifest.get('steps',[])),'warnings':len(manifest.get('warnings',[]))},
                               stats=dir_stats(out))
                    completed+=1
            except Cancelled:
                rec.update(status='cancelled')
                rec['elapsed_s']=round(time.perf_counter()-t0,2); rec['finished_at']=now()
                self.logs.append(rec); self._write(); results.append(rec); raise
            except Exception as e:
                rec.update(status='error',error=str(e))
            rec['elapsed_s']=round(time.perf_counter()-t0,2); rec['finished_at']=now()
            self.logs.append(rec); self._write(); results.append(rec)
        self.progress(100,f'Queue finished: {completed}/{total} complete')
        return results, str(self.log_path)

def save_queue(path,jobs,meta=None):
    payload={'version':APP_VERSION,'saved_at':now(),'jobs':jobs,'meta':meta or {}}
    Path(path).write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')

def load_queue(path):
    return json.loads(Path(path).read_text(encoding='utf-8')).get('jobs',[])

def save_template(path, settings):
    Path(path).write_text(json.dumps({'version':APP_VERSION,'saved_at':now(),'settings':settings},indent=2),encoding='utf-8')

def load_template(path):
    return json.loads(Path(path).read_text(encoding='utf-8')).get('settings',{})
