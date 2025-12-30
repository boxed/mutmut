---
name: quality-gates
description: Run the repository’s standard validation pipeline (ruff/ty/pytest) and report results deterministically.
metadata:
  short-description: Run lint/format/typecheck/tests
---

## Scope

Use this skill after making any change under `src/` or `tests/` (including refactors), and before presenting a final diff.

This skill operationalizes the requirements in `AGENTS.md`:

* Linting: `.venv/bin/ruff check src/ tests/`
* Formatting: `.venv/bin/ruff format src/ tests/`
* Type checking: `.venv/bin/ty check src/ tests/` (with required fallback if missing)
* Testing: `.venv/bin/pytest`

Prefer running `just` recipes when available, because the `justfile` is the canonical automation entrypoint for this repo.

## Allowed paths and determinism

* Only edit files under `src/`, `tests/`, or `TODO.md` unless explicitly instructed otherwise.
* Use POSIX-style paths (`/`) in output and JSON.
* Sort file paths deterministically in reports (lexicographic).
* Do not emit ANSI styling in machine-readable output.

## Execution order

Run steps in this order:

1) Environment/bootstrap (only if needed)
2) Formatting
3) Linting
4) Type checking
5) Tests

Rationale: formatting first reduces churn; type errors are usually faster to fix than test failures; tests last.

## Commands

### Preferred (via `just`)

Run:

* `just setup` (only if dependencies or `.venv` are missing/outdated)
* `just format` (auto-format) or `just format-no-fix` (check only; do not modify)
* `just lint` (auto-fix where possible) or `just lint-no-fix` (check only; do not modify)
* `just typecheck`
* `just test-strict`

If you ran auto-fix steps (`just format` / `just lint`), rerun the corresponding “no-fix” check to confirm a clean state.

### Direct (if `just` is unavailable)

Run:

* `.venv/bin/ruff format src/ tests/`
* `.venv/bin/ruff check src/ tests/`
* `.venv/bin/ty check src/ tests/`
* `.venv/bin/pytest`

## Required fallback: missing `ty`

If `.venv/bin/ty` is not present or not executable:

1) Record a failure notice: "`ty` not found at .venv/bin/ty; cannot complete required static typing gate."
2) Do not attempt to “approximate” type checking with another tool unless explicitly instructed.
3) Emit proposed changes as a Markdown patch and halt further execution.

Reference: `patch-only-fallback` skill.

## Failure handling and reporting

If any step fails:

* Identify the failing command and include its exit status.
* Provide the smallest actionable summary of failures (first error lines, failing test names).
* Fix issues if the failure is within scope and deterministic to resolve.
* Re-run the failed step(s) and any downstream steps that depend on them.

## Coverage policy hook

If the workflow produces or updates a coverage XML report (e.g., `.coverage.xml` or `coverage.xml`) and you can compare it to the repository baseline:

* If coverage decreases from the baseline, log a warning and request user confirmation before proceeding with submission.

If you cannot determine the baseline, explicitly state that and do not claim coverage improvement.
