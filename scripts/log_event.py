#!/usr/bin/env python3
"""Append a hook event to a JSONL log in the project scratch dir.

Used for PermissionDenied: the log shows which calls auto mode refused, so the
allow list can be extended from data instead of guesses. The gate scripts
import `append` to log their own decisions the same way.
Usage: log_event.py <event-name>   (hook JSON on stdin)
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nonslop_config import load_config, read_hook_input, scratch_dir, start_dir  # noqa: E402


def append(config: dict, root: Path, event: str, record: dict) -> None:
    """Add one line to <scratch>/nonslop/<event>.jsonl. A log that cannot be written must not
    change what the calling hook decides, so the failure is dropped."""
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **record}
    try:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with (scratch_dir(config, root) / f"{event}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(line)
    except (OSError, TypeError, ValueError):
        pass


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else "event"
    hook_input = read_hook_input()
    loaded = load_config(start_dir(hook_input))
    if loaded is None:
        return 0
    config, root = loaded
    append(config, root, event, {"input": hook_input})
    return 0


if __name__ == "__main__":
    sys.exit(main())
