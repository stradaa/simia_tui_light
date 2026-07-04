"""Async listener that mirrors a live Thalamus session into the logger.

Two server-streaming subscriptions, each with its own reconnect loop:

- ``observable_bridge_v2`` on the state server (default :50051). The first
  message is a full config snapshot (used to resolve the Storage node by
  name and read its current state); every later message is a delta whose
  ``address`` is a path like ``['nodes'][14]['Running']``. A ``Running``
  flip on the Storage node is a recording start/stop.
- ``logout`` on the native server (default :50050). Each finished trial
  arrives as one JSON Text line; outcomes are tallied in memory per task
  and only flushed to the log when the recording stops.

Callbacks run on the event loop that runs the listener (the Textual app
loop), so they may touch the UI directly.
"""

import asyncio
import json
import logging

import grpc.aio

from ._gen import thalamus_pb2, thalamus_pb2_grpc
from .parsing import find_storage_node, parse_output_file, parse_trial_text

LOGGER = logging.getLogger(__name__)

RECONNECT_MIN_S = 1.0
RECONNECT_MAX_S = 30.0


async def _silence():
    """Request iterator for observable_bridge_v2 that never sends anything."""
    await asyncio.Event().wait()
    yield  # pragma: no cover - unreachable, makes this an async generator


class ThalamusListener:
    def __init__(
        self,
        config,
        on_recording_start=None,
        on_recording_stop=None,
        on_connection_change=None,
    ):
        cfg = config or {}
        self.host = cfg.get("host", "localhost")
        self.cpp_port = int(cfg.get("cpp_port", 50050))
        self.state_port = int(cfg.get("state_port", 50051))
        self.storage_node = cfg.get("storage_node", "Storage")
        self.subject_regex = cfg.get("subject_regex", "")

        self.on_recording_start = on_recording_start
        self.on_recording_stop = on_recording_stop
        self.on_connection_change = on_connection_change

        self.recording = False
        self.storage_info = {}  # output_file, rec, subject, rig
        self._storage_index = None
        self._tally = {}  # task name -> [success, fail]
        self._connected = {"state": False, "trials": False}

    # -- public API ---------------------------------------------------------- #

    async def run(self):
        """Run both watchers until cancelled."""
        await asyncio.gather(
            self._reconnect_loop("state", self._watch_recording),
            self._reconnect_loop("trials", self._watch_trials),
        )

    @property
    def connected(self) -> bool:
        return all(self._connected.values())

    def tally_snapshot(self):
        return {task: tuple(counts) for task, counts in self._tally.items()}

    # -- connection management ------------------------------------------------ #

    async def _reconnect_loop(self, key, watcher):
        delay = RECONNECT_MIN_S
        while True:
            try:
                await watcher()
                delay = RECONNECT_MIN_S
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.debug("thalamus %s watcher error: %r", key, exc)
            self._set_connected(key, False)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_S)

    def _set_connected(self, key, value):
        before = self.connected
        self._connected[key] = value
        after = self.connected
        if before != after and self.on_connection_change:
            self.on_connection_change(after)

    # -- recording watcher ----------------------------------------------------- #

    async def _watch_recording(self):
        async with grpc.aio.insecure_channel(f"{self.host}:{self.state_port}") as channel:
            await asyncio.wait_for(channel.channel_ready(), timeout=5)
            stub = thalamus_pb2_grpc.ThalamusStub(channel)
            stream = stub.observable_bridge_v2(_silence())
            first = True
            async for transaction in stream:
                for change in transaction.changes:
                    if first:
                        first = False
                        self._set_connected("state", True)
                        self._apply_snapshot(change.value)
                    else:
                        self._apply_delta(change.address, change.value)

    def _apply_snapshot(self, value):
        try:
            state = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            LOGGER.debug("unparseable thalamus snapshot")
            return
        index, node = find_storage_node(state, self.storage_node)
        self._storage_index = index
        if node is None:
            LOGGER.debug("no storage node %r in thalamus config", self.storage_node)
            return
        self._read_storage_node(node)
        self._set_recording(bool(node.get("Running", False)))

    def _apply_delta(self, address, value):
        idx = self._storage_index
        if idx is None:
            return
        node_addr = f"['nodes'][{idx}]"
        if address == f"{node_addr}['Running']":
            self._set_recording(self._parse_json(value) is True)
        elif address == f"{node_addr}['Output File']":
            self._update_output_file(self._parse_json(value))
        elif address == f"{node_addr}['rec']":
            rec = self._parse_json(value)
            if isinstance(rec, int):
                self.storage_info["rec"] = rec
        elif address in (node_addr, "['nodes']", ""):
            # Storage node (or the whole node list / config) replaced: re-read.
            state = self._parse_json(value)
            if address == node_addr and isinstance(state, dict):
                self._read_storage_node(state)
                self._set_recording(bool(state.get("Running", False)))
            elif isinstance(state, (dict, list)):
                wrapped = state if isinstance(state, dict) else {"nodes": state}
                self._apply_snapshot(json.dumps(wrapped))

    @staticmethod
    def _parse_json(value):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None

    def _read_storage_node(self, node):
        self._update_output_file(node.get("Output File", ""))
        rec = node.get("rec")
        if isinstance(rec, int):
            self.storage_info["rec"] = rec

    def _update_output_file(self, output_file):
        if not isinstance(output_file, str):
            return
        self.storage_info["output_file"] = output_file
        if self.subject_regex:
            subject, rig = parse_output_file(output_file, self.subject_regex)
        else:
            subject, rig = parse_output_file(output_file)
        self.storage_info["subject"] = subject
        self.storage_info["rig"] = rig

    def _set_recording(self, running):
        if running == self.recording:
            return
        self.recording = running
        if running:
            self._tally = {}
            if self.on_recording_start:
                self.on_recording_start(dict(self.storage_info))
        else:
            tally = self.tally_snapshot()
            self._tally = {}
            if self.on_recording_stop:
                self.on_recording_stop(tally)

    # -- trial watcher --------------------------------------------------------- #

    async def _watch_trials(self):
        async with grpc.aio.insecure_channel(f"{self.host}:{self.cpp_port}") as channel:
            await asyncio.wait_for(channel.channel_ready(), timeout=5)
            stub = thalamus_pb2_grpc.ThalamusStub(channel)
            stream = stub.logout(thalamus_pb2.Empty())
            self._set_connected("trials", True)
            async for message in stream:
                self._record_outcome(parse_trial_text(message.text))

    def _record_outcome(self, outcome):
        if outcome is None or not self.recording:
            return
        counts = self._tally.setdefault(outcome.task, [0, 0])
        counts[0 if outcome.success else 1] += 1


