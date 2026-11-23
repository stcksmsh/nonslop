#!/usr/bin/env python3
"""PreToolUse hook: the rules of rules/core.md that can be decided from the call itself.

Denies, in a project wired with .nonslop.toml:
  - a subagent merging a pull request; the coordinator merging a slice that is not proven ready
    at its current head (verified, reviewed, CI green) -- [merge] in .nonslop.toml;
  - git that destroys or rewrites: force push, push to the default branch, amending or rebasing
    pushed commits, `add -f`; and inside a subagent or a linked worktree also `reset --hard`,
    `clean`, `stash`, whole-tree `checkout`/`restore`; removing a worktree that holds unsaved work;
  - an edit that leaves the worktree for the main checkout, or touches nonslop's own state
    (`<scratch>/nonslop/`) or the installed plugin;
  - reading secret files (`.env`, `.secrets`, private keys) into the conversation -- [guard].

Every denial names what it matched and what to do instead. An internal error denies too (a guard
that could not look must not answer "allowed") unless SLOP_FAIL_OPEN=1; either way it is logged.
"""

import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PLUGIN_ROOT / "tools" / "slopstop"))

import slices  # noqa: E402
from log_event import append  # noqa: E402
from nonslop_config import (default_branch, git_out, load_config, main_root, read_hook_input,  # noqa: E402
                            start_dir, worktree_root)

# slopstop lives outside this directory and stays self-contained; load its two modules by name.
SH = importlib.import_module("shellcmd")
slop = importlib.import_module("slop")
INTERNAL_ERRORS = slop.INTERNAL_ERRORS

