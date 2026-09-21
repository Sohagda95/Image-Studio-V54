# V18 — Artwork Reconstruction
Added:
- Automatic print-area detection heuristic
- Print-area coverage estimate
- Low-frequency shadow/lighting correction for reconstruction
- Optional Real-ESRGAN integration point with Lanczos fallback
- Dedicated V18 Reconstruction menu

Important:
Automatic print-area detection and reconstruction are heuristic. Real garment-aware
reconstruction needs a trained segmentation/dewarping model and should be validated visually.

Next:
- Connect reconstruction directly to Mockup → Flat
- AI garment segmentation + wrinkle-aware reconstruction
- True model-backed super-resolution packaging
- Separation handoff with preserved alpha and project metadata
- Production queue with worker threads and cancel
