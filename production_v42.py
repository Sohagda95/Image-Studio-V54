"""V42 local production job database and search."""
from pathlib import Path
import sqlite3, json, csv, datetime, shutil, os

SCHEMA='ImageStudio.V42.JobDatabase.1'
STATUSES=['New','Preflight','In Production','Proof','Approved','Hold','Complete','Archived']
PRIORITIES=['Low','Normal','High','Urgent']
FIELDS=['job_id','client','order_id','artwork_path','project_folder','status','priority','garment','ink_colors','dpi','print_width_mm','print_height_mm','tags','notes','created_at','updated_at','v41_project','v41_version']

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def connect(db):
    p=Path(db); p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(p)); c.row_factory=sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS jobs (
      job_id TEXT PRIMARY KEY, client TEXT DEFAULT '', order_id TEXT DEFAULT '', artwork_path TEXT DEFAULT '',
      project_folder TEXT DEFAULT '', status TEXT DEFAULT 'New', priority TEXT DEFAULT 'Normal', garment TEXT DEFAULT '',
      ink_colors INTEGER DEFAULT 0, dpi INTEGER DEFAULT 300, print_width_mm REAL DEFAULT 0, print_height_mm REAL DEFAULT 0,
      tags TEXT DEFAULT '', notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      v41_project TEXT DEFAULT '', v41_version INTEGER DEFAULT 0)''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_jobs_client ON jobs(client)')
    c.commit(); return c

def ensure_db(db):
    c=connect(db); c.close(); return Path(db)

def new_job_id(conn):
    prefix=datetime.datetime.now().strftime('JOB-%Y%m%d')
    n=conn.execute("SELECT COUNT(*) FROM jobs WHERE job_id LIKE ?",(prefix+'-%',)).fetchone()[0]+1
    return f'{prefix}-{n:03d}'

def upsert_job(db, data):
    c=connect(db); t=now(); d=dict(data); jid=d.get('job_id') or new_job_id(c)
    old=c.execute('SELECT created_at FROM jobs WHERE job_id=?',(jid,)).fetchone()
    d['job_id']=jid; d['created_at']=old['created_at'] if old else d.get('created_at') or t; d['updated_at']=t
    defaults={'client':'','order_id':'','artwork_path':'','project_folder':'','status':'New','priority':'Normal','garment':'','ink_colors':0,'dpi':300,'print_width_mm':0,'print_height_mm':0,'tags':'','notes':'','v41_project':'','v41_version':0}
    defaults.update(d); d=defaults
    cols=FIELDS; vals=[d.get(k,'') for k in cols]
    sql='INSERT INTO jobs (%s) VALUES (%s) ON CONFLICT(job_id) DO UPDATE SET %s' % (','.join(cols),','.join('?'*len(cols)),','.join(f'{k}=excluded.{k}' for k in cols if k!='job_id'))
    c.execute(sql,vals); c.commit(); row=dict(c.execute('SELECT * FROM jobs WHERE job_id=?',(jid,)).fetchone()); c.close(); return row

def get_job(db,jid):
    c=connect(db); r=c.execute('SELECT * FROM jobs WHERE job_id=?',(jid,)).fetchone(); c.close(); return dict(r) if r else None

def delete_job(db,jid):
    c=connect(db); c.execute('DELETE FROM jobs WHERE job_id=?',(jid,)); c.commit(); n=c.total_changes; c.close(); return bool(n)

def list_jobs(db, search='', status='', priority='', tag='', sort='updated_at DESC'):
    c=connect(db); clauses=[]; args=[]
    if search:
        s=f'%{search}%'; clauses.append('(job_id LIKE ? OR client LIKE ? OR order_id LIKE ? OR artwork_path LIKE ? OR project_folder LIKE ? OR tags LIKE ? OR notes LIKE ?)'); args += [s]*7
    if status and status!='All': clauses.append('status=?'); args.append(status)
    if priority and priority!='All': clauses.append('priority=?'); args.append(priority)
    if tag: clauses.append('tags LIKE ?'); args.append('%'+tag+'%')
    allowed={'updated_at DESC','updated_at ASC','created_at DESC','client ASC','status ASC','priority DESC','job_id ASC'}; sort=sort if sort in allowed else 'updated_at DESC'
    q='SELECT * FROM jobs'+((' WHERE '+' AND '.join(clauses)) if clauses else '')+' ORDER BY '+sort
    rows=[dict(r) for r in c.execute(q,args).fetchall()]; c.close(); return rows

def export_jobs(db, output, fmt='json'):
    rows=list_jobs(db); p=Path(output); p.parent.mkdir(parents=True,exist_ok=True)
    if fmt.lower()=='csv':
        with p.open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    else: p.write_text(json.dumps({'schema':SCHEMA,'exported_at':now(),'jobs':rows},indent=2,ensure_ascii=False),encoding='utf-8')
    return p

def duplicate_job(db,jid):
    d=get_job(db,jid)
    if not d: raise ValueError('Job not found')
    d['job_id']=''; d['order_id']=d.get('order_id','')+'-COPY'; d['status']='New'; return upsert_job(db,d)

def link_v41(db,jid,project_folder,version=0):
    d=get_job(db,jid) or {'job_id':jid}; d['project_folder']=str(project_folder); d['v41_project']=str(project_folder); d['v41_version']=int(version or 0); return upsert_job(db,d)
