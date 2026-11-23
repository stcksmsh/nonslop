"""Slice records: what one slice promised, and what has been proven about it since.

One JSON file per slice branch under the main checkout's scratch, `nonslop/slices/`. The
coordinator creates it from the builder prompt (`nonslop slice new`); the done-check, the
independent verify and the recorded reviews add to it; the merge guard reads it. Everything in a
record that says "passed" is pinned to the commit it was true for, so a later push makes it stale
instead of leaving it looking current.
"""

import fnmatch
import re
import time
from pathlib import Path

from nonslop_config import read_json, state_dir, write_json

REQUIRED_SECTIONS = ("task", "branch", "scope", "done means")
OPEN = ("open", "blocked", "released")
REVIEW_CAP = 3


def record_path(config: dict, cwd: Path, branch: str) -> Path:
    return state_dir(config, cwd) / "slices" / (re.sub(r"[^A-Za-z0-9_.-]", "_", branch) + ".json")


def load(config: dict, cwd: Path, branch: str) -> dict:
    return read_json(record_path(config, cwd, branch))


def save(config: dict, cwd: Path, record: dict) -> None:
    record["updated"] = int(time.time())
    write_json(record_path(config, cwd, record["branch"]), record)


def touch(config: dict, cwd: Path, branch: str, **fields: object) -> dict:
    """Update a record, creating a bare one for a slice that was dispatched without a brief."""
    record = load(config, cwd, branch) or {"branch": branch, "status": "open", "scope_in": [], "done": [],
                                           "reviews": [], "created": int(time.time())}
    record.update(fields)
    save(config, cwd, record)
    return record


def all_records(config: dict, cwd: Path) -> list[dict]:
    directory = state_dir(config, cwd) / "slices"
    records = [read_json(path) for path in sorted(directory.glob("*.json"))] if directory.is_dir() else []
    return [record for record in records if record.get("branch")]


def sections(text: str) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = heading[1].lower()
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in out.items()}


def _globs(text: str) -> list[str]:
    words = re.split(r"[,\s]+", text.replace("`", " "))
    return [word.removeprefix("./") for word in words if word and word not in ("-", "*") and not word.startswith("<")]


def parse_brief(text: str, prefix: str) -> tuple[dict, list[str]]:
    """Read a builder prompt. Returns (record fields, problems); any problem means do not dispatch."""
    found = sections(text)
    problems = [f"section `## {name.capitalize()}` is missing or empty" for name in REQUIRED_SECTIONS
                if not found.get(name)]
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")
    branch = (re.split(r"[,\s]", found.get("branch", "").replace("`", "").strip(), maxsplit=1) or [""])[0]
    if branch and not branch.startswith(prefix):
        problems.append(f"branch `{branch}` does not start with `{prefix}`, so it would not be checked as a slice")
    scope_in: list[str] = []
    scope_out: list[str] = []
    target = None
    for line in found.get("scope", "").splitlines():
        label = re.match(r"^\s*(in|out)\s*:\s*(.*)$", line, re.I)
        if label:
            target = scope_in if label[1].lower() == "in" else scope_out
            target.extend(_globs(label[2]))
        elif target is not None and line.strip():
            target.extend(_globs(line.lstrip(" -*")))
    if found.get("scope") and not scope_in:
        problems.append("`## Scope` has no `In:` paths; name the files or directories the slice may change")
    done = [match[1].strip() for match in re.finditer(r"^\s*(?:\d+[.)]|[-*])\s+(.+)$", found.get("done means", ""), re.M)]
    if found.get("done means") and not done:
        problems.append("`## Done means` must be a numbered list: one checkable end state per line")
    vague = [item for item in done if re.fullmatch(r"(it )?(works|done|complete[sd]?|tests? pass(es)?)\W*", item, re.I)]
    if vague:
        problems.append(f"`Done means` item is not checkable: `{vague[0]}`; say what is observable and how")
    fields = {"title": title, "branch": branch, "scope_in": scope_in, "scope_out": scope_out, "done": done}
    return fields, problems


def in_scope(path: str, globs: list[str]) -> bool:
    for glob in globs:
        bare = glob.rstrip("/")
        if path == bare or path.startswith(bare + "/") or fnmatch.fnmatch(path, glob):
            return True
    return False


def outside_scope(record: dict, changed: list[str]) -> list[str]:
    """Changed paths the slice was not given. No scope recorded means nothing to hold it to."""
    globs = record.get("scope_in") or []
    return [path for path in changed if not in_scope(path, globs)] if globs else []


def overlapping(record: dict, others: list[dict], tracked: list[str]) -> dict[str, list[str]]:
    """In-flight slices whose scope shares a path with `record`: tracked files both would touch, or
    the same glob spelled the same way (which also covers files neither has created yet)."""
    mine = {path for path in tracked if in_scope(path, record.get("scope_in") or [])}
    out: dict[str, list[str]] = {}
    for other in others:
        if other.get("branch") == record.get("branch") or other.get("status") not in OPEN:
            continue
        theirs = other.get("scope_in") or []
        shared = sorted(path for path in mine if in_scope(path, theirs))
        shared += sorted(set(theirs) & set(record.get("scope_in") or []) - set(shared))
        if shared:
            out[other["branch"]] = shared
    return out


def last_review(record: dict) -> dict:
    reviews = record.get("reviews") or []
    return reviews[-1] if reviews else {}


def must_fix_rounds(record: dict) -> int:
    """Blocking verdicts on distinct commits: how often review sent this slice back."""
    return len({review.get("sha") for review in record.get("reviews") or [] if review.get("verdict") == "must-fix"})


def merge_blockers(record: dict, head: str, need: list[str]) -> list[str]:
    """Why this slice is not proven ready at commit `head`. Empty means ready."""
    problems = []
    verify = record.get("verify") or {}
    if "verify" in need:
        if not verify:
            problems.append(f"not verified: run `nonslop slice verify {record.get('branch', '<branch>')}`")
        elif verify.get("sha") != head:
            problems.append(f"verified at {str(verify.get('sha'))[:9]}, but the head is now {head[:9]}: verify again")
        elif not verify.get("ok"):
            problems.append("the last verify failed: " + "; ".join(verify.get("failures", []))[:300])
    review = last_review(record)
    if "review" in need:
        if not review:
            problems.append("no review recorded: review it, then `nonslop slice review <branch> <verdict>`")
        elif review.get("sha") != head:
            problems.append(f"reviewed at {str(review.get('sha'))[:9]}, but the head is now {head[:9]}: review again")
        elif review.get("verdict") == "must-fix":
            problems.append("the last review verdict is must-fix")
    return problems
