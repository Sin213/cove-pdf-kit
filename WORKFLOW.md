This file covers repeatable local workflow for this repository.

When working in this repo, prefer existing local workflows over inventing new ones.
Before changing build or packaging behavior, search for the last successful local workflow and reuse it if possible.
For implementation tasks, prefer doing the obvious next step instead of asking for confirmation unless a missing detail blocks progress.
For build tasks, check for existing scripts, spec files, package scripts, or prior commands before creating a new workflow.
Prefer local builds over remote CI unless I explicitly ask for GitHub Actions or another remote system.
If the repo has known artifact folders such as dist, build, or release, reuse them unless there is a good reason not to.
If a workflow is unclear, inspect the repo first, then ask only the minimum question needed to proceed.

### Command Discipline
- Reuse prior successful commands before inventing new ones.
- Do not rerun heavy commands repeatedly unless code or inputs changed.
- For logs, test output, or build output, keep only the actionable lines needed to proceed.
- Do not paste large raw terminal output into the response unless I explicitly ask for full output.

### Handoff Discipline
- Treat handoff files as delta documents, not full reports.
- Update only sections affected by the current pass.
- Prefer evidence paths over pasted contents.
- For verification, record only command name, pass/fail, and changed state.
- If a check fails, include only the minimal failing excerpt.

### Phase Execution Rule
- Only execute the current requested phase.
- Do NOT implement future phases early.
- Do NOT expand scope beyond the phase.
- If a task belongs to a later phase, explicitly defer it.

### Output Discipline
- Prefer minimal diffs over full file rewrites.
- Only show new files or changed sections when possible.
- Summarize unchanged code instead of repeating it.
- When a task is complete, report:
  - exact command(s) used
  - exact output path(s)
  - blockers still remaining
