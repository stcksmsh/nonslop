#!/usr/bin/env python3
"""Stop / SubagentStop hook: refuse to finish a slice that is not actually done.

Deterministic, no model. Active only when:
  - the project has a .nonslop.toml, and
  - the current branch starts with [done].branch_prefix (default "claude/").
So a coordinator sitting on the default branch is never blocked.

Order: cheap git checks first, then the project's gates ([done].run), then
free disk. When everything passes and [done].auto_clean is set, the hook runs
the project's clean command itself, so agents do not have to remember it.

An agent whose final message starts with BLOCKED is asking a question, not
claiming to be done, and is let through.

Exit 2 with the failures on stderr keeps the agent working. After
[done].stop_retries identical failures in a row the hook lets the agent stop
and leaves the unresolved list in the scratch dir, so it cannot loop forever.
"""

import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gates import run_gates  # noqa: E402
from nonslop_config import load_config, read_hook_input, scratch_dir, start_dir  # noqa: E402

DEFAULT_REQUIRE = ["clean_tree", "pushed", "pr"]


def run(args: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str]:
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)
    return result.returncode, result.stdout.strip()


def check_clean_tree(cwd: Path) -> str | None:
    code, out = run(["git", "status", "--porcelain"], cwd)
    if code != 0:
        return "git status failed"
    return "uncommitted or untracked files remain: commit them or delete them" if out else None


def check_pushed(cwd: Path) -> str | None:
    code, _ = run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"], cwd)
    if code != 0:
        return "branch has no upstream: push it"
    code, out = run(["git", "rev-list", "--count", "@{upstream}..HEAD"], cwd)
    if code != 0:
        return "could not compare with upstream"
    return f"{out} commit(s) not pushed" if out != "0" else None


def check_pr(cwd: Path) -> str | None:
    if shutil.which("gh") is None:
        return "gh not installed, cannot verify the pull request"
    code, _ = run(["gh", "pr", "view", "--json", "number"], cwd)
    return "no pull request for this branch: open a draft PR" if code != 0 else None


CHECKS = {"clean_tree": check_clean_tree, "pushed": check_pushed, "pr": check_pr}


def check_free_space(cwd: Path, done: dict) -> str | None:
    minimum = done.get("min_free_gb")
    if not minimum:
        return None
    free_gb = shutil.disk_usage(cwd).free / 1e9
    if free_gb < minimum:
        return f"only {free_gb:.0f} GB free on this disk (minimum {minimum}): clean up and tell the coordinator"
    return None


def collect_failures(config: dict, cwd: Path, log_dir: Path) -> list[str]:
    done = config.get("done", {})
    failures = []
    for name in done.get("require", DEFAULT_REQUIRE):
        check = CHECKS.get(name)
        if check is None:
            failures.append(f"unknown check '{name}' in [done].require")
        elif problem := check(cwd):
            failures.append(problem)
    if not failures:  # gates are slow; do not run them on a slice that is visibly unfinished
        failures.extend(run_gates(config, cwd, log_dir))
    if problem := check_free_space(cwd, done):
        failures.append(problem)
    return failures


def retries_exhausted(state_file: Path, key: str, failures: list[str], limit: int) -> bool:
    """Count consecutive identical failure sets per session and agent."""
    digest = hashlib.sha256("\n".join(failures).encode()).hexdigest()
    state = load_state(state_file)
    previous = state.get(key, {})
    count = previous.get("count", 0) + 1 if previous.get("digest") == digest else 1
    state[key] = {"digest": digest, "count": count, "failures": failures}
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return count > limit


def load_state(state_file: Path) -> dict:
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def clear_state(state_file: Path, key: str) -> None:
    state = load_state(state_file)
    if state.pop(key, None) is not None:
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def auto_clean(config: dict, cwd: Path) -> None:
    command = config.get("commands", {}).get("clean")
    if not (config.get("done", {}).get("auto_clean") and command):
        return
    code, out = run(shlex.split(command), cwd, timeout=600)
    if code != 0:
        print(f"nonslop: clean command failed: `{command}`: {out[-300:]}", file=sys.stderr)


def main() -> int:
    hook_input = read_hook_input()
    if (hook_input.get("last_assistant_message") or "").lstrip().startswith("BLOCKED"):
        return 0
    cwd = start_dir(hook_input)
    loaded = load_config(cwd)
    if loaded is None:
        return 0
    config, root = loaded
    done = config.get("done", {})

    code, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if code != 0 or not branch.startswith(done.get("branch_prefix", "claude/")):
        return 0

    log_dir = scratch_dir(config, root)
    state_file = log_dir / "done-check.json"
    key = f"{hook_input.get('session_id', 'unknown')}:{hook_input.get('agent_id', 'main')}"

    failures = collect_failures(config, cwd, log_dir)
    if not failures:
        clear_state(state_file, key)
        auto_clean(config, cwd)
        return 0
    if retries_exhausted(state_file, key, failures, done.get("stop_retries", 2)):
        return 0

    print("nonslop done-check: slice is not finished:", file=sys.stderr)
    for problem in failures:
        print(f"  - {problem}", file=sys.stderr)
    print("If you cannot resolve this, end with a report that starts with BLOCKED.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
