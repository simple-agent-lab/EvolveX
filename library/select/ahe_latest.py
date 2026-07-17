"""Select the newest structurally valid AHE generation, regardless of score."""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, SelectOperator, SelectResult


def _generation_key(row: dict[str, object]) -> tuple[int, str]:
    genid = str(row.get("genid", ""))
    head = genid.split("-", 1)[0]
    return (int(head) if head.isdigit() else -1, genid)


class AheLatestSelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid AHE parents")
        return SelectResult(parents=[str(max(parents, key=_generation_key)["genid"])])


if __name__ == "__main__":
    sdk.main(AheLatestSelect)
