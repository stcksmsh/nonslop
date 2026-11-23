# Changelog

Each release bumps `version` in `.claude-plugin/plugin.json`; Claude Code only installs an update when that
number changes. Tag a release with `claude plugin tag --push` (creates `nonslop--vX.Y.Z`).

"Upgrade" lists what a wired project must change by hand after updating, if anything.

## 0.1.5

- New skill `/nonslop:wire`: wires the current repo to nonslop (finds the real commands, runs init, fills
  `.nonslop.toml`, runs doctor, dry-runs the slop checks on recent merged PRs, opens a draft PR). The README
  leads with it; the manual steps stay as a fallback.

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
