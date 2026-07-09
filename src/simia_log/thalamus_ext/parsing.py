"""Parsers for Thalamus log text and config values. Pure functions, no grpc."""

import json
import re
from dataclasses import dataclass

DEFAULT_SUBJECT_REGEX = r"(?P<subject>[^_/]+)_Behavior_(?P<rig>[^_/]+)"

# Params surfaced to the note (radius/hold/reward/goal/mode). The listener
# compares this tuple of fields between trials to detect a difficulty change.
PARAM_FIELDS = ("radius", "hold", "reward_ms", "reward_channel", "reward_scale",
                "control_mode", "goal")


@dataclass
class TrialOutcome:
    task: str
    success: bool
    # Everything below is best-effort: present only when the trial JSON carries
    # it (the Rust Grid task populates ``behav_result``; simpler tasks may not),
    # so every field defaults to None and callers must tolerate that.
    final_outcome: "str | None" = None
    radius: "float | None" = None
    hold: "float | None" = None
    reward_ms: "float | None" = None
    reward_channel: "int | None" = None
    reward_scale: "float | None" = None
    goal: "int | None" = None
    control_mode: "str | None" = None
    move_time_s: "float | None" = None

    def params(self):
        """The subset of fields shown in the PARAMS note line (change key)."""
        return {name: getattr(self, name) for name in PARAM_FIELDS}


def _num(value):
    """A finite int/float from an arbitrary JSON value, else None (bool is not a number)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return value


def parse_trial_text(text):
    """Extract a trial outcome from one Thalamus log line.

    The task controller emits each finished trial as a single JSON line with
    ``task_config`` and ``task_result`` and, for the Rust joystick task, a
    ``behav_result`` block (see TaskContext.run in Thalamus). Everything else
    (``TRIAL START``, ``BehavState=...``, plain notes) returns None.

    We keep the outcome, task name, the resolved difficulty params (radius,
    hold, reward, goal), and one timing number (first-movement latency). The
    bulky ``joystick_samples`` array inside ``behav_result`` is never read.
    """
    if not text or text[0] != "{":
        return None
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    result = obj.get("task_result")
    if not isinstance(result, dict) or "success" not in result:
        return None

    config = obj.get("task_config")
    if not isinstance(config, dict):
        config = {}
    used = obj.get("used_values")
    if not isinstance(used, dict):
        used = {}
    behav = obj.get("behav_result")
    if not isinstance(behav, dict):
        behav = {}

    task = str(config.get("name") or config.get("task_type") or "unknown")

    # The last attempt of the trial holds the resolved per-target values. Its
    # AttemptEnd fields (first_movement_time_s, ...) are flattened in, so they
    # read as top-level keys of the attempt dict.
    attempt = behav.get("final_attempt")
    if not isinstance(attempt, dict):
        attempts = behav.get("attempts")
        attempt = attempts[-1] if isinstance(attempts, list) and attempts else {}
    if not isinstance(attempt, dict):
        attempt = {}

    return TrialOutcome(
        task=task,
        success=bool(result["success"]),
        final_outcome=(str(behav["final_outcome"]) if behav.get("final_outcome") else None),
        radius=_num(attempt.get("target_radius_ratio")),
        hold=_num(attempt.get("hold_time_s")),
        reward_ms=_num(used.get("reward")),
        reward_channel=_num(attempt.get("reward_channel")),
        reward_scale=_num(config.get("reward_scale")),
        goal=_num(config.get("goal")),
        control_mode=(str(behav["control_mode"]) if behav.get("control_mode") else None),
        move_time_s=_num(attempt.get("first_movement_time_s")),
    )


def parse_output_file(path, regex=DEFAULT_SUBJECT_REGEX):
    """Derive (subject, rig) from a Storage node Output File path.

    E.g. ``/mnt/sraid/Eevee_Behavior_AlexRig/%y%m%d/behave`` -> ("Eevee", "AlexRig").
    Returns ("", "") when nothing matches.
    """
    if not path:
        return "", ""
    try:
        match = re.search(regex, str(path))
    except re.error:
        return "", ""
    if not match:
        return "", ""
    groups = match.groupdict()
    return groups.get("subject", "") or "", groups.get("rig", "") or ""


def find_storage_node(state, node_name):
    """Locate the storage node in a full Thalamus config snapshot.

    Returns (index, node_dict) matching ``node_name`` among STORAGE-type
    nodes, falling back to the first STORAGE-type node; (None, None) if
    there is none.
    """
    nodes = state.get("nodes") if isinstance(state, dict) else None
    if not isinstance(nodes, list):
        return None, None
    fallback = (None, None)
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        if "STORAGE" not in str(node.get("type", "")):
            continue
        if node.get("name") == node_name:
            return i, node
        if fallback == (None, None):
            fallback = (i, node)
    return fallback
