# simia_tui_light

A minimal TUI for fast, timestamped experiment logging with customizable macro hotkeys.

Default macro keys:
- `1` = START RECORDING
- `2` = STOP RECORDING
- `3` = START TASK
- `4` = STOP TASK

Other keys:
- `n` = note
- `l` = liquid
- `m` = mark
- `u` = undo
- `r` = reload config
- `p` = print full current session (header + all events)
- `/` = session metadata commands (`/fields`, `/edit`)
- `h` = help
- `q` = stop

## Startup flow improvements
- Professional ASCII welcome banner on launch.
- Session fields can be reordered at startup per session (for example, logging before weight).
- During session setup:
  - `/back` goes to previous field
  - `/skip` leaves current field blank
- During live logging:
  - Press `/` then run `/edit Weight` (or `/edit 3`) to update metadata header fields mid-session.
  - Press `l` then choose `2` to set `Total liquid consumed (mL)` in the header at session end.

## Optional config keys (`lablog_config.json`)
```json
{
  "output_dir": "logs",
  "macros": [
    { "key": "1", "label": "START RECORDING", "text": "START RECORDING" },
    { "key": "2", "label": "STOP RECORDING", "text": "STOP RECORDING" },
    { "key": "3", "label": "START TASK", "text": "START TASK" },
    { "key": "4", "label": "STOP TASK", "text": "STOP TASK" }
  ],
  "session_fields": [
    { "id": "behaviorists", "label": "Behaviorist(s)" },
    { "id": "animal_id", "label": "Simia (monkey)" },
    { "id": "animal_weight", "label": "Weight" },
    { "id": "total_liquid_ml", "label": "Total liquid consumed (mL)" },
    { "id": "notes", "label": "Optional notes" }
  ]
}
```
