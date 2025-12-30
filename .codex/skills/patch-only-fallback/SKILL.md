---
name: patch-only-fallback
description: Required behavior when shell/tool execution is unavailable - produce a patch and expected command outcomes and halt.
metadata:
  short-description: Patch-only mode
---

## When to use

Use this skill whenever:

* shell access is unavailable, or
* required tooling is missing/misconfigured (notably `.venv/bin/ty`), or
* you cannot run validation commands required by `AGENTS.md`.

## Required behavior

1) Emit a Markdown-formatted patch containing the proposed edits.
2) Describe what you would run (exact commands) to validate the change:
   * `.venv/bin/ruff format src/ tests/`
   * `.venv/bin/ruff check src/ tests/`
   * `.venv/bin/ty check src/ tests/`
   * `.venv/bin/pytest`
3) Describe the *expected* outcomes at a high level (e.g., “ruff clean”, “tests pass”), but do not fabricate logs.
4) Halt execution (do not proceed as if the checks ran).

## Output constraints

* Use POSIX-style paths.
* Sort file paths deterministically in the patch and any enumerations.
* Do not include ANSI styling.
