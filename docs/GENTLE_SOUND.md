# Gentle defaults and compatibility

New blank songs and newly added layers use sound version 2: eight distinct,
softer starting presets with slower envelopes, pitch-relative lowpasses and
restrained feedback. Existing songs, loops, snapshots and Undo/Redo retain their
original sound version 1 parameters and DSP. Selecting or clearing an existing
layer never changes its sound profile. Macro names and full ranges remain;
bright, rough and frozen sounds remain available through adjustment.

Song schema 3 requires integer `sound_version` 1 or 2 on every layer. Schema 1/2
songs omit that field and decode as version 1, including every history entry.
Unknown or invalid profiles fail visibly. Opening an existing song performs no
migration write; ordinary later saves write schema 3 with every profile retained.
The filename remains `sessions/current-v3.json`; envelope version 2, atomic
persistence, bounded history and no-overwrite library behavior remain unchanged.

Native ABI 5 carries the profile per layer. Python rejects an older native ABI
before history preparation or ALSA startup. Always install paired source/native.
Older builds reject schema 3: archive all newer music separately before rollback,
and never overwrite newer sessions with an older backup merely to restore code.

Version 2 uses seconds-based envelope coefficients, two voice lowpasses and a
dark feedback filter. Legacy arithmetic remains on its original DSP branch.
Oxide's sine/saw blend and quantization scale with Wear squared; full roughness
remains at Wear 1. No extra callback allocation, lock, I/O or thread is added.
All new layers retain level .30 and deterministic, bounded ±.015 variants.

## Reproduce without hardware

```sh
sh scripts/build.sh
python3 -m unittest discover -s tests -q
python3 scripts/preview-gentle.py
python3 scripts/rehearse-gentle.py
python3 scripts/rehearse-v4.py
python3 scripts/benchmark-v3.py
sh scripts/build.sh device
```

Preview creates 43 synthetic eight-second clips (legacy, gentle, bright, high,
lower effects and open fifths) and measured metrics under `.build/gentle/`.
WAV delivery gain is measured per clip; it does not change live master.
Rehearsal builds fifteen notes across Silt/Choir/Filament/Prism through the real
parser, dispatcher, native engine and renderer; output stays under `.build/`.
Neither tool opens device audio, MIDI, USB or user sessions. NumPy/Pillow and
host FFmpeg are developer dependencies only.

`tests/fixtures/gentle-legacy-*.json` contains synthetic pre-change PCM hashes
and exact toolchain/score preconditions. All eight legacy renders match bitwise
on the captured ARM/GCC/libm toolchain. The test explicitly skips elsewhere;
compare paired pre-change renders on another toolchain rather than asserting
cross-platform equality. Tests also cover mixed-profile history, schema 1/2
no-write opening, validation, early ABI rejection, native envelope timing,
64 macro responses and bounded low/mid/high-register transitions and Stop.
Automated signal checks do not establish listening quality or physical behavior.

## Reusable offline portrait tools

`scripts/social-gentle-edit.py` makes a 63-second portrait edit from an explicit
960×160, 10fps capture with native stereo. Its captions match the fifteen-note
rehearsal score; supply a capture of that score. It uses only renderer pixels,
with a labeled detail crop and whole-display overview. No hardware photo, private
film, device recording or personal state is included. It never controls hardware.
Use synthetic captures and retain honest source disclosure when adapting it.

```sh
python3 scripts/social-gentle-edit.py --source /path/to/synthetic.mp4 \
  --output-dir .build/portrait --gain-db 0 --preview-only
python3 scripts/social-gentle-audio.py /path/to/old.mp4 /path/to/new.mp4 \
  --output .build/audio-contrast.json
```

Remove `--preview-only` to encode. Specify `--regular-font`, `--bold-font` and
`--serif-font` if Inter/EB Garamond are absent; fonts are separately installed
under their own licenses. Gain must be chosen from measured source loudness and
true peak; this tool does not normalize or limit. Strict-decode the final film
and check headroom, timing and source attribution before sharing. The comparison
uses 10–58 seconds of two 44.1kHz stereo inputs; distinct scores cannot establish
controlled DSP causality or listening approval. Private device orchestration,
preservation/acceptance scripts and raw-journal QA depend on private deployment
state and are intentionally excluded. Production film capture remains documented
in [Controls](CONTROLS.md) and [Installation](INSTALL.md).
