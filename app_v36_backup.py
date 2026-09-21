
import sys, os, math, traceback, json, zipfile, datetime
from pathlib import Path
from PIL import Image, ImageDraw
from production_v19 import ProductionPipeline, prepare_separation_source, make_print_ready, validation_report
from production_v20 import ProductionJob, Cancelled
from production_v21 import make_print_sheet, save_layout_package, DEFAULT_PRESETS
from production_v22 import ItemSpec, export_gang_package, JobQueue
from production_v23 import validate_artworks, validate_job, save_preset, load_preset, make_job_report, export_report, package_job
from production_v24 import BatchProductionRunner
from production_v25 import ProductionQueueManager, save_queue, load_queue, save_template, load_template
from production_v26 import scan_paths, save_library, load_library, make_library_report
from production_v27 import STATUSES, enrich_item, save_library_v27, load_library_v27, make_contact_sheet, make_library_report_v27, make_queue_jobs
from production_v28 import V28_PRESETS, apply_preset_to_job, normalize_job, queue_from_library_items, estimate_job_stats
from production_v29 import WORKSPACE_PRESETS, save_workspace, load_workspace, make_workspace_summary
from production_v30 import export_artwork_package, safe_name
from production_v31 import build_print_intelligence, garment_proof, registration_overlay, save_intelligence_report
from production_v32 import rgb_to_lab, delta_e76, hex_to_rgb, rgb_to_hex, sample_palette, palette_distance_report, spot_mask, mask_stats, separation_diagnostics, make_lab_report
from production_v33 import DEFAULT_SPOT_LIBRARY, load_spot_library, save_spot_library, make_spot_channels, overlap_matrix, exclusive_knockout_channels, trap_mask, trapping_diagnostics, channel_contact_sheet, separation_report, save_separation_report
from production_v34 import lpi_to_cell_px, halftone_channel, simulate_film, halftone_contact_sheet, halftone_report, export_halftone_set
from production_v35 import GARMENTS, build_underbase_v35, coverage as underbase_coverage, preview_underbase, compare_underbases, underbase_report, export_underbase_set
from production_v36 import reconstruct_v36, reconstruction_report, export_reconstruction, difference_stats, estimate_print_bbox
from production_v18 import detect_artwork_bbox, reconstruct_print_area, ai_upscale_optional, estimate_print_area_score
from ai_v17 import has_rembg, ai_subject_cutout, remove_soft_shadows, artwork_cleanup, white_balance
from mockup_v16 import extract_artwork
from interactive_dewarp import QuadEditor
from production_v14 import derive_preview_channels, export_multi_channel, make_contact_sheet, quad_from_margins
from production_v13 import export_channels, angle_preview, build_separation_manifest, ANGLE_PRESETS, CancellableQueue
from production_v12 import ink_proof, registration_marks, film_sheet, JobQueue, INK_COLORS
from production_v11 import alpha_morph, apply_trap, channel_preview, build_underbase
from production_v10 import perspective_dewarp, History, batch_process
from production_engine import alpha_cleanup, flatten_on_garment, export_tiff, export_png, export_jpeg
from production_core import save_project, load_project, make_production_report, write_json
from ai_backends import has_rembg, rembg_cutout, ImageFilter, ImageEnhance, ImageOps, ImageDraw, ImageChops
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import *

APP_NAME = "Image Studio V36 — T-Shirt Production Suite"

def load_image(path):
    return Image.open(path).convert("RGBA")

def to_qpixmap(img):
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    q = QImage(data, img.width, img.height, img.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(q.copy())

def preview_image(img, max_size=(760, 520)):
    x = img.copy()
    x.thumbnail(max_size, Image.Resampling.LANCZOS)
    bg = Image.new("RGBA", x.size, (238,238,238,255))
    d = ImageDraw.Draw(bg)
    cell = 16
    for y in range(0, x.height, cell):
        for xx in range(0, x.width, cell):
            if (xx//cell + y//cell) % 2:
                d.rectangle((xx,y,xx+cell-1,y+cell-1), fill=(205,205,205,255))
    return Image.alpha_composite(bg, x)

# ---------- Core image processing ----------
def cutout_simple(im, tolerance=28):
    x = im.copy()
    p = x.load(); w,h = x.size
    samples = [p[a,b][:3] for a,b in [(0,0),(w-1,0),(0,h-1),(w-1,h-1)]]
    for y in range(h):
        for xx in range(w):
            c = p[xx,y][:3]
            if min(sum((c[i]-s[i])**2 for i in range(3))**0.5 for s in samples) < tolerance:
                p[xx,y] = (*c,0)
    return x

def cleanup(im, denoise=True, contrast=1.0, sharp=1.15):
    x = im
    if denoise: x = x.filter(ImageFilter.MedianFilter(3))
    x = ImageEnhance.Contrast(x).enhance(contrast)
    return ImageEnhance.Sharpness(x).enhance(sharp)

def upscale(im, scale=2):
    x = im.resize((im.width*scale, im.height*scale), Image.Resampling.LANCZOS)
    return ImageEnhance.Sharpness(x).enhance(1.25)

def mockup_extract(im, margin=.18):
    w,h = im.size
    return im.crop((int(w*margin), int(h*.12), int(w*(1-margin)), int(h*.90)))

# ---------- Color science ----------
def rgb_to_lab(rgb):
    vals=[]
    for c in rgb:
        c=c/255.0
        vals.append(((c+0.055)/1.055)**2.4 if c>0.04045 else c/12.92)
    r,g,b=vals
    x=(r*.4124564+g*.3575761+b*.1804375)/.95047
    y=(r*.2126729+g*.7151522+b*.0721750)
    z=(r*.0193339+g*.1191922+b*.9503041)/1.08883
    def f(t): return t**(1/3) if t>.008856 else 7.787*t+16/116
    X,Y,Z=f(x),f(y),f(z)
    return (116*Y-16,500*(X-Y),200*(Y-Z))

def delta_e76(a,b):
    return sum((x-y)**2 for x,y in zip(a,b))**0.5

def quantized_palette(im, n):
    q = im.convert("RGB").quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal=q.getpalette()
    ranked=sorted(q.getcolors(im.width*im.height), reverse=True)
    return [tuple(pal[idx*3:idx*3+3]) for count,idx in ranked[:n]]

def spot_masks(im, colors, tolerance):
    rgb=im.convert("RGB"); px=rgb.load()
    labs=[rgb_to_lab(c) for c in colors]
    masks=[Image.new("L", im.size, 0) for _ in colors]
    mp=[m.load() for m in masks]
    for y in range(im.height):
        for x in range(im.width):
            L=rgb_to_lab(px[x,y])
            ds=[delta_e76(L,c) for c in labs]
            i=min(range(len(ds)), key=ds.__getitem__)
            if ds[i] <= tolerance:
                mp[i][x,y]=255
    return masks

def cmyk_masks(im):
    c=im.convert("CMYK")
    return [c.getchannel(i) for i in range(4)], ["Cyan","Magenta","Yellow","Black"]

def morph(mask, px, mode):
    if px <= 0: return mask
    n=max(3, int(px)*2+1)
    if n%2==0:n+=1
    return mask.filter(ImageFilter.MinFilter(n) if mode=="choke" else ImageFilter.MaxFilter(n))

def underbase_mask(im, mode="adaptive", threshold=8, strength=95, choke=1):
    alpha=im.getchannel("A")
    gray=ImageOps.grayscale(im)
    if mode=="solid":
        u=alpha.point(lambda p:255 if p>threshold else 0)
    elif mode=="luma":
        u=ImageChops.multiply(alpha, ImageOps.invert(gray))
        u=u.point(lambda p:int(p*strength/100))
    else:
        inv=ImageOps.invert(gray).point(lambda p:int(p*strength/100))
        u=ImageChops.lighter(ImageChops.multiply(alpha,inv),
                             alpha.point(lambda p:255 if p>threshold else 0))
    return morph(u,choke,"choke") if choke else u

def screen_halftone(mask, cell=8, angle=45):
    """Rotated halftone preview using a temporary rotated coordinate system."""
    m=mask.convert("L")
    # Rotate the coverage field, create dots, then rotate back.
    pad=max(4, cell*2)
    padded=Image.new("L",(m.width+pad*2,m.height+pad*2),255)
    padded.paste(m,(pad,pad))
    rot=padded.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC, fillcolor=255)
    out=Image.new("L",rot.size,255); d=ImageDraw.Draw(out)
    for y in range(0,rot.height,cell):
        for x in range(0,rot.width,cell):
            crop=rot.crop((x,y,min(x+cell,rot.width),min(y+cell,rot.height)))
            if crop.width*crop.height==0: continue
            avg=sum(crop.getdata())/(crop.width*crop.height)
            r=(1-avg/255)*(cell/2-.6)
            if r>0:
                cx=x+cell/2; cy=y+cell/2
                d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=0)
    back=out.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC, fillcolor=255)
    # crop center back to original size
    left=(back.width-m.width)//2; top=(back.height-m.height)//2
    return back.crop((left,top,left+m.width,top+m.height))

