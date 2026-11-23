# nonslop

A workflow for AI coding agents that does not ship slop.

Agents write most of the code. nonslop is everything around them that keeps the result good without spending more tokens on it: static checks that run on every edit, gates that decide when a slice is really finished, and one way of coordinating the work that is the same in every project.

It has three layers:

1. **Static gates** (`tools/slopstop`, `scripts/guard.py`, `scripts/gates.py`). No model. slopstop looks only at lines the agent added and blocks the patterns agents leave behind: new suppressions, weakened or disabled tests, stubs, silent fallbacks, narrating comments, renamed copy-paste, edits to lint, test or CI configuration. The guard denies what the rules forbid outright: force pushes, pushes to the default branch, rewriting pushed commits, edits that leave the worktree, reading secret files. On top of that each project names its own lint and test commands as gates.
2. **Workflow** (`agents/`, `skills/`, `rules/`, `nonslop slice`). A coordinator plans and dispatches. Each slice has a record: its scope, its numbered "done means" items, and what has been proven about it at which commit. It goes to a fresh `builder` subagent in its own worktree and comes back as a draft pull request. The pushed commit is verified in a fresh worktree, independent of what the builder reported, and a fresh-context `reviewer` reads the diff. The owner gets a list of actions, and merges.
3. **Wiring** (`.nonslop.toml`). One tracked file per project says what is different there: its commands, which gates run, slop rule tuning, scratch directory, machine constraints. A project without the file is untouched.

The checks work from any shell through `bin/nonslop`. For Claude Code the repository is also a plugin, which is how the hooks, agents and skills get loaded.

