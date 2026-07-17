"""Accept canonically evaluated AHE children with a matching manifest artifact."""

import json

from evolve.frozen import sdk
from evolve.frozen.interfaces import GateOperator, GateResult, OperatorContext, Row


class AheArtifactValidGate(GateOperator):
    def decide(self, child: Row, parent: Row | None, ctx: OperatorContext) -> GateResult:
        if child.get("outcome") != "benchmark_complete" or child.get("selection_eligible") is not True:
            return GateResult(decision="reject", reason="canonical evaluation is not parent-eligible")
        path = ctx.run_dir / "meta_agent" / "change_manifest.json"
        try:
            manifest = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return GateResult(decision="reject", reason="required AHE manifest is missing or malformed")
        identity_ok = (
            isinstance(manifest, dict)
            and str(manifest.get("iteration")) == ctx.genid
            and isinstance(manifest.get("changes"), list)
            and bool(manifest["changes"])
        )
        return GateResult(
            decision="accept" if identity_ok else "reject",
            reason=(
                "validated AHE manifest and canonical evaluation" if identity_ok else "AHE manifest identity mismatch"
            ),
        )


if __name__ == "__main__":
    sdk.main(AheArtifactValidGate)
