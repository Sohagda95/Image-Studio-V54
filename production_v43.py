"""V43 client/order management and production dashboard built on the V42 SQLite job database."""
from pathlib import Path
import sqlite3, datetime, json, csv, re

SCHEMA='ImageStudio.V43.ClientOrderDashboard.1'

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def connect(db):
    p=Path(db); p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(p)); c.row_factory=sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS clients (client_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, email TEXT DEFAULT '', phone TEXT DEFAULT '', notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, client TEXT DEFAULT '', due_date TEXT DEFAULT '', status TEXT DEFAULT 'New', notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS job_events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, status TEXT NOT NULL, note TEXT DEFAULT '', created_at TEXT NOT NULL)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_job ON job_events(job_id)")
    c.commit(); return c

def ensure_v43(db):
    c=connect(db); c.close(); return Path(db)

def next_job_id(db):
    c=connect(db); prefix=datetime.datetime.now().strftime('JOB-%Y%m%d')+'-'
    rows=c.execute("SELECT job_id FROM jobs WHERE job_id LIKE ?",(prefix+'%',)).fetchall()
    nums=[]
    for r in rows:
        m=re.fullmatch(re.escape(prefix)+r'(\d+)', r['job_id'])
        if m: nums.append(int(m.group(1)))
    n=max(nums,default=0)+1; c.close(); return f'{prefix}{n:03d}'

def record_event(db, job_id, status, note=''):
    c=connect(db); c.execute('INSERT INTO job_events(job_id,status,note,created_at) VALUES(?,?,?,?)',(job_id,status,note,now())); c.commit(); c.close()

def job_history(db, job_id):
    c=connect(db); rows=[dict(r) for r in c.execute('SELECT * FROM job_events WHERE job_id=? ORDER BY id',(job_id,)).fetchall()]; c.close(); return rows

def dashboard_stats(db):
    c=connect(db)
    total=c.execute('SELECT COUNT(*) n FROM jobs').fetchone()['n']
    by_status={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM jobs GROUP BY status ORDER BY status')}
    by_priority={r['priority']:r['n'] for r in c.execute('SELECT priority,COUNT(*) n FROM jobs GROUP BY priority ORDER BY priority')}
    clients=c.execute("SELECT COUNT(DISTINCT NULLIF(client,'')) n FROM jobs").fetchone()['n']
    orders=c.execute("SELECT COUNT(DISTINCT NULLIF(order_id,'')) n FROM jobs").fetchone()['n']
    updated=c.execute('SELECT MAX(updated_at) t FROM jobs').fetchone()['t'] or ''
    c.close(); return {'total_jobs':total,'clients':clients,'orders':orders,'by_status':by_status,'by_priority':by_priority,'last_updated':updated}

def client_list(db, search=''):
    c=connect(db); q='SELECT * FROM clients'; args=[]
    if search: q+=' WHERE name LIKE ? OR email LIKE ? OR phone LIKE ?'; s='%'+search+'%'; args=[s,s,s]
    q+=' ORDER BY name COLLATE NOCASE'; rows=[dict(r) for r in c.execute(q,args).fetchall()]; c.close(); return rows

def upsert_client(db, name, email='', phone='', notes=''):
    name=name.strip()
    if not name: raise ValueError('Client name is required')
    c=connect(db); t=now(); c.execute('INSERT INTO clients(name,email,phone,notes,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET email=excluded.email,phone=excluded.phone,notes=excluded.notes,updated_at=excluded.updated_at',(name,email,phone,notes,t,t)); c.commit(); r=dict(c.execute('SELECT * FROM clients WHERE name=?',(name,)).fetchone()); c.close(); return r

def upsert_order(db, order_id, client='', due_date='', status='New', notes=''):
    order_id=order_id.strip()
    if not order_id: raise ValueError('Order ID is required')
    c=connect(db); t=now(); c.execute('INSERT INTO orders(order_id,client,due_date,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(order_id) DO UPDATE SET client=excluded.client,due_date=excluded.due_date,status=excluded.status,notes=excluded.notes,updated_at=excluded.updated_at',(order_id,client,due_date,status,notes,t,t)); c.commit(); r=dict(c.execute('SELECT * FROM orders WHERE order_id=?',(order_id,)).fetchone()); c.close(); return r

def order_list(db, search=''):
    c=connect(db); q='SELECT * FROM orders'; args=[]
    if search: q+=' WHERE order_id LIKE ? OR client LIKE ? OR status LIKE ?'; s='%'+search+'%'; args=[s,s,s]
    q+=' ORDER BY updated_at DESC'; rows=[dict(r) for r in c.execute(q,args).fetchall()]; c.close(); return rows

def export_dashboard(db, output):
    p=Path(output); p.parent.mkdir(parents=True,exist_ok=True)
    payload={'schema':SCHEMA,'exported_at':now(),'stats':dashboard_stats(db),'clients':client_list(db),'orders':order_list(db),'job_history':{}}
    c=connect(db); jobs=[r['job_id'] for r in c.execute('SELECT job_id FROM jobs').fetchall()]; c.close()
    payload['job_history']={j:job_history(db,j) for j in jobs}
    p.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8'); return p
