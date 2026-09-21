from __future__ import annotations
from pathlib import Path
import copy, datetime, json
from production_v28 import V28_PRESETS, normalize_job, apply_preset_to_job, estimate_job_stats

APP_VERSION='V29'

WORKSPACE_PRESETS = copy.deepcopy(V28_PRESETS)
WORKSPACE_PRESETS.update({
    'Dark Garment 8-Color Pro': {**V28_PRESETS['Dark Garment 6-Color'], 'colors':8, 'halftone':True, 'cell':7, 'angle':45, 'target_dpi':300},
    'Film Preview': {**V28_PRESETS['Production Proof'], 'halftone':True, 'cell':6, 'target_dpi':300},
    'High Quality Light': {**V28_PRESETS['Light Garment CMYK'], 'target_dpi':300, 'cell':6, 'angle':22},
})

def workspace_payload(jobs, output_root=''):
    return {
        'version': APP_VERSION,
        'saved_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'output_root': output_root,
        'jobs': [normalize_job(j) for j in jobs],
    }

def save_workspace(path, jobs, output_root=''):
    Path(path).write_text(json.dumps(workspace_payload(jobs, output_root), indent=2, ensure_ascii=False), encoding='utf-8')

def load_workspace(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    return data.get('jobs',[]), data.get('output_root','')

def make_workspace_summary(jobs):
    existing=sum(Path(j.get('source','')).exists() for j in jobs)
    return {
        'version':APP_VERSION,
        'jobs':len(jobs),
        'existing_sources':existing,
        'missing_sources':len(jobs)-existing,
        'estimated_megapixels':round(sum(estimate_job_stats(j).get('megapixels',0) for j in jobs),2),
        'presets':sorted({j.get('preset','') for j in jobs if j.get('preset')}),
    }
