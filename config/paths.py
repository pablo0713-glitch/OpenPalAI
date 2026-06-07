from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
LEGACY_ENV_PREFIX = "TRI" + "XXIE"


def _path_from_env(key: str, default: Path, legacy_key: str | None = None) -> Path:
    raw = os.getenv(key, "").strip()
    if not raw and legacy_key:
        raw = os.getenv(legacy_key, "").strip()
    path = Path(raw) if raw else default
    return path if path.is_absolute() else ROOT_DIR / path


def data_dir() -> Path:
    return _path_from_env(
        "OPENPALAI_DATA_DIR",
        ROOT_DIR / "data",
        f"{LEGACY_ENV_PREFIX}_DATA_DIR",
    )


def env_path() -> Path:
    return _path_from_env(
        "OPENPALAI_ENV_FILE",
        ROOT_DIR / ".env",
        f"{LEGACY_ENV_PREFIX}_ENV_FILE",
    )
