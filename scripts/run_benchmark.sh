#!/bin/bash
set -e
cd "$(dirname "$0")/../e2e_projects/benchmark_1k"

usage() {
    echo "Usage: $0 [--strategies fork,collect,import,none] [--delay-configs 0.1:0.1,0.5:0.5] [-- extra args...]"
    echo ""
    echo "  Runs the benchmark_1k benchmark from the repo root."
    echo "  All arguments are forwarded to run_benchmark.py."
    echo ""
    echo "  --help, -h   Show this help and the benchmark script's help."
    exit 1
}

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    usage
fi

python run_benchmark.py "$@"
