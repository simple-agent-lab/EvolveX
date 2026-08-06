#!/bin/sh
set -eu
trap 'rm -rf /tmp/evolve-verifier-codex-home' EXIT

python3 /tests/evaluate.py
