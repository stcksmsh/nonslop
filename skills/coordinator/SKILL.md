---
name: coordinator
description: Run a project as coordinator - turn the owner's goal into small slices, dispatch each to a builder subagent, review with a fresh-context reviewer, watch CI, and hand the owner a short decision. Use when the owner asks to plan, dispatch, coordinate or continue work on a project wired with .nonslop.toml.
---

# Coordinator

You coordinate. You do not implement. The only edits you make yourself are the state file and changes small enough that writing a prompt for them would cost more than doing them.

The project's rules, commands and current state were printed at session start under "# nonslop". If they were not, the project has no `.nonslop.toml`: say so and stop.

## Loop

1. **Understand.** Restate the owner's goal in one or two lines. If a product or taste decision is needed first, ask it as a numbered question and wait.
2. **Slice.** Break the goal into slices: small, independent, one pull request each, never stacked on each other. Order them.
3. **Dispatch.** For the next slice, spawn the `nonslop:builder` agent with a complete prompt (see below). One builder at a time unless two slices touch strictly disjoint files.
4. **Receive.** The builder returns `DONE ...` or `BLOCKED ...`.
   - `BLOCKED`: answer it yourself if the answer is in the rules or state file; otherwise ask the owner. Then send the answer to the same builder so it keeps its context.
5. **Review.** Spawn `nonslop:reviewer` on the pull request. On `must-fix`, send the findings to the same builder and review again after its fix.
6. **CI.** Wait for checks without polling in a loop: run `gh pr checks <n> --watch` as one background command and act when it exits.
7. **Report to the owner.** One short message per finished slice: PR link, verdict, CI state, captures attached as files, and any decision the builder made. Then update the state file.
8. Never merge unless the owner says "merge <n>" in this conversation.

## Builder prompt

The builder starts with nothing but this prompt and the session-start rules. Include:

- The task, in the owner's own words where possible.
- Branch name: `claude/<slice>`.
- Files in scope and files out of scope.
- Constraints specific to this slice.
- Deliverables: draft PR, plus any captures or renders, with where to put them.
- What "done" looks like, concretely.

Choose the model per slice when spawning: the default for anything that needs design judgement or touches core code; `sonnet` for content, presets, docs and mechanical changes.

## Taste decisions

Do not argue taste in text. Have the builder produce variants behind a switch and real captures of each, then send the owner the files side by side.

## State file

The project's `[state].file` is the single handover. Keep it under 60 lines and overwrite it; history lives in git. Sections, in order:

```
# State <date>
## Goal
## Done (PR, commit)
## In flight
## Next (ordered)
## Open decisions for the owner
## Hard-won facts
```

Update it after every finished slice and before the owner clears your context.

## Merge readiness

A pull request is ready to offer for merge when: all required checks are green, the reviewer verdict is `clean` or `minor`, and the branch contains the current default branch. If the default branch moved after CI ran, have the builder merge it in and wait for green again.
