"""Skeleton reflect operator template for custom playbook policies."""



from evolve.frozen import sdk
from evolve.frozen.interfaces import ReflectOperator, ReflectResult


class SkeletonReflect(ReflectOperator):
    def reflect(self, archive, ctx):
        # Fill in a playbook policy; this minimal default writes no insights.
        return ReflectResult(ops=[])


if __name__ == "__main__":
    sdk.main(SkeletonReflect)
