# V30 — Output / Export Center

Centralized export workflow for artwork production.

## Added
- Master PNG/TIFF export at selected DPI.
- Transparent-margin trimming.
- Spot/CMYK preview/engineering channel export.
- Optional underbase export with choke.
- Optional rotated halftone previews.
- Channel contact sheet.
- Production manifest JSON.
- Preflight information in manifest.
- Organized per-job output directory.
- Optional production ZIP package.
- Safe output/job naming.

## Accuracy note
Spot/CMYK conversion, underbase and halftone outputs reuse the application's existing preview/engineering algorithms. They are not a calibrated ICC/RIP replacement.
