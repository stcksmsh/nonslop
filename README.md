# nonslop

A hands-free AI coding workflow that does not ship slop.

nonslop is a [Claude Code plugin](https://code.claude.com/docs/en/plugins/overview). It packages one way of working so every project gets the same agents, rules and gates, and each project only declares what is different about it.

- **Coordinator / builder / reviewer.** One coordinator session plans and dispatches. Each slice goes to a fresh `builder` subagent in its own worktree and comes back as a draft pull request. A fresh-context `reviewer` reads the diff before the owner is asked to merge.
- **Static gates, no tokens.** Hooks check the work deterministically: a done-check that refuses to let a slice end unpushed or without a pull request, and (once vendored) slopstop for the code itself.
- **Per-project wiring.** A tracked `.nonslop.toml` names the project's test, lint and clean commands, its state file and its machine constraints. No file, no behaviour: the plugin is inert in projects that are not wired.

Status: v0 scaffold. Nothing here has been run inside Claude Code yet. See [Unverified](#unverified).

## Install

Requires Python 3.11+ and Claude Code with plugin support.

```sh
claude plugin marketplace add stcksmsh/nonslop
claude plugin install nonslop@nonslop
```

Repeat for each Claude Code config directory you use. To try a local checkout without installing:

```sh
claude --plugin-dir /path/to/nonslop
claude plugin validate /path/to/nonslop
```

## Wire a project

From the project root, in a Claude Code session with the plugin enabled:

```sh
nonslop init      # creates .nonslop.toml and .claude/settings.json, ignores .claude/tmp/
nonslop doctor    # shows what is wired
```

Then fill in `[commands]` in `.nonslop.toml`, review the permission lists in `.claude/settings.json`, and commit both to the default branch so every worktree sees them.

Start work with `/nonslop:coordinator`.

## What runs when

| Hook | Script | Effect |
|---|---|---|
| `SessionStart` (startup, clear, compact) | `scripts/session_start.py` | Prints shared rules, the project's commands and constraints, and the state file into the new context |
| `PermissionDenied` | `scripts/log_event.py` | Appends the refused call to `<scratch>/nonslop/permission-denied.jsonl` so the allow list can be tuned from data |
| `Stop`, `SubagentStop` | `scripts/done_check.py` | On `claude/*` branches, blocks finishing until the tree is clean, the branch is pushed, a pull request exists and build output is removed. Gives up after `stop_retries` identical failures |

## Layout

```
.claude-plugin/   plugin.json, marketplace.json (this repo is its own marketplace)
agents/           builder.md, reviewer.md
skills/           coordinator/
hooks/            hooks.json
scripts/          hook implementations (stdlib Python)
rules/            core.md, the shared rules printed at session start
bin/              nonslop CLI (on the Bash tool's PATH while enabled)
templates/        files `nonslop init` copies into a project
tools/slopstop/   static slop checks (not vendored yet)
```

## Unverified

Written against the Claude Code documentation as of 2026-11-21. `claude plugin validate .` passes (one warning: no icon) and the hook scripts were exercised by hand in a throwaway repository, but nothing has run inside a live session yet. `version` is deliberately unset in `plugin.json` so installs follow the repository. Check these first:

- `isolation: worktree` on the builder: where the worktree is created and that it branches from the remote default branch, not a stale local one.
- `SubagentStop` passes a `cwd` inside the subagent's worktree. The done-check depends on it.
- The permission rule patterns in `templates/settings.json` match the commands agents actually run, and an explicit allow rule is enough for `git push` under auto mode.
- `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` stops builders from spawning their own subagents without blocking the coordinator.

## Not here yet

- slopstop itself (see `tools/slopstop/README.md`).
- The `caveman` and `ponytail` skills.
- A license.
