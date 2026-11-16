# Playing Stillwater

Lower the speaker/headphone level before starting. A new song is silent, with one
blank role drawn from a shuffled eight-role deck. **Play** arms recording; the
first played note anchors the four-bar/sixteen-beat loop. Keep playing to overdub.
Play with an existing phrase starts at phase zero; Play again or **Stop Clips**
fades to silence. Stopped pads audition without recording.

| Physical control | Action |
|---|---|
| All 64 pads | D Dorian notes in every view; pressure follows that held voice |
| Left / Right | Shift the complete playable octave window, keeping the song key |
| New | Add the next unused role without stopping; eight layers maximum |
| Top eight screen buttons | Select existing layers without rerolling sounds |
| Lower eight screen buttons | Mute/unmute layers, including held/tail output |
| Note / Device | Selected role scene and eight macros |
| Eight screen encoders | Selected role macros; in Mix, respective layer levels |
| Mix (top-right physical mixer button) | Eight-layer mixer; ENV is activity, not level |
| Separate Volume encoder | MASTER OUTPUT 0–100% in every view |
| Session | All eight layers across the same four bars and moving loop cursor |
| Shift + Note | Toggle overdub/audition without restarting transport |
| Tempo | Apply tempo at the next loop boundary |
| Undo / Shift + Undo | Undo / redo; first undo cancels an unfinished take |
| Save | New no-overwrite named snapshot; autosave also runs asynchronously |
| Shift + Session | Library: encoders scroll, arrows jump eight, top buttons load |
| Shift + New | Archive current song, then create a blank one-layer song |
| Record | Finish automatic film while music continues; later toggle manual film |
| Shift + Record | Export exactly the next complete loop as stereo WAV + sidecar |
| Shift + Save | Bottle: last available 30 seconds of actual output |
| Help | Control reference; pads/knobs remain usable |
| Hold Settings two seconds | Deliberately return to stock for this session |

The first Play attempts one automatic screen+stereo film per song, after a real
screen frame and before the first note. REC/SAVING/errors remain visible.
This captures the rendered screen, not a camera. Finishing can take time while
music continues. Do not power off during saving. A 30-minute limit and 512MB
reserve bound admission; completed files are never overwritten.

For exact-loop WAV, release pads and finish pending captures/tempo changes first.
The next complete loop streams from post-limiter history (32 seconds at 30BPM).
Musical edits, audition, Stop, tempo change or xruns cancel the export; view
changes are allowed. The sidecar records sample endpoints and the PCM hash.

SAVED means that revision reached disk. UNSAVED/SAVE ERROR describe undurable
edits. Loading stops playback and archives the current song first; archive errors
preserve the current song. Playing/editing while replacement is busy cancels it.
The latest accepted load/new request wins. Undo/redo share a bounded 64-snapshot
history; encoder turns of the same parameter within 250ms group as one gesture,
with intervening notes breaking the group.

V2 uses `sessions/current-v2.json`. Legacy `current.json` and its journal are
preserved unchanged; only a validated legacy master is inherited on first launch.
There is no automatic legacy melody import. Back up the entire sessions directory.
