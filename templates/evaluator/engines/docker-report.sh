# docker report.json evaluator template
test -f report.json || { printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"; exit 3; }
python3 evaluator/parse_score.py report.json > "$EVOLVE_RUN_DIR/score"
printf 'complete\n' > "$EVOLVE_RUN_DIR/status"
exit 0
