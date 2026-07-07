# select 策略(与 operators/select.py 配对的 prose,可进化)

默认 parent-balancing:高分该被偏爱,但一个冠军的子孙不该淹没种群
(p ∝ score_norm × 1/(1+offspring)^α)。改这份 prose 或换变体前先想:
当前瓶颈是「不够 exploit」还是「多样性坍缩」?看账本里 valid_parent
集合的 task_vector 平均 pairwise 距离再动手。
