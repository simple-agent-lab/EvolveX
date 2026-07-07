# rollout 策略(与 operators/rollout.py 配对的 prose,可进化)

dev lane 是形成性的:目的是给 mutate 可瞄准的反馈,不是打分。
默认 failure-focused,预算封顶。采样越省越好 —— 但 dev 轨迹同时是
未来训练数据(M5 distill)的唯一来源,别省到没有轨迹可蒸。
永远只跑 train(dev) split;gate/sealed split 不属于这条 lane。
