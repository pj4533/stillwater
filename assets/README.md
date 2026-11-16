# Original Stillwater pond artwork

`pond-original.png` was generated on2026-11-15 with the built-in image generation
tool for this project. Prompt direction: an original whimsical submerged ambient
music machine, weathered teal enamel and brass pipes, glass bells and gauges,
coral mushrooms, lilac plants, gold lamps and calm dark water; wide composition
suited to Push's strip display. No Freakshow product imagery or branding was
used as an asset. Freakshow's tactile, peculiar-object art direction is an
influence; this is original generated artwork, not a commissioned human painting.

`scripts/prepare-art.py` crops the supplied2048x683 image to its central machine,
resamples to480x80 then doubles nearest-neighbor for a deliberate pixel texture.
It encodes960x160 visible pixels with1024-pixel row stride into
`pond-frame.bin` (BGR565,327680bytes). Pillow is an offline conversion dependency;
device rendering reads/cache-copies these bytes using only the standard library.
Both source and converted assets travel with the paired application payload.

## Chunky creature atlas (visual v2)

`creatures-original.png` is an original transparent RGBA1254x1254 atlas generated
on2026-11-15 with the built-in image tool. Prompt direction: four solid shaded
pixel-art pond-machine creatures with strong dark silhouettes and light rims:
coral snorkel frog with glass belly, lavender clockwork shell snail, golden
tank-toad, seafoam mushroom goblin. These are original generated characters.
The source has actual alpha0..255, not a painted checkerboard.

`prepare-art.py` crops quadrant alpha bounds and prepares44/64px subjects with
five small squash variants. It downsamples at half resolution then uses nearest
scaling for deliberate pixel texture. `creatures-spans.json` stores opaque
BGR565 row runs after thresholding alpha128. The device decodes these once and
blits clipped byte spans using only the standard library; no runtime Pillow,
filesystem writes per frame or per-pixel alpha blending. Dark recessed niches
leave quiet space around subjects. Breathing is decorative; native envelopes
and onsets drive body deformation, lantern intensity, plumes and water ripples.
The shared mixer manifold carries eight level-setpoint vessels, distinct ENV
activity beads and explicit open/closed mute valves. No audio behavior changes.

## Unified pond organism (visual v3)

`organism-original.png` is original built-in image-tool output, generated
on2026-11-15:2048x683, eight unsettling translucent reed/glass organs grown into
one corroded copper/root ecosystem, aged brass tags and gauges, earthy black
water with small bioluminescent patches. No copied product artwork. V3 uses this
whole authored organism as the interface; the v2 mascot assets are retained as
iteration history and are not read by the v3 renderer.

`prepare-organism.py` registers source x-centers260,495,735,970,1210,1460,1690,
1890 to visible x-centers60,180,300,420,540,660,780,900. Piecewise horizontal
resampling keeps every organ aligned to its hardware encoder while retaining
continuous roots between them. Source y0..550 is fitted to160px; the bottommost
extra roots are cropped. It downsamples960x160 to480x80, then doubles nearest
for the user-requested deliberate pixelated image treatment.

`organism-frame.bin` stores the resulting BGR565 scene with1024px stride.
`organism-fluid.json` stores hand-registered irregular interior masks as byte
row runs with a dry reflection and four subtly displaced/toned fluid textures.
They preserve the original material reflections and geometry; no repeated new
vessels or dark scene cutouts are drawn. Runtime selects a fill boundary for the
stored control and copies rows within that source lumen. Small bubbles and root
rings follow actual native envelope/onset telemetry. Texture phase is local slow
analog drift, maximum6.5% variation in the original material, not full-screen
flashing. Names and numbers are shadow-etched at the source tag positions.
Both cached assets load using only the standard library; Pillow stays offline.

Visual v3b retains the same registered source but carves continuous negative
space into the canopy and root bed offline. Two overlapping low-amplitude sine
contours give each edge an irregular scalloped silhouette; a five/six-pixel
feather blends the dark peat into sourced roots above and between organs. Source
texture remains at12% intensity in the quiet text region. This is one connected
material shelf, not eight cards. Primary labels/values are2x pixels; the full
selected voice stays in the canopy while Mix uses short readable names. V3 and
v3b preview artifacts remain separate for comparison.
