# Changelog

Each release bumps `version` in `.claude-plugin/plugin.json`; Claude Code only installs an update when that
number changes. Tag a release with `claude plugin tag --push` (creates `nonslop--vX.Y.Z`).

"Upgrade" lists what a wired project must change by hand after updating, if anything.

## 0.2.0

Gates and workflow, after reading how the open-gsd projects handle the same problems and probing
nonslop's own hooks with the bypasses they record. `docs/STATE.md` lists what was deliberately not taken.

Gates:

- **Fixed: dotfiles were not protected against shell writes.** `echo x > .nonslop.toml`,
  `tee .claude/settings.json` and `>> .github/workflows/ci.yml` passed the pre hook, because the path
  lost its leading dot before it was compared.
- Shell commands are read as commands and arguments, not matched as text (`tools/slopstop/shellcmd.py`).
  Now denied: `git commit -nm`, `git -C . commit --no-verify`, `git -c core.hooksPath=...`, abbreviated
  `--no-verif`, `HUSKY=0` / `LEFTHOOK=0`, the same inside `bash -c`, `env`, `timeout`. No longer denied:
  `git push -n`, and a flag that only appears inside a commit message or a heredoc.
- Writes to a protected file are also seen through `git checkout <ref> -- file`, `git restore`, `dd of=`,
  `ln`, `install` and inline `python -c` / `node -e` code.
- Protected by default now: test-runner and formatter configuration (`pytest.ini`, `setup.cfg`,
  `tox.ini`, `mypy.ini`, `jest.config.*`, `vitest.config.*`, `rustfmt.toml`, `deny.toml`,
  `.cargo/config.toml`, `.husky/**`), the `test` scripts of `package.json`, shell scripts and task files
  that `[commands]` runs, and the gates' own state (`.git/slopstop/`, `<scratch>/nonslop/`).
- Test gaming: an assertion that cannot fail (`assert True`, `expect(true).toBe(true)`) and a
  commented-out assertion no longer count as assertions; a test that is removed or renamed so the runner
  skips it is `test-removed`; `.only`, `fit`, `pytest.skip(` and `#[ignore = ...]` count as skips; a test
  that catches its own `AssertionError` is reported.
- `dependency-added` (advisory; a project can make it blocking) reports new direct dependencies in
  `package.json`, `Cargo.toml`, `pyproject.toml`, `requirements*.txt` and `go.mod`.
- An internal error in the pre hook used to exit 0 silently. It now denies the call, says so, and logs
  the crash. Post and Stop still let the agent continue. `SLOP_FAIL_OPEN=1` in Claude Code's environment
  restores the old behaviour if a bug ever blocks real work.
- New hook `scripts/guard.py` (replaces `merge_guard.py`) denies: force push, push to the default
  branch, amending or rebasing pushed commits, `git add -f`; in a subagent or worktree also
  `reset --hard`, `clean`, `stash`, whole-tree `checkout`/`restore`; removing a worktree with unsaved
  work; an edit from a worktree into the main checkout; reading `.env`, `.secrets` and private keys.
- Gates: a failure line above the tail is reported; `[done.expect]` fails a gate that exits 0 without the
  expected output; a pass is remembered per command and commit and not re-run.
- When Stop or the done-check lets an agent go with failures open, that is written to the slice record as
  `released`. The done-check counts repeated failures per branch, in a row or not, fails a subagent that
  ends off its slice branch, and requires the pull request to be open.
- The selftest fails if a rule slop.py can emit has no seeded case. `tests/test_hooks.py` feeds every
  nonslop hook its payloads and runs the slice commands end to end.

Workflow:

