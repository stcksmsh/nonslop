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
