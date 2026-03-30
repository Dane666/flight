# Flight Project Rules

This repository defaults to a low-waste workflow for Codex and other agents.

## Default Working Style

- Read the relevant files before editing.
- Prefer minimal, verifiable changes over broad rewrites.
- Do not refactor unrelated code while fixing the current problem.
- Do not add new dependencies unless they are clearly necessary.
- For UI work, preserve the existing visual quality. Do not make the UI worse while fixing logic.
- Keep each session focused on one concrete goal when possible.
- Large requests should be split into smaller milestones instead of one large pass.

## Planning

Use a short plan before editing when the task is more than a small single-file fix.

The plan should clarify:

- what problem is being solved
- which files are likely to change
- what the first safe step is

Do not start large edits before the plan is clear.

## Change Size

Prefer "minimum verifiable change":

- one round should fix one clear point
- verify that point before continuing
- avoid bundling multiple risky changes together

If a task is large, complete it in stages instead of one rewrite.

## Validation

After each meaningful change:

- run the smallest relevant validation immediately
- confirm the changed point works before continuing

At the end of the task, always report:

- validation steps
- expected result
- done definition
- remaining edge cases or known gaps

## Reusable Workflows

If a workflow becomes repetitive, capture it in a skill instead of re-explaining it each time.

Examples:

- smoke-test flow
- bugfix closeout format
- review output format
- release note format

## Closeout Format

When finishing work, include:

- what changed
- how to verify it
- what counts as done
- any unresolved boundary conditions
