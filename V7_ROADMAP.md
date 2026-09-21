# V7 roadmap / architecture

## Implemented foundation
- Modular optional AI backend (`ai_backends.py`)
- Production utilities for registration marks, mask cropping, ink density and estimated ink area
- Optional rembg installation script

## Next production-grade modules
1. AI subject segmentation with edge refinement.
2. AI garment segmentation and artwork extraction.
3. Perspective/dewarp from shirt mockups.
4. Layer reconstruction for hidden/wrinkled artwork.
5. Real super-resolution backend.
6. ICC profile import and proofing.
7. LAB/Delta-E color matching with user-selected spot colors.
8. Calibrated rotated halftone screening and dot-gain curves.
9. Underbase choke/spread/trapping presets by garment color.
10. PSD/TIFF/SVG/PNG export pipeline.
11. Project history, presets, undo/redo, batch queue.
12. GPU job management and progress/cancel.
13. Print-sheet layout with registration marks.
14. Production report with channel coverage and estimated ink area.

## Safety/accuracy note
Screen-print separations are press-dependent. Any production result should be
validated against the user's actual ink, mesh count, emulsion, exposure, garment,
press and color-management setup.
