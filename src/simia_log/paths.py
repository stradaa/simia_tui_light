"""Where Simia Log keeps its config and data.

Config lives in the platform config dir (e.g. ``~/.config/simia-log`` or
``~/Library/Application Support/simia-log``) so users never have to hunt for or
hand-edit a JSON file. Logs and exports default to the platform data dir.

The one hard rule: **existing logs are never moved or copied.** When an older
checkout-relative setup is detected, migration only *re-points* ``output_dir``
at the absolute path of the logs already on disk — the files stay exactly where
they are.
"""

import json
import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "simia-log"

# Historical config filename used by checkout-relative installs.
LEGACY_CONFIG_NAME = "lablog_config.json"


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))


def data_dir() -> Path:
    return Path(user_data_dir(APP_NAME))


def config_file() -> Path:
    """The active config path, honoring the ``SIMIA_LOG_CONFIG`` override."""
    override = os.environ.get("SIMIA_LOG_CONFIG", "").strip()
    if override:
        return Path(override).expanduser()
    return config_dir() / "config.json"


def default_output_dir() -> Path:
    return data_dir() / "logs"


def default_exports_dir() -> Path:
    return data_dir() / "exports"


def _find_legacy_config() -> Path | None:
    """Look for an old ``lablog_config.json`` next to where we were launched."""
    candidate = Path.cwd() / LEGACY_CONFIG_NAME
    if candidate.is_file():
        return candidate
    return None


def save_config(path: Path, cfg: dict) -> None:
    """Persist a config dict, creating the parent directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def migrate_legacy_if_needed(target: Path) -> str | None:
    """One-time, loss-free migration of a checkout-relative setup.

    If ``target`` (the platform config) does not yet exist, but an older
    ``lablog_config.json`` or a ``logs/`` folder is sitting in the current
    directory, import the config and pin ``output_dir`` to the *absolute* path
    of those existing logs. Nothing on disk is moved or copied.

    Returns a short human-readable note when a migration happened, else None.
    """
    if target.exists():
        return None

    cwd = Path.cwd()
    legacy_cfg = _find_legacy_config()
    legacy_logs = cwd / "logs"

    if legacy_cfg is None and not legacy_logs.is_dir():
        # Nothing to import — a brand-new user. The setup wizard takes over.
        return None

    if legacy_cfg is not None:
        try:
            cfg = json.loads(legacy_cfg.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    else:
        cfg = {}

    # Resolve output_dir against the legacy config's own location so we keep
    # pointing at the logs that already exist, wherever they are.
    raw_out = str(cfg.get("output_dir", "logs") or "logs").strip()
    out_path = Path(raw_out).expanduser()
    if not out_path.is_absolute():
        base = (legacy_cfg.parent if legacy_cfg is not None else cwd)
        out_path = (base / out_path).resolve()
    cfg["output_dir"] = str(out_path)

    save_config(target, cfg)
    return f"Imported your existing setup. Logs stay at: {out_path}"
