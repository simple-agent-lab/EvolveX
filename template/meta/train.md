# train 策略(与 operators/distill.py + train/recipe.yaml 配对,M5+)

- 数据只从 dev 轨迹来,必须过 FROZEN/decontam 盖章 —— 这不是策略,是不变量。
- 任务级筛选:失败代里成功任务的轨迹照样是好数据。
- 近似轨迹每任务封顶,防数据分布坍缩到简单任务。
- 训练触发看平台期(best-ever 停滞 K 代),不要按代数硬训。
- checkpoint 是候选,不是产物:训完照常过 canonical eval,掉分就淘汰。
