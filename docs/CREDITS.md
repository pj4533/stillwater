# Licenses, provenance and influences

Original code and generated original artwork use the existing [MIT license](../LICENSE),
copyright PJ Gray. Preserve applicable third-party notices. No vendor firmware,
stock init script, commercial plugin code/art, user songs/recordings or encoder
binary is distributed.

| Included material | Origin / terms |
|---|---|
| Display framing/XOR/control numbers | Federico Pepe, MIT, Push Hack revision ce412f54065b89ff6f341c588e35dccec7cc0bda; [NOTICE](../NOTICE), [full license](../LICENSE.push-hack) |
| DSP/scheduler | Original standard-algorithm implementation; no third-party DSP source copied |
| Source PNG/prepared art | Original image-generation-tool output plus original conversion/animation code; MIT; [V2 provenance](../assets/v2/README.md), [V4 material preparation](../assets/v4/README.md), [legacy provenance](../assets/README.md) |
| README masthead | Original artwork generated with the built-in OpenAI image generation tool; MIT; [exact prompt and provenance](BANNER.md) |
| Preview media | Actual V4 test-display pixels and synthetic production-renderer output; see [MEDIA](MEDIA.md); no vendor photo |

[Ambient Town](https://frontier.every.to/experiments/ambient-town) by **Kieran
Klaassen** inspired approachable ambient workflow and previewable agent controls.
No application code/assets copied. Its controller integration does not establish
standalone support. No claim of operating that application or listening to demos.

[Freakshow Industries](https://freakshowindustries.com/) inspired peculiar tangible
objects, decayed organic machinery and broad tape/reverse/pitch/time effect
families. This is independent original DSP, not proprietary internals/emulation.
No product art, plugin interaction or demo-listening claim. Sources use original
standard algorithms: PolyBLEP/subtractive, fractional Karplus, FM/phaser,
formants/chorus, moving tape delay, windowed reverse, bounded grains/comb and
modal shimmer. No DaisySP, Soundpipe, Mutable Instruments, Faust or Signalsmith
source copied; future reuse needs exact file/commit/license inspection.

## External dependencies, not bundled

Python uses PSF licensing. System libc/libm/pthread/dl and ALSA runtime/utilities
retain their applicable upstream terms (including LGPL for alsa-lib). The Linux
usbfs ABI is used directly; no libusb implementation is copied. Pillow is
offline development tooling under HPND/Pillow terms. GCC/Zig are external build
tools; consult upstream licenses.

FFmpeg/ffprobe are separately obtained distro binaries or a pinned GPL build;
the project MIT license does not cover them. Retain that build's license and
corresponding-source/build provenance when redistributing a payload. See
[installation](INSTALL.md). No codec patent, support or security guarantee is made.
