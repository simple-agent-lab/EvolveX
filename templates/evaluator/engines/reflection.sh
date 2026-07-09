# reflection evaluator template for solve-task plus reflection traces
test -f reflection.md || { printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"; exit 3; }
printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"
exit 3
