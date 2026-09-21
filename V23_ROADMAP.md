# Image Studio V23 — Production Validation & Job Management

## Added
- Artwork inspection with dimensions, embedded DPI, alpha presence, transparent bbox and SHA-256.
- Duplicate artwork detection.
- Preflight validation for artwork and gang-sheet settings.
- Saved/loaded production presets.
- JSON production report and ZIP job package helpers.
- Batch-oriented validation foundation.

## Accuracy note
DPI embedded in a file is metadata and is not proof of true image detail. Size-at-DPI calculations are mathematical estimates. Packing remains rectangle/bounding-box based rather than contour nesting.
