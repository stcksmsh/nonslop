# slopstop

Not vendored yet. The improved kit lives in the kabl repository, draft PR #167, under `eval/slopstop/improved/`.

To bring it in, from a kabl checkout on that branch:

```sh
cp -r eval/slopstop/improved/. <nonslop>/tools/slopstop/
```

Keep this directory self-contained: nothing here may import from the rest of nonslop, so it can be split back out into its own repository later.

Once the files are here, wire its `PreToolUse`, `PostToolUse` and `Stop` entry points into `hooks/hooks.json` next to the existing hooks, and move the `[slop]` settings from `.slop.toml` into each project's `.nonslop.toml`.
