#!/usr/bin/env python3
"""Textual front-end for the SIMIA lab logger.

The pure logging/state logic lives in ``lablog.py`` (the ``Logger`` class and
module-level helpers). This module only handles presentation and input:
a full-screen Textual app with a scrolling, color-coded event pane, modal
dialogs for every text entry (so arrow keys / backspace / multiline paste all
work), a startup wizard (new session or continue an existing log), and a way to
correct the current recording number.
"""

import time
from pathlib import Path

from rich.markup import escape

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import (
    Button,
    Header,
    Input,
    Label,
    OptionList,
    RadioButton,
    RadioSet,
    RichLog,
    Select,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option

from .lablog import compute_session_summary, parse_log_file

try:
    from .ascii_art import HEADER, MONKEY_FACES, STATE_LABELS
except ImportError:  # pragma: no cover
    HEADER = ""
    MONKEY_FACES = {}
    STATE_LABELS = {}


# --------------------------------------------------------------------------- #
# Rose Pine theme
# --------------------------------------------------------------------------- #

# Official Rose Pine palette.
RP = {
    "base": "#191724",
    "surface": "#1f1d2e",
    "overlay": "#26233a",
    "muted": "#6e6a86",
    "subtle": "#908caa",
    "text": "#e0def4",
    "love": "#eb6f92",
    "gold": "#f6c177",
    "rose": "#ebbcba",
    "pine": "#31748f",
    "foam": "#9ccfd8",
    "iris": "#c4a7e7",
}

ROSE_PINE = Theme(
    name="rose-pine",
    primary=RP["iris"],
    secondary=RP["pine"],
    accent=RP["rose"],
    foreground=RP["text"],
    background=RP["base"],
    surface=RP["surface"],
    panel=RP["overlay"],
    success=RP["foam"],
    warning=RP["gold"],
    error=RP["love"],
    dark=True,
    variables={
        "text-muted": RP["subtle"],
        "text-disabled": RP["muted"],
        "border": RP["overlay"],
        "block-cursor-foreground": RP["base"],
        "input-selection-background": RP["overlay"],
    },
)


# --------------------------------------------------------------------------- #
# Personality: the little monkey's mood line
# --------------------------------------------------------------------------- #

# Colour each mood so the one-line mood bar reads at a glance.
MOOD_COLORS = {
    "ready": RP["subtle"],
    "waiting": RP["muted"],
    "rec_start": RP["foam"],
    "rec_stop": RP["love"],
    "liquid": RP["pine"],
    "trial": RP["gold"],
}

# Seconds of no activity before the monkey gets bored/sleepy.
IDLE_SECONDS = 90
# How long a one-off reaction (juice!) lingers before reverting to base mood.
FLASH_SECONDS = 4


def summary_face(summary: dict) -> str:
    """Pick a monkey face for the end-of-session summary based on how it went."""
    if not MONKEY_FACES:
        return ""
    s = summary
    if s["liquid_ml"] <= 0 and s["recordings"] == 0 and s["tasks"] == 0:
        return MONKEY_FACES.get("sleepy", "")  # a whole lot of nothing
    trials = s["trials_success"] + s["trials_fail"]
    if trials and s["trials_success"] >= s["trials_fail"]:
        return MONKEY_FACES.get("happy", "")
    if s["liquid_ml"] > 0:
        return MONKEY_FACES.get("sweet", "")
    return MONKEY_FACES.get("cool", "")


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #

def colorize(line: str) -> str:
    """Turn one raw markdown log line into Rich markup for the event pane.

    Kept deliberately restrained: timestamps muted, REC start/stop the only
    strong accents, everything else close to the default foreground.
    """
    s = line.rstrip()
    if not s.strip():
        return ""
    if s.strip() == "---":
        return f"[{RP['muted']}]" + ("─" * 24) + "[/]"

    up = s.upper()
    if ">>> REC" in up and "START" in up:
        return f"[{RP['foam']}]{escape(s)}[/]"
    if "<<< REC" in up and "STOP" in up:
        return f"[{RP['love']}]{escape(s)}[/]"
    if "LOGGING RESUMED" in up:
        return f"[{RP['gold']}]{escape(s)}[/]"

    if s.startswith("- ["):
        close = s.find("] ")
        if close != -1:
            stamp = s[3:close]
            body = s[close + 2 :]
            bup = body.upper()
            if bup.startswith("LIQUID"):
                color = RP["pine"]
            elif bup.startswith("START TASK") or bup.startswith("STOP TASK"):
                color = RP["gold"]
            elif bup.startswith("SESSION END"):
                color = RP["iris"]
            else:
                color = RP["text"]
            return f"[{RP['muted']}]{escape(stamp)}[/]  [{color}]{escape(body)}[/]"
    return escape(s)


def select_options(values, current):
    """Build Select option tuples, ensuring ``current`` is always available."""
    opts = []
    seen = set()
    for v in values:
        v = str(v)
        opts.append((v, v))
        seen.add(v)
    current = str(current or "").strip()
    if current and current not in seen:
        opts.insert(0, (current, current))
    return opts


def dialog(title: str, classes: str = "dialog") -> Vertical:
    """A modal container whose title is rendered in its top border."""
    box = Vertical(classes=classes)
    box.border_title = title
    return box


# --------------------------------------------------------------------------- #
# Reusable confirm dialog
# --------------------------------------------------------------------------- #

class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, prompt: str, yes_label: str = "Yes", no_label: str = "No"):
        super().__init__()
        self.prompt = prompt
        self.yes_label = yes_label
        self.no_label = no_label

    def compose(self) -> ComposeResult:
        with dialog("Confirm"):
            yield Static(self.prompt, classes="dialog-body")
            with Horizontal(classes="buttons"):
                yield Button(self.yes_label, variant="primary", id="yes")
                yield Button(self.no_label, id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


# --------------------------------------------------------------------------- #
# Startup wizard screens
# --------------------------------------------------------------------------- #

class StartScreen(ModalScreen[str]):
    BINDINGS = [Binding("escape", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        with dialog("Simia Lab Log", "dialog wide tall"):
            with VerticalScroll(classes="body"):
                if HEADER:
                    yield Static(HEADER, classes="banner")
                else:
                    yield Static("SIMIA Lab Log", classes="dialog-body")
            with Horizontal(classes="buttons"):
                yield Button("New session", variant="primary", id="new")
                yield Button("Continue existing log", id="continue")
                yield Button("Settings", id="settings")
                yield Button("Quit", id="quit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)

    def action_quit(self) -> None:
        self.dismiss("quit")


class NewSessionScreen(ModalScreen):
    """Form to fill session metadata for a brand new log."""

    BINDINGS = [Binding("escape", "cancel", "Back")]

    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        self._fields = logger.get_session_fields()

    def compose(self) -> ComposeResult:
        with dialog("New session", "dialog wide tall"):
            with VerticalScroll(classes="form"):
                for field in self._fields:
                    fid = field["id"]
                    options = self.logger.get_field_options(fid)
                    default = self.logger.get_field_default(fid)
                    yield Label(field["label"], classes="field-label")
                    if options:
                        opts = select_options(options, default)
                        value = default if default else Select.BLANK
                        yield Select(opts, value=value, allow_blank=True, id=f"f_{fid}")
                    else:
                        yield Input(value=default, id=f"f_{fid}")
            with Horizontal(classes="buttons"):
                yield Button("Start session", variant="primary", id="start")
                yield Button("Back", id="back")

    def _collect(self) -> dict:
        data = {}
        for field in self._fields:
            fid = field["id"]
            widget = self.query_one(f"#f_{fid}")
            if isinstance(widget, Select):
                value = widget.value
                data[fid] = "" if value is Select.BLANK else str(value)
            else:
                data[fid] = widget.value.strip()
        return data

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.dismiss(self._collect())
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ContinueScreen(ModalScreen):
    """Pick a recent log to resume, or type a path."""

    BINDINGS = [Binding("escape", "cancel", "Back")]

    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        self._paths = self._recent_logs()

    def _recent_logs(self):
        out_dir = Path(self.logger.config.get("output_dir", "logs"))
        if not out_dir.exists():
            return []
        files = sorted(out_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[:40]

    def compose(self) -> ComposeResult:
        with dialog("Continue an existing log", "dialog wide tall"):
            yield Input(placeholder="…or type a path and press Enter", id="path")
            options = []
            for p in self._paths:
                session = parse_log_file(p)
                if session:
                    date = session["header"].get("Date", "?")
                    monkey = session["header"].get("Simia (monkey)", "?")
                    label = f"{date}  ·  {monkey}  ·  {p.name}"
                else:
                    label = p.name
                options.append(Option(label))
            if options:
                yield OptionList(*options, id="logs")
            else:
                yield Static("No logs found in the output directory.", classes="hint")
            with Horizontal(classes="buttons"):
                yield Button("Back", id="back")

    def on_mount(self) -> None:
        try:
            self.query_one("#logs", OptionList).focus()
        except Exception:
            self.query_one("#path", Input).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self._paths[event.option_index])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if value:
            self.dismiss(Path(value).expanduser())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class CopyDestScreen(ModalScreen):
    """Choose where the final markdown log is copied (or skip)."""

    BINDINGS = [Binding("escape", "skip", "Skip")]

    def __init__(self, logger, animal_hint: str = ""):
        super().__init__()
        self.logger = logger
        self.animal_hint = animal_hint or ""
        targets = logger.get_copy_targets()
        if self.animal_hint:
            match = [t for t in targets if logger.target_matches_monkey(t, self.animal_hint)]
            if not match:
                inferred = logger.infer_copy_target_for_monkey(targets, self.animal_hint)
                if inferred:
                    targets = [inferred] + targets
        self.targets = targets
        self.default_index = 0
        for i, t in enumerate(targets):
            if self.animal_hint and logger.target_matches_monkey(t, self.animal_hint):
                self.default_index = i
                break

    def compose(self) -> ComposeResult:
        with dialog("Copy destination", "dialog wide tall"):
            yield Static(
                "Highlight a destination, then press Enter or “Use this destination”.\n"
                "At session end the log is copied to <dest>/<YYMMDD>/<file>.md",
                classes="hint",
            )
            options = []
            for t in self.targets:
                options.append(Option(f"{t['label']}\n   {t['path']}"))
            options.append(Option("⊘  Skip — keep the log in logs/ only"))
            yield OptionList(*options, id="dests")
            yield Input(placeholder="…or type a custom parent folder and press Enter", id="path")
            yield Static("", id="dest-selected", classes="dest-selected")
            with Horizontal(classes="buttons"):
                yield Button("Use this destination", variant="primary", id="confirm")
                yield Button("Skip", id="skip")

    def on_mount(self) -> None:
        dests = self.query_one("#dests", OptionList)
        if self.targets:
            dests.highlighted = self.default_index
        dests.focus()
        self._update_preview()

    def _update_preview(self) -> None:
        sel = self.query_one("#dest-selected", Static)
        idx = self.query_one("#dests", OptionList).highlighted
        if idx is not None and idx < len(self.targets):
            target = self.targets[idx]
            folder = self.logger.build_copy_preview_path(target["path"])
            sel.update(
                f"[b]Selected:[/] {escape(target['label'])}\n"
                f"→ will copy to: {escape(str(folder))}/"
            )
        else:
            sel.update("[b]Selected:[/] no external copy — log kept in logs/ only")

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        self._update_preview()

    def _confirm_highlighted(self) -> None:
        idx = self.query_one("#dests", OptionList).highlighted
        if idx is not None and idx < len(self.targets):
            self.dismiss(self.targets[idx]["path"])
        else:
            self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index < len(self.targets):
            self.dismiss(self.targets[event.option_index]["path"])
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value or None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self._confirm_highlighted()
        else:
            self.dismiss(None)

    def action_skip(self) -> None:
        self.dismiss(None)


class EndSessionScreen(ModalScreen[str]):
    """Final confirmation before ending: spell out exactly what will be saved
    where, and let the user flip save/skip or change the destination."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, logger):
        super().__init__()
        self.logger = logger

    def compose(self) -> ComposeResult:
        root = str(self.logger.copy_target_root or "").strip()
        local = self.logger.file_path
        with dialog("End session", "dialog wide"):
            yield Static(
                f"Local log (always kept):\n   {escape(str(local))}",
                classes="hint",
            )
            if root:
                folder = self.logger.build_copy_preview_path(root)
                yield Static(
                    f"[b]✓ External copy ON[/] — this log WILL be saved to:\n"
                    f"   {escape(str(folder))}",
                    classes="dest-selected",
                )
            else:
                yield Static(
                    "[b]✗ External copy OFF[/] — the log will stay in logs/ only.",
                    classes="dest-selected",
                )
            with Horizontal(classes="buttons"):
                if root:
                    yield Button("End & save copy", variant="primary", id="save")
                    yield Button("End without copy", id="nosave")
                    yield Button("Change path…", id="change")
                else:
                    yield Button("End (local only)", variant="primary", id="nosave")
                    yield Button("Choose a copy path…", id="change")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)

    def action_cancel(self) -> None:
        self.dismiss("cancel")


class SettingsScreen(ModalScreen[bool]):
    """Edit defaults and options in-app so users never touch the JSON.

    Reachable from the start screen, as the first-run setup wizard, and with
    `S` during a live session. Dismisses True when settings were saved.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    # (config field id, human label) for the three list-backed fields.
    LIST_FIELDS = [
        ("behaviorists", "Behaviorist(s)"),
        ("animal_id", "Simia (monkey)"),
        ("project", "Project"),
    ]

    def __init__(self, logger, setup: bool = False):
        super().__init__()
        self.logger = logger
        self.setup = setup

    @staticmethod
    def _csv(values) -> str:
        return ", ".join(str(v) for v in values if str(v).strip())

    def _targets_text(self) -> str:
        lines = []
        for t in self.logger.get_copy_targets():
            label = str(t.get("label", "")).strip()
            path = str(t.get("path", "")).strip()
            lines.append(f"{label} = {path}" if label and label != path else path)
        return "\n".join(lines)

    def compose(self) -> ComposeResult:
        cfg = self.logger.config
        options = cfg.get("field_options", {})
        defaults = cfg.get("field_defaults", {})
        title = "Welcome — set up Simia Log" if self.setup else "Settings"
        with dialog(title, "dialog wide tall"):
            yield Static(
                "Choices are comma-separated. These become the dropdowns and "
                "pre-filled defaults on the new-session form.",
                classes="hint",
            )
            with VerticalScroll(classes="form"):
                for fid, label in self.LIST_FIELDS:
                    opts = options.get(fid, []) if isinstance(options, dict) else []
                    default = defaults.get(fid, "") if isinstance(defaults, dict) else ""
                    yield Label(f"{label} — choices", classes="field-label")
                    yield Input(value=self._csv(opts), id=f"opt_{fid}")
                    yield Label(f"{label} — default", classes="field-label")
                    yield Input(value=str(default or ""), id=f"def_{fid}")

                yield Label("Tasks — choices", classes="field-label")
                yield Input(value=self._csv(cfg.get("tasks", [])), id="tasks")

                yield Label("Logs folder", classes="field-label")
                yield Input(value=str(cfg.get("output_dir", "")), id="output_dir")

                yield Label(
                    "Copy destinations — one per line, “Label = /path”",
                    classes="field-label",
                )
                yield TextArea(self._targets_text(), id="copy_targets")
            with Horizontal(classes="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    @staticmethod
    def _parse_csv(raw: str):
        return [part.strip() for part in raw.split(",") if part.strip()]

    @staticmethod
    def _parse_targets(text: str):
        targets = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" in line:
                label, path = line.split("=", 1)
                label, path = label.strip(), path.strip()
            else:
                label, path = "", line
            if path:
                targets.append({"label": label or Path(path).name or path, "path": path})
        return targets

    def _save(self) -> None:
        import copy

        cfg = copy.deepcopy(self.logger.config)
        cfg.setdefault("field_options", {})
        cfg.setdefault("field_defaults", {})
        for fid, _label in self.LIST_FIELDS:
            cfg["field_options"][fid] = self._parse_csv(self.query_one(f"#opt_{fid}", Input).value)
            cfg["field_defaults"][fid] = self.query_one(f"#def_{fid}", Input).value.strip()
        cfg["tasks"] = self._parse_csv(self.query_one("#tasks", Input).value)
        cfg["output_dir"] = self.query_one("#output_dir", Input).value.strip() or cfg.get(
            "output_dir", ""
        )
        cfg["copy_on_stop_targets"] = self._parse_targets(
            self.query_one("#copy_targets", TextArea).text
        )
        self.logger.save_config(cfg)
        self.dismiss(True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self._save()
        else:
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


# --------------------------------------------------------------------------- #
# Live-session modals
# --------------------------------------------------------------------------- #

class TaskStartModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks

    def compose(self) -> ComposeResult:
        with dialog("Start task", "dialog wide"):
            if self.tasks:
                with RadioSet(id="tasks"):
                    for i, t in enumerate(self.tasks):
                        yield RadioButton(t, value=(i == 0))
            yield Label("…or a custom task name")
            yield Input(placeholder="custom task", id="custom")
            with Horizontal(classes="buttons"):
                yield Button("Start", variant="primary", id="start")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "start":
            self.dismiss(None)
            return
        custom = self.query_one("#custom", Input).value.strip()
        if custom:
            self.dismiss(custom)
            return
        if self.tasks:
            idx = self.query_one("#tasks", RadioSet).pressed_index
            if idx is not None and idx >= 0:
                self.dismiss(self.tasks[idx])
                return
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class TaskStopModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, task_label):
        super().__init__()
        self.task_label = task_label

    def compose(self) -> ComposeResult:
        with dialog(f"Stop task: {self.task_label}", "dialog wide"):
            yield Label("Trials (successful/failed), e.g. 12/3")
            yield Input(placeholder="12/3", id="trials")
            with Horizontal(classes="buttons"):
                yield Button("Stop task", variant="primary", id="stop")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stop":
            self.dismiss(self.query_one("#trials", Input).value.strip())
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)


class EditMetadataModal(ModalScreen):
    """Edit any session header field inline — replaces the old /edit flow."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        self._fields = logger.get_session_fields()

    def compose(self) -> ComposeResult:
        with dialog("Edit session details", "dialog wide tall"):
            with VerticalScroll(classes="form"):
                for field in self._fields:
                    fid = field["id"]
                    current = self.logger.session_data.get(fid, "")
                    options = self.logger.get_field_options(fid)
                    yield Label(field["label"], classes="field-label")
                    if options:
                        opts = select_options(options, current)
                        value = current if current else Select.BLANK
                        yield Select(opts, value=value, allow_blank=True, id=f"e_{fid}")
                    else:
                        yield Input(value=current, id=f"e_{fid}")
            with Horizontal(classes="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save":
            self.dismiss(None)
            return
        result = {}
        for field in self._fields:
            fid = field["id"]
            widget = self.query_one(f"#e_{fid}")
            if isinstance(widget, Select):
                value = widget.value
                result[fid] = "" if value is Select.BLANK else str(value)
            else:
                result[fid] = widget.value.strip()
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SetRecModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, current: int):
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        with dialog("Correct current recording number"):
            yield Static(
                f"Currently {self.current}. The next START will use this + 1.",
                classes="hint",
            )
            yield Input(value=str(self.current), type="integer", id="rec")
            with Horizontal(classes="buttons"):
                yield Button("Set", variant="primary", id="set")
                yield Button("Cancel", id="cancel")

    def _submit(self) -> None:
        raw = self.query_one("#rec", Input).value.strip()
        try:
            self.dismiss(int(raw))
        except ValueError:
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "set":
            self._submit()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpModal(ModalScreen):
    BINDINGS = [Binding("escape", "close", "Close"), Binding("h", "close", "Close")]

    def __init__(self, help_text: str):
        super().__init__()
        self.help_text = help_text

    def compose(self) -> ComposeResult:
        with dialog("Keys", "dialog wide"):
            yield Static(self.help_text, classes="help-body")
            with Horizontal(classes="buttons"):
                yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class SummaryModal(ModalScreen):
    """End-of-session recap: duration and headline tallies."""

    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self, summary: dict, duration: str, file_path):
        super().__init__()
        self.summary = summary
        self.duration = duration
        self.file_path = file_path

    @staticmethod
    def _fmt_ml(value: float) -> str:
        return f"{value:.0f}" if float(value).is_integer() else f"{value:.1f}"

    def compose(self) -> ComposeResult:
        s = self.summary
        rows = [
            ("Duration", self.duration or "—"),
            ("Recordings", str(s["recordings"])),
            ("Tasks run", str(s["tasks"])),
            ("Trials (ok / fail)", f"{s['trials_success']} / {s['trials_fail']}"),
            ("Liquid", f"{self._fmt_ml(s['liquid_ml'])} mL"),
            ("Notes", str(s["notes"])),
        ]
        face = summary_face(s)
        with dialog("Session summary", "dialog wide"):
            if face:
                yield Static(face, classes="summary-face")
            for label, value in rows:
                with Horizontal(classes="summary-row"):
                    yield Static(label, classes="summary-label")
                    yield Static(f"[b]{escape(value)}[/]", classes="summary-value")
            yield Static(f"[dim]{escape(str(self.file_path))}[/]", classes="hint")
            with Horizontal(classes="buttons"):
                yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


# --------------------------------------------------------------------------- #
# Main logging screen
# --------------------------------------------------------------------------- #

class LoggingScreen(Screen):
    BINDINGS = [Binding("escape", "cancel_inline", "Cancel", show=False)]

    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        self.input_active = False
        self.cmd_mode = None
        self._started_monotonic = None
        self._clock_timer = None
        self._showing_placeholder = False
        self._recording_active = False
        self._task_active = False
        self._last_activity = 0.0
        self._flash_key = None
        self._flash_until = 0.0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="statusbar")
        if STATE_LABELS:
            yield Static("", id="moodbar")
        yield RichLog(markup=True, wrap=True, id="log")
        yield Static("", id="hintbar")
        with Horizontal(id="cmdbar", classes="hidden"):
            yield Static("", id="cmdprompt")
            yield Input(id="cmdline")

    # -- population / refresh ------------------------------------------------ #

    def populate(self) -> None:
        self._started_monotonic = time.monotonic()
        self._last_activity = self._started_monotonic
        self._task_active = bool(self.logger.current_task)
        if self._clock_timer is None:
            self._clock_timer = self.set_interval(1.0, self._tick)
        self.refresh_status()
        self.refresh_hint()
        self.refresh_mood()
        self.reload_log_pane()
        log = self.query_one("#log", RichLog)
        log.focus()
        if self.logger.file_path:
            self.app.notify(
                str(self.logger.file_path),
                title="Logging started",
                severity="information",
            )

    def _elapsed_str(self) -> str:
        if self._started_monotonic is None:
            return ""
        secs = int(time.monotonic() - self._started_monotonic)
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def refresh_status(self) -> None:
        lg = self.logger
        monkey = lg.session_data.get("animal_id", "") or "—"
        task = lg.current_task or "—"
        fname = lg.file_path.name if lg.file_path else "—"
        elapsed = self._elapsed_str()
        clock = f"⏱ [b]{elapsed}[/]   " if elapsed else ""
        text = (
            f"[b]{escape(monkey)}[/]   "
            f"REC [b]{lg.recording_index}[/]   "
            f"task [b]{escape(task)}[/]   "
            f"{clock}"
            f"[dim]{escape(fname)}[/]"
        )
        self.query_one("#statusbar", Static).update(text)

    # -- the monkey's mood --------------------------------------------------- #

    def _tick(self) -> None:
        self.refresh_status()
        self.refresh_mood()

    def _bump_activity(self) -> None:
        self._last_activity = time.monotonic()

    def _flash_mood(self, key: str) -> None:
        """Show a one-off reaction (e.g. juice!) that fades back to base mood."""
        self._flash_key = key
        self._flash_until = time.monotonic() + FLASH_SECONDS
        self.refresh_mood()

    def _base_mood(self, now: float) -> str:
        if self._task_active:
            return "trial"
        if self._recording_active:
            return "rec_start"
        if now - self._last_activity > IDLE_SECONDS:
            return "waiting"
        return "ready"

    def refresh_mood(self) -> None:
        if not STATE_LABELS:
            return
        now = time.monotonic()
        if self._flash_key and now < self._flash_until:
            key = self._flash_key
        else:
            self._flash_key = None
            key = self._base_mood(now)
        label = STATE_LABELS.get(key, STATE_LABELS.get("ready", ""))
        color = MOOD_COLORS.get(key, RP["subtle"])
        self.query_one("#moodbar", Static).update(f"[{color}]{escape(label)}[/]")

    def refresh_hint(self) -> None:
        cfg = self.logger.config
        macros = cfg.get("macros", [])
        macro_bits = " ".join(
            f"[b]{m.get('key', '?')}[/] {m.get('label', m.get('text', ''))}" for m in macros
        )
        keys = (
            f"[b]{cfg.get('note_key', 'n')}[/] note  "
            f"[b]{cfg.get('liquid_key', 'l')}[/] juice  "
            f"[b]{cfg.get('mark_key', 'm')}[/] mark  "
            f"[b]{cfg.get('undo_key', 'u')}[/] undo  "
            f"[b]c[/] set-rec  "
            f"[b]/[/] edit  "
            f"[b]S[/] settings  "
            f"[b]{cfg.get('reload_key', 'r')}[/] reload  "
            f"[b]{cfg.get('print_key', 'p')}[/] bottom  "
            f"[b]{cfg.get('help_key', 'h')}[/] help  "
            f"[b]{cfg.get('stop_key', 'q')}[/] end"
        )
        self.query_one("#hintbar", Static).update(f"{macro_bits}\n{keys}")

    def reload_log_pane(self) -> None:
        log = self.query_one("#log", RichLog)
        log.clear()
        lines = self.logger.event_section_lines()
        if not any(line.strip() for line in lines):
            log.write(
                f"[{RP['muted']}]  No events yet — your actions will appear here. "
                f"Press [b]h[/b] for help.[/]"
            )
            self._showing_placeholder = True
        else:
            for line in lines:
                log.write(colorize(line))
            self._showing_placeholder = False
        log.scroll_end(animate=False)

    def write_lines(self, lines) -> None:
        real = list(lines or [])
        # Clear the empty-state placeholder once the first real entry arrives.
        if self._showing_placeholder and any(line.strip() for line in real):
            self.reload_log_pane()
            return
        log = self.query_one("#log", RichLog)
        for line in real:
            log.write(colorize(line))
        log.scroll_end(animate=False)

    # -- key dispatch -------------------------------------------------------- #

    def on_key(self, event) -> None:
        ch = event.character
        if ch is None or not self.logger.session_started or self.input_active:
            return
        if self.handle_char(ch):
            self._bump_activity()
            self.refresh_mood()
            event.stop()
            event.prevent_default()

    def handle_char(self, ch: str) -> bool:
        cfg = self.logger.config
        if ch == cfg.get("note_key", "n"):
            self.open_inline("note")
        elif ch == cfg.get("liquid_key", "l"):
            self.open_inline("liquid")
        elif ch == cfg.get("mark_key", "m"):
            self.write_lines(self.logger.mark())
        elif ch == cfg.get("undo_key", "u"):
            self.action_undo()
        elif ch == cfg.get("reload_key", "r"):
            self.logger.reload_config()
            self.refresh_hint()
            self.app.notify("Config reloaded.", title="Config", severity="information")
        elif ch == cfg.get("print_key", "p"):
            self.reload_log_pane()
        elif ch == "c":
            self.action_set_rec()
        elif ch == "/":
            self.action_edit_metadata()
        elif ch == "S":
            self.action_settings()
        elif ch == cfg.get("help_key", "h"):
            self.action_help()
        elif ch == cfg.get("stop_key", "q"):
            self.action_end()
        else:
            for m in cfg.get("macros", []):
                if ch == str(m.get("key", "")):
                    self.run_macro(m)
                    return True
            return False
        return True

    # -- actions ------------------------------------------------------------- #

    def run_macro(self, macro) -> None:
        text = macro.get("text") or macro.get("label") or ""
        upper = text.strip().upper()
        if upper == "START TASK":
            self.app.push_screen(
                TaskStartModal(self.logger.config.get("tasks", [])), self._after_task_start
            )
        elif upper == "STOP TASK":
            label = self.logger.current_task or "UNKNOWN"
            self.app.push_screen(TaskStopModal(label), self._after_task_stop)
        elif text:
            self.write_lines(self.logger.append_entry(text))
            if upper == "START RECORDING":
                self._recording_active = True
                self._flash_mood("rec_start")
            elif upper == "STOP RECORDING":
                self._recording_active = False
                self._flash_mood("rec_stop")
            self.refresh_status()
            self.refresh_mood()

    def _after_task_start(self, task) -> None:
        if task:
            self.logger.current_task = task
            self._task_active = True
            self.write_lines(self.logger.append_entry(f"START TASK: {task}"))
            self.refresh_status()
            self.refresh_mood()

    def _after_task_stop(self, trials) -> None:
        if trials is None:
            return
        label = self.logger.current_task or "UNKNOWN"
        if trials:
            self.write_lines(self.logger.append_entry(f"STOP TASK: {label} [{trials}]"))
        else:
            self.write_lines(self.logger.append_entry(f"STOP TASK: {label}"))
        self._task_active = False
        self.refresh_mood()

    # -- inline bottom prompt (note / juice) -------------------------------- #

    def open_inline(self, mode: str) -> None:
        self.cmd_mode = mode
        self.input_active = True
        prompt = "note ›" if mode == "note" else "juice mL ›"
        self.query_one("#cmdprompt", Static).update(prompt)
        self.query_one("#cmdbar").remove_class("hidden")
        inp = self.query_one("#cmdline", Input)
        inp.value = ""
        inp.focus()

    def close_inline(self) -> None:
        self.input_active = False
        self.cmd_mode = None
        self.query_one("#cmdbar").add_class("hidden")
        self.query_one("#log", RichLog).focus()

    def action_cancel_inline(self) -> None:
        if self.input_active:
            self.close_inline()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "cmdline":
            return
        mode = self.cmd_mode
        value = event.value
        self.close_inline()
        self._bump_activity()
        if mode == "note":
            if value.strip():
                self.write_lines(self.logger.note(value))
        elif mode == "liquid":
            self._log_liquid_quick(value)

    def _log_liquid_quick(self, raw: str) -> None:
        parts = raw.split()
        if not parts:
            return
        amount = parts[0]
        ltype = "diluted juice"
        if len(parts) > 1:
            token = parts[1].lower()
            ltype = "water" if token.startswith("w") else " ".join(parts[1:])
        self.write_lines(self.logger.append_entry(f"LIQUID: {amount} mL ({ltype})"))
        self._flash_mood("liquid")

    def action_undo(self) -> None:
        removed = self.logger.undo()
        if removed:
            self.reload_log_pane()
            self.refresh_status()
            self.app.notify(
                " | ".join(x for x in removed if x.strip()),
                title="Undone",
                severity="information",
            )
        else:
            self.app.notify("Nothing to undo.", title="Undo", severity="warning")

    def action_set_rec(self) -> None:
        self.app.push_screen(SetRecModal(self.logger.recording_index), self._after_set_rec)

    def _after_set_rec(self, value) -> None:
        if value is None:
            return
        self.logger.set_recording_index(value)
        self.refresh_status()
        self.app.notify(
            f"Recording counter set to {self.logger.recording_index}.",
            title="Recording counter",
            severity="information",
        )

    def action_edit_metadata(self) -> None:
        self.app.push_screen(EditMetadataModal(self.logger), self._after_edit)

    def _after_edit(self, result) -> None:
        if result is None:
            return
        changed = False
        for fid, value in result.items():
            if self.logger.session_data.get(fid, "") != value:
                self.logger.session_data[fid] = value
                changed = True
        if changed:
            self.logger.rebuild_header()
            self.reload_log_pane()
            self.refresh_status()
            self.app.notify("Session details updated.", title="Saved", severity="information")

    def action_settings(self) -> None:
        self.app.push_screen(SettingsScreen(self.logger), self._after_settings)

    def _after_settings(self, saved) -> None:
        if saved:
            self.refresh_hint()
            self.refresh_status()
            self.app.notify("Settings saved.", title="Settings", severity="information")

    def action_help(self) -> None:
        cfg = self.logger.config
        lines = ["Macros:"]
        for m in cfg.get("macros", []):
            lines.append(f"  {m.get('key', '?')}   {m.get('label', m.get('text', ''))}")
        lines += [
            "",
            "Live keys:",
            f"  {cfg.get('note_key', 'n')}   note (inline prompt at the bottom)",
            f"  {cfg.get('liquid_key', 'l')}   juice: type mL + enter (add ' w' for water)",
            f"  {cfg.get('mark_key', 'm')}   section mark",
            f"  {cfg.get('undo_key', 'u')}   undo last entry (this session)",
            "  c   correct the current recording number",
            "  /   edit session details",
            "  S   settings (defaults, options, folders)",
            f"  {cfg.get('reload_key', 'r')}   reload config",
            f"  {cfg.get('print_key', 'p')}   jump to newest / re-render",
            f"  {cfg.get('help_key', 'h')}   this help",
            f"  {cfg.get('stop_key', 'q')}   end session",
        ]
        self.app.push_screen(HelpModal("\n".join(lines)))

    def action_end(self) -> None:
        self.app.push_screen(EndSessionScreen(self.logger), self._after_end_decision)

    def _after_end_decision(self, decision) -> None:
        if decision in (None, "cancel"):
            return
        if decision == "change":
            animal = self.logger.session_data.get("animal_id", "")
            self.app.push_screen(
                CopyDestScreen(self.logger, animal_hint=animal),
                self._after_change_dest,
            )
            return
        if decision == "nosave":
            self.logger.copy_target_root = None
            self.write_lines(self.logger.stop())
            self._show_summary(
                lambda: self._finish("Session ended — log kept in logs/ only.")
            )
            return
        # decision == "save"
        self.write_lines(self.logger.stop())
        self._show_summary(lambda: self._do_copy(create_missing=False))

    def _show_summary(self, after) -> None:
        if self._clock_timer is not None:
            self._clock_timer.stop()
            self._clock_timer = None
        summary = compute_session_summary(self.logger.entries)
        self.app.push_screen(
            SummaryModal(summary, self._elapsed_str(), self.logger.file_path),
            lambda _result: after(),
        )

    def _after_change_dest(self, copy_root) -> None:
        # A returned path updates the destination; skipping (None) keeps the
        # current choice — use "End without copy" to deliberately clear it.
        if copy_root:
            self.logger.copy_target_root = copy_root
            self.app.notify(
                str(copy_root), title="Copy destination set", severity="information"
            )
        self.app.push_screen(EndSessionScreen(self.logger), self._after_end_decision)

    def _do_copy(self, create_missing: bool) -> None:
        result = self.logger.do_external_copy(create_missing=create_missing)
        status = result["status"]
        if status == "missing_folder":
            self.app.push_screen(
                ConfirmModal(
                    f"Copy folder does not exist:\n{result['folder']}\nCreate it now?",
                    "Create",
                    "Skip",
                ),
                lambda ok: self._do_copy(True) if ok else self._finish("Copy skipped."),
            )
            return
        if status == "copied":
            self._finish(f"Copied log to {result['message']}")
        else:
            self._finish(result["message"])

    def _finish(self, message: str) -> None:
        self.app.exit(message=f"{message}\nSession ended. Log: {self.logger.file_path}")


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #

class LabLogApp(App):
    CSS_PATH = "tui.tcss"
    TITLE = "SIMIA Lab Log"

    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        self.logging_screen = LoggingScreen(logger)

    def on_mount(self) -> None:
        self.register_theme(ROSE_PINE)
        self.theme = "rose-pine"
        self.push_screen(self.logging_screen)
        self.run_startup()

    @work
    async def run_startup(self) -> None:
        try:
            await self._startup_flow()
        except Exception:
            import traceback

            self.bell()
            self.exit(message="Startup error:\n" + traceback.format_exc())

    async def _startup_flow(self) -> None:
        # First run with no saved config: open Settings as a setup wizard.
        if not self.logger.config_loaded:
            await self.push_screen_wait(SettingsScreen(self.logger, setup=True))
        while True:
            mode = await self.push_screen_wait(StartScreen())
            if mode in (None, "quit"):
                self.exit()
                return
            if mode == "settings":
                await self.push_screen_wait(SettingsScreen(self.logger))
                continue
            if mode == "continue":
                path = await self.push_screen_wait(ContinueScreen(self.logger))
                if path is None:
                    continue
                animal = self._animal_from_path(path)
                copy_root = await self.push_screen_wait(
                    CopyDestScreen(self.logger, animal_hint=animal)
                )
                if self.logger.resume_session(path, copy_root) is None:
                    self.notify("Could not read that log.", severity="error")
                    continue
            elif mode == "new":
                data = await self.push_screen_wait(NewSessionScreen(self.logger))
                if data is None:
                    continue
                copy_root = await self.push_screen_wait(
                    CopyDestScreen(self.logger, animal_hint=data.get("animal_id", ""))
                )
                self.logger.begin_new_session(data, copy_root)
            else:
                continue
            self.logging_screen.populate()
            return

    @staticmethod
    def _animal_from_path(path) -> str:
        session = parse_log_file(Path(path))
        if session:
            return session["header"].get("Simia (monkey)", "")
        return ""


def run_app(logger) -> int:
    LabLogApp(logger).run()
    return 0
