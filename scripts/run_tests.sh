#!/bin/bash
set -e
cd "$(dirname "$0")/.."
docker build -t mutmut -f ./docker/Dockerfile.test .
docker run --rm -t -v "$(pwd)":/mutmut mutmut "$@"
