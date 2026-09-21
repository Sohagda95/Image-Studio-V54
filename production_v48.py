"""V48 Full System Validation & Test Center.
Runs deterministic health checks over image tools, dependencies, databases,
and V42-V47 integration without requiring the GUI.
"""
from pathlib import Path
import datetime, json, importlib.util, sqlite3, tempfile, shutil, zipfile
from PIL import Image, ImageOps

SCHEMA='ImageStudio.V48.Validation.1'
CORE_MODULES=[
 'production_v10','production_v11','production_v12','production_v13','production_v14',
 'production_v18','production_v19',
 'production_v20','production_v21','production_v22','production_v23','production_v24',
 'production_v25','production_v26','production_v27','production_v28','production_v29',
 'production_v30','production_v31','production_v32','production_v33','production_v34',
 'production_v35','production_v36','production_v37','production_v38','production_v39',
 'production_v40','production_v41','production_v42','production_v43','production_v44',
 'production_v45','production_v46','production_v47','production_v48','mockup_v16','ai_v17','interactive_dewarp']
OPTIONAL={'rembg':'AI cutout backend','cv2':'OpenCV inpainting / image utilities','pytesseract':'OCR backend','PySide6':'Desktop GUI'}


def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def result(name,status,detail='',category='System',extra=None):
    d={'name':name,'status':status,'detail':detail,'category':category}
    if extra: d.update(extra)
    return d

def check_modules():
    out=[]
    for m in CORE_MODULES:
        ok=importlib.util.find_spec(m) is not None
        out.append(result(f'Module: {m}','PASS' if ok else 'FAIL','Importable source module' if ok else 'Module not found','Dependencies'))
    return out

def check_optional():
    out=[]
    for mod,desc in OPTIONAL.items():
        try: ok=importlib.util.find_spec(mod) is not None
        except Exception: ok=False
        out.append(result(f'Optional: {mod}','PASS' if ok else 'WARNING',desc + (' available' if ok else ' not installed; fallback/feature limits apply'),'Optional Dependencies'))
    return out

def image_roundtrip(root):
    p=Path(root)/'validation_input.png'; out=Path(root)/'validation_output.png'
    im=Image.new('RGBA',(640,480),(0,0,0,0)); px=im.load()
    for y in range(480):
        for x in range(640):
            if 80<x<560 and 60<y<420: px[x,y]=(x%256,y%256,180,255)
    im.save(p,dpi=(300,300))
    loaded=Image.open(p).convert('RGBA')
    processed=ImageOps.autocontrast(loaded.convert('RGB')).convert('RGBA').resize((320,240),Image.Resampling.LANCZOS)
    processed.save(out,dpi=(300,300))
    re=Image.open(out)
    checks=[]
    checks.append(result('Image create/load','PASS' if loaded.size==(640,480) else 'FAIL',str(loaded.size),'Image Pipeline'))
    checks.append(result('Image process/resize','PASS' if re.size==(320,240) else 'FAIL',str(re.size),'Image Pipeline'))
    checks.append(result('Alpha channel','PASS' if loaded.mode=='RGBA' else 'FAIL',loaded.mode,'Image Pipeline'))
    checks.append(result('PNG output integrity','PASS' if out.stat().st_size>0 else 'FAIL',f'{out.stat().st_size} bytes','Image Pipeline'))
    return checks

def db_integrity(db_path):
    from production_v42 import upsert_job
    from production_v47 import ensure as ensure47, save_spec, checklist, set_check, set_delivery, add_material, add_operator, operations_summary
    checks=[]
    try:
        upsert_job(db_path, {'job_id':'V48-TEST-001','client':'Validation Client','order_id':'VAL-001','status':'New','priority':'Normal','garment':'Black','ink_colors':2,'dpi':300,'print_width_mm':300,'print_height_mm':400,'notes':'V48 test','tags':'validation'})
    except Exception as e:
        return [result('V42 job create','FAIL',str(e),'Database')]
    ensure47(db_path)
    save_spec(db_path,'V48-TEST-001',{'S':2,'M':3,'L':4},ink_notes='Black',operator='Tester')
    checklist(db_path,'V48-TEST-001'); set_check(db_path,'V48-TEST-001','Artwork Approved',True)
    set_delivery(db_path,'V48-TEST-001','Ready',tracking='TEST-001',recipient='Validation')
    add_material(db_path,'V48-TEST-001','Ink',1.5,'kg','test'); add_operator(db_path,'V48-TEST-001','Tester','QA')
    summary=operations_summary(db_path,'V48-TEST-001')
    checks.append(result('V42-V47 database integration','PASS' if summary and summary['production']['total_qty']==9 else 'FAIL',f"total_qty={summary['production']['total_qty'] if summary else None}",'Integration'))
    con=sqlite3.connect(db_path); tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]; con.close()
    checks.append(result('SQLite schema integrity','PASS' if 'production_specs' in tables and 'production_delivery' in tables else 'FAIL',f'{len(tables)} tables','Database'))
    return checks

def archive_integrity(root):
    from production_v41 import create_project, add_snapshot, archive_project
    proj=Path(root)/'archive_project'; src=Path(root)/'archive_source.txt'; src.write_text('V48 validation',encoding='utf-8')
    create_project(proj,'V48 Test Project','validation','test')
    add_snapshot(proj,[src],label='V48 Validation',copy_sources=True)
    z=Path(root)/'archive_test.zip'; archive_project(proj,z)
    ok=z.exists() and zipfile.is_zipfile(z)
    return [result('V41 project snapshot/archive','PASS' if ok else 'FAIL',str(z),'Archive')]

def run_validation(output_dir=None):
    temp_owned=output_dir is None
    root=Path(output_dir or tempfile.mkdtemp(prefix='image_studio_v48_')); root.mkdir(parents=True,exist_ok=True)
    results=[]
    try:
        results += check_modules(); results += check_optional(); results += image_roundtrip(root)
        results += db_integrity(root/'v48_validation.db'); results += archive_integrity(root)
    except Exception as e:
        results.append(result('Validation runner','FAIL',repr(e),'System'))
    passed=sum(x['status']=='PASS' for x in results); warnings=sum(x['status']=='WARNING' for x in results); failed=sum(x['status']=='FAIL' for x in results)
    report={'schema':SCHEMA,'generated_at':now(),'summary':{'total':len(results),'passed':passed,'warnings':warnings,'failed':failed,'overall':'FAIL' if failed else ('WARNING' if warnings else 'PASS')},'results':results}
    if output_dir:
        p=root/'v48_validation_report.json'; p.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8'); report['report_path']=str(p)
    if temp_owned: shutil.rmtree(root,ignore_errors=True)
    return report

def save_report(report, output):
    p=Path(output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8'); return p
