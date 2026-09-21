
from __future__ import annotations
from pathlib import Path
import json, zipfile, io, datetime
from PIL import Image

APP_VERSION = "V8"

def save_project(path, settings, source_path=None, preview_image=None):
    path = Path(path)
    manifest = {
        "format": "ImageStudioProject",
        "version": APP_VERSION,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "settings": settings,
        "source_name": Path(source_path).name if source_path else None,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        if preview_image is not None:
            buf = io.BytesIO()
            preview_image.save(buf, format="PNG")
            z.writestr("preview.png", buf.getvalue())

def load_project(path):
    with zipfile.ZipFile(path, "r") as z:
        data = json.loads(z.read("project.json").decode("utf-8"))
    return data

def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def make_production_report(source_image, separation_summary, settings, output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "application": "Image Studio",
        "version": APP_VERSION,
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": {
            "width_px": source_image.width,
            "height_px": source_image.height,
            "mode": source_image.mode,
        },
        "separation": separation_summary,
        "settings": settings,
        "notes": [
            "Preview/separation calculations are engineering approximations.",
            "Validate final output on the target RIP, ink set, mesh and substrate before production."
        ]
    }
    p = out / "production_report.json"
    write_json(p, report)
    return p
