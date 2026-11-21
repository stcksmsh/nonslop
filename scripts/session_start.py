#!/usr/bin/env python3
"""SessionStart hook: print shared rules, project wiring and the current state file.

Runs on startup, /clear and compaction, so a fresh context always begins with
the same rules and the newest handover without anyone pasting them.
Stdout becomes context for the session.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nonslop_config import load_config, read_hook_input, start_dir  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
STATE_MAX_LINES = 80


def section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}\n"


def render_commands(config: dict) -> str:
    commands = config.get("commands", {})
    if not commands:
        return ""
    lines = [f"- {name}: `{command}`" for name, command in commands.items()]
    return section("Project commands (use these, do not guess)", "\n".join(lines))


def render_env(config: dict) -> str:
    env = config.get("env", {})
    lines = []
    if scratch := env.get("scratch"):
        lines.append(f"- All scratch files go under `{scratch}/<job-id>/`. Never write to the home directory.")
    if sink := env.get("audio_sink"):
        lines.append(
            f"- Never play audio on the default output. Use `PIPEWIRE_NODE={sink} PULSE_SINK={sink}` "
            "and prefer offline renders."
        )
    for note in env.get("notes", []):
        lines.append(f"- {note}")
    return section("Machine constraints", "\n".join(lines)) if lines else ""


def render_state(config: dict, root: Path) -> str:
    relative = config.get("state", {}).get("file")
    if not relative:
        return ""
    path = root / relative
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    body = "\n".join(lines[:STATE_MAX_LINES])
    if len(lines) > STATE_MAX_LINES:
        body += f"\n[truncated: {len(lines) - STATE_MAX_LINES} more lines in {relative}]"
    return section(f"Current state ({relative})", body)


def main() -> int:
    loaded = load_config(start_dir(read_hook_input()))
    if loaded is None:
        return 0
    config, root = loaded
    parts = [
        "# nonslop",
        (PLUGIN_ROOT / "rules" / "core.md").read_text(encoding="utf-8"),
        render_commands(config),
        render_env(config),
        render_state(config, root),
    ]
    print("\n".join(part for part in parts if part))
    return 0


if __name__ == "__main__":
    sys.exit(main())
