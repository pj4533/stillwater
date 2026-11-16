# Stillwater V3 — play, audition, grow

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
- **Scale** opens KEY. Screen encoder1 chooses root, encoder2 chooses Major,
  Dorian, Phrygian, Lydian, Mixolydian, Minor or Locrian. All layers follow the key;
  Undo restores the preceding key and music. Left/Right shifts the complete pad
  octave window. All64 pads remain scale notes on every page.
- **Delete** clears just the selected layer's notes. Its sound, macros, level and
  mute remain. Undo restores the phrase. Late unfinished takes cannot return.
- **Note / Device** shows eight source-material mechanisms and macro values;
  screen encoders change their actual sound. Image geometry follows the values
  even silently; native envelopes/effects add restrained movement while sounding.
  **Mix** sets layer levels. **Volume** always controls MASTER OUTPUT0–100%.
- **Clip / Session** opens LOOP: encoder1 changes BPM; lower26 adds a bar, lower27
  exports exactly the next full loop to WAV. The separate Tempo encoder also
  works. Pending tempo and additions clearly show next-loop timing.
- Top screen buttons select existing layers. Lower buttons mute their matching
  layer on the main/Mix pages; colors follow each role. Pad roots and held pads
  glow in its hue, natural pitch classes are dim white and accidentals dark tint.
- **Undo / Shift+Undo** undo/redo. **Save** writes a new song snapshot; autosave
  runs asynchronously and SAVED/UNSAVED/SAVE ERROR shows durability. **Shift+Session**
  opens the library. **Shift+New** archives, then opens a blank one-bar song.
- First **Play** attempts an automatic screen+stereo film. **Shift+Record** starts
  or finishes a film without stopping music; FILM status is separate from REC.
  **Shift+Save** retains Bottle of the last available30seconds of real output.
- For exact WAV, release pads and settle takes/tempo/additions first. A32beat loop
  at30BPM is64seconds and may need nearly128seconds to wait+capture. Musical edits,
  audition, Stop, xruns and structural changes cancel it; view changes are allowed.
- **Help** lists controls. Hold **Settings** two seconds for deliberate stock return.

V3 validates and copies the latest V2 song and all undo/redo on first launch,
using its own `sessions/current-v3.json`. V2/legacy/library/recordings remain
untouched. Keep all session versions when backing up or rolling code back.
Start with speakers/headphones low. Automated PCM/control/render checks do not
establish physical pad feel, visible hardware hues or musical taste. No user
session or music is bundled. A fresh clone creates a new one-bar Silt song.
