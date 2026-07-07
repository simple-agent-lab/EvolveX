# mutate 策略(与 operators/mutate.py 配对的 prose,可进化)

- 先读 dev feedback 的失败簇,变异要对着失败去,不要漫游。
- 每代必须给出 predicted_fixes(预测本次改动会修好哪些 task)——
  下一代 reflect 会核对,持续说错的方向要放弃。
- 引用 playbook insight 时如实记录 used_insights,信用回填靠它。
- 一次改一个假设。diff 越小,归因越干净。
- 永远不碰 FROZEN/;M3 前也不碰 operators/。
