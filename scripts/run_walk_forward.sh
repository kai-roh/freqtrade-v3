#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

DATA_DIR="${V3_DATA_DIR:-user_data/data/binance/futures}"
OUTPUT_DIR="${V3_RESEARCH_OUTPUT:-research_results/milestone-1}"
IMAGE="${V3_FREQTRADE_IMAGE:-freqtradeorg/freqtrade@sha256:50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486}"
HOST_GID="$(id -g)"

mkdir -p "$OUTPUT_DIR"
# Keep the image's uid 1000 so its Python packages remain accessible, while
# sharing the host user's primary group for narrowly scoped artifact writes.
chgrp "$HOST_GID" "$OUTPUT_DIR"
chmod 2770 "$OUTPUT_DIR"

docker run --rm \
  --entrypoint python \
  --user "1000:$HOST_GID" \
  -e V3_GENERATED_AT="${V3_GENERATED_AT:-}" \
  -v "$PROJECT_ROOT:/project" \
  -w /project \
  "$IMAGE" \
  scripts/run_walk_forward.py \
  --data-dir "$DATA_DIR" \
  --output "$OUTPUT_DIR"
