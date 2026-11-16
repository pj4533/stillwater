# Installation, recovery and removal

Read this entire guide first. This is an experimental independent application,
not an Ableton-supported installation. It requires an already-authorized root
SSH connection to a Push 3 Standalone. It does not enroll SSH, supply a key,
change firmware, reset the device or bypass vendor protections. Keep a working
SSH connection and a verified off-device backup. Reduce physical speaker and
headphone levels; do not test unattended with audible notes.

Tested platform: Push 2.3.5b1 / Live 12.3.5b1 beta, x86_64 Linux, existing ALSA
card `A3`, named MIDI `Live Port`, USB display vendor/product `2982:1969`.
Other firmware may move paths or change behavior. Inspect your installation
before following commands; stop if paths, ownership or loader compatibility differ.
Never run Stillwater and the stock Push application against the hardware together.

## Prepare a payload on your computer

Build the paired x86_64 artifact as in [development](DEVELOPMENT.md). Python 3.10+
and the existing ALSA runtime/utilities must be available on the device. Stillwater
uses usbfs directly; there is no Python/libusb package to install. The runtime
payload consists of `src/`, `scripts/`, `assets/`, `engine.so` and `tools/ffmpeg`,
`tools/ffprobe` plus their license/provenance. Tests/docs need not be deployed.

Obtain FFmpeg separately; no binary is bundled. The explicit optional staging tool:

```sh
python3 scripts/stage-encoder.py
```

