"""Credit-backfill reflect: turn verified fixes into playbook insights.

Reads the ledger and, for every generation whose predictions were verified
(`verified_fixes`), credits the candidate note as an insight. Emits full-state
op lines (append-only; folding by id gives current state) so an insight's credit
accumulates across the lineage — the memory a future mutate operator can consult and
report as `used_insights`. Never rewrites the playbook.
"""

import hashlib

from evolve.frozen import sdk
from evolve.frozen.config import Config
from evolve.frozen.interfaces import OperatorContext, ReflectOperator, ReflectResult

CONFIG = Config({})


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
    sdk.main(CreditReflect, config_schema=CONFIG)
