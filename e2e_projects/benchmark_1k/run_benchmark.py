#!/usr/bin/env python3
"""
Benchmark runner for mutmut process isolation comparison.

Runs mutmut under each strategy and reports throughput.

Usage:
    python run_benchmark.py [--strategies collect,import,none,fork] [--delay-configs 0.1:0.1,0.5:0.5,1.0:1.0]
                            [--show-output] [--verbose]

The delay configs simulate different conftest.py loading times (Flask, SQLAlchemy, etc.).
Format: import_delay:conftest_delay pairs, comma-separated.
Higher values show bigger differences between warmup strategies.

Optionally add --test-delay to simulate per-test runtime with +/-10% gaussian jitter.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


STRATEGIES = ["fork", "collect", "import", "none"]
DEFAULT_OUTPUT = "benchmark_results.json"
DEFAULT_DELAY_CONFIGS = "0.1:0.1,0.5:0.5,1.0:1.0"  # cli format


def clean_mutants():
    """Remove mutants directory for fresh run."""
    mutants_dir = Path("mutants")
    if mutants_dir.exists():
        shutil.rmtree(mutants_dir)


def get_pyproject_content(debug: bool = False, process_isolation: str = "fork") -> str:
    """Get base pyproject.toml content."""
    return f"""[project]
name = "benchmark-1k"
version = "0.1.0"
description = "Benchmark project for mutmut warmup strategy comparison (~1000 mutants)"
requires-python = ">=3.10"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/benchmark"]

