"""Hatch build hook: compile the vendored thalamus.proto into gRPC stubs.

Best-effort — if grpcio-tools is unavailable the hook is skipped and the
stubs are compiled at runtime instead (see simia_log.thalamus_ext._protoc).
"""

import importlib.util
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

EXT_DIR = Path(__file__).parent / "src" / "simia_log" / "thalamus_ext"


def _load_protoc_helper():
    spec = importlib.util.spec_from_file_location(
        "simia_protoc", EXT_DIR / "_protoc.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProtocBuildHook(BuildHookInterface):
    PLUGIN_NAME = "protoc"

    def initialize(self, version, build_data):
        try:
            import grpc_tools  # noqa: F401
        except ImportError:
            self.app.display_warning(
                "grpcio-tools not available; skipping thalamus stub generation "
                "(stubs will be compiled at runtime if the [thalamus] extra is used)"
            )
            return
        helper = _load_protoc_helper()
        helper.compile_protos()
        build_data.setdefault("artifacts", []).append(
            "src/simia_log/thalamus_ext/_gen/"
        )
