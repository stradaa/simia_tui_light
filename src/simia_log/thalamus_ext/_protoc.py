"""Compile the vendored thalamus.proto into gRPC stubs.

Shared by the Hatch build hook (wheel builds) and the runtime fallback
(editable installs / source checkouts). Generated modules live in
``_gen/`` next to this file and are gitignored.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTO_DIR = HERE / "_proto"
GEN_DIR = HERE / "_gen"

_GEN_INIT = '"""Generated gRPC stubs for the vendored thalamus.proto (do not edit)."""\n'


def compile_protos(proto_dir: Path = PROTO_DIR, gen_dir: Path = GEN_DIR) -> None:
    """Run grpc_tools.protoc and fix the generated import to be package-relative."""
    from grpc_tools import protoc

    gen_dir.mkdir(parents=True, exist_ok=True)
    args = [
        "protoc",
        f"-I{proto_dir}",
        f"--python_out={gen_dir}",
        f"--grpc_python_out={gen_dir}",
        str(proto_dir / "thalamus.proto"),
    ]
    if protoc.main(args) != 0:
        raise RuntimeError("grpc_tools.protoc failed for thalamus.proto")

    # protoc emits an absolute import; rewrite it for use inside the package.
    grpc_file = gen_dir / "thalamus_pb2_grpc.py"
    text = grpc_file.read_text(encoding="utf-8")
    text = text.replace(
        "import thalamus_pb2 as thalamus__pb2",
        "from . import thalamus_pb2 as thalamus__pb2",
    )
    grpc_file.write_text(text, encoding="utf-8")
    (gen_dir / "__init__.py").write_text(_GEN_INIT, encoding="utf-8")


def stubs_present(gen_dir: Path = GEN_DIR) -> bool:
    return (gen_dir / "thalamus_pb2.py").exists() and (
        gen_dir / "thalamus_pb2_grpc.py"
    ).exists()
