#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from html import escape
from pathlib import Path

try:
    from ascii_art import MONKEY_FACES, HEADER, STATE_LABELS
except ImportError:
    MONKEY_FACES = {}
    HEADER = ""
    STATE_LABELS = {}

DEFAULT_CONFIG = {
    "output_dir": "logs",
    "macros": [
        {"key": "1", "label": "START RECORDING", "text": "START RECORDING"},
        {"key": "2", "label": "STOP RECORDING", "text": "STOP RECORDING"},
        {"key": "3", "label": "START TASK", "text": "START TASK"},
        {"key": "4", "label": "STOP TASK", "text": "STOP TASK"},
    ],
    "session_fields": [
        {"id": "behaviorists", "label": "Behaviorist(s)"},
        {"id": "animal_id", "label": "Simia (monkey)"},
        {"id": "project", "label": "Project"},
        {"id": "animal_weight", "label": "Weight"},
        {"id": "total_liquid_ml", "label": "Total liquid consumed (mL)"},
        {"id": "notes", "label": "Optional notes"},
    ],
    "field_options": {
        "behaviorists": [],
        "animal_id": [],
        "project": [],
    },
    "field_defaults": {
        "behaviorists": "",
        "animal_id": "",
        "project": "",
    },
    "copy_on_stop_dir": "",
    "copy_on_stop_targets": [],
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
    "line_time_format": "%H:%M:%S",
}

IS_WINDOWS = os.name == "nt"


def normalize_config(cfg):
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged.update({k: v for k, v in cfg.items() if k in merged})

    if isinstance(cfg.get("macros"), list):
        merged["macros"] = cfg["macros"]

    if isinstance(cfg.get("session_fields"), list):
        merged["session_fields"] = cfg["session_fields"]

    field_options = DEFAULT_CONFIG["field_options"].copy()
    cfg_field_options = cfg.get("field_options", {})
    if isinstance(cfg_field_options, dict):
        for key, value in cfg_field_options.items():
            if isinstance(value, list):
                field_options[key] = [str(item).strip() for item in value if str(item).strip()]
    merged["field_options"] = field_options

    field_defaults = DEFAULT_CONFIG["field_defaults"].copy()
    cfg_field_defaults = cfg.get("field_defaults", {})
    if isinstance(cfg_field_defaults, dict):
        for key, value in cfg_field_defaults.items():
            if value is None:
                continue
            field_defaults[key] = str(value).strip()
    merged["field_defaults"] = field_defaults

    copy_targets = []
    cfg_copy_targets = cfg.get("copy_on_stop_targets", [])
    if isinstance(cfg_copy_targets, list):
        for item in cfg_copy_targets:
            if isinstance(item, dict):
                path = str(item.get("path", "")).strip()
                label = str(item.get("label", "")).strip()
            else:
                path = str(item).strip()
                label = ""
            if path:
                copy_targets.append({"label": label or path, "path": path})

    old_copy_dir = str(cfg.get("copy_on_stop_dir", "") or "").strip()
    if old_copy_dir and not any(target["path"] == old_copy_dir for target in copy_targets):
        copy_targets.insert(0, {"label": "Configured copy folder", "path": old_copy_dir})

    merged["copy_on_stop_targets"] = copy_targets
    return merged


def load_config(path: Path):
    if not path.exists():
        return DEFAULT_CONFIG, False
    try:
        with path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return DEFAULT_CONFIG, False

    return normalize_config(cfg), True


def prompt_list_values(prompt: str):
    print(prompt)
    print("Enter comma-separated values. Leave blank for none.")
    raw = input("> ").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def prompt_default_value(label: str, options):
    if not options:
        return ""

    print(f"Default for {label}:")
    for i, option in enumerate(options, start=1):
        print(f"  {i}. {option}")
    print("Press Enter for no default.")
    raw = input("> ").strip()
    if not raw:
        return ""
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(options):
            return options[idx - 1]
    return raw


def prompt_copy_targets():
    print("Optional copy-on-stop destinations:")
    print("Each destination should be the parent folder for a monkey/project.")
    print("Example: C:\\Users\\Alex\\Documents\\Academics\\Penn\\Bowser_Behavior_AlexRig")
    print("Enter one destination per line. Leave blank when done.")
    targets = []
    while True:
        raw = input("> ").strip()
        if not raw:
            break
        label = Path(raw).name or raw
        targets.append({"label": label, "path": raw})
    return targets


def create_config_interactively(path: Path):
    print("")
    print("lablog_config.json was not found or could not be read.")
    print("Creating a user config now.")

    cfg = json.loads(json.dumps(DEFAULT_CONFIG))

    behaviorists = prompt_list_values("Behaviorist options")
    animals = prompt_list_values("Animal options")
    projects = prompt_list_values("Project options")

    cfg["field_options"]["behaviorists"] = behaviorists
    cfg["field_options"]["animal_id"] = animals
    cfg["field_options"]["project"] = projects

    cfg["field_defaults"]["behaviorists"] = prompt_default_value("Behaviorist(s)", behaviorists)
    cfg["field_defaults"]["animal_id"] = prompt_default_value("Simia (monkey)", animals)
    cfg["field_defaults"]["project"] = prompt_default_value("Project", projects)

    copy_targets = prompt_copy_targets()
    cfg["copy_on_stop_targets"] = copy_targets
    cfg["copy_on_stop_dir"] = ""

    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")

    print(f"Created config: {path}")
    return normalize_config(cfg)


