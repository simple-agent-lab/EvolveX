"""Expose complete per-case execution and verifier records."""

from evolve.frozen import sdk
from evolve.trace_analysis import AnalyzeBase
from library._shared.config import config_object, positive_int, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, {"history_cycles", "max_observations", "max_chars"})
    return {
        "history_cycles": positive_int(config, "history_cycles", 2),
        "max_observations": positive_int(config, "max_observations", 30),
        "max_chars": positive_int(config, "max_chars", 30_000),
    }


class ExecutionRecords(AnalyzeBase):
    operator = "execution_records"


if __name__ == "__main__":
    sdk.main(ExecutionRecords, validate_config=validate_config)
