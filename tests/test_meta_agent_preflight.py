"""Unit tests for the deterministic meta-agent image preflight core."""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

import evolve.meta_agent_preflight as preflight
from evolve.meta_agent_preflight import (
    STATIC_PROBE,
    CommandResult,
    PreflightCase,
    create_synthetic_workspace,
    inspect_image,
    load_matrix,
    redact,
    run_live,
    run_live_case,
    run_preflight,
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


@pytest.mark.parametrize(("require_rg", "expects_rg"), [(False, False), (True, True)])
def test_create_synthetic_workspace(tmp_path: Path, require_rg: bool, expects_rg: bool):
    workspace = create_synthetic_workspace(tmp_path / ("expanded" if require_rg else "minimal"), require_rg=require_rg)

    assert (workspace / "target" / "value.py").read_text() == "VALUE = 1\n"
    assert "VALUE == 2" in (workspace / "check.py").read_text()
    prompt = (workspace / "prompt.md").read_text()
    assert "Python" in prompt
    assert ("This task requires Python and rg." in prompt) is expects_rg
    assert "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in prompt
    assert not (workspace / "changed.json").exists()


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
    assert "if completed.returncode and not match:" in STATIC_PROBE


class LiveRunner:
    def __init__(
        self,
        outcome: str = "valid",
        *,
        outcomes_by_case: Mapping[str, str] | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self.outcome = outcome
        self.outcomes_by_case = outcomes_by_case or {}
        self.delay_s = delay_s
        self.calls: list[tuple[str, ...]] = []
        self.environments: list[Mapping[str, str] | None] = []
        self.entered = 0
        self.all_entered = asyncio.Event()
        self.expected_entries = 1

    async def __call__(
        self,
        argv: tuple[str, ...],
        timeout_s: float,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        self.calls.append(argv)
        self.environments.append(env)
        if argv[:2] == ("docker", "stop"):
            return CommandResult(0, "", "", 0.0)
        assert argv[:2] == ("docker", "run")
        container_name = next(part for part in argv if part.startswith("evolve-preflight-"))
        outcome = next(
            (value for name, value in self.outcomes_by_case.items() if f"evolve-preflight-{name}-" in container_name),
            self.outcome,
        )
        self.entered += 1
        if self.entered == self.expected_entries:
            self.all_entered.set()
        await self.all_entered.wait()
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if outcome == "RepeatedFormatError":
            return CommandResult(1, "RepeatedFormatError", "", self.delay_s)
        if outcome == "finish_reason=length":
            return CommandResult(1, "finish_reason=length", "", self.delay_s)
        if outcome == "agent process timeout":
            raise TimeoutError("agent process timeout")

        mounts = [part for part in argv if part.endswith(":/app/task/workspace") or part.endswith(":/app/task/output")]
        workspace = Path(next(part for part in mounts if part.endswith(":/app/task/workspace")).removesuffix(":/app/task/workspace"))
        case_dir = Path(next(part for part in mounts if part.endswith(":/app/task/output")).removesuffix(":/app/task/output"))
        if outcome != "Submitted without changed.json":
            (workspace / "changed.json").write_text('["target/value.py"]')
        if outcome not in {"check.py failed", "no git diff"}:
            (workspace / "target" / "value.py").write_text("VALUE = 2\n")
        if outcome == "no git diff":
            (workspace / "target" / "value.py").write_text("VALUE = 2\n")
            subprocess.run(
                ("git", "add", "target/value.py"), cwd=workspace, check=True, capture_output=True, text=True
            )
            subprocess.run(
                (
                    "git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "--quiet", "-m", "agent committed unexpectedly",
                ),
                cwd=workspace,
                check=True,
                capture_output=True,
                text=True,
            )
        (case_dir / "trajectory.json").write_text(
            json.dumps(
                {
                    "info": {
                        "config": {
                            "model": {
                                "model_kwargs": {
                                    "max_output_tokens": 64000,
                                    "include": ["reasoning.encrypted_content"],
                                    "reasoning": {"effort": "low"},
                                }
                            }
                        }
                    },
                    "messages": [
                        {
                            "role": "assistant",
                            "output": [{"type": "function_call", "name": "shell"}],
                        },
                        {"role": "exit", "extra": {"exit_status": "Submitted"}},
                    ],
                }
            )
        )
        return CommandResult(0, "model output", "", self.delay_s)


@pytest.mark.parametrize(
    ("outcome", "boundary"),
    [
        ("RepeatedFormatError", "model_protocol"),
        ("finish_reason=length", "model_protocol"),
        ("Submitted without changed.json", "artifact_import"),
        ("check.py failed", "verification"),
        ("no git diff", "workspace_edit"),
        ("agent process timeout", "agent_startup"),
    ],
)
def test_run_live_case_classifies_the_first_failed_protocol_boundary(tmp_path: Path, outcome: str, boundary: str):
    case = PreflightCase(**_case(name="case-" + boundary, timeout_s=1))

    result = asyncio.run(run_live_case(case, tmp_path / "out", LiveRunner(outcome), {}))

    assert result["passed"] is False
    assert result["failure_boundary"] == boundary
    assert (tmp_path / "out" / "cases" / case.name / "case.json").is_file()


def test_run_live_case_retains_a_valid_redacted_submission(tmp_path: Path):
    case = PreflightCase(**_case(name="valid-live"))
    runner = LiveRunner()

    result = asyncio.run(
        run_live_case(
            case,
            tmp_path / "out",
            runner,
            {"OPENAI_API_KEY": "do-not-retain", "OPENAI_BASE_URL": "https://model.test", "UNRELATED": "drop-me"},
        )
    )

    assert result["passed"] is True
    assert result["image_id"] == case.expected_image_id
    assert result["effective_model_config"]["max_output_tokens"] == 64000
    assert result["tool_calls"] == [{"type": "function_call", "name": "shell"}]
    assert result["changed_paths"] == ["target/value.py"]
    assert result["patch_bytes"] > 0
    assert set(result["logs"]) == {"stdout", "stderr", "trajectory", "patch", "config"}
    assert "do-not-retain" not in (tmp_path / "out" / "cases" / case.name / "stdout.log").read_text()
    assert runner.environments[0] == {
        "MSWEA_CONFIGURED": "true",
        "OPENAI_API_KEY": "do-not-retain",
        "OPENAI_BASE_URL": "https://model.test",
    }
    command = runner.calls[0]
    assert command[0:2] == ("docker", "run")
    assert "-w" in command and command[command.index("-w") + 1] == "/app/task/workspace"
    assert command[-17:] == (
        "python",
        "/app/task/output/runner.py",
        "--yolo",
        "--model=openai/gpt-5.4-2026-03-05",
        "--task-file=/app/task/workspace/prompt.md",
        "--output=/app/task/output/trajectory.json",
        "--cost-limit",
        "0",
        "-c",
        "mini",
        "-c",
        "model.model_class=litellm_response",
        "-c",
        "model.model_kwargs.reasoning.effort=low",
        "-c",
        "/app/task/output/responses.yaml",
        "--exit-immediately",
    )
    assert "do-not-retain" not in " ".join(command)
    assert any(part.startswith("evolve-preflight-valid-live-") for part in command)
    case_dir = tmp_path / "out" / "cases" / case.name
    config = json.loads((case_dir / "responses.yaml").read_text())
    assert config == {
        "model": {
            "model_kwargs": {
                "max_output_tokens": 64000,
                "include": ["reasoning.encrypted_content"],
                "prompt_cache_key": "evolve-preflight-valid-live",
                "extra_headers": {"extra": '{"session_id": "evolve-preflight-valid-live"}'},
            }
        }
    }
    shim = (case_dir / "runner.py").read_text()
    assert "mini-swe-agent" in shim
    assert "--task-file=" in shim
    assert "os.execv" in shim


def test_run_live_runs_cases_concurrently_and_keeps_siblings_after_a_timeout(tmp_path: Path):
    cases = tuple(PreflightCase(**_case(name=f"case-{index}", timeout_s=1)) for index in range(3))
    runner = LiveRunner(outcomes_by_case={"case-1": "agent process timeout"}, delay_s=0.08)
    runner.expected_entries = len(cases)
    started = preflight.monotonic()
    result = asyncio.run(run_live(cases, tmp_path / "out", runner, {}))

    assert runner.entered == 3
    assert preflight.monotonic() - started < 0.35
    assert result["passed"] is False
    assert [case_result["passed"] for case_result in result["cases"]] == [True, False, True]


def test_run_live_case_shares_one_deadline_with_local_verification(tmp_path: Path, monkeypatch):
    case = PreflightCase(**_case(name="deadline", timeout_s=1))
    clock = DeadlineClock()
    runner = LiveRunner()

    async def advance_deadline(argv, timeout_s, env=None):
        result = await runner(argv, timeout_s, env)
        clock.value = 1.0
        return result

    async def unexpected_host_command(argv, cwd, timeout_s):
        raise AssertionError(f"host command started after deadline: {argv}")

    monkeypatch.setattr(preflight, "monotonic", clock)
    monkeypatch.setattr(preflight, "_host_command", unexpected_host_command)

    result = asyncio.run(run_live_case(case, tmp_path / "out", advance_deadline, {}))

    assert result["passed"] is False
    assert result["failure_boundary"] == "verification"
    assert "timeout" in result["failures"][0].lower()


def test_run_preflight_static_failure_skips_live_and_writes_redacted_report(tmp_path: Path, monkeypatch):
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"cases": [_case(name="z-case"), _case(name="a-case")]}))
    live_called = False

    async def fake_static(cases, runner, environment=None):
        return {
            "passed": False,
            "elapsed_s": 1.23456,
            "images": [
                {
                    "name": case.name,
                    "passed": case.name != "z-case",
                    "failures": ["secret-value"],
                }
                for case in cases
            ],
        }

    async def fake_live(*args, **kwargs):
        nonlocal live_called
        live_called = True
        raise AssertionError("live tier must be skipped")

    monkeypatch.setattr(preflight, "run_static", fake_static)
    monkeypatch.setattr(preflight, "run_live", fake_live)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")

    code, report = asyncio.run(run_preflight(matrix, tmp_path / "out", static_only=False, selected_case=None))

    assert code == 1
    assert live_called is False
    assert report["schema_version"] == 1
    assert report["budget_s"] == 300
    assert report["tiers"]["static"]["elapsed_s"] == 1.235
    assert [item["name"] for item in report["tiers"]["static"]["images"]] == ["a-case", "z-case"]
    report_text = (tmp_path / "out" / "report.json").read_text()
    assert "secret-value" not in report_text
    assert not (tmp_path / "out" / "report.json.tmp").exists()


