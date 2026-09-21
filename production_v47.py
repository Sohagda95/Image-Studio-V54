"""V47 print-shop operations: garment quantities, production checklist, materials, operators, delivery and final reports."""
from pathlib import Path
import sqlite3, datetime, json
from production_v42 import connect as connect_v42, get_job, upsert_job
from production_v43 import record_event

SCHEMA='ImageStudio.V47.PrintShopOperations.1'
SIZE_FIELDS=['S','M','L','XL','XXL','3XL','4XL','5XL']
DELIVERY_STATUSES=['Not Ready','Ready','Packed','Shipped','Delivered','Returned','Hold']
CHECKLIST=['Artwork Approved','Preflight Passed','Film/Screen Ready','Underbase Ready','Garment Stock Checked','Ink Prepared','Print Completed','QC Passed','Packed']

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def connect(db):
    c=connect_v42(db)
    c.execute('''CREATE TABLE IF NOT EXISTS production_specs (job_id TEXT PRIMARY KEY, size_qty_json TEXT DEFAULT '{}', total_qty INTEGER DEFAULT 0, ink_notes TEXT DEFAULT '', material_notes TEXT DEFAULT '', operator TEXT DEFAULT '', machine TEXT DEFAULT '', shift TEXT DEFAULT '', print_method TEXT DEFAULT 'Screen Print', production_notes TEXT DEFAULT '', updated_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS production_materials (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, material TEXT NOT NULL, quantity REAL DEFAULT 0, unit TEXT DEFAULT '', note TEXT DEFAULT '', created_at TEXT NOT NULL)''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_material_job ON production_materials(job_id)')
    c.execute('''CREATE TABLE IF NOT EXISTS production_checklist (job_id TEXT NOT NULL, item TEXT NOT NULL, done INTEGER DEFAULT 0, note TEXT DEFAULT '', updated_at TEXT NOT NULL, PRIMARY KEY(job_id,item))''')
    c.execute('''CREATE TABLE IF NOT EXISTS production_delivery (job_id TEXT PRIMARY KEY, status TEXT DEFAULT 'Not Ready', tracking TEXT DEFAULT '', recipient TEXT DEFAULT '', delivery_date TEXT DEFAULT '', note TEXT DEFAULT '', updated_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS production_operators (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, operator TEXT NOT NULL, role TEXT DEFAULT '', start_at TEXT DEFAULT '', end_at TEXT DEFAULT '', note TEXT DEFAULT '')''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_operator_job ON production_operators(job_id)')
    c.commit(); return c

def ensure(db): c=connect(db); c.close(); return Path(db)

def get_spec(db, job_id):
    c=connect(db); r=c.execute('SELECT * FROM production_specs WHERE job_id=?',(job_id,)).fetchone(); c.close()
    d=dict(r) if r else {'job_id':job_id,'size_qty_json':'{}','total_qty':0,'ink_notes':'','material_notes':'','operator':'','machine':'','shift':'','print_method':'Screen Print','production_notes':''}
    try: d['size_qty']=json.loads(d.pop('size_qty_json','{}') or '{}')
    except Exception: d['size_qty']={}
    return d

def save_spec(db, job_id, size_qty=None, ink_notes='', material_notes='', operator='', machine='', shift='', print_method='Screen Print', production_notes=''):
    size_qty={k:max(0,int((size_qty or {}).get(k,0) or 0)) for k in SIZE_FIELDS}; total=sum(size_qty.values()); t=now(); c=connect(db)
    c.execute('''INSERT INTO production_specs(job_id,size_qty_json,total_qty,ink_notes,material_notes,operator,machine,shift,print_method,production_notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(job_id) DO UPDATE SET size_qty_json=excluded.size_qty_json,total_qty=excluded.total_qty,ink_notes=excluded.ink_notes,material_notes=excluded.material_notes,operator=excluded.operator,machine=excluded.machine,shift=excluded.shift,print_method=excluded.print_method,production_notes=excluded.production_notes,updated_at=excluded.updated_at''',
              (job_id,json.dumps(size_qty),total,ink_notes,material_notes,operator,machine,shift,print_method,production_notes,t)); c.commit(); c.close(); return get_spec(db,job_id)

def list_materials(db, job_id):
    c=connect(db); rows=[dict(r) for r in c.execute('SELECT * FROM production_materials WHERE job_id=? ORDER BY id',(job_id,)).fetchall()]; c.close(); return rows

def add_material(db, job_id, material, quantity=0, unit='', note=''):
    if not material.strip(): raise ValueError('Material name is required')
    c=connect(db); c.execute('INSERT INTO production_materials(job_id,material,quantity,unit,note,created_at) VALUES(?,?,?,?,?,?)',(job_id,material.strip(),float(quantity or 0),unit,note,now())); c.commit(); c.close(); return list_materials(db,job_id)

def remove_material(db, material_id):
    c=connect(db); c.execute('DELETE FROM production_materials WHERE id=?',(int(material_id),)); c.commit(); ok=c.total_changes>0; c.close(); return ok

def checklist(db, job_id):
    c=connect(db)
    for item in CHECKLIST: c.execute('INSERT OR IGNORE INTO production_checklist(job_id,item,done,note,updated_at) VALUES(?,?,?,?,?)',(job_id,item,0,'',now()))
    c.commit(); rows=[dict(r) for r in c.execute('SELECT * FROM production_checklist WHERE job_id=? ORDER BY rowid',(job_id,)).fetchall()]; c.close(); return rows

def set_check(db, job_id, item, done, note=''):
    if item not in CHECKLIST: raise ValueError('Unknown checklist item')
    c=connect(db); c.execute('INSERT INTO production_checklist(job_id,item,done,note,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(job_id,item) DO UPDATE SET done=excluded.done,note=excluded.note,updated_at=excluded.updated_at',(job_id,item,int(bool(done)),note,now())); c.commit(); c.close(); return checklist(db,job_id)

def delivery(db, job_id):
    c=connect(db); r=c.execute('SELECT * FROM production_delivery WHERE job_id=?',(job_id,)).fetchone(); c.close(); return dict(r) if r else {'job_id':job_id,'status':'Not Ready','tracking':'','recipient':'','delivery_date':'','note':''}

def set_delivery(db, job_id, status='Not Ready', tracking='', recipient='', delivery_date='', note=''):
    if status not in DELIVERY_STATUSES: raise ValueError('Invalid delivery status')
    c=connect(db); c.execute('''INSERT INTO production_delivery(job_id,status,tracking,recipient,delivery_date,note,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,tracking=excluded.tracking,recipient=excluded.recipient,delivery_date=excluded.delivery_date,note=excluded.note,updated_at=excluded.updated_at''',(job_id,status,tracking,recipient,delivery_date,note,now())); c.commit(); c.close()
    return delivery(db,job_id)

def add_operator(db, job_id, operator, role='', start_at='', end_at='', note=''):
    if not operator.strip(): raise ValueError('Operator is required')
    c=connect(db); c.execute('INSERT INTO production_operators(job_id,operator,role,start_at,end_at,note) VALUES(?,?,?,?,?,?)',(job_id,operator.strip(),role,start_at,end_at,note)); c.commit(); c.close(); return operators(db,job_id)

def operators(db, job_id):
    c=connect(db); rows=[dict(r) for r in c.execute('SELECT * FROM production_operators WHERE job_id=? ORDER BY id',(job_id,)).fetchall()]; c.close(); return rows

def operations_summary(db, job_id):
    j=get_job(db,job_id)
    if not j: return None
    spec=get_spec(db,job_id); checks=checklist(db,job_id); mats=list_materials(db,job_id); ops=operators(db,job_id); dl=delivery(db,job_id)
    done=sum(int(x['done']) for x in checks); total=len(checks); return {'schema':SCHEMA,'generated_at':now(),'job':j,'production':spec,'checklist':checks,'checklist_pct':round(done/total*100,1) if total else 0,'materials':mats,'operators':ops,'delivery':dl}

def save_final_report(db, job_id, output):
    payload=operations_summary(db,job_id)
    if not payload: raise ValueError('Job not found')
    p=Path(output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8'); return p

def finalize_delivery(db, job_id):
    d=delivery(db,job_id); set_delivery(db,job_id,'Ready',d.get('tracking',''),d.get('recipient',''),d.get('delivery_date',''),d.get('note',''))
    record_event(db,job_id,'Complete','V47 production operations finalized; delivery marked Ready')
    return operations_summary(db,job_id)
