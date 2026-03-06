from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _parse_env_line(line: str) -> tuple[str, str] | None:
    txt = line.strip()
    if not txt or txt.startswith("#") or "=" not in txt:
        return None
    key, value = txt.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value


def load_env_files(files: list[str], base_dir: Path) -> None:
    for raw in files:
        p = Path(raw)
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            parsed = _parse_env_line(line)
            if not parsed:
                continue
            key, value = parsed
            os.environ.setdefault(key, value)


def load_settings(settings_path: str | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    path = Path(settings_path or os.getenv("SCHED_SETTINGS_FILE") or (root / "config/settings.json"))
    if not path.exists():
        raise FileNotFoundError(f"Missing settings file: {path}")
    settings = json.loads(path.read_text(encoding="utf-8"))
    env_files = settings.get("env_files", []) if isinstance(settings, dict) else []
    if isinstance(env_files, list):
        load_env_files([str(x) for x in env_files], root)
    return settings


def abs_path(path_value: str) -> Path:
    p = Path(path_value)
    if p.is_absolute():
        return p
    return (Path(__file__).resolve().parents[2] / p).resolve()
