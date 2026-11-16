# Coding-agent guide

Read README and docs/ARCHITECTURE.md, DEVELOPMENT.md, CONTROLS.md and INSTALL.md
before editing or touching hardware. This standalone Linux/Python/C checkout
needs no parent repository, private agent runtime or credential broker.

## Ownership/invariants

Entry: src/app.py→loop_app.py. Model/writer: loop_model.py. Native admission:
loop_engine.py/loop_native.h. DSP: loop_dsp.h/engine.c. Renderer: loop_graphics.py.
Hardware/parser: hardware.py/midi.py. Service ownership: scripts/supervisor.py,
process.py/recovery.py. Preserve other contributors' work. A visual change must
not alter boot/audio ownership. Never add network listeners or delete music.

Sample callback stays bounded/allocation-free. Commands admit atomically before
model mutation; preserve note-off order/capture credits. Banks and scalars share
queue order. Epochs prevent delayed captures resurrecting Undo. Native capture
retention is independent of acknowledgment consumption. Latest accepted tokens
and revision/pending guards protect load/New. No UI fsync or false SAVED status.
Effects/levels/master apply smoothly once to held/tail audio.

## Validation

Run `sh scripts/build.sh` then `python3 -m unittest discover -s tests -v`.
Install development requirements/host FFmpeg as documented. For integration,
DSP or media changes run memory-only `python3 scripts/rehearse-v3.py`; measure
relevant macro/timing/drain scripts. Report exact counts, architecture and codec
alignment tolerances; never claim human listening from PCM checks. Cross-build
`sh scripts/build.sh device` with Zig0.13.0 for paired source/native hardware
review. Do not deploy host ARM binaries to x86_64 Push. Avoid repeating broad
checks without new changes/failures.

Graphics needs native960×160 production screenshots and an active-animation
GIF. Text remains last/readable; no flashes, strobes or per-frame fsync. Pillow
is offline only. Curated assets/*.bin, .poses and .working are packed image data; .build is disposable.
V3 length changes require guarded native boundary acknowledgment before history
commit. Preserve whole-window key normalization and onset-owned recording. Ship
all V2 backgrounds and V3 pose/working assets with matching ABI3 source/native.

## Hardware/deployment

Use verified CC map in ARCHITECTURE, never guess. All64pads stay notes; no second
MIDI reader. Quiet tests use memory PCM or copied sessions/master zero. Preserve
player master, sessions/history/recordings. No unattended notes, surprise level
increase, firmware reset or vendor-file deletion.

Hardware changes require explicit authorization and a quiet window. Read INSTALL
fully. Back up source/native/scripts/current state and original stock privately;
gracefully stop and prove all old owners dead; stage paired update, atomically
rename native engine; verify hashes, ready/ALSA/display counters, one app and
supervisor, stopped transport and no xruns/errors for at least60s. Reboot tests
need a saved checkpoint and explicit authorization. Blocked ownership means stop,
retain registry evidence; never erase it to bypass a gate. No reboot repetition
for view-only changes. Failure never automatically starts stock; preserve bounded
quiet retries and separate minimal audio-free recovery.

## Privacy/licensing

Do not commit keys, device identity/addresses, user songs/history/recordings,
private logs/backups or vendor binaries/scripts. Keep .gitignore broad and media
curated/synthetic. Never import private repository history. Preserve MIT/Push Hack
notices and AI-art provenance. Exact file/commit/license review is required for
new third-party DSP. FFmpeg is separately obtained under its own license.
External agents use the Unix socket in AGENT_API, not an onboard model/voice
system. Query first, serialize, honor backpressure, keep actions reversible/quiet.
Commit verified work; publication and deployment are separate explicit actions.
