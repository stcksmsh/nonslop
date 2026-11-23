---
name: wire
description: Wire the current repository to nonslop - run init, fill .nonslop.toml from the project's real commands, run doctor, dry-run the slop checks on recent merged PRs, and open a draft PR with the wiring. Use when the owner says /nonslop:wire, "wire this repo to nonslop", "set up nonslop", or "install nonslop here".
---

# Wire

Wire this repo to nonslop. You propose; the owner merges. Never commit to the default branch. Never merge. Never install anything without asking. Never add permission allow rules beyond what `init` merges. One plain command per shell call (no `&&`, `;`, pipes, `$(...)`). No `rm -rf`.

If a hook blocks writing `.nonslop.toml` or `.claude/settings.json`, or reports `gate-tampered` on them, stop and report to the owner. Never revert or work around it.

NONSLOP: this skill's base directory (given when it loaded) is `<plugin>/skills/wire`. Run `realpath <base>/../../bin/nonslop` once and use that absolute path. Run every NONSLOP call from the target repo root (or the dry-run worktree). Do not hard-code a user path.

## 1. Orient

- `git rev-parse --show-toplevel` must work, else stop. This is `<repo>`.
- `git symbolic-ref refs/remotes/origin/HEAD` gives the default branch. `git fetch origin`.
- If `.nonslop.toml` exists, stop and offer `NONSLOP doctor`.
- Find the real commands (test, lint, build, clean) in `.github/workflows/*`, manifests (pyproject, Cargo.toml, package.json, go.mod, Makefile, justfile), CLAUDE.md, AGENTS.md, CONTRIBUTING. Prefer what CI runs. Note where each came from.
- `gh pr list --state merged --limit 10` shows the branch naming of agent PRs, for `[done].branch_prefix` (default `claude/`).

## 2. Init

`git checkout -b nonslop-wire origin/<default>`. The name is fixed and does not use the slice prefix: Stop checks only judge `branch_prefix` branches, and they would flag the new protected files as `gate-tampered`. Then `NONSLOP init`.

## 3. Fill `.nonslop.toml`

Take keys only from `templates/nonslop.toml` and `examples/kabl.nonslop.toml` in the plugin dir. Do not invent keys.

- `[commands]`: from step 1. No shell syntax; wrap complex ones in a script.
- `[done]`: `branch_prefix`; `run` = command keys CI does not already run on every PR.
- `[state].file`: the project's handover file, or leave the default.
- `[rules].notes`: short project facts every agent needs.

## 4. Doctor

`NONSLOP doctor`. Report missing optional tools. Install nothing.

## 5. Dry run

`gh pr list --state merged --limit 5 --json number,mergeCommit`. For each PR, `<oid>` is `.mergeCommit.oid`; skip a null one. Base is `<oid>^1` (wrong for rebase-merged PRs: accept and note it). Per PR, as separate commands:

1. `git worktree add --detach <repo>/.claude/tmp/wire/<pr> <oid>`
2. `cp <repo>/.nonslop.toml <repo>/.claude/tmp/wire/<pr>/.nonslop.toml` so the proposed config is measured.
3. From inside that worktree: `NONSLOP slop check --base <oid>^1 --json`
4. `git worktree remove --force <repo>/.claude/tmp/wire/<pr>`

Then `git worktree prune`. Summarise findings per rule. For noisy rules, ask the owner numbered questions proposing `[slop] warn` or `disable` entries. Apply none without his answer.

## 6. Commit

`git status --short`. Add by name only the files that changed among `.nonslop.toml`, `.claude/settings.json`, `.gitignore`. If `.claude/settings.json` is git-ignored here, stop and ask. Commit, push, `gh pr create --draft`. Remove leftover scratch with `git worktree remove --force <path>` then `git worktree prune`, and `rmdir` the empty `.claude/tmp/wire/`.

## 7. Report

- Commands found and where each came from
- Dry-run noise per rule
- Open questions, numbered
- PR link
- "Restart Claude Code in this repo after merge."
