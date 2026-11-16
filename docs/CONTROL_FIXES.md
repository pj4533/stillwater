# Continuous pads and visible controls

This V5 follow-up uses paired native ABI6 with song schema3. Install source and
engine together; an ABI5 engine is rejected before opening audio. Saved music,
Undo/Redo, gentle sound versions and synthesis defaults are retained. Loading
existing songs does not transpose them. A song recorded outside MIDI24–96 will
be rejected by older builds: preserve newer music before rolling code back.

The 64 pads form one ascending keyboard: eight successive scale notes per row,
then the next eight on the row above. Every pad has a different absolute pitch;
octave counterparts remain different notes. The selected root lies near the
center of the default window (degree -31 through +32). All12 roots/seven modes
fit MIDI0–127. Left/Right shifts a whole octave only when the complete window
fits; an out-of-range window is refused, never clipped into repeated notes.
Playback lights the one pad with that exact absolute pitch. Notes outside the
visible scale/window have no substitute pad. Existing notes keep their pitches.

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

## Reviewed local validation

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

## Actual Push validation

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
