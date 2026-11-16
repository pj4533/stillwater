# Standalone V5 release snapshot

This repository contains the complete distributable instrument, with its public
history, original branding and MIT/Push Hack notices. No private parent history
is imported. V5 replaces only instrument renderer/artwork; native ABI6, song
schema3 and versioned gentle sound remain unchanged.

Included: production Python/C, original material-control geometry, eight V5
scenes and pose banks, offline support atlases, reproducible generators/previews,
ownership/recovery scripts, portable builds and fresh payload preparation,
full tests/fixtures, public guides and curated synthetic/actual-test UI media.
Legacy source art remains for regeneration and shared regression code.

Excluded: device identity/addresses, keys/host identities, local configuration,
private feedback/reference attachments, operational logs, user songs/history,
recordings, backups, vendor software/firmware, downloaded encoders and native
executables. Ignore patterns complement complete tracked-content review.

## Reproduce

Follow [Development](DEVELOPMENT.md):

```sh
sh scripts/build.sh
python3 -m unittest discover -s tests -q
python3 scripts/rehearse-v5.py
python3 scripts/prepare-v5-art.py .build/v5-regenerated
# Optional full production preview:
python3 scripts/preview-v5.py
sh scripts/build.sh device
python3 scripts/stage-v5.py .build/payload --engine .build/engine-device.so
```

The36-check rehearsal verifies parser/native/render/worker integration, actual
V5 film pixels, strict H264/AAC decode, exact WAV frames/native samples, key,
library, persistence and Stop. Tests exhaustively check4,352 supported-motion
combinations. No hardware is opened. [V5 materials](V5_MATERIALS.md).

The [runtime manifest](runtime-manifest.json) lists46 core hashes:22 source files,
eight V5 scenes, eight V5 pose banks and eight V4 working pages. Packaging checks
verify every hash and cache size. `prepare-home.py`/`stage-v5.py` add shared legacy
assets and ownership/recovery scripts, omit inactive V4 poses and offline support
metadata, refuse an existing destination and never import personal state.

The reviewed deployed reference had92 files. All production source and active
art match that payload exactly. Public build/art/preview/rehearsal/staging tools
retain portable toolchain selection, bundled inputs and `.build/` outputs; private
editorial/device-smoke tools are omitted. Public staging uses this standalone
checkout rather than a private prior deployment manifest. The renderer preloads
one pose bank, never duplicate V4/V5 banks. The native engine is unchanged; public
cross-build allocated ELF sections match the deployed ABI6 reference. Its whole
file hash can differ with build paths. No compiled engine is committed.

The [export manifest](export-manifest.json) records sizes/hashes for the entire
curated tracked tree except itself. Fresh-export checks cover build, full tests,
rehearsal, payload and documentation/media links. Optional FFmpeg remains separate
under its own license/provenance. Automated checks do not establish human listening,
physical control feel or universal hardware compatibility.
