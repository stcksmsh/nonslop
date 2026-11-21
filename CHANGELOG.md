# Changelog

Each release bumps `version` in `.claude-plugin/plugin.json`; Claude Code only installs an update when that
number changes. Tag a release with `claude plugin tag --push` (creates `nonslop--vX.Y.Z`).

"Upgrade" lists what a wired project must change by hand after updating, if anything.

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
