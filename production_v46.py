"""V46 batch production, proof approval and KPI utilities."""
from pathlib import Path
import sqlite3, datetime, json
from production_v42 import connect as connect_v42, list_jobs, get_job
from production_v43 import record_event, job_history
from production_v45 import run_job

SCHEMA='ImageStudio.V46.BatchApprovalKPI.1'
APPROVALS=['Pending','Approved','Needs Changes','Rejected']

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def connect(db):
    c=connect_v42(db)
    c.execute('''CREATE TABLE IF NOT EXISTS proof_approvals (
      id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, decision TEXT NOT NULL,
      note TEXT DEFAULT '', proof_path TEXT DEFAULT '', created_at TEXT NOT NULL)''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_approval_job ON proof_approvals(job_id)')
    c.commit(); return c

def ensure(db):
    c=connect(db); c.close(); return Path(db)

def approval_history(db, job_id):
    c=connect(db); rows=[dict(r) for r in c.execute('SELECT * FROM proof_approvals WHERE job_id=? ORDER BY id',(job_id,)).fetchall()]; c.close(); return rows

def latest_approval(db, job_id):
    rows=approval_history(db,job_id); return rows[-1] if rows else {'decision':'Pending','note':'','proof_path':''}

def set_approval(db, job_id, decision, note='', proof_path=''):
    if decision not in APPROVALS: raise ValueError('Invalid approval decision')
    j=get_job(db,job_id)
    if not j: raise ValueError('Job not found')
    c=connect(db); c.execute('INSERT INTO proof_approvals(job_id,decision,note,proof_path,created_at) VALUES(?,?,?,?,?)',(job_id,decision,note,proof_path,now())); c.commit(); c.close()
    status={'Approved':'Approved','Needs Changes':'Hold','Rejected':'Hold','Pending':'Proof'}[decision]
    from production_v42 import upsert_job
    upsert_job(db,dict(j,status=status))
    record_event(db,job_id,status,f'Proof decision: {decision}. {note}'.strip())
    return latest_approval(db,job_id)

def due_date_stats(db):
    today=datetime.date.today(); rows=list_jobs(db)
    due=overdue=due_soon=0
    for j in rows:
        d=str(j.get('due_date','') or '')
        if not d: continue
        try: dt=datetime.date.fromisoformat(d[:10])
        except Exception: continue
        if j.get('status') in ('Complete','Archived'): continue
        due += 1
        delta=(dt-today).days
        if delta < 0: overdue += 1
        elif delta <= 2: due_soon += 1
    return {'with_due_date':due,'overdue':overdue,'due_within_2_days':due_soon}

def kpi_stats(db):
    rows=list_jobs(db)
    total=len(rows); complete=sum(j.get('status')=='Complete' for j in rows)
    inprod=sum(j.get('status')=='In Production' for j in rows)
    hold=sum(j.get('status')=='Hold' for j in rows)
    proof=sum(j.get('status')=='Proof' for j in rows)
    approved=sum(j.get('status')=='Approved' for j in rows)
    high=sum(j.get('priority') in ('High','Urgent') for j in rows)
    approvals=[]
    for j in rows: approvals.append(latest_approval(db,j['job_id']))
    decided=sum(a.get('decision') in ('Approved','Needs Changes','Rejected') for a in approvals)
    approval_rate=(sum(a.get('decision')=='Approved' for a in approvals)/decided*100) if decided else 0
    return {'total_jobs':total,'complete':complete,'in_production':inprod,'proof':proof,'approved':approved,'hold':hold,'high_priority':high,'proof_decisions':decided,'approval_rate_pct':round(approval_rate,1),**due_date_stats(db)}

def batch_candidates(db, statuses=None, priority=None):
    rows=list_jobs(db)
    allowed=set(statuses or ['New','Preflight','Hold'])
    return [j for j in rows if j.get('status') in allowed and (not priority or j.get('priority')==priority)]

def run_batch(db, job_ids, output_root, options=None, progress=None, cancel=None, snapshot=True):
    results=[]; total=max(1,len(job_ids))
    for i,jid in enumerate(job_ids):
        if cancel and cancel(): break
        def emit(p,m):
            if progress: progress(int((i*100+p)/total),f'{jid}: {m}')
        try:
            m=run_job(db,jid,output_root,options or {},progress=emit,cancel=cancel,snapshot=snapshot)
            results.append({'job_id':jid,'status':'Complete','manifest':m})
        except Exception as e:
            results.append({'job_id':jid,'status':'Failed','error':str(e)})
    payload={'schema':SCHEMA,'started_at':now(),'results':results,'count':len(results)}
    p=Path(output_root)/'v46_batch_manifest.json'; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    return payload

def export_kpi(db, output):
    p=Path(output); p.parent.mkdir(parents=True,exist_ok=True)
    payload={'schema':SCHEMA,'exported_at':now(),'kpi':kpi_stats(db)}
    p.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8'); return p
