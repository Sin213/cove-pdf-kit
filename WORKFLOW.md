This file covers repeatable local workflow for this repository.

When working in this repo, prefer existing local workflows over inventing new ones.

Before changing build or packaging behavior, search for the last successful local workflow and reuse it if possible.

For implementation tasks, prefer doing the obvious next step instead of asking for confirmation unless a missing detail blocks progress.

For build tasks, check for existing scripts, spec files, package scripts, or prior commands before creating a new workflow.

Prefer local builds over remote CI unless I explicitly ask for GitHub Actions or another remote system.

When a task is complete, report the exact command used, the exact output path, and any blockers still remaining.

If the repo has known artifact folders such as dist, build, or release, reuse them unless there is a good reason not to.

If a workflow is unclear, inspect the repo first, then ask only the minimum question needed to proceed.
