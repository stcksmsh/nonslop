"""Shared helpers for nonslop hook scripts. Stdlib only, Python 3.11+."""

import hashlib
import json
import os
import re
import subprocess
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


def tree_state(cwd: Path) -> str:
    """Fingerprint of HEAD, uncommitted changes and untracked files (by size and mtime)."""
    digest = hashlib.sha256()
    for args in (["git", "rev-parse", "HEAD"], ["git", "diff", "HEAD", "--binary"]):
        digest.update(subprocess.run(args, cwd=cwd, capture_output=True, check=False).stdout)
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                               cwd=cwd, capture_output=True, check=False).stdout
    for name in sorted(filter(None, untracked.split(b"\0"))):
        try:
            stat = (cwd / os.fsdecode(name)).stat()
        except OSError:
            continue
        digest.update(name + f"\0{stat.st_size}\0{stat.st_mtime_ns}\0".encode())
    return digest.hexdigest()


def _start_file(config: dict, root: Path, session_id: str) -> Path:
    return scratch_dir(config, root) / "sessions" / f"{re.sub(r'[^A-Za-z0-9_-]', '_', session_id)}.txt"


def record_session_start(config: dict, root: Path, cwd: Path, session_id: str) -> None:
    if not session_id:
        return
    path = _start_file(config, root, session_id)
    if path.exists():  # SessionStart fires again on compaction; keep the state from the real start
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tree_state(cwd), encoding="utf-8")


def unchanged_since_start(config: dict, root: Path, cwd: Path, session_id: str) -> bool:
    """True when this session has changed nothing yet; its Stop must not judge work done before it."""
    if not session_id:
        return False
    try:
        recorded = _start_file(config, root, session_id).read_text(encoding="utf-8")
    except OSError:  # no recorded start (resumed session, subagent worktree): check as before
        return False
    return recorded == tree_state(cwd)
