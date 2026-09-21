# V39 Roadmap — Text & Typography Production Lab

Implemented:
- Heuristic text-like region detection using OpenCV contours/thresholding.
- Optional pytesseract OCR diagnostics when installed.
- Typography safe-area and small-region checks.
- Text-region mask and expand/soften controls.
- Outline/region overlay preview.
- Conservative cleanup for print preparation.
- Export of cleaned artwork, text mask, overlay, and JSON report.

Limitations:
- Region detection is not semantic AI text detection.
- OCR does not identify the original font or recreate editable text.
- No proprietary font files are bundled.
- No claim of perfect text/vector reconstruction.