Status: early. The slopstop kit was evaluated on a real project (see `eval/`). Every hook is tested with the payloads Claude Code sends, and the slice commands are tested end to end against a throwaway repository (`tests/`, the slopstop selftest). What still needs a live session is listed under [Not verified yet](#not-verified-yet).

## Install

Requires Python 3.11+ and git. Optional tools are used when present: `ast-grep`, `ruff`, `jscpd`, `gitleaks`, `shellcheck`, and each language's own linter (`nonslop doctor` lists them).

Install the plugin once for your user, per Claude Code config directory. It then acts in every project that has a `.nonslop.toml` and stays silent everywhere else:

```sh
claude plugin install nonslop --marketplace stcksmsh/nonslop --scope user
```

Or straight from a checkout, with nothing installed (for working on nonslop itself):

```sh
claude --plugin-dir /path/to/nonslop
```

## Update

```sh
claude plugin marketplace update nonslop
claude plugin update nonslop@nonslop
```

Restart Claude Code afterwards. Updates reach every wired project at once. `nonslop doctor` shows the installed version next to the version of the copy it runs from. Changes that need a project's own files to change are listed in `CHANGELOG.md` under "Upgrade".

## Wire a project

In the project, in Claude Code:

```
/nonslop:wire
```

Claude reads your CI, manifests and agent docs, drafts `.nonslop.toml` with the real commands, dry-runs the slop checks on your last merged PRs, asks you about noisy rules, then runs `nonslop init --from <draft>` and opens a draft PR with the wiring. (`init --from <file.toml>` writes that file instead of the template when `.nonslop.toml` is missing; an existing one is never overwritten.) Merge it, then restart Claude Code in that repo.

Manual fallback:

```sh
cd my-project
/path/to/nonslop/bin/nonslop init     # .nonslop.toml, .claude/settings.json (permissions merged; only retired allow rules removed), .gitignore
$EDITOR .nonslop.toml                 # fill in [commands]; see examples/kabl.nonslop.toml
/path/to/nonslop/bin/nonslop doctor   # wiring, tools, and whether the plugin is installed
```

Commit `.nonslop.toml` and `.claude/settings.json` to the default branch, so every worktree has them. Agents are blocked from editing either file afterwards. The project's settings carry only permissions; the plugin itself comes from your user install.

Then, in Claude Code: `/nonslop:coordinator`.

## Commands

```sh
nonslop check            # what an agent would be told now: slop checks on the diff, then the project's gates
nonslop check --all      # whole repository, legacy code included (one-off audit, not a gate)
nonslop rules            # the rules and wiring agents receive
nonslop doctor           # what is wired, which tools are active
nonslop slop selftest    # slopstop's own test on seeded slop

nonslop slice new <brief.md>                  # lint a builder prompt, refuse overlapping scope, write the slice record
nonslop slice verify <branch>                 # check the pushed head in a fresh worktree: slop, gates, scope, default merged in
nonslop slice review <branch> <verdict> --sha <sha>   # record a reviewer verdict against the commit it judged
nonslop slice close <branch> <merged|closed>
nonslop status           # every slice branch and worktree: PR, CI, record, stale or unsaved work, what to do
nonslop stats            # gate hits per rule, hook time, tokens per branch, review rounds (--json, --since <days>)
```

## A slice, start to merge

1. The coordinator writes the builder prompt to a file and runs `nonslop slice new`. A brief without numbered, checkable "Done means" items or `Scope In` paths is refused, and so is a scope that overlaps a slice in flight.
2. A builder implements it in its own worktree. When it tries to stop, hooks check: only files in scope changed, clean tree, pushed, open pull request, the project's gates.
3. `nonslop slice verify <branch>` repeats the checks on the pushed commit in a fresh worktree. What the builder said it ran is not consulted.
4. A reviewer judges the diff against the numbered items. `nonslop slice review` records its verdict with the commit.
5. A later push makes both stale. The coordinator's `gh pr merge` is denied until the slice is verified and reviewed at its current head and CI is green. The owner can always merge by hand.

If a builder cannot clear its finish checks it is let go after `[done].stop_retries` repeats, so it cannot loop forever. That is recorded as `released`, shown by `nonslop status` and at session start, and never passes the merge check.

## What runs when

| Hook | Runs | Effect |
|---|---|---|
| `SessionStart` (startup, clear, compact) | `scripts/session_start.py` | Rules, project commands and the state file go into the new context |
| `SubagentStart` (builder, reviewer) | `scripts/session_start.py --subagent` | The same rules go into the subagent's context |
| `PreToolUse` (edits, Bash) | `slop.py hook pre` | **Denies** the call when it edits a gate or the gates' state, adds a suppression, removes or disables a test or assertion, or bypasses git hooks |
| `PreToolUse` (edits, Bash, Read, Grep) | `scripts/guard.py` | **Denies** `gh pr merge` inside a subagent, and for the coordinator unless the slice is verified and reviewed at its head with CI green; force push, push to the default branch, amend or rebase of pushed commits, `add -f`; in a subagent or worktree `reset --hard`, `clean`, `stash`; removing a worktree with unsaved work; an edit from a worktree into the main checkout; reading `.env` and keys |
| `PostToolUse` (edits) | `slop.py hook post` | Findings on the edited file are fed back at once |
| `Stop`, `SubagentStop` (builder) | `scripts/slop_stop.py`, `scripts/done_check.py` | On slice branches, once the session has changed something (HEAD, tracked or untracked files since its start): full slop check, then scope, clean tree, pushed, open pull request, the project's gates, free disk. Exit 2 keeps the agent working. Then the clean command runs. A builder that ends off its slice branch fails |
| `PermissionDenied` | `scripts/log_event.py` | The refused call is appended to `<scratch>/nonslop/permission-denied.jsonl`, to tune allow lists from data |

Both Stop checks give up after `stop_retries` repeats of the same failures, so an agent cannot loop forever; the slice is then recorded as `released`, not done. A builder that ends with a `BLOCKED` report is asking a question and is let through, and recorded as `blocked`.

A hook that denies says what it matched and what to do instead. If a denying hook hits an internal error it denies and logs the crash instead of passing silently; the owner can set `SLOP_FAIL_OPEN=1` in Claude Code's environment if a bug there ever blocks real work.

Every slopstop hook call, and each finding it reports, is logged with its timing to `.git/slopstop/hits.jsonl`; the Stop checks and the guard log their decisions to `<scratch>/nonslop/{slop-stop,done-check,guard,merge-guard}.jsonl` in the main checkout. `nonslop stats` reads them.

## Layout

```
bin/nonslop        CLI
scripts/           hook entry points, the guard, the gate runner, slice records, stats (stdlib Python)
tools/slopstop/    static slop checks and the shell-command reader, self-contained (see NONSLOP-CHANGES.md)
tests/             hook payload tests and the slice commands end to end
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

- A full live run of the 0.2.0 loop: `/nonslop:coordinator` through `slice new`, builder, `slice verify`, reviewer, `slice review`, and the merge check against a real pull request. The parts are tested with scripted payloads and a local `origin`; `gh` against GitHub (pull request lookup, `gh pr checks` exit codes) is not.
- That `SubagentStop` matches the plugin-scoped agent names used in `hooks/hooks.json`. (The builder's worktree location, its start from the remote default branch, and `SubagentStart` are verified.)
- The permission lists in `templates/settings.json` under auto mode.
- Precision of the new rules (`test-removed`, `tautological-assert`, `assert-swallowed`, `dependency-added`) and of the guard on real agent work: they have seeded cases, not yet a triaged corpus.

## Licensing

Licensed under either of [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option.
The two vendored skills keep their own MIT licenses; see `THIRD_PARTY.md`.
