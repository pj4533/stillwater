# Sanitized standalone V3 snapshot

This checkout is a selective source snapshot. Existing public README/license
history is preserved; no parent repository history is imported. Commits use a
public no-reply identity. Publication remains separate from preparation and
requires an independent privacy/license review.

Included: complete production Python/C, ownership/recovery scripts, portable
build/fresh-payload tools, regression fixtures/tests, original generated artwork,
prepared V2 backgrounds and V3 material/working caches, adapted public docs,
MIT/Push Hack notices and curated synthetic production-renderer previews.

Omitted: personal handoffs/conversations, deployment logs/device evidence,
addresses/keys/host settings, all user sessions/history/music/media, recovery
backups, vendor stock scripts/binaries/firmware, downloaded encoders, executable
build artifacts and cache. Default runtime is V3. It imports a user's validated
V2 performed song only when current-v3 is absent; fresh songs start at one bar.
No existing user music is bundled. Existing V2 songs retain four bars and exact
notes/history/roles/parameters/master. Legacy step-song files stay untouched.

## Reproduction and payload

Build and full-suite instructions are in [DEVELOPMENT](DEVELOPMENT.md). The strict
host build uses C11 and `-Wall -Wextra -Werror`. The portable device build accepts
Zig from PATH/`ZIG` and uses the same strict flags with GNU2.35 x86_64 targeting.
The reviewed reference V3 native SHA256 is
`0090bb56e5ca9be4dbc621328ea8b72072522a0e353f5e211b25c21218026fde`.
A native ABI3 check precedes hardware/history startup.

The [runtime manifest](runtime-manifest.json) lists42core source/art hashes:
18source files, eight V2 backgrounds, eight V3 pose files and eight V3 working
backgrounds. `prepare-home.py` additionally copies shared/legacy renderer assets
and ownership/recovery scripts. It refuses an existing destination, excludes
cache and never imports sessions/recordings/recovery. A packaging regression
checks every core runtime hash and V3 asset size in a freshly prepared payload.
Optional FFmpeg tools must include ffmpeg/ffprobe/license/provenance together.
Python/system ALSA/utilities/build tools and FFmpeg are separately installed;
see [INSTALL](INSTALL.md) and [CREDITS](CREDITS.md). Pillow is build/preview only.

The [export manifest](export-manifest.json) records curated source-file sizes and
hashes, excluding itself. It contains no parent history identifiers or private
source paths. Build products/reports remain ignored.

## V3 production checks and previews

`rehearse-v3.py` exercises26workflow checks using production DSP/graphics,
persistence/library/New/Undo, a140second H.264/AAC film and sample-exact64second
32beat/30BPM WAV across45second history wrap. The legacy16beat V2 rehearsal
remains available. No ALSA/USB/MIDI device or speaker output is opened.

`docs/media/role-contact.png` shows current materials. Eight `*-fixed-audio.gif`
clips hold all macros at50%, followed by actual native playback and Stop/settle;
geometry remains visible while silent. They are synthetic renderer output, not
camera footage or human listening/visual acceptance. `preview-v3.py` regenerates
native960x160 low/high/silent/playing frames, knob sweeps and separate fixed-knob
clips under `.build/v3-preview/`.

The broad .gitignore protects routine local state/credentials, but is not a
substitute for staged-file review. New source or artwork requires privacy/license
review. Preserve original PNG provenance, MIT/Push Hack notices and independently
obtained encoder licenses; no third-party DSP kernels are copied here.

## Fresh archive validation

A Git archive of public candidate `aa05a635a11ba85ad5441a1433790bd4d3e425b2`,
extracted outside its original checkout, passed strict host build and all241tests
in23.784seconds, including three payload-safety/completeness tests. Its V3
production rehearsal passed26checks:1400film frames/6,174,000stereo PCM samples,
64second sample-exact WAV, zero xruns. Decoded AAC has zero-sample lag at2/64/128s
and correlation above.9988. These are offline build-host checks, not listening
approval or a claim about every device.

The standalone strict GNU2.35 x86_64 crossbuild passed with SHA256
`754e8100987252da366de3520b5cd37f3d27f769fc8eec1e6724973d9309e8c1`.
Its20allocated ELF sections are byte-identical to the reviewed reference binary;
Zig's embedded debug source/build paths account for the whole-file hash
difference. All18production source files and42core runtime source/art hashes
match the reference. The binary is not included in this repository/archive.

Local documentation link checks found25valid relative targets, zero missing.
Text-marker checks found no private absolute paths, deployment commit IDs,
personal handoff names or device addresses. An initial bare numeric marker
matched packed image-cache hex data; those pre-existing matches were inspected
as image bytes, not user-state metadata. Independent privacy/license review
remains required before publication; these checks are not a security audit.

Bundled-original V2 preparation followed by V3 preparation regenerated all42core
runtime hashes with zero mismatches. Image metadata checks found no EXIF, comment,
author or XMP fields in curated PNG/GIF media.
