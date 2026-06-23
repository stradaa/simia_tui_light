#!/usr/bin/env python3
"""Textual front-end for the SIMIA lab logger.

The pure logging/state logic lives in ``lablog.py`` (the ``Logger`` class and
module-level helpers). This module only handles presentation and input:
a full-screen Textual app with a scrolling, color-coded event pane, modal
dialogs for every text entry (so arrow keys / backspace / multiline paste all
work), a startup wizard (new session or continue an existing log), and a way to
correct the current recording number.
"""

from pathlib import Path

from rich.markup import escape

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
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

from lablog import parse_log_file

try:
    from ascii_art import HEADER
except ImportError:  # pragma: no cover
    HEADER = ""


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #

def colorize(line: str) -> str:
    """Turn one raw markdown log line into Rich markup for the event pane."""
    s = line.rstrip()
    if not s.strip():
        return ""
    if s.strip() == "---":
        return "[dim]" + ("─" * 36) + "[/]"

    up = s.upper()
    if ">>> REC" in up and "START" in up:
        return f"[bold green]{escape(s)}[/]"
    if "<<< REC" in up and "STOP" in up:
        return f"[bold red]{escape(s)}[/]"

    if s.startswith("- ["):
        close = s.find("] ")
        if close != -1:
            stamp = s[3:close]
            body = s[close + 2 :]
            bup = body.upper()
            if bup.startswith("LIQUID"):
                color = "cyan"
            elif bup.startswith("START TASK") or bup.startswith("STOP TASK"):
                color = "yellow"
            elif bup.startswith("SESSION END"):
                color = "bold magenta"
            else:
                color = "white"
            return f"[dim]{escape(stamp)}[/]  [{color}]{escape(body)}[/]"
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
        with Vertical(classes="dialog"):
            yield Static(self.prompt, classes="dialog-title")
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
        with Vertical(classes="dialog wide"):
            if HEADER:
                yield Static(HEADER, classes="banner")
            yield Static("SIMIA Lab Log", classes="dialog-title")
            with Horizontal(classes="buttons"):
                yield Button("New session", variant="primary", id="new")
                yield Button("Continue existing log", id="continue")
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
        with Vertical(classes="dialog wide"):
            yield Static("New session", classes="dialog-title")
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
        with Vertical(classes="dialog wide"):
            yield Static("Continue an existing log", classes="dialog-title")
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
        with Vertical(classes="dialog wide"):
            yield Static("Copy destination", classes="dialog-title")
            yield Static(
                "At session end the log is copied to <dest>/<YYMMDD>/<file>.md",
                classes="hint",
            )
            yield Input(placeholder="…or type a custom parent folder and press Enter", id="path")
            options = []
            for t in self.targets:
                options.append(Option(f"{t['label']}\n   {t['path']}"))
            options.append(Option("⊘  Skip external copy for this session"))
            yield OptionList(*options, id="dests")

    def on_mount(self) -> None:
        dests = self.query_one("#dests", OptionList)
        if self.targets:
            dests.highlighted = self.default_index

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index < len(self.targets):
            self.dismiss(self.targets[event.option_index]["path"])
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value or None)

    def action_skip(self) -> None:
        self.dismiss(None)


# --------------------------------------------------------------------------- #
# Live-session modals
# --------------------------------------------------------------------------- #

class NoteModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static("Note", classes="dialog-title")
            yield Static("Arrow keys, backspace and paste all work here.", classes="hint")
            yield TextArea(id="note")
            with Horizontal(classes="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#note", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.dismiss(self.query_one("#note", TextArea).text)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class LiquidModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static("Liquid", classes="dialog-title")
            with RadioSet(id="mode"):
                yield RadioButton("Log a liquid event", value=True)
                yield RadioButton("Set final total consumed (header)")
            yield Label("Event amount (mL)")
            yield Input(placeholder="e.g. 1.5", id="amount")
            yield Label("Liquid type")
            yield Input(value="water", id="ltype")
            yield Label("Final total consumed (mL) — for the second option")
            yield Input(placeholder="e.g. 42", id="total")
            with Horizontal(classes="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save":
            self.dismiss(None)
            return
        mode_index = self.query_one("#mode", RadioSet).pressed_index
        if mode_index == 1:
            total = self.query_one("#total", Input).value.strip()
            self.dismiss({"mode": "set_total", "total_ml": total})
            return
        amount = self.query_one("#amount", Input).value.strip()
        ltype = self.query_one("#ltype", Input).value.strip()
        if amount and ltype:
            entry = f"LIQUID: {amount} mL ({ltype})"
        elif amount:
            entry = f"LIQUID: {amount} mL"
        else:
            entry = "LIQUID"
        self.dismiss({"mode": "event", "entry": entry})

    def action_cancel(self) -> None:
        self.dismiss(None)


class TaskStartModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static("Start task", classes="dialog-title")
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
        with Vertical(classes="dialog wide"):
            yield Static(f"Stop task: {self.task_label}", classes="dialog-title")
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
        with Vertical(classes="dialog wide"):
            yield Static("Edit session details", classes="dialog-title")
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
        with Vertical(classes="dialog"):
            yield Static("Correct current recording number", classes="dialog-title")
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
        with Vertical(classes="dialog wide"):
            yield Static("Keys", classes="dialog-title")
            yield Static(self.help_text, classes="help-body")
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
    def __init__(self, logger):
        super().__init__()
        self.logger = logger

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="statusbar")
        yield RichLog(markup=True, wrap=True, id="log")
        yield Static("", id="hintbar")

    # -- population / refresh ------------------------------------------------ #

    def populate(self) -> None:
        self.refresh_status()
        self.refresh_hint()
        self.reload_log_pane()
        log = self.query_one("#log", RichLog)
        log.focus()
        if self.logger.file_path:
            self.app.notify(f"Logging to {self.logger.file_path}")

    def refresh_status(self) -> None:
        lg = self.logger
        monkey = lg.session_data.get("animal_id", "") or "—"
        task = lg.current_task or "—"
        fname = lg.file_path.name if lg.file_path else "—"
        text = (
            f"[b]{escape(monkey)}[/]   "
            f"REC [b]{lg.recording_index}[/]   "
            f"task [b]{escape(task)}[/]   "
            f"[dim]{escape(fname)}[/]"
        )
        self.query_one("#statusbar", Static).update(text)

    def refresh_hint(self) -> None:
        cfg = self.logger.config
        macros = cfg.get("macros", [])
        macro_bits = " ".join(
            f"[b]{m.get('key', '?')}[/] {m.get('label', m.get('text', ''))}" for m in macros
        )
        keys = (
            f"[b]{cfg.get('note_key', 'n')}[/] note  "
            f"[b]{cfg.get('liquid_key', 'l')}[/] liquid  "
            f"[b]{cfg.get('mark_key', 'm')}[/] mark  "
            f"[b]{cfg.get('undo_key', 'u')}[/] undo  "
            f"[b]c[/] set-rec  "
            f"[b]/[/] edit  "
            f"[b]{cfg.get('reload_key', 'r')}[/] reload  "
            f"[b]{cfg.get('print_key', 'p')}[/] bottom  "
            f"[b]{cfg.get('help_key', 'h')}[/] help  "
            f"[b]{cfg.get('stop_key', 'q')}[/] end"
        )
        self.query_one("#hintbar", Static).update(f"{macro_bits}\n{keys}")

    def reload_log_pane(self) -> None:
        log = self.query_one("#log", RichLog)
        log.clear()
        for line in self.logger.event_section_lines():
            log.write(colorize(line))
        log.scroll_end(animate=False)

    def write_lines(self, lines) -> None:
        log = self.query_one("#log", RichLog)
        for line in lines or []:
            log.write(colorize(line))
        log.scroll_end(animate=False)

    # -- key dispatch -------------------------------------------------------- #

    def on_key(self, event) -> None:
        ch = event.character
        if ch is None or not self.logger.session_started:
            return
        if self.handle_char(ch):
            event.stop()
            event.prevent_default()

    def handle_char(self, ch: str) -> bool:
        cfg = self.logger.config
        if ch == cfg.get("note_key", "n"):
            self.action_note()
        elif ch == cfg.get("liquid_key", "l"):
            self.action_liquid()
        elif ch == cfg.get("mark_key", "m"):
            self.write_lines(self.logger.mark())
        elif ch == cfg.get("undo_key", "u"):
            self.action_undo()
        elif ch == cfg.get("reload_key", "r"):
            self.logger.reload_config()
            self.refresh_hint()
            self.app.notify("Config reloaded.")
        elif ch == cfg.get("print_key", "p"):
            self.reload_log_pane()
        elif ch == "c":
            self.action_set_rec()
        elif ch == "/":
            self.action_edit_metadata()
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
            self.refresh_status()

    def _after_task_start(self, task) -> None:
        if task:
            self.logger.current_task = task
            self.write_lines(self.logger.append_entry(f"START TASK: {task}"))
            self.refresh_status()

    def _after_task_stop(self, trials) -> None:
        if trials is None:
            return
        label = self.logger.current_task or "UNKNOWN"
        if trials:
            self.write_lines(self.logger.append_entry(f"STOP TASK: {label} [{trials}]"))
        else:
            self.write_lines(self.logger.append_entry(f"STOP TASK: {label}"))

    def action_note(self) -> None:
        self.app.push_screen(NoteModal(), self._after_note)

    def _after_note(self, text) -> None:
        if text:
            self.write_lines(self.logger.note(text))

    def action_liquid(self) -> None:
        self.app.push_screen(LiquidModal(), self._after_liquid)

    def _after_liquid(self, result) -> None:
        if not result:
            return
        if result.get("mode") == "set_total":
            self.logger.set_total_liquid(result.get("total_ml", "").strip())
            self.app.notify("Updated header: total liquid consumed.")
        else:
            entry = result.get("entry", "")
            if entry:
                self.write_lines(self.logger.append_entry(entry))

    def action_undo(self) -> None:
        removed = self.logger.undo()
        if removed:
            self.reload_log_pane()
            self.refresh_status()
            self.app.notify(f"Undone: {' | '.join(x for x in removed if x.strip())}")
        else:
            self.app.notify("Nothing to undo.", severity="warning")

    def action_set_rec(self) -> None:
        self.app.push_screen(SetRecModal(self.logger.recording_index), self._after_set_rec)

    def _after_set_rec(self, value) -> None:
        if value is None:
            return
        self.logger.set_recording_index(value)
        self.refresh_status()
        self.app.notify(f"Recording counter set to {self.logger.recording_index}.")

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
            self.app.notify("Session details updated.")

    def action_help(self) -> None:
        cfg = self.logger.config
        lines = ["Macros:"]
        for m in cfg.get("macros", []):
            lines.append(f"  {m.get('key', '?')}   {m.get('label', m.get('text', ''))}")
        lines += [
            "",
            "Live keys:",
            f"  {cfg.get('note_key', 'n')}   note (multiline, full editing)",
            f"  {cfg.get('liquid_key', 'l')}   liquid event / set total",
            f"  {cfg.get('mark_key', 'm')}   section mark",
            f"  {cfg.get('undo_key', 'u')}   undo last entry (this session)",
            "  c   correct the current recording number",
            "  /   edit session details",
            f"  {cfg.get('reload_key', 'r')}   reload config",
            f"  {cfg.get('print_key', 'p')}   jump to newest / re-render",
            f"  {cfg.get('help_key', 'h')}   this help",
            f"  {cfg.get('stop_key', 'q')}   end session",
        ]
        self.app.push_screen(HelpModal("\n".join(lines)))

    def action_end(self) -> None:
        self.app.push_screen(
            ConfirmModal("End this session and copy the log?", "End session", "Cancel"),
            self._after_end_confirm,
        )

    def _after_end_confirm(self, ok) -> None:
        if not ok:
            return
        self.write_lines(self.logger.stop())
        self._do_copy(create_missing=False)

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
        while True:
            mode = await self.push_screen_wait(StartScreen())
            if mode in (None, "quit"):
                self.exit()
                return
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
            else:
                data = await self.push_screen_wait(NewSessionScreen(self.logger))
                if data is None:
                    continue
                copy_root = await self.push_screen_wait(
                    CopyDestScreen(self.logger, animal_hint=data.get("animal_id", ""))
                )
                self.logger.begin_new_session(data, copy_root)
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
