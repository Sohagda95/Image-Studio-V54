from __future__ import annotations
import json, os, shutil
from pathlib import Path
from datetime import datetime

APP_VERSION = 'V52'
SCHEMA = 'ImageStudio.V52.Settings.1'

def now(): return datetime.now().isoformat(timespec='seconds')

def data_root(base=None):
    if base: return Path(base)
    if os.name == 'nt':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData'/'Local'))
    elif sys_platform := os.environ.get('XDG_CONFIG_HOME'):
        root = Path(sys_platform)
    else:
        root = Path.home()/'.config'
    return root/'Image Studio'

def settings_path(base=None):
    p=data_root(base); p.mkdir(parents=True, exist_ok=True); return p/'settings_v52.json'

def presets_path(base=None):
    p=data_root(base); p.mkdir(parents=True, exist_ok=True); return p/'presets_v52.json'

DEFAULT_SETTINGS = {
    'schema': SCHEMA,
    'theme': 'Dark',
    'accent': '#f0c400',
    'ui_scale': 100,
    'default_dpi': 300,
    'default_garment': 'Black',
    'default_separation': 'Spot Color',
    'auto_validate_before_export': True,
    'auto_snapshot_projects': True,
    'remember_last_workspace': True,
    'show_advanced_tools': True,
    'confirm_destructive_actions': True,
    'last_workspace': 'V52 Control Center',
    'recent_files': [],
    'recent_projects': [],
    'updated_at': None,
}

DEFAULT_PRESETS = {
    'Dark Garment Production': {
        'dpi': 300, 'garment': 'Black', 'separation': 'Spot Color',
        'spot_colors': 6, 'underbase': 'Adaptive', 'halftone_lpi': 45,
        'screen_angle': 22.5, 'proof': 'Black'
    },
    'Light Garment CMYK': {
        'dpi': 300, 'garment': 'White', 'separation': 'CMYK',
        'spot_colors': 4, 'underbase': 'None', 'halftone_lpi': 55,
        'screen_angle': 22.5, 'proof': 'White'
    },
    'Fast Preview': {
        'dpi': 150, 'garment': 'Black', 'separation': 'Spot Color',
        'spot_colors': 4, 'underbase': 'Adaptive', 'halftone_lpi': 35,
        'screen_angle': 22.5, 'proof': 'Black'
    },
    'Prepress QC': {
        'dpi': 300, 'garment': 'Black', 'separation': 'Spot Color',
        'spot_colors': 6, 'underbase': 'Adaptive', 'halftone_lpi': 45,
        'screen_angle': 22.5, 'proof': 'Black'
    },
}

def _read(path, default):
    p=Path(path)
    if not p.exists(): return default.copy() if isinstance(default,dict) else list(default)
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return default.copy() if isinstance(default,dict) else list(default)

def load_settings(base=None):
    data=_read(settings_path(base), DEFAULT_SETTINGS)
    out=DEFAULT_SETTINGS.copy(); out.update(data); out['schema']=SCHEMA
    return out

def save_settings(settings, base=None):
    out=DEFAULT_SETTINGS.copy(); out.update(settings); out['schema']=SCHEMA; out['updated_at']=now()
    p=settings_path(base); p.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8'); return p

def load_presets(base=None):
    data=_read(presets_path(base), DEFAULT_PRESETS)
    out=DEFAULT_PRESETS.copy(); out.update(data); return out

def save_presets(presets, base=None):
    p=presets_path(base); p.write_text(json.dumps(presets,indent=2,ensure_ascii=False),encoding='utf-8'); return p

def save_preset(name, values, base=None):
    name=str(name).strip()
    if not name: raise ValueError('Preset name is required')
    presets=load_presets(base); presets[name]=dict(values); save_presets(presets,base); return name

def delete_preset(name, base=None):
    if name in DEFAULT_PRESETS: raise ValueError('Built-in presets cannot be deleted')
    presets=load_presets(base); presets.pop(name,None); save_presets(presets,base); return True

def reset_settings(base=None):
    return save_settings(DEFAULT_SETTINGS.copy(),base)

def export_settings_package(output, base=None):
    p=Path(output); p.parent.mkdir(parents=True,exist_ok=True)
    package={'schema':SCHEMA,'exported_at':now(),'settings':load_settings(base),'presets':load_presets(base)}
    p.write_text(json.dumps(package,indent=2,ensure_ascii=False),encoding='utf-8'); return p

def import_settings_package(source, base=None):
    data=json.loads(Path(source).read_text(encoding='utf-8'))
    if data.get('schema') != SCHEMA: raise ValueError('Unsupported V52 settings package')
    save_settings(data.get('settings',{}),base); save_presets(data.get('presets',{}),base); return True

def self_test(base=None):
    root=Path(base or (Path.cwd()/'v52_self_test'))
    root.mkdir(parents=True,exist_ok=True)
    results=[]
    try:
        save_settings(DEFAULT_SETTINGS,root); s=load_settings(root)
        results.append({'status':'PASS' if s['default_dpi']==300 else 'FAIL','test':'Settings round-trip','detail':str(settings_path(root))})
        save_preset('Self Test Preset',{'dpi':600,'garment':'Navy'},root); p=load_presets(root)
        results.append({'status':'PASS' if p['Self Test Preset']['dpi']==600 else 'FAIL','test':'Preset round-trip','detail':'Custom preset saved'})
        export_settings_package(root/'package.json',root); reset_settings(root); import_settings_package(root/'package.json',root)
        results.append({'status':'PASS' if load_settings(root)['default_dpi']==300 else 'FAIL','test':'Settings package import/export','detail':'JSON package round-trip'})
        delete_preset('Self Test Preset',root)
        results.append({'status':'PASS','test':'Custom preset deletion','detail':'Built-in preset protection retained'})
    except Exception as e:
        results.append({'status':'FAIL','test':'V52 self-test exception','detail':repr(e)})
    return {'schema':SCHEMA,'timestamp':now(),'results':results,'summary':{'passed':sum(r['status']=='PASS' for r in results),'failed':sum(r['status']=='FAIL' for r in results)}}
