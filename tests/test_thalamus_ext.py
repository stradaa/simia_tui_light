"""Tests for the optional Thalamus integration.

Runnable with pytest, or directly: ``python tests/test_thalamus_ext.py``
(requires the [thalamus] extra for the listener tests).
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simia_log.lablog import Logger, compute_session_summary, normalize_config
from simia_log.thalamus_ext.parsing import (
    find_storage_node,
    parse_output_file,
    parse_trial_text,
)

# Shape captured from a live session (thalamus TaskContext.run trial_summ).
TRIAL_JSON = json.dumps(
    {
        "used_values": {"reward": 50.0},
        "task_config": {
            "task_type": "joystick_intro_rust",
            "name": "Grid (Rust) - test",
            "task_cluster_name": "Joy",
            "goal": 96,
        },
        "task_result": {"success": True, "done": True},
        "behav_result": {"final_outcome": "success", "joystick_samples": [0] * 100},
    }
)


def test_parse_trial_text():
    outcome = parse_trial_text(TRIAL_JSON)
    assert outcome is not None
    assert outcome.task == "Grid (Rust) - test"
    assert outcome.success is True

    fail = parse_trial_text(
        json.dumps({"task_config": {"name": "X"}, "task_result": {"success": False}})
    )
    assert fail.success is False

    # Non-trial log lines are ignored.
    assert parse_trial_text("BehavState=success") is None
    assert parse_trial_text("TRIAL START task Grid (Rust) - test") is None
    assert parse_trial_text('{"no_result": 1}') is None
    assert parse_trial_text("") is None
    assert parse_trial_text("[1, 2, 3]") is None


def test_parse_output_file():
    assert parse_output_file("/mnt/sraid/Eevee_Behavior_AlexRig/%y%m%d/behave") == (
        "Eevee",
        "AlexRig",
    )
    assert parse_output_file("") == ("", "")
    assert parse_output_file("/data/foo/bar") == ("", "")


def test_find_storage_node():
    state = {
        "nodes": [
            {"name": "Cam", "type": "GENICAM"},
            {"name": "Storage", "type": "STORAGE2", "Running": False},
            {"name": "experiment", "type": "STORAGE2"},
        ]
    }
    idx, node = find_storage_node(state, "Storage")
    assert idx == 1 and node["name"] == "Storage"
    # Falls back to the first STORAGE-type node when the name is absent.
    idx, node = find_storage_node(state, "missing")
    assert idx == 1
    assert find_storage_node({"nodes": []}, "Storage") == (None, None)
    assert find_storage_node({}, "Storage") == (None, None)


def test_listener_recording_state_machine():
    from simia_log.thalamus_ext.listener import ThalamusListener
    from simia_log.thalamus_ext.parsing import parse_trial_text as parse

    events = []
    listener = ThalamusListener(
        {"storage_node": "Storage"},
        on_recording_start=lambda info: events.append(("start", info)),
        on_recording_stop=lambda tally: events.append(("stop", tally)),
    )
    snapshot = json.dumps(
        {
            "nodes": [
                {"name": "Cam", "type": "GENICAM"},
                {
                    "name": "Storage",
                    "type": "STORAGE2",
                    "Running": False,
                    "Output File": "/mnt/sraid/Eevee_Behavior_AlexRig/%y%m%d/behave",
                    "rec": 3,
                },
            ]
        }
    )
    listener._apply_snapshot(snapshot)
    assert listener._storage_index == 1
    assert listener.recording is False
    assert listener.storage_info["subject"] == "Eevee"
    assert events == []

    # Trials while not recording are ignored.
    listener._record_outcome(parse(TRIAL_JSON))
    assert listener.tally_snapshot() == {}

    # Recording starts: callback fires once, tally resets.
    listener._apply_delta("['nodes'][1]['Running']", "true")
    listener._apply_delta("['nodes'][1]['Running']", "true")  # duplicate: no-op
    assert [e[0] for e in events] == ["start"]
    assert events[0][1]["subject"] == "Eevee"

    for _ in range(3):
        listener._record_outcome(parse(TRIAL_JSON))
    listener._record_outcome(
        parse(json.dumps({"task_config": {"name": "Grid (Rust) - test"},
                          "task_result": {"success": False}}))
    )
    assert listener.tally_snapshot() == {"Grid (Rust) - test": (3, 1)}

    # Recording stops: tally is delivered and cleared.
    listener._apply_delta("['nodes'][1]['Running']", "false")
    assert [e[0] for e in events] == ["start", "stop"]
    assert events[1][1] == {"Grid (Rust) - test": (3, 1)}
    assert listener.tally_snapshot() == {}


def test_log_round_trip():
    """The auto-written entries must feed the existing summary math unchanged."""
    with tempfile.TemporaryDirectory() as tmp:
        logger = Logger(Path(tmp) / "config.json")
        logger.config["output_dir"] = tmp
        logger.begin_new_session({"animal_id": "Eevee"}, None)

        logger.append_entry("START RECORDING")
        logger.append_entry("STOP TASK: Grid (Rust) - test [15/2]")
        logger.append_entry("STOP TASK: Cardinal [4/1]")
        logger.append_entry("STOP RECORDING")

        summary = compute_session_summary(logger.entries)
        assert summary["recordings"] == 1
        assert summary["trials_success"] == 19
        assert summary["trials_fail"] == 3
        assert logger.recording_index == 1


def test_normalize_config_thalamus_block():
    cfg = normalize_config({"thalamus": {"enabled": False, "host": "10.0.0.5"}})
    assert cfg["thalamus"]["enabled"] is False
    assert cfg["thalamus"]["host"] == "10.0.0.5"
    # Unspecified keys keep their defaults.
    assert cfg["thalamus"]["cpp_port"] == 50050
    assert cfg["thalamus"]["state_port"] == 50051
    assert cfg["thalamus"]["storage_node"] == "Storage"
    # Absent block: fully defaulted, enabled (gated on the extra being installed).
    cfg = normalize_config({})
    assert cfg["thalamus"]["enabled"] is True


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"{name} OK")
    print("all tests passed")
