"""Random parent selection samples uniformly from valid parents.

It is the exploration baseline recipe for population search.
"""



from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, SelectOperator, SelectResult


class RandomSelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid parents")
        chosen = ctx.rng.choice(parents)
        return SelectResult(parents=[str(chosen["genid"])])


if __name__ == "__main__":
    sdk.main(RandomSelect)
