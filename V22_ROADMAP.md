# Image Studio V22 — Multi-Design Auto Pack

## Added
- Mixed-design gang-sheet packing with per-design quantity and target width.
- Transparent/alpha margin trimming before packing.
- Optional 90° rotation per design.
- Automatic multi-page packing when the sheet cannot fit all copies.
- Utilization and rectangular waste estimate per page.
- 300 DPI PNG gang-sheet export with JSON manifest.
- Center registration marks and labels.
- Persistent JSON job queue for repeatable gang-sheet jobs.

## Accuracy note
The V22 packer is deterministic rectangle/bounding-box nesting after transparent-margin trimming. It is not polygon/contour nesting and does not claim press/RIP-calibrated output. Validate final dimensions and production marks against the actual RIP/press workflow.
