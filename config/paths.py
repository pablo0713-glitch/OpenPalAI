from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent


def _path_from_env(key: str, default: Path) -> Path:
    raw = os.getenv(key, "").strip()
    path = Path(raw) if raw else default
    return path if path.is_absolute() else ROOT_DIR / path


def data_dir() -> Path:
    return _path_from_env("TRIXXIE_DATA_DIR", ROOT_DIR / "data")


def env_path() -> Path:
    return _path_from_env("TRIXXIE_ENV_FILE", ROOT_DIR / ".env")
