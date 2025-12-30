---
name: changelog-release
description: Update CHANGELOG.md (Keep a Changelog) and bump pyproject.toml version consistently with repo policy.
metadata:
  short-description: Update changelog + version
---

## When to use

Use this skill when a change is user-visible or release-relevant (features, fixes, behavior changes, deprecations, removals, security).

## Files

* `CHANGELOG.md`
* `pyproject.toml`

If `CHANGELOG.md` does not exist, create a stub file and note that it was missing.

## Keep a Changelog rules (repo policy)

* Use the heading format: `## [x.y.z] - YYYY-MM-DD`
* Allowed sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`
* Historical entries are never modified.
* Each bullet:
  * begins with a lowercase imperative verb (e.g., “add”, “fix”, “remove”, “deprecate”)
  * uses valid Markdown list syntax

## Procedure

1) Determine whether the change warrants a version bump.
   * If uncertain, default to *not* bumping and explicitly state uncertainty; do not guess silently.
2) If bumping:
   * Update `pyproject.toml` version to the new `x.y.z`.
3) Update `CHANGELOG.md`:
   * Add a new topmost entry for the new version/date.
   * Place changes under the correct section(s).
   * Do not edit older entries.
4) Ensure changelog content matches actual code changes:
   * No speculative bullets.
   * No missing bullets for significant user-visible changes.

## Version selection guidance (pragmatic)

Use semantic versioning heuristics unless the repository specifies otherwise:

* PATCH: bug fix, internal refactor with no behavior change, test-only changes (often no release)
* MINOR: additive feature, new CLI option, backwards-compatible behavior enhancement
* MAJOR: breaking change, removal, incompatible behavior change

If the repo already uses a different scheme, follow the existing precedent.

## Output discipline

When reporting the changelog update:

* Show the exact new changelog entry you added.
* Show the `pyproject.toml` version line that changed.
* Keep paths POSIX-style and sort any lists deterministically.
