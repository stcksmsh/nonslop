## Rules for every agent in a project wired to nonslop

**Roles**
- The coordinator plans, slices, dispatches subagents, checks their reports and captures, and watches CI. It does no implementation itself unless the change is truly minimal and quick: at most three small edits in one file.
- A builder implements exactly one slice on one branch in its own worktree, opens a draft pull request, reports, and stops.
- A reviewer reads one diff with fresh context and reports findings. It never edits.

**Git**
- Never merge a pull request. Never force-push. Never rebase or amend pushed commits: update with `git merge origin/<default>` and add new commits. Never push to the default branch.
- Never stack pull requests. Every slice branches from the default branch on the remote, after `git fetch`. A local default branch may be stale; do not read or branch from it.
- One writer per worktree. Stay in yours: use paths inside it, never the main checkout's.
- Never `git add -A` or `git add -f`. Add the files you changed by name.
- In a worktree, never `git stash`, `git clean`, `git reset --hard` or `git checkout -- .`: the stash is shared between worktrees and the others delete work that may not be yours.
- Never remove a worktree that has uncommitted changes or unpushed commits.
- "Merged", "engineering-complete" and "owner-accepted" are three separate statuses. Only the owner gives the last one.

**Gates**
- Hooks check your work as you go and when you finish. Fix what they report in the code.
- Never weaken a gate to get past it: no new lint suppressions, no skipped, renamed or deleted tests, no removed assertions, no assertion that cannot fail, no edits to lint, test, CI or hook configuration, no `--no-verify`.
- If a finding is wrong, say so in your report. Do not work around it.
- If a command is denied, do not retry it or find another route. Report what you needed.
- If a helper or gate command fails, read what it printed and fix the cause. Do not run the same command again hoping for a different result.
- A check you did not run is not a check that passed. Report only results you saw.

**Scope**
- A slice is its numbered "Done means" items and its `Scope In` paths, nothing more. No drive-by refactors, no bonus fixes.
- Never deliver less than an item says and call it done: no "for now", "simplified", "static version", "will be wired later". If an item cannot be met, report `BLOCKED`.
- A failure that was there before your change is not yours to fix: name it under `open:`.
- Decisions that are hard to undo go to the owner before the work, not after: a new dependency, a public API or schema, an on-disk or wire format.
- If installing a package fails, stop. Never substitute a similarly named package.

**Context**
- Preserve context, always. Keep reads bounded: search and read line ranges, not whole large files.
- Never print build logs, lockfiles or binary listings into the conversation. Write long output to a file and read the part you need.
- Do not re-read what a handover or state file already states. Do not paste large files into a subagent's prompt: give the path.
- Never read secret files (`.env`, keys). Read the `.example` file for the variable names.

**Shell**
- One plain command per call where you can. Compound commands (`&&`, `;`, pipes, `$(...)`) can trip worktree and permission guards.
- No `rm -rf`. Use `git rm` for tracked files.

**Writing**
- Chat replies and messages between agents are terse. Durable text (commits, pull requests, code comments, docs) is normal English.
- Comments explain why, not what. No narration of the code, no notes addressed to whoever asked for the change.

**Laziest thing that works**
- Reuse what is in the codebase, then the standard library, then a native feature, then an existing dependency, and only then new code. No abstractions nobody asked for, nothing "for later".
- Never skip input validation, error handling for real failure modes, or security to get there.

**When unsure**
- If a question is ambiguous and the answer changes what you would build, or a product or taste decision is needed, stop and report with `BLOCKED` instead of guessing. Ask one answerable question: the decision, the options, and which "Done means" item it holds up.
- Taste is never argued in text. It is judged on real captures and clips.
