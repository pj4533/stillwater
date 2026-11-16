# Loop browser and loaded-source deployment — 2026-11-16

Reviewed source is published and deployed. Actual-device validation passed;
existing music/history/media were preserved.

## Controls and persistence

The complete pinned protocol source was read:
https://github.com/danielknng/push3-protocol-docs/blob/0d843cd69a7a0d2c52eddb46a57ea69fd0ddc2e5/docs/encoders.md

Its Jog Wheel section assigns the large right navigation wheel CC70 rotation,
CC93/95 discrete left/right nudges, CC94 press and CC11 touch. Its Master Volume
section assigns CC79. Screen encoders remain CC71–78. LOOPS and RECORDINGS/SAVED
use immediate one-row CC70 steps or nudges, with clamping and no automatic load.
The original four-unit browser slowdown was removed in the sensitivity follow-up.
Wheel press/touch do not confirm; screen encoders remain for rename/key editing.

An optional source object in the existing envelope tracks the actual saved-file
ID, display name, modified and deleted flags. Old envelopes load unchanged with
unknown provenance; the UI says CURRENT AUTOSAVE / UNNAMED. No file association
is guessed by content. Successful SAVE NEW/LOAD identifies the actual file;
asynchronous save completion cannot override a newer replacement generation.
Edits/Undo/Redo conservatively retain EDITED until explicit save/load. New clears
source, including when later Undo returns older music. Rename/delete metadata
reconciles after leaving a page. Startup resolves the name sidecar and missing
source without changing song/history. Metadata durability changes do not add
Undo entries; native staged operations guard immutable Song identity so a
source checkpoint cannot crash/cancel pending Add Bar.

Schema3 and native ABI6 remain unchanged. Older strict envelope readers reject
the additional source key. A rollback must preserve all current sessions and
retain the new compatible reader, or separately preserve newer sessions before
restoring an older baseline. Never restore old sessions over new music merely
to roll back code. This is backward reading compatibility, not permission to
open source-bearing envelopes with older code.

## Local evidence

- `sh scripts/build.sh`: strict native host build passed.
- `python3 -m unittest discover -s tests -q`: 310 passed,
  zero failures/errors, 31.278 seconds. Includes 16 new browser/provenance tests.
- `python3 -m unittest discover -s tests -p test_loop_browser.py -q`:
  16 passed, zero failures/errors (included in full suite).
- `python3 scripts/rehearse-v5.py`: 36/36 production checks
  passed, actual H264/AAC MP4 strict decode, actual V5 pixels, sample-exact native
  WAV, save/rename/load/delete, durable state and quiet Stop. Maximum local render
  6.896 ms. Generated synthetic media/report remain under .build; historical
  tracked V5 rehearsal evidence was restored after this script regenerated it.
- `python3 scripts/preview-loop-browser.py`: seven production
  render states, no hardware/files outside disposable home. [Contact](loop-browser/contact.png).
- `git diff --check`: passed.

The native 960x160 contact was inspected: unknown, loaded, edited, deleted,
24-character rename, confirmation and saved recordings states. LOADED identifies
one file while the highlighted row identifies another. The longest permitted
24-character name, eight-character file suffix, DELETED and EDITED fit together
before WORKING at x740; a regression measures that text extent. Browser hint and
full controlled selected filename fit the details area. No font brackets are
used (the appliance font lacks them); `/ ID` is drawable. Names are shown in the
existing small header font, while library title/actions retain their larger font.
Physical knob feel, hardware hue/contrast and listening remain unverified.
Actual-device checks passed as recorded below. Overlapping pads, native sounds and sound defaults unchanged.


The two reviewed completion-order regressions pass: repeated identical saves
remain unedited; metadata-only rename/delete does not cancel a pending LOAD/New.
Public strict build, 315 tests, and 36 production rehearsal checks pass.

## Actual-device checks

104/104 quiet checks passed in33.864s using a disposable master-zero home under
the sole production MIDI/ALSA/display owner. Synthetic browser packets entered
Midi.read and the production parser/dispatcher; nobody is claimed to have
physically turned the wheel. Checks cover browsing/no automatic load, volume
isolation, saved identity,24character rename, pinned confirmation, load/edit,
durable restart-reader/delete/New, and saved RECORDINGS. All64 overlapping pads,
Dorian triangle, global button commands and stopped idle behavior also passed.

92/92 deployed hashes verified; native ABI6 unchanged. All live sessions/history,
recordings and current music were preserved.61normal-service samples over61.56s
showed stopped clean state, advancing audio/display, zero xruns and peak, live
owners and maximum reported render8.282ms. New service logs contained only
starting/ready, with no new errors. Rollback retains a source-capable reader and
latest sessions. [Sanitized results](loop-browser/device-acceptance.json) ·
[Actual synthetic fixture frames](loop-browser/device-contact.png).
