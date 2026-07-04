"""Optional Thalamus integration (``pip install simia-log[thalamus]``).

Listens to a running Thalamus session over gRPC and drives the log
automatically: recording start/stop is mirrored from the Storage node and
per-task trial tallies are written at the end of each recording. Everything
gRPC-related is import-guarded so the base app never needs grpc installed.
"""

_IMPORT_ERROR = None


def _load_stubs():
    """Import the generated gRPC stubs, compiling them on first use if needed."""
    try:
        from ._gen import thalamus_pb2, thalamus_pb2_grpc
    except ImportError:
        from . import _protoc

        _protoc.compile_protos()
        from ._gen import thalamus_pb2, thalamus_pb2_grpc
    return thalamus_pb2, thalamus_pb2_grpc


try:
    import grpc  # noqa: F401
    import grpc.aio  # noqa: F401

    _load_stubs()
except Exception as exc:  # ImportError, or protoc failure without grpcio-tools
    _IMPORT_ERROR = exc


def is_available() -> bool:
    """True when grpc and the generated thalamus stubs are importable."""
    return _IMPORT_ERROR is None


def unavailable_reason() -> str:
    return "" if _IMPORT_ERROR is None else str(_IMPORT_ERROR)


if is_available():
    from .listener import ThalamusListener, fetch_session_hints  # noqa: F401
    from .parsing import parse_output_file, parse_trial_text  # noqa: F401
