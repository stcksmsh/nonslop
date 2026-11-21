#!/usr/bin/env python3
"""Append a hook event to a JSONL log in the project scratch dir.

Used for PermissionDenied: the log shows which calls auto mode refused, so the
allow list can be extended from data instead of guesses.
Usage: log_event.py <event-name>   (hook JSON on stdin)
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nonslop_config import load_config, read_hook_input, scratch_dir, start_dir  # noqa: E402


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else "event"
    hook_input = read_hook_input()
    loaded = load_config(start_dir(hook_input))
    if loaded is None:
        return 0
    config, root = loaded
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, "input": hook_input}
    with (scratch_dir(config, root) / f"{event}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
