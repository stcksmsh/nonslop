# State 2026-11-23

## Goal
One updateable Claude Code plugin that keeps agent-written code clean in all of Kosta's projects. Two halves, both must hold: the workflow and the gates. Measure what nonslop saves with real numbers; build only what the numbers support.

## Done
- 0.1.0–0.1.5 (#1–#17): see CHANGELOG. Wired: aegis, kabl, nonslop. Builder path verified live.
- 0.2.0 on branch `ccr-27207502-hdarvr`, not merged, not tagged: gates read commands as argv (`shellcmd.py`), dotfile protection bug fixed, test-gaming rules, crash policy, `scripts/guard.py`, slice records, `nonslop slice new|verify|review|close|show`, `nonslop status`, `nonslop stats`, rewritten builder/reviewer/coordinator/rules. Selftest 84 pass, `tests/test_hooks.py` 69 pass.

## In flight
- claude/static-corpus: `eval/static/` replay of merged PRs and seeded recall set (state before this session; check `nonslop status`).

## Next
1. Owner reviews and merges 0.2.0; release steps below. Then one live coordinator run through the new loop on a small slice.
2. Re-run the static corpus against 0.2.0: precision per rule for `test-removed`, `tautological-assert`, `assert-swallowed`, `dependency-added` and the guard denials. Demote anything noisy.
3. `nonslop stats` on kabl and aegis after a week of use: tokens and review rounds per merged PR.
4. A/B harness for caveman and ponytail (haiku), as planned.
5. Only with numbers: baseline/ratchet for `check --all`; evidence ledger; review gate beyond the single reviewer.

## Waiting on owner
- Add CI step `python tests/test_hooks.py` to `.github/workflows/ci.yml`, and `hooks = "python3 tests/test_hooks.py"` to `[commands]` in `.nonslop.toml` (agents edit neither).
- aegis and kabl after updating: pull requests without CI need `[merge] allow_no_ci = true`; decide `[guard] secret_read` per project.
- aegis `[slop]` tuning (BLE001, T201); kabl allow rule, Rust 1.100.0, kabl_agents sink; pull aegis and kabl checkouts.

## Decisions
- Taken from the open-gsd projects as ideas, no text: argv parsing of commands, commit-pinned verdicts, bounded review rounds, verify independent of the builder, recovery from git state, failure-first gate output.
- Not taken: phase pipelines and planning artifacts, SQLite/daemon state, orchestrator-lands and auto-merge, full shell emulation, injection and base64 scanners, commit-message validator, review panels and skeptic agents, code index/graph. Reason: prose- or state-heavy, unmeasured, or solved by PR-per-slice.
- Not built, on purpose: evidence ledger (not verified that Claude Code's PostToolUse payload carries a command's exit code; `slice verify` runs the gates itself, which needs no such record); baseline/ratchet (slopstop judges added lines only, so there is no legacy backlog to baseline until `check --all` becomes a gate).
- A release after `stop_retries` stays (an agent must not loop forever) but is recorded and blocks the coordinator's merge.

## Hard-won facts
- Release: bump version + CHANGELOG in the PR → squash-merge → green main CI → owner runs `claude plugin tag --push .` (auto mode refuses it for agents) → `claude plugin marketplace update nonslop` and `claude plugin update nonslop@nonslop`, both also with `CLAUDE_CONFIG_DIR=/home/stcksmsh/.claude-alt`.
- Config can only be created via `init --from`: every Edit/Write and (since 0.2.0, for real) every shell write to `.nonslop.toml` is denied.
- Agents cannot edit `.github/workflows/**`; CI changes go to the owner.
- `gh pr merge --delete-branch` fails while a builder worktree holds the branch: delete the remote branch, then `git worktree remove <path>` without `--force`; if it refuses, something is unsaved. Local squash-merged branches need `-D`, which is denied: leave them.
- Max subscription only: no API spend. `--bare` needs an API key; measure with `claude -p --output-format stream-json`.
- kabl sessions run on `~/.claude-alt`, aegis on `~/.claude`. Plugins load at session start.
- `gh pr edit` fails; use `gh api -X PATCH repos/stcksmsh/nonslop/pulls/<n> -F body=@file`.
- The auto-mode classifier refuses widening a project's permission allow list.
- Transcripts: `~/.claude*/projects/<path with - for />/<session>.jsonl` plus `<session>/subagents/agent-*.jsonl`; one API response spans several lines with the same `message.id`.
