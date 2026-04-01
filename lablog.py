#!/usr/bin/env python3
import json
import os
import shutil
import sys
from datetime import datetime
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
    merged = DEFAULT_CONFIG.copy()
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

    print("Optional copy-on-stop parent directory:")
    print("Example: C:\\Users\\Alex\\Documents\\Academics\\Penn")
    print("Leave blank to disable.")
    cfg["copy_on_stop_dir"] = input("> ").strip()

    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")

    print(f"Created config: {path}")
    return normalize_config(cfg)


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
        self.file_path = None
        self.session_started = False
        self.recording_index = 0
        self.current_task = None
        self.session_data = {}
        self.session_date = ""
        self.session_started_at = ""

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
        inner = 48
        self.print_left("")
        border = "+" + ("-" * inner) + "+"
        self.print_left(border)
        self.print_left(f"| {'SIMIA TUI'.center(inner - 2)} |")
        self.print_left(f"| {'Behavioral Session Logging'.center(inner - 2)} |")
        self.print_left(border)
        self.print_left(f"| {f'Started: {ts}'.ljust(inner - 2)} |")
        self.print_left(border)
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

    def prompt_field_value(self, field):
        options = self.get_field_options(field["id"])
        default_value = self.get_field_default(field["id"])

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

    def get_copy_on_stop_dir(self):
        value = self.config.get("copy_on_stop_dir", "")
        return str(value).strip() if value is not None else ""

    def copy_log_to_external_dir(self):
        if not self.file_path:
            return

        copy_root_raw = self.get_copy_on_stop_dir()
        if not copy_root_raw:
            return

        copy_root = Path(copy_root_raw).expanduser()
        session_folder = copy_root / datetime.now().strftime("%y%m%d")

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

    def append_entry(self, text: str):
        rendered = self.render_entry_text(text)
        line = f"- [{self.tshort()}] {rendered}"
        self.entries.append(line)
        self.write_all()
        sys.stdout.write("\r" + line + "\n")
        sys.stdout.flush()

    def render_entry_text(self, text: str) -> str:
        upper = text.strip().upper()
        if upper == "START RECORDING":
            self.recording_index += 1
            return f"START RECORDING (REC {self.recording_index})"
        if upper == "STOP RECORDING":
            if self.recording_index > 0:
                return f"STOP RECORDING (REC {self.recording_index})"
            return "STOP RECORDING (REC ?)"
        return text

    def mark(self):
        self.append_entry("---")

    def note(self):
        self.clear_line()
        print("Note: ", end="", flush=True)
        note = input().strip()
        if note:
            self.append_entry(note)

    def undo(self):
        # Avoid undoing header lines
        for i in range(len(self.entries) - 1, -1, -1):
            if self.entries[i].startswith("- ["):
                removed = self.entries.pop(i)
                self.write_all()
                print(f"Undone: {removed}")
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
        sys.stdout.write("\r" + (" " * 120) + "\r")
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


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. If you want to stop cleanly, press q next time.")
