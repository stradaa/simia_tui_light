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
- Session fields can be selectively filled at startup per session (for example, `1,2` to fill only behaviorist and monkey).
- During session setup:
  - `/back` goes to previous field
  - `/skip` leaves current field blank
  - Press `Enter` at the selection prompt to fill all fields
  - Unselected fields stay blank and can be updated later with `/edit`
  - If configured, `Behaviorist(s)`, `Simia (monkey)`, and `Project` show numbered choices and optional defaults
  - Press `Enter` on one of those fields to use its configured default value
- During live logging:
  - Press `/` then run `/edit Weight` (or `/edit 3`) to update metadata header fields mid-session.
  - Press `l` then choose `2` to set `Total liquid consumed (mL)` in the header at session end.

## User config (`lablog_config.json`)
If `lablog_config.json` is missing or invalid, `lablog.py` now prompts for a minimal user-specific config and writes it automatically.

This config is meant to hold personalized defaults and numbered selection lists so you do not need to retype common values every session.

If `copy_on_stop_dir` is set, the session log is still always saved locally in `output_dir`. At session end, `lablog.py` checks for a matching `YYMMDD` subfolder under that configured parent directory. If it is missing, the script prompts to create it, then copies the `.md` file there if you confirm.

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
    { "id": "project", "label": "Project" },
    { "id": "animal_weight", "label": "Weight" },
    { "id": "total_liquid_ml", "label": "Total liquid consumed (mL)" },
    { "id": "notes", "label": "Optional notes" }
  ],
  "field_options": {
    "behaviorists": ["Alex", "Sam"],
    "animal_id": ["SimiaA", "SimiaB"],
    "project": ["Motor mapping", "Reach training"]
  },
  "field_defaults": {
    "behaviorists": "Alex",
    "animal_id": "SimiaA",
    "project": "Motor mapping"
  },
  "copy_on_stop_dir": "C:\\Users\\Alex\\Documents\\Academics\\Penn"
}
```
