# Static gate corpus

Numbers for slopstop's free static gates: precision per rule on merged work,
recall per defect category on seeded defects, and run time per PR. Both scripts
run the same full check the Stop hook runs (`fast=False`), so results depend on
which analyzers are installed; `recall.py` prints the ones it found.

All output goes to `.claude/tmp/static-corpus/out/`, which is git-ignored. Do not
commit output from private repositories.

## Replay merged pull requests

```
python3 eval/static/replay.py <path-to-local-clone> [--limit N] [--out DIR]
```

Lists the repo's merged PRs with `gh` (run inside the clone), and for each one
checks out the merge commit in a temporary detached worktree under
`.claude/tmp/static-corpus/wt/`, runs
`tools/slopstop/slop.py check --base <merge>^1 --json` there, times it, and removes
the worktree. The check reads the target repo's own `.nonslop.toml` at that commit.
The target clone is only read and fetched from; its branches are not touched.

Clippy shares one `CARGO_TARGET_DIR` per repo (`.claude/tmp/static-corpus/cargo-target/<repo>/`)
so builds stay incremental across PRs; the first Rust PR of a run pays for a cold
build and shows up as the slowest. Delete that directory with `cargo clean
--target-dir <dir>` when done.

For squash and merge-commit merges, `<merge>^1` is the default branch before the
PR, so the diff is the whole PR. For rebase merges it is only the PR's last commit.

Output in `out/<repo>/`:

`findings.csv`, one row per finding, in the triage format of `eval/slopstop/`:

| column | meaning |
|---|---|
| repo | GitHub repository name |
| pr | PR number |
| head | PR head branch; agent-made PRs use the project's branch prefix (`claude/`, `claude/slice-`) |
| file, line | where the finding is, at the merge commit |
| rule | slopstop rule id (`ruff:…`, `detekt:…` etc. for analyzer rules) |
| severity | `block` or `warn` after the repo's own policy |
| tool | analyzer that produced it (`slop` for the built-in diff checks) |
| msg | finding message |
| label | empty; triage fills in `TP`, `FP` or `MEH` |
| reason | empty; one line on why |

`runs.csv`, one row per PR:

| column | meaning |
|---|---|
| repo, pr, head, title | the PR |
| merge | merge commit SHA |
| files_changed | files in `git diff --numstat <merge>^1 <merge>` |
| added_lines | added lines in that diff (binary files count 0) |
| findings | number of findings; empty if the run failed |
| seconds | wall time of the `slop.py check` call |
| error | why the PR could not be checked, else empty |

## Seeded recall

```
python3 eval/static/recall.py [--out DIR]
```

Runs every case in `seeded/cases.json` in its own throwaway git repo: the base
content is committed, the new content written over it (`base: null` = new file,
`new: null` = deleted file), and the check runs on that diff. Each content field is
a list of lines. A case counts as caught when the check reports any finding.
Which cases the gates should catch is deliberately not recorded: recall is
measured, not asserted. The secret values are fake but match the provider formats;
each is broken with `<<>>`, which `recall.py` removes, because GitHub push
protection rejects even fake tokens in a pushed file.

Prints a markdown table of recall per category and writes `recall.csv`:

| column | meaning |
|---|---|
| id | case id |
| category | `test-gaming`, `swallowed-error`, `secret`, `narrating-comment`, `stub-todo`, `versioned-debug` |
| path | file the case changes |
| caught | `yes` if the check reported anything |
| rules | rule ids that fired, so a catch for the wrong reason can be spotted |