retrieves this pinned x86_64 GPL build from
[FFmpeg-Builds release](https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/tag/autobuild-2026-11-15-12-40):
`ffmpeg-n8.1.3-35-gf1acb0a266-linux64-gpl-8.1.tar.xz` (151596896 bytes), SHA256
`94879ca4e4d17aae5e6a30d0de16ba765df708572e4ce3f6c2623a48405be917`.
It validates archive paths/types and stages only FFmpeg, ffprobe and LICENSE.txt
under `.build/tools`; it never installs or executes them. The resulting binary
hashes are `8823e8d5df39fd4008eb84e8c8fb5d28d3400a02b3b8edb9e3c82141c33a3a11`
and `3c65eff3750bd58a40d05b2dfef79fb27e8517916212b14d69d52d3d4e226102` respectively.
Retain its `provenance.json` and GPL license. See upstream release/build repository
for corresponding source and build configuration; do not treat the project MIT
license as covering these binaries. If unavailable, obtain/build a compatible
FFmpeg from [FFmpeg](https://ffmpeg.org/download.html), verify its provenance and
licenses, and re-run film/decode acceptance rather than substituting silently.

The tested device lacks `/lib64`; the runtime explicitly invokes existing
`/lib/ld-linux-x86-64.so.2` when necessary. Verify the staged encoder's interpreter,
DT_NEEDED libraries and version with that loader on your device. Do not change
system loader links or replace system libraries to make a binary work.

Create a clean payload with `scripts/prepare-home.py`:

```sh
python3 scripts/prepare-home.py .build/payload --engine .build/engine-device.so --tools .build/tools
```

This refuses an existing destination, copies only runtime files and the selected
engine/tools, and never copies sessions, backups, recordings or machine configuration.
Inspect its hashes before copying.

## Connect and back up deliberately

`.env.example` lists optional shell settings; no file is automatically loaded.
Set your own `STILLWATER_SSH_TARGET`, `STILLWATER_SSH_KEY` and
`STILLWATER_KNOWN_HOSTS` privately. Pin the host key through a trusted channel;
never use `StrictHostKeyChecking=no`. Example connection (blank placeholders must
be set first):

```sh
ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$STILLWATER_KNOWN_HOSTS" -i "$STILLWATER_SSH_KEY" \
  "$STILLWATER_SSH_TARGET"
```

The scripts intentionally use `/data/push-ambient` as the device installation home.
Do not rename it piecemeal: selector, supervisor and recovery agree on that path.
Before an update, ask the current player to stop; capture the current master and
state, then gracefully stop Stillwater through `/etc/init.d/push3 stop`. Confirm
all registered PID/start identities are dead, no stale child owns audio/USB/MIDI,
and stock Live/Push3 is absent. **If ownership cannot be proved released, stop.**
Do not delete an ownership registry to get past a blocked start.

Copy the entire stopped `/data/push-ambient` to a uniquely named private backup
on the device and off-device, including sessions, histories, recordings, enabled
preference, recovery/original stock script and existing engine/source. Record
hashes. Keep enough free space. A first installation must also privately preserve
`/etc/init.d/push3` verbatim before replacing it. Never publish that vendor file.
The installer additionally saves it once as `recovery/push3.stock`; never replace
that backup with a copy of an already-installed selector.

Transfer the clean payload into a new staging directory, **not over live state**.
Use your pinned SSH options for transfer. On update, with all owners stopped,
copy only payload `src/`, `scripts/`, `assets/`, `tools/` into the installation and
write the new engine as `engine.so.new` then rename atomically to `engine.so`.
Do not copy/delete/rsync-overwrite `sessions/`, `recordings/`, `recovery/` or enabled
preference. Verify every payload hash after copying; keep paired rollback source.

## First installation and acceptance

On-device, after checking the original vendor backup and payload:

```sh
sh /data/push-ambient/scripts/install-device.sh
```

This installs a boot selector and preserves the stock init script; it does not
stop a running stock application or itself enable Stillwater. Read the scripts
before running them. To switch after saving any stock work:

```sh
sh /data/push-ambient/scripts/switch-to-stillwater.sh
```

It asks Live to quit via the existing official updater quit path, waits, then
terminates the now-idle surface launcher, verifies release, removes the temporary
updater marker, enables Stillwater and starts the selector. It refuses takeover
if Live/Push3 remains. It does not itself reboot. This is a deliberate transition;
keep your private backup and SSH recovery available.

Acceptance before leaving auto-start enabled:

1. Exactly one supervisor and one app own the hardware, ready exists, ALSA PCM
   and display counters advance, no ownership errors/xruns, transport stopped.
2. Verify source/native/assets hashes and boot selector/original backup hashes.
3. Query status; retain the player's actual master and song. On a copied session,
   master zero, test production parser controls without opening a second MIDI reader.
4. Check all views, Mix button, both master paths, library and bounded shutdown.
   Audible playing is a supervised human check with levels reduced.
5. Test a controlled failure/retry and recovery only after backing up, confirming
   silence and ownership release. No automatic fallback to stock is expected.
6. After saving a checkpoint, a deliberate OS reboot may verify the boot ID changed
   and Stillwater starts stopped with enabled retained. A physical cold boot is a
   separate human check. Never reboot a device another person may be playing.

## Recovery and uninstall

Main failure never automatically starts Ableton or removes enabled preference.
The supervisor first proves prior owners dead, then uses bounded quiet same-app
retries/backoff. Repeated failure opens a minimal audio-free STILLWATER recovery
screen with reason, Play-to-retry and deliberate held-Settings stock escape.
Hardware failure can prevent even this screen. Recovery and normal app never own
USB together. Ownership-blocked errors fail closed and retain registry evidence.

Hold Settings for two seconds to return to stock **for this session**. To disable
Stillwater on subsequent boots, via SSH:

```sh
sh /data/push-ambient/scripts/stock.sh --disable
```

It stops registered owners, confirms release and invokes the preserved stock
script. If release fails, investigate rather than starting another owner.
For full removal, first return to stock with `--disable`, verify its operation,
then restore your verified original `/etc/init.d/push3` from the private backup
with its executable mode preserved. Keep `/data/push-ambient` and off-device
backups until music/recordings have been exported; no removal script deletes them.

Rollback requires matching source/native/assets and the appropriate session format.
V2 leaves legacy files untouched; never overwrite newer music merely to restore an
old build. Restore a private session backup only deliberately, after archiving the
newer state. Do not factory-reset or update firmware as a troubleshooting shortcut.