async def fetch_session_hints(config, timeout=3.0):
    """One-shot snapshot read for session-start prefill.

    Returns {subject, rig, output_file, rec} from the Storage node of a
    running Thalamus session, or None if unreachable within ``timeout``.
    """
    cfg = config or {}
    host = cfg.get("host", "localhost")
    port = int(cfg.get("state_port", 50051))
    node_name = cfg.get("storage_node", "Storage")
    regex = cfg.get("subject_regex", "")

    async def _fetch():
        async with grpc.aio.insecure_channel(f"{host}:{port}") as channel:
            await channel.channel_ready()
            stub = thalamus_pb2_grpc.ThalamusStub(channel)
            stream = stub.observable_bridge_v2(_silence())
            async for transaction in stream:
                for change in transaction.changes:
                    state = json.loads(change.value)
                    _, node = find_storage_node(state, node_name)
                    if node is None:
                        return None
                    output_file = str(node.get("Output File", "") or "")
                    if regex:
                        subject, rig = parse_output_file(output_file, regex)
                    else:
                        subject, rig = parse_output_file(output_file)
                    return {
                        "subject": subject,
                        "rig": rig,
                        "output_file": output_file,
                        "rec": node.get("rec"),
                    }
        return None

    try:
        return await asyncio.wait_for(_fetch(), timeout=timeout)
    except asyncio.CancelledError:
        raise
    except Exception:
        return None
