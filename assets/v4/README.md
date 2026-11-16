# V4 source-material ranges

Prepared offline by `scripts/prepare-v4-art.py` from the exact pixelated V2 binary
backgrounds. All eight worlds ship together. The original source/provenance is
unchanged; see ../v2/README.md. V3 remains available for paired rollback.

Each `.poses` file is 5,570,560 bytes: eight columns x17 macro positions x5 audio
positions x64x64 x2 BGR565 bytes. Each `.working` background is327,680 bytes.
The eight-world pose cache remains44,564,480 bytes. Runtime performs512 bounded
128byte row copies per frame; Pillow is only a development/preparation tool.

A fixed source-material recess runs y52–108. Filled material rises from below,
with each role's source grain, color and contour. Two-pixel grain stays fixed;
audio changes source grain/refraction inside the occupied area. The exact seam,
index notch, fixed100/0 endstops and midpoint witness are drawn afterward by
the production renderer. Seam y=108-round(56*value), independent of audio.
The17 baked fills are approximate; the seam has less than one pixel error.

Ship V4 assets with ABI4 native/source and the existing eight V2 backgrounds.
The runtime now reads V4, never a mix of V3/V4 poses. Generate real-render
0/25/50/75/100, mixed ranges, masked-value sheets and fixed-audio clips with
`scripts/preview-v4.py`. These are container previews, not Push photographs.
