"""Skeleton record operator template for custom archive-annotation recipes."""



from evolve.frozen import sdk
from evolve.frozen.interfaces import RecordOperator, RecordResult


class SkeletonRecord(RecordOperator):
    def annotate(self, child, ctx):
        # Fill in archive annotations; this minimal default records only a note.
        return RecordResult(fields={"note": "fill in record annotations"})


if __name__ == "__main__":
    sdk.main(SkeletonRecord)
