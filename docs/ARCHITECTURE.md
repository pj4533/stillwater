# Architecture and invariants

`src/app.py` launches `loop_app.py` by default. One app owns the ALSA engine,
MIDI reader, USB display, Unix IPC socket and film/export workers. Legacy classes
remain for shared infrastructure/regression tests; V2 never silently imports an
old step song. The supervisor starts one app or audio-free recovery child under
a singleton lock and PID/start-identity registry. No onboard inference process,
voice listener or network server exists.

| Files | Responsibility |
|---|---|
| `loop_model.py` | Frozen song/layer/event model, validation, bounded undo/redo, async persistence/library |
| `loop_engine.py` | ctypes ABI, bank publication, manual admission, native acknowledgments |
| `engine.c`, `loop_native.h` | ALSA/history, sample-timed transport, ordered commands and scheduler |
| `loop_dsp.h`, `roles.py` | Eight original sources/buses, ranges and macro labels |
| `loop_graphics.py`, `graphics.py` | Role scenes, registered material animation, typography/canvas |
| `hardware.py`, `midi.py` | usbfs display, named raw MIDI, parsing/receipt observation/backpressure |
| `recorder.py`, `loop_export.py`, `bottle.py` | Film, next-loop streaming WAV, retrospective capture |
| `scripts/supervisor.py`, `process.py`, `recovery.py` | Exclusive ownership, bounded retries, minimal recovery |

## Audio and state

Audio is 44100Hz/256-frame blocks (5.805ms deadline). Typed commands share one
bounded ordered native queue: scalar master/tempo cannot overtake bank publication.
Complete immutable banks use fixed mailboxes. Publication rejects atomically if
retained native captures plus active reservations do not fit. Retained capture
state is independent of acknowledgment consumption. No allocation/filesystem work
belongs in the sample callback. Measure worst-case actual device timing, including
publication/capture, before making a CPU claim.

First-note anchoring starts an empty armed loop; existing songs start phase zero.
Native sample time captures duration/velocity/gates. Capture intent belongs to each
note onset: toggling overdub later does not change held-note intent. Undo/deletion
advances capture epoch; delayed completions cannot resurrect notes. Empty redo is
a no-op. Admission precedes model mutation; backpressure never loses note-off.
The MIDI dispatcher observes fresh Settings receipt while draining ordered bounded
backlog, preventing a released button becoming a false long hold.

All64pads stay in D Dorian; octave shifts the complete window. Pressure uses the
manual voice token, not a global layer parameter. Eight manual voices,64global
playback voices, eight brief steal tails and256events/layer bound work. Macros
smooth continuously on held/tail sources and buses; layer gain applies once
post-bus, followed by smoothed mute/master and output limiting.

`sessions/current-v2.json` holds independent schema/history. Only validated legacy
master is inherited initially; old current/journal bytes remain intact. Undo/redo
share64snapshots. A coalescing one-slot autosave worker and bounded jobs keep
serialization/fsync off input handling; dirty/durable revisions and errors are
truthful. Snapshots use generated no-overwrite names. Load/New archives before
replacement and uses a monotonic accepted-request token plus revision/pending
checks. Playing/editing cancels replacement. Shutdown silences before bounded
persistence/media finalization.

## Media/display

BGR565 scenes have1024pixel stride/960×160visible. Native envelope/onset/FX
telemetry animates registered material; typography draws last over authored quiet
areas. Target10fps; no runtime Pillow, per-frame fsync, global pulses or strobes.
Film spools actual frames/post-limiter stereo history then encodes on a worker.
Exact-loop export streams the next complete boundary interval in chunks from the
45-second history; it creates no second audio engine. Activity/epoch/xrun guards
cancel changed takes; view-only changes are allowed. Output/sidecar files never
overwrite previous files. No microphone/input-audio recording exists.

## Hardware protocol

Tested display VID/PID`2982:1969`, usbfs bulk endpoint1,16-byte header beginning
`ff cc aa 88`, XOR framing and duplicated packed-image transfers. See NOTICE for
MIT Push Hack adaptation. MIDI discovery uses named `Live Port`, not a guessed
port number. Audio is `hw:A3,0` on the tested device; verify compatibility first.

CC map: screen encoders71–78, Volume79, Tempo14; select102–109, mute20–27;
Play85, Stop Clips29, New92, Note50, Session51, Mix112, Device110, Shift49,
Save82, Undo119, Record86, Help81, Settings30, arrows62/63. Pads36–99.
No calibrated full-MPE pitch/slide is assumed. Never open a competing MIDI reader.

Failure retains boot preference and uses bounded quiet retries. Prior PID/start
identities must all be dead before a new hardware child is gated open. Blocked
ownership fails closed and retains evidence. Explicit Settings or stock.sh
--disable are the deliberate stock escape; crashes never start competing stock
software. Hardware failure can prevent the recovery display itself.
