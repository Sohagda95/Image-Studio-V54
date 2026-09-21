# V24 Roadmap / Release Notes

## Added
- Multi-job Production Queue.
- Sequential threaded production processing.
- Pause / Resume at production step boundaries.
- Cancel queue safely.
- Per-job output folders and ZIP packages.
- Per-job completion/error/cancel status.
- Persistent `job_history.json` in queue output root.
- Current-session job history table.
- Job reorder/remove/clear controls.
- Reuses V20 production engine and all V21-V23 workflows.

## Accuracy note
Pause/resume is cooperative: it pauses between production steps and progress callbacks rather than interrupting a Pillow operation in the middle of a single image-processing call.
