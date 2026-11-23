#!/usr/bin/env python3
"""Measure the static gates' recall on the seeded defect set.

Each case in seeded/cases.json gets its own throwaway git repo: the base content is
committed, the new content is written over it, and slopstop's full check (the same
one the Stop hook runs) is run on the diff. A case counts as caught when the check
reports any finding; the rules that fired are recorded so a catch for the wrong
reason can be spotted.

Usage: python3 eval/static/recall.py [--out DIR]
Writes recall.csv to DIR (default .claude/tmp/static-corpus/out/) and prints recall
per category as a markdown table.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCRATCH = REPO / ".claude" / "tmp" / "static-corpus"
sys.path.insert(0, str(REPO / "tools" / "slopstop"))
import slop  # noqa: E402


def text(lines: list[str] | None) -> str | None:
    # cases.json breaks each fake secret with "<<>>" so GitHub push protection
    # does not reject the data file; the seeded repo gets the joined value.
    return None if lines is None else "\n".join(lines).replace("<<>>", "") + "\n"


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def run_case(case: dict) -> list:
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="recall-") as td:
        root = Path(td)
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@t")
        git(root, "config", "user.name", "t")
        p = root / case["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("seed\n")
        if case["base"] is not None:
            p.write_text(text(case["base"]))
        git(root, "add", "-A")
        git(root, "commit", "-qm", "base")
        if case["new"] is None:
            p.unlink()
        else:
            p.write_text(text(case["new"]))
        cfg = slop.load_config(root)
        return slop.run_checks(root, slop.collect_diff(root, "base", "HEAD"), cfg, fast=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=SCRATCH / "out")
    args = ap.parse_args()
    cases = json.loads((HERE / "seeded" / "cases.json").read_text())
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        sys.exit("recall: duplicate case ids in cases.json")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)

    rows = []
    for c in cases:
        found = run_case(c)
        rules = sorted({f.rule for f in found})
        rows.append({"id": c["id"], "category": c["category"], "path": c["path"],
                     "caught": "yes" if found else "no", "rules": " ".join(rules)})

    out_csv = args.out / "recall.csv"
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "category", "path", "caught", "rules"])
        w.writeheader()
        w.writerows(rows)

    per: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        per[r["category"]].append(r)
    print("| category | caught | cases | recall | missed |")
    print("|---|---|---|---|---|")
    total_hit = 0
    for cat, rs in per.items():
        hit = sum(r["caught"] == "yes" for r in rs)
        total_hit += hit
        missed = ", ".join(r["id"] for r in rs if r["caught"] == "no") or "-"
        print(f"| {cat} | {hit} | {len(rs)} | {hit / len(rs):.0%} | {missed} |")
    print(f"| **all** | {total_hit} | {len(rows)} | {total_hit / len(rows):.0%} | |")
    # recall depends on which analyzers are installed, so say which ones ran
    tools = sorted({t for ts in [*slop.TOOLS_BY_LANG.values(), slop.TOOLS_ANY] for alt in ts for t in alt.split("|") if slop.have(t)})
    print(f"\nanalyzers found: {' '.join(tools) or 'none'}\nwrote {out_csv}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