MERGE_API = re.compile(r"/pulls/(\d+)/merge\b")
SECRET_NAME = re.compile(r"^(\.env(\..+)?|\.secrets|\.netrc|id_(rsa|dsa|ecdsa|ed25519)|.+\.pem|.+\.key)$", re.I)
SECRET_EXEMPT = re.compile(r"\.(example|sample|template|dist|defaults|pub)$", re.I)
READERS = {"cat", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "rg", "ag", "awk", "sed", "cut", "sort",
           "uniq", "strings", "xxd", "od", "hexdump", "base64", "nl", "tac", "bat", "jq", "yq", "source", ".",
           "diff", "cmp", "tee", "envsubst", "dotenv"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def is_secret(path: str) -> bool:
    name = path.rstrip("/").rsplit("/", 1)[-1]
    return bool(SECRET_NAME.match(name)) and not SECRET_EXEMPT.search(name)


def inside(path: Path, parent: Path | None) -> bool:
    return parent is not None and (path == parent or parent in path.parents)


class Guard:
    def __init__(self, hook_input: dict, config: dict, root: Path):
        self.input = hook_input
        self.config = config
        self.root = root                       # where .nonslop.toml is: this worktree's root
        self.cwd = start_dir(hook_input)
        self.subagent = bool(hook_input.get("agent_id"))
        self.top = worktree_root(self.cwd) or root
        self.main = main_root(self.cwd)
        self.linked = self.main is not None and self.top.resolve() != self.main.resolve()
        self.scratch = config.get("env", {}).get("scratch", ".claude/tmp").strip("/")

    # ------------------------------------------------------------ paths

    def path_reason(self, raw: str) -> str | None:
        """Why an edit or shell write to `raw` is refused."""
        path = Path(raw) if os.path.isabs(raw) else self.cwd / raw
        path = Path(os.path.normpath(path))
        roots = [r for r in (self.top, self.main) if r is not None and inside(path, r)]
        if any((path.relative_to(r).as_posix() + "/").startswith(f"{self.scratch}/nonslop/") for r in roots):
            return (f"`{raw}` is nonslop's own state (logs, slice records, retry counters). "
                    "It is written by the hooks and by `nonslop slice ...`, never by hand.")
        installed = PLUGIN_ROOT.resolve()
        develops_plugin = inside(installed, self.top) or inside(installed, self.main) or inside(self.top, installed)
        if inside(path, installed) and not develops_plugin:
            return f"`{raw}` is inside the installed nonslop plugin; the gates are not yours to edit."
        main = self.main
        if main is not None and self.linked and inside(path, main) and not inside(path, self.top):
            within = path.relative_to(main).as_posix() + "/"
            if within.startswith((".claude/worktrees/", f"{self.scratch}/")):
                return None  # another worktree is not the main checkout; scratch is shared on purpose
            return (f"`{raw}` is in the main checkout, but you work in the worktree `{self.top}`. "
                    "Use paths inside your worktree (relative paths are safest).")
        return None

    # ------------------------------------------------------------ git

    def git(self, args: list[str], directory: str | None = None) -> tuple[int, str]:
        return git_out(args, self.cwd / directory if directory else self.cwd)

    def git_reason(self, call) -> str | None:
        sub, args = call.sub, call.args
        shorts, longs, positional = SH.options(args, slop.HOOKED.get(sub, ""), slop.COMMIT_LONG_VALUE)
        isolated = self.subagent or self.linked
        if sub == "push":
            if "f" in shorts or any(name.startswith("--force") for name in longs) or any(p.startswith("+") for p in positional):
                return "force push rewrites a pushed branch. Add a new commit instead; never force-push."
            default = default_branch(self.cwd)
            for refspec in positional[1:]:
                if refspec.rpartition(":")[2].removeprefix("refs/heads/") == default:
                    return (f"`{refspec}` writes to the default branch `{default}`. "
                            "Push your slice branch and open a pull request.")
            if len(positional) <= 1 and "--tags" not in longs and self.git(["rev-parse", "--abbrev-ref", "HEAD"], call.directory)[1] == default:
                return f"you are on the default branch `{default}`; nothing is pushed to it directly. Branch first."
        if sub == "add" and ("f" in shorts or "--force" in longs):
            return "`git add -f` commits files the project ignores on purpose. Add the files you changed by name."
        if sub == "commit" and "--amend" in longs and self.pushed(call.directory):
            return "`--amend` rewrites a commit that is already pushed. Make a new commit."
        if sub == "rebase" or (sub == "pull" and ("r" in shorts or "--rebase" in longs)):
            if not any(name in ("--abort", "--continue", "--skip", "--quit") for name in longs) and self.pushed(call.directory):
                return "rebasing rewrites pushed commits. Update with `git merge origin/<default>` instead."
        if sub == "worktree" and positional[:1] == ["remove"]:
            return self.worktree_removal_reason(positional[1:])
        if not isolated:
            return None
        if sub == "reset" and "--hard" in longs:
            return "`git reset --hard` discards work. Revert the specific change, or report BLOCKED."
        if sub == "clean" and ("f" in shorts or "--force" in longs) and "n" not in shorts:
            return "`git clean` deletes untracked files, yours or another agent's. Delete the files you made by name."
        if sub == "stash" and positional[:1] not in (["list"], ["show"]):
            return "the stash is shared between worktrees: another agent can pop yours. Commit to your branch instead."
        if sub in ("checkout", "restore") and any(p in (".", ":/", "*") for p in positional):
            return f"`git {sub} .` discards every change in the tree. Restore the specific files by name."
        return None

    def pushed(self, directory: str | None) -> bool:
        """True when HEAD is already on a remote branch."""
        code, out = self.git(["branch", "-r", "--contains", "HEAD"], directory)
        return code == 0 and bool(out.strip())

    def worktree_removal_reason(self, paths: list[str]) -> str | None:
        for raw in paths:
            path = Path(raw) if os.path.isabs(raw) else self.cwd / raw
            if not path.is_dir():
                continue
            code, dirty = git_out(["status", "--porcelain"], path)
            if code == 0 and dirty:
                return (f"worktree `{raw}` has uncommitted changes; removing it deletes them. "
                        "Commit and push them from that worktree, or ask the owner.")
            code, ahead = git_out(["log", "--oneline", "HEAD", "--not", "--remotes", "-n", "1"], path)
            if code == 0 and ahead:
                return (f"worktree `{raw}` has commits that are on no remote; removing it can strand them. "
                        "Push its branch first.")
        return None

    # ------------------------------------------------------------ merge

    def merge_reason(self, command) -> str | None:
        argv = command.argv
        pr = None
        if command.prog == "gh" and argv[1:3] == ["pr", "merge"]:
            pr = next((a for a in argv[3:] if not a.startswith("-")), "")
        elif command.prog == "gh" and argv[1:2] == ["api"]:
            hit = next((MERGE_API.search(a) for a in argv[2:] if MERGE_API.search(a)), None)
            pr = hit[1] if hit else None
        if pr is None:
            return None
        if self.subagent:
            return "subagents never merge. Report DONE; the owner or the coordinator merges."
        merge = self.config.get("merge", {})
        if merge.get("guard", True) is False:
            return None
        return self.unready_reason(pr, merge)

    def unready_reason(self, pr: str, merge: dict) -> str | None:
        fields = "number,headRefName,headRefOid,state,isDraft"
        code, out = self.run(["gh", "pr", "view", *([pr] if pr else []), "--json", fields])
        try:
            info = json.loads(out) if code == 0 else None
        except json.JSONDecodeError:
            info = None
        if not info:
            return ("could not look this pull request up with `gh pr view`, so its readiness is unknown. "
                    "Check `gh auth status`; if the owner said to merge anyway, they merge it.")
        branch, head = info["headRefName"], info["headRefOid"]
        prefix = self.config.get("done", {}).get("branch_prefix", "claude/")
        if not branch.startswith(prefix):
            return None  # not a slice: the owner's own pull request
        if info.get("state") != "OPEN":
            return f"pull request #{info['number']} is {info.get('state')}, not open."
        need = merge.get("require", ["verify", "review", "ci"])
        problems = slices.merge_blockers(slices.load(self.config, self.cwd, branch) or {"branch": branch}, head, need)
        if "ci" in need and (problem := self.ci_problem(str(info["number"]), merge)):
            problems.append(problem)
        if not problems:
            return None
        return (f"pull request #{info['number']} ({branch} at {head[:9]}) is not proven ready to merge:\n- "
                + "\n- ".join(problems)
                + "\nFix these and merge then. If the owner wants it merged as it is, the owner merges it.")

    def ci_problem(self, number: str, merge: dict) -> str | None:
        code, out = self.run(["gh", "pr", "checks", number, "--required"], combine=True)
        if code != 0 and "no required checks" in out.lower():
            code, out = self.run(["gh", "pr", "checks", number], combine=True)
        if code == 0:
            return None
        if code == 8:
            return "CI is still running: wait for every check"
        if "no checks reported" in out.lower():
            if merge.get("allow_no_ci", False):
                return None
            return "no CI checks ran on this head; absent CI is not passing CI (owner: set [merge].allow_no_ci to accept)"
        return "CI is failing: " + " | ".join(line.split("\t")[0] for line in out.splitlines() if "\tfail" in line)[:200]

    def run(self, args: list[str], combine: bool = False) -> tuple[int, str]:
        try:
            result = subprocess.run(args, cwd=self.cwd, capture_output=True, text=True, timeout=40, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            return 1, str(error)
        return result.returncode, result.stdout + (result.stderr if combine else "")

    # ------------------------------------------------------------ dispatch

    def verdict(self) -> tuple[str, str] | None:
        """(rule, reason) when the call is refused."""
        tool = self.input.get("tool_name", "")
        tool_input = self.input.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            raise TypeError("tool_input is not an object")
        secrets = self.config.get("guard", {}).get("secret_read", True)
        if tool in EDIT_TOOLS:
            path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            if not isinstance(path, str):
                raise TypeError("file_path is not a string")
            if path and (reason := self.path_reason(path)):
                return "path-guard", reason
            return None
        if tool in ("Read", "Grep"):
            names = [tool_input.get(key) for key in ("file_path", "path", "glob")]
            hit = next((n for n in names if isinstance(n, str) and is_secret(n)), None)
            if secrets and hit:
                return "secret-read", self.secret_message(hit)
            return None
        if tool != "Bash":
            return None
        command = tool_input.get("command", "")
        if not isinstance(command, str):
            raise TypeError("command is not a string")
        for simple in SH.parse(command):
            if reason := self.merge_reason(simple):
                return "merge-guard", reason
            call = SH.git_call(simple)
            if call and (reason := self.git_reason(call)):
                return "destructive-git", reason
            for target in slop.write_targets(simple, SH):
                if reason := self.path_reason(target):
                    return "path-guard", reason
            if secrets and simple.prog in READERS:
                operands = [a for a in simple.argv[1:] if not a.startswith("-")] + simple.reads
                if hit := next((a for a in operands if is_secret(a)), None):
                    return "secret-read", self.secret_message(hit)
        return None

    @staticmethod
    def secret_message(name: str) -> str:
        return (f"`{name}` holds secrets; its contents must not enter the conversation. "
                "Read the `.example` file for the variable names, or ask the owner for what you need.")


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": f"nonslop: {reason}",
    }}))


def main() -> int:
    hook_input = read_hook_input()
    loaded = None
    try:
        loaded = load_config(start_dir(hook_input))
        if loaded is None:
            return 0
        guard = Guard(hook_input, *loaded)
        hit = guard.verdict()
    except INTERNAL_ERRORS as error:  # decide here what a crash in the guard means
        print(f"nonslop guard internal error: {type(error).__name__}: {error}", file=sys.stderr)
        if loaded is None:
            return 0
        append(*loaded, "guard", {"session": hook_input.get("session_id", ""), "decision": "crash",
                                  "error": f"{type(error).__name__}: {error}"[:300]})
        if os.environ.get("SLOP_FAIL_OPEN") != "1":
            deny(f"internal error, so this call was not checked ({type(error).__name__}: {error}). "
                 "Do not retry it in another form; report it to the owner.")
        return 0
    if hit is None:
        return 0
    rule, reason = hit
    # Log the rule and the tool only: a command line can carry tokens or message bodies.
    append(*loaded, "merge-guard" if rule == "merge-guard" else "guard", {
        "session": hook_input.get("session_id", ""), "agent": hook_input.get("agent_id", ""),
        "decision": "deny", "rule": rule, "tool": hook_input.get("tool_name", "")})
    deny(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
