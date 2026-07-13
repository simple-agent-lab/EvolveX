# Notes

The executable baseline uses Harbor train failures as adversarial evidence and
the canonical non-regression gate as rollback. More sophisticated adversary
generation can replace `operators/rollout.py` without changing the frozen
train/gate/sealed contract.
