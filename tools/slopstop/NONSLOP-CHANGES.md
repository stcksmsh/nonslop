# Changes made to slopstop inside nonslop

This directory is the improved slopstop kit from the kabl evaluation (kabl draft PR #167,
`eval/slopstop/improved/slopstop/`), copied unchanged except for the edits listed here. The history of
the kit before that, including the patch against the original and the notes for its author, is under
`eval/slopstop/`.

Keep this directory self-contained: nothing here imports from the rest of nonslop, so the kit can be
split back out into its own repository.

## 2026-11-21: read settings from `.nonslop.toml`

`slop.py` only:

- New `CONFIG_FILES` and `config_file()`. Settings come from the `[slop]` table of `.nonslop.toml`
  when that file exists, otherwise from `.slop.toml` as before.
- `opted_in()` accepts either file, so hooks are active in any project wired to nonslop.
- `.nonslop.toml` added to `PROTECTED_DEFAULT`, so agents cannot edit their own gate configuration.

`slop init` and `slop install-global` are not used by nonslop (the plugin's `hooks/hooks.json` and
`nonslop init` replace them) and are unchanged.

## Selftest status

25 passed, 1 failed, 13 skipped on a machine without `ast-grep`, both before and after the change
above. The failure is `rust: semantic slop`, which expects the ast-grep rule `rs-empty-fn` and is not
skipped when ast-grep is missing.

2026-11-21, with ast-grep 0.51.3, ruff 0.17.6 and shellcheck 0.11.0 installed: 36 passed, 0 failed,
3 skipped (detekt, biome, cppcheck missing).

## 2026-11-21: selftest names only the missing tools

A skipped case printed every tool it needs, so `SKIP typescript ... (missing ['ast-grep', 'biome'])`
appeared with ast-grep installed. It now lists only the tools that are absent.

## 2026-11-21: fixes from the aegis trial

`slop.py` and `semantic.py`:

- `BAD_NAME` and the `variant-of-existing` suffixes no longer contain `backup`: in a backup app it is the
  domain noun, and all four blocking `versioned-name` findings in the trial were false.
- `collect_diff` exits with git's error when `git diff` fails, instead of returning no changes (an
  unknown `--base` printed `slopstop: clean`).
- Untracked files carry the diff's base, so a new protected file is flagged `gate-tampered`.
- ruff runs with `--no-cache`.

Selftest after these: 38 passed, 0 failed, 3 skipped (detekt, biome, cppcheck missing).

## 2026-11-22: hit log with timing

`slop.py` and `selftest.py`:

- New `log_hits()` appends to `.git/slopstop/hits.jsonl` (next to `stop.json`). Each hook call in an
  opted-in git repository writes one record per finding it reported (`ts, session, event, rule, severity,
  decision, file`) and one record for the call itself (`rule: null, decision, ms`), also when nothing
  fired. `decision` is `deny` or `pass` for pre, `warn` or `pass` for post, `block`, `warn` or `pass` for
  stop. A failed write (`OSError`) is dropped; it never changes the hook's outcome.
- To give each call one exit point to time, the bodies of `hook_pre`, `hook_post` and `hook_stop` moved
  into `pre_verdict`, `post_findings` and `stop_verdict`. Their checks and outputs are unchanged; pre
  denials now carry a rule name (`gate-bypass`, `gate-tampered`, `suppression-added`, `test-weakened`).
- Selftest: a denied pre call logs a finding and a timed call record; a passing post call logs a `pass`
  call record. All three assertions fail on the previous `slop.py`.

Selftest after these: 41 passed, 0 failed, 3 skipped (detekt, biome, cppcheck missing).

## 2026-11-23: commands read as argv, test gaming, crash policy, release marker

New file `shellcmd.py` (stdlib only, imports nothing from nonslop). `slop.py`, `selftest.py`:

- **Bug fix.** `pre_verdict` stripped `./` from a token with `lstrip("./")`, which also removed the
  leading dot of every dotfile, so `.nonslop.toml`, `.slop.toml`, `.claude/settings.json` and
  `.github/workflows/**` were never matched for shell writes. Fixed with `removeprefix("./")`.
- `BASH_BYPASS` and `BASH_WRITE` (regexes over the whole command line) are gone. `bash_verdict` parses the
  command with `shellcmd.parse` into simple commands (quotes, heredoc bodies and comments handled;
  `$(...)`, backticks, `sh -c`, `eval` and runner prefixes unwrapped) and decides per command:
  `bypass_reason` (hook-skipping env vars, `-c core.hooksPath`, `git config core.hooksPath`, `--no-verify`
  and its accepted abbreviations on commit/push/merge/rebase/am/cherry-pick/revert/pull, `-n` clusters on
  commit only, `chmod -x` on hooks) and `write_targets` (redirections, tee/mv/rm/..., destination of
  cp/ln/install, `sed -i`, `perl -i`, `dd of=`, `git checkout|restore|rm|mv`, inline interpreter code that
  writes). A denial names what matched. `git push -n` and flags inside a commit message no longer deny.
- `PROTECTED_DEFAULT` grew: test-runner and formatter configs, `.husky/**`, slopstop's own state files.
  `gate_scripts()` adds the shell scripts and task files named in `.nonslop.toml` `[commands]`.
  `MANIFEST_LINT["package.json"]` also covers `test` scripts.
- Test checks: `real_asserts()` ignores comments and `TAUTOLOGY` matches; new rules `tautological-assert`
  (block), `test-removed` (block, also in the pre hook), `assert-swallowed` (advisory). `SUPPRESS` also
  matches `.only`/`.todo`, `fit`/`fdescribe`, `pytest.skip(`, unprefixed `pytest.mark.skip`, `#[ignore`.
- New rule `dependency-added` (advisory): direct dependencies a manifest gained relative to the base.
- Crash policy: `hook_crashed()`. Pre denies in an opted-in repo and logs `decision: crash`; post and stop
  let the agent continue. `SLOP_FAIL_OPEN=1` disables the deny. The catch lists exception classes
  (`INTERNAL_ERRORS`) instead of `Exception`. A malformed `tool_input` raises instead of passing.
- `record_release()` writes `.git/slopstop/released.json` (branch, commit, findings) when Stop lets an
  agent go after `stop_retries`.
- Selftest: seven new cases, 30 pre-hook command checks (17 deny, 9 allow, 4 test edits), crash-policy
  and release checks, and a completeness check: every rule id `slop.py` or `semantic.py` can emit must be
  wanted by a case (four tool- or size-dependent ids are listed as not seeded). The dotfile, `-nm`,
  `git -C`, `-c core.hooksPath`, `HUSKY=0`, `git push -n`, `assert True` and renamed-test checks all fail
  on the previous `slop.py`.

Selftest after these: 84 passed, 0 failed, 3 skipped (detekt, biome, cppcheck missing).
