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

## Export print-ready packets
Use export mode to scan saved session logs and generate a condensed HTML packet for printing.

Run:

```bash
python lablog.py --export
```

The export flow will prompt for:
- `Simia (monkey)` as a required filter
- `Project` as an optional filter
- start date
- end date

This is designed so older logs without a `Project` header can still be included when you leave the project filter blank.

After filtering, the script shows a preview list of matching sessions before generating the packet. Example:

```text
Matching sessions:
  1. 2026-03-11 | project omitted | 260311_Bowser.md
  2. 2026-03-12 | project omitted | 260312_Bowser.md
  3. 2026-03-13 | project omitted | 260313_Bowser.md
```

If you confirm, `lablog.py` writes an HTML file into `exports/` with a filename based on the selected monkey, optional project, and date range.

The generated HTML is print-optimized:
- low-ink black-on-white styling
- a compact `Matching Sessions` index at the top
- `Matching Sessions` kept on page 1 before session details begin
- sessions kept intact while allowing multiple sessions per page when space allows
- session filename shown in small text for traceability
- timestamps preserved for every event
- event order preserved exactly as recorded
- empty metadata fields omitted instead of shown as `N/A`

Open the generated `.html` file in your browser and print it directly or print to PDF.

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

The session log is always saved locally in `output_dir`. If copy destinations are configured, `lablog.py` shows them during session setup after you choose `Simia (monkey)`. It picks a default only when the destination label or path contains the monkey name, clearly previews the exact `YYMMDD/<file>.md` copy path, and lets you choose another destination, type a custom path, or skip the external copy for that session.

At session end, `lablog.py` checks for the matching `YYMMDD` subfolder under the selected parent directory. If it is missing, the script prompts to create it, then copies the `.md` file there if you confirm.

Older configs with only `copy_on_stop_dir` still work. For multiple destinations, use `copy_on_stop_targets`.

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
    "behaviorists": ["Alex", "Jake", "Indie", "Seokhee", "Katie", "Betty"],
    "animal_id": ["Bowser", "Snorlax", "Troopa"],
    "project": ["BCI (Cursor Control)"]
  },
  "field_defaults": {
    "behaviorists": "Alex",
    "animal_id": "Bowser",
    "project": "BCI (Cursor Control)"
  },
  "copy_on_stop_targets": [
    {
      "label": "Bowser behavior folder",
      "path": "/mnt/sraid/Bowser_Behavior_AlexRig"
    },
    {
      "label": "Snorlax behavior folder",
      "path": "/mnt/sraid/Snorlax_Behavior_AlexRig"
    }
  ],
  "copy_on_stop_dir": "",
  "tasks": ["simple touch", "center out reach"],
  "note_key": "n",
  "mark_key": "m",
  "liquid_key": "l",
  "undo_key": "u",
  "reload_key": "r",
  "print_key": "p",
  "stop_key": "q",
  "help_key": "h",
  "timestamp_format": "%Y-%m-%d %H:%M:%S",
  "line_time_format": "%H:%M:%S"
}
```
