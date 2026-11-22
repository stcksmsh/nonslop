#!/usr/bin/env python3
"""Replay slopstop's full check over a repository's merged pull requests.

For each merged PR, the merge commit is checked out in a temporary detached
worktree under .claude/tmp/static-corpus/ of this repo, and
`slop.py check --base <merge>^1 --json` runs in it, so the check sees exactly the
PR's change and reads the target repo's own .nonslop.toml from that commit.
The target repo is only read: no branch is moved, nothing is committed.

Usage: python3 eval/static/replay.py REPO [--limit N] [--out DIR]
Writes <out>/<repo-name>/findings.csv (one row per finding, label/reason empty
for triage) and runs.csv (one row per PR). Rows are flushed as each PR finishes,
so a long run can be watched and a partial run still leaves usable output.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SLOP = REPO / "tools" / "slopstop" / "slop.py"
SCRATCH = REPO / ".claude" / "tmp" / "static-corpus"

FINDING_COLS = ["repo", "pr", "head", "file", "line", "rule", "severity", "tool", "msg", "label", "reason"]
RUN_COLS = ["repo", "pr", "head", "title", "merge", "files_changed", "added_lines", "findings", "seconds", "error"]


def run(cmd: list[str], cwd: Path, check: bool = False, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check, env=env)


def diff_size(repo: Path, sha: str) -> tuple[int, int]:
    r = run(["git", "diff", "--numstat", f"{sha}^1", sha], repo, check=True)
    files = added = 0
    for line in r.stdout.splitlines():
        a, _, _ = line.split("\t", 2)
        files += 1
        added += int(a) if a.isdigit() else 0  # "-" for binary files
    return files, added


def have_commit(repo: Path, sha: str) -> bool:
    return run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], repo).returncode == 0


def remove_worktree(repo: Path, wt: Path) -> None:
    # --force: analyzers may leave untracked reports behind in the checkout
    run(["git", "worktree", "remove", "--force", str(wt)], repo)
    run(["git", "worktree", "prune"], repo)


def check_pr(repo: Path, name: str, pr: dict, env: dict) -> tuple[list[dict], dict]:
    sha = pr["mergeCommit"]["oid"]
    row = {"repo": name, "pr": pr["number"], "head": pr["headRefName"], "title": pr["title"], "merge": sha,
           "files_changed": "", "added_lines": "", "findings": "", "seconds": "", "error": ""}
    if not have_commit(repo, sha):
        run(["git", "fetch", "-q", "origin", sha], repo)
    if not have_commit(repo, sha):
        row["error"] = "merge commit not available locally or on origin"
        return [], row
    row["files_changed"], row["added_lines"] = diff_size(repo, sha)

    wt = SCRATCH / "wt" / f"{name}-{pr['number']}"
    if wt.exists():
        remove_worktree(repo, wt)
    r = run(["git", "worktree", "add", "-q", "--detach", str(wt), sha], repo)
    if r.returncode != 0:
        row["error"] = f"worktree add failed: {r.stderr.strip()[:200]}"
        return [], row
    try:
        t0 = time.monotonic()
        r = run([sys.executable, str(SLOP), "check", "--base", f"{sha}^1", "--json"], wt, env=env)
        row["seconds"] = f"{time.monotonic() - t0:.1f}"
    finally:
        remove_worktree(repo, wt)
    # exit 0 = clean or advisory only, 1 = blocking findings; anything else is a crash
    try:
        found = json.loads(r.stdout) if r.returncode in (0, 1) else None
    except json.JSONDecodeError:
        found = None
    if found is None:
        row["error"] = f"slop exit {r.returncode}: {r.stderr.strip()[-200:]}"
        return [], row
    row["findings"] = len(found)
    rows = [{"repo": name, "pr": pr["number"], "head": pr["headRefName"], "file": f["file"], "line": f["line"],
             "rule": f["rule"], "severity": f["sev"], "tool": f["tool"], "msg": f["msg"], "label": "", "reason": ""}
            for f in found]
    return rows, row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", type=Path, help="path to a local clone whose GitHub remote has the PRs")
    ap.add_argument("--limit", type=int, default=500, help="most recent merged PRs to replay (default 500)")
    ap.add_argument("--out", type=Path, default=SCRATCH / "out")
    args = ap.parse_args()
    if args.limit < 1:
        ap.error("--limit must be positive")

    r = run(["git", "rev-parse", "--show-toplevel"], args.repo)
    if r.returncode != 0:
        sys.exit(f"replay: {args.repo} is not a git repository")
    repo = Path(r.stdout.strip())
    # the GitHub name, not the directory name: the clone may be a worktree with any name
    r = run(["gh", "repo", "view", "--json", "name", "-q", ".name"], repo)
    if r.returncode != 0:
        sys.exit(f"replay: gh repo view failed: {r.stderr.strip()}")
    name = r.stdout.strip()
    r = run(["gh", "pr", "list", "--state", "merged", "--limit", str(args.limit),
             "--json", "number,mergeCommit,headRefName,title"], repo)
    if r.returncode != 0:
        sys.exit(f"replay: gh pr list failed: {r.stderr.strip()}")
    prs = sorted((p for p in json.loads(r.stdout) if p.get("mergeCommit")), key=lambda p: p["number"])

    out = args.out / name
    out.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "wt").mkdir(parents=True, exist_ok=True)
    # Clippy would otherwise rebuild the whole crate graph from scratch in every fresh
    # worktree; one target dir per repo keeps the build incremental across PRs.
    env = {**os.environ, "CARGO_TARGET_DIR": str(SCRATCH / "cargo-target" / name)}

    with (out / "findings.csv").open("w", newline="") as ff, (out / "runs.csv").open("w", newline="") as rf:
        fw = csv.DictWriter(ff, fieldnames=FINDING_COLS)
        rw = csv.DictWriter(rf, fieldnames=RUN_COLS)
        fw.writeheader()
        rw.writeheader()
        for i, pr in enumerate(prs, 1):
            rows, row = check_pr(repo, name, pr, env)
            fw.writerows(rows)
            rw.writerow(row)
            ff.flush()
            rf.flush()
            print(f"[{i}/{len(prs)}] {name}#{pr['number']} findings={row['findings'] or 0} "
                  f"{row['seconds'] or '-'}s {row['error']}", file=sys.stderr)
    print(f"wrote {out}/findings.csv and runs.csv", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
