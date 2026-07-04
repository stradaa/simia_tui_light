"""Parsers for Thalamus log text and config values. Pure functions, no grpc."""

import json
import re
from dataclasses import dataclass

DEFAULT_SUBJECT_REGEX = r"(?P<subject>[^_/]+)_Behavior_(?P<rig>[^_/]+)"


@dataclass
class TrialOutcome:
    task: str
    success: bool


def parse_trial_text(text):
    """Extract a trial outcome from one Thalamus log line.

    The task controller emits each finished trial as a single JSON line
    containing ``task_config`` and ``task_result`` (see TaskContext.run in
    Thalamus). Everything else (``TRIAL START``, ``BehavState=...``, plain
    notes) returns None. Only the outcome and task name are kept — the
    ``behav_result`` payload can carry thousands of joystick samples and is
    deliberately discarded.
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
    task = str(config.get("name") or config.get("task_type") or "unknown")
    return TrialOutcome(task=task, success=bool(result["success"]))


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
