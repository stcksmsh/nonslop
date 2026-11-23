#!/usr/bin/env python3
"""Print the rules and project wiring into a fresh context.

  session_start.py              SessionStart hook: plain text on stdout, for the main session.
                                Runs on startup, /clear and compaction. Includes the state file.
  session_start.py --subagent   SubagentStart hook: the same rules as additionalContext JSON, so
                                builders and reviewers start with them. No state file: a subagent
                                gets its task from its prompt.
  session_start.py --print      Plain text for a human (`nonslop rules`).

Silent in projects without .nonslop.toml.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slices  # noqa: E402
from nonslop_config import load_config, read_hook_input, record_session_start, start_dir  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
STATE_MAX_LINES = 80


def section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}\n"


def render_commands(config: dict) -> str:
    commands = {name: command for name, command in config.get("commands", {}).items() if command}
    if not commands:
        return ""
    lines = [f"- {name}: `{command}`" for name, command in commands.items()]
    return section("Project commands (use these exactly, do not substitute your own)", "\n".join(lines))


def render_project_rules(config: dict) -> str:
    env = config.get("env", {})
    prefix = config.get("done", {}).get("branch_prefix", "claude/")
    lines = [f"- Slice branches are named `{prefix}<slice>`; only those are checked as finished slices at Stop."]
    if scratch := env.get("scratch"):
        lines.append(
            f"- All scratch (scripts, renders, logs, repo copies) goes under `{scratch}/<job-id>/`. "
            "Never write to the home directory, `/tmp` or `~/.cache`. Delete your scratch before you stop."
        )
    if sink := env.get("audio_sink"):
        lines.append(
            f"- Never play audio on the default output. Run anything that makes sound with "
            f"`env PIPEWIRE_NODE={sink} PULSE_SINK={sink} ...` and prefer offline renders."
        )
    lines.extend(f"- {note}" for note in config.get("rules", {}).get("notes", []))
    return section("This project", "\n".join(lines))


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


def render_slices(config: dict, root: Path) -> str:
    """What the slice records say is open. Local files only: this hook has ten seconds."""
    lines = []
    for record in slices.all_records(config, root):
        status = record.get("status")
        if status not in slices.OPEN:
            continue
        verify, review = record.get("verify") or {}, slices.last_review(record)
        line = (f"- {record['branch']}: {status}; verify "
                f"{'none' if not verify else 'ok' if verify.get('ok') else 'FAILED'} "
                f"{str(verify.get('sha', ''))[:9]}; review {review.get('verdict', 'none')} {str(review.get('sha', ''))[:9]}")
        if status == "released":
            line += "  <- let go with finish checks failing; not done"
        lines.append(line)
    if not lines:
        return ""
    lines.append("Run `nonslop status` for pull requests, CI and worktrees before acting on these.")
    return section("Slices in flight (from the slice records)", "\n".join(lines))


def render(config: dict, root: Path, with_state: bool) -> str:
    parts = [
        "# nonslop",
        (PLUGIN_ROOT / "rules" / "core.md").read_text(encoding="utf-8"),
        render_commands(config),
        render_project_rules(config),
        render_state(config, root) if with_state else "",
        render_slices(config, root) if with_state else "",
    ]
    return "\n".join(part for part in parts if part)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    hook_input = {} if mode == "--print" else read_hook_input()
    loaded = load_config(start_dir(hook_input))
    if loaded is None:
        return 0
    config, root = loaded
    if mode == "--subagent":
        text = render(config, root, with_state=False)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": text}}))
    else:
        if mode != "--print":
            record_session_start(config, root, start_dir(hook_input), hook_input.get("session_id", ""))
        print(render(config, root, with_state=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
