---
name: wire
description: Wire the current repository to nonslop - run init, fill .nonslop.toml from the project's real commands, run doctor, dry-run the slop checks on recent merged PRs, and open a draft PR with the wiring. Use when the owner says /nonslop:wire, "wire this repo to nonslop", "set up nonslop", or "install nonslop here".
---

# Wire

Wire this repo to nonslop. You propose; the owner merges. Never commit to the default branch. Never merge. Never install anything without asking. Never add permission allow rules beyond what `init` merges.

NONSLOP means `bin/nonslop` in this plugin. This skill's base directory (given when it loaded) is `<plugin>/skills/wire`, so use `<base>/../../bin/nonslop`. Do not hard-code a user path.

## 1. Orient

- Confirm `git rev-parse --show-toplevel` works. Else stop.
- Default branch: `git symbolic-ref refs/remotes/origin/HEAD` (or `git remote show origin`). Then `git fetch origin`.
- If `.nonslop.toml` exists, stop and offer `NONSLOP doctor`.
- Find the real commands (test, lint, build, clean) in: `.github/workflows/*`, manifests (pyproject, Cargo.toml, package.json, go.mod, Makefile, justfile), CLAUDE.md, AGENTS.md, CONTRIBUTING. Prefer what CI runs. Remember where each came from.
- `gh pr list --state merged --limit 10` shows the branch naming of agent PRs; use it for `[done].branch_prefix` (default `claude/`).

## 2. Init

Branch first: `git checkout -b <prefix>wire-nonslop origin/<default>`. Then run `NONSLOP init`.

## 3. Fill `.nonslop.toml`

Take keys only from `templates/nonslop.toml` and `examples/kabl.nonslop.toml` in the plugin dir. Do not invent keys.

- `[commands]`: from step 1. No shell syntax (pipes, `&&`, `VAR=x`); wrap complex ones in a script.
- `[done]`: `branch_prefix`; `run` = command keys that CI does not already run on every PR.
- `[state].file`: the project's handover file, or leave the default.
- `[rules].notes`: short project facts every agent needs.

If a hook blocks writing `.nonslop.toml` or `.claude/settings.json`, stop and ask the owner. Do not work around it.

## 4. Doctor

Run `NONSLOP doctor`. Report missing optional tools. Install nothing.

## 5. Dry run

For each of the last ~5 merged PRs (`gh pr list --state merged --limit 5 --json number,mergeCommit`): make a detached worktree under `.claude/tmp/` at the merge commit, run `NONSLOP slop check --base <merge>^1 --json` in it, then remove the worktree. Read-only. Summarise findings per rule. For rules that look noisy, ask the owner numbered questions proposing `[slop] warn` or `disable` entries. Apply none without his answer.

## 6. Commit

Add only `.nonslop.toml`, `.claude/settings.json`, `.gitignore`, by name. Commit, push, `gh pr create --draft`. Delete your scratch under `.claude/tmp/`.

## 7. Report

- Commands found and where each came from
- Dry-run noise per rule
- Open questions, numbered
- PR link
- "Restart Claude Code in this repo after merge."
