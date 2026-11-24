"""Hook payload -> decision tests for nonslop's own scripts, plus the slice commands end to end.

Builds a throwaway repository with a bare `origin`, wires it, and feeds each hook the JSON Claude
Code would send. No model, no network. Run: python3 tests/test_hooks.py
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin" / "nonslop"
sys.path.insert(0, str(ROOT / "scripts"))
gates = importlib.import_module("gates")
slices = importlib.import_module("slices")

CONFIG = """\
[commands]
test = "python3 check.py"

[done]
branch_prefix = "claude/"
require = ["clean_tree", "pushed"]
run = ["test"]
stop_retries = 1

[done.expect]
test = "[1-9][0-9]* passed"

[env]
scratch = ".claude/tmp"
"""
BRIEF = """\
# Add the widget

## Task
Add a widget module.

## Branch
`claude/widget`, from origin/main

## Scope
In:  src/widget.py, tests/
Out: everything else

## Done means
1. `src/widget.py` exports `widget()` returning 3.
2. `tests/test_widget.py` fails without the change and passes with it.
"""
passed = failed = 0


def check(name: str, condition: bool, detail: object = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"ok   {name}")
    else:
        failed += 1
        print(f"FAIL {name} {str(detail)[:400]}")


def sh(args: list[str], cwd: Path, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False, env={**os.environ, **env})


def git(cwd: Path, *args: str) -> str:
    result = sh(["git", *args], cwd)
    assert result.returncode == 0, f"git {' '.join(args)}: {result.stderr}"
    return result.stdout.strip()


def hook(script: str, payload: dict, *args: str) -> tuple[int, str, str]:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], input=json.dumps(payload),
                            capture_output=True, text=True, check=False)
    return result.returncode, result.stdout, result.stderr


def guard(cwd: Path, tool: str, tool_input: dict, agent: str = "") -> str:
    payload = {"cwd": str(cwd), "session_id": "t", "tool_name": tool, "tool_input": tool_input}
    if agent:
        payload["agent_id"] = agent
    return hook("guard.py", payload)[1]


def nonslop(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return sh([sys.executable, str(BIN), *args], cwd)


def make_repo(work: Path) -> Path:
    origin, repo = work / "origin.git", work / "repo"
    git(work, "init", "-q", "--bare", "-b", "main", str(origin))
    git(work, "clone", "-q", str(origin), str(repo))
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    (repo / ".nonslop.toml").write_text(CONFIG, encoding="utf-8")
    (repo / ".gitignore").write_text(".claude/tmp/\n.claude/worktrees/\n.env\n", encoding="utf-8")
    (repo / "check.py").write_text("print('3 passed')\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=x\n", encoding="utf-8")
    (repo / ".env.example").write_text("TOKEN=\n", encoding="utf-8")
    git(repo, "add", ".nonslop.toml", ".gitignore", "check.py", "src", ".env.example")
    git(repo, "commit", "-qm", "base")
    git(repo, "push", "-q", "-u", "origin", "main")
    git(repo, "remote", "set-head", "origin", "main")
    return repo


def test_guard(repo: Path) -> None:
    def bash(command: str, agent: str = "") -> str:
        return guard(repo, "Bash", {"command": command}, agent)

    for command in ["git push --force origin claude/x", "git push -f", "git push origin +claude/x",
                    "git push --force-with-lease", "git push origin HEAD:main", "git push origin main",
                    "git push origin :main", "git push", "git add -f secret.bin", "cat .env", "grep TOKEN ./.env",
                    "source .env", "echo '{}' > .claude/tmp/nonslop/done-check.json",
                    "rm .claude/tmp/nonslop/slices/claude_x.json", "head -1 < .env"]:
        check(f"guard denies `{command}`", '"deny"' in bash(command), bash(command))
    for command in ["git push -u origin claude/x", "git push origin --delete claude/old", "cat .env.example",
                    "cp .env.example .env", "git reset --hard origin/main", "git stash list", "ls .claude/tmp/nonslop",
                    "cat .claude/tmp/nonslop/gate-test.log", "git commit -m 'never git push --force'",
                    "git rebase --abort"]:
        check(f"guard allows `{command}`", bash(command).strip() == "", bash(command))
    for command in ["git reset --hard HEAD~1", "git stash", "git clean -fd", "git checkout -- .", "git restore .",
                    "gh pr merge 3 --squash", "gh api -X PUT repos/o/r/pulls/3/merge"]:
        check(f"guard denies a subagent `{command}`", '"deny"' in bash(command, agent="a1"), bash(command, agent="a1"))
    interpreter_reads = ["python3 -c \"print(open('.env').read())\"", "node -e \"require('fs').readFileSync('.env')\"",
                         "bash -c 'cat .env'", "python3.11 load.py .env", "perl -e 'open(F, \".env\")'"]
    for command in interpreter_reads:
        out = bash(command)
        check(f"guard denies interpreter read `{command}`", '"deny"' in out and "secret" in out, out)
    for command in ["echo .env >> .gitignore", "python3 -c \"print(1)\"", "python3 -c \"print(d.key)\"",
                    "node -e \"require('fs').readFileSync('.env.example')\"", "git check-ignore .env", "ls -a"]:
        check(f"guard allows `{command}`", bash(command).strip() == "", bash(command))
    out = bash("git commit --amend -m x")
    check("guard denies amending a pushed commit", '"deny"' in out, out)
    out = bash("git rebase origin/main")
    check("guard denies rebasing a pushed branch", '"deny"' in out, out)
    out = guard(repo, "Read", {"file_path": str(repo / ".env")})
    check("guard denies Read of .env", '"deny"' in out and "secret" in out, out)
    check("guard allows Read of .env.example", guard(repo, "Read", {"file_path": str(repo / ".env.example")}) == "")
    out = guard(repo, "Write", {"file_path": str(repo / ".claude/tmp/nonslop/slices/x.json"), "content": "{}"})
    check("guard denies Write to a slice record", '"deny"' in out, out)
    out = guard(repo, "Edit", {"file_path": 7})
    check("guard denies a payload it cannot read", '"deny"' in out and "internal error" in out, out)
    out = bash("gh pr merge 5 --squash")
    check("guard refuses a coordinator merge it cannot prove ready", '"deny"' in out, out)
    unwired = repo.parent / "unwired"
    unwired.mkdir()
    git(unwired, "init", "-q")
    toml = repo / ".nonslop.toml"
    saved = toml.read_text(encoding="utf-8")
    toml.write_text(saved + "\n[guard]\nsecret_read = false\n", encoding="utf-8")
    out = bash(interpreter_reads[0])
    toml.write_text(saved, encoding="utf-8")
    check("guard secret_read = false also turns off the interpreter check", out.strip() == "", out)
    check("guard is silent in a project without .nonslop.toml", guard(unwired, "Bash", {"command": "git push --force"}) == "")


def test_worktree(repo: Path) -> Path:
    tree = repo / ".claude" / "worktrees" / "widget"
    git(repo, "worktree", "add", "-q", "-b", "claude/widget", str(tree), "origin/main")
    out = guard(tree, "Edit", {"file_path": str(repo / "src" / "a.py"), "old_string": "1", "new_string": "2"}, "a1")
    check("guard denies an edit that leaves the worktree for the main checkout", '"deny"' in out and "worktree" in out, out)
    out = guard(tree, "Edit", {"file_path": str(tree / "src" / "a.py"), "old_string": "1", "new_string": "2"}, "a1")
    check("guard allows an edit inside the worktree", out == "", out)
    out = guard(tree, "Bash", {"command": f"echo x > {repo / 'src' / 'a.py'}"}, "a1")
    check("guard denies a shell write into the main checkout", '"deny"' in out, out)
    (tree / "scratch.txt").write_text("unsaved\n", encoding="utf-8")
    out = guard(repo, "Bash", {"command": f"git worktree remove --force {tree}"})
    check("guard denies removing a worktree with unsaved work", '"deny"' in out and "uncommitted" in out, out)
    (tree / "scratch.txt").unlink()
    return tree


def test_slices(repo: Path, tree: Path) -> None:
    fields, problems = slices.parse_brief(BRIEF, "claude/")
    check("brief parses", not problems and fields["branch"] == "claude/widget" and len(fields["done"]) == 2
          and fields["scope_in"] == ["src/widget.py", "tests/"], (fields, problems))
    _, problems = slices.parse_brief(BRIEF.replace("claude/widget", "feature/widget").replace("1. `src", "`src"), "claude/")
    check("brief lint catches a wrong prefix", any("prefix" in p or "start with" in p for p in problems), problems)
    _, problems = slices.parse_brief("# x\n\n## Task\nt\n\n## Branch\nclaude/x\n\n## Scope\nIn: a\n\n## Done means\n1. works\n", "claude/")
    check("brief lint catches an uncheckable done item", any("checkable" in p for p in problems), problems)
    check("scope: `*` stays inside one directory", not slices.in_scope("src/private/deep.py", ["src/*.py"]))
    for path, glob in [("src/a.py", "src/*.py"), ("src/x/b.py", "src/**/*.py"), ("src/a.py", "src/**/*.py"),
                       ("src/x/y.txt", "src/"), ("src/x/y.txt", "src"), ("src/a.py", "src/a.py")]:
        check(f"scope: `{glob}` covers {path}", slices.in_scope(path, [glob]))
    check("scope: `?` stays inside one directory", not slices.in_scope("src/a/b", ["src/a?b"]))
    check("scope: file, directory and outsider",
          slices.outside_scope(fields, ["src/widget.py", "tests/test_widget.py", "src/a.py"]) == ["src/a.py"])

    brief = repo / ".claude" / "tmp" / "brief.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text(BRIEF, encoding="utf-8")
    result = nonslop(repo, "slice", "new", str(brief))
    check("slice new writes a record", result.returncode == 0 and slices.load({}, repo, "claude/widget").get("done"), result.stdout + result.stderr)
    other = brief.with_name("other.md")
    other.write_text(BRIEF.replace("claude/widget", "claude/other").replace("In:  src/widget.py, tests/", "In: tests/"), encoding="utf-8")
    result = nonslop(repo, "slice", "new", str(other))
    check("slice new refuses a scope that overlaps a slice in flight", result.returncode == 1 and "overlap" in result.stdout, result.stdout)

    # the builder works in its worktree: one file in scope, one outside
    (tree / "src" / "widget.py").write_text("def widget():\n    return 3\n", encoding="utf-8")
    (tree / "src" / "a.py").write_text("A = 2\n", encoding="utf-8")
    git(tree, "add", "src/widget.py", "src/a.py")
    git(tree, "commit", "-qm", "widget")
    git(tree, "push", "-q", "-u", "origin", "claude/widget")
    payload = {"cwd": str(tree), "session_id": "s", "agent_id": "a1", "last_assistant_message": "DONE 1 abc"}
    code, _, err = hook("done_check.py", payload)
    check("done-check blocks a change outside the slice's scope", code == 2 and "scope" in err and "src/a.py" in err, err)
    code, out, _ = hook("done_check.py", payload)
    record = slices.load({}, repo, "claude/widget")
    check("done-check lets go after the retry limit, and records the release",
          code == 0 and record.get("status") == "released" and record["done_check"]["ok"] is False, (code, record))
    result = nonslop(repo, "status", "--no-remote")
    check("status names the released slice", "released" in result.stdout and "claude/widget" in result.stdout, result.stdout)
    code, out, _ = hook("session_start.py", {"cwd": str(repo), "session_id": "c"})
    check("session start lists the released slice", "claude/widget: released" in out, out[-400:])

    result = nonslop(repo, "slice", "verify", "claude/widget")
    check("verify fails on the out-of-scope change, independent of the builder", result.returncode == 1 and "scope" in result.stdout, result.stdout)
    git(tree, "checkout", "-q", "origin/main", "--", "src/a.py")
    git(tree, "commit", "-qm", "back in scope")
    git(tree, "push", "-q")
    code, _, err = hook("done_check.py", payload)
    check("done-check passes a slice that is in scope, pushed and green", code == 0, err)
    result = nonslop(repo, "slice", "verify", "claude/widget")
    head = git(tree, "rev-parse", "HEAD")
    record = slices.load({}, repo, "claude/widget")
    check("verify passes at the pushed head and clears the release",
          result.returncode == 0 and record["verify"] == {**record["verify"], "sha": head, "ok": True}
          and record["status"] == "open", result.stdout + result.stderr)
    check("verify leaves no worktree behind", "verify" not in git(repo, "worktree", "list"))
    check("not ready without a review", any("review" in p for p in slices.merge_blockers(record, head, ["verify", "review"])))
    result = nonslop(repo, "slice", "review", "claude/widget", "clean", "--sha", "0000000")
    check("a verdict for another commit is refused as stale", result.returncode == 1 and "stale" in result.stdout, result.stdout)
    nonslop(repo, "slice", "review", "claude/widget", "clean", "--sha", head[:10])
    record = slices.load({}, repo, "claude/widget")
    check("verified and reviewed at the head: ready", slices.merge_blockers(record, head, ["verify", "review"]) == [])

    (tree / "src" / "widget.py").write_text("def widget():\n    return 4\n", encoding="utf-8")
    git(tree, "commit", "-qam", "late change")
    git(tree, "push", "-q")
    new_head = git(tree, "rev-parse", "HEAD")
    blockers = slices.merge_blockers(slices.load({}, repo, "claude/widget"), new_head, ["verify", "review"])
    check("a later push makes both the verify and the review stale", len(blockers) == 2 and all("now" in b for b in blockers), blockers)
    for _ in range(3):
        (tree / "src" / "widget.py").write_text(f"def widget():\n    return {_ + 5}\n", encoding="utf-8")
        git(tree, "commit", "-qam", "fix round")
        git(tree, "push", "-q")
        result = nonslop(repo, "slice", "review", "claude/widget", "must-fix")
    check("the third must-fix round escalates instead of looping", "ESCALATE" in result.stdout, result.stdout)

    git(tree, "checkout", "-q", "-b", "wip-elsewhere")
    (tree / "src" / "widget.py").write_text("def widget():\n    return 9\n", encoding="utf-8")
    git(tree, "commit", "-qam", "drift")
    code, _, err = hook("done_check.py", {**payload, "session_id": "s2"})
    check("done-check fails a subagent that left its slice branch", code == 2 and "slice branch" in err, err)
    git(tree, "checkout", "-q", "claude/widget")
    code, _, _ = hook("done_check.py", {"cwd": str(tree), "session_id": "s3", "agent_id": "a1",
                                        "last_assistant_message": "BLOCKED\nopen: which format?"})
    check("a BLOCKED report passes and is recorded", code == 0 and slices.load({}, repo, "claude/widget")["status"] == "blocked")


def test_gates(work: Path) -> None:
    repo = work / "gates"
    repo.mkdir()
    git(repo, "init", "-q")
    log_dir = work / "logs"
    log_dir.mkdir()
    noisy = "import sys; print('FAILED tests/x.py::test_a - boom'); [print('line', i) for i in range(60)]; sys.exit(1)"
    failure = gates.run_gate("t", f'python3 -c "{noisy}"', repo, log_dir, 60)
    check("a failure above the tail is still reported", failure is not None and "FAILED tests/x.py::test_a" in failure, failure)
    failure = gates.run_gate("t", "python3 -c \"print('0 passed')\"", repo, log_dir, 60, r"[1-9]\d* passed")
    check("a gate that exits 0 having run nothing fails its expect pattern", failure is not None and "run nothing" in failure.replace("\n", " "), failure)
    check("a real pass passes", gates.run_gate("t", "python3 -c \"print('4 passed')\"", repo, log_dir, 60, r"[1-9]\d* passed") is None)


def test_stats(repo: Path) -> None:
    result = nonslop(repo, "stats", "--json")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = {}
    check("stats reports the slice and the finish-check log",
          data.get("slices", {}).get("claude/widget", {}).get("must_fix_rounds") == 3
          and "released" in data.get("hook_logs", {}).get("done-check", {}), result.stdout[:600] + result.stderr)


def test_merge_policy(work: Path) -> None:
    def rules(value: str | None) -> str:
        project = work / f"policy-{value}"
        project.mkdir()
        body = "" if value is None else f'[merge]\ncoordinator = "{value}"\n'
        (project / ".nonslop.toml").write_text(body, encoding="utf-8")
        return nonslop(project, "rules").stdout

    auto, absent, ask, bad = rules("auto"), rules(None), rules("ask"), rules("yes")
    check("auto: session start says the coordinator may merge", "coordinator may merge" in auto and "WARNING" not in auto, auto[-400:])
    check("absent or ask: merges wait for the owner",
          all('wait for the owner\'s "merge <n>"' in text and "WARNING" not in text for text in (absent, ask)))
    check("unknown value: one warning, treated as ask",
          bad.count("WARNING") == 1 and "'yes'" in bad and "wait for the owner" in bad and "coordinator may merge" not in bad, bad[-400:])


def test_style() -> None:
    _, out, _ = hook("session_start.py", {}, "--print")
    check("session start carries the Style block", "least that works" in out and "full sentences for warnings" in out, out[-400:])


def main() -> int:
    scratch_root = ROOT / ".claude" / "tmp"
    scratch_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=scratch_root, prefix="test-hooks-"))
    try:
        repo = make_repo(work)
        test_guard(repo)
        tree = test_worktree(repo)
        test_slices(repo, tree)
        test_gates(work)
        test_stats(repo)
        test_merge_policy(work)
        test_style()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
