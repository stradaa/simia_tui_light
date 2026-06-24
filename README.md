# simia_tui_light

A fast, minimal TUI for timestamped experiment logging with customizable macro
hotkeys. The interface is a full-screen [Textual](https://textual.textualize.io/)
app themed with [Rose Pine](https://rosepinetheme.com/): a slim status bar, a
scrolling event pane (each entry printed exactly once — no more double-printed
notes), and compact dialogs that resize to fit small terminal windows. Text entry
happens in focused inputs so arrow keys and backspace work correctly.

## Install

```bash
pip install -r requirements.txt
```

Then run:

```bash
python lablog.py
```

On launch you choose **New session** or **Continue existing log**.

## Keys (live session)

Default macro keys:
- `1` = START RECORDING
- `2` = STOP RECORDING
- `3` = START TASK
- `4` = STOP TASK

Other keys:
- `n` = note (inline prompt at the bottom; the event log stays visible above it — Enter saves, Esc cancels)
- `l` = juice — type the mL and press Enter (defaults to diluted juice; add ` w`, e.g. `30 w`, for water)
- `m` = mark / section break
- `u` = undo last entry (this session)
- `c` = correct the current recording number (after a misclick)
- `/` = edit session details (all header fields in one form)
- `r` = reload config
- `p` = jump to newest / re-render the pane
- `h` = help
- `q` = end session (asks to confirm, then copies the log)

## Continue an existing log

Choose **Continue existing log** at startup to resume appending to a previous
`.md` file instead of starting fresh. Pick a recent log from the list (or type a
path). Resuming restores the header fields, the recording counter (so the next
START continues from the right number), and the active task. Note: `undo` after
resuming only affects entries added in the resumed session.

## Correct the recording number

If you mis-click START/STOP and the recording counter drifts, press `c` and type
the correct number. The next START RECORDING continues from there.

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

## Startup flow
- ASCII welcome banner on the start screen with **New session** / **Continue existing log**.
- The new-session form pre-fills configured defaults; fields with configured
  `field_options` (`Behaviorist(s)`, `Simia (monkey)`, `Project`) show a dropdown,
  the rest are free text. Adjust what you need and start.
- During live logging:
  - Press `/` to edit any header field in a single form (replaces the old
    `/edit Weight` flow). The running `Total liquid consumed (mL)` is one of
    those fields, so set it here.
  - Note and juice entry happen inline at the bottom of the screen, so the
    event log stays visible while you type.

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
