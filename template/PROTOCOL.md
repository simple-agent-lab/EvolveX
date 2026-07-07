# PROTOCOL.md — 算子协议(人 / LLM 可读版)

机器可读的权威定义在 `FROZEN/contracts/protocol.py`(接口是 mechanism,
实现才可进化;两者冲突时以 protocol.py 为准)。这份文档随谱系旅行,
M2 起注入 mutate 的 prompt:**改算子时,必须保持这里声明的接口。**

当前 `PROTOCOL_VERSION = 1`。

## 调用约定

每个算子是一个独立可执行脚本,跑在子进程里(崩溃隔离)。参数只有标量
flag,输出是 stdout 上的**单个 JSON 对象**。JSON 只是进程边界的序列化
格式,协议本身是 protocol.py 里的类型。

## 退出码

| code | 含义 | driver 的反应 |
|---|---|---|
| 0 | 成功,stdout 有一个 JSON 对象 | 继续 |
| 1 | 算子失败 | 废弃本代,循环继续 |
| 2 | 调用错误(argparse;含伪造 flag,如给 record 传 `--score`) | 废弃本代 |
| 3 | 能力属于后续里程碑(not wired) | 停循环,大声报错 |

## 每算子的接口

| 算子 | CLI | 输出必需键 | 可写(tracked 路径) |
|---|---|---|---|
| select | — | `parent: int`(必须是 archive 中的 valid_parent) | 无 |
| rollout | `--gen --parent` | `ok: bool, lane: "dev"` | 无 |
| mutate | `--gen --parent` | `note, predicted_fixes, used_insights, cost` | `candidate/`(M3+:`operators/ meta/ program.md`) |
| novelty | `--gen --parent` | `novelty: float, accept: bool` | 无 |
| gate | `--gen [--parent]` | `status: keep\|discard, valid_parent: bool` | 无 |
| record | `--gen [--parent\|--genesis] [--note]` | LedgerEntry 全部 21 键(schema v2) | 无 |
| reflect | `--gen` | `ops: list`(playbook delta,严禁整篇重写) | 无 |
| distill | — | `ok, manifest, sft, dpo`(manifest 每样本可溯源) | 无 |

**扩展规则:必需键封闭,额外键开放。** 算子可以进化出更丰富的输出
(放 `extras`,序列化时平铺),driver 只依赖必需键。加可选键、加新算子
随时可以;改必需键 = 人在循环外走正门(bump PROTOCOL_VERSION),
与 harness 版本化同一扇门。

## 文件系统约定(git 之外的状态)

- `runs/gen-<id>/` — 本代 scratch,任何算子可写;driver 会把每个算子的
  stdout 持久化成 `runs/gen-<id>/<name>.json`(可检视、可尸检)。
- `archive.jsonl` — 仅 append,仅经 record;score 等冻结字段仅来自
  `runs/gen-<id>/stamp.json`(不变量 ②)。
- `insights/` — 仅 reflect 写(delta 操作)。
- `FROZEN/` — **任何算子永远只读**。driver 在 mutation 前后做摘要比对,
  被改则回滚并废弃该代;contracts 同样校验。

## 公开环境变量

`HARNESS_STUB`(M0 假 harness 开关)· `EVOLVE_SEED`(可复现运行)·
`EVOLVE_SELECT_ALPHA`(parent-balancing 的 α)。其余 env 均为实现细节。

## 校验点(同一份 protocol.py 驱动)

1. **driver**:每次算子调用后校验输出类型(纵深防御)。
2. **oplib**:算子自己 emit 前校验(违反自己协议的算子立刻失败,
   不把垃圾喂给 driver)。
3. **contracts**(`FROZEN/contracts/run_contracts.py`):Tier-0 门,
   自指改动必须先过它;presence / CLI / 输出 / 写权限全部由
   OPERATORS registry 驱动,没有手写断言。
