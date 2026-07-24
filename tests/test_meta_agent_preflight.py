"""Unit tests for the deterministic meta-agent image preflight core."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from evolve.meta_agent_preflight import CommandResult, PreflightCase, load_matrix, redact, run_static


def _case(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "name": "expanded-2.4.5",
        "image": "evolve/meta-agent:expanded-2.4.5",
        "expected_image_id": "sha256:" + "a" * 64,
        "miniswe_version": "2.4.5",
        "expanded_tools": True,
        "timeout_s": 120,
    }
    value.update(overrides)
    return value


def test_load_matrix_accepts_a_valid_three_case_matrix(tmp_path):
    matrix = {
        "cases": [
            _case(),
            _case(
                name="minimal-2.4.5",
                image="evolve/meta-agent:minimal-2.4.5",
                expected_image_id="sha256:" + "b" * 64,
                expanded_tools=False,
                timeout_s=30,
            ),
            _case(
                name="expanded-2.4.6",
                image="evolve/meta-agent:expanded-2.4.6",
                expected_image_id="sha256:" + "c" * 64,
                miniswe_version="2.4.6",
            ),
        ]
    }
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(matrix))

    cases = load_matrix(path)

    assert cases == (
        PreflightCase(**matrix["cases"][0]),
        PreflightCase(**matrix["cases"][1]),
        PreflightCase(**matrix["cases"][2]),
    )


def test_preflight_case_uses_the_default_timeout_when_matrix_omits_it():
    data = _case()
    data.pop("timeout_s")

    case = PreflightCase.from_dict(data)

    assert case.timeout_s == 120


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda case: case.pop("expected_image_id"), "expected_image_id"),
        (lambda case: case.update(timeout_s=121), "timeout_s must be between 1 and 120"),
        (lambda case: case.update(name="../escape"), "case name"),
        (lambda case: case.update(miniswe_version="latest"), "semantic version"),
    ],
)
def test_load_matrix_rejects_invalid_case(tmp_path, mutation, message):
    case = _case()
    mutation(case)
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps({"cases": [case]}))

    with pytest.raises(ValueError, match=message):
        load_matrix(path)


def test_load_matrix_rejects_an_empty_or_duplicate_matrix(tmp_path):
    path = tmp_path / "matrix.json"
    path.write_text('{"cases": []}')

    with pytest.raises(ValueError, match="nonempty"):
        load_matrix(path)

    path.write_text(json.dumps({"cases": [_case(), _case()]}))
    with pytest.raises(ValueError, match="duplicate"):
        load_matrix(path)


def test_redact_removes_environment_secrets_and_common_credentials():
    environment = {"OPENAI_API_KEY": "secret-value", "PROXY_PASSWORD": "proxy-secret"}

    redacted = redact(
        "OPENAI_API_KEY=secret-value Authorization: Bearer abc.def "
        "password: hunter2 https://alice:in-url@example.test/path proxy-secret",
        environment,
    )

    for secret in ("secret-value", "proxy-secret", "abc.def", "hunter2", "alice", "in-url"):
        assert secret not in redacted
    assert "[REDACTED]" in redacted


def test_redact_leaves_ordinary_diagnostics_unchanged():
    assert redact("missing executable: rg", {}) == "missing executable: rg"


REQUIRED_TOOLS = (Path(__file__).parents[1] / "containers" / "meta-agent" / "required-tools.txt").read_text().splitlines()


def _probe(case: PreflightCase, commands: list[str]) -> str:
    return json.dumps(
        {
            "miniswe_version": case.miniswe_version,
            "python_version": "3.12.10",
            "uv_version": "0.7.13",
            "commands": commands,
            "app_exists": True,
            "app_writable": True,
        }
    )


class StaticRunner:
    def __init__(self, cases: tuple[PreflightCase, ...], *, timeout_case: str | None = None) -> None:
        self.cases = {case.image: case for case in cases}
        self.timeout_case = timeout_case
        self.calls: list[tuple[str, ...]] = []
        self.entered = 0
        self.both_started = asyncio.Event()

    async def __call__(
        self,
        argv: tuple[str, ...],
        timeout_s: float,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        assert isinstance(argv, tuple)
        assert env is None
        self.calls.append(argv)
        image = argv[3] if argv[:3] == ("docker", "image", "inspect") else argv[5]
        case = self.cases[image]
        if argv[:3] == ("docker", "image", "inspect"):
            self.entered += 1
            if self.entered == len(self.cases):
                self.both_started.set()
            await asyncio.wait_for(self.both_started.wait(), timeout=0.1)
            if case.name == self.timeout_case:
                raise TimeoutError("timed out")
            return CommandResult(
                0,
                json.dumps({"Id": case.expected_image_id, "Config": {"Labels": {}}}),
                "",
                0.2,
            )
        commands = (
            REQUIRED_TOOLS
            if case.expanded_tools
            else [tool for tool in REQUIRED_TOOLS if tool not in {"jq", "rg", "rsync", "tree"}]
        )
        return CommandResult(0, _probe(case, commands), "", 0.3)


def test_run_static_checks_image_contracts_concurrently_with_tuple_argv():
    cases = (
        PreflightCase(**_case()),
        PreflightCase(
            **_case(
                name="minimal-2.4.5",
                image="evolve/meta-agent:minimal-2.4.5",
                expected_image_id="sha256:" + "b" * 64,
                expanded_tools=False,
            )
        ),
    )
    runner = StaticRunner(cases)

    result = asyncio.run(run_static(cases, runner))

    assert runner.entered == 2
    assert result["passed"] is True
    assert result["elapsed_s"] == 0.5
    assert [image["name"] for image in result["images"]] == [case.name for case in cases]
    assert all(image["passed"] for image in result["images"])
    assert runner.calls[0] == ("docker", "image", "inspect", cases[0].image, "--format", "{{json .}}")
    assert runner.calls[1] == ("docker", "image", "inspect", cases[1].image, "--format", "{{json .}}")
    assert all(isinstance(call, tuple) for call in runner.calls)
    assert any(
        call == ("docker", "run", "--rm", "--entrypoint", "bash", cases[0].image, "-lc", call[-1])
        for call in runner.calls
        if call[:3] == ("docker", "run", "--rm")
    )


def test_run_static_reports_image_contract_failures_without_cancelling_siblings():
    passing = PreflightCase(**_case())
    timed_out = PreflightCase(
        **_case(
            name="timed-out",
            image="evolve/meta-agent:timed-out",
            expected_image_id="sha256:" + "d" * 64,
        )
    )
    runner = StaticRunner((passing, timed_out), timeout_case=timed_out.name)

    result = asyncio.run(run_static((passing, timed_out), runner))

    assert result["passed"] is False
    assert result["images"][0]["passed"] is True
    assert result["images"][1]["failure_boundary"] == "image_contract"
    assert "timeout" in result["images"][1]["failures"][0]
