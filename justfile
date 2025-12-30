# ======================================================================
# Global shell + environment
# ======================================================================

set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := true
set export := true

# ----------------------------------------------------------------------
# Config (overridable via env/.env)
# ----------------------------------------------------------------------

PYTHON_PACKAGE := env("PYTHON_PACKAGE", "borh")
PY_TESTPATH    := env("PY_TESTPATH", "tests")
PY_SRC         := env("PY_SRC", "src")
VERBOSE        := env("VERBOSE", "0")

# ----------------------------------------------------------------------
# Tool wrappers
# ----------------------------------------------------------------------

UV         := "uv"
RUFF       := justfile_directory() + "/.venv/bin/ruff"
PYTEST     := justfile_directory() + "/.venv/bin/pytest"
TY         := justfile_directory() + "/.venv/bin/ty"
SHOWCOV    := justfile_directory() + "/.venv/bin/showcov"
MUTMUT     := justfile_directory() + "/.venv/bin/mutmut"
MKDOCS     := justfile_directory() + "/.venv/bin/mkdocs"
WILY       := justfile_directory() + "/.venv/bin/wily"
WILY_CACHE := justfile_directory() + "/.wily"
WILY_CONFIG := justfile_directory() + "/wily.cfg"
VULTURE    := justfile_directory() + "/.venv/bin/vulture"
RADON      := justfile_directory() + "/.venv/bin/radon"
JSCPD      := "npx --yes jscpd@4.0"
DIFF_COVER := justfile_directory() + "/.venv/bin/diff-cover"


# ======================================================================
# Meta / Defaults
# ======================================================================

[private]
default: help

# List available recipes; also the default entry point
help:
  @just --list --unsorted --list-prefix "  "

# Print runtime configuration (paths + tool binaries)
env:
  @echo "PYTHON_PACKAGE={{PYTHON_PACKAGE}}"
  @echo "PY_TESTPATH={{PY_TESTPATH}}"
  @echo "PY_SRC={{PY_SRC}}"
  @echo "UV={{UV}}"
  @echo "RUFF={{RUFF}}"
  @echo "PYTEST={{PYTEST}}"
  @echo "TY={{TY}}"
  @echo "SHOWCOV={{SHOWCOV}}"
  @echo "MUTMUT={{MUTMUT}}"
  @echo "MKDOCS={{MKDOCS}}"
  @{{UV}} --version || true
  @{{PYTEST}} --version || true
  @{{RUFF}} --version || true
  @echo "WILY={{WILY}}"
  @echo "WILY_CACHE={{WILY_CACHE}}"
  @echo "WILY_CONFIG={{WILY_CONFIG}}"
  @echo "VULTURE={{VULTURE}}"
  @echo "RADON={{RADON}}"
  @echo "JSCPD={{JSCPD}}"
  @echo "DIFF_COVER={{DIFF_COVER}}"

# ======================================================================
# Bootstrap
# ======================================================================

# Bootstrap: refresh .venv via `uv sync`
setup:
  {{UV}} sync

# ======================================================================
# Code quality: lint / format / type-check
# ======================================================================

# Code Quality: Lint with `ruff check` and auto-fix where possible
lint:
  {{RUFF}} check --fix {{PY_SRC}} {{PY_TESTPATH}} || true

# Code Quality: Check for linting violations with `ruff check` without modifying files
lint-no-fix:
  {{RUFF}} check --no-fix {{PY_SRC}} {{PY_TESTPATH}}

# Code Quality: Format with `ruff format` and auto-fix where possible
format:
  {{RUFF}} format {{PY_SRC}} {{PY_TESTPATH}} || true

# Code Quality: Check for formatting violations with `ruff format` without modifying files
format-no-fix:
  {{RUFF}} format --check {{PY_SRC}} {{PY_TESTPATH}}

# Code Quality: Typecheck with `ty` (if available)
typecheck:
  #!/usr/bin/env bash
  if [ -x {{TY}} ]; then
    {{TY}} check {{PY_SRC}} {{PY_TESTPATH}}
  else
    echo "[typecheck] skipping: ty not found ({{TY}})"
  fi

# Code Quality: dead-code scan
dead-code:
  {{VULTURE}} {{PY_SRC}} {{PY_TESTPATH}} || true

