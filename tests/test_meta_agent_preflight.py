"""Unit tests for the deterministic meta-agent image preflight core."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

import evolve.meta_agent_preflight as preflight
from evolve.meta_agent_preflight import (
    STATIC_PROBE,
    CommandResult,
    PreflightCase,
    inspect_image,
    load_matrix,
    redact,
    run_static,
)


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


def _probe(case: PreflightCase, commands: Sequence[str], *, miniswe_version: str | None = None) -> str:
    return json.dumps(
        {
            "miniswe_version": miniswe_version or case.miniswe_version,
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
        self.timeouts: list[float] = []
        self.environments: list[Mapping[str, str] | None] = []
        self.entered = 0
        self.both_started = asyncio.Event()

    async def __call__(
        self,
        argv: tuple[str, ...],
        timeout_s: float,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        assert isinstance(argv, tuple)
        self.calls.append(argv)
        self.timeouts.append(timeout_s)
        self.environments.append(env)
        image = argv[3] if argv[:3] == ("docker", "image", "inspect") else argv[5]
        case = self.cases[image]
        if argv[:3] == ("docker", "image", "inspect"):
            self.entered += 1
            if self.entered == len(self.cases):
                self.both_started.set()
            await asyncio.wait_for(self.both_started.wait(), timeout=0.1)
            if case.name == self.timeout_case:
                await asyncio.sleep(0.01)
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


class FixedRunner:
    def __init__(self, *results: CommandResult) -> None:
        self.results = list(results)

    async def __call__(
        self,
        argv: tuple[str, ...],
        timeout_s: float,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        assert isinstance(argv, tuple)
        assert 0 < timeout_s <= 15
        return self.results.pop(0)


class OSErrorStaticRunner(StaticRunner):
    async def __call__(
        self,
        argv: tuple[str, ...],
        timeout_s: float,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        result = await super().__call__(argv, timeout_s, env)
        image = argv[3] if argv[:3] == ("docker", "image", "inspect") else argv[5]
        if image == "evolve/meta-agent:missing-docker":
            await asyncio.sleep(0.01)
            raise FileNotFoundError("docker diagnostic OPENAI_API_KEY=runner-secret")
        return result


class DeadlineClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class DeadlineRunner:
    def __init__(self, case: PreflightCase, clock: DeadlineClock, inspection_elapsed_s: float) -> None:
        self.case = case
        self.clock = clock
        self.inspection_elapsed_s = inspection_elapsed_s
        self.calls: list[tuple[tuple[str, ...], float]] = []

    async def __call__(
        self,
        argv: tuple[str, ...],
        timeout_s: float,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        self.calls.append((argv, timeout_s))
        if argv[:3] == ("docker", "image", "inspect"):
            self.clock.value += self.inspection_elapsed_s
            return CommandResult(0, json.dumps({"Id": self.case.expected_image_id}), "", self.inspection_elapsed_s)
        return CommandResult(0, _probe(self.case, REQUIRED_TOOLS), "", 0.1)


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
    assert all(0 < timeout <= 15 for timeout in runner.timeouts)
    assert any(
        call == ("docker", "run", "--rm", "--entrypoint", "bash", cases[0].image, "-lc", call[-1])
        for call in runner.calls
        if call[:3] == ("docker", "run", "--rm")
    )


def test_inspect_image_uses_one_deadline_and_skips_the_probe_after_it_expires(monkeypatch):
    case = PreflightCase(**_case())
    remaining_clock = DeadlineClock()
    monkeypatch.setattr(preflight, "monotonic", remaining_clock)
    remaining_runner = DeadlineRunner(case, remaining_clock, inspection_elapsed_s=11)

    remaining = asyncio.run(inspect_image(case, remaining_runner))

    assert remaining["passed"] is True
    assert [timeout for _, timeout in remaining_runner.calls] == [15, 4]

    expired_clock = DeadlineClock()
    monkeypatch.setattr(preflight, "monotonic", expired_clock)
    expired_runner = DeadlineRunner(case, expired_clock, inspection_elapsed_s=15)

    expired = asyncio.run(inspect_image(case, expired_runner))

    assert expired["failure_boundary"] == "image_contract"
    assert "timeout" in expired["failures"][0]
    assert len(expired_runner.calls) == 1


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
    assert result["images"][1]["elapsed_s"] >= 0.01


def test_run_static_turns_os_errors_into_redacted_image_contract_failures_without_cancelling_siblings():
    passing = PreflightCase(**_case())
    missing = PreflightCase(
        **_case(
            name="missing-docker",
            image="evolve/meta-agent:missing-docker",
            expected_image_id="sha256:" + "d" * 64,
        )
    )
    runner = OSErrorStaticRunner((passing, missing))

    result = asyncio.run(run_static((passing, missing), runner, {"OPENAI_API_KEY": "runner-secret"}))

    assert result["images"][0]["passed"] is True
    assert result["images"][1]["failure_boundary"] == "image_contract"
    assert "runner-secret" not in result["images"][1]["failures"][0]
    assert result["images"][1]["elapsed_s"] >= 0.01


def test_inspect_image_redacts_configured_secrets_from_nonzero_stdout_and_stderr():
    case = PreflightCase(**_case())
    runner = FixedRunner(CommandResult(1, "stdout secret-value", "stderr secret-value", 0.2))

    result = asyncio.run(inspect_image(case, runner, {"OPENAI_API_KEY": "secret-value"}))

    assert result["failure_boundary"] == "image_contract"
    assert "secret-value" not in result["failures"][0]
    assert "[REDACTED]" in result["failures"][0]


def test_inspect_image_preserves_the_observed_miniswe_version_on_mismatch():
    case = PreflightCase(**_case())
    runner = FixedRunner(
        CommandResult(0, json.dumps({"Id": case.expected_image_id}), "", 0.2),
        CommandResult(0, _probe(case, REQUIRED_TOOLS, miniswe_version="2.4.6"), "", 0.3),
    )

    result = asyncio.run(inspect_image(case, runner))

    assert result["failure_boundary"] == "image_contract"
    assert result["observed_miniswe_version"] == "2.4.6"


def test_inspect_image_rejects_missing_required_tool_malformed_probe_and_nonzero_probe():
    case = PreflightCase(**_case())
    inspection = CommandResult(0, json.dumps({"Id": case.expected_image_id}), "", 0.2)
    missing_tool = asyncio.run(
        inspect_image(case, FixedRunner(inspection, CommandResult(0, _probe(case, REQUIRED_TOOLS[:-1]), "", 0.3)))
    )
    malformed = asyncio.run(inspect_image(case, FixedRunner(inspection, CommandResult(0, "not-json", "", 0.3))))
    nonzero = asyncio.run(inspect_image(case, FixedRunner(inspection, CommandResult(1, "stdout", "stderr", 0.3))))

    assert "mini-swe-agent" in missing_tool["failures"][0]
    assert "JSON object" in malformed["failures"][0]
    assert "static probe failed: stdout\nstderr" == nonzero["failures"][0]
    assert all(tool in STATIC_PROBE for tool in REQUIRED_TOOLS)
