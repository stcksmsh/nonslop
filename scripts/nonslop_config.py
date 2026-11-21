"""Shared helpers for nonslop hook scripts. Stdlib only, Python 3.11+."""

import json
import os
import sys
import tomllib
from pathlib import Path

CONFIG_NAME = ".nonslop.toml"


def read_hook_input() -> dict:
    """Parse the hook JSON that Claude Code writes to stdin."""
    if sys.stdin.isatty():
        return {}
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_unparsed": raw}


def start_dir(hook_input: dict) -> Path:
    return Path(hook_input.get("cwd") or os.getcwd())


def find_config(start: Path) -> Path | None:
    """Walk up from `start` to the nearest .nonslop.toml."""
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def load_config(start: Path) -> tuple[dict, Path] | None:
    """Return (config, project_root), or None when the project is not wired.

    A project without .nonslop.toml gets no nonslop behaviour at all, so the
    plugin can be enabled user-wide without touching unrelated repos.
    """
    path = find_config(start)
    if path is None:
        return None
    with path.open("rb") as handle:
        return tomllib.load(handle), path.parent


def scratch_dir(config: dict, root: Path) -> Path:
    """Project-local scratch. Never the home directory or the plugin data dir."""
    relative = config.get("env", {}).get("scratch", ".claude/tmp")
    directory = root / relative / "nonslop"
    directory.mkdir(parents=True, exist_ok=True)
    return directory
