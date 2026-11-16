# Sanitized standalone snapshot

This checkout was prepared as a selective source snapshot. Existing public
README/license history is preserved; no private development repository history
was imported. New commits use a public no-reply identity. Publication is separate
from preparation and requires an independent privacy/license review.

## Included and omitted

Included: complete production Python/C source, ownership/recovery scripts,
standalone build/preparation tools, regression tests/fake native fixtures,
original generated art and prepared image caches, adapted public documentation,
MIT/Push Hack notices, and curated synthetic-renderer screenshots/GIF.

Omitted: personal handoffs/conversations, private research inventories, deployment
logs and device evidence, addresses/keys/host configuration, all user
sessions/history/music/media, recovery backups, vendor stock scripts/binaries and
firmware, product photos/social-edit tools, downloaded encoders, executable build
artifacts, cache and private repository history. Legacy code/tests/art remain
because shared infrastructure and regression coverage still use them; the default
runtime entry is V2. No legacy user music is included or converted automatically.

The broad .gitignore protects normal local credentials/state/build/media paths;
it is not a substitute for reviewing every staged file.

## Validation of this snapshot

- Strict local C11 build passed (`sh scripts/build.sh`).
- All210existing unit/native tests passed in22.707s; two added fresh-payload safety
  tests passed in0.004s (runtime-only selection/refusal to overwrite existing state,
  and rejection of incomplete encoder bundles before creating a destination).
- `python3 scripts/rehearse-v2.py`:25production-workflow checks passed on the
  build host, without hardware/audio output. Eight roles, persistence/undo/library,
  stopped silence, actual film and exact-loop WAV were exercised.
- Film:65seconds,650frames,960×160at10fps, H.264/AAC stereo44100Hz. Decoded AAC
  lag0samples at2/32/64seconds; correlations0.999365/0.999505/0.999483.
  The32-second loop export is1411200stereo frames and sample-exact.
- Actual default-entry offline smoke passed: ready, real mode0600 Unix-socket
  status, stopped transport, SIGTERM exit0 and ready removal. First attempt on a
  shared bind mount could not chmod the socket; corrected run on local Linux
  filesystem passed. No production code change was needed for that limitation.
-19local Markdown links checked, zero missing targets (external URLs are source
  references, not a claim of availability forever).
- Recursive text audit found zero private absolute paths/network addresses,
  credential patterns, personal email addresses or private handoff identifiers.
  Image metadata audit found no EXIF/comments/author/XMP fields. Compressed image
  data was excluded from email matching to avoid random-byte false positives;
  source images are original generated artwork. Audits are heuristic, not a
  security certification; an independent review is still required.

The [manifest](export-manifest.json) lists106curated files (excluding this report
and the manifest itself), with sizes and SHA256. It contains no parent history
reference or private source paths. Build outputs/test logs remain ignored.

## Intentional portability adjustments

`build.sh` resolves Zig from PATH or `ZIG`, rather than a private build-host path.
The V2 art converter reads bundled originals and fails clearly if one is missing,
rather than searching a private generation cache. New `prepare-home.py` creates
only a fresh runtime payload and refuses an existing destination. Production
source/native behavior is otherwise unchanged by the export. Installation remains
an explicit, reviewed hardware procedure, not an unattended installer.

## Licenses

Original source/art: repository MIT. Adapted hardware protocol: Federico Pepe MIT,
full LICENSE.push-hack and NOTICE retained. No third-party DSP kernels copied.
FFmpeg/ffprobe are excluded; optional pinned download uses its GPL license and
separate source/build provenance. Python/system ALSA/libc/Pillow/build tools are
external dependencies under their own upstream terms; see CREDITS and INSTALL.
