# program.md — 循环规则(agent 模式的编排说明书)

driver 模式下这份文件只是文档;agent 模式下,编排 agent 读它决定何时调哪个算子。

## 每代的标准节拍(与 loop.sh 一致)

1. `operators/select.py` 从 archive.jsonl 选父代(默认 parent-balancing)。
2. `git checkout gen/<P>` 取出父代快照(代码 + 按 weights_ref 恢复权重)。
3. `operators/rollout.py` 跑 dev 采样,产反馈(advisory,永不进 canonical)。
4. `operators/mutate.py` 读反馈 + meta/mutate.md + playbook top-K,改 candidate(M3+ 可含 operators/)。
5. `operators/novelty.py` 变异查重,近重复打回重变异(≤2 次)。
6. `git commit` + `git tag gen/<id>`。
7. `FROZEN/eval.sh` → `FROZEN/stamp.sh`:canonical 打分并盖章(score / task_vector / CI)。
8. `operators/gate.py` 判 status / valid_parent。
9. `operators/record.py` append 账本(冻结字段只从 stamp.json 读)。
10. `operators/reflect.py` 证伪核对 + playbook 增量更新。

## 硬规则(agent 也不许绕)

- FROZEN/ 只读。改了会被 driver 的 frozen guard 回滚并废弃该代。
- score / task_vector / best-ever 永远以 FROZEN 盖章为准,不接受任何一方传参。
- diff 触及 operators/ 时必须先过 FROZEN/contracts 合同测试与 meta_eval 准入门(M3 起强制)。
- 训练数据只能来自 dev lane 轨迹,须带 decontam_stamp(M5 起强制)。

## 外环触发(M7 起)

best-ever 停滞 K 代 / distill 样本超阈值 / 固定节奏 → 异步派训练 job;
checkpoint 作为新 gen 排队过 canonical eval,照常 gate 入档。

## 停机条件

target score | max_iter | budget 任一命中。
