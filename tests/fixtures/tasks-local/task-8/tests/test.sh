#!/bin/sh
expected="9"
actual=$(cat "$HARBOR_WORKDIR/answer.txt" 2>/dev/null | tr -d "[:space:]")
mkdir -p "$HARBOR_LOGS_DIR/verifier"
if [ "$actual" = "$expected" ]; then
  printf '1\n' > "$HARBOR_LOGS_DIR/verifier/reward.txt"
else
  printf '0\n' > "$HARBOR_LOGS_DIR/verifier/reward.txt"
fi