@pytest.mark.parametrize(
    ("static_only", "live_cases", "expected_code"),
    [(True, None, 0), (False, [True, False], 0), (False, [False, False], 1)],
)
def test_run_preflight_aggregates_static_and_live_results(
    tmp_path: Path, monkeypatch, static_only: bool, live_cases: list[bool] | None, expected_code: int
):
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"cases": [_case(name="b-case"), _case(name="a-case")]}))

    async def fake_static(cases, runner, environment=None):
        return {"passed": True, "elapsed_s": 0.1, "images": [{"name": case.name, "passed": True} for case in cases]}

    async def fake_live(cases, output, runner, environment):
        assert live_cases is not None
        return {
            "passed": all(live_cases),
            "elapsed_s": 2.34567,
            "cases": [
                {"name": case.name, "passed": passed, "failures": []}
                for case, passed in zip(cases, live_cases, strict=True)
            ],
        }

    monkeypatch.setattr(preflight, "run_static", fake_static)
    monkeypatch.setattr(preflight, "run_live", fake_live)

    code, report = asyncio.run(
        run_preflight(matrix, tmp_path / f"out-{static_only}", static_only=static_only, selected_case=None)
    )

    assert code == expected_code
    assert report["passed"] is (expected_code == 0)
    assert [item["name"] for item in report["tiers"]["static"]["images"]] == ["a-case", "b-case"]
    if static_only:
        assert "live" not in report["tiers"]
    else:
        assert report["tiers"]["live"]["elapsed_s"] == 2.346
        assert [item["name"] for item in report["tiers"]["live"]["cases"]] == ["a-case", "b-case"]


def test_run_preflight_case_selection_and_unknown_case_fail_before_docker(tmp_path: Path, monkeypatch):
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"cases": [_case(name="first"), _case(name="second")]}))
    selected: list[str] = []

    async def fake_static(cases, runner, environment=None):
        selected.extend(case.name for case in cases)
        return {"passed": True, "elapsed_s": 0.1, "images": [{"name": case.name, "passed": True} for case in cases]}

    monkeypatch.setattr(preflight, "run_static", fake_static)

    code, _ = asyncio.run(
        run_preflight(matrix, tmp_path / "selected", static_only=True, selected_case="second")
    )
    assert code == 0
    assert selected == ["second"]

    selected.clear()
    with pytest.raises(ValueError, match="unknown case"):
        asyncio.run(run_preflight(matrix, tmp_path / "unknown", static_only=True, selected_case="missing"))
    assert selected == []
