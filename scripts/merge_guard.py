#!/usr/bin/env python3
"""PreToolUse hook (Bash): subagents never merge pull requests.

The coordinator may merge when the owner tells it to, so merging cannot be
denied in settings: those are shared by the coordinator and its subagents.
This hook denies it only when the call comes from inside a subagent, which
the hook input marks with `agent_id`.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from log_event import append  # noqa: E402
from nonslop_config import load_config, read_hook_input, start_dir  # noqa: E402

MERGE = re.compile(r"\bgh\s+pr\s+merge\b|\bgh\s+api\b[^|;&]*/pulls/\d+/merge\b")


def main() -> int:
    hook_input = read_hook_input()
    if not hook_input.get("agent_id"):
        return 0
    loaded = load_config(start_dir(hook_input))
    if loaded is None:
        return 0
    command = (hook_input.get("tool_input") or {}).get("command", "")
    if not MERGE.search(command):
        return 0
    append(*loaded, "merge-guard", {"session": hook_input.get("session_id", ""),
                                    "agent": hook_input["agent_id"], "decision": "deny", "command": command})
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "nonslop: subagents never merge. Report DONE; the owner or the coordinator merges.",
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
