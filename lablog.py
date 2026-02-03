#!/usr/bin/env python3
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

DEFAULT_CONFIG = {
    "output_dir": "logs",
    "macros": [
        {"key": "1", "label": "START RECORDING", "text": "START RECORDING"},
        {"key": "2", "label": "STOP RECORDING", "text": "STOP RECORDING"},
        {"key": "3", "label": "START TASK", "text": "START TASK"},
        {"key": "4", "label": "STOP TASK", "text": "STOP TASK"},
        {"key": "5", "label": "FIX CAMERA", "text": "FIX CAMERA"},
        {"key": "6", "label": "PAUSE TASK", "text": "PAUSE TASK"},
        {"key": "7", "label": "RESUME TASK", "text": "RESUME TASK"},
        {"key": "8", "label": "ADJUST LIGHTING/CAMERA", "text": "ADJUST LIGHTING/CAMERA"},
        {"key": "9", "label": "SLEEPY", "text": "SLEEPY"},
    ],
    "tasks": ["simple touch", "center out reach"],
    "note_key": "n",
    "mark_key": "m",
    "liquid_key": "l",
    "undo_key": "u",
    "reload_key": "r",
    "stop_key": "q",
    "help_key": "h",
    "timestamp_format": "%Y-%m-%d %H:%M:%S",
    "line_time_format": "%H:%M:%S",
}

IS_WINDOWS = os.name == "nt"


def load_config(path: Path):
    if not path.exists():
        return DEFAULT_CONFIG, False
    try:
        with path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return DEFAULT_CONFIG, False

    merged = DEFAULT_CONFIG.copy()
    merged.update({k: v for k, v in cfg.items() if k in merged})
    # Ensure macros list is valid
    if isinstance(cfg.get("macros"), list):
        merged["macros"] = cfg["macros"]
    return merged, True


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
        print("Behaviorist(s): ", end="", flush=True)
        behaviorists = input().strip()
        print("Simia (monkey): ", end="", flush=True)
        animal_id = input().strip()
        print("Weight: ", end="", flush=True)
        animal_weight = input().strip()
        print("Optional notes: ", end="", flush=True)
        notes = input().strip()

        out_dir = self.ensure_output_dir()
        beh_part = self.sanitize(behaviorists) if behaviorists else "behaviorists"
        animal_part = self.sanitize(animal_id) if animal_id else "animal"
        filename = f"{file_date}_{beh_part}_{animal_part}.md"
        self.file_path = out_dir / filename

        header = [
            "# Session Log",
            f"- Date: {date_str}",
            f"- Behaviorist(s): {behaviorists or 'N/A'}",
            f"- Simia: {animal_id or 'N/A'}",
            f"- Weight: {animal_weight or 'N/A'}",
            f"- Notes: {notes or 'N/A'}",
            f"- Started: [{self.tshort()}]",
            "",
            "## Events",
        ]
        self.entries = header.copy()
        self.write_all()
        self.session_started = True
        print(f"Session file: {self.file_path}")

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
        self.session_started = False

    def reload_config(self):
        self.config, self.config_loaded = load_config(self.config_path)

    def print_menu(self):
        macros = self.config.get("macros", [])
        self.print_left("")
        self.print_left("Commands:")
        for m in macros:
            key = m.get("key", "?")
            label = m.get("label", m.get("text", ""))
            self.print_left(f"  {key} = {label}")
        self.print_left("  n = note, l = liquid, m = mark, u = undo, r = reload config, h = help, q = stop")
        self.print_left("Press a key...")

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
            return f"LIQUID: {amount} mL ({liquid_type})"
        if amount:
            return f"LIQUID: {amount} mL"
        return "LIQUID"


def main():
    config_path = Path("lablog_config.json")
    logger = Logger(config_path)

    if not logger.config_loaded:
        print("Using default config (lablog_config.json not found or invalid).")

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
                entry = logger.prompt_liquid()
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
