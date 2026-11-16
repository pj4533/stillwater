# Release media

Included media comprises original Stillwater UI and an original generated brand
banner. No hardware/product photograph,
stock Ableton graphics, user recording or private operational screenshot is
included. The earlier private social edit used an Ableton product photograph
without an established redistribution license; it is deliberately omitted.

| File in `docs/media/` | Provenance |
|---|---|
| `stillwater-banner.png` | Original AI-generated masthead, not device UI or a hardware photograph; [tool and exact prompt](BANNER.md) |
| `v5-device-silt.png` | Actual V5 pixels transmitted to Push in an isolated synthetic/master-zero test; mixed settings |
| `v5-device-prism.gif` | Actual V5 transmitted frames; fixed mixed controls, native-energy material motion; silent |
| `v5-device-range.png` | Actual V5 all-role zero/middle/full/mixed contact sheet from the same synthetic test |
| `v4-device-prism.png` | Actual pixels sent to Push during the V4 isolated scripted acceptance; mixed macro ranges, master zero |
| `v4-device-key.png` | Same device test; draft key selection |
| `v4-device-recordings-off.png` | Same device test; explicit film controls, capture off |
| `v4-device-library.png` | Same device test; generated test snapshot, not a user's library |
| `v4-prism.gif` | Local synthetic production renderer and real native DSP telemetry; fixed 50% macros, playback then Stop; silent |

The device test used a disposable copied home, then constructed synthetic
all-role material for its display checks. Selected images show only that test
state: no personal title, user performance, path, device address, key or account
identity. PNGs were re-encoded as plain RGB without inherited metadata. They
are display captures, not camera images, hardware composites or physical-pad
acceptance. The V4 GIF comes from fresh synthetic state; V5 GIF frames are actual
transmitted device buffers. No private film or personal recording was used.

To regenerate the synthetic preview after building/installing development tools:

```sh
python3 scripts/preview-v4.py
python3 scripts/curate-preview.py
```

`preview-v4.py` writes native 960×160 images, 0/25/50/75/100 range sheets,
manager screens and eight 10-second fixed-macro GIFs under `.build/v4-preview/`.
`curate-preview.py` strips metadata and optimizes the Prism GIF into docs/media.
Actual hardware screenshots are intentionally retained as curated evidence;
regenerating those requires a separately authorized hardware test, not this script.

Current V5 synthetic previews are reproduced with `python3 scripts/preview-v5.py`
under `.build/v5-preview/`. These are clearly distinct from the curated actual
Push captures. V4 images remain historical controls/media evidence. The V5
reference attachment and private photo-based social film are not distributed.
