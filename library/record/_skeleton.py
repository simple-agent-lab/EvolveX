"""Skeleton record operator template for custom archive-annotation recipes."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import RecordOperator, RecordResult
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class SkeletonRecord(RecordOperator):
    def annotate(self, child, ctx):
        # Fill in archive annotations; this minimal default records only a note.
        return RecordResult(fields={"note": "fill in record annotations"})


if __name__ == "__main__":
    sdk.main(SkeletonRecord, validate_config=validate_config)
