"""Skeleton gate operator template for custom child-acceptance recipes."""



from evolve.frozen import sdk
from evolve.frozen.interfaces import GateOperator, GateResult


class SkeletonGate(GateOperator):
    def decide(self, child, parent, ctx):
        # Fill in acceptance policy; this minimal default rejects until customized.
        return GateResult(decision="reject", reason="fill in gate decision policy")


if __name__ == "__main__":
    sdk.main(SkeletonGate)