# Code Quality: complexity report
complexity:
  {{RADON}} cc -s -a {{PY_SRC}}

# Code Quality: raw metrics (optional)
complexity-raw:
  {{RADON}} raw {{PY_SRC}}

# Code Quality: strict complexity check (fail on high-complexity blocks)
complexity-strict MIN_COMPLEXITY="11":
  #!/usr/bin/env bash
  echo "[complexity-strict] Failing if any block has cyclomatic complexity >= ${MIN_COMPLEXITY}"
  output="$({{RADON}} cc -s -n {{MIN_COMPLEXITY}} {{PY_SRC}} || true)"
  if [ -n "$output" ]; then
    echo "[complexity-strict] Found blocks with complexity >= ${MIN_COMPLEXITY}:"
    echo "$output"
    exit 1
  fi
  echo "[complexity-strict] All blocks are below complexity ${MIN_COMPLEXITY}."

# Code Quality: duplication detection
dup:
  {{JSCPD}} --pattern "{{PY_SRC}}/*/*.py" --pattern "{{PY_SRC}}/*/*/*.py" --pattern "{{PY_SRC}}/*/*/*/*.py" --pattern "{{PY_TESTPATH}}/*/*.py" --pattern "{{PY_TESTPATH}}/*/*/*.py" --pattern "{{PY_TESTPATH}}/*/*/*/*.py" --reporters console


# ======================================================================
# Security / supply chain
# ======================================================================

# Security: Secret scan with trufflehog (report-only; does not fail if tool missing)
sec-secrets:
  #!/usr/bin/env bash
  if command -v trufflehog >/dev/null 2>&1; then
    tmp_file=$(mktemp)
    printf ".venv\nbuild\ndist\n" > "$tmp_file"
    trufflehog filesystem . --exclude-paths "$tmp_file"
    rm -f "$tmp_file"
  else
    echo "[sec-secrets] skipping: trufflehog not found on PATH"
  fi

# Security: Dependency scan with pip-audit
sec-deps:
  #!/usr/bin/env bash
  if [ -x .venv/bin/pip-audit ]; then
    .venv/bin/pip-audit
  else
    echo "[sec-deps] ERROR: .venv/bin/pip-audit not found; run 'just setup' to install dev deps"
    exit 1
  fi

# Security: Check external tools (presence + minimum versions)
sec-tools:
  #!/usr/bin/env bash
  if [ -x .venv/bin/python ] && [ -f scripts/check_tools.py ]; then
    .venv/bin/python scripts/check_tools.py
  else
    echo "[sec-tools] ERROR: scripts/check_tools.py missing"
    exit 1
  fi


# ======================================================================
# Testing
# ======================================================================

# Testing: Run full test suite 
test:
  {{PYTEST}} {{PY_TESTPATH}} || true

# Testing: Run full test suite and fail if any test fails
test-strict:
  {{PYTEST}} {{PY_TESTPATH}}

# Testing: Marker-driven test runner with graceful "no tests" handling
test-marker MARKER:
  #!/usr/bin/env bash
  set +e
  {{PYTEST}} {{PY_TESTPATH}} -m "{{MARKER}}"
  status=$?
  set -e
  if [ "$status" -eq 5 ]; then
    echo "[{{MARKER}}] skipping: no tests marked with {{MARKER}} collected"
  elif [ "$status" -ne 0 ]; then
    exit "$status"
  fi

# Testing: Run tests marked with "unit" and not marked with "slow"
test-fast:
  @just test-marker "unit and not slow"

# Testing: Run tests marked with "smoke"
test-smoke:
  @just test-marker "smoke"

# Testing: Run tests marked with "regression"
test-regression:
  @just test-marker "regression"

# Testing: Run tests marked with "performance"
test-performance:
  @just test-marker "performance"

# Testing: Run tests marked with "property_based"
test-property:
  @just test-marker "property_based"


# ======================================================================
# Test Quality
# ======================================================================

# Testing: Run full test suite and report slowest tests
test-timed:
  {{PYTEST}} {{PY_TESTPATH}} --durations=25

