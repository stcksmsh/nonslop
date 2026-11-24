# State 2026-11-24

## Goal
One updateable Claude Code plugin that keeps agent-written code clean in all of Kosta's projects. Two halves, both must hold: the workflow and the gates. Measure what nonslop saves with real numbers; build only what the numbers support.

## Done
- 0.1.0–0.1.5 (#1–#17): see CHANGELOG. Wired: aegis, kabl, nonslop.
- 0.2.0 (#18, 4d6296a): argv command parsing, guard.py, slice records, `nonslop slice new|verify|review|close`, `status`, `stats`.
- 0.2.1 (#19, 1248920): interpreter secret reads denied; scope globs stay inside one path segment. First live run of the 0.2.0 loop.
- 0.2.2 (#20, 3f73673): `[merge] coordinator = "ask"|"auto"`; owner decisions given in full, never by ID.
- #21: nonslop itself sets `coordinator = "auto"`.
- 0.2.3 (#23, ca9fda4): caveman and ponytail skills deleted; a short Style block in rules/core.md replaces them (owner, 2026-11-24). Same block in global `~/.claude/CLAUDE.md` and `~/.claude-alt/CLAUDE.md`.
- Tags nonslop--v0.2.0–0.2.3 pushed; 0.2.3 installed in `~/.claude` and `~/.claude-alt`.

## In flight
- claude/static-corpus (PR #13, draft, behind main): `eval/static/` replay and seeded recall. Needs main merged in before the 0.2.x re-run.

## Next
1. Hardening release (pending owner): heredoc secret reads (`python3 - <<EOF`), unwrap `uv run`/`npx`/`pnpm exec`, CHANGELOG note that `.pem`/`.key` interpreter args are refused, log allowed merges in the merge guard, no "commits on no remote" denial for a squash-merged branch's worktree.
2. `[slice] max_in_flight` per project (pending owner); kabl OOM: shared `CARGO_TARGET_DIR` + `CARGO_BUILD_JOBS` (pending owner).
3. Re-run the static corpus against 0.2.x: precision for `test-removed`, `tautological-assert`, `assert-swallowed`, `dependency-added`, guard denials. Propose demotions; owner decides.
4. `nonslop stats` on kabl and aegis after a week of use.
5. Optional: A/B the Style block against no instruction (haiku, minimal quota, pilot first), if its effect is ever in doubt.

## Waiting on owner
- 4 decisions: verify gates for nonslop (`hooks` command + `[verify].run`), kabl build sharing, `max_in_flight`, scope of the hardening release.
- Delete standalone `skills/caveman` and `skills/ponytail` in `~/.claude` and `~/.claude-alt` (`rm -rf` is denied for agents); kabl's `.nonslop.toml` note about caveman/ponytail.
- Delete 15 local squash-merged branches (`git branch -D` is denied for agents); `nonslop status` lists them.
- aegis `[slop]` tuning (BLE001, T201); kabl allow rule, Rust 1.100.0, kabl_agents sink.

## Decisions
- Merge: coordinator merges nonslop slices once verify, review and CI pass (`coordinator = "auto"`, 2026-11-24). Subagents never merge. aegis and kabl stay `"ask"` until the owner changes them.
- Owner decisions: status says "N decisions pending"; full question, options, recommendation and answer format only when asked or blocking.
- aegis and kabl have CI: `allow_no_ci` stays false; `[verify].run` empty there (cargo in a fresh worktree is slow; CI runs lint and tests); `secret_read` stays true.
- From the open-gsd comparison: argv parsing, commit-pinned verdicts, bounded review rounds, independent verify, recovery from git state. Not taken: phase pipelines, daemon state, auto-merge without checks, review panels, code index.

## Hard-won facts
- Release: version + CHANGELOG in the PR → squash-merge → green main CI → tag `nonslop--v<ver>` (annotated, message `nonslop <ver>`). Auto mode often refuses `claude plugin tag --push .`; `git tag -a` + `git push origin <tag>` works → `claude plugin marketplace update nonslop` + `claude plugin update nonslop@nonslop`, both also with `CLAUDE_CONFIG_DIR=/home/stcksmsh/.claude-alt` → `/reload-plugins` in running sessions.
- Owner-requested edits to protected files (`.nonslop.toml`, `.github/workflows/**`) go through the GitHub contents API on a branch plus a PR, only on the owner's explicit instruction; local edits are denied by design.
- Cleanup order: `git worktree remove` before deleting the remote branch; afterwards the guard sees "commits on no remote" and refuses.
- `gh pr checks --watch` started right after `gh pr create` can exit 1 with "no checks reported"; re-run it.
- Claude Code's own worktree guard refuses Bash heredocs whose text contains "git"; builders use Edit/Write for file content.
- SubagentStop fires for `nonslop:builder` (done-check logs `agent` and `decision`).
- Max subscription only: no API spend. kabl sessions run on `~/.claude-alt`, aegis on `~/.claude`.
- `gh pr edit` fails; use `gh api -X PATCH repos/stcksmsh/nonslop/pulls/<n> -F body=@file`.
