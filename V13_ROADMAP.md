# V13
Added:
- Channel-file export pipeline
- PNG film/channel files with 300 DPI metadata
- Screen-angle presets
- Separation manifest JSON
- Batch export queue with progress status

Current limitation:
The current UI export treats the loaded artwork as one channel. The next integration will
connect the Professional Separation tab's actual spot/CMYK channel images into this export
pipeline, then generate multi-film sheets with registration marks.

Next:
- Connect real Spot/CMYK separation outputs
- Multi-channel film sheet export
- Interactive dewarp canvas
- Mockup artwork segmentation
- Queue cancel button and threaded execution