# Test Quality: Summarize coverage results from last test execution
cov:
  #!/usr/bin/env bash
  if [ -x {{SHOWCOV}} ]; then
    {{SHOWCOV}} --sections summary --format human || true
  else
    echo "[cov] skipping: showcov ({{SHOWCOV}}) not found"
  fi

# Test Quality: List lines not covered by last test execution
cov-lines:
  #!/usr/bin/env bash
  if [ -x {{SHOWCOV}} ]; then
    {{SHOWCOV}} --code --context 2,2 || true
  else
    echo "[cov-lines] skipping: showcov ({{SHOWCOV}}) not found"
  fi

# Test Quality: Run mutation testing on the test suite
mutation *ARGS:
  #!/usr/bin/env bash
  if [ -x {{MUTMUT}} ]; then
    {{MUTMUT}} run {{ARGS}}
  else
    echo "[mutmut] skipping: mutmut not found ({{MUTMUT}})"
  fi

# Test Quality: Report mutation testing results
mutation-report:
  #!/usr/bin/env bash
  if [ -x {{MUTMUT}} ]; then
    {{MUTMUT}} results
  else
    echo "[mutation-report] skipping: mutmut not found ({{MUTMUT}})"
  fi

# Test Quality: Mutation score summary (for humans/CI)
mutation-score:
  {{MUTMUT}} results | .venv/bin/python scripts/mutation_score.py


# Test Quality: Show the diff for every mutant listed by `mutmut results`
mutation-diffs *ARGS:
  #!/usr/bin/env bash
  echo "=== Mutant Diffs ==="
  .venv/bin/python scripts/mutation_diffs.py {{ARGS}} || true


# Test Quality: Test test flakiness by repeated runs of the test suite
flake N='5':
  #!/usr/bin/env bash
  set +e
  rm -f .flake-log.txt
  for i in $(seq 1 {{N}}); do
    echo "=== run $i ===" | tee -a .flake-log.txt
    {{PYTEST}} {{PY_TESTPATH}} --maxfail=50 --randomly-seed=last \
      | tee -a .flake-log.txt
  done
  set -e

# Test Quality: Report test flakiness results
flake-report:
  #!/usr/bin/env bash
  if [ -f .flake-log.txt ]; then
    if [ -x .venv/bin/python ] && [ -f scripts/flake_report.py ]; then
      .venv/bin/python scripts/flake_report.py
    else
      echo "[flake-report] scripts/flake_report.py missing; basic summary:"
      echo "Tests that failed in at least one run:"
      grep -oE "FAILED .*::[a-zA-Z0-9_]+" .flake-log.txt \
        | sed 's/FAILED *//g' \
        | sort | uniq -c | sort -nr
    fi
  else
    echo "[flake-report] no .flake-log.txt; run 'just flake' first"
  fi

# Test Quality: coverage of changed lines vs main
diff-cov BRANCH="origin/main":
  #!/usr/bin/env bash
  if [ ! -f .coverage.xml ]; then
    echo "[diff-cov] .coverage.xml not found; run 'just test-strict' first"
    exit 1
  fi
  {{DIFF_COVER}} .coverage.xml --compare-branch={{BRANCH}}

# Test Quality: strict coverage of changed lines vs main with threshold
diff-cov-strict BRANCH="origin/main" THRESHOLD="90":
  #!/usr/bin/env bash
  if [ ! -f .coverage.xml ]; then
    echo "[diff-cov-strict] .coverage.xml not found; run 'just test-strict' first"
    exit 1
  fi
  echo "[diff-cov-strict] Enforcing changed-line coverage >= ${THRESHOLD}% against ${BRANCH}"
  {{DIFF_COVER}} .coverage.xml --compare-branch={{BRANCH}} --fail-under={{THRESHOLD}}


# Test Quality: Performance regression check against baselines
perf-regression:
  #!/usr/bin/env bash
  if [ ! -d .perf_results ]; then
    echo "[perf-regression] skipping: no .perf_results directory; run 'just test-performance' first"
    exit 0
  fi
  if [ -x .venv/bin/python ] && [ -f scripts/check_perf_regression.py ]; then
    .venv/bin/python scripts/check_perf_regression.py
  else
    echo "[perf-regression] ERROR: scripts/check_perf_regression.py missing"
    exit 1
  fi


