# Standalone V4 release snapshot

This repository contains the complete distributable instrument, with its existing
public history and MIT/Push Hack notices. It does not import private parent
repository history. Runtime source is paired with native ABI4 and all eight V4
material caches; V2 backgrounds and legacy assets remain for shared regression
code and reproducible artwork. V3 assets remain available for deliberate rollback.

Included: production Python/C, ownership and recovery scripts, portable builds,
fresh payload preparation, tests, original source art and prepared image data,
public installation/development/agent documentation and curated media.

Excluded: SSH keys/host identities/addresses, local configuration, personal
handoffs/conversations, deployment logs, user songs/history/recordings, vendor
stock scripts/firmware, backups, downloaded encoders, native executables, cache
and temporary media. Ignore patterns are a convenience; review tracked files
before any release. No user session ships in this checkout.

## Reproduce

Follow [DEVELOPMENT](DEVELOPMENT.md). Build with `sh scripts/build.sh`, run
`python3 -m unittest discover -s tests -q`, then
`python3 scripts/rehearse-v4.py`. The latter exercises 32 assertions through the
production parser, native engine, renderer and serialized workers, including
explicit film start/stop, real H.264/AAC strict decode, Apply, safe library
rename/load/delete, inventory and durable state. No hardware is opened.
V3/V2 long-loop rehearsals remain for regression; they are not current controls
documentation. Regenerate V4 assets with `python3 scripts/prepare-v4-art.py`.
See [MEDIA](MEDIA.md) for preview provenance and reproduction.

The [runtime manifest](runtime-manifest.json) lists 45 core source/art hashes:
21 source files, eight V2 backgrounds and sixteen V4 pose/working files.
`prepare-home.py` adds shared/legacy assets and ownership/recovery scripts,
refuses an existing destination, excludes caches and never imports private data.
The packaging tests verify manifest hashes and every role's cache dimensions.
The native ABI is checked before audio/history startup. Cross-build using
Zig 0.13.0 on PATH or `ZIG`, targeting GNU2.35 x86_64. Match source/native/art
as a stopped-service update; see [INSTALL](INSTALL.md).

The manifest records the verified reference device engine hash. Rebuilds may
differ due to debug source/build paths; compare allocated ELF sections when
checking equivalent output. No compiled engine is committed. Optional FFmpeg
is separately obtained with its GPL license and provenance; MIT does not cover it.

The [export manifest](export-manifest.json) records hashes/sizes for the complete
curated tree excluding itself. It contains no private source paths. Fresh archive
validation checks native build, Python suite, media, local documentation links,
payload completeness and source/art identity. Automated tests are not a claim
of human listening, physical pad feel, universal device safety or security audit.
