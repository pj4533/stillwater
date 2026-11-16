# External agent and tool control

Stillwater has no onboard language model, voice command system or autonomous
editing loop. External processes use a mode0600 Unix socket, default
`/data/push-ambient/control.sock`. There is no TCP listener. Local account/socket
access is the authority boundary; this is not multi-user authentication or a
revision-CAS collaborative protocol. Serialize requests and query before editing.

```sh
python3 src/control.py --socket /data/push-ambient/control.sock '{"op":"status"}'
```

The CLI accepts one JSON argument or stdin; exits nonzero for `ok:false`. Replies
include model/revision, native/transport counters, pending takes, undo/redo,
dirty/durable revision and recording/capture/export status.

| Operation | Fields / meaning |
|---|---|
| `status` | Current state and counters |
| `event` | `kind`, `number`, `value`, optional `channel` default0; real wire dispatcher |
| `set_master` | Finite `value`0–1 through ordered smoothed queue |
| `export_loop` | Next complete loop, subject to capture/activity admission |
| `request_capture`, `query_capture_status` | Bottle request / job status |
| `record_start`, `record_stop` | Start/finish screen+stereo film |
| `record_status`, `record_recover` | Film status / interrupted-spool recovery |

Read `LoopInstrument.operation` in src/loop_app.py and Bottle/SessionRecorder for
optional fields/validation. Old query_state/Grow/garden proposals and tone/decay
operations are unsupported in V3. Explicit backpressure errors happen before
mutation; retry deliberately. Query whether a non-idempotent operation completed
before retrying. Do not edit session files directly while the app runs.

A quiet reversible example: query status, remember `result.state.master` (the CLI reply also nests the snapshot as
`state.state.master`), set
`{"op":"set_master","value":0}`, confirm, then restore exactly the remembered
value. Master is a musical edit and can cancel exact-loop export. Never raise a
stranger's current level as a demo. On a copied/offline session, event
`{"op":"event","kind":"cc","number":112,"value":127}` opens Mix; CC50
returns to Note. Send button releases too. Musical edits use Undo(CC119) and
Shift+Undo for redo through the same control path.

Events can make audible notes, change music or invoke Settings escape. No
unattended notes on speakers: use the memory-only rehearsal or a copied session
with master zero, restoring exact current state/history after probes. Never open
a second physical MIDI reader. Pressure follows a manual token; full-MPE slide
or pitch semantics are not promised. Worker threads must never become another
audio command producer.

V4 controls use the same event path: CC86 toggles note recording only; Shift49
plus Record86 opens RECORDINGS. CURRENT top104 / SAVED top105; CURRENT lower20
starts film and lower21 stops+saves. Scale58 opens KEY; encoders71/72 choose the
draft and lower27 applies / lower26 cancels. Session51 opens LOOPS; Clip113 opens
LOOP; Repeat56 stages Add Bar. Delete118 clears selected notes on the instrument,
but requests confirmation in managers. Physical Delete cannot confirm deletion.
Send releases and release Shift after combinations. Manager buttons are contextual:
query status, consult CONTROLS and inspect LoopInstrument before destructive events.
Never retry non-idempotent edits without checking the result.
