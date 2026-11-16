# Loop browser and saved-source identity — deployed 2026-11-16

LOOPS and RECORDINGS/SAVED use the large right navigation wheel: CC70 scroll,
CC93/95 one-row nudges. Scroll retains four-unit accumulation, idle/reversal
reset, one-row maximum per packet and endpoint clamping. Encoder1 no longer
browses; encoders1/2 still edit the rename cursor/character and KEY root/mode.
Wheel press94 and touch11 are consumed without loading, deleting or editing.
Confirmation and rename drafts pin the original target; wheel movement cannot
change them. Volume79 remains master; screen encoder8 remains78. Browsing,
touch and wheel press cannot cancel pending musical operations.

Mapping evidence: the complete [pinned Push3 encoder mapping](https://github.com/danielknng/push3-protocol-docs/blob/0d843cd69a7a0d2c52eddb46a57ea69fd0ddc2e5/docs/encoders.md)
was read, especially “Jog Wheel (Navigation Control)” and “Master Volume Knob”.
This is protocol/source evidence, not a claim of physical encoder acceptance.

LOOPS displays LOADED name + short saved-file ID separately from the selected
row. The current-v3 envelope accepts an optional validated `source` object:
controlled filename `id`, display `name`, Boolean `modified` and `deleted`.
Song schema3 and native ABI6 are unchanged. Old envelopes remain readable and
unnamed; no content matching guesses which snapshot they came from. The worker
returns the actual filename on successful load/save. Snapshot results are pinned
to the song and replacement generation so a late save cannot replace a newer
load/New identity. Metadata checkpoints increment durability revision without
adding musical Undo entries. Source names/deletions reconcile even after leaving
the manager, and startup checks the source sidecar/existence.

Any musical state edit, including master and Undo/Redo, conservatively marks the
source EDITED; autosave does not claim an exact saved-library match. Loading or
saving a new snapshot clears EDITED only for the state actually loaded/saved.
New clears provenance; Undo after New remains unnamed. Rename retains the file
identity. Deleting a source leaves its name/ID with DELETED, retaining current
music/history. Older code with strict envelope keys cannot read source-bearing
sessions: preserve current sessions and use this reader when rolling back UI.

# Overlapping scale pads and visible controls

This V5 follow-up uses paired native ABI6 with song schema3. Install source and
engine together; an ABI5 engine is rejected before opening audio. Saved music,
Undo/Redo, gentle sound versions and synthesis defaults are retained. Loading
existing songs does not transpose them. A song recorded outside MIDI24–96 will
be rejected by older builds: preserve newer music before rolling code back.

The restored overlapping grid advances one scale degree to the right and three
scale degrees up a row (a diatonic fourth). Its formula is
`column + 3*row - 14 + 7*octave`. D Dorian defaults span MIDI38–86,
29 distinct pitches across64pads; duplicates are intentional. The triangle
(row0,col0), (row0,col2), (row1,col1) plays scale degrees0,2,4 relative
to its first note: C/E/G in C major. Moving the shape gives diatonic triads.
Left/Right shifts the complete window only when every pitch fits MIDI0–127.
Playback lights every pad with the exact absolute pitch, including duplicate
positions. Octave counterparts remain distinct. Existing saved notes are unchanged.

Every globally actionable physical button has a resting light, including New,
Shift, Save, Undo, Stop Clips, Device, Settings and arrows. New brightens while
Shift is held. Record uses distinct red palette commands: inactive7, active5;
both remain lit. Manager lights follow their contextual actions, confirmation
and rename controls. Software checks establish emitted commands, not perceived
physical hue/brightness.

Pressure belongs to held manual voice tokens, including stopped audition. It
never records macro automation or changes a saved Tone value. Untargeted pressure
and encoder-touch notes no longer cancel pending operations. No arbitrary
encoder deadband or transport-based knob lock has been added: knobs still edit
while stopped, and valid held-note pressure still works. Encoder CC is accepted
only on channel0; zero rotation is a no-op. Two's-complement values1..63 and
64..127 retain their existing signed meaning. Stop clears pressure targets;
queued genuine encoder movement remains ordered input rather than automation.

The reported Spore Tone/SAVED oscillation has not been reproduced. A15second
trace of the existing device reader contained only power replies/active sensing,
no CC, pressure or notes. This observation does not establish its cause or prove
that it is fixed. Use the opt-in diagnostic during a reproduction:

```sh
python3 src/control.py '{"op":"input_diagnostic_start","seconds":30,"count":512}'
python3 src/control.py '{"op":"input_diagnostic_status"}'
```

Use the installed control socket as documented. The diagnostic runs within the
existing input owner, opens no second MIDI reader and never edits music. It is
bounded to30seconds/2048events, held only in memory, disabled by default, and
returns parsed input, transport, before/after revision and selected-layer macros.
It stops recording when either bound is reached. Capture a status query alongside
it for dirty/durable revisions. Private diagnostic output can contain musical
input and should not be published. It cannot distinguish a physical knob turn
from a synthetic local socket event, and pending native take completion may also
advance a revision during dispatch.

## Previous continuous-layout local validation (historical)

The channel0 guard covers both global CC dispatch and contextual KEY/Load
mutation classification. Nonzero-channel Apply cannot cancel a pending operation.
Private suite:292passed; standalone public suite:297passed, including11focused
control regressions and five portable payload tests. Host native build and strict
C11 x86_64 Zig0.13.0 device build passed. Production V5 rehearsal passed36checks
with real film/WAV/key/library operations. Six changed runtime modules match
between development and public checkout; all46 public runtime hashes match.

The selected public device binary is ABI6, SHA256
`48c9170127e616a422285aaf476c2e9c51700f1a390c4206722dd0ed41456ab0`.
The initial private build used different compiler flags and had a different hash;
staging uses the rebuilt strict public artifact. Device installation/health is
recorded separately after controlled rollout. These checks do not establish
physical hue or listening acceptance and do not resolve the unreproduced Tone
oscillation.

## Previous continuous-layout Push validation (historical)

The reviewed release `a4f62a4ca09377807c36322abf637eecbc5f04b0` is installed
with the ABI6 native hash above.92/92staged files matched on device. A disposable
master-zero session under the sole ALSA/MIDI/display owner passed85checks:
all64exact native pitches and emitted pad LEDs,19global action lights, distinct
Record7/5, Shift/New/contextual pages, stopped held Spore pressure, diagnostic
capture/expiry, and16seconds of stable stopped Spore macros/revision.
Normal supervision resumed with the existing saved music/history/media unchanged.
61samples over61.044seconds showed zero xruns/peak, stable clean saved revision,
and advancing audio/display counters. No second MIDI reader was opened.

An initial rollout attempt aborted before installation when the previous runtime
USB display returned ENOMEM during a large live backup and its supervisor
recovered. The retry verified the complete backup with the hardware owner stopped
and restored the original transient controls. This deployment procedure correction
does not explain the reported Spore Tone/SAVED oscillation, which remains
unreproduced and unresolved. Physical hue/brightness, feel and listening acceptance
remain unverified.

## Restored overlapping scale layout

At the player’s request the earlier +1right/+3up geometry and centered register
are restored, retaining ABI6, all lighting/input fixes and the opt-in diagnostic.
The movable triangle is tested across12roots,7modes, valid octave windows, all
7row pairs and6horizontal positions; major/minor qualities follow the scale.
No saved note, song, history or synthesis default is rewritten by this change.
The previous continuous-layout release and device results above are historical.

Restoration validation: private294tests and public299tests passed, including
13focused regressions. The triangle records exact pitches and survives saved
roundtrip/native playback; exhaustive geometry tests cover scale and octave
boundaries. Public host native build passed. Native C is unchanged and the
verified ABI6 device artifact above is retained.46/46runtime hashes match both
source checkouts. Actual restoration deployment results follow separately.

The restored release `132b2dfc1d65ab84be386c54280b079f1a81720c` is live
on Push:92/92hashes,86quiet actual-device checks passed, including simultaneous
D/F/A and duplicate-pitch LED commands. Normal service resumed with saved music,
history/media and stopped state unchanged.61samples over61.044seconds had zero
xruns/peak and stable clean revision. No physical hue/listening acceptance is
claimed; the Spore oscillation remains unresolved.
