## Rules for every agent in a project wired to nonslop

**Roles**
- The coordinator plans, slices, dispatches subagents, checks their reports and captures, and watches CI. It does no implementation itself unless the change is truly minimal and quick.
- A builder implements exactly one slice on one branch in its own worktree, opens a draft pull request, reports, and stops.
- A reviewer reads one diff with fresh context and reports findings. It never edits.

**Git**
- Never merge a pull request. Never force-push. Never rebase a pushed branch: update with `git merge origin/<default>`. Never push to the default branch.
- Never stack pull requests. Every slice branches from the default branch on the remote, after `git fetch`. A local default branch may be stale; do not read or branch from it.
- One writer per worktree.
- Never `git add -A`. Add the files you changed by name.
- "Merged", "engineering-complete" and "owner-accepted" are three separate statuses. Only the owner gives the last one.

**Gates**
- Hooks check your work as you go and when you finish. Fix what they report in the code.
- Never weaken a gate to get past it: no new lint suppressions, no skipped or deleted tests, no removed assertions, no edits to lint, CI or hook configuration, no `--no-verify`.
- If a finding is wrong, say so in your report. Do not work around it.
- If a command is denied, do not retry it or find another route. Report what you needed.

**Context**
- Preserve context, always. Keep reads bounded: search and read line ranges, not whole large files.
- Never print build logs, lockfiles or binary listings into the conversation. Write long output to a file and read the part you need.
- Do not re-read what a handover or state file already states.

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
- If a question is ambiguous and the answer changes what you would build, or a product or taste decision is needed, stop and report with `BLOCKED` instead of guessing.
- Taste is never argued in text. It is judged on real captures and clips.