- Slice records. `nonslop slice new <brief.md>` lints the builder prompt (numbered, checkable "Done
  means"; `Scope In` paths; branch prefix), refuses a scope that overlaps a slice in flight, and writes
  the record. The done-check then holds the builder to that scope.
- `nonslop slice verify <branch>` checks the pushed head in a fresh worktree (slop checks, gates, scope,
  default branch merged in), independent of the builder's report.
- `nonslop slice review <branch> <verdict> --sha <sha>` records a reviewer verdict against the commit it
  judged; a verdict for an older commit is refused; three must-fix rounds print `ESCALATE`.
- The coordinator's `gh pr merge` of a slice branch is denied unless the slice is verified and reviewed
  at its current head and CI is green. A pull request with no CI at all is refused.
- `nonslop status` lists every slice branch and worktree with its pull request, CI, record, and unsaved
  work, and says what to do about each. Session start lists open slice records.
- `nonslop stats`: gate hits per rule, hook time, finish-check outcomes, tokens per branch from the
  session transcripts (subagents included), review rounds per slice. Measured values only.
- Builder, reviewer, coordinator and the shared rules are rewritten around the above: evidence per
  "Done means" item, reviewer judges exists / wired / real data / tested and never runs tests in the
  coordinator's checkout, scope reduction is must-fix, later review rounds may only block on earlier
  findings or changed code, recovery of dead builders from git state, no forced worktree removal.

Upgrade:

- Restart Claude Code. The plugin's `hooks.json` changed.
- The coordinator can no longer merge a slice pull request that has not been through
  `nonslop slice verify` and `nonslop slice review`. To keep the old behaviour in a project, the owner
  sets `[merge] guard = false` in its `.nonslop.toml`.
- Projects whose pull requests have no CI: set `[merge] allow_no_ci = true`, or the merge is refused.
- Agents can no longer read `.env`. If a project needs that, the owner sets `[guard] secret_read = false`.
- Optional new tables for `.nonslop.toml`: `[verify]`, `[merge]`, `[guard]`, `[done.expect]`; see
  `templates/nonslop.toml`. Hook logs moved to the main checkout's scratch directory.
- `nonslop`'s own CI should also run `python tests/test_hooks.py` (owner: agents do not edit workflows).

## 0.1.5

- New skill `/nonslop:wire`: wires the current repo to nonslop (finds the real commands, runs init, fills
  `.nonslop.toml`, runs doctor, dry-runs the slop checks on recent merged PRs, opens a draft PR). The README
  leads with it; the manual steps stay as a fallback.
- `nonslop init --from <file.toml>` writes the given file (checked with tomllib) instead of the template when
  `.nonslop.toml` is missing. An existing `.nonslop.toml` is still kept. This lets the skill draft the config
  outside the protected file name and dry-run it before the repo is opted in.

## 0.1.4

- slopstop logs every hook call with its wall time, and every finding it reports with rule, severity and
  decision, to `.git/slopstop/hits.jsonl`. `slop_stop.py`, `done_check.py` and `merge_guard.py` log
  their decisions (skip and why, pass, fail with the failures, deny) to
  `<scratch>/nonslop/{slop-stop,done-check,merge-guard}.jsonl`. This is the data for a later
  `nonslop stats`. No gate decides differently.

## 0.1.3

- The session rules state the project's slice branch prefix (`[done].branch_prefix`), and the coordinator
  names builder branches with it instead of a fixed `claude/`. A project that narrows the prefix (for
  example `claude/slice-`, so other `claude/` work branches are not held to slice rules) still gets its
  slices checked.

## 0.1.2

- The hooks look for `.nonslop.toml` only inside the current git repository. A repository nested in a
  wired one (a scratch clone under `.claude/tmp/`, a vendored repo) was treated as wired by its parent and
  got the parent's rules and commands. slopstop already stopped at the repository root.

## 0.1.1

- The Stop checks skip a session that has changed nothing since it started. Before, a session that only
  answered a question on a `claude/` branch was blocked over work already on the branch, and told to
  revert the owner's own `.nonslop.toml` and `.claude/settings.json`. SessionStart records the state
  under `<scratch>/nonslop/sessions/`.

## 0.1.0

First versioned release.

- Licensed MIT OR Apache-2.0.
- Install once per user (`claude plugin install nonslop --marketplace stcksmsh/nonslop --scope user`).
  The plugin is silent in projects without `.nonslop.toml`.
- `nonslop init` no longer adds `extraKnownMarketplaces` / `enabledPlugins` to a project's
  `.claude/settings.json`; it merges only `env` and permissions.
- `nonslop doctor` shows the installed plugin version and scope, and prints its sections in order.
- CI runs the slopstop selftest and checks every script compiles.
- The settings template no longer allows `env`, `timeout`, `python3`, `find` or `gh api` without a prompt;
  each could run any command past the deny list.
- `versioned-name` and `variant-of-existing` no longer treat "backup" as a hedged suffix.
- `slop check` fails on an unknown `--base` instead of reporting clean, and flags new, uncommitted
  protected files (CI workflows, `.nonslop.toml`, lint configs) as `gate-tampered`.
- ruff runs without a cache, so no `.ruff_cache/` is left in the project.
- The selftest names only the tools that are actually missing.

### Upgrade

- Re-run `nonslop init` in each wired project and commit `.claude/settings.json`: it removes the five
  retired allow rules.
- Projects wired before 0.1.0 may remove `extraKnownMarketplaces.nonslop` and
  `enabledPlugins."nonslop@nonslop"` from `.claude/settings.json` once the plugin is installed for the user.
  Leaving them is harmless.