# ======================================================================
# Metrics
# ======================================================================

# Metrics: build or update wily index incrementally
wily-index:
  #!/usr/bin/env bash
  set -euo pipefail
  stash_name=""
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if [ -n "$(git status --porcelain)" ]; then
      stash_name="wily:temp:$(date -u +%Y%m%dT%H%M%SZ)"
      git stash push -u -m "$stash_name" >/dev/null
      trap 'git stash pop -q' EXIT
    fi
  fi
  {{WILY}} --config {{WILY_CONFIG}} --cache {{WILY_CACHE}} build {{PY_SRC}} {{PY_TESTPATH}}

# Metrics: report current metrics from index
wily-metrics FILE="": wily-index
  #!/usr/bin/env bash
  file="{{FILE}}"
  if [ -z "$file" ]; then
    file="{{PY_SRC}}/{{PYTHON_PACKAGE}}/__init__.py"
  fi
  {{WILY}} --config {{WILY_CONFIG}} --cache {{WILY_CACHE}} report "$file"

# Metrics: report stats for all files
wily-stats: wily-index
  #!/usr/bin/env bash
  mapfile -t files < <(rg --files -g '*.py' {{PY_SRC}} {{PY_TESTPATH}})
  if [ "${#files[@]}" -eq 0 ]; then
    echo "[wily-stats] no Python files found in {{PY_SRC}} or {{PY_TESTPATH}}"
    exit 0
  fi
  {{WILY}} --config {{WILY_CONFIG}} --cache {{WILY_CACHE}} diff --all --no-detail "${files[@]}"



# Metrics: report-only (no gating)
metrics-report:
  #!/usr/bin/env bash
  echo "=== Metrics Report (non-gating) ==="

  echo "--- Coverage summary ---"
  if [ -x {{SHOWCOV}} ]; then
    {{SHOWCOV}} --sections summary --format human || true
  else
    echo "[metrics-report] showcov not found ({{SHOWCOV}}); skipping coverage summary"
  fi

  echo
  echo "--- Mutation score ---"
  if [ -x {{MUTMUT}} ]; then
    {{MUTMUT}} results | .venv/bin/python scripts/mutation_score.py || true
  else
    echo "[metrics-report] mutmut not found ({{MUTMUT}}); skipping mutation score"
  fi

  echo
  echo "--- Complexity report ---"
  if [ -x {{RADON}} ]; then
    {{RADON}} cc -s -a {{PY_SRC}} || true
  else
    echo "[metrics-report] radon not found ({{RADON}}); skipping complexity report"
  fi

  echo
  echo "--- Duplication report ---"
  {{JSCPD}} --pattern "{{PY_SRC}}/**/*.py" --pattern "{{PY_TESTPATH}}/**/*.py" --reporters console || true

  echo
  echo "--- Flakiness report ---"
  if [ -f .flake-log.txt ]; then
    if [ -x .venv/bin/python ] && [ -f scripts/flake_report.py ]; then
      .venv/bin/python scripts/flake_report.py || true
    else
      echo "[metrics-report] flake_report script missing; using basic grep summary"
      grep -oE "FAILED .*::[a-zA-Z0-9_]+" .flake-log.txt \
        | sed 's/FAILED *//g' \
        | sort | uniq -c | sort -nr || true
    fi
  else
    echo "[metrics-report] no .flake-log.txt; run 'just flake' first for flake metrics"
  fi

  echo
  echo "=== Metrics Report complete (non-gating) ==="

