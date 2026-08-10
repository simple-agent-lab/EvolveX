"""Skeleton select operator template for custom parent-selection recipes."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import SelectOperator, SelectResult
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, {"seed"})
    seed = config.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    return {"seed": seed}


def _generation_key(row):
    genid = str(row.get("genid", ""))
    head = genid.split("-", 1)[0]
    return int(head) if head.isdigit() else -1


class SkeletonSelect(SelectOperator):
    def pick(self, archive, ctx):
        # Fill in your selection policy; this minimal default picks the newest valid parent.
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid parents")
        chosen = max(parents, key=_generation_key)
        return SelectResult(parents=[str(chosen["genid"])])


if __name__ == "__main__":
    sdk.main(SkeletonSelect, validate_config=validate_config)
