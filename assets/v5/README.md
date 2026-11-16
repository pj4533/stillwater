# V5 material worlds

Original deterministic code-native constructions, sampled from the owned V2
background grain and palettes. No third-party reference art, private attachment
or copied plugin shape is included. Original image lineage: [V2](../v2/README.md).

Regenerate from the repository root:

    python3 scripts/prepare-v5-art.py

Eight instrument `.bin` scenes: 1024×160×2 bytes, visible width960, BGR565 little
endian. Eight `.poses` banks: eight columns ×17 material geometries ×5 native
music poses ×64×64×2 bytes =5,570,560 bytes each,44,564,480 bytes total.
[manifest.json](manifest.json) contains every generated file size and SHA256.
The generator takes an optional output directory for deterministic comparison.

Each64×64 patch starts at `(120*column+28,48)`. Its two-pixel border is exactly
the full-scene background in every geometry/audio pose. Surrounding grown-in
pipes, anchors, sockets, river banks, roots and hinge beds connect across
columns. Surface grain is sampled at two-pixel spacing from V2, never from the
V4 black recess. Endpoints and witnesses are made from the same material.

The authoritative marker paths live in `src/material_controls.py`. All eight
contacts are drawn at exact normalized values after baked audio geometry. The
marker/socket region plus two pixels, all permanent witnesses, and Prism's
entire terminal facet are protected over the coarse pose's rounding interval.
Baked geometry contains no duplicate coarse pointer. Secondary material shape
uses17 poses; percentages and exact contact position retain the actual value.

V5 changes no audio/control/song behavior. ABI5, schema3 and gentle sound2 are
unchanged. Runtime loads one V5 pose cache and eight V5 scenes; existing V4
`.working` pages remain the non-instrument backgrounds. The portable payload omits inactive V4 poses and offline support metadata.
V2 sources remain available for shared legacy code and reproducible artwork.
Pillow remains build-only.

Music support is explicit build-time geometry. `Painter` records visible
foreground surfaces, excluding cast shadows and inherited scenery. Role-native
interior/return masks intersect that support before landmark protection is
subtracted. `support/*.png` are512×1088 atlases (eight columns ×17 geometries),
with their own SHA256 manifest. They are small offline/test metadata and are
not loaded or shipped in the runtime payload. Every audio pose changes only
23–32 existing supported pixels through localized material light; no independent
music strokes are painted over the scene. Static geometry is unchanged.
