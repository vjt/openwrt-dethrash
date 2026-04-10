#!/bin/bash
#
# Build and test station-resolver in Docker (no local Go needed).
# Usage: ./build.sh [test|build]
#   test  — run tests only (default)
#   build — compile binary to ./station-resolver
#
set -euo pipefail

cd "$(dirname "$0")"

IMAGE="golang:1.23-alpine"
ACTION="${1:-test}"

case "$ACTION" in
  test)
    echo "Running tests..."
    docker run --rm -v "$PWD":/src -w /src "$IMAGE" go test -v ./...
    ;;
  build)
    echo "Building station-resolver..."
    docker run --rm -v "$PWD":/src -w /src \
      -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH=arm64 \
      "$IMAGE" go build -o station-resolver .
    echo "Built: station-resolver (linux/arm64)"
    ;;
  *)
    echo "Usage: $0 [test|build]" >&2
    exit 1
    ;;
esac
