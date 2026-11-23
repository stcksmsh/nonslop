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

Exit 2 with the failures on stderr keeps the agent working. Once the same set
of failures has come back more than [done].stop_retries times on a branch (in
a row or not: A-B-A-B counts) the hook lets the agent stop, so it cannot loop
forever. That is a release, not a pass: it is written to the slice record as
`released` with the failures, where the coordinator, `nonslop status` and the
merge guard see it. A subagent that ends on a branch without the slice prefix
is not skipped: it has left its slice, and that is a failure.
"""

import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slices  # noqa: E402
from gates import run_gates  # noqa: E402
from log_event import append  # noqa: E402
from nonslop_config import (default_branch, git_out, load_config, read_hook_input, scratch_dir,  # noqa: E402
                            start_dir, state_dir, unchanged_since_start, write_json)

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
    code, out = run(["gh", "pr", "view", "--json", "number,state"], cwd)
    if code != 0:
        return "no pull request for this branch: open a draft PR"
    try:
        state = json.loads(out).get("state")
    except json.JSONDecodeError:
        return None
    return None if state == "OPEN" else f"the pull request for this branch is {state}: open a new draft PR"


CHECKS = {"clean_tree": check_clean_tree, "pushed": check_pushed, "pr": check_pr}


def check_free_space(cwd: Path, done: dict) -> str | None:
    minimum = done.get("min_free_gb")
    if not minimum:
        return None
    free_gb = shutil.disk_usage(cwd).free / 1e9
    if free_gb < minimum:
        return f"only {free_gb:.0f} GB free on this disk (minimum {minimum}): clean up and tell the coordinator"
    return None


def changed_files(cwd: Path) -> list[str]:
    """Paths this branch changes relative to where it left the default branch."""
    code, base = git_out(["merge-base", f"origin/{default_branch(cwd)}", "HEAD"], cwd)
    if code != 0:
        return []
    code, out = git_out(["diff", "--name-only", f"{base}..HEAD"], cwd)
    return out.splitlines() if code == 0 else []


def check_scope(config: dict, cwd: Path, branch: str) -> str | None:
    record = slices.load(config, cwd, branch)
    stray = slices.outside_scope(record, changed_files(cwd)) if record else []
    if not stray:
        return None
    shown = ", ".join(stray[:8]) + (f" (+{len(stray) - 8} more)" if len(stray) > 8 else "")
    return (f"changed outside the slice's scope ({', '.join(record['scope_in'])}): {shown}. "
            "Take those changes out, or end with BLOCKED and say why the slice needs them")


def collect_failures(config: dict, cwd: Path, log_dir: Path, branch: str) -> list[str]:
    done = config.get("done", {})
    failures = []
    if problem := check_scope(config, cwd, branch):
        failures.append(problem)
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
    """Count how often each exact failure set has come back for this branch, in a row or not."""
    digest = hashlib.sha256("\n".join(failures).encode()).hexdigest()
    state = load_state(state_file)
    counts = state.get(key, {}).get("counts", {})
    counts[digest] = counts.get(digest, 0) + 1
    state[key] = {"counts": counts, "failures": failures}
    write_json(state_file, state)
    return counts[digest] > limit


def load_state(state_file: Path) -> dict:
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def clear_state(state_file: Path, key: str) -> None:
    state = load_state(state_file)
    if state.pop(key, None) is not None:
        write_json(state_file, state)


def auto_clean(config: dict, cwd: Path) -> None:
    command = config.get("commands", {}).get("clean")
    if not (config.get("done", {}).get("auto_clean") and command):
        return
    code, out = run(shlex.split(command), cwd, timeout=600)
    if code != 0:
        print(f"nonslop: clean command failed: `{command}`: {out[-300:]}", file=sys.stderr)


def note_blocked(config: dict, cwd: Path) -> None:
    """Record that a slice stopped to ask, and whether it left unsaved work behind."""
    code, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if code != 0 or not branch.startswith(config.get("done", {}).get("branch_prefix", "claude/")):
        return
    dirty = bool(run(["git", "status", "--porcelain"], cwd)[1])
    slices.touch(config, cwd, branch, status="blocked",
                 blocked={"sha": git_out(["rev-parse", "HEAD"], cwd)[1], "uncommitted": dirty, "worktree": str(cwd)})


def main() -> int:
    start = time.monotonic()
    hook_input = read_hook_input()
    session = hook_input.get("session_id", "")
    cwd = start_dir(hook_input)
    if (hook_input.get("last_assistant_message") or "").lstrip().startswith("BLOCKED"):
        # A BLOCKED report passes whatever the config says; the log and the slice record need it.
        try:
            loaded = load_config(cwd)
        except (OSError, ValueError):
            loaded = None
        if loaded is not None:
            append(*loaded, "done-check", {"session": session, "agent": hook_input.get("agent_id", ""),
                                           "decision": "skip", "reason": "BLOCKED report"})
            note_blocked(loaded[0], cwd)
        return 0
    loaded = load_config(cwd)
    if loaded is None:
        return 0
    config, root = loaded

    def log(decision: str, **extra: object) -> None:
        ms = int((time.monotonic() - start) * 1000)
        append(config, root, "done-check", {"session": session, "agent": hook_input.get("agent_id", ""),
                                            "decision": decision, "ms": ms, **extra})

    if unchanged_since_start(config, root, cwd, session):
        log("skip", reason="unchanged")
        return 0
    done = config.get("done", {})

    prefix = done.get("branch_prefix", "claude/")
    code, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    log_dir = scratch_dir(config, root)
    state_file = state_dir(config, cwd) / "done-check.json"
    if code != 0 or not branch.startswith(prefix):
        if not hook_input.get("agent_id"):
            log("skip", reason="not a slice branch", branch=branch)
            return 0
        # A subagent that changed something and is not on a slice branch has left its slice.
        failures = [f"you are on `{branch or 'no branch'}`, not on a slice branch (`{prefix}<slice>`): "
                    "move your work to the branch named in your prompt, from the default branch on the remote"]
        key = f"{branch}:offbranch"
    else:
        key = branch
        failures = collect_failures(config, cwd, log_dir, branch)
    sha = git_out(["rev-parse", "HEAD"], cwd)[1]
    if not failures:
        clear_state(state_file, key)
        auto_clean(config, cwd)
        slices.touch(config, cwd, branch, status="open", done_check={"sha": sha, "ok": True})
        log("pass", branch=branch)
        return 0
    if retries_exhausted(state_file, key, failures, done.get("stop_retries", 2)):
        if branch.startswith(prefix):
            slices.touch(config, cwd, branch, status="released",
                         done_check={"sha": sha, "ok": False, "failures": failures})
        log("released", branch=branch, failures=failures)
        print(json.dumps({"systemMessage": "nonslop: this slice was let go with its finish checks still failing "
                                           f"({len(failures)}); it is recorded as released, not done."}))
        return 0
    log("fail", branch=branch, failures=failures)

    print("nonslop done-check: slice is not finished:", file=sys.stderr)
    for problem in failures:
        print(f"  - {problem}", file=sys.stderr)
    print("If you cannot resolve this, end with a report that starts with BLOCKED.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