[tool.mutmut]
log_to_file = true
paths_to_mutate = ["src/"]
process_isolation = "{process_isolation}"
debug = {"true" if debug else "false"}
"""


def run_mutmut(
    strategy: str,
    import_delay: float = 0.1,
    conftest_delay: float = 0.1,
    test_delay: float = 0.0,
    verbose: bool = False,
    show_output: bool = False,
) -> dict:
    """Run mutmut with specified strategy."""
    config = get_pyproject_content(debug=verbose, process_isolation=strategy if strategy == "fork" else "hot-fork")

    if strategy != "fork":
        config += f'hot_fork_warmup = "{strategy}"\n'
        if strategy == "import":
            config += 'preload_modules_file = "mutmut_preload.txt"\n'

    config_path = Path("pyproject.toml")
    config_path.write_text(config)

    clean_mutants()

    print("  Starting mutmut run...")
    start = time.perf_counter()

    cmd = ["mutmut", "run"]

    env = {
        **os.environ,
        "PYTHONPATH": "src",
        "BENCHMARK_IMPORT_DELAY": str(import_delay),
        "BENCHMARK_CONFTEST_DELAY": str(conftest_delay),
        "BENCHMARK_TEST_DELAY": str(test_delay),
    }

    if verbose or show_output:
        result = subprocess.run(cmd, text=True, env=env)
    else:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, env=env)

    returncode = result.returncode
    elapsed = time.perf_counter() - start

    summary_path = Path("mutants/summary.json")
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}

    stats = summary.get("stats", {})
    phase_timings = summary.get("phase_timings", {})

    total_mutants = stats.get("total", 0)
    mutation_testing_time = phase_timings.get("mutation_testing", 0)
    if mutation_testing_time > 0 and total_mutants > 0:
        throughput = total_mutants / mutation_testing_time
    else:
        throughput = 0

    # Rename mutants dir to preserve results for this strategy
    mutants_dir = Path("mutants")
    dir_name = f"mutants_{strategy}_i{int(import_delay*1000)}_c{int(conftest_delay*1000)}_t{int(test_delay*1000)}"
    strategy_dir = Path(dir_name)
    if strategy_dir.exists():
        shutil.rmtree(strategy_dir)
    if mutants_dir.exists():
        mutants_dir.rename(strategy_dir)
        print(f"  Results saved to {strategy_dir}/")

    return {
        "strategy": strategy,
        "elapsed_seconds": round(elapsed, 2),
        "mutations_per_second": round(throughput, 2),
        "total_mutants": stats.get("total", 0),
        "killed": stats.get("killed", 0),
        "survived": stats.get("survived", 0),
        "timeout": stats.get("timeout", 0),
        "suspicious": stats.get("suspicious", 0),
        "exit_code": returncode,
        "phase_mutant_generation": round(phase_timings.get("mutant_generation", 0), 3),
        "phase_stats_collection": round(phase_timings.get("stats_collection", 0), 3),
        "phase_clean_tests": round(phase_timings.get("clean_tests", 0), 3),
        "phase_forced_fail_test": round(phase_timings.get("forced_fail_test", 0), 3),
        "phase_mutation_testing": round(phase_timings.get("mutation_testing", 0), 3),
    }


def print_result(result: dict):
    """Print result summary for one strategy."""
    print(f"  Avg. Mut/s:    {result['mutations_per_second']:.2f} mut/s")
    print(f"  Total time:    {result['elapsed_seconds']:.1f}s")
    print(f"  Total mutants: {result['total_mutants']}")
    print(f"  Killed:        {result['killed']}")
    print(f"  Survived:      {result['survived']}")
    if result["timeout"] > 0:
        print(f"  Timeout:       {result['timeout']}")
    if result["exit_code"] != 0:
        print(f"  Exit code:     {result['exit_code']} (non-zero)")
    print("  Phase timings:")
    print(f"    Mutant generation: {result['phase_mutant_generation']:.3f}s")
    print(f"    Stats collection:  {result['phase_stats_collection']:.3f}s")
    print(f"    Clean tests:       {result['phase_clean_tests']:.3f}s")
    print(f"    Forced fail test:  {result['phase_forced_fail_test']:.3f}s")
    print(f"    Mutation testing:  {result['phase_mutation_testing']:.3f}s")


def main():
    parser = argparse.ArgumentParser(description="Benchmark mutmut run modes")
    parser.add_argument(
        "--strategies",
        default=",".join(STRATEGIES),
        help=f"Comma-separated list of strategies (default: {','.join(STRATEGIES)})",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Output JSON file (default: {DEFAULT_OUTPUT})")
    parser.add_argument(
        "--delay-configs",
        default=DEFAULT_DELAY_CONFIGS,
        help="Comma-separated import:conftest delay pairs. Default: 0.1:0.1,0.5:0.5,1.0:1.0",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable mutmut debug mode and show all output")
    parser.add_argument(
        "--show-output", "-s", action="store_true",
        help="Show mutmut stdout/stderr (spinners, progress) without enabling debug mode",
    )
    parser.add_argument(
        "--test-delay",
        type=float,
        default=0.05,
        help="Per-test delay in seconds with +/-10%% gaussian jitter (default: 0.05)",
    )
    args = parser.parse_args()

    strategies = [s.strip() for s in args.strategies.split(",")]
    for s in strategies:
        if s not in STRATEGIES:
            print(f"Error: Unknown strategy '{s}'. Valid: {STRATEGIES}")
            sys.exit(1)

    # Parse delay configs (e.g., "0.1:0.1,0.5:0.5" -> [(0.1, 0.1), (0.5, 0.5)])
    delay_configs = []
    for pair in args.delay_configs.split(","):
        import_delay, conftest_delay = pair.strip().split(":")
        delay_configs.append((float(import_delay), float(conftest_delay)))

    test_delay = args.test_delay

    if not Path("src/benchmark").exists():
        print("Error: Must run from benchmark_1k directory")
        sys.exit(1)

    print("=" * 60)
    print("Mutmut Process Isolation Benchmark")
    print("=" * 60)
    print(f"Strategies to test: {strategies}")
    print(f"Delay configs (import, conftest): {delay_configs}")
    print(f"Per-test delay: {test_delay}s (+/-10% jitter)")

    all_results = []
    import_delay = 0.05
    conftest_delay = 0.05

    for import_delay, conftest_delay in delay_configs:
        print(f"\n{'#' * 60}")
        print(f"# DELAY CONFIG: import={import_delay}s, conftest={conftest_delay}s, test={test_delay}s")
        print(f"{'#' * 60}")

        config_results = []

        for strategy in strategies:
            print(f"\n{'=' * 60}")
            print(f"Strategy: {strategy}")
            print("=" * 60)

            result = run_mutmut(
                strategy,
                import_delay=import_delay,
                conftest_delay=conftest_delay,
                test_delay=test_delay,
                verbose=args.verbose,
                show_output=args.show_output,
            )
            result["import_delay"] = import_delay
            result["conftest_delay"] = conftest_delay
            result["test_delay"] = test_delay
            config_results.append(result)
            print_result(result)

        all_results.append(
            {
                "import_delay": import_delay,
                "conftest_delay": conftest_delay,
                "results": config_results,
            }
        )

    flat_results = []
    for config in all_results:
        for r in config["results"]:
            flat_results.append(
                {
                    "import_delay": config["import_delay"],
                    "conftest_delay": config["conftest_delay"],
                    **r,
                }
            )

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "python_version": sys.version.split()[0],
        "strategies": strategies,
        "delay_configs": [(c["import_delay"], c["conftest_delay"]) for c in all_results],
        "test_delay": test_delay,
        "results": flat_results,
        "results_by_config": all_results,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(output, indent=2))
    print(f"\n\nResults saved to {output_path}")

    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)

    for config in all_results:
        import_delay = config["import_delay"]
        conftest_delay = config["conftest_delay"]
        config_results = config["results"]

        print(f"\n--- Delay: import={import_delay}s, conftest={conftest_delay}s ---")

        max_throughput = max(r["mutations_per_second"] for r in config_results) if config_results else 1

        print(f"{'Strategy':<12} {'Avg. Mut/s':>12} {'% of Max':>10} {'Mut Test':>10} {'Wall Time':>10}")
        print("-" * 60)

        for r in config_results:
            throughput = r["mutations_per_second"]
            pct_of_max = (throughput / max_throughput * 100) if max_throughput > 0 else 0
            mut_test_time = r.get("phase_mutation_testing", 0)
            print(
                f"{r['strategy']:<12} {throughput:>10.1f}/s {pct_of_max:>9.0f}% {mut_test_time:>8.1f}s {r['elapsed_seconds']:>8.1f}s"
            )

    print("\n" + "=" * 80)
    print("MUTATION THROUGHPUT COMPARISON ACROSS ALL DELAY CONFIGS")
    print("=" * 80)

    print(f"\n{'Strategy':<12}", end="")
    for config in all_results:
        delay = config["import_delay"]
        print(f" {delay}s delay".center(15), end="")
    print()
    print("-" * (12 + 15 * len(all_results)))

    for strategy in strategies:
        print(f"{strategy:<12}", end="")
        for config in all_results:
            for r in config["results"]:
                if r["strategy"] == strategy:
                    print(f" {r['mutations_per_second']:>10.1f}/s  ", end="")
                    break
        print()

    print()

    config = get_pyproject_content()
    Path("pyproject.toml").write_text(config)

    return 0


if __name__ == "__main__":
    sys.exit(main())
