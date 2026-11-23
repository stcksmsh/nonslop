"""`nonslop slice ...` and `nonslop status`: the coordinator's deterministic half.

  nonslop slice new <brief.md> [--force]   lint a builder prompt, refuse scope overlap with a slice
                                           in flight, write the slice record
  nonslop slice verify <branch>            check the slice at its pushed head in a fresh worktree:
                                           slop checks, the project's gates, scope, default branch
                                           merged in. The builder's own claims are not consulted.
  nonslop slice review <branch> <clean|minor|must-fix> [--sha <sha>]
                                           record a reviewer verdict against the head it judged
  nonslop slice close <branch> <merged|closed>
  nonslop slice show <branch>
  nonslop status [--no-remote]             every slice branch and worktree: PR, head, record,
                                           what is stale, what holds unsaved work

No model is involved in any of these.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import slices
from gates import run_gates
from nonslop_config import default_branch, git_out, load_config, main_root, read_json, state_dir

SLOP = Path(__file__).resolve().parent.parent / "tools" / "slopstop" / "slop.py"
VERDICTS = ("clean", "minor", "must-fix")


def project() -> tuple[dict, Path]:
    loaded = load_config(Path.cwd())
    if loaded is None:
        sys.exit("nonslop: no .nonslop.toml here (run `nonslop init`)")
    return loaded


def prefix_of(config: dict) -> str:
    return config.get("done", {}).get("branch_prefix", "claude/")


def remote_head(root: Path, branch: str, fetch: bool = True) -> str | None:
    if fetch:  # separately: a branch missing on origin must not stop the default branch from updating
        git_out(["fetch", "--quiet", "origin", default_branch(root)], root, timeout=120)
        git_out(["fetch", "--quiet", "origin", branch], root, timeout=120)
    for ref in (f"origin/{branch}", branch):
        code, sha = git_out(["rev-parse", "--verify", "-q", f"{ref}^{{commit}}"], root)
        if code == 0:
            return sha
    return None


# ---------------------------------------------------------------- new

def cmd_new(args: list[str]) -> int:
    force = "--force" in args
    paths = [a for a in args if not a.startswith("--")]
    if len(paths) != 1:
        sys.exit("usage: nonslop slice new <brief.md> [--force]")
    config, root = project()
    try:
        text = Path(paths[0]).read_text(encoding="utf-8")
    except OSError as error:
        sys.exit(f"nonslop: {error}")
    fields, problems = slices.parse_brief(text, prefix_of(config))
    missing = [glob for glob in fields["scope_in"] if not any(ch in glob for ch in "*?[") and not (root / glob).exists()]
    if missing:
        print(f"note: scope names paths that do not exist yet (fine if the slice creates them): {', '.join(missing)}")
    if problems:
        print("nonslop: this brief is not ready to dispatch:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    existing = slices.load(config, root, fields["branch"])
    if existing and existing.get("status") in slices.OPEN and not force:
        print(f"nonslop: a slice record for `{fields['branch']}` is already open (status {existing['status']}). "
              "Use another branch name, close it with `nonslop slice close`, or pass --force to replace it.")
        return 1
    tracked = git_out(["ls-files"], root)[1].splitlines()
    clashes = slices.overlapping(fields, slices.all_records(config, root), tracked)
    if clashes and not force:
        print("nonslop: this slice's scope overlaps a slice in flight; two builders must not share a file:")
        for branch, shared in clashes.items():
            print(f"  - {branch}: {', '.join(shared[:6])}" + (f" (+{len(shared) - 6} more)" if len(shared) > 6 else ""))
        print("Narrow the scope, wait for that slice to merge, or pass --force if the overlap is intended.")
        return 1
    record = {**fields, "status": "open", "brief": str(Path(paths[0]).resolve()), "created": int(time.time()),
              "reviews": [], "dispatches": existing.get("dispatches", 0) + 1 if existing else 1}
    slices.save(config, root, record)
    print(f"ok  {record['branch']}: {len(record['done'])} done item(s), scope {', '.join(record['scope_in'])}")
    return 0


# ---------------------------------------------------------------- verify

def cmd_verify(args: list[str]) -> int:
    if len(args) != 1:
        sys.exit("usage: nonslop slice verify <branch>")
    config, root = project()
    branch = args[0]
    main = main_root(root) or root
    default = default_branch(main)
    head = remote_head(main, branch)
    if head is None:
        sys.exit(f"nonslop: no branch `{branch}` on origin or locally")
    failures: list[str] = []
    notes: list[str] = []
    base = git_out(["merge-base", f"origin/{default}", head], main)[1]
    if git_out(["merge-base", "--is-ancestor", f"origin/{default}", head], main)[0] != 0:
        failures.append(f"`{branch}` does not contain the current `origin/{default}`: merge it in and re-run the checks")
    tree = state_dir(config, main) / "verify" / head[:12]
    git_out(["worktree", "remove", "--force", str(tree)], main)  # a leftover of an interrupted verify, ours alone
    code, _ = git_out(["worktree", "add", "--detach", str(tree), head], main, timeout=120)
    if code != 0:
        sys.exit(f"nonslop: could not create a worktree for {head[:9]} at {tree}")
    try:
        loaded = load_config(tree)
        tree_config = loaded[0] if loaded else config
        if base:
            changed = git_out(["diff", "--name-only", f"{base}..{head}"], main)[1].splitlines()
            record = slices.load(config, main, branch)
            if stray := slices.outside_scope(record, changed):
                failures.append(f"changed outside the slice's scope: {', '.join(stray[:8])}")
            result = subprocess.run([sys.executable, str(SLOP), "check", "--base", base], cwd=tree,
                                    capture_output=True, text=True, check=False)
            if result.returncode != 0:
                failures.append("slop checks: " + (result.stdout.strip() or result.stderr.strip())[:1500])
        log_dir = state_dir(config, main) / "verify"
        gates = tree_config.get("verify", {}).get("run") or tree_config.get("done", {}).get("run", [])
        if gates:
            failures.extend(run_gates(tree_config, tree, log_dir, gates))
        else:
            notes.append("no gates configured in [done].run or [verify].run: only slop checks and scope were verified")
    finally:
        git_out(["worktree", "remove", "--force", str(tree)], main)
    ok = not failures
    fields: dict = {"verify": {"sha": head, "ok": ok, "failures": failures, "notes": notes, "ts": int(time.time())}}
    record = slices.load(config, main, branch)
    if ok and record.get("status") == "released":
        fields["status"] = "open"  # what was let go unresolved has since been proven
    slices.touch(config, main, branch, **fields)
    for line in notes:
        print(f"note: {line}")
    for failure in failures:
        print(f"FAIL {failure}")
    print(json.dumps({"type": "verdict", "slice": branch, "sha": head, "ok": ok, "failures": len(failures)}))
    return 0 if ok else 1


# ---------------------------------------------------------------- review / close / show

def cmd_review(args: list[str]) -> int:
    sha = None
    if "--sha" in args:
        at = args.index("--sha")
        sha = args[at + 1] if at + 1 < len(args) else None
        args = args[:at] + args[at + 2:]
    if len(args) != 2 or args[1] not in VERDICTS:
        sys.exit("usage: nonslop slice review <branch> <clean|minor|must-fix> [--sha <sha>]")
    config, root = project()
    branch, verdict = args
    main = main_root(root) or root
    head = remote_head(main, branch)
    if head is None:
        sys.exit(f"nonslop: no branch `{branch}` on origin or locally")
    if sha and not head.startswith(sha):
        print(f"nonslop: the reviewer judged {sha[:9]} but `{branch}` is now at {head[:9]}. "
              "That verdict is stale: review the new head.")
        return 1
    record = slices.load(config, main, branch) or {"branch": branch, "status": "open", "scope_in": [], "done": []}
    reviews = [r for r in record.get("reviews", []) if r.get("sha") != head]
    reviews.append({"sha": head, "verdict": verdict, "ts": int(time.time())})
    record["reviews"] = reviews
    slices.save(config, main, record)
    rounds = slices.must_fix_rounds(record)
    print(f"ok  {branch} at {head[:9]}: {verdict} (must-fix rounds so far: {rounds})")
    if verdict == "must-fix" and rounds >= slices.REVIEW_CAP:
        print(f"ESCALATE: {rounds} review rounds have not converged. Stop sending it back; "
              "give the owner `ACTION: decide` with the open findings.")
    return 0


def cmd_close(args: list[str]) -> int:
    if len(args) != 2 or args[1] not in ("merged", "closed"):
        sys.exit("usage: nonslop slice close <branch> <merged|closed>")
    config, root = project()
    if not slices.load(config, root, args[0]):
        sys.exit(f"nonslop: no slice record for `{args[0]}`")
    slices.touch(config, root, args[0], status=args[1])
    print(f"ok  {args[0]}: {args[1]}")
    return 0


def cmd_show(args: list[str]) -> int:
    if len(args) != 1:
        sys.exit("usage: nonslop slice show <branch>")
    config, root = project()
    record = slices.load(config, root, args[0])
    if not record:
        sys.exit(f"nonslop: no slice record for `{args[0]}`")
    print(json.dumps(record, indent=2))
    return 0


def cmd_slice(args: list[str]) -> int:
    commands = {"new": cmd_new, "verify": cmd_verify, "review": cmd_review, "close": cmd_close, "show": cmd_show}
    if not args or args[0] not in commands:
        print((__doc__ or "").strip())
        return 2
    return commands[args[0]](args[1:])


# ---------------------------------------------------------------- status

def worktrees(root: Path) -> dict[str, Path]:
    """branch -> worktree path, for every worktree that is on a branch."""
    out: dict[str, Path] = {}
    path = None
    path: Path | None = None
    for line in git_out(["worktree", "list", "--porcelain"], root)[1].splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:])
        elif line.startswith("branch refs/heads/") and path is not None:
            out[line[18:]] = path
    return out


def pull_requests(root: Path) -> dict[str, dict] | None:
    fields = "number,headRefName,headRefOid,state,isDraft,mergeable,statusCheckRollup"
    try:
        result = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "100", "--json", fields],
                                cwd=root, capture_output=True, text=True, timeout=40, check=False)
        rows = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    if rows is None:
        return None
    out: dict[str, dict] = {}
    for row in rows:  # newest first; keep the newest per branch
        out.setdefault(row["headRefName"], row)
    return out


def ci_word(pr: dict) -> str:
    states = [(c.get("conclusion") or c.get("state") or c.get("status") or "").upper() for c in pr.get("statusCheckRollup") or []]
    if not states:
        return "no-ci"
    if any(s in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT") for s in states):
        return "ci-failing"
    if any(s in ("PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "") for s in states):
        return "ci-running"
    return "ci-green"


def slice_lines(config: dict, root: Path, remote: bool) -> list[str]:
    main = main_root(root) or root
    prefix = prefix_of(config)
    default = default_branch(main)
    if remote:
        git_out(["fetch", "--quiet", "--prune", "origin"], main, timeout=120)
    records = {r["branch"]: r for r in slices.all_records(config, main)}
    trees = worktrees(main)
    prs = pull_requests(main) if remote else None
    refs = git_out(["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin"], main)[1].splitlines()
    branches = {ref.removeprefix("origin/") for ref in refs}
    names = sorted(b for b in branches | set(records) | set(trees) if b.startswith(prefix)
                   and (b in branches or b in trees or records.get(b, {}).get("status") in slices.OPEN))
    lines = []
    for branch in names:
        record = records.get(branch, {})
        if record.get("status") in ("merged", "closed") and branch not in trees and (prs or {}).get(branch, {}).get("state") != "OPEN":
            continue
        head = remote_head(main, branch, fetch=False) or ""
        parts = [f"{branch} @{head[:9] or 'no-commit'}"]
        actions = []
        if prs is not None:
            pr = prs.get(branch)
            if pr is None:
                parts.append("no PR")
                actions.append("open the draft PR (or the builder died before it): reconcile before re-dispatching")
            else:
                parts.append(f"PR #{pr['number']} {pr['state'].lower()}{' draft' if pr.get('isDraft') else ''} {ci_word(pr)}")
                if pr["state"] == "MERGED" and record.get("status") != "merged":
                    actions.append(f"merged: `nonslop slice close {branch} merged`, then remove its worktree if clean")
                if pr["state"] == "OPEN" and pr.get("mergeable") == "CONFLICTING":
                    actions.append("conflicts with the default branch: have the builder merge it in")
        if head and git_out(["merge-base", "--is-ancestor", f"origin/{default}", head], main)[0] != 0:
            parts.append(f"behind {default}")
        if not record:
            parts.append("no slice record")
        else:
            parts.append(f"record {record.get('status', '?')}")
            if record.get("status") == "released":
                actions.append("released with finish checks failing: do not treat as DONE; `nonslop slice verify` or re-dispatch")
            if record.get("status") == "blocked":
                actions.append("builder is BLOCKED: answer it, or ask the owner")
            verify, review = record.get("verify") or {}, slices.last_review(record)
            parts.append("verify " + ("none" if not verify else ("stale" if verify.get("sha") != head else
                                                                 "ok" if verify.get("ok") else "FAILED")))
            parts.append("review " + ("none" if not review else ("stale" if review.get("sha") != head else review["verdict"])))
            if slices.must_fix_rounds(record) >= slices.REVIEW_CAP:
                actions.append(f"{slices.must_fix_rounds(record)} must-fix rounds: escalate to the owner")
        if tree := trees.get(branch):
            dirty = bool(git_out(["status", "--porcelain"], tree)[1])
            unpushed = bool(git_out(["log", "--oneline", "HEAD", "--not", "--remotes", "-n", "1"], tree)[1])
            parts.append(f"worktree {tree}" + (" DIRTY" if dirty else "") + (" UNPUSHED" if unpushed else ""))
            if dirty or unpushed:
                actions.append("worktree holds work that is nowhere else: do not remove it; resume or commit and push it")
        lines.append("- " + " | ".join(parts))
        lines.extend(f"    -> {action}" for action in actions)
    return lines


def cmd_status(args: list[str]) -> int:
    config, root = project()
    lines = slice_lines(config, root, remote="--no-remote" not in args)
    print("\n".join(lines) if lines else "no slices in flight")
    released = read_json(state_dir(config, root) / "done-check.json")
    if stuck := [key for key, value in released.items() if value.get("failures")]:
        print(f"finish checks currently failing for: {', '.join(sorted(stuck))}")
    return 0
