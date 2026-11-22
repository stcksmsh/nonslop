# State 2026-11-22

## Goal
One updateable Claude Code plugin that keeps agent-written code clean in all of Kosta's projects, wired one project at a time.

## Done
- 0.1.0 (#1–#7): version, MIT OR Apache-2.0, CI, install once per user. Trial fixes: "backup" name false positive, retired allow rules (env, timeout, python3, find, gh api), selftest SKIP text, ruff `--no-cache`, bad `--base` fails, new untracked protected files flagged.
- 0.1.1 (#8) Stop skips a session that changed nothing. 0.1.2 (#9) `.nonslop.toml` lookup stops at the repo root. 0.1.3 (#10) slice branch prefix in the rules and the coordinator.
- 0.1.3 installed at user scope in `~/.claude` and `~/.claude-alt`.
- Wired: aegis (aegis#1, `045fa02`, `branch_prefix = "claude/slice-"`), kabl (kabl#186, `fd5be61`), nonslop itself (this file).
- Live headless checks passed: rules at SessionStart in a wired repo; silent in unwired and nested repos; Stop lets an unchanged session go; skills listed under both configs.

## In flight
None.

## Next
1. Secrets release 0.2.0, slices:
   a. template denies Read/Edit of `**/.env*`, `**/*.pem`, `**/*.key`, `**/id_rsa*`, `**/credentials*.json`, `~/.ssh/**`, `~/.aws/**`; `init` adds them to wired projects;
   b. pre-hook blocks `git add`/commit of those names and Bash commands matching the `SECRET` regex (`tools/slopstop/slop.py`);
   c. fix and test `a_gitleaks` (marked untested), install gitleaks in CI, doctor reports it;
   d. `[slop].secret_patterns` for project secrets (aegis: a literal `RESTIC_PASSWORD=` value or a passphrase as an argument).
   One selftest case per slice that fails on the old code.
2. Verify the builder path live: a coordinator slice through `nonslop:builder`. Check that SubagentStart/SubagentStop matchers fire, hook `cwd` is the builder worktree, and the worktree starts from origin/<default>. Then clear README "Not verified yet".
3. Upgrade path: a `schema` key in `.nonslop.toml`; `doctor` reports drift (missing keys, old schema, permissions vs template).
4. `/nonslop:wire` skill: orient, init, fill the toml from CI and agent docs, doctor, fast dry run over recent PRs, triage, wiring PR.
5. Wire the next project.

## Waiting on owner
- aegis `[slop]`: `ruff:BLE001` blocked once falsely (`tests/e2e_handover.py` poll loop); `ruff:T201` warns on E2E prints. Tune or leave.
- kabl: allow `Bash(gh api -X PATCH repos/stcksmsh/kabl/pulls/:*)` (auto-mode refused my adding it); install Rust 1.100.0 to match CI (kabl uses `+1.99.0`); `kabl_agents` sink is not loaded.
- Pull local checkouts: aegis and kabl roots are behind their master.

## Hard-won facts
- Release: in the PR bump `version` in `.claude-plugin/plugin.json` and add a CHANGELOG entry → squash-merge → wait for green main CI → `claude plugin tag --push <clean checkout at origin/main>` → `claude plugin marketplace update nonslop` and `claude plugin update nonslop@nonslop`. Repeat both with `CLAUDE_CONFIG_DIR=/home/stcksmsh/.claude-alt`. No version bump, no update.
- kabl sessions run on `~/.claude-alt`, aegis on `~/.claude`. Plugins load at session start: restart after install or update.
- Live hook test: `claude -p "..." --model haiku --tools "" --strict-mcp-config --no-session-persistence --output-format stream-json --include-hook-events --verbose > file`, then `jq` the `hook_response` events. The `init` event lists plugins and slash commands.
- `slop check --all` on nonslop flags its own suppression-regex lines in `slop.py` (`suppression-added`); editing those lines trips the gate. Report it, do not work around it.
- The worktree guard reads paths containing `eval` as shell `eval`; use `git grep` for `eval/`.
- `gh pr edit` fails (GraphQL Projects classic); use `gh api -X PATCH .../pulls/<n> -F body=@file`.
- The auto-mode classifier refuses widening a project's permission allow list; the owner adds those himself.
