# train.py evaluator template producing negative bits-per-byte (-bpb)
test -f train.py || { printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"; exit 3; }
python3 train.py > "$EVOLVE_RUN_DIR/train.log" || { printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"; exit 3; }
printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"
exit 3
