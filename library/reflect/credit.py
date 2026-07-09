"""Credit-backfill reflect: turn verified fixes into playbook insights.

Reads the ledger and, for every generation whose predictions were verified
(`verified_fixes`), credits the mutation's note as an insight. Emits full-state
op lines (append-only; folding by id gives current state) so an insight's credit
accumulates across the lineage — the memory a future mutator can consult and
report as `used_insights`. Never rewrites the playbook.
"""

# ruff: noqa: E402

import hashlib
import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, ReflectOperator, ReflectResult


class CreditReflect(ReflectOperator):
    def reflect(self, archive, ctx: OperatorContext) -> ReflectResult:
        credit: dict[str, dict] = {}
        for row in archive.rows():
            verified = row.get("verified_fixes") or []
            note = (row.get("note") or "").strip()
            if not verified or not note:
                continue
            entry = credit.setdefault(note[:120], {"credit": 0, "gens": []})
            entry["credit"] += len(verified)
            entry["gens"].append(row.get("genid"))
        ops = [
            {
                "id": "ins-" + hashlib.sha1(note.encode()).hexdigest()[:10],
                "text": note,
                "status": "active",
                "credit": info["credit"],
                "gens": info["gens"],
            }
            for note, info in credit.items()
        ]
        return ReflectResult(ops=ops)


if __name__ == "__main__":
    sdk.main(CreditReflect)
