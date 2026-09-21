from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter
import json, datetime, zipfile

class Cancelled(Exception): pass

class ProductionJob:
    def __init__(self, source, out_dir, options, progress=lambda p,m:None, cancelled=lambda:False):
        self.source=Path(source); self.out=Path(out_dir); self.opt=options; self.progress=progress; self.cancelled=cancelled
        self.work=self.out/'workflow'; self.channels=self.out/'films'
        self.out.mkdir(parents=True,exist_ok=True); self.work.mkdir(exist_ok=True); self.channels.mkdir(exist_ok=True)
        self.manifest={'app':'Image Studio','version':'V20','created':datetime.datetime.now().isoformat(timespec='seconds'),
                       'source':str(self.source),'options':options,'steps':[],'warnings':[],'outputs':[]}
    def check(self):
        if self.cancelled(): raise Cancelled()
    def step(self,name,im=None):
        self.check(); self.manifest['steps'].append(name)
        if im is not None:
            p=self.work/f'{len(self.manifest["steps"]):02d}_{name}.png'; im.save(p,'PNG'); self.manifest['outputs'].append(str(p.relative_to(self.out)))
    def run(self):
        from PIL import ImageEnhance
        from production_v19 import make_print_ready, prepare_separation_source, validation_report
        from production_v18 import detect_artwork_bbox, reconstruct_print_area
        from production_v14 import derive_preview_channels, export_multi_channel, make_contact_sheet
        from production_v11 import build_underbase, alpha_morph
        self.progress(3,'Loading source')
        im=Image.open(self.source).convert('RGBA'); self.step('source',im)
        if self.opt.get('cutout'):
            self.progress(15,'Applying subject cutout')
            try:
                from ai_v17 import has_rembg, ai_subject_cutout
                if has_rembg(): im=ai_subject_cutout(im)
                else: self.manifest['warnings'].append('rembg not installed; cutout skipped')
            except Exception as e: self.manifest['warnings'].append(f'AI cutout skipped: {e}')
            self.step('cutout',im)
        if self.opt.get('reconstruct'):
            self.progress(28,'Reconstructing print area')
            try: im=reconstruct_print_area(im)
            except Exception as e: self.manifest['warnings'].append(f'Reconstruction skipped: {e}')
            self.step('reconstruct',im)
        if self.opt.get('cleanup'):
            self.progress(40,'Cleaning artwork')
            im=im.filter(ImageFilter.MedianFilter(3)); im=ImageEnhance.Sharpness(im).enhance(1.15)
            self.step('cleanup',im)
        self.progress(50,'Preparing 300 DPI source')
        im=make_print_ready(prepare_separation_source(im,300),12000); self.step('print_ready',im)
        self.check()
        mode=self.opt.get('mode','Spot'); n=int(self.opt.get('colors',6))
        self.progress(60,f'Generating {mode} channels')
        ch=derive_preview_channels(im,mode,n)
        if self.opt.get('underbase'):
            alpha=im.getchannel('A')
            ub=alpha.point(lambda p: 255 if p>8 else 0)
            choke=int(self.opt.get('choke',1))
            if choke:
                ub=ub.filter(ImageFilter.MinFilter(max(3,choke*2+1)|1))
            ch={'WHITE_UNDERBASE':ub,**ch}
        self.step('separation')
        self.progress(72,'Rendering film channels')
        manifest=export_multi_channel(ch,self.channels,300)
        self.manifest['filmset']=manifest
        for name,m in ch.items():
            if self.opt.get('halftone'):
                from app import screen_halftone
                hm=screen_halftone(m,int(self.opt.get('cell',8)),int(self.opt.get('angle',45)))
                safe=''.join(c if c.isalnum() or c in '-_' else '_' for c in name)
                p=self.channels/f'{safe}_halftone.png'; hm.save(p,'PNG',dpi=(300,300)); self.manifest['outputs'].append(str(p.relative_to(self.out)))
        contact=make_contact_sheet(ch,columns=2)
        if contact:
            p=self.out/'film_contact_sheet.png'; contact.save(p); self.manifest['outputs'].append(p.name)
        self.progress(86,'Validating output')
        self.manifest['validation']=validation_report(im,300)
        self.manifest['outputs'].append('workflow/07_print_ready.png')
        (self.out/'production_manifest.json').write_text(json.dumps(self.manifest,indent=2,ensure_ascii=False),encoding='utf-8')
        self.progress(94,'Packaging project')
        zip_path=self.out.parent/(self.out.name+'.zip')
        with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
            for p in self.out.rglob('*'):
                if p.is_file(): z.write(p,p.relative_to(self.out))
        self.progress(100,'Complete')
        return str(zip_path),self.manifest
