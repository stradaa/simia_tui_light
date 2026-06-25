# simia_tui_light

A fast, keyboard-driven terminal app for **timestamped lab session logging** —
built for behavioral / BCI experiments where someone at the rig needs to record
what happened, when, without taking their eyes off the animal.

You run it before a session, tap single keys to mark recordings, tasks, juice
rewards, and notes as they happen, and it writes a clean, human-readable
Markdown log for you. At the end it can copy that log straight into a per-animal
folder on a shared drive. No spreadsheets, no timestamps typed by hand, no
mouse.

The interface is a full-screen [Textual](https://textual.textualize.io/) app
themed with [Rose Pine](https://rosepinetheme.com/): a slim status bar up top, a
scrolling color-coded event pane in the middle, and a hint bar of available keys
along the bottom. Every text entry happens in a focused input or inline prompt,
so arrow keys, backspace, and paste all behave the way you expect.

```
 Eevee   REC 3   task center out reach   260624_Eevee.md
─────────────────────────────────────────────────────────
 21:37:41   START TASK: center out reach
 21:41:02   LIQUID: 30 mL (diluted juice)
 21:52:10   STOP TASK: center out reach [42/6]

 21:52:33  >>> REC 3 START >>>
 ────────────────────────
 1 START RECORDING  2 STOP RECORDING  3 START TASK  4 STOP TASK
 n note  l juice  m mark  u undo  c set-rec  / edit  ...  q end
```

## Why it exists

During a live session your hands and attention are on the experiment. Typing
full timestamps, remembering recording numbers, and reconstructing what happened
afterward is error-prone. `simia_tui_light` makes the common actions
single-keystroke, stamps the time for you, keeps the running recording counter
straight, and produces a log that's readable as plain text *and* trivial to
parse later for print-ready summaries.

## Highlights

- **One key per action.** Configurable macro hotkeys for the things you log most
  (start/stop recording, start/stop task), plus quick keys for notes, juice, and
  section marks.
- **Always-correct timestamps & recording counter.** The app stamps every entry
  and auto-increments the recording number; if it ever drifts, fix it with one
  key.
- **Plain-Markdown output.** Each session is a readable `.md` file you can open
  anywhere — see [Log format](#log-format).
- **Resume any past log.** Reopen an earlier session and keep appending; the
  point where you resumed is clearly marked in the file.
- **Local + shared-drive saving.** The log is always saved locally; optionally
  copy it to a per-animal network folder, with an explicit confirmation before
  anything is written.
- **Print-ready export.** Generate a condensed, low-ink HTML packet across a date
  range for one animal — open in a browser and print or save as PDF.
- **Yours to configure.** Defaults, dropdown choices, task lists, and every
  hotkey live in one JSON file.

## Install & run

```bash
pip install -r requirements.txt
python lablog.py
```

Requires Python 3 and `textual>=8.2`. On first run, if no config exists, the app
prompts for a few values and writes `lablog_config.json` for you.

## How a session works

```
        ┌─────────────┐
        │ Start screen │  New session  ·  Continue existing log  ·  Quit
        └──────┬───────┘
               │
   New ────────┤──────── Continue
   fill the    │         pick a recent log (or type a path)
   metadata    │
   form        │
               ▼
        ┌──────────────────┐
        │ Copy destination  │  pick where the log will be copied at the end
        └────────┬─────────┘   (auto-selects the folder matching the animal)
                 ▼
        ┌──────────────┐
        │ Live logging  │  tap keys to record events as they happen
        └──────┬───────┘
               │ press  q
               ▼
        ┌──────────────┐
        │ End session   │  confirm save / don't-save / change path, then copy
        └──────────────┘
```

### 1. Start

The welcome screen offers **New session**, **Continue existing log**, or
**Quit**.

### 2. Set up

- **New session** opens a form. Fields with configured options
  (`Behaviorist(s)`, `Simia (monkey)`, `Project`) are dropdowns pre-filled with
  your defaults; everything else is free text. Adjust what you need and start.
- **Continue existing log** lists your recent logs (date · animal · filename) to
  resume, or lets you type a path. See [Resuming a log](#resuming-a-log).

### 3. Choose where it gets copied

Next you pick the **copy destination** — the folder the finished log is copied
into at session end. The app **auto-highlights the destination whose name
matches the animal** you selected and shows a live preview of the exact path it
will write (`<dest>/<YYMMDD>/<file>.md`). You can pick a different destination,
type a custom parent folder, or skip the external copy entirely and keep the log
in `logs/` only. The log is *always* saved locally regardless of this choice.

### 4. Log live

Tap keys to record events (see [Keys](#keys-live-session)). The event pane shows
each entry exactly once, color-coded by type, and stays visible while you type
notes or juice amounts in the inline prompt at the bottom.

### 5. End & copy

Press `q` to end. Before anything is written, a confirmation screen spells out:

- the **local log path** (always kept), and
- whether the **external copy is ON** (with the exact target path) or **OFF**.

From there you can **End & save the copy**, **End without copying**, or **Change
the path** — so you're never surprised about where (or whether) the log lands.
If the target's `YYMMDD` subfolder doesn't exist yet, the app offers to create
it before copying.

## Keys (live session)

| Key | Action |
|-----|--------|
| `1` | START RECORDING *(macro)* |
| `2` | STOP RECORDING *(macro)* |
| `3` | START TASK *(macro — pick from your task list or type a custom name)* |
| `4` | STOP TASK *(macro — prompts for trials, e.g. `12/3`)* |
| `n` | note — inline prompt at the bottom; Enter saves, Esc cancels |
| `l` | juice — type the mL and Enter (diluted juice by default; add ` w`, e.g. `30 w`, for water) |
| `m` | mark / section break |
| `u` | undo the last entry *(this session only)* |
| `c` | correct the current recording number after a misclick |
| `/` | edit session details — all header fields in one form |
| `r` | reload config |
| `p` | jump to newest / re-render the pane |
| `h` | help |
| `q` | end session (confirm, then copy) |

The macro keys (`1`–`4`) and all the single-letter keys are configurable — see
[Configuration](#configuration-lablog_configjson).

> **Recording counter.** START/STOP RECORDING auto-increment the counter shown in
> the status bar. If a misclick throws it off, press `c` and type the correct
> number — the next START continues from there.

## Log format

Each session is a single Markdown file in `output_dir` (default `logs/`), named
`<YYMMDD>_<animal>.md`. A header captures the session metadata; an `## Events`
section holds the timestamped stream:

```markdown
# Session Log
- Date: 2026-06-24
- Behaviorist(s): Alex
- Simia (monkey): Eevee
- Project: BCI (Cursor Control)
- Weight: 9.2
- Total liquid consumed (mL): 45
- Optional notes: N/A
- Started: [21:37:41]

## Events

21:37:55  >>> REC 1 START >>>

- [21:38:10] LIQUID: 15 mL (diluted juice)
- [21:39:02] START TASK: center out reach
- [21:52:10] STOP TASK: center out reach [42/6]

21:52:33  <<< REC 1 STOP <<<
```

Empty header fields are written as `N/A` and can be filled in any time with `/`.

## Resuming a log

Choose **Continue existing log** to append to a previous `.md` instead of
starting fresh. Resuming restores the header fields, the recording counter (so
the next START continues from the right number), and the active task. A
`··· LOGGING RESUMED ···` marker is stamped into the file at the point you
reopened it, so a session that was logged across multiple sittings is obvious at
a glance.

> `undo` (`u`) after resuming only affects entries you add in the resumed
> session — it won't remove anything from before you reopened the file.

## Export print-ready packets

Scan saved logs and generate a condensed, print-optimized HTML packet for one
animal across a date range:

```bash
python lablog.py --export
```

You'll be prompted for:

- **Simia (monkey)** — required filter
- **Project** — optional (leave blank to include older logs that predate the
  `Project` header)
- **start date** and **end date**

The tool shows a preview of matching sessions before generating anything:

```text
Matching sessions:
  1. 2026-03-11 | project omitted | 260311_Bowser.md
  2. 2026-03-12 | project omitted | 260312_Bowser.md
  3. 2026-03-13 | project omitted | 260313_Bowser.md
```

Confirm and it writes an `.html` file into `exports/`, named from the animal,
optional project, and date range. The output is built for printing:

- low-ink black-on-white styling
- a compact **Matching Sessions** index kept on page 1
- sessions kept intact, with multiple per page when they fit
- the source filename shown in small text for traceability
- every timestamp and the exact event order preserved
- empty metadata fields omitted rather than printed as `N/A`

Open it in a browser and print directly, or print to PDF.

## Configuration (`lablog_config.json`)

All personalization lives in `lablog_config.json` next to the script. If it's
missing or invalid, the app prompts for a minimal config and writes it
automatically. Use it to hold your defaults and selection lists so you don't
retype common values every session, define your macros and tasks, and remap any
hotkey.

**Saving & copying.** The log is always saved in `output_dir`. List one or more
shared-drive folders under `copy_on_stop_targets`; the app offers them at setup
and auto-selects the one matching the animal. Older configs that used a single
`copy_on_stop_dir` still work — prefer `copy_on_stop_targets` for multiple
destinations.

| Key | Purpose |
|-----|---------|
| `output_dir` | Where session `.md` files are written locally |
| `macros` | Hotkey → label/text for the macro actions (`1`–`4` by default) |
| `session_fields` | The header fields collected per session (`id` + `label`) |
| `field_options` | Dropdown choices for specific fields |
| `field_defaults` | Pre-filled values in the new-session form |
| `copy_on_stop_targets` | Shared-drive folders to copy the log into at session end |
| `tasks` | Task names offered when you start a task |
| `note_key`, `liquid_key`, `mark_key`, `undo_key`, `reload_key`, `print_key`, `stop_key`, `help_key` | Single-letter hotkeys |
| `timestamp_format`, `line_time_format` | strftime patterns for headers and event lines |

<details>
<summary>Full example config</summary>

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

</details>
