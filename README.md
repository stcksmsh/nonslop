# nonslop

A workflow for AI coding agents that does not ship slop.

Agents write most of the code. nonslop is everything around them that keeps the result good without spending more tokens on it: static checks that run on every edit, gates that decide when a slice is really finished, and one way of coordinating the work that is the same in every project.

It has three layers:

1. **Static gates** (`tools/slopstop`, `scripts/gates.py`). No model. slopstop looks only at lines the agent added and blocks the patterns agents leave behind: new suppressions, weakened tests, stubs, silent fallbacks, narrating comments, renamed copy-paste, edits to lint or CI configuration. On top of that each project names its own lint and test commands as gates.
2. **Workflow** (`agents/`, `skills/`, `rules/`). A coordinator plans and dispatches. Each slice goes to a fresh `builder` subagent in its own worktree and comes back as a draft pull request. A fresh-context `reviewer` reads the diff. The owner gets a list of actions, and merges.
3. **Wiring** (`.nonslop.toml`). One tracked file per project says what is different there: its commands, which gates run, slop rule tuning, scratch directory, machine constraints. A project without the file is untouched.

The checks work from any shell through `bin/nonslop`. For Claude Code the repository is also a plugin, which is how the hooks, agents and skills get loaded.

Status: early. The slopstop kit was evaluated on a real project (see `eval/`). The plugin validates and the scripts are tested by hand, but the workflow has not yet been run end to end in a live session. See [Not verified yet](#not-verified-yet).

## Install

Requires Python 3.11+ and git. Optional tools are used when present: `ast-grep`, `ruff`, `jscpd`, `gitleaks`, `shellcheck`, and each language's own linter (`nonslop doctor` lists them).

As a Claude Code plugin, once per Claude Code config directory:

```sh
claude plugin marketplace add stcksmsh/nonslop
claude plugin install nonslop@nonslop
```

Or straight from a checkout, with nothing installed:

```sh
claude --plugin-dir /path/to/nonslop
```

## Wire a project

```sh
cd my-project
/path/to/nonslop/bin/nonslop init     # .nonslop.toml, .claude/settings.json (merged, nothing removed), .gitignore
$EDITOR .nonslop.toml                 # fill in [commands]; see examples/kabl.nonslop.toml
/path/to/nonslop/bin/nonslop doctor
```

Commit `.nonslop.toml` and `.claude/settings.json` to the default branch, so every worktree has them. Agents are blocked from editing either file afterwards.

Then, in Claude Code: `/nonslop:coordinator`.

## Commands

```sh
nonslop check            # what an agent would be told now: slop checks on the diff, then the project's gates
nonslop check --all      # whole repository, legacy code included (one-off audit, not a gate)
nonslop rules            # the rules and wiring agents receive
nonslop doctor           # what is wired, which tools are active
nonslop slop selftest    # slopstop's own test on seeded slop
```

## What runs when

| Hook | Runs | Effect |
|---|---|---|
| `SessionStart` (startup, clear, compact) | `scripts/session_start.py` | Rules, project commands and the state file go into the new context |
| `SubagentStart` (builder, reviewer) | `scripts/session_start.py --subagent` | The same rules go into the subagent's context |
| `PreToolUse` (edits, Bash) | `slop.py hook pre` | **Denies** the call when it edits a gate, adds a suppression, removes assertions or bypasses hooks |
| `PreToolUse` (Bash) | `scripts/merge_guard.py` | **Denies** `gh pr merge` inside a subagent. The coordinator may still merge on the owner's word |
| `PostToolUse` (edits) | `slop.py hook post` | Findings on the edited file are fed back at once |
| `Stop`, `SubagentStop` (builder) | `scripts/slop_stop.py`, `scripts/done_check.py` | On slice branches: full slop check, then clean tree, pushed, pull request, the project's gates, free disk. Exit 2 keeps the agent working. Then the clean command runs |
| `PermissionDenied` | `scripts/log_event.py` | The refused call is appended to `<scratch>/nonslop/permission-denied.jsonl`, to tune allow lists from data |

Both Stop checks give up after `stop_retries` identical failures, so an agent cannot loop forever. A builder that ends with a `BLOCKED` report is asking a question and is let through.

## Layout

```
bin/nonslop        CLI
scripts/           hook entry points and the gate runner (stdlib Python)
tools/slopstop/    static slop checks, self-contained (see NONSLOP-CHANGES.md)
rules/core.md      the shared rules every agent receives
agents/            builder, reviewer
skills/            coordinator, caveman, ponytail
hooks/hooks.json   Claude Code hook wiring
templates/         what `nonslop init` puts in a project
examples/          a real project's .nonslop.toml
eval/              how slopstop and a competitor were measured: reports, seeds, triage
.claude-plugin/    plugin manifest and marketplace entry
```

## Measuring

`eval/` holds the method and the numbers: hand-written slop seeds wired into real code for recall, and every finding over nine real agent-written pull requests triaged true / false / not-worth-acting-on for precision. Any change to a rule should be re-run against both before it is trusted. Blocking rules must stay high-precision; everything else is advisory.

## Not verified yet

- A live run: `/nonslop:coordinator` dispatching a builder and reviewing the result.
- `isolation: worktree` on the builder: where the worktree lands and that it starts from the remote default branch.
- That `SubagentStop` and `SubagentStart` match the plugin-scoped agent names used in `hooks/hooks.json`, and that `cwd` in their input is the subagent's worktree.
- slopstop with `ast-grep` installed (one selftest case fails without it; see `tools/slopstop/NONSLOP-CHANGES.md`).
- The permission lists in `templates/settings.json` under auto mode.

## Licensing

No license has been chosen yet. Until one is added, the code is published but not licensed for reuse.
The two vendored skills keep their own MIT licenses; see `THIRD_PARTY.md`.
