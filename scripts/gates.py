"""Project gates: the commands a project declares must pass before work counts as done.

A gate is a key of [commands] in .nonslop.toml that is listed in [done].run.
Each one is run without a shell; its full output goes to a log file. What is reported is built to
be read in one glance: the lines that look like failures first, then the tail, so a failure that
scrolled past the end of a long build is not lost and a failing build never floods a context.

A gate that exits 0 is believed, with two exceptions. [done.expect] can name a pattern its output
must contain (`test = "\\d+ passed"`), which catches a command that "passed" by running nothing. And
a pass is remembered per (command, commit): the same gate on the same clean commit is not run twice.
"""

import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path

TAIL_LINES = 12
FAILURE_LINES = 12
WIDTH = 200
FAILURE = re.compile(r"\bFAIL(ED|URE)?\b|\bERROR\b|\berror(\[|:)|Error:|panicked at|AssertionError|Traceback \(most|✗|✖|not ok \d")


def _report(log: Path) -> str:
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    tail_start = max(0, len(lines) - TAIL_LINES)
    failures = [(n, line) for n, line in enumerate(lines[:tail_start]) if FAILURE.search(line)][:FAILURE_LINES]
    out = [f"      {n + 1}: {line[:WIDTH]}" for n, line in failures]
    if failures:
        out.append("      ...")
    out += [f"      {line[:WIDTH]}" for line in lines[tail_start:]]
    return "\n".join(out)


def _commit_key(name: str, command: str, cwd: Path) -> str | None:
    """Identity of this gate on this exact tree, or None when the tree has uncommitted changes."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=False)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, check=False)
    except OSError:
        return None
    if head.returncode != 0 or dirty.returncode != 0 or dirty.stdout.strip():
        return None
    return hashlib.sha256(f"{name}\0{command}\0{head.stdout.strip()}".encode()).hexdigest()


def _passed_before(cache: Path, key: str | None) -> bool:
    if key is None:
        return False
    try:
        return key in json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False


def _remember(cache: Path, key: str | None) -> None:
    if key is None:
        return
    try:
        known = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        known = []
    try:
        cache.write_text(json.dumps((known + [key])[-200:]), encoding="utf-8")
    except OSError:
        pass


def run_gate(name: str, command: str, cwd: Path, log_dir: Path, timeout: int, expect: str | None = None) -> str | None:
    """Run one gate. Returns a failure description, or None when it passed."""
    log = log_dir / f"gate-{name}.log"
    cache = log_dir / "gate-passes.json"
    key = _commit_key(name, command, cwd)
    if _passed_before(cache, key):
        return None
    try:
        with log.open("w", encoding="utf-8") as handle:
            result = subprocess.run(
                shlex.split(command), cwd=cwd, stdout=handle, stderr=subprocess.STDOUT,
                timeout=timeout, check=False,
            )
    except subprocess.TimeoutExpired:
        return f"gate '{name}' timed out after {timeout} s: `{command}` (log: {log})"
    except (OSError, ValueError) as error:
        return f"gate '{name}' could not start: `{command}`: {error}"
    if result.returncode != 0:
        return f"gate '{name}' failed (exit {result.returncode}): `{command}`\n{_report(log)}\n      full log: {log}"
    if expect:
        try:
            shown = re.search(expect, log.read_text(encoding="utf-8", errors="replace"))
        except re.error as error:
            return f"[done.expect].{name} is not a valid pattern: {error}"
        if not shown:
            return (f"gate '{name}' exited 0 but its output does not show `{expect}`: `{command}` may have run "
                    f"nothing\n{_report(log)}\n      full log: {log}")
    _remember(cache, key)
    return None


def run_gates(config: dict, cwd: Path, log_dir: Path, names: list[str] | None = None) -> list[str]:
    """Run every gate in [done].run (or `names`), in order, stopping at the first failure."""
    done = config.get("done", {})
    commands = config.get("commands", {})
    expect = done.get("expect", {})
    timeout = done.get("gate_timeout_s", 1800)
    for name in done.get("run", []) if names is None else names:
        command = commands.get(name)
        if not command:
            return [f"gate '{name}' is listed in [done].run but [commands].{name} is empty"]
        if failure := run_gate(name, command, cwd, log_dir, timeout, expect.get(name)):
            return [failure]
    return []
