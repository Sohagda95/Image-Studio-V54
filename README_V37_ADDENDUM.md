# V37 Addendum

V37 adds an AI-reconstruction-ready workflow while keeping dependencies light. The application detects whether OpenCV is available and uses Telea/Navier-Stokes classical inpainting when possible; otherwise it uses a deterministic texture-fill fallback. Users can load a custom repair mask or generate a broad-shadow candidate mask automatically.

Reports include a heuristic confidence score. It is a diagnostic metric, not a probability and not a substitute for human inspection.
