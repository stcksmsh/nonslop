---
name: wire
description: Wire the current repository to nonslop - draft .nonslop.toml from the project's real commands, dry-run the slop checks on recent merged PRs, run init, and open a draft PR with the wiring. Use when the owner says /nonslop:wire, "wire this repo to nonslop", "set up nonslop", or "install nonslop here".
---

# Wire

Wire this repo to nonslop. You propose; the owner merges. Never commit to the default branch. Never merge. Never install anything without asking. Never add permission allow rules beyond what `init` merges. One plain command per shell call (no `&&`, `;`, pipes, `$(...)`). No `rm -rf`.

Once `init` has run, the repo is opted in and hooks deny edits to `.nonslop.toml` and `.claude/settings.json`. After init, never touch either file. Any later change goes to the owner as a proposed diff. If a hook still blocks you or reports `gate-tampered` on them, stop and report; never revert or work around it.

NONSLOP: this skill's base directory (given when it loaded) is `<plugin>/skills/wire`. Run `realpath <base>/../../bin/nonslop` once and use that absolute path. Run every NONSLOP call from the target repo root (or the dry-run worktree). Do not hard-code a user path.

## 1. Orient

- `git rev-parse --show-toplevel` must work, else stop. This is `<repo>`.
- `git symbolic-ref refs/remotes/origin/HEAD` gives the default branch. `git fetch origin`.
- If `.nonslop.toml` exists, stop and offer `NONSLOP doctor`.
- Find the real commands (test, lint, build, clean) in `.github/workflows/*`, manifests (pyproject, Cargo.toml, package.json, go.mod, Makefile, justfile), CLAUDE.md, AGENTS.md, CONTRIBUTING. Prefer what CI runs. Note where each came from.
- `gh pr list --state merged --limit 10` shows the branch naming of agent PRs, for `[done].branch_prefix` (default `claude/`).

## 2. Draft

Write `<repo>/.claude/tmp/wire/draft.toml` (not named `.nonslop.toml`) from `templates/nonslop.toml` plus findings. Take keys only from that template and `examples/kabl.nonslop.toml` in the plugin dir. Do not invent keys.

- `[commands]`: from step 1. No shell syntax; wrap complex ones in a script.
- `[done]`: `branch_prefix` must be non-empty and must not be a prefix of `nonslop-wire`. `run` = command keys CI does not already run on every PR.
- `[state].file`: the project's handover file, or leave the default.
- `[rules].notes`: short project facts every agent needs.

## 3. Dry run (before init)

`gh pr list --state merged --limit 5 --json number,mergeCommit`. For each PR, `<oid>` is `.mergeCommit.oid`; skip a null one. Base is `<oid>^1` (wrong for rebase-merged PRs: accept and note it). Per PR, separate commands:

1. `git worktree add --detach <repo>/.claude/tmp/wire/<pr> <oid>`
2. `cp <repo>/.claude/tmp/wire/draft.toml <repo>/.claude/tmp/wire/<pr>/.nonslop.toml` (allowed: the repo is not opted in yet)
3. From inside that worktree: `NONSLOP slop check --base <oid>^1 --json`
4. `git worktree remove --force <repo>/.claude/tmp/wire/<pr>`

The copied draft always shows `gate-tampered` on `.nonslop.toml` in the dry run; ignore that one finding, it is an artifact. Then `git worktree prune`. Summarise findings per rule. For noisy rules, ask the owner numbered questions proposing `[slop] warn` or `disable` entries. Apply answers to the draft only. Never weaken a gate without his answer.

## 4. Init and PR

1. `git switch -c nonslop-wire origin/<default>`. Fixed name, not the slice prefix: Stop checks only judge `branch_prefix` branches and would flag the new protected files as `gate-tampered`.
2. `NONSLOP init --from <repo>/.claude/tmp/wire/draft.toml`
3. `NONSLOP doctor`. Report missing optional tools; install nothing.
4. `git status --short`. Add by name only the changed files among `.nonslop.toml`, `.claude/settings.json`, `.gitignore`. If `.claude/settings.json` is git-ignored here, stop and ask.
5. Write the commit message to `.claude/tmp/wire/commit.txt` and the PR body to `.claude/tmp/wire/pr.md`. Then `git commit -F <repo>/.claude/tmp/wire/commit.txt`, `git push -u origin nonslop-wire`, `gh pr create --draft --body-file <repo>/.claude/tmp/wire/pr.md`.
6. Cleanup: `git worktree remove --force <path>` for any leftover, `git worktree prune`, then `rmdir` the empty dirs under `.claude/tmp/wire/` after removing `draft.toml` with `rm`.

## 5. Report

- Commands found and where each came from
- Dry-run noise per rule
- Open questions, numbered
- PR link
- "Restart Claude Code in this repo after merge."
