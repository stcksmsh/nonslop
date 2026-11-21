#!/usr/bin/env python3
"""Run slopstop's Stop check, but only on slice branches.

slopstop's own Stop hook checks every session. A coordinator sits on the
default branch in a checkout full of untracked notes, where a full check is
slow and reports files nobody is shipping. This wrapper passes the hook
through unchanged when the branch starts with [done].branch_prefix and is
silent otherwise.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nonslop_config import load_config, read_hook_input, start_dir  # noqa: E402

SLOP = Path(__file__).resolve().parent.parent / "tools" / "slopstop" / "slop.py"


def main() -> int:
    hook_input = read_hook_input()
    cwd = start_dir(hook_input)
    loaded = load_config(cwd)
    if loaded is None:
        return 0
    config, _root = loaded
    prefix = config.get("done", {}).get("branch_prefix", "claude/")
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, capture_output=True, text=True, check=False
    ).stdout.strip()
    if not branch.startswith(prefix):
        return 0
    result = subprocess.run(
        [sys.executable, str(SLOP), "hook", "stop"], input=json.dumps(hook_input), text=True, check=False
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
