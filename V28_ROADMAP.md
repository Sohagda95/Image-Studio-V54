# V28 — Library ↔ Production Workspace

Implemented:
- Direct Artwork Library → Production Queue handoff via Qt signal.
- Drag-and-drop image files into the Production Queue.
- Reusable production presets with auto-apply.
- Save/load production queue JSON.
- Save/load production template JSON.
- Queue items inherit preset settings without overwriting explicit existing settings unless Apply Preset is used.
- Basic per-job size/DPI estimate helper.
- V27 library, V25 dashboard, V24 queue and all earlier production modules retained.

Notes:
- Presets are engineering workflow presets, not calibrated RIP/ICC profiles.
- Queue remains sequential and uses the existing V25 ProductionQueueManager.
