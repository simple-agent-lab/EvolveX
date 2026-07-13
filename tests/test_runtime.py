import json

import pytest

from evolve.runtime import EvaluationPaused, RuntimeFingerprint, attempt_dir, current_epoch, mark_preflight


def test_attempt_paths_never_replace_prior_evidence(tmp_path) -> None:
    first = attempt_dir(
        tmp_path,
        epoch=0,
        purpose="candidate",
        generation="7",
        candidate_id="abc",
        attempt=1,
    )
    first.mkdir(parents=True)
    (first / "marker").write_text("first")

    second = attempt_dir(
        tmp_path,
        epoch=0,
        purpose="candidate",
        generation="7",
        candidate_id="abc",
        attempt=2,
    )

    assert first != second
    assert (first / "marker").read_text() == "first"
    with pytest.raises(FileExistsError, match="attempt already exists"):
        attempt_dir(
            tmp_path,
            epoch=0,
            purpose="candidate",
            generation="7",
            candidate_id="abc",
            attempt=1,
        )


def test_changed_capsule_digest_requires_new_epoch(tmp_path) -> None:
    old = RuntimeFingerprint("sha256:old", "eval", "tasks")
    new = RuntimeFingerprint("sha256:new", "eval", "tasks")
    mark_preflight(tmp_path, old, epoch=0)

    assert current_epoch(tmp_path, old) == 0
    with pytest.raises(EvaluationPaused, match="new evaluation epoch"):
        current_epoch(tmp_path, new)


def test_preflight_marker_is_small_and_readable(tmp_path) -> None:
    fingerprint = RuntimeFingerprint("sha256:capsule", "eval", "tasks")

    mark_preflight(tmp_path, fingerprint, epoch=3)

    payload = json.loads((tmp_path / "runs" / "runtime" / "preflight.json").read_text())
    assert payload == {"epoch": 3, "fingerprint": fingerprint.digest}


@pytest.mark.parametrize("value", ["../escape", "a/b", "", "."])
def test_attempt_identity_rejects_unsafe_path_components(tmp_path, value: str) -> None:
    with pytest.raises(ValueError, match="unsafe"):
        attempt_dir(
            tmp_path,
            epoch=0,
            purpose=value,
            generation="7",
            candidate_id="abc",
            attempt=1,
        )
