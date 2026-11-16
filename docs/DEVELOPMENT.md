# Development

All commands below run from the repository root; no parent checkout or external
agent tooling is required. Linux is required for `/proc`, Unix sockets and the
hardware ownership tests. Python 3.11+ standard library is the runtime; GCC/Clang
with C11, libc, libm, pthread and dl build the native engine. ALSA is dynamically
loaded on hardware (`libasound.so.2`); no ALSA development headers are required.
The display uses Linux usbfs ioctls directly, **not libusb**. Install ALSA utilities
for `amidi`, plus FFmpeg/ffprobe with H.264/AAC for media workflows. On Debian-like
systems the relevant packages are `build-essential python3 python3-venv
python3-pip alsa-utils libasound2 ffmpeg binutils` (ALSA package names vary).
Pillow is offline tooling only, never needed on Push. Keep at least2GiB free
on the filesystem containing the checkout/.build: media tests exercise real
admission thresholds (1GiB at film start), so a512MB temporary filesystem
cannot run the full suite even when the code/build itself fits.

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
sh scripts/build.sh
python3 -m unittest discover -s tests -v
```

The native build uses `-Wall -Wextra -Werror`. Tests render memory-only PCM and
use fake ALSA/process fixtures where needed. They must never be run in a real
installation home. Media tests need `/usr/bin/ffmpeg` and `/usr/bin/ffprobe`;
install distro binaries there on the test host. No secrets or network access
are needed to run tests. The optional encoder downloader accesses the network
only when explicitly invoked.

## Offline production workflow and measurements

```sh
python3 scripts/rehearse-v4.py # V4 managers, native notes, real film and deletion checks
python3 scripts/rehearse-v3.py # long-loop regression
python3 scripts/rehearse-v2.py # legacy16beat regression
python3 scripts/benchmark-v3.py
python3 scripts/benchmark-v2.py
python3 scripts/benchmark-v2-drain.py
python3 scripts/measure-v2-macros.py
```

The V3 rehearsal builds all eight roles from notes, checks undo/redo and library
operations, captures actual production-rendered images, produces a140second
film, decodes AAC with measured alignment checks, and exports a sample-exact
64second32beat/30BPM loop across the45second history wrap. Results live under
`.build/v3-rehearsal/`. The V2 regression retains16beats and32second export.
Benchmarks use the local CPU, not Push
unless explicitly run offline on Push. Do not describe container timing as device
timing. Do not infer listening quality from PCM comparisons.

To smoke-test the actual app entry point without USB/MIDI/ALSA, first build and
prepare a **disposable** home, then run briefly without Play or note events:

```sh
python3 scripts/prepare-home.py /tmp/stillwater-offline-home --engine .build/engine.so
python3 src/app.py --offline --home /tmp/stillwater-offline-home
# In another shell: python3 src/control.py --socket /tmp/stillwater-offline-home/control.sock '{"op":"status"}'
# Ctrl-C requests orderly shutdown.
```

Use a local Linux filesystem for that temporary home: some shared/container
bind mounts do not support chmod on Unix sockets. The destination must not
already exist. The runtime itself needs Python3.10+; development/staging tooling
uses Python3.11+.

The full application uses device-oriented encoder-loader paths. On a non-x86
host use the rehearsal for films; the no-Play entry smoke does not exercise film
encoding. The rehearsal uses host FFmpeg directly. Hardware execution is x86_64.

## Paired x86_64 artifact

Install Zig 0.13.0 from [the official download archive](https://ziglang.org/download/0.13.0/)
for your build host, verify its published signature/checksum, and place `zig` in
PATH or set `ZIG` to that executable. Then:

```sh
sh scripts/build.sh device
sha256sum .build/engine-device.so
```

This targets `x86_64-linux-gnu.2.35`, independent of the host architecture. Deploy
matching `src/` and the built engine as one stopped-service update; the native ABI
must match. Do not deploy host ARM `.build/engine.so` to Push.

## Artwork

Reviewed original PNGs and prepared `.bin`/JSON caches are committed under assets.
The `.bin` files are BGR565 image data, not executable binaries. To regenerate:

```sh
python3 scripts/prepare-v2-art.py
python3 scripts/prepare-v4-art.py
python3 scripts/preview-v4.py # .build/v4-preview; ranges, managers, native audio
# Optional legacy renderer assets:
python3 scripts/prepare-art.py
python3 scripts/prepare-organism.py
```

The V4 converter derives material deformations from exact prepared V2 pixels,
including independent audio poses and quiet working backgrounds. Its32low/high
frames, fixed50%-macro native-audition clips and knob sweeps use the production
renderer at960x160. Silent geometry persists.

The V2 converter downsamples then nearest-neighbor scales for intentional pixel
texture; runtime needs no Pillow. Draw text after animated material, retain
readable negative space, and keep main/mixer/help previews at native 960×160.
Curated media provenance and regeneration are in [MEDIA](MEDIA.md): V4 device
display captures and synthetic production-renderer animation, with no camera footage. Do not check generated music, logs or private state in.
