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

### Upgrade

- Projects wired before 0.1.0 may remove `extraKnownMarketplaces.nonslop` and
  `enabledPlugins."nonslop@nonslop"` from `.claude/settings.json` once the plugin is installed for the user.
  Leaving them is harmless.
