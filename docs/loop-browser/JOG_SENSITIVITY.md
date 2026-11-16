# Immediate jog browsing — 2026-11-16

The first browser release reused SlowChoice, which requires four accumulated
relative units and resets after350ms or a direction change. Normal jog packets
are CC70 value1 clockwise and127 counterclockwise. Consequently four messages
were required per item; sufficiently slow repeated turns could reset before any
item moved. This explains the reported excessive spinning.

The pinned [encoder protocol](https://github.com/danielknng/push3-protocol-docs/blob/0d843cd69a7a0d2c52eddb46a57ea69fd0ddc2e5/docs/encoders.md)
was re-read in full. It identifies those normal jog values and signed relative
encoding. Its general resolution note says1–2messages per detent, not an exact
per-device detent calibration. We therefore establish immediate message response,
not a measured physical-detent guarantee or human feel result.

Only LOOPS and RECORDINGS/SAVED CC70 selection changes: every nonzero packet
moves exactly one item in its signed direction, immediately. Zero does nothing;
multiunit/extreme values remain one item, with endpoint clamping. No accumulator,
timing filter or global acceleration remains for browsing. Nudges93/95, wheel
press/touch, rename/KEY slowing and Volume79 retain their previous behavior.
Nothing loads automatically and browser input does not change music/history.

The regression sends raw MIDI through MidiParser and LoopInstrument.wire,
including fragmented/running-status/realtime-interleaved packets, repeated1/127,
immediate reversal, all128 possible values, endpoint clamping and both managers.
Existing tests cover no automatic load, nonzero channels, rename/confirmation,
current recordings, master and pending structural/replacement protection.

Local focused tests:17passed; strict builds and full suites passed:
311private tests in31.541s and316public tests in31.462s. Reviewed source is now published and deployed. Device acceptance now uses normal1/127 jog packets plus zero/extremes
through the sole production Midi.read; it still aborts on physical non-sysex
input and uses an isolated master-zero home. Unchanged ABI6 native is retained.

## Actual-device result

111/111 quiet checks passed in35.009s, including immediate normal1/127 steps,
repeats, reversals, zero and signed extremes through the sole production Midi.read.
Both LOOPS and saved RECORDINGS respond to a single normal jog packet. Existing
volume/no-load/rename/source/persistence/pad tests also pass.343display frames
and1546586audio frames advanced, with zero xruns/rejections/output peak.

All92installed hashes match; ABI6 native is unchanged.61normal-service samples
over61.393s passed: clean stopped song, live owners, advancing audio/display,
zero xruns/peak, maximum reported render8.690ms. New service-log suffix contains
only starting/ready lines, no new errors/backoff/exits. All current music,
sessions/history/recordings, master and transient controls were preserved.
Rollback retains the reviewed source-capable reader and latest sessions.

[Sanitized checks](jog-device-acceptance.json) ·
[Actual synthetic fixture frames](jog-device-contact.png).
No physical detent telemetry was observed; synthetic packets establish software
response, not the player's physical feel. No sound/DSP/graphics changes were made.
