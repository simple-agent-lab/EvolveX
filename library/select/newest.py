"""Newest parent selection chooses the youngest valid archive parent.

It is a small proof variant written from PROTOCOL.md and the select skeleton.
"""

from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, SelectOperator, SelectResult


def _generation_key(row: dict[str, object]) -> int:
    genid = str(row.get("genid", ""))
    head = genid.split("-", 1)[0]
    return int(head) if head.isdigit() else -1


class NewestSelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid parents")
        chosen = max(parents, key=_generation_key)
        return SelectResult(parents=[str(chosen["genid"])])


if __name__ == "__main__":
    sdk.main(NewestSelect)
