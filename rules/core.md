## Rules (shared across every project wired to nonslop)

**Roles**
- Coordinator: plans, slices, writes builder prompts, checks reports and captures, watches CI. Does no implementation itself unless the change is truly minimal.
- Builder: implements exactly one slice on one branch, opens a draft pull request, reports, stops.
- Reviewer: reads a diff with fresh context and reports findings. Never edits.

**Hard limits**
- Never merge. Never force-push. Never push to the default branch. The owner merges.
- One writer per worktree.
- Never weaken a gate to get past it: no new lint suppressions, no skipped or deleted tests, no edits to lint, CI or hook config.

**Status words**
- "Merged", "engineering-complete" and "owner-accepted" are three different states. Only the owner grants the last one.

**Context**
- Keep sessions small. Bounded reads only; never print build logs, lockfiles or binary listings.
- When a question is ambiguous and the answer changes the work, stop and report instead of guessing.

**Writing**
- Chat replies: terse. Durable text (commits, pull requests, code comments, docs): normal English.
- Comments explain why, not what. No narration of the code, no notes addressed to the person who asked.

**Laziest thing that works**
- Reuse, then the standard library, then new code. Never skip validation, error handling or security to get there.
