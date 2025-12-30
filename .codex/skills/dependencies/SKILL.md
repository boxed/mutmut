---
name: dependencies
description: Add/remove Python dependencies via uv while meeting repo policy (justification, tests, determinism).
metadata:
  short-description: Manage deps via uv
---

## Policy requirements (from AGENTS.md)

* Use `uv` for all package management, including adding/removing dependencies.
* Do not add new dependencies without an inline comment justifying the change.
* Prefer existing, popular, well-supported libraries when appropriate.

## When to use

Use this skill whenever you consider introducing a new third-party library, or removing/upgrading one.

## Decision procedure before adding a dependency

1) Confirm the need:
   * Is the functionality truly non-core to the project, or not highly customized?
2) Prefer existing solutions:
   * Standard library
   * Existing project dependencies
3) If adding a dependency is still justified:
   * Choose a well-supported library with stable maintenance and good adoption.
   * Minimize dependency surface area (avoid pulling in large stacks for small tasks).

## Required in-code justification

When introducing a new dependency, add an inline comment near the first usage explaining:

* why a third-party dependency is necessary (vs stdlib / existing deps)
* why this specific library was chosen
* any constraints (performance, determinism, portability)

Keep the comment brief but specific.

## Commands

Use `uv` for dependency changes. Prefer to run through `just setup` afterwards to refresh `.venv` if needed.

Typical flows:

* Add dependency: `uv add <package>`
* Add dev dependency: `uv add --dev <package>` (if your project uses this convention)
* Remove dependency: `uv remove <package>`
* Sync environment: `uv sync` (or `just setup`)

Do not add or remove dependencies in ways that bypass `uv` (e.g., editing lockfiles directly) unless explicitly instructed.

## Validation requirements after dependency changes

After modifying dependencies:

1) Run the standard validation pipeline (use `quality-gates`).
2) Add or update tests if the dependency supports new behavior or replaces custom logic.
3) Ensure determinism:
   * avoid time-dependent behavior introduced by the library
   * avoid environment-dependent defaults

## Reporting

When presenting the change:

* State the dependency added/removed and the reason (consistent with the inline comment).
* Identify any files updated by `uv` (lockfile, `pyproject.toml`, etc.).
* Confirm that `quality-gates` passed (or report failures precisely).
