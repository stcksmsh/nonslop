"""`nonslop stats`: what the gates did and what the work cost, from logs that already exist.

Nothing here is estimated and no model is called. Sources:
  - slopstop's hit log (`.git/slopstop/hits.jsonl`, also in each worktree's git dir): every hook
    call with its wall time, every finding with rule and decision;
  - the nonslop hook logs in the scratch dir (done-check, slop-stop, guard, merge-guard);
  - Claude Code's session transcripts (`~/.claude*/projects/<project>/`, subagents included): the
    token counts the API reported, per git branch;
  - the slice records: review rounds, verify results, releases.
A number that cannot be measured is left out, not guessed.

  nonslop stats [--json] [--since <days>]
"""

import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import slices
from nonslop_config import git_out, load_config, main_root, state_dir

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def read_jsonl(path: Path) -> list[dict]:
    out = []
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    out.append(record)
    except OSError:
        pass
    return out


def epoch(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        for form in (value.replace("Z", "+00:00"), value):
            try:
                return datetime.fromisoformat(form).timestamp()
            except ValueError:
                pass
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z").timestamp()
        except ValueError:
            pass
    return 0.0


def gate_stats(main: Path, since: float) -> dict:
    git_dir = Path(git_out(["rev-parse", "--path-format=absolute", "--git-common-dir"], main)[1] or main / ".git")
    logs = [git_dir / "slopstop" / "hits.jsonl", *git_dir.glob("worktrees/*/slopstop/hits.jsonl")]
    rules: dict[str, Counter] = defaultdict(Counter)
    timing: dict[str, list[int]] = defaultdict(list)
    calls: dict[str, Counter] = defaultdict(Counter)
    for log in logs:
        for record in read_jsonl(log):
            if epoch(record.get("ts")) < since:
                continue
            event = record.get("event", "?")
            if record.get("rule"):
                rules[record["rule"]][f"{event}:{record.get('decision')}"] += 1
            else:
                calls[event][record.get("decision", "?")] += 1
                if isinstance(record.get("ms"), int):
                    timing[event].append(record["ms"])
    hooks = {}
    for event, values in timing.items():
        values.sort()
        hooks[event] = {"calls": len(values), "p50_ms": int(statistics.median(values)),
                        "p95_ms": values[min(len(values) - 1, int(len(values) * 0.95))],
                        "decisions": dict(calls[event])}
    return {"rules": {rule: dict(counts) for rule, counts in sorted(rules.items())}, "hooks": hooks}


def hook_log_stats(scratch: Path, since: float) -> dict:
    out = {}
    for name in ("done-check", "slop-stop", "guard", "merge-guard", "permission-denied"):
        records = [r for r in read_jsonl(scratch / f"{name}.jsonl") if epoch(r.get("ts")) >= since]
        if records:
            key = "rule" if name == "guard" else "decision"
            out[name] = dict(Counter(str(r.get(key) or r.get("decision") or "event") for r in records))
    return out


def transcript_dirs(main: Path) -> list[Path]:
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(main))
    out = []
    for home in Path.home().glob(".claude*"):
        projects = home / "projects"
        if projects.is_dir():
            out += [d for d in projects.iterdir() if d.is_dir() and (d.name == slug or d.name.startswith(slug + "-"))]
    return out


def token_stats(main: Path, since: float) -> dict:
    """Tokens the API reported, per git branch. One API response can span several transcript lines
    with the same message id; it is counted once."""
    seen: set[str] = set()
    branches: dict[str, dict] = {}
    for directory in transcript_dirs(main):
        for path in [*directory.glob("*.jsonl"), *directory.glob("*/subagents/*.jsonl")]:
            subagent = path.parent.name == "subagents"
            for record in read_jsonl(path):
                message = record.get("message")
                if record.get("type") != "assistant" or not isinstance(message, dict):
                    continue
                usage, stamp = message.get("usage"), epoch(record.get("timestamp"))
                if not isinstance(usage, dict) or stamp < since:
                    continue
                identity = str(message.get("id") or record.get("uuid") or "")
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                row = branches.setdefault(record.get("gitBranch") or "(none)", {
                    "requests": 0, "subagent_requests": 0, "sessions": set(), "first": stamp, "last": stamp,
                    **{field: 0 for field in TOKEN_FIELDS}})
                row["requests"] += 1
                row["subagent_requests"] += subagent
                row["sessions"].add(record.get("sessionId"))
                row["first"], row["last"] = min(row["first"], stamp), max(row["last"], stamp)
                for field in TOKEN_FIELDS:
                    row[field] += usage.get(field) or 0
    for row in branches.values():
        row["sessions"] = len(row["sessions"])
        row["span_min"] = round((row.pop("last") - row.pop("first")) / 60)
    return branches


def slice_stats(config: dict, main: Path) -> dict:
    out = {}
    for record in slices.all_records(config, main):
        verify = record.get("verify") or {}
        out[record["branch"]] = {
            "status": record.get("status"), "dispatches": record.get("dispatches", 0),
            "review_rounds": len(record.get("reviews") or []), "must_fix_rounds": slices.must_fix_rounds(record),
            "verify": None if not verify else bool(verify.get("ok")),
        }
    return out


def collect(config: dict, root: Path, since: float) -> dict:
    main = main_root(root) or root
    return {"gates": gate_stats(main, since), "hook_logs": hook_log_stats(state_dir(config, main), since),
            "tokens_by_branch": token_stats(main, since), "slices": slice_stats(config, main)}


def render(data: dict) -> str:
    lines = ["## Gate findings (rule: event:decision count)"]
    lines += [f"  {rule:26} " + "  ".join(f"{k} {v}" for k, v in sorted(counts.items()))
              for rule, counts in data["gates"]["rules"].items()] or ["  none logged"]
    lines.append("## Hook cost")
    lines += [f"  {event:5} calls {h['calls']:5}  p50 {h['p50_ms']} ms  p95 {h['p95_ms']} ms  {h['decisions']}"
              for event, h in sorted(data["gates"]["hooks"].items())] or ["  none logged"]
    lines.append("## Finish checks and guards")
    lines += [f"  {name:18} {counts}" for name, counts in data["hook_logs"].items()] or ["  none logged"]
    lines.append("## Tokens by branch (as reported by the API; in / out / cache read / cache write)")
    for branch, row in sorted(data["tokens_by_branch"].items(), key=lambda item: -item[1]["output_tokens"]):
        lines.append(f"  {branch[:40]:40} req {row['requests']:5} (subagent {row['subagent_requests']})  "
                     f"{row['input_tokens']:>9,} / {row['output_tokens']:>9,} / {row['cache_read_input_tokens']:>12,} / "
                     f"{row['cache_creation_input_tokens']:>10,}  sessions {row['sessions']}  span {row['span_min']} min")
    if not data["tokens_by_branch"]:
        lines.append("  no transcripts found for this project")
    lines.append("## Slices")
    lines += [f"  {branch[:40]:40} {row}" for branch, row in data["slices"].items()] or ["  no slice records"]
    return "\n".join(lines)


def cmd_stats(args: list[str]) -> int:
    loaded = load_config(Path.cwd())
    if loaded is None:
        sys.exit("nonslop: no .nonslop.toml here (run `nonslop init`)")
    since = 0.0
    if "--since" in args:
        try:
            since = time.time() - float(args[args.index("--since") + 1]) * 86400
        except (IndexError, ValueError):
            sys.exit("usage: nonslop stats [--json] [--since <days>]")
    data = collect(*loaded, since)
    print(json.dumps(data, indent=2) if "--json" in args else render(data))
    return 0
