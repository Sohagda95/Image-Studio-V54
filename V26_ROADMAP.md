# V26 — Smart Artwork Library

- Searchable artwork library with thumbnails
- Recursive folder scanning and multi-file import
- Favorites
- Exact SHA-256 duplicate detection
- Same perceptual aHash grouping for near-duplicate candidates
- Dimensions, DPI, alpha, format and file-size metadata
- Save/load library JSON
- Export machine-readable library report
- Open selected artwork and copy its source path

Near-duplicate detection is intentionally conservative: identical aHash values are grouped as candidates; it is not a semantic image-matching model.