# Metrics: enforce thresholds
metrics-gate:
  #!/usr/bin/env bash
  set -e

  echo "=== Metrics Gate (gating) ==="

  # 1) Ensure tests have proper markers and layout
  if [ -x .venv/bin/python ] && [ -f scripts/check_test_markers.py ]; then
    .venv/bin/python scripts/check_test_markers.py
  else
    echo "[metrics-gate] ERROR: scripts/check_test_markers.py not found"
    exit 1
  fi

  # 2) Coverage: enforce changed-line coverage threshold (e.g. 90%)
  if [ ! -f .coverage.xml ]; then
    echo "[metrics-gate] .coverage.xml not found; run 'just test-strict' first"
    exit 1
  fi
  {{DIFF_COVER}} .coverage.xml --compare-branch=origin/main --fail-under=90

  # 3) Complexity: enforce strict threshold
  {{RADON}} cc -s -n 11 {{PY_SRC}}

  # 4) Mutation: enforce minimum score
  if [ -x {{MUTMUT}} ]; then
    {{MUTMUT}} results | .venv/bin/python scripts/mutation_score.py | tee .mutation-score.txt
    if [ -x .venv/bin/python ] && [ -f scripts/check_mutation_threshold.py ]; then
      export MUTATION_MIN="${MUTATION_MIN:-70}"
      .venv/bin/python scripts/check_mutation_threshold.py < .mutation-score.txt
    else
      echo "[metrics-gate] ERROR: scripts/check_mutation_threshold.py not found"
      exit 1
    fi
  else
    echo "[metrics-gate] ERROR: mutmut not found ({{MUTMUT}})"
    exit 1
  fi

  echo "=== Metrics Gate PASSED ==="


# ======================================================================
# Documentation
# ======================================================================

# Documentation: Build documentation using `mkdocs`
build-docs:
  #!/usr/bin/env bash
  if [ -x {{MKDOCS}} ]; then
    {{MKDOCS}} build
  else
    echo "[build-docs] skipping: mkdocs not found ({{MKDOCS}} or on PATH)"
  fi

# Documentation: Serve the documentation site locally
docs: build-docs
  #!/usr/bin/env bash
  if [ -x {{MKDOCS}} ]; then
    python3 -m webbrowser http://127.0.0.1:8000
    {{MKDOCS}} serve --livereload
  else
    echo "[docs] skipping: mkdocs not found ({{MKDOCS}} or on PATH)"
  fi


# ======================================================================
# Build, packaging, publishing
# ======================================================================

# Production: Build Python artifacts with `uv build`
build:
  {{UV}} build

# Production: Publish to PyPI using `uv publish`
publish: 
  {{UV}} publish


# ======================================================================
# Running
# ======================================================================

# Run: CLI mode via `python -m {{PYTHON_PACKAGE}}`
cli: setup
  .venv/bin/python -m {{PYTHON_PACKAGE}}


# ======================================================================
# Cleaning / maintenance
# ======================================================================

# Cleaning: Remove caches/build artifacts and prune uv cache
clean:
  find . -name '__pycache__' -type d -prune -exec rm -rf '{}' +
  rm -rf .ruff_cache .pytest_cache .mypy_cache .pytype
  rm -rf .coverage .coverage.* coverage.xml htmlcov
  rm -rf dist build
  rm -rf logs
  rm -rf .hypothesis .ropeproject .wily mutants
  {{UV}} cache prune

# Cleaning: Stash untracked (non-ignored) files (used by `scour`)
stash-untracked:
  #!/usr/bin/env bash
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    msg="scour:untracked:$(date -u +%Y%m%dT%H%M%SZ)"
    if git ls-files --others --exclude-standard --directory --no-empty-directory | grep -q .; then
      git ls-files --others --exclude-standard -z | xargs -0 git stash push -m "$msg" -- >/dev/null
      echo "Stashed untracked (non-ignored) files as: $msg"
    else
      echo "No untracked (non-ignored) paths to stash."
    fi
  else
    echo "[stash-untracked] not a git repository; skipping"
  fi

# Cleaning: Remove git-ignored files/dirs while keeping .venv
scour: clean stash-untracked
  #!/usr/bin/env bash
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git clean -fXd -e .venv
  else
    echo "[scour] not a git repository; skipping git clean"
  fi


# ======================================================================
# Composite flows
# ======================================================================

# Convenience: setup, lint, format, typecheck, build-docs, test, cov
fix: setup lint format typecheck build-docs test cov

# CI: lint/type/tests/coverage summary with tool fallbacks
check: setup format-no-fix lint-no-fix typecheck test-strict cov sec-deps

ci-pr: check diff-cov-strict sec-secrets sec-tools

ci-nightly: setup test-strict complexity-strict dead-code mutation flake cov mutation-report flake-report test-property metrics-gate sec-secrets sec-tools sec-deps

ci-slow: ci-nightly wily-index wily-metrics test-performance perf-regression
