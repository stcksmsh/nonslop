"""Project gates: the commands a project declares must pass before work counts as done.

A gate is a key of [commands] in .nonslop.toml that is listed in [done].run.
Each one is run without a shell; its full output goes to a log file and only
the tail is reported, so a failing build never floods an agent's context.
"""

import shlex
import subprocess
from pathlib import Path

TAIL_LINES = 25
TAIL_WIDTH = 200


def _tail(log: Path) -> str:
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-TAIL_LINES:]
    return "\n".join(f"      {line[:TAIL_WIDTH]}" for line in lines)


def run_gate(name: str, command: str, cwd: Path, log_dir: Path, timeout: int) -> str | None:
    """Run one gate. Returns a failure description, or None when it passed."""
    log = log_dir / f"gate-{name}.log"
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
    if result.returncode == 0:
        return None
    return f"gate '{name}' failed (exit {result.returncode}): `{command}`\n{_tail(log)}\n      full log: {log}"


def run_gates(config: dict, cwd: Path, log_dir: Path) -> list[str]:
    """Run every gate in [done].run, in order, stopping at the first failure."""
    done = config.get("done", {})
    commands = config.get("commands", {})
    timeout = done.get("gate_timeout_s", 1800)
    for name in done.get("run", []):
        command = commands.get(name)
        if not command:
            return [f"gate '{name}' is listed in [done].run but [commands].{name} is empty"]
        if failure := run_gate(name, command, cwd, log_dir, timeout):
            return [failure]
    return []
