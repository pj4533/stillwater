# V3 registered source mechanisms

All original worlds/provenance remain in `../v2/README.md`. The build-only Pillow
script `scripts/prepare-v3-art.py` decodes the exact prepared pixelated V2 binary
background. It deforms that source material itself; no repeated outline symbols,
new image sources or fonts are added. Soft organic masks register each64x64
region at x28..91 of each120px column, y48..111. The two-pixel source grain is
retained. Minimum contrast persists at low parameter values.

Each role `.poses` file contains eight macros,17 macro geometries, five independent
native-audio deformations and64x64 packed BGR565 pixels:5,570,560bytes. Macro
endstops retain independent audio displacement. The actual native envelope gates
all motion; the PCM clock provides a slow phase even when a role's auxiliary FX
metric is zero. Local brightness is bounded; no whole-frame flash is used.
Silt breathes vessels, Filament bends wires, Glass displaces fractured optics,
Choir opens bellows, Oxide shifts tape bands, Backwash folds currents, Spore
scatters grains and Prism shears its lattice.

Runtime performs at most512bounded128byte row copies per frame, with no Python
pixel transforms or image package. Cached pose data totals44,564,480bytes if all
eight roles have been visited. Eight `.working` backgrounds (327,680bytes each)
provide continuous organic negative space for actual timeline/fader data. LOOP
and Mix do not render macro mechanisms across empty channels. Their notes/levels
and role colors correspond to the song's actual layers.

Ship **all eight `.poses` and all eight `.working` files**, paired with source,
ABI3 native engine and original eight V2 backgrounds. Build with
`python3 scripts/prepare-v3-art.py`. Review with
`python3 scripts/preview-v3.py`; output is
`.build/v3-preview/`. Each role has both a knob sweep and a separate fixed50%
macro silent/native-audition/settled clip. Native preview decoding uses RGB;16
(red in the low five bits), matching the hardware packing.
