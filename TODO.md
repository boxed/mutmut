# TODO

## Architecture and boundaries

* [ ] **Introduce an application-layer run orchestration module**

  * Create `src/nootnoot/core/run_session.py` (name flexible) with a single public entrypoint like `run_mutation_session(...) -> RunReport`.
  * Define explicit inputs/outputs (no printing in core; return a report + events).
  * Acceptance:

    * CLI `nootnoot run` uses the core entrypoint.
    * Core module can be invoked from tests without Click or global state.

* [ ] **Thin the CLI to argument parsing + rendering**

  * Refactor `src/nootnoot/cli/run.py` to:

    * parse args
    * call `core.run_mutation_session`
    * render results + choose exit code
  * Acceptance:

    * `cli/run.py` contains minimal orchestration logic (no fork/wait loop, no file IO beyond calling core).
    * Error messaging goes to stderr; results go to stdout.

* [ ] **Introduce “ports” for side effects (dependency injection)**

  * Add lightweight interfaces / protocols for:

    * `Clock` (utcnow/time)
    * `Env` (get/set env vars for MUTANT_UNDER_TEST)
    * `FS` (read/write/atomic replace)
    * `ProgressSink` (spinner/progress updates)
    * `EventSink` / `Logger` (structured events)
  * Acceptance:

    * Core orchestration depends on interfaces, not concrete OS calls.
    * Unit tests can run with fakes (no real fork, no real pytest, no disk writes).

## Execution isolation (reduce heisenbugs)

* [ ] **Add a subprocess-based pytest runner**

  * Implement `SubprocessPytestRunner` (alongside or instead of in-process `pytest.main` usage).
  * Execute `python -m pytest ...` with:

    * `PYTHONPATH` set to prefer `mutants/`
    * `MUTANT_UNDER_TEST` set per mutant
  * Acceptance:

    * Mutation runs no longer require `sys.path` surgery.
    * Debug mode can print the exact subprocess command for repro.

* [ ] **Make execution strategy configurable**

  * Add config option, e.g. `runner = "subprocess" | "inprocess"` (default to safest).
  * Acceptance:

    * Works with existing configs; no behavior regressions for default usage.

* [ ] **Remove/retire `setup_source_paths()` sys.path mutation**

  * Replace with subprocess environment (`PYTHONPATH`) approach.
  * Acceptance:

    * `setup_source_paths()` removed or unused (kept only if needed for legacy runner).
    * No direct `sys.path.insert()` needed for the default runner path.

* [ ] **Rework module unloading during coverage gathering**

  * Avoid manipulating `sys.modules` for correctness.
  * Prefer running coverage in subprocess (or isolating the entire “coverage gather” step).
  * Acceptance:

    * Coverage gathering is deterministic and does not leak imports into the main process.

## Concurrency model (supervised workers, parent as single writer)

* [ ] **Replace fork/wait loop with a supervised worker model**

  * Use `multiprocessing` (or `concurrent.futures`) with:

    * work queue (mutant tasks)
    * result queue (exit code, duration, captured output metadata)
  * Parent process:

    * schedules tasks
    * collects results
    * writes `.meta` updates (single writer)
  * Acceptance:

    * No per-file mutable PID maps required for correctness.
    * Ctrl-C reliably stops workers and leaves meta in a consistent state.

* [ ] **Implement robust timeouts**

  * Wall-clock timeout enforced by supervisor (terminate worker process).
  * Optional Unix CPU time limit as an additional guard (where supported).
  * Acceptance:

    * Timeouts produce consistent “timeout” status.
    * No stuck workers after interrupt or timeout.

* [ ] **Capture and manage worker output deterministically**

  * Decide policy: capture stdout/stderr in workers, store in memory only on failure (or store truncated).
  * Acceptance:

    * Logs are not interleaved unpredictably across processes.
    * CLI output remains readable and stable.

## Persistence hardening (schema + atomic writes)

* [x] **Add schema versioning to stats and meta JSON**

  * Add `schema_version: int` to:

    * `mutants/nootnoot-stats.json`
    * each `mutants/<path>.meta`
  * Add migration logic on read (tolerate unknown keys; warn in debug).
  * Acceptance:

    * New fields don’t break old runs.
    * Unknown keys do not hard-fail by default.

* [x] **Implement atomic JSON writes**

  * Write to `*.tmp`, `flush + fsync`, then `os.replace(tmp, path)`.
  * Apply to both meta and stats saves.
  * Acceptance:

    * Abrupt termination does not corrupt JSON files.
    * Readers never observe partially-written JSON.

* [x] **Centralize persistence logic**

  * Move JSON read/write + migrations into dedicated module, e.g. `nootnoot/persistence.py`.
  * Acceptance:

    * `meta.py` and stats handling don’t duplicate serialization rules.

## Output, observability, and UX contracts

* [x] **Introduce structured event stream in core**

  * Core emits events like:

    * `session_started`, `mutant_started`, `mutant_finished`, `session_finished`, `error`
  * CLI subscribes and renders human output.
  * Acceptance:

    * Core does not call `print()`.
    * Unit tests can assert on emitted events.

* [x] **Add `--format json` output mode**

  * JSON output should be stable and machine-readable.
  * Ensure no ANSI / spinner output contaminates JSON mode.
  * Acceptance:

    * `nootnoot run --format json` prints valid JSON to stdout only.
    * Diagnostics go to stderr (or are suppressed per contract).

* [x] **Fix stdout/stderr separation across all commands**

  * Results: stdout
  * Diagnostics/progress/errors: stderr
  * Acceptance:

    * Running in pipelines works correctly (`nootnoot ... | jq`).

* [ ] **Make progress reporting TTY-aware and rate-limited**

  * Replace current spinner/print throttling with `ProgressSink`.
  * Disable progress automatically in non-TTY or JSON mode.
  * Acceptance:

    * No flicker spam in CI logs.
    * Progress updates do not interfere with result output.

## Testing strategy (locks in correctness)

* [ ] **Unit tests for new core orchestration**

  * Use fakes for runner/fs/clock/env.
  * Cover:

    * scheduling order
    * timeout handling
    * error propagation
    * event emission
  * Acceptance:

    * Tests do not require pytest invocation, fork, or real filesystem.

* [ ] **Component tests using a tiny fixture project**

  * Run end-to-end in a temp directory:

    * generates mutants
    * writes meta/stats
    * produces stable summary
  * Acceptance:

    * Deterministic results across runs.

* [ ] **System tests for CLI**

  * Execute `python -m nootnoot ...` as subprocess against fixture project.
  * Assert:

    * exit codes
    * key output lines (human)
    * valid JSON (machine)
  * Acceptance:

    * CLI contract is stable and versionable.

* [ ] **Contract tests for JSON output schema**

  * Snapshot tests for `--format json` output.
  * Acceptance:

    * Schema changes require intentional updates.

## Cleanup and consolidation

* [ ] **Remove duplicated helpers and consolidate constants**

  * Deduplicate `collected_test_names()` (currently exists in multiple modules).
  * Replace magic codes/strings with constants/enums where appropriate.
  * Acceptance:

    * Single source of truth for statuses/exit codes.

* [ ] **Document runner modes and output contracts**

  * Update README/docs to describe:

    * subprocess vs in-process runner
    * JSON format stability expectations
    * stderr/stdout rules
  * Acceptance:

    * Users know how to integrate nootnoot into CI reliably.
