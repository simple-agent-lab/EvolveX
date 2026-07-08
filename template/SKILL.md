# SKILL.md — 如何操作这个进化 workspace(给 agent 的手册)

你降落在一个 evolve-agent workspace 里。这里在进化一个 candidate(代码 +
prompt + 配置,可能还有权重指针),用一把冻结的尺(FROZEN/eval.sh)逐代打分,
git 是谱系档案(commit = 候选,tag `gen/<id>`),archive.jsonl 是账本。
**所有操作走 `./evolve`,先跑 `./evolve status` 看现状。**

## 黄金路径(你作为 mutator 工作一代)

```bash
./evolve status              # 现状:冠军、最近几代、有没有挂起的东西
./evolve gen begin           # 机制侧做完 select/checkout/rollout,
                             # 给你打印一份变异简报:失败簇 + 相关经验 + 允许改哪里
⟨用你自己的编辑工具改 candidate/(或 operators/ meta/ program.md config.json)⟩
./evolve gen finish --note "改了什么、为什么" \
    --predict task_3         # 你预测会修好的任务(下一代会核对,别乱说)
                             # --used-insight <id> 如实报告你参考了哪条经验
```

finish 会替你走完 novelty 查重、自指准入门、冻结评测盖章、gate、记账、反思。
改砸了或想放弃:`./evolve gen abort`。想让循环自己跑:`./evolve run 10`。

## 你必须遵守的(五条不变量,机制会强制,别试)

1. **FROZEN/ 只读。** 改了会被摘要比对抓住并回滚。想改评测协议 → 写提案留给人。
2. **分数不由你报。** score/task_vector 由 FROZEN 盖章进账本;record 没有分数参数。
3. **best-ever 由冻结规则重算**,换冠军要复评。你 gate 得再松也污染不了它。
4. **训练数据永不含 gate/sealed 任务**,decontam 无章引擎拒收。
5. **checkpoint 只经 canonical eval 入档。**

你的可写范围就是变异范围:`candidate/ operators/ meta/ program.md config.json`。
改 `operators/` = 自指,会触发合同测试 + meta-eval 回放准入,不过关只回滚算子部分。
**不要手改 `archive.jsonl` / `best_ever.json`** —— `./evolve verify` 会重算揭穿,
人和 CI 都会跑它。

## 出问题了

- 任何命令报错:**先读报错**,里面写了下一步命令。
- 状态混乱 / 上个会话崩了:`./evolve doctor`(检测并修复中断态)。
- 怀疑账本不对:`./evolve verify`。
- 看某一代到底发生了什么:`./evolve show <gen>`。

## 更深的资料(按需读,别全读)

- `PROTOCOL.md` — 算子接口/写权限/退出码的权威定义(改算子前必读)
- `program.md` — 循环编排规则;`meta/*.md` — 各算子的策略 prose
- `./evolve report` — 多样性健康度 + 算子改动的谱系归因
- 人类专属面:`./evolve sealed <gen>`(封存测试)、`./evolve audit`(隔离区)、
  FROZEN 版本升级 —— 这些不属于你。
