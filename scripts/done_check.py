#!/usr/bin/env python3
"""Stop / SubagentStop hook: refuse to finish a slice that is not actually done.

Deterministic, no model. Active only when:
  - the project has a .nonslop.toml, and
  - the current branch starts with [done].branch_prefix (default "claude/").
So a coordinator sitting on the default branch is never blocked.

Exit 2 with the failures on stderr keeps the agent working. After
[done].stop_retries identical failures in a row the hook lets the agent stop
and records the unresolved list, so it cannot loop forever.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nonslop_config import load_config, read_hook_input, scratch_dir, start_dir  # noqa: E402

DEFAULT_REQUIRE = ["clean_tree", "pushed", "pr", "cleaned"]


def run(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)
    return result.returncode, result.stdout.strip()


def check_clean_tree(cwd: Path, _done: dict) -> str | None:
    code, out = run(["git", "status", "--porcelain"], cwd)
    if code != 0:
        return "git status failed"
    return "uncommitted or untracked files remain: commit them or delete them" if out else None


def check_pushed(cwd: Path, _done: dict) -> str | None:
    code, _ = run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"], cwd)
    if code != 0:
        return "branch has no upstream: push it"
    code, out = run(["git", "rev-list", "--count", "@{upstream}..HEAD"], cwd)
    if code != 0:
        return "could not compare with upstream"
    return f"{out} commit(s) not pushed" if out != "0" else None


def check_pr(cwd: Path, _done: dict) -> str | None:
    if shutil.which("gh") is None:
        return "gh not installed, cannot verify the pull request"
    code, _ = run(["gh", "pr", "view", "--json", "number"], cwd)
    return "no pull request for this branch: open a draft PR" if code != 0 else None


def check_cleaned(cwd: Path, done: dict) -> str | None:
    leftovers = [name for name in done.get("clean_paths", []) if (cwd / name).exists()]
    if leftovers:
        return f"build output still present ({', '.join(leftovers)}): run the project's clean command"
    return None


def check_free_space(cwd: Path, done: dict) -> str | None:
    minimum = done.get("min_free_gb")
    if not minimum:
        return None
    free_gb = shutil.disk_usage(cwd).free / 1e9
    if free_gb < minimum:
        return f"only {free_gb:.0f} GB free on this disk (minimum {minimum}): clean up and tell the coordinator"
    return None


CHECKS = {
    "clean_tree": check_clean_tree,
    "pushed": check_pushed,
    "pr": check_pr,
    "cleaned": check_cleaned,
}


def retries_exhausted(state_file: Path, session: str, failures: list[str], limit: int) -> bool:
    """Count consecutive identical failure sets per session."""
    digest = hashlib.sha256("\n".join(failures).encode()).hexdigest()
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    previous = state.get(session, {})
    count = previous.get("count", 0) + 1 if previous.get("digest") == digest else 1
    state[session] = {"digest": digest, "count": count, "failures": failures}
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return count > limit


def main() -> int:
    hook_input = read_hook_input()
    cwd = start_dir(hook_input)
    loaded = load_config(cwd)
    if loaded is None:
        return 0
    config, root = loaded
    done = config.get("done", {})

    code, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if code != 0 or not branch.startswith(done.get("branch_prefix", "claude/")):
        return 0

    failures = []
    for name in done.get("require", DEFAULT_REQUIRE):
        check = CHECKS.get(name)
        if check is None:
            failures.append(f"unknown check '{name}' in [done].require")
            continue
        if problem := check(cwd, done):
            failures.append(problem)
    if problem := check_free_space(cwd, done):
        failures.append(problem)
    if not failures:
        return 0

    state_file = scratch_dir(config, root) / "done-check.json"
    session = hook_input.get("session_id", "unknown")
    if retries_exhausted(state_file, session, failures, done.get("stop_retries", 2)):
        return 0

    print("nonslop done-check: slice is not finished:", file=sys.stderr)
    for problem in failures:
        print(f"  - {problem}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