def prompt_with_options(label: str, options, default_value=""):
    print(label)
    if options:
        for i, option in enumerate(options, start=1):
            suffix = " [default]" if option == default_value and default_value else ""
            print(f"  {i}. {option}{suffix}")
    if default_value:
        print("Press Enter to use the default, or leave blank to skip when no default is shown.")
    raw = input("> ").strip()
    if not raw:
        return default_value.strip()
    if raw.isdigit() and options:
        idx = int(raw)
        if 1 <= idx <= len(options):
            return options[idx - 1]
    return raw


def prompt_date_value(label: str):
    while True:
        print(f"{label} (YYYY-MM-DD):")
        raw = input("> ").strip()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date. Use YYYY-MM-DD.")


def parse_log_file(path: Path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None

    if not lines or lines[0].strip() != "# Session Log":
        return None

    session = {
        "path": path,
        "filename": path.name,
        "header": {},
        "events": [],
        "date": None,
        "started": "",
    }

    in_events = False
    for line in lines[1:]:
        if line.strip() == "## Events":
            in_events = True
            continue
        if in_events:
            if line.strip():
                session["events"].append(line.rstrip())
            continue
        if not line.startswith("- "):
            continue
        payload = line[2:]
        if ":" not in payload:
            continue
        key, value = payload.split(":", 1)
        key = key.strip()
        value = value.strip()
        session["header"][key] = value

    date_text = session["header"].get("Date", "")
    if date_text:
        try:
            session["date"] = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            session["date"] = None

    started_text = session["header"].get("Started", "").strip()
    if started_text.startswith("[") and started_text.endswith("]"):
        started_text = started_text[1:-1].strip()
    session["started"] = started_text
    return session


def sort_session_key(session):
    started = session.get("started") or ""
    return (
        session.get("date") or datetime.max.date(),
        started,
        session.get("filename", ""),
    )


def build_export_filename(monkey, project, start_date, end_date):
    parts = [
        start_date.strftime("%Y-%m-%d"),
        "to",
        end_date.strftime("%Y-%m-%d"),
        monkey or "animal",
    ]
    if project:
        parts.append(project)
    safe = []
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    for part in parts:
        cleaned = "".join(ch if ch in allowed else "_" for ch in str(part).strip())
        safe.append(cleaned.strip("_") or "unknown")
    return "_".join(safe) + ".html"


def render_meta_row(label: str, value: str):
    if not value:
        return ""
    return (
        '<div class="meta-row">'
        f'<div class="meta-label">{escape(label)}</div>'
        f'<div class="meta-value">{escape(value)}</div>'
        "</div>"
    )


def render_event_line(line: str):
    if line.startswith("- [") and "] " in line:
        close = line.find("] ")
        timestamp = line[3:close]
        text = line[close + 2 :]
        return (
            '<div class="event">'
            f'<div class="event-time">{escape(timestamp)}</div>'
            f'<div class="event-text">{escape(text)}</div>'
            "</div>"
        )
    return (
        '<div class="event">'
        '<div class="event-time"></div>'
        f'<div class="event-text">{escape(line)}</div>'
        "</div>"
    )


def render_export_html(monkey, project, start_date, end_date, sessions):
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    project_line = (
        f"<p><strong>Project:</strong> {escape(project)}</p>"
        if project
        else "<p><strong>Project:</strong> All projects</p>"
    )
    index_rows = []
    for i, session in enumerate(sessions, start=1):
        header = session["header"]
        project_text = header.get("Project", "").strip() or "project omitted"
        index_rows.append(
            "<tr>"
            f'<td class="index-num">{i}.</td>'
            f'<td class="index-date">{escape(header.get("Date", "Unknown date"))}</td>'
            f'<td class="index-project">{escape(project_text)}</td>'
            f'<td class="index-file">{escape(session["filename"])}</td>'
            "</tr>"
        )

    sections = []
    for session in sessions:
        header = session["header"]
        meta_html = "".join(
            [
                render_meta_row("Behaviorist(s)", header.get("Behaviorist(s)", "")),
                render_meta_row("Weight", header.get("Weight", "")),
                render_meta_row("Total liquid consumed (mL)", header.get("Total liquid consumed (mL)", "")),
                render_meta_row("Optional notes", header.get("Optional notes", "")),
            ]
        )
        events_html = "\n".join(render_event_line(line) for line in session["events"])
        sections.append(
            f"""
<section class="session">
  <div class="session-header">
    <div>
      <h2>{escape(header.get("Date", "Undated session"))}</h2>
      <p class="session-subtitle">{escape(header.get("Simia (monkey)", monkey or ""))}</p>
    </div>
    <div class="session-file">{escape(session["filename"])}</div>
  </div>
  <div class="session-project">{escape(header.get("Project", "Project omitted"))}</div>
  <div class="meta-grid">{meta_html}</div>
  <div class="events">{events_html}</div>
</section>
""".strip()
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Lab Log Packet</title>
  <style>
    @page {{
      size: letter;
      margin: 0.6in 0.7in;
    }}
    body {{
      color: #111;
      background: #fff;
      font-family: "Georgia", "Times New Roman", serif;
      font-size: 11pt;
      line-height: 1.35;
      margin: 0;
    }}
    .packet-header {{
      border-bottom: 1px solid #888;
      margin-bottom: 18px;
      padding-bottom: 10px;
    }}
    h1 {{
      font-size: 19pt;
      margin: 0 0 6px 0;
      font-weight: 600;
      letter-spacing: 0.02em;
    }}
    .packet-header p {{
      margin: 2px 0;
    }}
    .session {{
      break-inside: avoid;
      page-break-inside: avoid;
      break-before: auto;
      page-break-before: auto;
      padding-top: 2px;
      margin-top: 18px;
    }}
    .session-index {{
      margin: 14px 0 18px 0;
    }}
    .session-index h2 {{
      font-size: 11pt;
      margin: 0 0 6px 0;
      font-weight: 600;
    }}
    .session-index table {{
      border-collapse: collapse;
      width: 100%;
    }}
    .session-index td {{
      border: 0;
      font-size: 8.5pt;
      padding: 1px 6px 1px 0;
      vertical-align: top;
    }}
    .index-num {{
      color: #333;
      width: 28px;
    }}
    .index-date {{
      width: 96px;
      white-space: nowrap;
    }}
    .index-project {{
      color: #444;
    }}
    .index-file {{
      color: #555;
      font-family: "Courier New", monospace;
      text-align: right;
      white-space: nowrap;
      width: 160px;
    }}
    .session:first-of-type {{
      margin-top: 0;
    }}
    .session-header {{
      align-items: baseline;
      border-bottom: 1px solid #bbb;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 8px;
      padding-bottom: 5px;
    }}
    h2 {{
      font-size: 15pt;
      margin: 0;
      font-weight: 600;
    }}
    .session-subtitle {{
      color: #444;
      font-size: 10pt;
      margin: 2px 0 0 0;
    }}
    .session-file {{
      color: #555;
      font-family: "Courier New", monospace;
      font-size: 8.5pt;
      white-space: nowrap;
    }}
    .session-project {{
      font-size: 10pt;
      margin-bottom: 8px;
    }}
    .meta-grid {{
      margin-bottom: 12px;
    }}
    .meta-row {{
      display: flex;
      gap: 10px;
      margin: 1px 0;
    }}
    .meta-label {{
      color: #444;
      flex: 0 0 160px;
      font-size: 9.5pt;
    }}
    .meta-value {{
      flex: 1 1 auto;
      font-size: 9.5pt;
    }}
    .events {{
      border-top: 1px solid #ddd;
      padding-top: 8px;
    }}
    .event {{
      display: grid;
      gap: 10px;
      grid-template-columns: 70px 1fr;
      padding: 1px 0;
    }}
    .event-time {{
      color: #333;
      font-family: "Courier New", monospace;
      font-size: 9pt;
      white-space: nowrap;
    }}
    .event-text {{
      font-size: 10pt;
      word-break: break-word;
    }}
    @media print {{
      .packet-header {{
        page-break-after: avoid;
      }}
      .session-index {{
        break-after: page;
        page-break-after: always;
      }}
    }}
  </style>
</head>
<body>
  <header class="packet-header">
    <h1>Lab Log Packet</h1>
    <p><strong>Monkey:</strong> {escape(monkey)}</p>
    {project_line}
    <p><strong>Date range:</strong> {escape(start_date.strftime("%Y-%m-%d"))} to {escape(end_date.strftime("%Y-%m-%d"))}</p>
    <p><strong>Sessions included:</strong> {len(sessions)}</p>
    <p><strong>Generated:</strong> {escape(generated_at)}</p>
  </header>
  <section class="session-index">
    <h2>Matching Sessions</h2>
    <table>
      {"".join(index_rows)}
    </table>
  </section>
  {"".join(sections)}
</body>
</html>
"""


def export_logs(config):
    output_dir = Path(config.get("output_dir", "logs"))
    if not output_dir.exists():
        print(f"Log directory not found: {output_dir}")
        return 1

    field_options = config.get("field_options", {})
    defaults = config.get("field_defaults", {})
    monkey_options = field_options.get("animal_id", []) if isinstance(field_options, dict) else []
    project_options = field_options.get("project", []) if isinstance(field_options, dict) else []

    print("")
    print("Export print-ready log packet")
    print("Monkey is required. Project is optional.")
    monkey = prompt_with_options("Simia (monkey):", monkey_options, str(defaults.get("animal_id", "")).strip())
    while not monkey:
        print("Monkey is required.")
        monkey = prompt_with_options("Simia (monkey):", monkey_options, str(defaults.get("animal_id", "")).strip())

    project = prompt_with_options("Project (optional):", project_options, "")
    start_date = prompt_date_value("Start date")
    end_date = prompt_date_value("End date")
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    sessions = []
    for path in sorted(output_dir.glob("*.md")):
        session = parse_log_file(path)
        if not session or not session.get("date"):
            continue
        if session["date"] < start_date or session["date"] > end_date:
            continue
        animal_value = session["header"].get("Simia (monkey)", "").strip()
        if animal_value.lower() != monkey.strip().lower():
            continue
        project_value = session["header"].get("Project", "").strip()
        if project and project_value.lower() != project.strip().lower():
            continue
        sessions.append(session)

    sessions.sort(key=sort_session_key)

    print("")
    print("Matching sessions:")
    if not sessions:
        print("  No matching logs found.")
        return 1

    for i, session in enumerate(sessions, start=1):
        header = session["header"]
        project_text = header.get("Project", "").strip() or "project omitted"
        print(
            f"  {i}. {header.get('Date', 'Unknown date')} | "
            f"{project_text} | {session['filename']}"
        )

    print("")
    print(f"Generate packet for {len(sessions)} session(s)? [y/N]: ")
    confirm = input().strip().lower()
    if confirm not in ("y", "yes"):
        print("Export cancelled.")
        return 0

    export_dir = Path("exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    output_name = build_export_filename(monkey, project, start_date, end_date)
    output_path = export_dir / output_name
    html = render_export_html(monkey, project, start_date, end_date, sessions)
    output_path.write_text(html, encoding="utf-8")

    print(f"Created packet: {output_path}")
    print("Open the HTML file in a browser and print to PDF or paper.")
    return 0


class RawInput:
    def __init__(self):
        self._old = None

    def __enter__(self):
        if IS_WINDOWS:
            return self
        import termios
        import tty

        self._old = termios.tcgetattr(sys.stdin.fileno())
        tty.setraw(sys.stdin.fileno())
        return self

    def __exit__(self, exc_type, exc, tb):
        if IS_WINDOWS:
            return False
        import termios

        if self._old:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old)
        return False

    def getch(self):
        if IS_WINDOWS:
            import msvcrt

            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                ch = msvcrt.getch()  # skip special keys
            try:
                return ch.decode("utf-8", errors="ignore")
            except Exception:
                return ""
        else:
            ch = sys.stdin.read(1)
            return ch


class Logger:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config, self.config_loaded = load_config(config_path)
        self.entries = []
        self.event_line_counts = []
        self.file_path = None
        self.session_started = False
        self.recording_index = 0
        self.current_task = None
        self.session_data = {}
        self.session_date = ""
        self.session_started_at = ""
        self.copy_target_root = None

    def ts(self):
        return datetime.now().strftime(self.config["timestamp_format"])

    def tshort(self):
        return datetime.now().strftime(self.config["line_time_format"])

    def sanitize(self, s: str):
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_. "
        cleaned = "".join(c if c in allowed else "_" for c in s.strip())
        cleaned = cleaned.strip().replace(" ", "_")
        return cleaned or "unknown"

    def ensure_output_dir(self):
        out_dir = Path(self.config.get("output_dir", "logs"))
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    def start_session(self):
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_date = datetime.now().strftime("%y%m%d")
        self.print_welcome()
        self.session_data = self.prompt_session_data()
        behaviorists = self.session_data.get("behaviorists", "")
        animal_id = self.session_data.get("animal_id", "")

        self.session_date = date_str
        self.session_started_at = self.tshort()

        out_dir = self.ensure_output_dir()

        # 🔹 Filename is now based on SIMIA, not behaviorist
        animal_part = self.sanitize(animal_id) if animal_id else "animal"
        filename = f"{file_date}_{animal_part}.md"

        base_path = out_dir / filename
        self.file_path = self.next_available_path(base_path)

        header = self.build_header()

        self.entries = header.copy()
        self.write_all()
        self.session_started = True

        print(f"Session file: {self.file_path}")
        self.prompt_copy_destination(animal_id)

    def build_header(self):
        fields = self.get_session_fields()
        lines = [
            "# Session Log",
            f"- Date: {self.session_date or datetime.now().strftime('%Y-%m-%d')}",
        ]
        for field in fields:
            value = self.session_data.get(field["id"], "")
            lines.append(f"- {field['label']}: {value or 'N/A'}")
        started = self.session_started_at or self.tshort()
        lines.append(f"- Started: [{started}]")
        lines.append("")
        lines.append("## Events")
        return lines

    def rebuild_header(self):
        events = []
        if "## Events" in self.entries:
            idx = self.entries.index("## Events")
            events = self.entries[idx + 1 :]
        self.entries = self.build_header() + events
        self.write_all()

    def print_box(self, title: str, lines):
        body = [str(line) for line in lines]
        width = max([len(title)] + [len(line) for line in body]) + 2
        border = "+" + ("-" * (width + 2)) + "+"
        self.print_left(border)
        self.print_left(f"| {title.ljust(width)} |")
        self.print_left(border)
        for line in body:
            self.print_left(f"| {line.ljust(width)} |")
        self.print_left(border)

    def print_welcome(self):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.print_left("")
        if HEADER:
            for line in HEADER.splitlines():
                self.print_left(line)
        self.print_left(f"  started: {ts}")
        self.print_left("")

    def get_session_fields(self):
        fields = self.config.get("session_fields", DEFAULT_CONFIG["session_fields"])
        if not isinstance(fields, list):
            return DEFAULT_CONFIG["session_fields"]
        normalized = []
        for idx, field in enumerate(fields, start=1):
            if not isinstance(field, dict):
                continue
            field_id = str(field.get("id", f"field_{idx}")).strip()
            label = str(field.get("label", field_id)).strip()
            if field_id and label:
                normalized.append({"id": field_id, "label": label})
        if not normalized:
            return DEFAULT_CONFIG["session_fields"]

        # Keep required defaults available even if older custom config omits them.
        existing_ids = {f["id"] for f in normalized}
        for field in DEFAULT_CONFIG["session_fields"]:
            if field["id"] not in existing_ids:
                normalized.append(field)
        return normalized

    def choose_startup_fields(self, fields):
        self.print_box(
            "Session Setup",
            [
                "Choose which fields to fill out now.",
                "Press Enter to fill all fields.",
                "Use comma list, e.g. 1,2 to fill only those now.",
            ],
        )
        for i, field in enumerate(fields, start=1):
            self.print_left(f"  {i}. {field['label']}")
        self.print_left("Fill now: ")
        selection_text = input().strip()
        if not selection_text:
            return list(range(len(fields)))

        parts = [p.strip() for p in selection_text.split(",") if p.strip()]
        if any(not p.isdigit() for p in parts):
            self.print_left("Invalid selection. Filling all fields.")
            return list(range(len(fields)))

        selected = [int(p) - 1 for p in parts]
        if len(set(selected)) != len(selected):
            self.print_left("Invalid selection. Filling all fields.")
            return list(range(len(fields)))
        if any(i < 0 or i >= len(fields) for i in selected):
            self.print_left("Invalid selection. Filling all fields.")
            return list(range(len(fields)))
        return selected

    def get_field_options(self, field_id: str):
        field_options = self.config.get("field_options", {})
        if not isinstance(field_options, dict):
            return []
        values = field_options.get(field_id, [])
        if not isinstance(values, list):
            return []
        return [str(value).strip() for value in values if str(value).strip()]

    def get_field_default(self, field_id: str):
        field_defaults = self.config.get("field_defaults", {})
        if not isinstance(field_defaults, dict):
            return ""
        value = field_defaults.get(field_id, "")
        return str(value).strip() if value is not None else ""

    def parse_option_selection(self, raw: str, options):
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if not parts:
            return None
        if all(part.isdigit() for part in parts):
            values = []
            for part in parts:
                idx = int(part)
                if idx < 1 or idx > len(options):
                    return None
                values.append(options[idx - 1])
            return ", ".join(values)
        return raw

    def prompt_animal_field(self, field, options, default_value):
        face_keys = list(MONKEY_FACES.keys())
        self.print_left(f"{field['label']}:")
        self.print_left("")
        for i, option in enumerate(options):
            face_key = face_keys[i % len(face_keys)]
            face_lines = MONKEY_FACES[face_key].split("\n")
            suffix = " [default]" if option == default_value and default_value else ""
            self.print_left(f"  {face_lines[0]}   {i + 1}. {option}{suffix}")
            for line in face_lines[1:]:
                self.print_left(f"  {line}")
            self.print_left("")
        self.print_left("  Enter number, name, /skip, or /back.")
        if default_value:
            self.print_left("  Press Enter for default.")
        value = input().strip()
        if not value:
            return default_value if (options or default_value) else ""
        parsed = self.parse_option_selection(value, options)
        if parsed is None:
            self.print_left("Invalid selection.")
            return None
        return parsed

    def prompt_field_value(self, field):
        options = self.get_field_options(field["id"])
        default_value = self.get_field_default(field["id"])

        if field["id"] == "animal_id" and options and MONKEY_FACES:
            return self.prompt_animal_field(field, options, default_value)

        self.print_left(f"{field['label']}: ")
        if options:
            self.print_left("  Options:")
            for i, option in enumerate(options, start=1):
                suffix = " [default]" if option == default_value and default_value else ""
                self.print_left(f"    {i}. {option}{suffix}")
            self.print_left("  Enter a number, comma list, custom text, /skip, or /back.")
            if default_value:
                self.print_left("  Press Enter to use the default.")

        value = input().strip()
        if not value:
            return default_value if options or default_value else ""
        if options:
            parsed = self.parse_option_selection(value, options)
            if parsed is None:
                self.print_left("Invalid selection.")
                return None
            return parsed
        return value

    def get_copy_targets(self):
        targets = self.config.get("copy_on_stop_targets", [])
        if not isinstance(targets, list):
            targets = []

        normalized = []
        for item in targets:
            if isinstance(item, dict):
                path = str(item.get("path", "") or "").strip()
                label = str(item.get("label", "") or "").strip()
            else:
                path = str(item or "").strip()
                label = ""
            if path:
                normalized.append({"label": label or path, "path": path})

        value = self.config.get("copy_on_stop_dir", "")
        old_copy_dir = str(value).strip() if value is not None else ""
        if old_copy_dir and not any(target["path"] == old_copy_dir for target in normalized):
            normalized.insert(0, {"label": "Configured copy folder", "path": old_copy_dir})

        return normalized

    def target_matches_monkey(self, target, animal_id):
        animal_norm = self.normalize_token(animal_id)
        if not animal_norm:
            return False
        haystack = f"{target.get('label', '')} {target.get('path', '')}"
        return animal_norm in self.normalize_token(haystack)

    def infer_copy_target_for_monkey(self, targets, animal_id):
        animal_part = self.sanitize(animal_id) if animal_id else ""
        if not animal_part:
            return None

        marker = "_Behavior_"
        existing_paths = {target["path"] for target in targets}
        for target in targets:
            path_text = str(target.get("path", "") or "").strip()
            if not path_text:
                continue
            path = Path(path_text)
            folder_name = path.name
            marker_index = folder_name.find(marker)
            if marker_index <= 0:
                continue
            inferred_name = f"{animal_part}{folder_name[marker_index:]}"
            inferred_path = str(path.with_name(inferred_name))
            if inferred_path in existing_paths:
                continue
            return {
                "label": f"{inferred_name} (inferred)",
                "path": inferred_path,
            }
        return None

    def session_folder_name(self):
        if self.session_date:
            try:
                return datetime.strptime(self.session_date, "%Y-%m-%d").strftime("%y%m%d")
            except ValueError:
                pass
        return datetime.now().strftime("%y%m%d")

    def build_copy_preview_path(self, copy_root):
        folder = Path(copy_root).expanduser() / self.session_folder_name()
        if self.file_path:
            return folder / self.file_path.name
        return folder

    def confirm_non_matching_copy_target(self, target, animal_id):
        if not animal_id or self.target_matches_monkey(target, animal_id):
            return True
        self.print_left("")
        self.print_left(f"Selected destination does not contain Simia name '{animal_id}'.")
        self.print_left(f"Destination: {target['path']}")
        self.print_left("Use this destination anyway? [y/N]: ")
        choice = input().strip().lower()
        return choice in ("y", "yes")

    def prompt_custom_copy_target(self, animal_id):
        self.print_left("Custom copy parent directory, or /skip: ")
        raw = input().strip()
        if not raw or raw.lower() == "/skip":
            return None
        target = {"label": Path(raw).name or raw, "path": raw}
        if not self.confirm_non_matching_copy_target(target, animal_id):
            self.print_left("Copy skipped.")
            return None
        return target

    def prompt_copy_destination(self, animal_id):
        targets = self.get_copy_targets()
        matching_targets = [target for target in targets if self.target_matches_monkey(target, animal_id)]
        default_target = matching_targets[0] if matching_targets else None
        inferred_target = None
        if default_target is None:
            inferred_target = self.infer_copy_target_for_monkey(targets, animal_id)
            if inferred_target:
                default_target = inferred_target
                targets = [inferred_target] + targets

        self.print_left("")
        self.print_box(
            "Copy Destination",
            [
                "Choose where the final Markdown log should be copied.",
                "The default is a configured folder containing the Simia name.",
            ],
        )

        if targets:
            for i, target in enumerate(targets, start=1):
                suffix = " [default]" if target == default_target else ""
                self.print_left(f"  {i}. {target['label']}{suffix}")
                self.print_left(f"     {target['path']}")
        else:
            self.print_left("No copy destinations are configured.")

        if default_target:
            self.print_left("")
            self.print_left("At session end, this log will be copied to:")
            self.print_left(f"  {self.build_copy_preview_path(default_target['path'])}")
            if inferred_target:
                self.print_left("Inferred from the configured behavior folder pattern.")
            self.print_left("Press Enter to use this destination, choose a number, type a custom path, or /skip.")
        else:
            self.print_left("")
            if animal_id:
                self.print_left(f"No configured copy destination contains Simia name '{animal_id}'.")
            self.print_left("Choose a number, type a custom path, or /skip.")

        while True:
            self.print_left("Copy destination: ")
            raw = input().strip()
            if not raw:
                selected = default_target
            elif raw.lower() == "/skip":
                selected = None
            elif raw.lower() in ("change", "custom"):
                selected = self.prompt_custom_copy_target(animal_id)
            elif raw.isdigit() and targets:
                idx = int(raw)
                if 1 <= idx <= len(targets):
                    selected = targets[idx - 1]
                else:
                    self.print_left("Invalid selection.")
                    continue
            else:
                selected = {"label": Path(raw).name or raw, "path": raw}

            if selected is None:
                self.copy_target_root = None
                self.print_left("External copy disabled for this session.")
                return

            if not self.confirm_non_matching_copy_target(selected, animal_id):
                continue

            self.copy_target_root = selected["path"]
            self.print_left("Selected copy destination:")
            self.print_left(f"  {self.build_copy_preview_path(self.copy_target_root)}")
            return

    def copy_log_to_external_dir(self):
        if not self.file_path:
            return

        copy_root_raw = str(self.copy_target_root or "").strip()
        if not copy_root_raw:
            return

        copy_root = Path(copy_root_raw).expanduser()
        session_folder = copy_root / self.session_folder_name()

        if not session_folder.is_dir():
            self.print_left(f"Copy target not found: {session_folder}")
            self.print_left("Create this folder now? [y/N]: ")
            choice = input().strip().lower()
            if choice not in ("y", "yes"):
                self.print_left("Copy skipped.")
                return
            try:
                session_folder.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                self.print_left(f"Could not create folder: {exc}")
                return

        target_path = session_folder / self.file_path.name
        try:
            shutil.copy2(self.file_path, target_path)
        except Exception as exc:
            self.print_left(f"Copy failed: {exc}")
            return

        self.print_left(f"Copied log to {target_path}")

    def prompt_session_data(self):
        fields = self.get_session_fields()
        selected = self.choose_startup_fields(fields)
        data = {}
        startup_fields = [fields[i] for i in selected]

        self.print_box(
            "Entry Controls",
            [
                "Type /back to edit previous field",
                "Type /skip to leave a field blank",
                "Unselected fields stay blank for later /edit",
            ],
        )

        i = 0
        while i < len(startup_fields):
            field = startup_fields[i]
            value = self.prompt_field_value(field)
            if value is None:
                continue
            if value.lower() == "/back":
                if i > 0:
                    i -= 1
                else:
                    self.print_left("Already at first field.")
                continue
            if value.lower() == "/skip":
                value = ""
            data[field["id"]] = value
            i += 1

        return data

    def normalize_token(self, text: str):
        return "".join(ch.lower() for ch in text if ch.isalnum())

    def resolve_field(self, token: str):
        token = token.strip()
        fields = self.get_session_fields()
        if token.isdigit():
            idx = int(token)
            if 1 <= idx <= len(fields):
                return fields[idx - 1]
            return None

        token_norm = self.normalize_token(token)
        for field in fields:
            if token.lower() == field["id"].lower():
                return field
            if token_norm == self.normalize_token(field["label"]):
                return field
        return None

    def show_session_fields(self):
        self.print_box("Session Fields", ["Editable session metadata"])
        fields = self.get_session_fields()
        for i, field in enumerate(fields, start=1):
            value = self.session_data.get(field["id"], "")
            self.print_left(f"  {i}. {field['label']}: {value or 'N/A'}")

    def edit_session_field(self, token: str):
        field = self.resolve_field(token)
        if not field:
            self.print_left(f"Unknown field: {token}")
            self.show_session_fields()
            return
        current = self.session_data.get(field["id"], "")
        self.print_left(f"Editing {field['label']} (current: {current or 'N/A'}).")
        new_value = self.prompt_field_value(field)
        if new_value is None:
            return
        if new_value.lower() == "/skip":
            new_value = ""
        self.session_data[field["id"]] = new_value
        self.rebuild_header()
        self.print_left(f"Updated {field['label']}.")

    def prompt_slash_command(self):
        self.print_left("")
        self.print_box(
            "Slash Commands",
            [
                "/fields                show session fields",
                "/edit <name|index>     edit one field",
                "/help                  show commands",
            ],
        )
        self.print_left("Slash command: ")
        raw = input().strip()
        if not raw:
            return
        cmd = raw[1:] if raw.startswith("/") else raw
        parts = cmd.split(maxsplit=1)
        action = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if action in ("help", "?"):
            return
        if action in ("fields", "show"):
            self.show_session_fields()
            return
        if action in ("edit", "set"):
            if not arg:
                self.show_session_fields()
                self.print_left("Field to edit: ")
                arg = input().strip()
            if arg:
                self.edit_session_field(arg)
            return
        self.print_left(f"Unknown slash command: {raw}")

    def write_all(self):
        if not self.file_path:
            return
        with self.file_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(self.entries) + "\n")

    def print_state_label(self, text: str):
        if not STATE_LABELS:
            return
        upper = text.strip().upper()
        if upper == "START RECORDING":
            label = STATE_LABELS.get("rec_start")
        elif upper == "STOP RECORDING":
            label = STATE_LABELS.get("rec_stop")
        elif upper.startswith("LIQUID"):
            label = STATE_LABELS.get("liquid")
        else:
            return
        if label:
            self.print_left(label)

    def append_entry(self, text: str):
        lines = self.render_entry_lines(text)
        self.entries.extend(lines)
        self.event_line_counts.append(len(lines))
        self.write_all()
        for line in lines:
            sys.stdout.write("\r" + line + "\n")
            sys.stdout.flush()
        self.print_state_label(text)

    def render_entry_lines(self, text: str):
        ts = self.tshort()
        upper = text.strip().upper()
        if upper == "START RECORDING":
            self.recording_index += 1
            return self.wrap_standalone_line(f"[{ts}] >>> REC {self.recording_index} START >>>")
        if upper == "STOP RECORDING":
            if self.recording_index > 0:
                rec_label = str(self.recording_index)
            else:
                rec_label = "?"
            return self.wrap_standalone_line(f"[{ts}] <<< REC {rec_label} STOP <<<")
        if text.strip() == "---":
            return self.wrap_standalone_line("---")
        return [f"- [{ts}] {text}"]

    def wrap_standalone_line(self, line: str):
        lines = []
        if self.entries and self.entries[-1] != "":
            lines.append("")
        lines.append(line)
        lines.append("")
        return lines

    def mark(self):
        self.append_entry("---")

    def note(self):
        self.clear_line()
        print("Note: ", end="", flush=True)
        note = input().strip()
        if note:
            self.append_entry(note)

    def undo(self):
        if self.event_line_counts:
            count = self.event_line_counts.pop()
            removed = self.entries[-count:]
            del self.entries[-count:]
            self.write_all()
            print(f"Undone: {' | '.join(removed)}")
            return
        print("Nothing to undo.")

    def stop(self):
        self.append_entry("SESSION END")
        self.copy_log_to_external_dir()
        self.session_started = False

    def reload_config(self):
        self.config, self.config_loaded = load_config(self.config_path)

    def print_menu(self):
        macros = self.config.get("macros", [])
        self.print_left("")
        self.print_box(
            "Live Commands",
            [
                "Main logging keys",
                "Press h any time to reprint this menu",
            ],
        )
        for m in macros:
            key = m.get("key", "?")
            label = m.get("label", m.get("text", ""))
            self.print_left(f"  [{key}] {label}")
        self.print_left("  [n] note    [l] liquid    [m] mark")
        self.print_left("  [u] undo    [r] reload    [p] print current log")
        self.print_left("  [/] edit session metadata")
        self.print_left("  [h] help    [q] stop")
        self.print_left("Press a key...")

    def print_entries_snapshot(self):
        self.print_left("")
        self.print_box(
            "Current Session",
            [
                "Reprint of current header and events",
                f"File: {self.file_path}" if self.file_path else "File: N/A",
            ],
        )
        for line in self.entries:
            self.print_left(line)
        self.print_left("")

    def clear_line(self):
        if sys.stdout.isatty():
            # ANSI erase-in-line avoids wrapped whitespace when the terminal is narrow.
            sys.stdout.write("\r\x1b[2K")
        else:
            width = max(shutil.get_terminal_size(fallback=(80, 24)).columns - 1, 1)
            sys.stdout.write("\r" + (" " * width) + "\r")
        sys.stdout.flush()

    def print_left(self, text: str):
        self.clear_line()
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def prompt_task(self):
        tasks = self.config.get("tasks", [])
        if tasks:
            self.print_left("Select task or type a custom name:")
            for i, t in enumerate(tasks, start=1):
                self.print_left(f"  {i} = {t}")
        self.print_left("Task: ")
        choice = input().strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(tasks):
                return tasks[idx - 1]
        return choice

    def prompt_trials(self):
        self.print_left("Trials (successful/failed), e.g. 12/3: ")
        return input().strip()

    def prompt_liquid(self):
        self.print_left("Liquid options:")
        self.print_left("  1 = log liquid event")
        self.print_left("  2 = set final total consumed (header)")
        self.print_left("Choice [1/2]: ")
        choice = input().strip()
        if choice == "2":
            self.print_left("Total liquid consumed (mL): ")
            total_ml = input().strip()
            return {"mode": "set_total", "total_ml": total_ml}

        self.print_left("Liquid amount (mL): ")
        amount = input().strip()
        self.print_left("Liquid type (select or type custom):")
        self.print_left("  1 = water")
        self.print_left("  2 = diluted juice")
        self.print_left("Type: ")
        liquid_type = input().strip()
        if liquid_type == "1":
            liquid_type = "water"
        elif liquid_type == "2":
            liquid_type = "diluted juice"
        if amount and liquid_type:
            return {"mode": "event", "entry": f"LIQUID: {amount} mL ({liquid_type})"}
        if amount:
            return {"mode": "event", "entry": f"LIQUID: {amount} mL"}
        return {"mode": "event", "entry": "LIQUID"}
    
    def next_available_path(self, path: Path) -> Path:
        """
        If path exists, append _01, _02, ... before the suffix.
        """
        if not path.exists():
            return path

        stem = path.stem
        suffix = path.suffix
        parent = path.parent

        i = 1
        while True:
            candidate = parent / f"{stem}_{i:02d}{suffix}"
            if not candidate.exists():
                return candidate
            i += 1


def main():
    config_path = Path("lablog_config.json")
    logger = Logger(config_path)

    if not logger.config_loaded:
        logger.config = create_config_interactively(config_path)
        logger.config_loaded = True

    parser = argparse.ArgumentParser(description="SIMIA TUI logger")
    parser.add_argument(
        "--export",
        action="store_true",
        help="scan saved logs and generate a print-ready HTML packet",
    )
    args = parser.parse_args()

    if args.export:
        return export_logs(logger.config)

    logger.start_session()
    logger.print_menu()

    with RawInput() as inp:
        while logger.session_started:
            ch = inp.getch()
            if not ch:
                continue
            key = ch.strip()
            if not key:
                continue

            if key == logger.config.get("help_key", "h"):
                logger.print_menu()
                continue
            if key == logger.config.get("note_key", "n"):
                # leave raw mode for input
                if not IS_WINDOWS:
                    import termios

                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, inp._old)
                logger.note()
                if not IS_WINDOWS:
                    import tty

                    tty.setraw(sys.stdin.fileno())
                continue
            if key == logger.config.get("liquid_key", "l"):
                if not IS_WINDOWS:
                    import termios

                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, inp._old)
                result = logger.prompt_liquid()
                if result.get("mode") == "set_total":
                    total_ml = result.get("total_ml", "").strip()
                    logger.session_data["total_liquid_ml"] = total_ml
                    logger.rebuild_header()
                    print("Updated header: Total liquid consumed (mL).")
                else:
                    entry = result.get("entry", "")
                    if entry:
                        logger.append_entry(entry)
                if not IS_WINDOWS:
                    import tty

                    tty.setraw(sys.stdin.fileno())
                continue
            if key == logger.config.get("mark_key", "m"):
                logger.mark()
                continue
            if key == logger.config.get("undo_key", "u"):
                logger.undo()
                continue
            if key == logger.config.get("reload_key", "r"):
                logger.reload_config()
                print("Config reloaded.")
                logger.print_menu()
                continue
            if key == logger.config.get("print_key", "p"):
                logger.print_entries_snapshot()
                continue
            if key == "/":
                if not IS_WINDOWS:
                    import termios

                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, inp._old)
                logger.prompt_slash_command()
                if not IS_WINDOWS:
                    import tty

                    tty.setraw(sys.stdin.fileno())
                continue
            if key == logger.config.get("stop_key", "q"):
                if not IS_WINDOWS:
                    import termios

                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, inp._old)
                logger.stop()
                print("Session ended.")
                break

            matched = False
            for m in logger.config.get("macros", []):
                if key == str(m.get("key", "")):
                    text = m.get("text") or m.get("label") or ""
                    upper = text.strip().upper()
                    if upper == "START TASK":
                        if not IS_WINDOWS:
                            import termios

                            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, inp._old)
                        task = logger.prompt_task()
                        if task:
                            logger.current_task = task
                            logger.append_entry(f"START TASK: {task}")
                        if not IS_WINDOWS:
                            import tty

                            tty.setraw(sys.stdin.fileno())
                    elif upper == "STOP TASK":
                        if not IS_WINDOWS:
                            import termios

                            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, inp._old)
                        trials = logger.prompt_trials()
                        task_label = logger.current_task or "UNKNOWN"
                        if trials:
                            logger.append_entry(f"STOP TASK: {task_label} [{trials}]")
                        else:
                            logger.append_entry(f"STOP TASK: {task_label}")
                        if not IS_WINDOWS:
                            import tty

                            tty.setraw(sys.stdin.fileno())
                    elif text:
                        logger.append_entry(text)
                    matched = True
                    break

            if not matched:
                print(f"Unknown key: {key}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. If you want to stop cleanly, press q next time.")
