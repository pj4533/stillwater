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
311private tests in31.541s and316public tests in31.462s. No live installation
yet at this checkpoint. Device acceptance now uses normal1/127 jog packets plus zero/extremes
through the sole production Midi.read; it still aborts on physical non-sysex
input and uses an isolated master-zero home. Unchanged ABI6 native is retained.
