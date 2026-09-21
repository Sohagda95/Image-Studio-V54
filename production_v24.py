from __future__ import annotations
from pathlib import Path
import json, datetime, threading, re
from production_v20 import ProductionJob, Cancelled

APP_VERSION='V24'

def safe_name(name):
    s=re.sub(r'[^A-Za-z0-9._-]+','_',str(name)).strip('._')
    return s or 'job'

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

class BatchProductionRunner:
    """Sequential production queue with pause/resume/cancel and persistent history."""
    def __init__(self, jobs, root, progress=lambda *a:None, cancelled=lambda:False, paused=lambda:False):
        self.jobs=list(jobs); self.root=Path(root); self.progress=progress
        self.cancelled=cancelled; self.paused=paused
        self.history_path=self.root/'job_history.json'
        self.history=[]
    def _gate(self):
        while self.paused():
            if self.cancelled(): raise Cancelled()
            threading.Event().wait(.15)
        return self.cancelled()
    def run(self):
        self.root.mkdir(parents=True,exist_ok=True)
        completed=0; results=[]
        total=max(1,len(self.jobs))
        for idx, spec in enumerate(self.jobs,1):
            if self.cancelled(): break
            while self.paused():
                if self.cancelled(): break
                threading.Event().wait(.15)
            if self.cancelled(): break
            name=safe_name(spec.get('name') or f'Job_{idx:03d}')
            src=Path(spec['source'])
            if not src.exists():
                rec={'name':name,'source':str(src),'status':'error','error':'Source file not found','finished_at':now()}
                self.history.append(rec); self._save_history(); results.append(rec); continue
            out=self.root/name
            if out.exists(): out=self.root/(name+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
            self.progress(int((idx-1)/total*100),f'Job {idx}/{total}: {name}')
            def cb(p,m):
                if self.cancelled(): return True
                self._gate()
                overall=int(((idx-1)+(p/100))/total*100)
                self.progress(overall,f'{name}: {m}')
                return False
            try:
                job=ProductionJob(str(src),str(out),spec.get('options',{}),progress=cb,cancelled=lambda:self.cancelled() or self._gate())
                zp,manifest=job.run()
                rec={'name':name,'source':str(src),'status':'complete','output':str(out),'package':str(zp),
                     'finished_at':now(),'manifest_summary':{'steps':len(manifest.get('steps',[])),'warnings':len(manifest.get('warnings',[]))}}
                completed+=1
            except Cancelled:
                rec={'name':name,'source':str(src),'status':'cancelled','output':str(out),'finished_at':now()}
                self.history.append(rec); self._save_history(); results.append(rec); break
            except Exception as e:
                rec={'name':name,'source':str(src),'status':'error','output':str(out),'error':str(e),'finished_at':now()}
            self.history.append(rec); self._save_history(); results.append(rec)
        self.progress(100 if not self.cancelled() else 0,f'Queue finished: {completed}/{total} completed')
        return results
    def _save_history(self):
        payload={'version':APP_VERSION,'updated_at':now(),'jobs':self.history}
        self.history_path.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
