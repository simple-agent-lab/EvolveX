#!/usr/bin/env bash
# Instantiate a meta-workspace from template/ with its own git repo (git-as-archive).
# The workspace git is the evolution archive: commit = candidate, tag gen/<id>.
set -euo pipefail

TARGET="${1:?usage: init-workspace.sh <dir>}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../template" && pwd)"

if [[ -e "$TARGET" && -n "$(ls -A "$TARGET" 2>/dev/null)" ]]; then
  echo "refusing to init into non-empty dir: $TARGET" >&2
  exit 1
fi

mkdir -p "$TARGET"
cp -R "$SRC/." "$TARGET/"
cd "$TARGET"

# untracked state dirs (survive git reset — reset-protected by being outside git)
mkdir -p runs manifests ckpts insights
[[ -f insights/playbook.jsonl ]] || : > insights/playbook.jsonl

chmod +x loop.sh driver.py FROZEN/*.sh operators/*.sh operators/*.py operators/engines/*.sh \
         FROZEN/*.py FROZEN/contracts/*.py 2>/dev/null || true

git init -q -b main
git config user.name "evolve"
git config user.email "evolve@workspace.local"
git add -A
git commit -qm "genesis"
git tag gen/0

echo "workspace ready: $TARGET (tag gen/0)"