def registration_preview(channels, margin=70):
    if not channels:return None
    w,h=channels[0].size
    out=Image.new("RGBA",(w+2*margin,h+2*margin),(255,255,255,255))
    d=ImageDraw.Draw(out)
    pts=[(margin,margin),(margin+w,margin),(margin,margin+h),(margin+w,margin+h),
         (margin+w//2,margin),(margin+w//2,margin+h),(margin,margin+h//2),(margin+w,margin+h//2)]
    for x,y in pts:
        d.line((x-18,y,x+18,y),fill="black",width=1)
        d.line((x,y-18,x,y+18),fill="black",width=1)
        d.ellipse((x-5,y-5,x+5,y+5),outline="black",width=1)
    return out

def garment_preview(channels, garment_rgb):
    if not channels:return None
    w,h=channels[0].size
    base=Image.new("RGBA",(w,h),(*garment_rgb,255))
    # Show channels as density layers, neutralized for proofing.
    for m in channels:
        layer=Image.new("RGBA",(w,h),(255,255,255,0))
        layer.putalpha(m)
        base=Image.alpha_composite(base,layer)
    return base

# ---------- UI ----------
class Worker(QThread):
    ok=Signal(object); fail=Signal(str)
    def __init__(self,fn): super().__init__(); self.fn=fn
    def run(self):
        try:self.ok.emit(self.fn())
        except Exception:self.fail.emit(traceback.format_exc())

class DropLabel(QLabel):
    fileDropped=Signal(str)
    def __init__(self):
        super().__init__("Open or drop an image here")
        self.setAcceptDrops(True); self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(700,430)
        self.setStyleSheet("background:#111;border:1px solid #333;border-radius:12px;color:#888")
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self,e):
        urls=e.mimeData().urls()
        if urls:self.fileDropped.emit(urls[0].toLocalFile())

class BasicTab(QWidget):
    def __init__(self):
        super().__init__(); self.im=None; self.result=None; self.path=None
        self.view=DropLabel(); self.view.fileDropped.connect(self.load_path)
        self.open=QPushButton("Open");self.go=QPushButton("Process");self.save=QPushButton("Save");self.save.setEnabled(False)
        self.status=QLabel("Ready")
        row=QHBoxLayout();row.addWidget(self.open);row.addWidget(self.go);row.addWidget(self.save);row.addStretch();row.addWidget(self.status)
        l=QVBoxLayout(self);l.addLayout(row);l.addWidget(self.view,1)
        self.open.clicked.connect(self.pick);self.go.clicked.connect(self.process);self.save.clicked.connect(self.save_result);self.go.setEnabled(False)
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,"Image","","Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if p:self.load_path(p)
    def load_path(self,p):
        self.path=p;self.im=load_image(p);self.result=None;self.go.setEnabled(True);self.show_im(self.im);self.status.setText(Path(p).name)
    def show_im(self,im):self.view.setPixmap(to_qpixmap(preview_image(im)).scaled(self.view.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
    def resizeEvent(self,e):
        if self.result:self.show_im(self.result)
        elif self.im:self.show_im(self.im)
        super().resizeEvent(e)
    def process(self):
        self.go.setEnabled(False);self.status.setText("Processing…")
        self.w=Worker(self.work);self.w.ok.connect(self.done);self.w.fail.connect(self.err);self.w.start()
    def work(self):return self.im.copy()
    def done(self,x):self.result=x;self.show_im(x);self.go.setEnabled(True);self.save.setEnabled(True);self.status.setText("Done")
    def err(self,s):self.go.setEnabled(True);QMessageBox.critical(self,"Error",s)
    def save_result(self):
        p,_=QFileDialog.getSaveFileName(self,"Save","","PNG (*.png);;TIFF (*.tif);;JPEG (*.jpg)")
        if p:
            x=self.result.convert("RGB") if p.lower().endswith(".jpg") else self.result
            x.save(p)
            self.status.setText("Saved")

class CutoutTab(BasicTab):
    def __init__(self):
        super().__init__();b=QGroupBox("Cutout");f=QFormLayout(b);self.t=QSlider(Qt.Horizontal);self.t.setRange(5,80);self.t.setValue(28);f.addRow("Tolerance",self.t);self.layout().insertWidget(0,b)
    def work(self):return cutout_simple(self.im,self.t.value())

class CleanupTab(BasicTab):
    def __init__(self):
        super().__init__();b=QGroupBox("Cleanup");f=QFormLayout(b);self.c=QSlider(Qt.Horizontal);self.c.setRange(80,140);self.c.setValue(100);f.addRow("Contrast",self.c);self.layout().insertWidget(0,b)
    def work(self):return cleanup(self.im,True,self.c.value()/100)

class EnhanceTab(BasicTab):
    def __init__(self):
        super().__init__();b=QGroupBox("Enhance");f=QFormLayout(b);self.s=QComboBox();self.s.addItems(["2×","4×"]);f.addRow("Scale",self.s);self.layout().insertWidget(0,b)
    def work(self):return upscale(self.im,4 if self.s.currentText()=="4×" else 2)

class MockupTab(BasicTab):
    def __init__(self):
        super().__init__();self.layout().insertWidget(0,QLabel("MVP garment crop. Replace with AI garment/artwork segmentation for production."))
    def work(self):return mockup_extract(self.im)

class SeparationTab(QWidget):
    def __init__(self):
        super().__init__(); self.im=None;self.channels=[];self.names=[]
        self.view=DropLabel();self.view.fileDropped.connect(self.load_path)
        self.open=QPushButton("Open Artwork");self.generate=QPushButton("Generate");self.export=QPushButton("Export Project");self.export.setEnabled(False)
        self.method=QComboBox();self.method.addItems(["Spot Color","CMYK"])
        self.n=QSpinBox();self.n.setRange(2,16);self.n.setValue(6)
        self.de=QSpinBox();self.de.setRange(1,60);self.de.setValue(18)
        self.ub=QCheckBox("White underbase");self.ub.setChecked(True)
        self.ubmode=QComboBox();self.ubmode.addItems(["Adaptive","Solid","Luma"])
        self.ubstrength=QSlider(Qt.Horizontal);self.ubstrength.setRange(50,100);self.ubstrength.setValue(95)
        self.choke=QSpinBox();self.choke.setRange(0,10);self.choke.setValue(1)
        self.cell=QSpinBox();self.cell.setRange(3,40);self.cell.setValue(8)
        self.angle=QSpinBox();self.angle.setRange(0,179);self.angle.setValue(45)
        self.halftone=QCheckBox("Use halftone in export")
        self.dpi=QSpinBox();self.dpi.setRange(72,1200);self.dpi.setValue(300)
        self.garment=QComboBox()
        garments={"Black":(20,20,20),"White":(245,245,245),"Navy":(25,35,70),"Red":(145,25,25),"Royal Blue":(30,65,150),"Dark Gray":(55,55,58)}
        for k,v in garments.items():self.garment.addItem(k,v)
        self.list=QListWidget();self.list.currentRowChanged.connect(self.preview_channel)
        self.info=QLabel("Load artwork. Recommended source: high-resolution PNG with transparency.")
        self.info.setWordWrap(True)
        box=QGroupBox("Professional Screen-Print Controls");f=QFormLayout(box)
        f.addRow("Separation",self.method);f.addRow("Spot colors",self.n);f.addRow("ΔE tolerance",self.de)
        f.addRow(self.ub);f.addRow("Underbase mode",self.ubmode);f.addRow("Underbase strength",self.ubstrength)
        f.addRow("Underbase choke",self.choke);f.addRow("Halftone cell",self.cell);f.addRow("Screen angle",self.angle)
        f.addRow("Output DPI",self.dpi);f.addRow("Garment",self.garment);f.addRow(self.halftone)
        buttons=QHBoxLayout();buttons.addWidget(self.open);buttons.addWidget(self.generate);buttons.addWidget(self.export);buttons.addStretch()
        left=QVBoxLayout();left.addWidget(box);left.addLayout(buttons);left.addWidget(self.info);left.addWidget(QLabel("Channels"));left.addWidget(self.list)
        main=QHBoxLayout();main.addLayout(left,0);main.addWidget(self.view,1)
        lay=QVBoxLayout(self);lay.addLayout(main)
        self.open.clicked.connect(self.pick);self.generate.clicked.connect(self.make);self.export.clicked.connect(self.export_project)
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,"Artwork","","Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if p:self.load_path(p)
    def load_path(self,p):
        self.path=p;self.im=load_image(p);self.show(self.im);self.info.setText(f"{Path(p).name} • {self.im.width}×{self.im.height}")
    def show(self,im):self.view.setPixmap(to_qpixmap(preview_image(im)).scaled(self.view.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
    def resizeEvent(self,e):
        if self.im:self.show(self.im)
        super().resizeEvent(e)
    def make(self):
        if not self.im:return
        if self.method.currentText()=="CMYK":
            self.channels,self.names=cmyk_masks(self.im)
        else:
            cols=quantized_palette(self.im,self.n.value())
            self.channels=spot_masks(self.im,cols,self.de.value())
            self.names=[f"Spot {i+1} RGB {c}" for i,c in enumerate(cols)]
        if self.ub.isChecked():
            self.channels.insert(0,underbase_mask(self.im,self.ubmode.currentText().lower(),strength=self.ubstrength.value(),choke=self.choke.value()))
            self.names.insert(0,"WHITE UNDERBASE")
        self.list.clear();self.list.addItems(self.names);self.export.setEnabled(bool(self.channels))
        if self.channels:self.list.setCurrentRow(0)
    def preview_channel(self,row):
        if row<0 or row>=len(self.channels):return
        m=self.channels[row]
        if self.halftone.isChecked():m=screen_halftone(m,self.cell.value(),self.angle.value())
        inv=ImageOps.invert(m)
        self.show(Image.merge("RGBA",(inv,inv,inv,Image.new("L",inv.size,255))))
    def export_project(self):
        if not self.channels:return
        out=QFileDialog.getExistingDirectory(self,"Choose project folder")
        if not out:return
        out=Path(out);out.mkdir(exist_ok=True)
        project=out/"separations";project.mkdir(exist_ok=True)
        for i,(m,n) in enumerate(zip(self.channels,self.names),1):
            safe="".join(c if c.isalnum() or c in "-_" else "_" for c in n)[:70]
            m.save(project/f"{i:02d}_{safe}.png")
            if self.halftone.isChecked():
                screen_halftone(m,self.cell.value(),self.angle.value()).save(project/f"{i:02d}_{safe}_halftone.png")
        reg=registration_preview(self.channels)
        if reg:reg.save(out/"registration_preview.png")
        proof=garment_preview(self.channels,self.garment.currentData())
        if proof:proof.save(out/"garment_proof.png")
        settings={
            "app":"Image Studio V6","source":str(self.path),"width_px":self.im.width,"height_px":self.im.height,
            "output_dpi":self.dpi.value(),"method":self.method.currentText(),"spot_colors":self.n.value(),
            "deltaE76_tolerance":self.de.value(),"underbase":self.ub.isChecked(),"underbase_mode":self.ubmode.currentText(),
            "underbase_strength":self.ubstrength.value(),"underbase_choke_px":self.choke.value(),
            "halftone_cell_px":self.cell.value(),"screen_angle_deg":self.angle.value(),
            "halftone_export":self.halftone.isChecked(),"garment":self.garment.currentText()
        }
        (out/"settings.json").write_text(json.dumps(settings,indent=2),encoding="utf-8")
        zipname=out.with_suffix(".zip")
        with zipfile.ZipFile(zipname,"w",zipfile.ZIP_DEFLATED) as z:
            for p in out.rglob("*"):
                if p.is_file() and p != zipname:z.write(p,p.relative_to(out))
        QMessageBox.information(self,"Project exported",f"Project folder and ZIP created:\n{zipname}")


class DewarpTab(QWidget):
    def __init__(self):
        super().__init__()
        self.im=None
        self.editor=QuadEditor()
        self.open_btn=QPushButton("Open Image")
        self.apply_btn=QPushButton("Apply Dewarp")
        self.reset_btn=QPushButton("Reset Corners")
        self.apply_btn.setEnabled(False)
        self.info=QLabel("Drag the 4 red corners to match the artwork/garment area.")
        row=QHBoxLayout()
        row.addWidget(self.open_btn); row.addWidget(self.reset_btn); row.addWidget(self.apply_btn)
        layout=QVBoxLayout(self); layout.addLayout(row); layout.addWidget(self.info); layout.addWidget(self.editor,1)
        self.open_btn.clicked.connect(self.open_image)
        self.reset_btn.clicked.connect(self.reset)
        self.apply_btn.clicked.connect(self.apply)

    def open_image(self):
        path,_=QFileDialog.getOpenFileName(self,"Open Image","","Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if not path:return
        self.im=load_image(path); self.editor.set_image(self.im); self.apply_btn.setEnabled(True)
        self.info.setText(f"{Path(path).name} — drag corners, then Apply Dewarp.")

    def reset(self):
        if self.im is not None:self.editor.set_image(self.im)

    def apply(self):
        if self.im is None:return
        try:
            out=perspective_dewarp(self.im,self.editor.points)
            path,_=QFileDialog.getSaveFileName(self,"Save Dewarped Image","","PNG (*.png);;TIFF (*.tif *.tiff)")
            if not path:return
            if path.lower().endswith((".tif",".tiff")):out.save(path,"TIFF",compression="tiff_lzw",dpi=(300,300))
            else:out.save(path,"PNG")
            self.info.setText(f"Dewarped output saved: {Path(path).name}")
        except Exception as e:
            QMessageBox.warning(self,"Dewarp",str(e))



class MockupFlatTab(QWidget):
    def __init__(self):
        super().__init__()
        self.im=None
        self.editor=QuadEditor()
        self.open_btn=QPushButton("Open Mockup")
        self.extract_btn=QPushButton("Extract Artwork")
        self.reset_btn=QPushButton("Reset")
        self.extract_btn.setEnabled(False)
        self.bg=QSpinBox(); self.bg.setRange(0,80); self.bg.setValue(18)
        self.info=QLabel("Select the artwork/print area with the 4 corners.")
        row=QHBoxLayout()
        row.addWidget(self.open_btn); row.addWidget(self.reset_btn); row.addWidget(self.extract_btn)
        row.addWidget(QLabel("Background tolerance")); row.addWidget(self.bg)
        layout=QVBoxLayout(self); layout.addLayout(row); layout.addWidget(self.info); layout.addWidget(self.editor,1)
        self.open_btn.clicked.connect(self.open_image)
        self.reset_btn.clicked.connect(self.reset)
        self.extract_btn.clicked.connect(self.extract)

    def open_image(self):
        path,_=QFileDialog.getOpenFileName(self,"Open Mockup","","Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if not path:return
        self.im=load_image(path)
        self.editor.set_image(self.im)
        self.extract_btn.setEnabled(True)
        self.info.setText(f"{Path(path).name} — place corners around the printed artwork.")

    def reset(self):
        if self.im is not None:self.editor.set_image(self.im)

    def extract(self):
        if self.im is None:return
        try:
            out=extract_artwork(self.im,self.editor.points,self.bg.value(),1)
            path,_=QFileDialog.getSaveFileName(self,"Save Flat Artwork","","PNG (*.png);;TIFF (*.tif *.tiff)")
            if not path:return
            if path.lower().endswith((".tif",".tiff")):
                out.save(path,"TIFF",compression="tiff_lzw",dpi=(300,300))
            else: out.save(path,"PNG")
            self.info.setText(f"Artwork extracted: {Path(path).name}")
        except Exception as e:
            QMessageBox.warning(self,"Mockup → Flat",str(e))


class BatchTab(QWidget):
    def __init__(self):
        super().__init__();self.files=[]
        self.info=QLabel("No files selected");self.pick=QPushButton("Select Images");self.run=QPushButton("Batch Cleanup");self.run.setEnabled(False)
        l=QVBoxLayout(self);l.addWidget(self.info);l.addWidget(self.pick);l.addWidget(self.run);l.addStretch()
        self.pick.clicked.connect(self.select);self.run.clicked.connect(self.process)
    def select(self):
        self.files,_=QFileDialog.getOpenFileNames(self,"Select","","Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if self.files:self.info.setText("\n".join(Path(x).name for x in self.files[:25]));self.run.setEnabled(True)
    def process(self):
        out=QFileDialog.getExistingDirectory(self,"Output")
        if not out:return
        for p in self.files:cleanup(load_image(p)).save(Path(out)/(Path(p).stem+"_clean.png"))
        QMessageBox.information(self,"Complete",f"{len(self.files)} images processed.")


class ProductionThread(QThread):
    progress=Signal(int,str); ok=Signal(object); fail=Signal(str); cancelled=Signal()
    def __init__(self,src,out,opt): super().__init__(); self.src=src; self.out=out; self.opt=opt
    def run(self):
        try:
            job=ProductionJob(self.src,self.out,self.opt,progress=lambda p,m:self.progress.emit(p,m),cancelled=self.isInterruptionRequested)
            self.result=job.run(); self.ok.emit(self.result)
        except Cancelled: self.cancelled.emit()
        except Exception as e: self.fail.emit(traceback.format_exc())

class ProductionRunnerTab(QWidget):
    """One-click V20 production runner with threaded execution, progress and project packaging."""
    def __init__(self):
        super().__init__(); self.thread=None
        self.source=QLineEdit(); self.source.setPlaceholderText("Choose artwork / mockup image…")
        self.out=QLineEdit(); self.out.setPlaceholderText("Choose output folder…")
        self.browse=QPushButton("Browse Image"); self.outbtn=QPushButton("Output Folder")
        self.cut=QCheckBox("AI Cutout (optional)"); self.recon=QCheckBox("Print-area Reconstruction"); self.clean=QCheckBox("Cleanup")
        self.recon.setChecked(True); self.clean.setChecked(True)
        self.mode=QComboBox(); self.mode.addItems(["Spot","CMYK"])
        self.colors=QSpinBox(); self.colors.setRange(2,16); self.colors.setValue(6)
        self.ub=QCheckBox("White Underbase"); self.ub.setChecked(True)
        self.choke=QSpinBox(); self.choke.setRange(0,8); self.choke.setValue(1)
        self.half=QCheckBox("Halftone Film"); self.cell=QSpinBox(); self.cell.setRange(3,40); self.cell.setValue(8)
        self.angle=QSpinBox(); self.angle.setRange(0,179); self.angle.setValue(45)
        self.run=QPushButton("▶ RUN PRODUCTION"); self.cancel=QPushButton("Cancel"); self.cancel.setEnabled(False)
        self.bar=QProgressBar(); self.status=QLabel("Ready — source → cleanup → separation → films → package")
        form=QFormLayout(); form.addRow("Source",self.source); form.addRow("Output",self.out); form.addRow("Separation",self.mode); form.addRow("Spot colors",self.colors)
        form.addRow("Underbase choke",self.choke); form.addRow("Halftone cell",self.cell); form.addRow("Screen angle",self.angle)
        opts=QGroupBox("Production Options"); of=QVBoxLayout(opts)
        for w in (self.cut,self.recon,self.clean,self.ub,self.half): of.addWidget(w)
        row=QHBoxLayout(); row.addWidget(self.browse); row.addWidget(self.outbtn); row.addWidget(self.run); row.addWidget(self.cancel)
        lay=QVBoxLayout(self); lay.addLayout(form); lay.addWidget(opts); lay.addLayout(row); lay.addWidget(self.bar); lay.addWidget(self.status); lay.addStretch()
        self.browse.clicked.connect(self.pick_source); self.outbtn.clicked.connect(self.pick_out); self.run.clicked.connect(self.start); self.cancel.clicked.connect(self.stop)
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: e.ignore()
    def dropEvent(self,e):
        paths=[u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        imgs=[x for x in paths if Path(x).suffix.lower() in {'.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'}]
        for x in imgs: self.add_spec(normalize_job({'name':Path(x).stem,'source':x}, V28_PRESETS[self.preset.currentText()]))
        if imgs: self.status.setText(f'Added {len(imgs)} dropped artwork(s) using {self.preset.currentText()}')
    def add_spec(self, sp):
        sp=normalize_job(sp, V28_PRESETS[self.preset.currentText()]); self.jobs.append(sp); self.list.addItem(f"{sp['name']}  —  {Path(sp['source']).name}  [{self.preset.currentText()}]")
    def import_library_jobs(self,jobs):
        for sp in jobs: self.add_spec(sp)
        self.status.setText(f'Imported {len(jobs)} library artwork(s) into queue')
    def apply_selected_preset(self):
        preset=V28_PRESETS[self.preset.currentText()]
        rows=sorted({i.row() for i in self.list.selectedIndexes()})
        targets=rows if rows else list(range(len(self.jobs)))
        for r in targets:
            self.jobs[r]=apply_preset_to_job(self.jobs[r],preset)
            if r < self.list.count(): self.list.item(r).setText(f"{self.jobs[r]['name']}  —  {Path(self.jobs[r]['source']).name}  [{self.preset.currentText()}]")
        self.status.setText(f'Preset applied to {len(targets)} job(s): {self.preset.currentText()}')
    def save_queue_file(self):
        p,_=QFileDialog.getSaveFileName(self,'Save Production Queue','production_queue_v28.json','JSON (*.json)')
        if p: Path(p).write_text(json.dumps({'version':'V28','jobs':self.jobs,'preset':self.preset.currentText()},indent=2,ensure_ascii=False),encoding='utf-8'); self.status.setText('Queue saved')
    def load_queue_file(self):
        p,_=QFileDialog.getOpenFileName(self,'Load Production Queue','','JSON (*.json)')
        if not p:return
        try:
            d=json.loads(Path(p).read_text(encoding='utf-8')); self.jobs=[normalize_job(x,V28_PRESETS.get(d.get('preset','Dark Garment 6-Color'),V28_PRESETS['Dark Garment 6-Color'])) for x in d.get('jobs',[])]; self.list.clear()
            for x in self.jobs:self.list.addItem(f"{x['name']}  —  {Path(x['source']).name}")
            self.status.setText(f'Loaded {len(self.jobs)} jobs')
        except Exception as e: QMessageBox.critical(self,'Queue Load',str(e))
    def save_template_file(self):
        p,_=QFileDialog.getSaveFileName(self,'Save Production Template','production_template_v28.json','JSON (*.json)')
        if p: Path(p).write_text(json.dumps({'version':'V28','preset':self.preset.currentText(),'settings':V28_PRESETS[self.preset.currentText()]},indent=2),encoding='utf-8'); self.status.setText('Template saved')
    def load_template_file(self):
        p,_=QFileDialog.getOpenFileName(self,'Load Production Template','','JSON (*.json)')
        if not p:return
        try:
            d=json.loads(Path(p).read_text(encoding='utf-8')); name=d.get('preset','Dark Garment 6-Color'); idx=self.preset.findText(name); self.preset.setCurrentIndex(max(0,idx)); self.apply_selected_preset()
        except Exception as e: QMessageBox.critical(self,'Template Load',str(e))
    def pick_source(self):
        p,_=QFileDialog.getOpenFileName(self,"Choose Artwork / Mockup","","Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if p:self.source.setText(p); self.status.setText(Path(p).name)
    def pick_out(self):
        p=QFileDialog.getExistingDirectory(self,"Choose Output Folder")
        if p:self.out.setText(p)
    def start(self):
        src=self.source.text().strip()
        if not src or not Path(src).exists(): QMessageBox.warning(self,"Production","Choose a valid source image."); return
        out=self.out.text().strip() or str(Path(src).parent/'ImageStudio_Production')
        self.out.setText(out)
        opt={'cutout':self.cut.isChecked(),'reconstruct':self.recon.isChecked(),'cleanup':self.clean.isChecked(),
             'mode':self.mode.currentText(),'colors':self.colors.value(),'underbase':self.ub.isChecked(),'choke':self.choke.value(),
             'halftone':self.half.isChecked(),'cell':self.cell.value(),'angle':self.angle.value()}
        self.bar.setValue(0); self.run.setEnabled(False); self.cancel.setEnabled(True); self.status.setText('Starting…')
        self.thread=ProductionThread(src,out,opt); self.thread.progress.connect(self.report); self.thread.ok.connect(self.done); self.thread.fail.connect(self.failed); self.thread.cancelled.connect(self.was_cancelled); self.thread.finished.connect(self.thread.deleteLater); self.thread.start()
    def report(self,p,m): self.bar.setValue(p); self.status.setText(m)
    def stop(self):
        if self.thread and self.thread.isRunning(): self.thread.requestInterruption(); self.status.setText('Cancelling…')
    def reset_controls(self): self.run.setEnabled(True); self.cancel.setEnabled(False)
    def done(self,result):
        self.reset_controls(); zp,manifest=result; self.bar.setValue(100); self.status.setText(f'Complete — {zp}')
        QMessageBox.information(self,'Production Complete',f'Project package created:\n{zp}\n\nFilm channels: {len(manifest.get("filmset",{}).get("channels",[]))}')
    def failed(self,msg):
        self.reset_controls(); self.status.setText('Failed'); QMessageBox.critical(self,'Production Error',msg)
    def was_cancelled(self): self.reset_controls(); self.status.setText('Cancelled')

class PrintSheetTab(QWidget):
    """V21 gang-sheet / print-sheet layout with copies, spacing and registration marks."""
    def __init__(self):
        super().__init__(); self.im=None; self.path=None; self.preview=None
        self.open=QPushButton("Open Artwork"); self.generate=QPushButton("Generate Print Sheet"); self.save=QPushButton("Export Layout Package")
        self.save.setEnabled(False)
        self.preset=QComboBox(); self.preset.addItems(list(DEFAULT_PRESETS.keys()))
        self.w=QDoubleSpinBox(); self.w.setRange(50,1000); self.w.setDecimals(1); self.w.setValue(330.2)
        self.h=QDoubleSpinBox(); self.h.setRange(50,1000); self.h.setDecimals(1); self.h.setValue(482.6)
        self.dpi=QSpinBox(); self.dpi.setRange(72,1200); self.dpi.setValue(300)
        self.copies=QSpinBox(); self.copies.setRange(1,1000); self.copies.setValue(10)
        self.gap=QDoubleSpinBox(); self.gap.setRange(0,50); self.gap.setDecimals(1); self.gap.setValue(5)
        self.margin=QDoubleSpinBox(); self.margin.setRange(0,50); self.margin.setDecimals(1); self.margin.setValue(8)
        self.rotate=QCheckBox("Rotate artwork 90° when packing")
        self.marks=QCheckBox("Registration marks"); self.marks.setChecked(True)
        self.labels=QCheckBox("Copy labels"); self.labels.setChecked(True)
        self.info=QLabel("Load artwork to create a gang/print sheet. Layout is a geometric placement tool; it does not perform ICC/RIP nesting.")
        self.info.setWordWrap(True)
        self.view=DropLabel(); self.view.fileDropped.connect(self.load_path)
        form=QFormLayout(); form.addRow("Preset",self.preset); form.addRow("Sheet width (mm)",self.w); form.addRow("Sheet height (mm)",self.h); form.addRow("DPI",self.dpi); form.addRow("Copies",self.copies); form.addRow("Gap (mm)",self.gap); form.addRow("Margin (mm)",self.margin)
        box=QGroupBox("Print Sheet / Gang Sheet"); bf=QVBoxLayout(box); bf.addLayout(form); bf.addWidget(self.rotate); bf.addWidget(self.marks); bf.addWidget(self.labels)
        row=QHBoxLayout(); row.addWidget(self.open); row.addWidget(self.generate); row.addWidget(self.save); row.addStretch()
        lay=QVBoxLayout(self); lay.addWidget(box); lay.addLayout(row); lay.addWidget(self.info); lay.addWidget(self.view,1)
        self.open.clicked.connect(self.pick); self.generate.clicked.connect(self.make); self.save.clicked.connect(self.export)
        self.preset.currentTextChanged.connect(self.apply_preset)
        self.apply_preset(self.preset.currentText())
    def apply_preset(self,name):
        d=DEFAULT_PRESETS.get(name,{}); 
        if d:
            self.w.setValue(d['sheet_width_mm']); self.h.setValue(d['sheet_height_mm']); self.dpi.setValue(d['dpi']); self.gap.setValue(d['gap_mm']); self.margin.setValue(d['margin_mm'])
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,"Artwork","","Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if p:self.load_path(p)
    def load_path(self,p):
        self.path=p; self.im=load_image(p); self.show(self.im); self.save.setEnabled(False); self.info.setText(f"{Path(p).name} • {self.im.width}×{self.im.height}px")
    def show(self,im): self.view.setPixmap(to_qpixmap(preview_image(im)).scaled(self.view.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
    def resizeEvent(self,e):
        if self.preview is not None:self.show(self.preview)
        elif self.im is not None:self.show(self.im)
        super().resizeEvent(e)
    def make(self):
        if self.im is None:return
        try:
            pages,meta=make_print_sheet(self.im,self.w.value(),self.h.value(),self.dpi.value(),self.copies.value(),self.gap.value(),self.margin.value(),self.rotate.isChecked(),self.marks.isChecked(),self.labels.isChecked())
            self.preview=pages[0][0]; self.show(self.preview); self.save.setEnabled(True)
            self._pages=pages; self._meta=meta
            self.info.setText(f"{meta['pages']} page(s) • {meta['columns']}×{meta['rows']} grid • {meta['placed_total']} copies • {meta['sheet_px'][0]}×{meta['sheet_px'][1]}px @ {meta['dpi']} DPI")
        except Exception as e: QMessageBox.warning(self,"Print Sheet",str(e))
    def export(self):
        if self.im is None:return
        out=QFileDialog.getExistingDirectory(self,"Choose Output Folder")
        if not out:return
        try:
            manifest=save_layout_package(self.im,out,sheet_width_mm=self.w.value(),sheet_height_mm=self.h.value(),dpi=self.dpi.value(),copies=self.copies.value(),gap_mm=self.gap.value(),margin_mm=self.margin.value(),rotate=self.rotate.isChecked(),show_marks=self.marks.isChecked(),labels=self.labels.isChecked(),background='white')
            QMessageBox.information(self,"Layout Exported",f"Print-sheet package created in:\n{out}\n\nPages: {manifest['layout']['pages']}")
        except Exception as e: QMessageBox.critical(self,"Export Error",str(e))


class GangPackTab(QWidget):
    """V22 multi-design gang-sheet packer: alpha-trimmed bounds, per-design width/quantity, packing and waste report."""
    def __init__(self):
        super().__init__(); self.rows=[]; self.last_specs=[]
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["Design","Width mm","Qty","Rotate","Status"])
        self.table.horizontalHeader().setStretchLastSection(True); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.add=QPushButton("+ Add Designs"); self.remove=QPushButton("Remove Selected"); self.clear=QPushButton("Clear")
        self.preset=QComboBox(); self.preset.addItems(list(DEFAULT_PRESETS.keys())); self.preset.setCurrentText('13x19 in 300dpi')
        self.w=QDoubleSpinBox(); self.w.setRange(50,1000); self.w.setDecimals(1); self.h=QDoubleSpinBox(); self.h.setRange(50,1000); self.h.setDecimals(1)
        self.dpi=QSpinBox(); self.dpi.setRange(72,1200); self.dpi.setValue(300)
        self.gap=QDoubleSpinBox(); self.gap.setRange(0,50); self.gap.setDecimals(1); self.gap.setValue(5)
        self.margin=QDoubleSpinBox(); self.margin.setRange(0,50); self.margin.setDecimals(1); self.margin.setValue(8)
        self.labels=QCheckBox("Labels"); self.labels.setChecked(True); self.marks=QCheckBox("Center registration marks")
        self.run=QPushButton("▶ Auto Pack / Preview"); self.export=QPushButton("Export Gang Package"); self.queue=QPushButton("Add Job to Queue")
        self.export.setEnabled(False); self.preview=QLabel("Add two or more designs to create a mixed gang sheet."); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumHeight(420)
        self.report=QLabel("No layout generated."); self.report.setWordWrap(True)
        form=QFormLayout(); form.addRow('Preset',self.preset); form.addRow('Sheet width (mm)',self.w); form.addRow('Sheet height (mm)',self.h); form.addRow('DPI',self.dpi); form.addRow('Gap (mm)',self.gap); form.addRow('Margin (mm)',self.margin)
        top=QHBoxLayout(); top.addWidget(self.add); top.addWidget(self.remove); top.addWidget(self.clear); top.addStretch(); top.addWidget(self.queue)
        opts=QHBoxLayout(); opts.addWidget(self.labels); opts.addWidget(self.marks); opts.addStretch(); opts.addWidget(self.run); opts.addWidget(self.export)
        lay=QVBoxLayout(self); lay.addLayout(form); lay.addLayout(top); lay.addWidget(self.table); lay.addLayout(opts); lay.addWidget(self.report); lay.addWidget(self.preview,1)
        self.add.clicked.connect(self.add_files); self.remove.clicked.connect(self.remove_rows); self.clear.clicked.connect(self.clear_rows); self.run.clicked.connect(self.make); self.export.clicked.connect(self.do_export); self.queue.clicked.connect(self.add_job); self.preset.currentTextChanged.connect(self.apply_preset); self.apply_preset(self.preset.currentText())
    def apply_preset(self,name):
        d=DEFAULT_PRESETS.get(name,{})
        if d:self.w.setValue(d['sheet_width_mm']); self.h.setValue(d['sheet_height_mm']); self.dpi.setValue(d['dpi']); self.gap.setValue(d['gap_mm']); self.margin.setValue(d['margin_mm'])
    def add_files(self):
        files,_=QFileDialog.getOpenFileNames(self,'Add Artwork Designs','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        for p in files:
            r=self.table.rowCount(); self.table.insertRow(r); self.table.setItem(r,0,QTableWidgetItem(p));
            wi=QTableWidgetItem('100'); qi=QTableWidgetItem('1'); ri=QTableWidgetItem('Yes'); st=QTableWidgetItem('Ready')
            self.table.setItem(r,1,wi); self.table.setItem(r,2,qi); self.table.setItem(r,3,ri); self.table.setItem(r,4,st)
    def remove_rows(self):
        for r in sorted({x.row() for x in self.table.selectedItems()},reverse=True): self.table.removeRow(r)
    def clear_rows(self): self.table.setRowCount(0); self.export.setEnabled(False); self.report.setText('No layout generated.')
    def specs(self):
        out=[]
        for r in range(self.table.rowCount()):
            path=self.table.item(r,0).text(); name=Path(path).stem
            try: width=float(self.table.item(r,1).text()); qty=int(self.table.item(r,2).text())
            except: raise ValueError(f'Invalid width/quantity on row {r+1}.')
            rot=self.table.item(r,3).text().strip().lower() not in ('no','0','false')
            if width<=0 or qty<1: raise ValueError(f'Invalid width/quantity for {name}.')
            out.append(ItemSpec(path,name,qty,width,rot))
        if not out: raise ValueError('Add at least one design.')
        return out
    def make(self):
        try:
            specs=self.specs(); pages,meta=__import__('production_v22').pack_designs(specs,self.w.value(),self.h.value(),self.dpi.value(),self.margin.value(),self.gap.value())
            self.last_specs=specs; self.last_pages=pages; self.last_meta=meta
            from production_v22 import render_page, calculate_utilization, mm_to_px
            page=render_page(pages[0][0],pages[0][1],tuple(meta['sheet_px']),meta['dpi'],'white',self.labels.isChecked(),self.marks.isChecked())
            self.preview.setPixmap(to_qpixmap(preview_image(page)).scaled(self.preview.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
            margin=mm_to_px(self.margin.value(),self.dpi.value()); stats=calculate_utilization(pages[0][1],tuple(meta['sheet_px']),margin)
            self.report.setText(f"{meta['designs']} designs • {meta['copies']} copies • {meta['pages']} page(s) • Page 1 utilization {stats['utilization_percent']}% • estimated rectangular waste {stats['waste_percent']}%.\nTransparent margins are trimmed before packing; this is rectangle/bounding-box nesting, not polygon contour nesting.")
            self.export.setEnabled(True)
        except Exception as e: QMessageBox.warning(self,'Gang Pack',str(e))
    def do_export(self):
        try: specs=self.specs()
        except Exception as e: QMessageBox.warning(self,'Gang Pack',str(e)); return
        out=QFileDialog.getExistingDirectory(self,'Choose Output Folder')
        if not out:return
        try:
            m=export_gang_package(specs,out,self.w.value(),self.h.value(),self.dpi.value(),self.margin.value(),self.gap.value(),'white',self.labels.isChecked(),self.marks.isChecked())
            QMessageBox.information(self,'Gang Package',f"Exported {m['layout']['pages']} page(s) to:\n{out}\n\nManifest: gang_manifest.json")
        except Exception as e: QMessageBox.critical(self,'Export Error',str(e))
    def add_job(self):
        try: specs=self.specs()
        except Exception as e: QMessageBox.warning(self,'Queue',str(e)); return
        q=JobQueue(); q.add(f"Gang Job {datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",specs,{'sheet_width_mm':self.w.value(),'sheet_height_mm':self.h.value(),'dpi':self.dpi.value(),'margin_mm':self.margin.value(),'gap_mm':self.gap.value()})
        out,_=QFileDialog.getSaveFileName(self,'Save Queue JSON','gang_jobs.json','JSON (*.json)')
        if out:
            q.to_json(out); QMessageBox.information(self,'Queue Saved',f'Job queue saved:\n{out}')


class ProductionValidationTab(QWidget):
    """V23 preflight, presets, duplicate detection and repeatable job packaging."""
    def __init__(self):
        super().__init__(); self.paths=[]; self.records=[]; self.issues=[]; self.last_report=None
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(["Artwork","Pixels","Embedded DPI","Size @ target","Alpha","Status"])
        self.table.horizontalHeader().setStretchLastSection(True); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.add=QPushButton("+ Add Artwork"); self.remove=QPushButton("Remove Selected"); self.clear=QPushButton("Clear")
        self.target=QSpinBox(); self.target.setRange(72,1200); self.target.setValue(300)
        self.min_dpi=QSpinBox(); self.min_dpi.setRange(72,1200); self.min_dpi.setValue(150)
        self.sheet_w=QDoubleSpinBox(); self.sheet_w.setRange(50,2000); self.sheet_w.setValue(330.2); self.sheet_w.setDecimals(1)
        self.sheet_h=QDoubleSpinBox(); self.sheet_h.setRange(50,2000); self.sheet_h.setValue(482.6); self.sheet_h.setDecimals(1)
        self.margin=QDoubleSpinBox(); self.margin.setRange(0,100); self.margin.setValue(8); self.margin.setDecimals(1)
        self.gap=QDoubleSpinBox(); self.gap.setRange(0,100); self.gap.setValue(5); self.gap.setDecimals(1)
        self.validate=QPushButton("✓ Preflight Validate"); self.preset_save=QPushButton("Save Preset"); self.preset_load=QPushButton("Load Preset")
        self.report_btn=QPushButton("Export Report"); self.package_btn=QPushButton("Package Job ZIP")
        self.status=QLabel("Add artwork and run preflight validation."); self.status.setWordWrap(True)
        form=QFormLayout(); form.addRow('Target DPI',self.target); form.addRow('Minimum embedded DPI',self.min_dpi); form.addRow('Sheet width (mm)',self.sheet_w); form.addRow('Sheet height (mm)',self.sheet_h); form.addRow('Margin (mm)',self.margin); form.addRow('Gap (mm)',self.gap)
        row=QHBoxLayout(); row.addWidget(self.add); row.addWidget(self.remove); row.addWidget(self.clear); row.addStretch(); row.addWidget(self.validate)
        row2=QHBoxLayout(); row2.addWidget(self.preset_save); row2.addWidget(self.preset_load); row2.addWidget(self.report_btn); row2.addWidget(self.package_btn); row2.addStretch()
        lay=QVBoxLayout(self); lay.addLayout(form); lay.addLayout(row); lay.addWidget(self.table); lay.addWidget(self.status); lay.addLayout(row2)
        self.add.clicked.connect(self.add_files); self.remove.clicked.connect(self.remove_rows); self.clear.clicked.connect(self.clear_all); self.validate.clicked.connect(self.run_validate); self.preset_save.clicked.connect(self.save_p); self.preset_load.clicked.connect(self.load_p); self.report_btn.clicked.connect(self.export_r); self.package_btn.clicked.connect(self.package)
    def add_files(self):
        files,_=QFileDialog.getOpenFileNames(self,'Add Artwork','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        for p in files:
            if p not in self.paths:self.paths.append(p)
        self.refresh()
    def refresh(self):
        self.table.setRowCount(0)
        for p in self.paths:
            r=self.table.rowCount(); self.table.insertRow(r); self.table.setItem(r,0,QTableWidgetItem(p));
            for c in range(1,6): self.table.setItem(r,c,QTableWidgetItem('—'))
    def remove_rows(self):
        selected=sorted({x.row() for x in self.table.selectedItems()},reverse=True)
        for r in selected:
            if 0<=r<len(self.paths): self.paths.pop(r)
        self.refresh()
    def clear_all(self): self.paths=[]; self.records=[]; self.issues=[]; self.last_report=None; self.refresh(); self.status.setText('Cleared.')
    def settings(self): return {'target_dpi':self.target.value(),'min_dpi':self.min_dpi.value(),'sheet_width_mm':self.sheet_w.value(),'sheet_height_mm':self.sheet_h.value(),'margin_mm':self.margin.value(),'gap_mm':self.gap.value()}
    def run_validate(self):
        if not self.paths: QMessageBox.warning(self,'Preflight','Add at least one artwork.'); return
        try:
            self.records,self.issues=validate_artworks(self.paths,self.target.value(),self.min_dpi.value())
            # Quantity is one here; the gang tab performs per-row quantity validation.
            specs=[ItemSpec(r.path,r.name,1,100,True) for r in self.records]
            self.issues.extend(validate_job(specs,self.sheet_w.value(),self.sheet_h.value(),self.target.value(),self.margin.value(),self.gap.value()))
            bypath={r.path:r for r in self.records}
            for row,p in enumerate(self.paths):
                r=bypath.get(p); vals=['—']*5
                if r:
                    vals=[f'{r.width_px}×{r.height_px}',f'{r.dpi_x:g}×{r.dpi_y:g}',f'{r.width_mm_at_dpi:.1f}×{r.height_mm_at_dpi:.1f} mm','Yes' if r.alpha else 'No','OK']
                    if any(i.path==p and i.severity=='ERROR' for i in self.issues): vals[-1]='ERROR'
                    elif any(i.path==p and i.severity=='WARNING' for i in self.issues): vals[-1]='WARN'
                for c,v in enumerate(vals,1): self.table.setItem(row,c,QTableWidgetItem(v))
            errors=sum(i.severity=='ERROR' for i in self.issues); warns=sum(i.severity=='WARNING' for i in self.issues)
            dups=sum(1 for r in self.records if r.duplicate_of)
            self.status.setText(f'Preflight: {len(self.records)} file(s) • {errors} error(s) • {warns} warning(s) • {dups} duplicate(s). Embedded DPI is metadata; size estimates are mathematical.')
            self.last_report=make_job_report(self.records,self.issues,{'settings':self.settings()})
        except Exception as e: QMessageBox.critical(self,'Preflight Error',str(e))
    def save_p(self):
        path,_=QFileDialog.getSaveFileName(self,'Save Production Preset','production_preset.json','JSON (*.json)')
        if path:
            name=Path(path).stem
            try: save_preset(path,name,self.settings()); QMessageBox.information(self,'Preset',f'Saved:\n{path}')
            except Exception as e: QMessageBox.critical(self,'Preset Error',str(e))
    def load_p(self):
        path,_=QFileDialog.getOpenFileName(self,'Load Production Preset','','JSON (*.json)')
        if not path:return
        try:
            d=load_preset(path).get('settings',{})
            for widget,key in [(self.target,'target_dpi'),(self.min_dpi,'min_dpi'),(self.sheet_w,'sheet_width_mm'),(self.sheet_h,'sheet_height_mm'),(self.margin,'margin_mm'),(self.gap,'gap_mm')]:
                if key in d: widget.setValue(d[key])
            self.status.setText(f'Loaded preset: {Path(path).name}')
        except Exception as e: QMessageBox.critical(self,'Preset Error',str(e))
    def export_r(self):
        if not self.last_report:self.run_validate()
        if not self.last_report:return
        path,_=QFileDialog.getSaveFileName(self,'Export Production Report','production_report.json','JSON (*.json)')
        if path:
            export_report(path,self.last_report); QMessageBox.information(self,'Report',f'Report saved:\n{path}')
    def package(self):
        if not self.last_report:self.run_validate()
        if not self.last_report:return
        if any(i.severity=='ERROR' for i in self.issues):
            QMessageBox.warning(self,'Package','Resolve preflight errors before packaging the job.'); return
        path,_=QFileDialog.getSaveFileName(self,'Package Job ZIP','ImageStudio_Production_Job.zip','ZIP (*.zip)')
        if path:
            try:
                preset={'version':'V23','settings':self.settings()}
                package_job(path,self.paths,self.last_report,preset); QMessageBox.information(self,'Job Package',f'Package created:\n{path}')
            except Exception as e: QMessageBox.critical(self,'Package Error',str(e))


class BatchProductionThread(QThread):
    progress=Signal(int,str); ok=Signal(object); fail=Signal(str); cancelled=Signal()
    def __init__(self,jobs,root):
        super().__init__(); self.jobs=jobs; self.root=root; self._paused=False
    def set_paused(self,v): self._paused=v
    def run(self):
        try:
            runner=BatchProductionRunner(self.jobs,self.root,progress=lambda p,m:self.progress.emit(p,m),
                cancelled=self.isInterruptionRequested,paused=lambda:self._paused)
            self.result=runner.run()
            if self.isInterruptionRequested(): self.cancelled.emit()
            else: self.ok.emit(self.result)
        except Cancelled: self.cancelled.emit()
        except Exception: self.fail.emit(traceback.format_exc())

class BatchProductionTab(QWidget):
    """V24 multi-job production queue: add jobs, reorder, run, pause/resume, cancel and history."""
    def __init__(self):
        super().__init__(); self.jobs=[]; self.thread=None
        self.list=QListWidget(); self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.name=QLineEdit(); self.name.setPlaceholderText('Job name')
        self.source=QLineEdit(); self.source.setPlaceholderText('Source artwork / mockup')
        self.output=QLineEdit(); self.output.setPlaceholderText('Queue output root')
        self.browse=QPushButton('Browse Source'); self.pickout=QPushButton('Output Root')
        self.mode=QComboBox(); self.mode.addItems(['Spot','CMYK'])
        self.colors=QSpinBox(); self.colors.setRange(2,16); self.colors.setValue(6)
        self.clean=QCheckBox('Cleanup'); self.clean.setChecked(True)
        self.recon=QCheckBox('Reconstruct'); self.recon.setChecked(True)
        self.cut=QCheckBox('AI Cutout')
        self.ub=QCheckBox('Underbase'); self.ub.setChecked(True)
        self.half=QCheckBox('Halftone'); self.half.setChecked(True)
        self.choke=QSpinBox(); self.choke.setRange(0,8); self.choke.setValue(1)
        self.cell=QSpinBox(); self.cell.setRange(3,40); self.cell.setValue(8)
        self.angle=QSpinBox(); self.angle.setRange(0,179); self.angle.setValue(45)
        self.add=QPushButton('＋ Add Job'); self.remove=QPushButton('Remove'); self.up=QPushButton('↑'); self.down=QPushButton('↓'); self.clear=QPushButton('Clear')
        self.run=QPushButton('▶ RUN QUEUE'); self.pause=QPushButton('Pause'); self.cancel=QPushButton('Cancel'); self.pause.setEnabled(False); self.cancel.setEnabled(False)
        self.preset=QComboBox(); self.preset.addItems(list(V28_PRESETS.keys())); self.apply_preset=QPushButton('Apply Preset'); self.save_queue_btn=QPushButton('Save Queue'); self.load_queue_btn=QPushButton('Load Queue'); self.save_template_btn=QPushButton('Save Template'); self.load_template_btn=QPushButton('Load Template')
        self.progress=QProgressBar(); self.status=QLabel('Queue ready'); self.history=QTableWidget(0,4); self.history.setHorizontalHeaderLabels(['Job','Status','Output','Finished']); self.history.horizontalHeader().setStretchLastSection(True)
        form=QFormLayout(); form.addRow('Name',self.name); form.addRow('Source',self.source); form.addRow('Separation',self.mode); form.addRow('Spot colors',self.colors); form.addRow('Choke',self.choke); form.addRow('Halftone cell',self.cell); form.addRow('Screen angle',self.angle)
        opts=QHBoxLayout()
        for w in (self.clean,self.recon,self.cut,self.ub,self.half): opts.addWidget(w)
        source_row=QHBoxLayout(); source_row.addWidget(self.browse); source_row.addWidget(self.pickout); source_row.addWidget(self.output)
        edit=QHBoxLayout(); [edit.addWidget(w) for w in (self.add,self.remove,self.up,self.down,self.clear,self.apply_preset)]; edit.addWidget(QLabel('Preset:')); edit.addWidget(self.preset); edit.addWidget(self.save_queue_btn); edit.addWidget(self.load_queue_btn); edit.addWidget(self.save_template_btn); edit.addWidget(self.load_template_btn)
        controls=QHBoxLayout(); [controls.addWidget(w) for w in (self.run,self.pause,self.cancel)]
        left=QVBoxLayout(); left.addWidget(QLabel('Queued production jobs')); left.addWidget(self.list,1); left.addLayout(edit)
        right=QVBoxLayout(); right.addLayout(form); right.addLayout(opts); right.addLayout(source_row); right.addWidget(QLabel('Queue output root is required before running.')); right.addLayout(controls); right.addWidget(self.progress); right.addWidget(self.status); right.addWidget(QLabel('Current-session job history')); right.addWidget(self.history,1)
        main=QHBoxLayout(self); main.addLayout(left,2); main.addLayout(right,3)
        self.browse.clicked.connect(self.pick_source); self.pickout.clicked.connect(self.pick_output); self.add.clicked.connect(self.add_job); self.remove.clicked.connect(self.remove_job); self.up.clicked.connect(lambda:self.move(-1)); self.down.clicked.connect(lambda:self.move(1)); self.clear.clicked.connect(self.clear_jobs); self.run.clicked.connect(self.start); self.pause.clicked.connect(self.toggle_pause); self.cancel.clicked.connect(self.stop); self.apply_preset.clicked.connect(self.apply_selected_preset); self.save_queue_btn.clicked.connect(self.save_queue_file); self.load_queue_btn.clicked.connect(self.load_queue_file); self.save_template_btn.clicked.connect(self.save_template_file); self.load_template_btn.clicked.connect(self.load_template_file); self.setAcceptDrops(True)
    def pick_source(self):
        p,_=QFileDialog.getOpenFileName(self,'Choose Source','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if p:
            self.source.setText(p)
            if not self.name.text().strip(): self.name.setText(Path(p).stem)
    def pick_output(self):
        p=QFileDialog.getExistingDirectory(self,'Choose Queue Output Root')
        if p:self.output.setText(p)
    def spec(self):
        return {'name':self.name.text().strip() or Path(self.source.text()).stem or f'Job_{len(self.jobs)+1:03d}',
                'source':self.source.text().strip(), 'options':{'mode':self.mode.currentText(),'colors':self.colors.value(),'cleanup':self.clean.isChecked(),'reconstruct':self.recon.isChecked(),'cutout':self.cut.isChecked(),'underbase':self.ub.isChecked(),'choke':self.choke.value(),'halftone':self.half.isChecked(),'cell':self.cell.value(),'angle':self.angle.value()}}
    def add_job(self):
        if not self.source.text().strip() or not Path(self.source.text().strip()).exists(): QMessageBox.warning(self,'Queue','Choose a valid source image.'); return
        sp=self.spec(); self.add_spec(sp); self.name.clear(); self.source.clear(); self.status.setText(f'{len(self.jobs)} job(s) queued')
    def remove_job(self):
        r=self.list.currentRow()
        if r>=0:self.list.takeItem(r); self.jobs.pop(r)
    def move(self,d):
        r=self.list.currentRow(); n=r+d
        if 0<=r<len(self.jobs) and 0<=n<len(self.jobs):
            self.jobs[r],self.jobs[n]=self.jobs[n],self.jobs[r]; item=self.list.takeItem(r); self.list.insertItem(n,item); self.list.setCurrentRow(n)
    def clear_jobs(self): self.jobs.clear(); self.list.clear(); self.status.setText('Queue cleared')
    def start(self):
        if not self.jobs: QMessageBox.warning(self,'Queue','Add at least one job.'); return
        root=self.output.text().strip()
        if not root: QMessageBox.warning(self,'Queue','Choose an output root.'); return
        self.thread=BatchProductionThread(self.jobs,root); self.thread.progress.connect(self.report); self.thread.ok.connect(self.done); self.thread.fail.connect(self.failed); self.thread.cancelled.connect(self.was_cancelled); self.thread.finished.connect(self.thread.deleteLater)
        self.run.setEnabled(False); self.add.setEnabled(False); self.pause.setEnabled(True); self.cancel.setEnabled(True); self.progress.setValue(0); self.status.setText('Queue starting…'); self.thread.start()
    def report(self,p,m): self.progress.setValue(p); self.status.setText(m)
    def toggle_pause(self):
        if not self.thread:return
        paused=not self.thread._paused; self.thread.set_paused(paused); self.pause.setText('Resume' if paused else 'Pause'); self.status.setText('Paused' if paused else 'Resuming…')
    def stop(self):
        if self.thread and self.thread.isRunning(): self.thread.requestInterruption(); self.status.setText('Cancelling queue…')
    def reset(self): self.run.setEnabled(True); self.add.setEnabled(True); self.pause.setEnabled(False); self.pause.setText('Pause'); self.cancel.setEnabled(False)
    def done(self,results):
        self.reset(); self.progress.setValue(100); self.status.setText(f'Queue finished — {sum(r["status"]=="complete" for r in results)}/{len(results)} complete'); self.refresh_history(results)
        QMessageBox.information(self,'Queue Complete',f'Processed {len(results)} job(s).\nCompleted: {sum(r["status"]=="complete" for r in results)}')
    def failed(self,msg): self.reset(); self.status.setText('Queue failed'); QMessageBox.critical(self,'Queue Error',msg)
    def was_cancelled(self): self.reset(); self.status.setText('Queue cancelled'); QMessageBox.information(self,'Queue','Queue cancellation requested.')
    def refresh_history(self,results):
        self.history.setRowCount(0)
        for r in results:
            row=self.history.rowCount(); self.history.insertRow(row)
            vals=[r.get('name',''),r.get('status',''),r.get('output',''),r.get('finished_at','')]
            for c,v in enumerate(vals): self.history.setItem(row,c,QTableWidgetItem(str(v)))


class ProductionDashboardTab(QWidget):
    """V25 dashboard: queue templates, preflight gate, retry failed jobs, logs and statistics."""
    def __init__(self):
        super().__init__(); self.jobs=[]; self.thread=None; self.last_results=[]
        self.list=QListWidget(); self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.name=QLineEdit(); self.source=QLineEdit(); self.output=QLineEdit()
        self.mode=QComboBox(); self.mode.addItems(['Spot','CMYK'])
        self.colors=QSpinBox(); self.colors.setRange(2,16); self.colors.setValue(6)
        self.clean=QCheckBox('Cleanup'); self.clean.setChecked(True); self.recon=QCheckBox('Reconstruct'); self.recon.setChecked(True)
        self.cut=QCheckBox('AI Cutout'); self.ub=QCheckBox('Underbase'); self.ub.setChecked(True); self.half=QCheckBox('Halftone'); self.half.setChecked(True)
        self.choke=QSpinBox(); self.choke.setRange(0,8); self.choke.setValue(1); self.cell=QSpinBox(); self.cell.setRange(3,40); self.cell.setValue(8); self.angle=QSpinBox(); self.angle.setRange(0,179); self.angle.setValue(45)
        self.target=QSpinBox(); self.target.setRange(72,1200); self.target.setValue(300); self.min_dpi=QSpinBox(); self.min_dpi.setRange(72,1200); self.min_dpi.setValue(150)
        self.add=QPushButton('＋ Add Job'); self.remove=QPushButton('Remove'); self.clear=QPushButton('Clear'); self.run=QPushButton('▶ RUN'); self.retry=QPushButton('↻ Retry Failed'); self.pause=QPushButton('Pause'); self.cancel=QPushButton('Cancel')
        self.loadq=QPushButton('Load Queue'); self.saveq=QPushButton('Save Queue'); self.savet=QPushButton('Save Template'); self.loadt=QPushButton('Load Template'); self.logbtn=QPushButton('Open Last Log')
        self.pause.setEnabled(False); self.cancel.setEnabled(False)
        self.progress=QProgressBar(); self.status=QLabel('V25 dashboard ready'); self.stats=QLabel('Jobs: 0 • Complete: 0 • Errors: 0 • Warnings: 0 • Output: 0 MB'); self.stats.setWordWrap(True)
        self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(['Job','Status','Elapsed','Files','Output MB','Preflight','Message']); self.table.horizontalHeader().setStretchLastSection(True)
        form=QFormLayout(); form.addRow('Job name',self.name); form.addRow('Source',self.source); form.addRow('Separation',self.mode); form.addRow('Spot colors',self.colors); form.addRow('Choke',self.choke); form.addRow('Halftone cell',self.cell); form.addRow('Screen angle',self.angle); form.addRow('Target DPI',self.target); form.addRow('Min embedded DPI',self.min_dpi)
        opts=QHBoxLayout(); [opts.addWidget(w) for w in (self.clean,self.recon,self.cut,self.ub,self.half)]
        top=QHBoxLayout(); top.addWidget(self.add); top.addWidget(self.remove); top.addWidget(self.clear); top.addStretch(); top.addWidget(self.loadq); top.addWidget(self.saveq); top.addWidget(self.savet); top.addWidget(self.loadt)
        runrow=QHBoxLayout(); [runrow.addWidget(w) for w in (self.run,self.retry,self.pause,self.cancel,self.logbtn)]; runrow.addStretch()
        source=QHBoxLayout(); b=QPushButton('Browse Source'); o=QPushButton('Output Root'); source.addWidget(b); source.addWidget(o); source.addWidget(self.output)
        left=QVBoxLayout(); left.addWidget(QLabel('Production jobs')); left.addWidget(self.list,1); left.addLayout(top)
        right=QVBoxLayout(); right.addLayout(form); right.addLayout(opts); right.addLayout(source); right.addLayout(runrow); right.addWidget(self.progress); right.addWidget(self.status); right.addWidget(self.stats); right.addWidget(self.table,1)
        main=QHBoxLayout(self); main.addLayout(left,2); main.addLayout(right,3)
        b.clicked.connect(self.pick_source); o.clicked.connect(self.pick_output); self.add.clicked.connect(self.add_job); self.remove.clicked.connect(self.remove_job); self.clear.clicked.connect(self.clear_jobs)
        self.run.clicked.connect(self.start); self.retry.clicked.connect(self.retry_failed); self.pause.clicked.connect(self.toggle_pause); self.cancel.clicked.connect(self.stop)
        self.loadq.clicked.connect(self.load_queue); self.saveq.clicked.connect(self.save_queue); self.savet.clicked.connect(self.save_template); self.loadt.clicked.connect(self.load_template); self.logbtn.clicked.connect(self.open_log)
    def pick_source(self):
        p,_=QFileDialog.getOpenFileName(self,'Choose Source','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if p: self.source.setText(p); self.name.setText(self.name.text().strip() or Path(p).stem)
    def pick_output(self):
        p=QFileDialog.getExistingDirectory(self,'Choose Output Root');
        if p:self.output.setText(p)
    def spec(self):
        return {'name':self.name.text().strip() or Path(self.source.text()).stem or f'Job_{len(self.jobs)+1:03d}','source':self.source.text().strip(),
                'options':{'mode':self.mode.currentText(),'colors':self.colors.value(),'cleanup':self.clean.isChecked(),'reconstruct':self.recon.isChecked(),'cutout':self.cut.isChecked(),'underbase':self.ub.isChecked(),'choke':self.choke.value(),'halftone':self.half.isChecked(),'cell':self.cell.value(),'angle':self.angle.value()}}
    def add_job(self):
        if not self.source.text().strip() or not Path(self.source.text().strip()).exists(): QMessageBox.warning(self,'Job','Choose a valid source image.'); return
        sp=self.spec(); self.jobs.append(sp); self.list.addItem(f"{sp['name']} — {Path(sp['source']).name}"); self.name.clear(); self.source.clear(); self.update_stats()
    def remove_job(self):
        rows=sorted({i.row() for i in self.list.selectedIndexes()},reverse=True)
        for r in rows:
            if 0<=r<len(self.jobs): self.jobs.pop(r); self.list.takeItem(r)
        self.update_stats()
    def clear_jobs(self): self.jobs=[]; self.list.clear(); self.last_results=[]; self.table.setRowCount(0); self.update_stats()
    def settings(self): return {'mode':self.mode.currentText(),'colors':self.colors.value(),'cleanup':self.clean.isChecked(),'reconstruct':self.recon.isChecked(),'cutout':self.cut.isChecked(),'underbase':self.ub.isChecked(),'choke':self.choke.value(),'halftone':self.half.isChecked(),'cell':self.cell.value(),'angle':self.angle.value(),'target_dpi':self.target.value(),'min_dpi':self.min_dpi.value()}
    def apply_settings(self,d):
        for w,k in [(self.colors,'colors'),(self.choke,'choke'),(self.cell,'cell'),(self.angle,'angle'),(self.target,'target_dpi'),(self.min_dpi,'min_dpi')]:
            if k in d: w.setValue(d[k])
        if 'mode' in d:self.mode.setCurrentText(d['mode'])
        for w,k in [(self.clean,'cleanup'),(self.recon,'reconstruct'),(self.cut,'cutout'),(self.ub,'underbase'),(self.half,'halftone')]:
            if k in d:w.setChecked(bool(d[k]))
    def save_queue(self):
        if not self.jobs: QMessageBox.warning(self,'Queue','No jobs to save.'); return
        p,_=QFileDialog.getSaveFileName(self,'Save Queue','production_queue.json','JSON (*.json)');
        if p: save_queue(p,self.jobs,{'output_root':self.output.text(),'settings':self.settings()}); self.status.setText(f'Saved queue: {p}')
    def load_queue(self):
        p,_=QFileDialog.getOpenFileName(self,'Load Queue','','JSON (*.json)');
        if not p:return
        try:
            self.jobs=load_queue(p); self.list.clear()
            for sp in self.jobs:self.list.addItem(f"{sp.get('name','Job')} — {Path(sp.get('source','')).name}")
            self.update_stats(); self.status.setText(f'Loaded {len(self.jobs)} job(s)')
        except Exception as e: QMessageBox.critical(self,'Load Queue',str(e))
    def save_template(self):
        p,_=QFileDialog.getSaveFileName(self,'Save Template','production_template.json','JSON (*.json)');
        if p: save_template(p,self.settings()); self.status.setText(f'Saved template: {p}')
    def load_template(self):
        p,_=QFileDialog.getOpenFileName(self,'Load Template','','JSON (*.json)');
        if p:
            try:self.apply_settings(load_template(p)); self.status.setText('Template loaded')
            except Exception as e:QMessageBox.critical(self,'Template',str(e))
    def retry_failed(self):
        failed=[r for r in self.last_results if r.get('status') in ('error','preflight_error')]
        if not failed: QMessageBox.information(self,'Retry','No failed jobs in the last run.'); return
        bysrc={str(j.get('source')):j for j in self.jobs}; self.jobs=[bysrc[r['source']] for r in failed if r['source'] in bysrc]
        self.list.clear(); [self.list.addItem(f"{j['name']} — {Path(j['source']).name}") for j in self.jobs]; self.status.setText(f'{len(self.jobs)} failed job(s) moved to retry queue')
    def start(self):
        if not self.jobs: QMessageBox.warning(self,'Run','Add at least one job.'); return
        root=self.output.text().strip()
        if not root: QMessageBox.warning(self,'Run','Choose an output root.'); return
        self.thread=ProductionDashboardThread(self.jobs,root,self.target.value(),self.min_dpi.value()); self.thread.progress.connect(self.report); self.thread.ok.connect(self.done); self.thread.fail.connect(self.failed); self.thread.cancelled.connect(self.was_cancelled)
        for w in (self.run,self.retry,self.add,self.remove,self.clear,self.loadq,self.saveq,self.savet,self.loadt): w.setEnabled(False)
        self.pause.setEnabled(True); self.cancel.setEnabled(True); self.progress.setValue(0); self.thread.start()
    def report(self,p,m): self.progress.setValue(p); self.status.setText(m)
    def toggle_pause(self):
        if self.thread and self.thread.isRunning(): self.thread.paused=not self.thread.paused; self.pause.setText('Resume' if self.thread.paused else 'Pause')
    def stop(self):
        if self.thread and self.thread.isRunning(): self.thread.requestInterruption(); self.status.setText('Cancelling…')
    def reset(self):
        for w in (self.run,self.retry,self.add,self.remove,self.clear,self.loadq,self.saveq,self.savet,self.loadt): w.setEnabled(True)
        self.pause.setEnabled(False); self.cancel.setEnabled(False); self.pause.setText('Pause')
    def done(self,results,log): self.reset(); self.last_results=results; self.refresh(results); self.status.setText(f'Finished • log: {log}'); self.progress.setValue(100); self.update_stats()
    def failed(self,msg): self.reset(); QMessageBox.critical(self,'Queue Error',msg)
    def was_cancelled(self,results,log): self.reset(); self.last_results=results; self.refresh(results); self.status.setText(f'Cancelled • log: {log}'); self.update_stats()
    def refresh(self,results):
        self.table.setRowCount(0)
        for r in results:
            row=self.table.rowCount(); self.table.insertRow(row); pf=r.get('preflight',{}); st=r.get('stats',{})
            vals=[r.get('name',''),r.get('status',''),r.get('elapsed_s',''),st.get('files',''),st.get('mb',''),f"{pf.get('errors',0)}E/{pf.get('warnings',0)}W",r.get('error','')]
            for c,v in enumerate(vals):self.table.setItem(row,c,QTableWidgetItem(str(v)))
    def update_stats(self):
        complete=sum(r.get('status')=='complete' for r in self.last_results); errors=sum(r.get('status') in ('error','preflight_error') for r in self.last_results); warns=sum(r.get('preflight',{}).get('warnings',0) for r in self.last_results); mb=round(sum(r.get('stats',{}).get('mb',0) for r in self.last_results),2)
        self.stats.setText(f'Jobs: {len(self.jobs)} • Complete: {complete} • Errors: {errors} • Warnings: {warns} • Output: {mb} MB')
    def open_log(self):
        logs=sorted(Path(self.output.text()).glob('queue_*.json')) if self.output.text() and Path(self.output.text()).exists() else []
        if logs: os.startfile(str(logs[-1])) if sys.platform=='win32' else QMessageBox.information(self,'Log',str(logs[-1]))
        else: QMessageBox.information(self,'Log','No queue log found yet.')

class ProductionDashboardThread(QThread):
    progress=Signal(int,str); ok=Signal(object,str); fail=Signal(str); cancelled=Signal(object,str)
    def __init__(self,jobs,root,target,min_dpi): super().__init__(); self.jobs=jobs; self.root=root; self.target=target; self.min_dpi=min_dpi; self.paused=False
    def run(self):
        try:
            mgr=ProductionQueueManager(self.jobs,self.root,progress=lambda p,m:self.progress.emit(p,m),cancelled=self.isInterruptionRequested,paused=lambda:self.paused,target_dpi=self.target,min_dpi=self.min_dpi,preflight=True)
            res,log=mgr.run()
            if self.isInterruptionRequested(): self.cancelled.emit(res,log)
            else:self.ok.emit(res,log)
        except Cancelled:
            self.cancelled.emit(getattr(locals().get('mgr',None),'logs',[]),getattr(locals().get('mgr',None),'log_path',''))
        except Exception: self.fail.emit(traceback.format_exc())



class ArtworkLibraryTab(QWidget):
    queue_handoff=Signal(object)
    """V28 visual library: tags, notes, print status, contact sheets and queue handoff."""
    def __init__(self):
        super().__init__(); self.items=[]; self.favorites=set(); self.library_path=''
        self.search=QLineEdit(); self.search.setPlaceholderText('Search name, folder, tags, notes, status, format…')
        self.only_fav=QCheckBox('Favorites only'); self.only_dup=QCheckBox('Duplicates only')
        self.recursive=QCheckBox('Recursive'); self.recursive.setChecked(True)
        self.add_folder=QPushButton('＋ Add Folder'); self.add_files=QPushButton('＋ Add Files'); self.remove=QPushButton('Remove Selected'); self.clear=QPushButton('Clear')
        self.scan=QPushButton('↻ Rescan'); self.save=QPushButton('Save Library'); self.load=QPushButton('Load Library'); self.report=QPushButton('Export Report')
        self.favorite=QPushButton('★ Favorite'); self.edit=QPushButton('✎ Tags / Notes'); self.status_btn=QPushButton('Print Status')
        self.contact=QPushButton('🖼 Contact Sheet'); self.queue=QPushButton('🚀 Send Selected to Queue'); self.open_btn=QPushButton('Open File')
        self.table=QTableWidget(0,10); self.table.setHorizontalHeaderLabels(['','Artwork','Dimensions','DPI','Mode','Alpha','Size','Tags','Print Status','Notes'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setIconSize(QSize(72,72)); self.table.setColumnWidth(0,82); self.table.setColumnWidth(1,210); self.table.setColumnWidth(7,180); self.table.setColumnWidth(8,120); self.table.horizontalHeader().setStretchLastSection(True); self.table.verticalHeader().setDefaultSectionSize(82)
        self.stats=QLabel('V27 Library: 0 assets'); self.status=QLabel('V27 Smart Artwork Library ready')
        filters=QHBoxLayout(); [filters.addWidget(w) for w in (self.search,self.only_fav,self.only_dup,self.recursive)]
        row1=QHBoxLayout(); [row1.addWidget(w) for w in (self.add_folder,self.add_files,self.remove,self.clear,self.scan)]; row1.addStretch(); [row1.addWidget(w) for w in (self.save,self.load,self.report)]
        row2=QHBoxLayout(); [row2.addWidget(w) for w in (self.favorite,self.edit,self.status_btn,self.contact,self.queue,self.open_btn)]; row2.addStretch()
        lay=QVBoxLayout(self); lay.addLayout(filters); lay.addLayout(row1); lay.addLayout(row2); lay.addWidget(self.table,1); lay.addWidget(self.stats); lay.addWidget(self.status)
        self.search.textChanged.connect(self.refresh); self.only_fav.toggled.connect(self.refresh); self.only_dup.toggled.connect(self.refresh)
        self.add_folder.clicked.connect(self.add_folder_clicked); self.add_files.clicked.connect(self.add_files_clicked); self.remove.clicked.connect(self.remove_selected); self.clear.clicked.connect(self.clear_all); self.scan.clicked.connect(self.rescan)
        self.save.clicked.connect(self.save_lib); self.load.clicked.connect(self.load_lib); self.report.clicked.connect(self.export_report); self.favorite.clicked.connect(self.toggle_favorite); self.edit.clicked.connect(self.edit_metadata); self.status_btn.clicked.connect(self.change_status); self.contact.clicked.connect(self.export_contact_sheet); self.queue.clicked.connect(self.send_to_queue); self.open_btn.clicked.connect(self.open_selected)
    def normalize(self): self.items=[enrich_item(x) for x in self.items]
    def add_folder_clicked(self):
        p=QFileDialog.getExistingDirectory(self,'Add Artwork Folder')
        if p: self.items.extend(scan_paths([p],self.recursive.isChecked())); self.normalize(); self.dedupe(); self.refresh()
    def add_files_clicked(self):
        ps,_=QFileDialog.getOpenFileNames(self,'Add Artwork Files','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if ps: self.items.extend(scan_paths(ps)); self.normalize(); self.dedupe(); self.refresh()
    def dedupe(self):
        seen=set(); out=[]
        for x in self.items:
            if x['path'] not in seen: seen.add(x['path']); out.append(enrich_item(x))
        self.items=out
    def clear_all(self): self.items=[]; self.favorites=set(); self.refresh()
    def remove_selected(self):
        shown=self.filtered(); rows=sorted({i.row() for i in self.table.selectedIndexes()},reverse=True); remove={shown[r]['path'] for r in rows if 0<=r<len(shown)}
        self.items=[x for x in self.items if x['path'] not in remove]; self.favorites-=remove; self.refresh()
    def rescan(self):
        old={x['path']:x for x in self.items}; paths=list(old); dirs=sorted({str(Path(p).parent) for p in paths}); fresh=scan_paths(dirs,self.recursive.isChecked()) if dirs else []
        for x in fresh:
            if x['path'] in old:
                for k in ('tags','notes','print_status'):
                    x[k]=old[x['path']].get(k,enrich_item({})[k])
        self.items=[enrich_item(x) for x in fresh]; self.dedupe(); self.refresh(); self.status.setText('Library rescanned; metadata preserved')
    def filtered(self):
        q=self.search.text().strip().lower(); dups=make_library_report(self.items)['duplicates']; dup_paths=set(sum(dups['exact']+dups['near'],[])); out=[]
        for x in self.items:
            hay=f"{x['name']} {x['path']} {x['suffix']} {x['width_px']}x{x['height_px']} {' '.join(x.get('tags',[]))} {x.get('notes','')} {x.get('print_status','New')}".lower()
            if q and q not in hay: continue
            if self.only_fav.isChecked() and x['path'] not in self.favorites: continue
            if self.only_dup.isChecked() and x['path'] not in dup_paths: continue
            out.append(x)
        return out
    def refresh(self):
        shown=self.filtered(); self.table.setRowCount(0); dups=make_library_report(self.items)['duplicates']; dup_paths=set(sum(dups['exact']+dups['near'],[]))
        for x in shown:
            r=self.table.rowCount(); self.table.insertRow(r)
            try:
                pix=QPixmap(x['path']).scaled(72,72,Qt.KeepAspectRatio,Qt.SmoothTransformation); it=QTableWidgetItem(); it.setIcon(QIcon(pix)); self.table.setItem(r,0,it)
            except Exception: self.table.setItem(r,0,QTableWidgetItem(''))
            vals=[x['name'],f"{x['width_px']} × {x['height_px']} px",f"{x['dpi_x']} × {x['dpi_y']}",x['mode'],'Yes' if x['alpha'] else 'No',f"{x['bytes']/1048576:.2f} MB",', '.join(x.get('tags',[])),x.get('print_status','New'),x.get('notes','')[:80]]
            for c,v in enumerate(vals,1): self.table.setItem(r,c,QTableWidgetItem(str(v)))
            if x['path'] in dup_paths and self.table.item(r,8): self.table.item(r,8).setText((self.table.item(r,8).text()+' • Duplicate').strip())
        rep=make_library_report_v27(self.items); base=make_library_report(self.items); self.stats.setText(f"Library: {len(self.items)} assets • {base['total_mb']} MB • {base['exact_duplicate_groups']} exact dup groups • {base['near_duplicate_groups']} near dup groups • {len(rep['tags'])} tags • Showing {len(shown)}")
    def selected_items(self):
        shown=self.filtered(); rows=sorted({i.row() for i in self.table.selectedIndexes()}); return [shown[r] for r in rows if 0<=r<len(shown)]
    def selected_item(self):
        xs=self.selected_items(); return xs[0] if xs else None
    def toggle_favorite(self):
        xs=self.selected_items()
        for x in xs:
            p=x['path']; self.favorites.remove(p) if p in self.favorites else self.favorites.add(p)
        self.refresh()
    def edit_metadata(self):
        x=self.selected_item()
        if not x:return
        tags,ok=QInputDialog.getText(self,'Artwork Tags','Comma-separated tags:',text=', '.join(x.get('tags',[])))
        if not ok:return
        notes,ok=QInputDialog.getMultiLineText(self,'Artwork Notes','Notes:',x.get('notes',''))
        if not ok:return
        x['tags']=[t.strip() for t in tags.split(',') if t.strip()]; x['notes']=notes; self.refresh()
    def change_status(self):
        x=self.selected_item()
        if not x:return
        current=x.get('print_status','New'); val,ok=QInputDialog.getItem(self,'Print Status','Status:',STATUSES,STATUSES.index(current) if current in STATUSES else 0,False)
        if ok:x['print_status']=val; self.refresh()
    def open_selected(self):
        x=self.selected_item()
        if not x:return
        if sys.platform=='win32': os.startfile(x['path'])
        elif sys.platform=='darwin': os.system(f'open "{x["path"]}"')
        else: os.system(f'xdg-open "{x["path"]}"')
    def export_contact_sheet(self):
        xs=self.selected_items() or self.filtered()
        if not xs:return
        p,_=QFileDialog.getSaveFileName(self,'Export Visual Contact Sheet','artwork_contact_sheet.jpg','JPEG (*.jpg *.jpeg)')
        if p:
            try: make_contact_sheet(xs,p); self.status.setText(f'Contact sheet exported: {p}')
            except Exception as e: QMessageBox.critical(self,'Contact Sheet',str(e))
    def send_to_queue(self):
        xs=self.selected_items()
        if not xs:
            QMessageBox.information(self,'Production Queue','Select one or more artworks first.'); return
        jobs=queue_from_library_items(xs, V28_PRESETS['Dark Garment 6-Color'])
        self.queue_handoff.emit(jobs)
        p,_=QFileDialog.getSaveFileName(self,'Optional: Save Queue JSON','library_queue_v28.json','JSON (*.json)')
        if p:
            Path(p).write_text(json.dumps({'version':'V28','created_at':datetime.datetime.now().isoformat(timespec='seconds'),'jobs':jobs},indent=2,ensure_ascii=False),encoding='utf-8')
            self.status.setText(f'{len(jobs)} artwork(s) sent to Production Queue + saved: {p}')
        else:
            self.status.setText(f'{len(jobs)} artwork(s) sent directly to Production Queue')
    def save_lib(self):
        p,_=QFileDialog.getSaveFileName(self,'Save Artwork Library','artwork_library_v27.json','JSON (*.json)')
        if p: save_library_v27(p,self.items,self.favorites); self.library_path=p; self.status.setText(f'Saved V27 library: {p}')
    def load_lib(self):
        p,_=QFileDialog.getOpenFileName(self,'Load Artwork Library','','JSON (*.json)')
        if not p:return
        try:self.items,self.favorites=load_library_v27(p); self.library_path=p; self.refresh(); self.status.setText(f'Loaded {len(self.items)} assets')
        except Exception as e: QMessageBox.critical(self,'Library',str(e))
    def export_report(self):
        p,_=QFileDialog.getSaveFileName(self,'Export V27 Library Report','artwork_library_v27_report.json','JSON (*.json)')
        if p:
            d=make_library_report_v27(self.items); base=make_library_report(self.items); d.update({'total_bytes':base['total_bytes'],'total_mb':base['total_mb'],'duplicates':base['duplicates'],'favorites':len(self.favorites)})
            Path(p).write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8'); self.status.setText(f'Exported report: {p}')


class WorkspaceThread(QThread):
    progress=Signal(int,str); ok=Signal(object,str); fail=Signal(str); cancelled=Signal(object,str)
    def __init__(self,jobs,root,target=300,min_dpi=150):
        super().__init__(); self.jobs=jobs; self.root=root; self.target=target; self.min_dpi=min_dpi; self.paused=False
    def run(self):
        try:
            mgr=ProductionQueueManager(self.jobs,self.root,
                progress=lambda p,m:self.progress.emit(p,m),
                cancelled=self.isInterruptionRequested,
                paused=lambda:self.paused,
                target_dpi=self.target,min_dpi=self.min_dpi,preflight=True)
            res,log=mgr.run()
            if self.isInterruptionRequested(): self.cancelled.emit(res,log)
            else: self.ok.emit(res,log)
        except Cancelled:
            self.cancelled.emit(getattr(locals().get('mgr',None),'logs',[]), getattr(locals().get('mgr',None),'log_path',''))
        except Exception: self.fail.emit(traceback.format_exc())


class ProductionWorkspaceTab(QWidget):
    """V29 unified visual workspace: thumbnails, job editor, presets, validation and queue handoff."""
    queue_handoff=Signal(object)
    def __init__(self):
        super().__init__(); self.jobs=[]; self.thread=None; self._loading=False
        self.list=QListWidget(); self.list.setIconSize(QSize(92,92)); self.list.setMinimumWidth(360); self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.preview=QLabel('Select an artwork'); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumHeight(360); self.preview.setStyleSheet('background:#111;border:1px solid #333;border-radius:10px;color:#777')
        self.name=QLineEdit(); self.source=QLineEdit(); self.output=QLineEdit(); self.browse=QPushButton('Browse Source'); self.output_btn=QPushButton('Output Folder')
        self.mode=QComboBox(); self.mode.addItems(['Spot','CMYK'])
        self.colors=QSpinBox(); self.colors.setRange(2,16); self.colors.setValue(6)
        self.target=QSpinBox(); self.target.setRange(72,1200); self.target.setValue(300); self.min_dpi=QSpinBox(); self.min_dpi.setRange(36,1200); self.min_dpi.setValue(150)
        self.choke=QSpinBox(); self.choke.setRange(0,8); self.choke.setValue(1); self.cell=QSpinBox(); self.cell.setRange(3,40); self.cell.setValue(8); self.angle=QSpinBox(); self.angle.setRange(0,179); self.angle.setValue(45)
        self.clean=QCheckBox('Cleanup'); self.recon=QCheckBox('Reconstruct'); self.cut=QCheckBox('AI Cutout'); self.ub=QCheckBox('Underbase'); self.half=QCheckBox('Halftone')
        for w in (self.clean,self.recon,self.ub,self.half): w.setChecked(True)
        self.preset=QComboBox(); self.preset.addItems(list(WORKSPACE_PRESETS.keys())); self.apply=QPushButton('Apply Preset')
        self.add=QPushButton('＋ Add Artwork'); self.dup=QPushButton('Duplicate'); self.remove=QPushButton('Remove'); self.up=QPushButton('↑'); self.down=QPushButton('↓')
        self.save=QPushButton('Save Workspace'); self.load=QPushButton('Load Workspace'); self.save_preset=QPushButton('Save Current Preset')
        self.validate=QPushButton('✓ Validate'); self.send=QPushButton('🚀 Send to Queue'); self.run_sel=QPushButton('▶ Run Selected'); self.run_all=QPushButton('▶ Run All'); self.pause=QPushButton('Pause'); self.cancel=QPushButton('Cancel'); self.pause.setEnabled(False); self.cancel.setEnabled(False)
        self.progress=QProgressBar(); self.status=QLabel('V29 Production Workspace ready')
        self.summary=QLabel('0 jobs')
        self.results=QTableWidget(0,5); self.results.setHorizontalHeaderLabels(['Job','Status','Time (s)','Output MB','Preflight']); self.results.horizontalHeader().setStretchLastSection(True)
        self.list.currentRowChanged.connect(self.select_job); self.browse.clicked.connect(self.pick_source); self.output_btn.clicked.connect(self.pick_output); self.add.clicked.connect(self.add_artwork); self.dup.clicked.connect(self.duplicate_job); self.remove.clicked.connect(self.remove_job); self.up.clicked.connect(lambda:self.move(-1)); self.down.clicked.connect(lambda:self.move(1)); self.apply.clicked.connect(self.apply_preset); self.save.clicked.connect(self.save_ws); self.load.clicked.connect(self.load_ws); self.save_preset.clicked.connect(self.save_current_preset); self.validate.clicked.connect(self.validate_current); self.send.clicked.connect(self.send_queue); self.run_sel.clicked.connect(lambda:self.start(False)); self.run_all.clicked.connect(lambda:self.start(True)); self.pause.clicked.connect(self.toggle_pause); self.cancel.clicked.connect(self.stop)
        for w in (self.name,self.source,self.mode,self.colors,self.target,self.min_dpi,self.choke,self.cell,self.angle,self.clean,self.recon,self.cut,self.ub,self.half):
            try: w.editingFinished.connect(self.commit_editor)
            except Exception: pass
        self.mode.currentTextChanged.connect(self.commit_editor); [w.stateChanged.connect(self.commit_editor) for w in (self.clean,self.recon,self.cut,self.ub,self.half)]
        form=QFormLayout(); form.addRow('Name',self.name); form.addRow('Source',self.source); form.addRow('Separation',self.mode); form.addRow('Spot colors',self.colors); form.addRow('Target DPI',self.target); form.addRow('Min DPI',self.min_dpi); form.addRow('Choke',self.choke); form.addRow('Halftone cell',self.cell); form.addRow('Screen angle',self.angle)
        src=QHBoxLayout(); src.addWidget(self.browse); src.addWidget(self.output_btn); src.addWidget(self.output)
        opts=QHBoxLayout(); [opts.addWidget(w) for w in (self.clean,self.recon,self.cut,self.ub,self.half)]; opts.addStretch()
        tools=QHBoxLayout(); [tools.addWidget(w) for w in (self.add,self.dup,self.remove,self.up,self.down)]; tools.addWidget(QLabel('Preset:')); tools.addWidget(self.preset); tools.addWidget(self.apply); tools.addWidget(self.save_preset)
        io=QHBoxLayout(); [io.addWidget(w) for w in (self.save,self.load,self.validate,self.send)]
        run=QHBoxLayout(); [run.addWidget(w) for w in (self.run_sel,self.run_all,self.pause,self.cancel)]
        right=QVBoxLayout(); right.addWidget(self.preview,2); right.addLayout(form); right.addLayout(opts); right.addWidget(QLabel('Output root')); right.addLayout(src); right.addLayout(tools); right.addLayout(io); right.addLayout(run); right.addWidget(self.progress); right.addWidget(self.summary); right.addWidget(self.status); right.addWidget(self.results,1)
        left=QVBoxLayout(); left.addWidget(QLabel('Visual Job List')); left.addWidget(self.list,1)
        main=QHBoxLayout(self); main.addLayout(left,2); main.addLayout(right,4)
    def _item_text(self,j):
        st=estimate_job_stats(j); dims=(f"{st.get('width_px','?')}×{st.get('height_px','?')}" if st.get('exists') else 'missing')
        return f"{j.get('name','Job')}  •  {Path(j.get('source','')).name}\n{dims}  •  {j.get('preset','Custom') or 'Custom'}"
    def rebuild(self,select=0):
        self.list.clear()
        for j in self.jobs:
            item=QListWidgetItem(self._item_text(j)); p=j.get('source','')
            if p and Path(p).exists():
                try: item.setIcon(QIcon(QPixmap(p).scaled(92,92,Qt.KeepAspectRatio,Qt.SmoothTransformation)))
                except Exception: pass
            self.list.addItem(item)
        if self.jobs: self.list.setCurrentRow(max(0,min(select,len(self.jobs)-1)))
        self.summary.setText(self._summary_text())
    def _summary_text(self):
        s=make_workspace_summary(self.jobs); return f"Jobs: {s['jobs']} • Sources OK: {s['existing_sources']} • Missing: {s['missing_sources']} • Estimated MP: {s['estimated_megapixels']} • Presets: {', '.join(s['presets']) or 'Custom'}"
    def selected_index(self): return self.list.currentRow()
    def select_job(self,row):
        if row<0 or row>=len(self.jobs): self.preview.setText('Select an artwork'); return
        self._loading=True; j=self.jobs[row]; self.name.setText(j.get('name','')); self.source.setText(j.get('source','')); o=j.get('options',{}); self.mode.setCurrentText(o.get('mode','Spot')); self.colors.setValue(int(o.get('colors',6))); self.target.setValue(int(o.get('target_dpi',300))); self.min_dpi.setValue(int(o.get('min_dpi',150))); self.choke.setValue(int(o.get('choke',1))); self.cell.setValue(int(o.get('cell',8))); self.angle.setValue(int(o.get('angle',45)))
        for w,k in ((self.clean,'cleanup'),(self.recon,'reconstruct'),(self.cut,'cutout'),(self.ub,'underbase'),(self.half,'halftone')): w.setChecked(bool(o.get(k,False)))
        p=j.get('source','')
        if p and Path(p).exists():
            try: self.preview.setPixmap(QPixmap(p).scaled(760,360,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            except Exception: self.preview.setText(p)
        else: self.preview.setText('Source file missing')
        preset=j.get('preset',''); idx=self.preset.findText(preset); self.preset.setCurrentIndex(idx if idx>=0 else 0); self._loading=False; self.status.setText(f'Editing: {j.get("name","Job")}')
    def commit_editor(self,*args):
        if self._loading:return
        r=self.selected_index()
        if not (0<=r<len(self.jobs)):return
        j=self.jobs[r]; j['name']=self.name.text().strip() or Path(self.source.text()).stem or 'Job'; j['source']=self.source.text().strip(); j['options']={'mode':self.mode.currentText(),'colors':self.colors.value(),'target_dpi':self.target.value(),'min_dpi':self.min_dpi.value(),'choke':self.choke.value(),'cell':self.cell.value(),'angle':self.angle.value(),'cleanup':self.clean.isChecked(),'reconstruct':self.recon.isChecked(),'cutout':self.cut.isChecked(),'underbase':self.ub.isChecked(),'halftone':self.half.isChecked()}; self.rebuild(r)
    def add_artwork(self):
        ps,_=QFileDialog.getOpenFileNames(self,'Add Artwork(s)','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if not ps:return
        start=len(self.jobs)
        for p in ps:self.jobs.append({'name':Path(p).stem,'source':p,'options':{},'preset':'Dark Garment 6-Color'}); self.jobs[-1]=apply_preset_to_job(self.jobs[-1],WORKSPACE_PRESETS['Dark Garment 6-Color'])
        self.rebuild(start)
    def pick_source(self):
        p,_=QFileDialog.getOpenFileName(self,'Choose Source','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if p:self.source.setText(p); self.name.setText(self.name.text().strip() or Path(p).stem); self.commit_editor()
    def pick_output(self):
        p=QFileDialog.getExistingDirectory(self,'Choose Production Output Root')
        if p:self.output.setText(p)
    def duplicate_job(self):
        r=self.selected_index()
        if 0<=r<len(self.jobs): self.jobs.insert(r+1,copy.deepcopy(self.jobs[r])); self.jobs[r+1]['name']=self.jobs[r+1].get('name','Job')+' Copy'; self.rebuild(r+1)
    def remove_job(self):
        r=self.selected_index()
        if 0<=r<len(self.jobs): self.jobs.pop(r); self.rebuild(max(0,r-1) if self.jobs else 0)
    def move(self,d):
        r=self.selected_index(); n=r+d
        if 0<=r<len(self.jobs) and 0<=n<len(self.jobs): self.jobs[r],self.jobs[n]=self.jobs[n],self.jobs[r]; self.rebuild(n)
    def apply_preset(self):
        r=self.selected_index()
        if not (0<=r<len(self.jobs)):return
        name=self.preset.currentText(); self.jobs[r]=apply_preset_to_job(self.jobs[r],WORKSPACE_PRESETS[name]); self.jobs[r]['preset']=name; self.rebuild(r); self.status.setText(f'Applied {name}')
    def save_ws(self):
        self.commit_editor(); p,_=QFileDialog.getSaveFileName(self,'Save V29 Workspace','production_workspace_v29.json','JSON (*.json)')
        if p: save_workspace(p,self.jobs,self.output.text().strip()); self.status.setText(f'Saved workspace: {p}')
    def load_ws(self):
        p,_=QFileDialog.getOpenFileName(self,'Load V29 Workspace','','JSON (*.json)')
        if not p:return
        try:
            self.jobs,out=load_workspace(p); self.output.setText(out); self.rebuild(); self.status.setText(f'Loaded {len(self.jobs)} job(s)')
        except Exception as e: QMessageBox.critical(self,'Workspace',str(e))
    def save_current_preset(self):
        r=self.selected_index()
        if not (0<=r<len(self.jobs)):return
        p,_=QFileDialog.getSaveFileName(self,'Save Current Preset','custom_preset_v29.json','JSON (*.json)')
        if p:
            Path(p).write_text(json.dumps({'version':'V29','name':self.jobs[r].get('name','Custom'),'options':self.jobs[r].get('options',{})},indent=2),encoding='utf-8'); self.status.setText(f'Saved preset: {p}')
    def validate_current(self):
        r=self.selected_index()
        if not (0<=r<len(self.jobs)):return
        src=self.jobs[r].get('source','')
        try:
            recs,issues=validate_one(src,self.target.value(),self.min_dpi.value())
            errs=[i.message for i in issues if i.severity=='ERROR']; warns=[i.message for i in issues if i.severity=='WARNING']
            self.status.setText(f'Preflight: {len(errs)} error(s), {len(warns)} warning(s)')
            QMessageBox.information(self,'Preflight Result','ERRORS:\n'+'\n'.join(errs or ['None'])+'\n\nWARNINGS:\n'+'\n'.join(warns or ['None']))
        except Exception as e: QMessageBox.critical(self,'Preflight',str(e))
    def send_queue(self):
        self.commit_editor(); jobs=[normalize_job(j) for j in self.jobs]
        if not jobs:return
        self.queue_handoff.emit(jobs); self.status.setText(f'{len(jobs)} job(s) sent to Production Queue')
    def start(self,all_jobs):
        self.commit_editor(); jobs=self.jobs if all_jobs else ([self.jobs[self.selected_index()]] if 0<=self.selected_index()<len(self.jobs) else [])
        if not jobs:return
        root=self.output.text().strip()
        if not root: QMessageBox.warning(self,'Production','Choose an output root first.'); return
        self.thread=WorkspaceThread(jobs,root,self.target.value(),self.min_dpi.value()); self.thread.progress.connect(self.report); self.thread.ok.connect(self.done); self.thread.fail.connect(self.failed); self.thread.cancelled.connect(self.was_cancelled); self.thread.finished.connect(self.thread.deleteLater)
        for w in (self.add,self.dup,self.remove,self.up,self.down,self.apply,self.save,self.load,self.validate,self.send,self.run_sel,self.run_all):w.setEnabled(False)
        self.pause.setEnabled(True); self.cancel.setEnabled(True); self.progress.setValue(0); self.thread.start()
    def report(self,p,m):self.progress.setValue(p);self.status.setText(m)
    def toggle_pause(self):
        if self.thread and self.thread.isRunning(): self.thread.paused=not self.thread.paused; self.pause.setText('Resume' if self.thread.paused else 'Pause'); self.status.setText('Paused' if self.thread.paused else 'Resuming…')
    def stop(self):
        if self.thread and self.thread.isRunning(): self.thread.requestInterruption(); self.status.setText('Cancelling…')
    def reset_run(self):
        for w in (self.add,self.dup,self.remove,self.up,self.down,self.apply,self.save,self.load,self.validate,self.send,self.run_sel,self.run_all):w.setEnabled(True)
        self.pause.setEnabled(False);self.cancel.setEnabled(False);self.pause.setText('Pause')
    def done(self,results,log):
        self.reset_run();self.progress.setValue(100);self.refresh_results(results);self.status.setText(f'Finished • {len(results)} job(s) • log: {log}')
    def was_cancelled(self,results,log):self.reset_run();self.refresh_results(results);self.status.setText(f'Cancelled • log: {log}')
    def failed(self,msg):self.reset_run();QMessageBox.critical(self,'Production Error',msg)
    def refresh_results(self,results):
        self.results.setRowCount(0)
        for r in results:
            row=self.results.rowCount();self.results.insertRow(row);pf=r.get('preflight',{});st=r.get('stats',{})
            vals=[r.get('name',''),r.get('status',''),r.get('elapsed_s',''),st.get('mb',''),f"{pf.get('errors',0)}E/{pf.get('warnings',0)}W"]
            for c,v in enumerate(vals):self.results.setItem(row,c,QTableWidgetItem(str(v)))


class OutputCenterThread(QThread):
    ok=Signal(object); fail=Signal(str)
    def __init__(self, source, root, settings):
        super().__init__(); self.source=source; self.root=root; self.settings=settings
    def run(self):
        try:
            def ch_builder(im, mode, n, tol):
                if mode=='CMYK': return cmyk_masks(im)
                cols=quantized_palette(im,max(2,min(16,n))); return spot_masks(im,cols,tol), [f'Spot_{i+1}' for i in range(len(cols))]
            def ub_builder(im, mode, threshold, strength, choke): return underbase_mask(im,mode,threshold,strength,choke)
            def half_builder(mask,cell,angle): return screen_halftone(mask,cell,angle)
            def contact_builder(imgs,labels): return production_v30_contact(imgs,labels)
            def validate(src,dpi):
                try:
                    recs,issues=validate_artworks([src],target_dpi=dpi,min_dpi=int(self.settings.get('min_dpi',150)))
                    return {'records':[r.__dict__ for r in recs], 'issues':[i.__dict__ for i in issues]}
                except Exception as e:return {'error':str(e)}
            manifest,outputs,jobdir=export_artwork_package(self.source,self.root,self.settings,
                validate_fn=validate,channel_builder=ch_builder,underbase_builder=ub_builder,
                halftone_builder=half_builder,contact_builder=contact_builder)
            self.ok.emit({'manifest':manifest,'outputs':outputs,'jobdir':jobdir})
        except Exception:self.fail.emit(traceback.format_exc())


def production_v30_contact(imgs,labels):
    if not imgs:return Image.new('RGBA',(10,10),(255,255,255,255))
    # local contact sheet avoids coupling to a UI-specific library helper
    thumbs=[]
    for im in imgs:
        x=im.convert('L').convert('RGBA'); x.thumbnail((520,380),Image.Resampling.LANCZOS); thumbs.append(x)
    cols=2; gap=18; margin=24; cw=max(x.width for x in thumbs); ch=max(x.height for x in thumbs)+28; rows=(len(thumbs)+1)//2
    out=Image.new('RGBA',(margin*2+cols*cw+(cols-1)*gap,margin*2+rows*ch+(rows-1)*gap),(238,238,238,255)); d=ImageDraw.Draw(out)
    for i,x in enumerate(thumbs):
        c=i%2;r=i//2;xx=margin+c*(cw+gap)+(cw-x.width)//2;yy=margin+r*(ch+gap);out.alpha_composite(x,(xx,yy));d.text((margin+c*(cw+gap),yy+x.height+5),str(labels[i]),fill=(20,20,20,255))
    return out


class OutputCenterTab(QWidget):
    """V30 centralized export/package center. Uses existing separation/underbase/halftone engines as preview/engineering outputs."""
    def __init__(self):
        super().__init__(); self.thread=None
        self.source=QLineEdit(); self.root=QLineEdit(); self.prefix=QLineEdit(); self.prefix.setPlaceholderText('Optional output/job name')
        self.browse=QPushButton('Choose Artwork'); self.root_btn=QPushButton('Output Folder')
        self.sep=QComboBox(); self.sep.addItems(['Spot','CMYK']); self.colors=QSpinBox(); self.colors.setRange(2,16); self.colors.setValue(6)
        self.dpi=QSpinBox(); self.dpi.setRange(72,1200); self.dpi.setValue(300); self.min_dpi=QSpinBox(); self.min_dpi.setRange(36,1200); self.min_dpi.setValue(150)
        self.cell=QSpinBox(); self.cell.setRange(3,40); self.cell.setValue(8); self.angle=QSpinBox(); self.angle.setRange(0,179); self.angle.setValue(45)
        self.choke=QSpinBox(); self.choke.setRange(0,8); self.choke.setValue(1); self.tol=QDoubleSpinBox(); self.tol.setRange(1,100); self.tol.setValue(18); self.tol.setDecimals(1)
        self.format=QComboBox(); self.format.addItems(['PNG','TIFF'])
        self.trim=QCheckBox('Trim transparent margins'); self.trim.setChecked(True); self.ub=QCheckBox('Export Underbase'); self.ub.setChecked(True); self.half=QCheckBox('Export Halftone previews'); self.half.setChecked(True); self.contact=QCheckBox('Channel Contact Sheet'); self.contact.setChecked(True); self.package=QCheckBox('Create Production ZIP'); self.package.setChecked(True)
        self.run=QPushButton('🚀 Build Export Package'); self.status=QLabel('V30 Output Center ready'); self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.setVisible(False)
        self.result=QTextEdit(); self.result.setReadOnly(True)
        form=QFormLayout();
        r=QHBoxLayout();r.addWidget(self.source,1);r.addWidget(self.browse);form.addRow('Artwork',r)
        r=QHBoxLayout();r.addWidget(self.root,1);r.addWidget(self.root_btn);form.addRow('Output Root',r)
        form.addRow('Job / Prefix',self.prefix);form.addRow('Separation',self.sep);form.addRow('Spot Colors',self.colors);form.addRow('DPI',self.dpi);form.addRow('Minimum DPI',self.min_dpi);form.addRow('Tolerance ΔE76',self.tol);form.addRow('Halftone Cell',self.cell);form.addRow('Screen Angle',self.angle);form.addRow('Underbase Choke',self.choke);form.addRow('Master Format',self.format)
        checks=QVBoxLayout();
        for w in (self.trim,self.ub,self.half,self.contact,self.package):checks.addWidget(w)
        btns=QHBoxLayout();btns.addWidget(self.run);btns.addStretch();btns.addWidget(self.status)
        layout=QVBoxLayout(self); layout.addLayout(form);layout.addLayout(checks);layout.addLayout(btns);layout.addWidget(self.progress);layout.addWidget(self.result,1)
        self.browse.clicked.connect(self.pick); self.root_btn.clicked.connect(self.pick_root); self.run.clicked.connect(self.start)
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,'Choose Artwork','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if p:self.source.setText(p); self.prefix.setText(Path(p).stem)
    def pick_root(self):
        p=QFileDialog.getExistingDirectory(self,'Choose Output Root')
        if p:self.root.setText(p)
    def start(self):
        src=self.source.text().strip(); root=self.root.text().strip()
        if not src or not Path(src).exists(): QMessageBox.warning(self,'Output Center','Choose a valid artwork first.'); return
        if not root: root=str(Path(src).parent/'ImageStudio_Exports'); self.root.setText(root)
        settings={'prefix':self.prefix.text().strip() or Path(src).stem,'separation':self.sep.currentText(),'colors':self.colors.value(),'dpi':self.dpi.value(),'min_dpi':self.min_dpi.value(),'tolerance':self.tol.value(),'cell':self.cell.value(),'angle':self.angle.value(),'choke':self.choke.value(),'format':self.format.currentText(),'trim_alpha':self.trim.isChecked(),'underbase':self.ub.isChecked(),'halftone':self.half.isChecked(),'contact_sheet':self.contact.isChecked(),'package_zip':self.package.isChecked()}
        self.run.setEnabled(False);self.progress.setVisible(True);self.status.setText('Building production export…');self.result.clear()
        self.thread=OutputCenterThread(src,root,settings);self.thread.ok.connect(self.done);self.thread.fail.connect(self.failed);self.thread.finished.connect(self.thread.deleteLater);self.thread.start()
    def done(self,data):
        self.run.setEnabled(True);self.progress.setVisible(False);m=data['manifest'];outs=data['outputs'];
        self.status.setText(f'Export complete • {len(outs)} files');self.result.setPlainText(json.dumps({'jobdir':data['jobdir'],'outputs':outs,'manifest':m},indent=2,ensure_ascii=False))
    def failed(self,msg):self.run.setEnabled(True);self.progress.setVisible(False);self.status.setText('Export failed');QMessageBox.critical(self,'Output Center',msg)


class PrintIntelligenceTab(QWidget):
    """V31 print-production intelligence: measurable coverage/size/proof/report; not a calibrated RIP."""
    def __init__(self):
        super().__init__(); self.source=QLineEdit(); self.root=QLineEdit(); self.dpi=QSpinBox(); self.dpi.setRange(72,1200); self.dpi.setValue(300)
        self.garment=QComboBox(); self.garment.addItems(['Black','White','Navy','Red','Royal Blue','Dark Gray'])
        self.sheet=QComboBox(); self.sheet.addItems(['None','A4 (210×297 mm)','A3 (297×420 mm)','12×18 in (304.8×457.2 mm)','13×19 in (330.2×482.6 mm)'])
        self.analyze=QPushButton('🔍 Analyze Production'); self.proof=QPushButton('👕 Garment Proof'); self.reg=QPushButton('🎯 Registration Preview'); self.save=QPushButton('💾 Save Intelligence Report')
        self.out=QTextEdit(); self.out.setReadOnly(True); self.status=QLabel('V31 Production Intelligence ready'); self.last=None
        f=QFormLayout(); r=QHBoxLayout();r.addWidget(self.source,1);b=QPushButton('Choose Artwork');r.addWidget(b);f.addRow('Artwork',r);f.addRow('Target DPI',self.dpi);f.addRow('Garment',self.garment);f.addRow('Gang Sheet',self.sheet)
        row=QHBoxLayout();[row.addWidget(x) for x in (self.analyze,self.proof,self.reg,self.save)];row.addStretch();f.addRow(row)
        lay=QVBoxLayout(self);lay.addLayout(f);lay.addWidget(self.status);lay.addWidget(self.out,1)
        b.clicked.connect(self.pick);self.analyze.clicked.connect(self.run);self.proof.clicked.connect(self.make_proof);self.reg.clicked.connect(self.make_reg);self.save.clicked.connect(self.save_report)
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,'Choose Artwork','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if p:self.source.setText(p);self.status.setText(Path(p).name)
    def sheet_mm(self):
        vals={'A4 (210×297 mm)':(210,297),'A3 (297×420 mm)':(297,420),'12×18 in (304.8×457.2 mm)':(304.8,457.2),'13×19 in (330.2×482.6 mm)':(330.2,482.6)}
        return vals.get(self.sheet.currentText())
    def run(self):
        p=self.source.text().strip()
        if not p or not Path(p).exists(): QMessageBox.warning(self,'Production Intelligence','Choose a valid artwork first.');return
        try:
            self.last=build_print_intelligence(p,target_dpi=self.dpi.value(),sheet_mm=self.sheet_mm(),garment=self.garment.currentText())
            self.out.setPlainText(json.dumps(self.last,indent=2,ensure_ascii=False));self.status.setText('Analysis complete')
        except Exception as e: QMessageBox.critical(self,'Analysis',str(e))
    def make_proof(self):
        p=self.source.text().strip()
        if not p or not Path(p).exists(): return
        try:
            im=Image.open(p).convert('RGBA'); x=garment_proof(im,self.garment.currentText()); path,_=QFileDialog.getSaveFileName(self,'Save Garment Proof','garment_proof.png','PNG (*.png)')
            if path:x.save(path,'PNG');self.status.setText(f'Garment proof saved: {path}')
        except Exception as e: QMessageBox.critical(self,'Garment Proof',str(e))
    def make_reg(self):
        p=self.source.text().strip()
        if not p or not Path(p).exists(): return
        try:
            im=Image.open(p).convert('RGBA'); ov=registration_overlay(im.size); out=Image.alpha_composite(im,ov); path,_=QFileDialog.getSaveFileName(self,'Save Registration Preview','registration_preview.png','PNG (*.png)')
            if path:out.save(path,'PNG');self.status.setText(f'Registration preview saved: {path}')
        except Exception as e: QMessageBox.critical(self,'Registration',str(e))
    def save_report(self):
        if not self.last: self.run()
        if not self.last:return
        p,_=QFileDialog.getSaveFileName(self,'Save Production Intelligence Report','production_intelligence.json','JSON (*.json)')
        if p:save_intelligence_report(p,self.last);self.status.setText(f'Report saved: {p}')


class ColorLabTab(QWidget):
    """V32 Color Management & Separation Lab. Preview/diagnostic color science, not ICC/RIP calibration."""
    def __init__(self):
        super().__init__(); self.im=None; self.palette=[]; self.mask=None
        self.source=QLineEdit(); self.hex=QLineEdit('#FF6600'); self.tol=QSpinBox(); self.tol.setRange(1,100); self.tol.setValue(12)
        self.count=QSpinBox(); self.count.setRange(2,16); self.count.setValue(8)
        self.open=QPushButton('Open Artwork'); self.extract=QPushButton('Extract Palette'); self.compare=QPushButton('Compare to Reference')
        self.make=QPushButton('Create Spot Mask'); self.save_mask=QPushButton('Save Spot Mask'); self.save_report=QPushButton('Save LAB Report')
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(['#','HEX','RGB','L*','a*','b* / ΔE'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.info=QTextEdit(); self.info.setReadOnly(True); self.status=QLabel('V32 Color & Separation Lab ready'); self.last=None
        form=QFormLayout(); r=QHBoxLayout();r.addWidget(self.source,1);r.addWidget(self.open);form.addRow('Artwork',r);form.addRow('Reference HEX',self.hex);form.addRow('ΔE76 tolerance',self.tol);form.addRow('Palette colors',self.count)
        buttons=QHBoxLayout(); [buttons.addWidget(x) for x in (self.extract,self.compare,self.make,self.save_mask,self.save_report)]; buttons.addStretch()
        lay=QVBoxLayout(self); lay.addLayout(form); lay.addLayout(buttons); lay.addWidget(self.status)
        split=QSplitter(Qt.Horizontal); split.addWidget(self.table); split.addWidget(self.info); lay.addWidget(split,1)
        self.open.clicked.connect(self.pick); self.extract.clicked.connect(self.do_palette); self.compare.clicked.connect(self.do_compare); self.make.clicked.connect(self.do_mask); self.save_mask.clicked.connect(self.export_mask); self.save_report.clicked.connect(self.export_report)
        self.save_mask.setEnabled(False)
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,'Choose Artwork','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if p:self.source.setText(p); self.im=load_image(p); self.status.setText(f'Loaded {Path(p).name} • {self.im.width}×{self.im.height}')
    def do_palette(self):
        if self.im is None:return
        try:
            self.palette=sample_palette(self.im,self.count.value()); self.render_palette(); self.status.setText(f'Extracted {len(self.palette)} palette colors')
        except Exception as e:QMessageBox.critical(self,'Palette',str(e))
    def reference(self):
        try:return hex_to_rgb(self.hex.text())
        except Exception as e:QMessageBox.warning(self,'Reference Color',str(e)); return None
    def do_compare(self):
        if self.im is None:return
        if not self.palette:self.palette=sample_palette(self.im,self.count.value())
        ref=self.reference()
        if ref is None:return
        rows=palette_distance_report(self.palette,ref); self.render_rows(rows,ref); self.last={'reference':ref,'rows':rows}
        self.status.setText('LAB / ΔE76 comparison complete')
    def render_palette(self):
        ref=self.reference(); rows=[]
        for i,c in enumerate(self.palette,1):
            lab=rgb_to_lab(c); de=delta_e76(lab,rgb_to_lab(ref)) if ref else None
            rows.append({'index':i,'rgb':list(c),'hex':rgb_to_hex(c),'lab':lab,'delta_e76':de})
        self.render_rows(rows,ref)
    def render_rows(self,rows,ref):
        self.table.setRowCount(0)
        for r in rows:
            row=self.table.rowCount();self.table.insertRow(row)
            vals=[r['index'],r['hex'],str(tuple(r['rgb'])),f"{r['lab'][0]:.2f}",f"{r['lab'][1]:.2f}",f"{r['lab'][2]:.2f} / {r.get('delta_e76','—') if r.get('delta_e76') is not None else '—'}"]
            for c,v in enumerate(vals):self.table.setItem(row,c,QTableWidgetItem(str(v)))
        self.info.setPlainText(json.dumps({'reference':{'rgb':list(ref),'hex':rgb_to_hex(ref),'lab':rgb_to_lab(ref)} if ref else None,'palette':rows},indent=2,ensure_ascii=False))
    def do_mask(self):
        if self.im is None:return
        ref=self.reference()
        if ref is None:return
        try:
            self.mask=spot_mask(self.im,ref,self.tol.value(),True); st=mask_stats(self.mask)
            self.info.append('\n\nSpot mask diagnostics:\n'+json.dumps(st,indent=2)); self.save_mask.setEnabled(True); self.status.setText(f'Spot mask created • coverage {st["soft_coverage_pct"]}%')
        except Exception as e:QMessageBox.critical(self,'Spot Mask',str(e))
    def export_mask(self):
        if self.mask is None:return
        p,_=QFileDialog.getSaveFileName(self,'Save Spot Mask','spot_mask.png','PNG (*.png)')
        if p:self.mask.save(p,'PNG');self.status.setText(f'Saved mask: {p}')
    def export_report(self):
        if self.im is None:return
        ref=self.reference()
        if ref is None:return
        if not self.palette:self.palette=sample_palette(self.im,self.count.value())
        p,_=QFileDialog.getSaveFileName(self,'Save V32 LAB Report','color_lab_report.json','JSON (*.json)')
        if p:
            rep=make_lab_report(p,ref,self.palette,[self.mask] if self.mask else None,['Reference Spot'] if self.mask else None,self.tol.value()); self.last=rep; self.status.setText(f'Report saved: {p}')


class SeparationLabV33Tab(QWidget):
    """V33 named-spot separation lab. Engineering/preview calculations, not calibrated RIP."""
    def __init__(self):
        super().__init__(); self.im=None; self.channels=[]; self.knockout=[]; self.library=dict(DEFAULT_SPOT_LIBRARY)
        self.source=QLineEdit(); self.tol=QSpinBox(); self.tol.setRange(1,100); self.tol.setValue(12)
        self.trap=QSpinBox(); self.trap.setRange(0,8); self.trap.setValue(1)
        self.spot_table=QTableWidget(0,4); self.spot_table.setHorizontalHeaderLabels(['Use','Name','HEX','Status']); self.spot_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.info=QTextEdit(); self.info.setReadOnly(True); self.status=QLabel('V33 Advanced Separation Lab ready')
        self.open=QPushButton('Open Artwork'); self.generate=QPushButton('Generate Spot Channels'); self.knock=QPushButton('Build Knockout Preview'); self.contact=QPushButton('Save Channel Contact Sheet'); self.save_report=QPushButton('Save Separation Report'); self.save_lib=QPushButton('Save Spot Library'); self.load_lib=QPushButton('Load Spot Library')
        self.add=QPushButton('Add Spot'); self.remove=QPushButton('Remove Spot')
        f=QFormLayout(); r=QHBoxLayout(); r.addWidget(self.source,1); r.addWidget(self.open); f.addRow('Artwork',r); f.addRow('ΔE76 tolerance',self.tol); f.addRow('Trap pixels',self.trap)
        tools=QHBoxLayout(); [tools.addWidget(x) for x in (self.add,self.remove,self.load_lib,self.save_lib)]; tools.addStretch(); f.addRow('Spot Library',tools)
        row=QHBoxLayout(); [row.addWidget(x) for x in (self.generate,self.knock,self.contact,self.save_report)]; row.addStretch()
        lay=QVBoxLayout(self); lay.addLayout(f); lay.addLayout(row); lay.addWidget(self.status)
        split=QSplitter(Qt.Horizontal); split.addWidget(self.spot_table); split.addWidget(self.info); lay.addWidget(split,1)
        self.open.clicked.connect(self.pick); self.add.clicked.connect(self.add_spot); self.remove.clicked.connect(self.remove_spot); self.generate.clicked.connect(self.do_generate); self.knock.clicked.connect(self.do_knockout); self.contact.clicked.connect(self.save_contact); self.save_report.clicked.connect(self.export_report); self.load_lib.clicked.connect(self.load_library); self.save_lib.clicked.connect(self.save_library)
        self.populate()
    def populate(self):
        self.spot_table.setRowCount(0)
        for name,hx in self.library.items(): self.add_row(name,hx)
    def add_row(self,name,hx):
        r=self.spot_table.rowCount(); self.spot_table.insertRow(r)
        item=QTableWidgetItem(); item.setFlags(item.flags()|Qt.ItemIsUserCheckable); item.setCheckState(Qt.Checked); self.spot_table.setItem(r,0,item)
        self.spot_table.setItem(r,1,QTableWidgetItem(name)); self.spot_table.setItem(r,2,QTableWidgetItem(hx)); self.spot_table.setItem(r,3,QTableWidgetItem('Ready'))
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,'Choose Artwork','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if p:self.source.setText(p); self.im=Image.open(p).convert('RGBA'); self.status.setText(f'Loaded {Path(p).name} • {self.im.width}×{self.im.height}')
    def add_spot(self):
        from PySide6.QtWidgets import QInputDialog
        name,ok=QInputDialog.getText(self,'Add Spot','Spot name:')
        if not ok or not name.strip(): return
        hx,ok=QInputDialog.getText(self,'Add Spot','HEX color:','#FF6600')
        if not ok: return
        try: hex_to_rgb(hx); self.add_row(name.strip(),hx.strip().upper()); self.status.setText('Spot added')
        except Exception as e: QMessageBox.warning(self,'Spot',str(e))
    def remove_spot(self):
        rows=sorted({i.row() for i in self.spot_table.selectedIndexes()},reverse=True)
        for r in rows:self.spot_table.removeRow(r)
    def selected_spots(self):
        spots={}
        for r in range(self.spot_table.rowCount()):
            chk=self.spot_table.item(r,0); 
            if chk and chk.checkState()==Qt.Checked:
                name=self.spot_table.item(r,1).text().strip(); hx=self.spot_table.item(r,2).text().strip(); hex_to_rgb(hx); spots[name]=hx
        return spots
    def do_generate(self):
        if self.im is None: QMessageBox.warning(self,'Separation','Choose artwork first.'); return
        try:
            spots=self.selected_spots()
            if not spots: QMessageBox.warning(self,'Separation','Select at least one spot.'); return
            self.channels=make_spot_channels(self.im,spots,self.tol.value())
            rep=separation_report(self.channels,self.tol.value(),self.trap.value()); self.info.setPlainText(json.dumps(rep,indent=2,ensure_ascii=False)); self.status.setText(f'Generated {len(self.channels)} spot channels')
        except Exception as e: QMessageBox.critical(self,'Separation',str(e))
    def do_knockout(self):
        if not self.channels:self.do_generate()
        if not self.channels:return
        self.knockout=exclusive_knockout_channels(self.channels); rep=separation_report(self.channels,self.tol.value(),self.trap.value()); rep['knockout_mode']='priority/order'; self.info.setPlainText(json.dumps(rep,indent=2,ensure_ascii=False)); self.status.setText('Knockout overlap preview generated')
    def save_contact(self):
        if not self.channels:self.do_generate()
        if not self.channels:return
        p,_=QFileDialog.getSaveFileName(self,'Save Channel Contact Sheet','spot_channel_contact_sheet.png','PNG (*.png)')
        if p: channel_contact_sheet(self.channels).save(p,'PNG'); self.status.setText(f'Contact sheet saved: {p}')
    def export_report(self):
        if not self.channels:self.do_generate()
        if not self.channels:return
        p,_=QFileDialog.getSaveFileName(self,'Save V33 Separation Report','separation_v33.json','JSON (*.json)')
        if p: save_separation_report(p,separation_report(self.channels,self.tol.value(),self.trap.value())); self.status.setText(f'Report saved: {p}')
    def load_library(self):
        p,_=QFileDialog.getOpenFileName(self,'Load Spot Library','spot_library.json','JSON (*.json)')
        if p:
            try:self.library=load_spot_library(p); self.populate(); self.status.setText(f'Loaded {len(self.library)} spot definitions')
            except Exception as e:QMessageBox.critical(self,'Spot Library',str(e))
    def save_library(self):
        lib={}
        for r in range(self.spot_table.rowCount()):
            try:lib[self.spot_table.item(r,1).text().strip()]=self.spot_table.item(r,2).text().strip().upper(); hex_to_rgb(lib[self.spot_table.item(r,1).text().strip()])
            except Exception: pass
        p,_=QFileDialog.getSaveFileName(self,'Save Spot Library','spot_library.json','JSON (*.json)')
        if p:save_spot_library(p,lib); self.status.setText(f'Spot library saved: {p}')


class HalftoneFilmV34Tab(QWidget):
    """Channel-wise halftone/film lab. Engineering preview/export, not calibrated RIP screening."""
    def __init__(self):
        super().__init__(); self.im=None; self.channels=[]; self.items=[]
        self.source=QLineEdit(); self.open=QPushButton('Open Artwork')
        self.tol=QSpinBox(); self.tol.setRange(1,100); self.tol.setValue(12)
        self.dpi=QSpinBox(); self.dpi.setRange(72,1200); self.dpi.setValue(300)
        self.lpi=QDoubleSpinBox(); self.lpi.setRange(10,150); self.lpi.setValue(45); self.lpi.setDecimals(1)
        self.angle=QDoubleSpinBox(); self.angle.setRange(-180,180); self.angle.setValue(22.5); self.angle.setDecimals(1)
        self.shape=QComboBox(); self.shape.addItems(['circle','square','diamond','line'])
        self.density=QDoubleSpinBox(); self.density.setRange(0.1,2.0); self.density.setValue(1.0); self.density.setDecimals(2)
        self.film=QDoubleSpinBox(); self.film.setRange(0.1,2.0); self.film.setValue(1.0); self.film.setDecimals(2)
        self.spot_table=QTableWidget(0,3); self.spot_table.setHorizontalHeaderLabels(['Use','Name','HEX']); self.spot_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.info=QTextEdit(); self.info.setReadOnly(True); self.status=QLabel('V34 Halftone & Film Lab ready')
        self.generate=QPushButton('Generate Channels'); self.preview=QPushButton('Generate Halftone Preview'); self.export=QPushButton('Export Film Set'); self.contact=QPushButton('Save Contact Sheet'); self.report=QPushButton('Save Report')
        form=QFormLayout(); rr=QHBoxLayout(); rr.addWidget(self.source,1); rr.addWidget(self.open); form.addRow('Artwork',rr)
        form.addRow('ΔE76 tolerance',self.tol); form.addRow('Output DPI',self.dpi); form.addRow('LPI',self.lpi); form.addRow('Screen angle',self.angle); form.addRow('Dot shape',self.shape); form.addRow('Dot density',self.density); form.addRow('Film density',self.film)
        row=QHBoxLayout(); [row.addWidget(x) for x in (self.generate,self.preview,self.export,self.contact,self.report)]; row.addStretch()
        lay=QVBoxLayout(self); lay.addLayout(form); lay.addLayout(row); lay.addWidget(self.status)
        split=QSplitter(Qt.Horizontal); split.addWidget(self.spot_table); split.addWidget(self.info); lay.addWidget(split,1)
        self.open.clicked.connect(self.pick); self.generate.clicked.connect(self.do_generate); self.preview.clicked.connect(self.do_preview); self.export.clicked.connect(self.do_export); self.contact.clicked.connect(self.save_contact); self.report.clicked.connect(self.save_report)
        self.populate_spots()
    def populate_spots(self):
        self.spot_table.setRowCount(0)
        for name,hx in DEFAULT_SPOT_LIBRARY.items():
            r=self.spot_table.rowCount(); self.spot_table.insertRow(r)
            it=QTableWidgetItem(); it.setFlags(it.flags()|Qt.ItemIsUserCheckable); it.setCheckState(Qt.Checked); self.spot_table.setItem(r,0,it)
            self.spot_table.setItem(r,1,QTableWidgetItem(name)); self.spot_table.setItem(r,2,QTableWidgetItem(hx))
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,'Choose Artwork','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if p: self.source.setText(p); self.im=load_image(p); self.status.setText(f'Loaded {Path(p).name} • {self.im.width}×{self.im.height}')
    def selected_spots(self):
        spots={}
        for r in range(self.spot_table.rowCount()):
            if self.spot_table.item(r,0).checkState()==Qt.Checked:
                n=self.spot_table.item(r,1).text().strip(); hx=self.spot_table.item(r,2).text().strip(); hex_to_rgb(hx); spots[n]=hx
        return spots
    def do_generate(self):
        if self.im is None: QMessageBox.warning(self,'Halftone','Choose artwork first.'); return
        try:
            self.channels=make_spot_channels(self.im,self.selected_spots(),self.tol.value())
            self.info.setPlainText(json.dumps({'channels':[{'name':c['name'],'hex':c['hex'],'stats':c['stats']} for c in self.channels]},indent=2,ensure_ascii=False))
            self.status.setText(f'Generated {len(self.channels)} source channels')
        except Exception as e: QMessageBox.critical(self,'Halftone',str(e))
    def do_preview(self):
        if not self.channels:self.do_generate()
        if not self.channels:return
        try:
            items=[]; cell=lpi_to_cell_px(self.dpi.value(),self.lpi.value())
            for ch in self.channels:
                ht=halftone_channel(ch['mask'],cell,self.angle.value(),self.shape.currentText(),self.density.value(),True)
                film=simulate_film(ht,self.film.value(),True); items.append({'name':ch['name'],'image':film,'coverage_pct':sum(1 for v in film.getdata() if v<128)/(film.width*film.height)*100})
            self.items=items; self.info.setPlainText(json.dumps(halftone_report(items,self.dpi.value(),self.lpi.value(),self.angle.value(),self.shape.currentText(),self.density.value(),self.film.value()),indent=2,ensure_ascii=False)); self.status.setText(f'Halftone preview ready • cell {cell:.2f}px')
        except Exception as e: QMessageBox.critical(self,'Halftone Preview',str(e))
    def do_export(self):
        if not self.channels:self.do_generate()
        if not self.channels:return
        out=QFileDialog.getExistingDirectory(self,'Choose Film Output Folder')
        if not out:return
        try:
            items,rep=export_halftone_set(self.channels,out,self.dpi.value(),self.lpi.value(),self.angle.value(),self.shape.currentText(),self.density.value(),self.film.value()); self.items=items; self.info.setPlainText(json.dumps(rep,indent=2,ensure_ascii=False)); self.status.setText(f'Film set exported to {out}')
        except Exception as e: QMessageBox.critical(self,'Film Export',str(e))
    def save_contact(self):
        if not self.items:self.do_preview()
        if not self.items:return
        p,_=QFileDialog.getSaveFileName(self,'Save Halftone Contact Sheet','halftone_contact_sheet.png','PNG (*.png)')
        if p: halftone_contact_sheet(self.items).save(p,'PNG',dpi=(self.dpi.value(),self.dpi.value())); self.status.setText(f'Contact sheet saved: {p}')
    def save_report(self):
        if not self.items:self.do_preview()
        if not self.items:return
        p,_=QFileDialog.getSaveFileName(self,'Save V34 Halftone Report','halftone_v34.json','JSON (*.json)')
        if p: Path(p).write_text(json.dumps(halftone_report(self.items,self.dpi.value(),self.lpi.value(),self.angle.value(),self.shape.currentText(),self.density.value(),self.film.value()),indent=2,ensure_ascii=False),encoding='utf-8'); self.status.setText(f'Report saved: {p}')


class UnderbaseLabV35Tab(QWidget):
    """Dark-garment underbase engineering lab. Preview/mask generator, not calibrated RIP."""
    def __init__(self):
        super().__init__(); self.im=None; self.items=[]
        self.source=QLineEdit(); self.open=QPushButton('Open Artwork')
        self.mode=QComboBox(); self.mode.addItems(['adaptive','solid','luma'])
        self.threshold=QSpinBox(); self.threshold.setRange(0,255); self.threshold.setValue(12)
        self.strength=QSpinBox(); self.strength.setRange(1,100); self.strength.setValue(95)
        self.choke=QSpinBox(); self.choke.setRange(0,12); self.choke.setValue(1)
        self.spread=QSpinBox(); self.spread.setRange(0,12); self.spread.setValue(0)
        self.highlight=QSpinBox(); self.highlight.setRange(0,100); self.highlight.setValue(15)
        self.smooth=QDoubleSpinBox(); self.smooth.setRange(0,3); self.smooth.setValue(.6); self.smooth.setDecimals(2)
        self.dpi=QSpinBox(); self.dpi.setRange(72,1200); self.dpi.setValue(300)
        self.garment=QComboBox(); self.garment.addItems(list(GARMENTS.keys())); self.garment.setCurrentText('Black')
        self.preview_label=QLabel('Open artwork to preview'); self.preview_label.setAlignment(Qt.AlignCenter); self.preview_label.setMinimumHeight(400); self.preview_label.setStyleSheet('background:#111;border:1px solid #333;border-radius:10px;color:#777')
        self.info=QTextEdit(); self.info.setReadOnly(True)
        self.generate=QPushButton('Generate Underbase'); self.compare=QPushButton('Compare Modes'); self.proof=QPushButton('Garment Proof'); self.export=QPushButton('Export Underbase Set'); self.report=QPushButton('Save Report')
        form=QFormLayout(); rr=QHBoxLayout(); rr.addWidget(self.source,1); rr.addWidget(self.open); form.addRow('Artwork',rr)
        for label,w in [('Mode',self.mode),('Threshold',self.threshold),('Strength %',self.strength),('Choke px',self.choke),('Spread px',self.spread),('Highlight protection',self.highlight),('Smooth px',self.smooth),('Output DPI',self.dpi),('Garment',self.garment)]: form.addRow(label,w)
        row=QHBoxLayout(); [row.addWidget(x) for x in (self.generate,self.compare,self.proof,self.export,self.report)]; row.addStretch()
        split=QSplitter(Qt.Horizontal); split.addWidget(self.preview_label); split.addWidget(self.info); split.setStretchFactor(0,2); split.setStretchFactor(1,1)
        lay=QVBoxLayout(self); lay.addLayout(form); lay.addLayout(row); lay.addWidget(split,1)
        self.open.clicked.connect(self.pick); self.generate.clicked.connect(self.do_generate); self.compare.clicked.connect(self.do_compare); self.proof.clicked.connect(self.do_proof); self.export.clicked.connect(self.do_export); self.report.clicked.connect(self.save_report)
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,'Choose Artwork','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if p:
            self.source.setText(p); self.im=load_image(p); self.items=[]; self.show(self.im); self.info.setPlainText(f'Loaded {Path(p).name}\nSize: {self.im.width} × {self.im.height}')
    def settings(self): return {'threshold':self.threshold.value(),'strength':self.strength.value(),'choke':self.choke.value(),'spread':self.spread.value(),'highlight_protection':self.highlight.value(),'smooth':self.smooth.value()}
    def show(self,im): self.preview_label.setPixmap(to_qpixmap(preview_image(im,(700,500))).scaled(self.preview_label.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
    def current(self):
        if self.im is None: QMessageBox.warning(self,'Underbase','Choose artwork first.'); return None
        return build_underbase_v35(self.im,self.mode.currentText(),**self.settings())
    def do_generate(self):
        m=self.current()
        if m is None:return
        self.items=[{'mode':self.mode.currentText(),'mask':m,'stats':underbase_coverage(m)}]; self.show(preview_underbase(self.im,m,self.garment.currentText())); self.info.setPlainText(json.dumps(underbase_report(self.items,self.garment.currentText(),self.settings()),indent=2,ensure_ascii=False))
    def do_compare(self):
        if self.im is None: QMessageBox.warning(self,'Compare','Choose artwork first.'); return
        self.items=compare_underbases(self.im,['adaptive','solid','luma'],self.settings());
        lines=[f"{x['mode']}: mean {x['stats']['mean_coverage_pct']}% • solid {x['stats']['solid_coverage_pct']}%" for x in self.items]
        self.info.setPlainText('\n'.join(lines)+'\n\n'+json.dumps(underbase_report(self.items,self.garment.currentText(),self.settings()),indent=2,ensure_ascii=False))
        self.show(preview_underbase(self.im,self.items[0]['mask'],self.garment.currentText()))
    def do_proof(self):
        m=self.current()
        if m is None:return
        self.show(preview_underbase(self.im,m,self.garment.currentText())); self.info.setPlainText(json.dumps({'garment':self.garment.currentText(),'coverage':underbase_coverage(m),'note':'Garment proof is a visual preview.'},indent=2))
    def do_export(self):
        if self.im is None: QMessageBox.warning(self,'Export','Choose artwork first.'); return
        out=QFileDialog.getExistingDirectory(self,'Choose Underbase Output Folder')
        if not out:return
        try:
            items,rep=export_underbase_set(self.im,['adaptive','solid','luma'],out,self.garment.currentText(),self.settings(),self.dpi.value()); self.items=items; self.info.setPlainText(json.dumps(rep,indent=2,ensure_ascii=False)); self.status_text(f'Exported underbase set to {out}')
        except Exception as e: QMessageBox.critical(self,'Export',str(e))
    def status_text(self,t): self.info.append('\n'+t)
    def save_report(self):
        if not self.items:self.do_generate()
        if not self.items:return
        p,_=QFileDialog.getSaveFileName(self,'Save V35 Underbase Report','underbase_v35.json','JSON (*.json)')
        if p: Path(p).write_text(json.dumps(underbase_report(self.items,self.garment.currentText(),self.settings()),indent=2,ensure_ascii=False),encoding='utf-8')


class ReconstructionLabV36Tab(QWidget):
    """Smart cleanup/reconstruction lab. Heuristic image processing, not generative AI."""
    def __init__(self):
        super().__init__(); self.im=None; self.result=None
        self.source=QLineEdit(); self.open=QPushButton('Open Artwork')
        self.shadow=QSpinBox(); self.shadow.setRange(0,100); self.shadow.setValue(65)
        self.blur=QSpinBox(); self.blur.setRange(3,151); self.blur.setSingleStep(2); self.blur.setValue(35)
        self.texture=QSpinBox(); self.texture.setRange(0,100); self.texture.setValue(80)
        self.sat=QSpinBox(); self.sat.setRange(-50,50); self.sat.setValue(5)
        self.contrast=QSpinBox(); self.contrast.setRange(-30,50); self.contrast.setValue(3)
        self.warmth=QSpinBox(); self.warmth.setRange(-30,30); self.warmth.setValue(0)
        self.edge=QDoubleSpinBox(); self.edge.setRange(.3,4); self.edge.setValue(1.2); self.edge.setDecimals(1)
        self.crop=QCheckBox('Crop to detected print area'); self.crop.setChecked(False)
        self.dpi=QSpinBox(); self.dpi.setRange(72,1200); self.dpi.setValue(300)
        self.before=QLabel('Open artwork'); self.before.setAlignment(Qt.AlignCenter); self.before.setMinimumHeight(360)
        self.after=QLabel('Processed preview'); self.after.setAlignment(Qt.AlignCenter); self.after.setMinimumHeight(360)
        for x in (self.before,self.after): x.setStyleSheet('background:#111;border:1px solid #333;border-radius:10px;color:#777')
        self.info=QTextEdit(); self.info.setReadOnly(True)
        self.run=QPushButton('Reconstruct / Cleanup'); self.compare=QPushButton('Before / After Report'); self.export=QPushButton('Export Result'); self.save=QPushButton('Save Report')
        form=QFormLayout(); rr=QHBoxLayout(); rr.addWidget(self.source,1); rr.addWidget(self.open); form.addRow('Artwork',rr)
        for label,w in [('Shadow correction %',self.shadow),('Illumination blur px',self.blur),('Texture preserve %',self.texture),('Saturation',self.sat),('Contrast',self.contrast),('Warmth',self.warmth),('Edge repair radius',self.edge),('Output DPI',self.dpi)]: form.addRow(label,w)
        form.addRow('',self.crop)
        row=QHBoxLayout(); [row.addWidget(x) for x in (self.run,self.compare,self.export,self.save)]; row.addStretch()
        imgs=QSplitter(Qt.Horizontal); imgs.addWidget(self.before); imgs.addWidget(self.after); imgs.setStretchFactor(0,1); imgs.setStretchFactor(1,1)
        split=QSplitter(Qt.Horizontal); split.addWidget(imgs); split.addWidget(self.info); split.setStretchFactor(0,2); split.setStretchFactor(1,1)
        lay=QVBoxLayout(self); lay.addLayout(form); lay.addLayout(row); lay.addWidget(split,1)
        self.open.clicked.connect(self.pick); self.run.clicked.connect(self.do_run); self.compare.clicked.connect(self.do_compare); self.export.clicked.connect(self.do_export); self.save.clicked.connect(self.save_report)
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,'Choose Artwork','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if p:
            self.source.setText(p); self.im=load_image(p); self.result=None; self.show_img(self.before,self.im); self.after.clear(); self.info.setPlainText(f'Loaded {Path(p).name}\nSize: {self.im.width} × {self.im.height}')
    def settings(self): return {'shadow_strength':self.shadow.value(),'blur_radius':self.blur.value(),'texture_preserve':self.texture.value(),'saturation':self.sat.value(),'contrast':self.contrast.value(),'warmth':self.warmth.value(),'edge_radius':self.edge.value(),'crop_to_print_area':self.crop.isChecked()}
    def show_img(self,label,im): label.setPixmap(to_qpixmap(preview_image(im,(700,500))).scaled(label.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
    def do_run(self):
        if self.im is None: QMessageBox.warning(self,'V36 Reconstruction','Choose artwork first.'); return
        try:
            self.result=reconstruct_v36(self.im,**self.settings()); self.show_img(self.after,self.result); self.info.setPlainText(json.dumps(reconstruction_report(self.im,self.result,self.settings()),indent=2,ensure_ascii=False))
        except Exception as e: QMessageBox.critical(self,'Reconstruction',str(e))
    def do_compare(self):
        self.do_run()
        if self.im is not None and self.result is not None:
            st=difference_stats(self.im,self.result); self.info.append('\n\nBefore → After difference\n'+json.dumps(st,indent=2))
    def do_export(self):
        if self.im is None: QMessageBox.warning(self,'Export','Choose artwork first.'); return
        if self.result is None: self.do_run()
        if self.result is None:return
        p,_=QFileDialog.getSaveFileName(self,'Export V36 Result','reconstructed_v36.png','PNG (*.png);;TIFF (*.tif *.tiff)')
        if not p:return
        try:
            if p.lower().endswith(('.tif','.tiff')): self.result.save(p,'TIFF',compression='tiff_lzw',dpi=(self.dpi.value(),self.dpi.value()))
            else: self.result.save(p,'PNG',dpi=(self.dpi.value(),self.dpi.value()))
            rep=export_reconstruction(self.im,self.result,p,self.settings(),self.dpi.value()); self.info.setPlainText(json.dumps(rep,indent=2,ensure_ascii=False))
        except Exception as e: QMessageBox.critical(self,'Export',str(e))
    def save_report(self):
        if self.im is None: QMessageBox.warning(self,'Report','Choose artwork first.'); return
        if self.result is None: self.do_run()
        if self.result is None:return
        p,_=QFileDialog.getSaveFileName(self,'Save V36 Reconstruction Report','reconstruction_v36.json','JSON (*.json)')
        if p: Path(p).write_text(json.dumps(reconstruction_report(self.im,self.result,self.settings()),indent=2,ensure_ascii=False),encoding='utf-8')


class Main(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle(APP_NAME);self.resize(1450,900)
        self.setStyleSheet("""
        QWidget{background:#0b0b0d;color:#eee;font-size:14px}
        QTabWidget::pane{border:1px solid #28282f}
        QTabBar::tab{background:#151519;padding:12px 16px;border-radius:8px;margin:2px}
        QTabBar::tab:selected{background:#f0c400;color:#111}
        QPushButton{background:#202027;border:1px solid #34343d;padding:10px 15px;border-radius:8px}
        QPushButton:hover{background:#2b2b34}
        QSpinBox,QComboBox{background:#151519;border:1px solid #34343d;padding:6px}
        QListWidget{background:#121216;border:1px solid #29292f}
        """)
        tabs=QTabWidget()
        tabs.addTab(CutoutTab(),"✂ Cutout")
        tabs.addTab(CleanupTab(),"🧹 Cleanup")
        tabs.addTab(MockupTab(),"👕 Mockup → Flat")
        tabs.addTab(EnhanceTab(),"✨ Enhance")
        tabs.addTab(SeparationTab(),"🎨 Professional Separation")
        tabs.addTab(BatchTab(),"📦 Batch")
        tabs.addTab(MockupFlatTab(),"👕 Mockup → Flat")
        tabs.addTab(DewarpTab(),"📐 Dewarp")
        tabs.addTab(ProductionRunnerTab(),"🚀 Run Production")
        tabs.addTab(PrintSheetTab(),"🧩 Print Sheet / Gang")
        tabs.addTab(GangPackTab(),"🧬 Multi-Design Auto Pack")
        tabs.addTab(ProductionValidationTab(),"✅ Preflight / Job Manager")
        self.queue_tab=BatchProductionTab(); tabs.addTab(self.queue_tab,"🗂️ Production Queue")
        tabs.addTab(ProductionDashboardTab(),"📊 V25 Dashboard")
        self.workspace_tab=ProductionWorkspaceTab(); tabs.addTab(self.workspace_tab,"🧰 V29 Production Workspace")
        tabs.addTab(OutputCenterTab(),"📤 V30 Output Center")
        tabs.addTab(PrintIntelligenceTab(),"🧠 V31 Print Intelligence")
        tabs.addTab(ColorLabTab(),"🎨 V32 Color & Separation Lab")
        tabs.addTab(SeparationLabV33Tab(),"🧪 V33 Advanced Separation Lab")
        tabs.addTab(HalftoneFilmV34Tab(),"🎞️ V34 Halftone & Film Lab")
        tabs.addTab(UnderbaseLabV35Tab(),"⚪ V35 Underbase & Dark Garment")
        tabs.addTab(ReconstructionLabV36Tab(),"🧽 V36 Smart Cleanup & Reconstruction")
        self.library_tab=ArtworkLibraryTab(); tabs.addTab(self.library_tab,"🗃️ V28 Smart Artwork Library")
        self.library_tab.queue_handoff.connect(self.queue_tab.import_library_jobs)
        self.workspace_tab.queue_handoff.connect(self.queue_tab.import_library_jobs)
        self.setCentralWidget(tabs)

if __name__=="__main__":
    app=QApplication(sys.argv);w=Main();w.show();sys.exit(app.exec())
