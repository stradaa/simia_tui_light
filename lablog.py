#!/usr/bin/env python3
import argparse
import json
import os
import shutil
from datetime import datetime
from html import escape
from pathlib import Path

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

    def write_all(self):
        if not self.file_path:
            return
        with self.file_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(self.entries) + "\n")

    def append_entry(self, text: str):
        lines = self.render_entry_lines(text)
        self.entries.extend(lines)
        self.event_line_counts.append(len(lines))
        self.write_all()
        return lines

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
        if upper == "LOGGING RESUMED":
            return self.wrap_standalone_line(f"[{ts}] ··· LOGGING RESUMED ···")
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
        return self.append_entry("---")

    def note(self, text: str):
        text = (text or "").strip()
        if text:
            return self.append_entry(text)
        return []

    def undo(self):
        if self.event_line_counts:
            count = self.event_line_counts.pop()
            removed = self.entries[-count:]
            del self.entries[-count:]
            self.write_all()
            return removed
        return None

    def stop(self):
        lines = self.append_entry("SESSION END")
        self.session_started = False
        return lines

    def reload_config(self):
        self.config, self.config_loaded = load_config(self.config_path)

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

    # --- UI-free session lifecycle (driven by the Textual app) ---

    def begin_new_session(self, session_data, copy_target_root):
        self.session_data = dict(session_data or {})
        self.session_date = datetime.now().strftime("%Y-%m-%d")
        self.session_started_at = self.tshort()
        self.copy_target_root = copy_target_root or None
        self.recording_index = 0
        self.current_task = None
        self.event_line_counts = []

        animal_id = self.session_data.get("animal_id", "")
        animal_part = self.sanitize(animal_id) if animal_id else "animal"
        file_date = datetime.now().strftime("%y%m%d")
        out_dir = self.ensure_output_dir()
        base_path = out_dir / f"{file_date}_{animal_part}.md"
        self.file_path = self.next_available_path(base_path)

        self.entries = self.build_header()
        self.write_all()
        self.session_started = True
        return self.file_path

    def resume_session(self, path: Path, copy_target_root):
        import re

        session = parse_log_file(path)
        if session is None:
            return None
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return None

        self.file_path = path
        self.entries = [line.rstrip("\r\n") for line in lines]
        self.copy_target_root = copy_target_root or None
        self.event_line_counts = []

        header = session["header"]
        data = {}
        for field in self.get_session_fields():
            value = header.get(field["label"], "")
            if value and value != "N/A":
                data[field["id"]] = value
        self.session_data = data

        self.session_date = header.get("Date", "") or datetime.now().strftime("%Y-%m-%d")
        self.session_started_at = session.get("started", "") or self.tshort()

        max_rec = 0
        for event in session["events"]:
            match = re.search(r"REC (\d+) START", event)
            if match:
                max_rec = max(max_rec, int(match.group(1)))
        self.recording_index = max_rec

        start_idx = stop_idx = -1
        task_name = None
        for i, event in enumerate(session["events"]):
            if "START TASK:" in event:
                start_idx = i
                task_name = event.split("START TASK:", 1)[1].strip()
            if "STOP TASK:" in event:
                stop_idx = i
        self.current_task = task_name if start_idx > stop_idx else None

        self.session_started = True
        # Stamp a visible marker so the appended log clearly shows it was
        # reopened/amended rather than written in one continuous sitting.
        self.append_entry("LOGGING RESUMED")
        return session

    def set_recording_index(self, n: int):
        self.recording_index = max(0, int(n))

    def set_field(self, field_id: str, value: str):
        self.session_data[field_id] = value
        self.rebuild_header()

    def set_total_liquid(self, value: str):
        self.session_data["total_liquid_ml"] = value
        self.rebuild_header()

    def event_section_lines(self):
        if "## Events" in self.entries:
            idx = self.entries.index("## Events")
            return self.entries[idx + 1 :]
        return []

    # --- UI-free external copy ---

    def external_copy_folder(self):
        root = str(self.copy_target_root or "").strip()
        if not root:
            return None
        return Path(root).expanduser() / self.session_folder_name()

    def do_external_copy(self, create_missing: bool = False):
        if not self.file_path:
            return {"status": "skipped", "message": "No session file."}
        folder = self.external_copy_folder()
        if folder is None:
            return {"status": "skipped", "message": "External copy disabled for this session."}
        if not folder.is_dir():
            if not create_missing:
                return {"status": "missing_folder", "message": str(folder), "folder": str(folder)}
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                return {"status": "error", "message": f"Could not create folder: {exc}"}
        target_path = folder / self.file_path.name
        try:
            shutil.copy2(self.file_path, target_path)
        except Exception as exc:
            return {"status": "error", "message": f"Copy failed: {exc}"}
        return {"status": "copied", "message": str(target_path)}


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

    from tui import run_app

    return run_app(logger)


if __name__ == "__main__":
    raise SystemExit(main())
