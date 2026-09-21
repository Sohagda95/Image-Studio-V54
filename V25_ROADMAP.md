# V25 — Production Dashboard

Added a higher-level production control layer on top of V24.

- Production dashboard with live queue statistics.
- Queue JSON save/load.
- Reusable production template save/load.
- Mandatory per-job preflight gate (configurable DPI thresholds in dashboard).
- Retry failed/preflight-failed jobs from the last session.
- Per-job elapsed time, output file count and output size statistics.
- Persistent per-session queue JSON log.
- Pause/resume/cancel at production-step boundaries.
- Existing V24 queue and all earlier image/T-shirt workflows remain available.

Accuracy notes:
- Preflight validates metadata and measurable image properties; it does not prove visual print quality.
- Output-size statistics describe generated files, not ink consumption or press time.
- Color separation, underbase and halftone remain engineering/preview workflows unless calibrated to a specific RIP/ink/mesh/substrate/press setup.
