"""V45 integrated job-to-production automation.
Links V42/V43 jobs, V44 smart workflow, and V41 project snapshots.
All processing is local and deterministic; no calibrated RIP/ICC claims.
"""
from pathlib import Path
import json, datetime, shutil
from production_v42 import get_job, upsert_job
from production_v43 import record_event, job_history
from production_v44 import run_workflow
from production_v41 import add_snapshot, list_versions

SCHEMA='ImageStudio.V45.JobProductionAutomation.1'


def now(): return datetime.datetime.now().isoformat(timespec='seconds')


def run_job(db, job_id, output_root, options=None, progress=None, cancel=None, snapshot=True):
    job=get_job(db,job_id)
    if not job: raise ValueError(f'Job not found: {job_id}')
    source=Path(job.get('artwork_path','')).expanduser()
    if not source.exists(): raise FileNotFoundError(f'Artwork not found: {source}')
    root=Path(output_root); root.mkdir(parents=True,exist_ok=True)
    safe=''.join(c if c.isalnum() or c in '-_.' else '_' for c in job_id)
    out=root/safe
    def emit(p,m):
        if progress: progress(p,m)
    record_event(db,job_id,'In Production','V45 Smart Workflow started')
    upsert_job(db,dict(job,status='In Production'))
    try:
        manifest=run_workflow(str(source),str(out),options or {},progress=progress,cancel=cancel)
        # attach job identity to the manifest for traceability
        manifest['job']={'job_id':job_id,'client':job.get('client',''),'order_id':job.get('order_id','')}
        manifest['v45_finished_at']=now()
        (out/'v45_job_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
        if snapshot and job.get('project_folder'):
            proj=Path(job['project_folder'])
            if proj.exists() and proj.is_dir():
                files=[Path(x) for x in [source, out/'02_print_ready.png', out/'03_qc_report.json', out/'workflow_manifest.json', out/'v45_job_manifest.json'] if Path(x).exists()]
                try:
                    snap=add_snapshot(proj,files,label=f'V45 {job_id}',notes='Smart production workflow output',settings=options or {},copy_sources=True)
                    manifest['v41_snapshot']=snap
                    (out/'v45_job_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
                    upsert_job(db,dict(job,status='Complete',v41_project=str(proj),v41_version=int(snap.get('version',0))))
                except Exception as e:
                    manifest['v41_snapshot_error']=str(e)
                    upsert_job(db,dict(job,status='Complete'))
            else:
                upsert_job(db,dict(job,status='Complete'))
        else:
            upsert_job(db,dict(job,status='Complete'))
        record_event(db,job_id,'Complete','V45 workflow completed')
        emit(100,'Job complete.')
        return manifest
    except Exception as e:
        upsert_job(db,dict(job,status='Hold',notes=(job.get('notes','')+'\nV45 error: '+str(e)).strip()))
        record_event(db,job_id,'Hold',f'V45 workflow failed: {e}')
        raise


def job_package_path(output_root,job_id):
    safe=''.join(c if c.isalnum() or c in '-_.' else '_' for c in job_id)
    p=Path(output_root)/safe/'production_package.zip'
    return p if p.exists() else None


def job_summary(db,job_id):
    j=get_job(db,job_id)
    if not j: return None
    return {'job':j,'history':job_history(db,job_id)}
