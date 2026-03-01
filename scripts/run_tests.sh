#!/bin/bash
set -e
cd "$(dirname "$0")/.."

usage() {
    echo "Usage: $0 [--py 3.10,3.12,3.14] [--ff] [-- pytest args...]"
    echo "  --py   Comma-separated Python versions to test."
    echo "                  Default: 3.10"
    echo "  --ff     Stop on first failure instead of running all versions."
    echo ""
    echo "  Everything after '--' is forwarded to pytest."
    exit 1
}

PY_VERSIONS="3.10"
FAIL_FAST=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --py)
            PY_VERSIONS="$2"
            shift 2
            ;;
        --ff)
            FAIL_FAST=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        --)
            shift
            break
            ;;
        *)
            break
            ;;
    esac
done

IFS=',' read -r -a VERSIONS <<< "$PY_VERSIONS"
RESULTS=()

print_results() {
    echo ""
    echo "=== Results ==="
    for RESULT in "${RESULTS[@]}"; do
        echo "  $RESULT"
    done
}

for VER in "${VERSIONS[@]}"; do
    IMAGE_NAME="mutmut-test-${VER}"
    docker build -t "$IMAGE_NAME" --build-arg "PYTHON_VERSION=$VER" -f ./docker/Dockerfile.test .
    if docker run --rm -t -v "$(pwd)":/mutmut "$IMAGE_NAME" "$@"; then
        RESULTS+=("Python $VER: PASSED")
    else
        RESULTS+=("Python $VER: FAILED")
        if [[ "$FAIL_FAST" == true ]]; then
            print_results
            exit 1
        fi
    fi
done

print_results

for RESULT in "${RESULTS[@]}"; do
    if [[ "$RESULT" == *FAILED* ]]; then
        exit 1
    fi
done
