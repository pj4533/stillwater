# Release media

All included media is original Stillwater UI. No hardware/product photograph,
stock Ableton graphics, user recording or private operational screenshot is
included. The earlier private social edit used an Ableton product photograph
without an established redistribution license; it is deliberately omitted.

| File in `docs/media/` | Provenance |
|---|---|
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
acceptance. The GIF comes entirely from fresh synthetic state; no device film
or personal recording was used.

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
