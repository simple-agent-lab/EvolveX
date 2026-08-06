#!/bin/sh
set -eu

run_dir=${1:?run directory is required}
env_file=${2:?runtime environment output is required}

# Docker and other isolated environments retain their existing image-provided
# renderer. Only Harbor's in-process LocalEnvironment needs a host toolchain.
case "${EVOLVE_HARBOR_ENVIRONMENT:-docker}" in
  *:LocalEnvironment)
    python3 evaluator/prepare_poster_runtime.py \
      --cache-root "$EVOLVE_WORKSPACE/runs/runtime/paper-poster-svg" \
      --env-out "$env_file" \
      --receipt-out "$run_dir/poster-runtime.json"
    ;;
  *)
    : > "$env_file"
    ;;
esac
