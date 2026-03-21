# Benchmark 1K

A synthetic benchmark project with 1000 mutants for validating mutmut's process isolation and hot-fork warmup strategy performance.

**TL;DR:**
- `fork` is fastest and nearly immune to import delays (requires fork-safe libraries)
- `collect` (hot-fork default) is 2-9x faster than `import`/`none` depending on import cost
- Higher import delays dramatically penalize `import` and `none` strategies


## Mutant Distribution

| Type       | Total | Killed | Survived | Kill Rate |
|------------|-------|--------|----------|-----------|
| return     | 221   | 161    | 60       | 73%       |
| number     | 159   | 99     | 60       | 62%       |
| argument   | 141   | 132    | 9        | 94%       |
| string     | 125   | 78     | 47       | 62%       |
| boolean    | 120   | 47     | 73       | 39%       |
| comparison | 119   | 19     | 100      | 16%       |
| operator   | 115   | 90     | 25       | 78%       |
| **Total**  | **1000** | **626** | **374** | **63%** |

## Usage

### Run mutation testing

```bash
cd e2e_projects/benchmark_1k
mutmut run
```

### Run benchmark comparison

```bash
python run_benchmark.py
```

This runs `mutmut run` under each strategy (`fork`, `collect`, `import`, `none`) and outputs:
- Throughput (mutations/second) for each strategy
- Results saved to `benchmark_results.json`

### View results

```bash
cat mutants/summary.json | python -m json.tool
```

## Test Design

Tests are fast unit tests with instant assertions. Configurable delays simulate real-world costs:

- **Import delay**: Simulates library import time (Flask, SQLAlchemy, etc.)
- **Conftest delay**: Simulates fixture/plugin setup time
- **Test delay**: Per-test runtime with +/-10% gaussian jitter for realistic variance

Usage:
```bash
python run_benchmark.py --test-delay 0.01  # Add 10ms per-test with jitter
```
