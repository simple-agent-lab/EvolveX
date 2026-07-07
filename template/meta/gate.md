# gate 策略(与 operators/gate.py 配对的 prose,可进化)

默认 open:非 crash 即 valid_parent —— 开放式种群,把淘汰交给 select 的
权重而不是硬闸。要收紧(hillclimb / elitist+rollback)前记住:gate 只能
污染种群,污染不了 fitness(score 与 best-ever 由冻结环节守着),所以
宁可松,不可假装严。
