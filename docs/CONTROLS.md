# Stillwater V5 controls

**Session opens LOOPS; Shift+Record opens RECORDINGS; Scale opens the visible
KEY picker.** Clip opens LOOP, whose first two lower buttons also open LOOPS and
RECORDINGS. Note/Device returns to the instrument. Managers take the screen
buttons and encoders; pads, Play/Stop, Volume and Hold Settings still work.
Physical Save always saves a new song snapshot. Musical Record still toggles
note overdub. Musical recording and film recording are separate.

Film starts **OFF**. Play and notes never start it. On RECORDINGS/CURRENT,
lower20 START FILM begins screen+stereo capture; lower21 STOP+SAVE finishes and
encodes an MP4 while music continues. DETAILS shows the complete local Push
path and any warning. Top104 selects CURRENT; top105 selects SAVED, matching their display columns.
SAVED browses films, exact-loop WAVs and Bottle WAVs with
known duration, size and interrupted/error status. REFRESH updates the list;
RECOVER explicitly retries a recoverable film. DELETE needs the labeled
confirmation; pressing physical Delete twice never confirms. Film deletion
includes its large private raw job bundle. Interrupted cleanup remains visible
as DELETE INCOMPLETE and is retried at startup. Saves are local on Push, with no
implied download/upload. Paths are `/data/push-ambient/recordings/film-<id>.mp4`,
`loop-<timestamp>-<id>.wav` and `bottle-<timestamp>-<id>.wav`.

LOOPS shows four saved snapshots at a time. Encoder1 selects slowly, Left/Right
pages, and selection never loads by itself. SAVE NEW writes another immutable
snapshot. LOAD asks first, archives current music and stops playback. RENAME
changes only a display-name sidecar: encoder1 moves the cursor, encoder2 chooses
a visible character, INSERT/SPACE/BACKSPACE edit, SAVE NAME commits, CANCEL
abandons. Names are at most24 drawable ASCII characters; duplicate names are
allowed. DELETE removes the selected saved snapshot and its name sidecar;
current music/Undo remain. Both confirmations pin the original file identity.

KEY shows all seven modes on top102–108. Tap one to choose a candidate; encoder1
chooses root and encoder2 chooses mode, four relative units per step, with no
acceleration/wrap and at most one step per packet. APPLY lower27 changes all
layers together as one Undo action; CANCEL lower26 restores the active key.
Leaving KEY discards the draft. Pads continue using the active key until Apply.

All layers' real native note starts/gates light matching absolute pitches in
the current pad window in their own role colors, regardless of selection.
Very short notes remain visible; overlapping roles share the pad color in
stable200ms turns. Held manual notes retain their onset layer. Role names in
the main header and the top layer colors give a legend; + marks selection.
Mute/zero layer level, Stop and song/key resets clear stale indications.
Master zero still allows visual practice. Physical hue recognition remains a
playing check.

Each role has its own complete material construction: amphora, wire bridge,
cracked lens, ceramic lung, tape loop, river gate, living root or crystal fan.
Exact contacts and permanent witnesses show the setting from 0 to 100%, even
silently. Native music animates only the material interior; the contact never
moves with audio. All eight macro names, encoder mappings and ranges are unchanged.
See [V5 material worlds](V5_MATERIALS.md).

## Playing and sound design

Press **Play**, then play a pad to anchor a fresh one-bar loop. **Record** lights
when notes will record; tap it to audition while playback continues, then tap it
again to overdub. Stopped pads audition. The large header says REC, AUDITION or
STOPPED REC ARMED. A held note keeps the recording intent it had at onset.
Existing V2 music keeps its original four-bar loop and exact performed notes.

- **Repeat** adds one bar at the next loop boundary, repeating the first bar.
  Maximum8bars. Release pads and let pending takes/tempo finish first. New notes
  or edits cancel a pending addition; views remain usable. Undo before it applies
  cancels it; Undo afterward restores the old length at a boundary.
- **New** opens the sound chooser. Top screen buttons choose an available role.
  Silt starts every fresh song; recorded foundation unlocks middle sounds, then
  recorded foundation+middle unlock accents. Used/locked roles explain their
  state. Selecting an existing layer keeps its sound and notes.
- **Scale** opens KEY: choose root/mode, then Apply or Cancel as described above.
  Left/Right shifts the complete pad octave window. All 64 pads remain scale notes.
- **Delete** clears just the selected layer's notes. Its sound, macros, level and
  mute remain. Undo restores the phrase. Late unfinished takes cannot return.
- **Note / Device** shows eight source-material mechanisms and macro values;
  screen encoders change their actual sound. Image geometry follows the values
  even silently; native envelopes/effects add restrained movement while sounding.
  **Mix** sets layer levels. **Volume** always controls MASTER OUTPUT0–100%.
- **Clip** opens LOOP: encoder1 changes BPM; lower26 adds a bar, lower27
  exports exactly the next full loop to WAV. The separate Tempo encoder also
  works. Pending tempo and additions clearly show next-loop timing.
- Top screen buttons select existing layers. Lower buttons mute their matching
  layer on the main/Mix pages; colors follow each role. Pad roots and held pads
  glow in its hue, natural pitch classes are dim white and accidentals dark tint.
- **Undo / Shift+Undo** undo/redo. **Save** writes a new song snapshot; autosave
  runs asynchronously and SAVED/UNSAVED/SAVE ERROR shows durability. **Session**
  opens LOOPS. **Shift+New** archives, then opens a blank one-bar song.
- **Shift+Record** opens RECORDINGS; film starts only with explicit START FILM.
  **Shift+Save** retains Bottle of the last available 30 seconds of real output.
- For exact WAV, release pads and settle takes/tempo/additions first. A32beat loop
  at30BPM is64seconds and may need nearly128seconds to wait+capture. Musical edits,
  audition, Stop, xruns and structural changes cancel it; view changes are allowed.
- **Help** lists controls. Hold **Settings** two seconds for deliberate stock return.

V4 validates and copies the latest V2 song and all undo/redo on first launch,
using its own `sessions/current-v3.json`. V2/legacy/library/recordings remain
untouched. Keep all session versions when backing up or rolling code back.
Start with speakers/headphones low. Automated PCM/control/render checks do not
establish physical pad feel, visible hardware hues or musical taste. No user
session or music is bundled. A fresh clone creates a new one-bar Silt song.

New layers use gentle sound version 2; existing music retains version 1.
Song schema 3 requires paired ABI5 and is rejected by older builds. Preserve
newer sessions before rollback; see [sound compatibility](GENTLE_SOUND.md).
