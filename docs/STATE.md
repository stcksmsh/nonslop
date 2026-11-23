# State 2026-11-23

## Goal
One updateable Claude Code plugin that keeps agent-written code clean in all of Kosta's projects. Current focus: measure what nonslop saves with real numbers, then build only what the numbers support. Plan: three parts (workflow, static gates, optional token gates); research report and plan live outside git.

## Done
- 0.1.0–0.1.3 (#1–#10): see CHANGELOG. Wired: aegis, kabl, nonslop.
- 0.1.4 (#12, `d6c7b4f`): gate hit log `.git/slopstop/hits.jsonl` (per hook call: decision, ms; per finding: rule, severity) and wrapper logs in `<scratch>/nonslop/*.jsonl`.
- #14: `.claude/worktrees/` gitignored (unblocks `claude plugin tag`).
- 0.1.5 (#15, `90fb810`): `/nonslop:wire` skill and `nonslop init --from <draft>`. Tagged `nonslop--v0.1.5`, installed in `~/.claude` and `~/.claude-alt`.
- Builder path verified live: worktree under `.claude/worktrees/`, starts at origin/main, SubagentStart rules injected.

## In flight
- claude/static-corpus: `eval/static/` replay of merged PRs (kabl, aegis, nonslop) and seeded recall set. Builder running.

## Next
1. Model triage of the static findings (reviewer labels, owner spot-checks 30) → precision per rule.
2. `nonslop stats`: hit log + session transcripts (`~/.claude*/projects/*.jsonl`) → tokens, time, review rounds per merged PR. Zero quota.
3. Small A/B harness, quota only for caveman and ponytail (haiku): caveman 12 single-turn prompts × 3 arms × 3; ponytail 6 small tasks × 3 arms × 3. Pilot first; owner reads `/usage` before and after; full set only if ≤ ~15% of a 5h window.
4. 0.2.0 secrets + hardening (bypass gaps HUSKY=0/LEFTHOOK=0/stash, `git push -n` false positive, test-gaming rules, onFailure block, escape-hatch line, plugin hooks/scripts protected), each with a before/after number.
5. New-dependency gate; baseline/ratchet; review gate only if it beats the single reviewer per token.

## Waiting on owner
- Add CI step `python tests/test_cli_init.py` to `.github/workflows/ci.yml` (agents are blocked from CI config).
- aegis `[slop]` tuning (BLE001, T201); kabl allow rule, Rust 1.100.0, kabl_agents sink; pull aegis and kabl checkouts.

## Hard-won facts
- Release: bump version + CHANGELOG in the PR → squash-merge → green main CI → owner runs `claude plugin tag --push .` (auto mode refuses it for agents) → `claude plugin marketplace update nonslop` and `claude plugin update nonslop@nonslop`, both also with `CLAUDE_CONFIG_DIR=/home/stcksmsh/.claude-alt`.
- Once `.nonslop.toml` exists the pre hook denies every Edit/Write/cp of it (matched by file name anywhere); create config only via `init --from`.
- Agents cannot edit `.github/workflows/**`; CI changes go to the owner.
- `gh pr merge --delete-branch` fails while a builder worktree holds the branch; delete the remote branch and `git worktree remove --force` instead. Local squash-merged branches need `-D`, which is denied: leave them.
- Max subscription only: no API spend. `--bare` needs an API key; measure with `claude -p --output-format stream-json`.
- kabl sessions run on `~/.claude-alt`, aegis on `~/.claude`. Plugins load at session start.
- The worktree guard reads paths containing `eval` as shell `eval`; use `git grep` for `eval/`.
- `gh pr edit` fails; use `gh api -X PATCH repos/stcksmsh/nonslop/pulls/<n> -F body=@file`.
- The auto-mode classifier refuses widening a project's permission allow list.
