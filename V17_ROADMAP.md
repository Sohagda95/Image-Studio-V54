# V17 — AI Artwork Foundation
Added:
- Optional rembg AI subject/garment cutout
- Soft-shadow removal helper
- Artwork contrast/sharpness cleanup
- White-balance correction
- Dedicated V17 AI Artwork Tools menu

AI note:
The segmentation backend is optional because model/runtime packages are large and may
require model download. The app keeps a non-AI workflow when it is unavailable.

Next:
- Automatic print-artwork boundary detection
- Wrinkle/shadow-aware artwork reconstruction
- AI upscaling backend
- Connect Mockup → Flat output directly to Separation
- Real per-channel underbase/halftone pipeline
