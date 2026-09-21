# V37 — AI Artwork Reconstruction Lab

## Added
- Optional reconstruction backend abstraction.
- OpenCV Telea / Navier-Stokes classical inpainting when OpenCV is installed.
- Deterministic texture-fill fallback using Pillow.
- Auto shadow-mask heuristic for broad dark regions.
- External repair-mask loading.
- Mask expansion and feathering.
- Repair result, mask and JSON diagnostic export.
- Heuristic repair confidence metric with explicit limitations.
- Dedicated V37 tab.

## Accuracy note
This release does **not** bundle or claim a generative AI inpainting model. OpenCV is classical inpainting and the fallback is deterministic image processing. The architecture is ready for a future optional model adapter without pretending a model is installed.
