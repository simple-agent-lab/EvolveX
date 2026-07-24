"""Deterministic checks for meta-agent container contracts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Protocol

_CASE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([a-z0-9_-]*(?:api[_-]?key|access[_-]?token|auth(?:orization)?|secret|password))\b"
    r"([\"']?)(\s*[:=]\s*)([^\s,;}]+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_URL_USERINFO = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
_REQUIRED_TOOLS = tuple(
    tool
    for tool in (Path(__file__).resolve().parents[2] / "containers" / "meta-agent" / "required-tools.txt")
    .read_text()
    .splitlines()
    if tool
)
_MINIMAL_EXCLUDED_TOOLS = frozenset({"jq", "rg", "rsync", "tree"})
_STATIC_TIMEOUT_S = 15.0
_LIVE_MAX_OUTPUT_TOKENS = 64000
_LIVE_MODEL = "openai/gpt-5.4-2026-03-05"
_LIVE_ENVIRONMENT = frozenset(
    {
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "NO_PROXY",
        "no_proxy",
    }
)
_MINISWE_SHIM = """\
import os
import shutil
import sys
from pathlib import Path

entrypoint = shutil.which("mini-swe-agent")
if entrypoint is None:
    raise SystemExit("mini-swe-agent is not on PATH")

arguments = []
for argument in sys.argv[1:]:
    if argument.startswith("--task-file="):
        arguments.append("--task=" + Path(argument.removeprefix("--task-file=")).read_text())
    else:
        arguments.append(argument)
os.execv(entrypoint, [entrypoint, *arguments])
"""

STATIC_PROBE = (
    r"""python - <<'PY'
import json
import os
import re
import shutil
import subprocess

def version(command):
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    match = re.search(r"\d+\.\d+\.\d+", completed.stdout + completed.stderr)
    if completed.returncode and not match:
        raise SystemExit(completed.stderr or completed.stdout or "version command failed")
    if not match:
        raise SystemExit("semantic version missing from " + " ".join(command))
    return match.group(0)

commands = """
    + repr(_REQUIRED_TOOLS)
    + r"""
print(json.dumps({
    "miniswe_version": version(("mini-swe-agent", "--version")),
    "python_version": version(("python", "--version")),
    "uv_version": version(("uv", "--version")),
    "commands": [command for command in commands if shutil.which(command)],
    "app_exists": os.path.isdir("/app"),
    "app_writable": os.access("/app", os.W_OK),
}))
PY"""
)


@dataclass(frozen=True)
class CommandResult:
    """The normalized result of one argv-only host process invocation."""

    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float


class CommandRunner(Protocol):
    """Run one host process without shell interpolation."""

    async def __call__(
        self,
        argv: tuple[str, ...],
        timeout_s: float,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult: ...


@dataclass(frozen=True)
class PreflightCase:
    """One immutable preflight configuration entry."""

    name: str
    image: str
    expected_image_id: str
    miniswe_version: str
    expanded_tools: bool
    timeout_s: int = 120

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PreflightCase:
        """Construct a validated case from one JSON matrix entry."""
        required = {"name", "image", "expected_image_id", "miniswe_version", "expanded_tools"}
        accepted = required | {"timeout_s"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"missing case field: {sorted(missing)[0]}")
        extra = data.keys() - accepted
        if extra:
            raise ValueError(f"unknown case field: {sorted(extra)[0]}")

        name = data["name"]
        image = data["image"]
        image_id = data["expected_image_id"]
        miniswe_version = data["miniswe_version"]
        expanded_tools = data["expanded_tools"]
        timeout_s = data.get("timeout_s", 120)
        if not isinstance(name, str) or not _CASE_NAME.fullmatch(name):
            raise ValueError("case name must match the safe name format")
        if not isinstance(image, str) or not image:
            raise ValueError("image must be a nonempty string")
        if not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id):
            raise ValueError("expected_image_id must be a sha256 image ID")
        if not isinstance(miniswe_version, str) or not _SEMVER.fullmatch(miniswe_version):
            raise ValueError("miniswe_version must be a semantic version")
        if not isinstance(expanded_tools, bool):
            raise ValueError("expanded_tools must be a boolean")
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, int) or not 1 <= timeout_s <= 120:
            raise ValueError("timeout_s must be between 1 and 120")
        return cls(name, image, image_id, miniswe_version, expanded_tools, timeout_s)


def create_synthetic_workspace(root: Path, *, require_rg: bool) -> Path:
    """Create a small committed edit task that needs no network dependencies."""
    root.mkdir(parents=True, exist_ok=False)
    target = root / "target"
    target.mkdir()
    (target / "value.py").write_text("VALUE = 1\n")
    (root / "check.py").write_text(
        "from target.value import VALUE\n\n"
        "if VALUE != 2:\n"
        "    raise SystemExit('VALUE == 2 is required')\n"
    )
    tools = "Python and rg" if require_rg else "Python"
    (root / "prompt.md").write_text(
        "Update target/value.py so the verification passes.\n\n"
        f"This task requires {tools}.\n"
        "Run python check.py. After it succeeds, write [\"target/value.py\"] to changed.json.\n"
        "Your exact final command must be:\n"
        "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n"
    )
    for argv in (
        ("git", "init", "--quiet"),
        ("git", "add", "target/value.py", "check.py", "prompt.md"),
        (
            "git",
            "-c",
            "user.name=Evolve Preflight",
            "-c",
            "user.email=preflight@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "synthetic workspace baseline",
        ),
    ):
        subprocess.run(argv, cwd=root, check=True, capture_output=True, text=True)
    return root


def load_matrix(path: Path) -> tuple[PreflightCase, ...]:
    """Read a nonempty, uniquely named JSON preflight matrix."""
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid matrix JSON: {error.msg}") from error
    if not isinstance(data, dict) or set(data) != {"cases"} or not isinstance(data["cases"], list):
        raise ValueError("matrix must be an object containing a cases list")
    if not data["cases"]:
        raise ValueError("matrix cases must be nonempty")

    cases: list[PreflightCase] = []
    names: set[str] = set()
    for item in data["cases"]:
        if not isinstance(item, dict):
            raise ValueError("each matrix case must be an object")
        case = PreflightCase.from_dict(item)
        if case.name in names:
            raise ValueError(f"duplicate case name: {case.name}")
        names.add(case.name)
        cases.append(case)
    return tuple(cases)


def redact(value: str, environment: Mapping[str, str]) -> str:
    """Remove credentials from diagnostic text without loading Harbor helpers."""
    for secret in environment.values():
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]", value
    )
    return _URL_USERINFO.sub(r"\1[REDACTED]@", value)


def _json_object(stdout: str, description: str) -> dict[str, object]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"{description} did not emit one JSON object: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{description} did not emit one JSON object")
    return value


def _failure(message: str, elapsed_s: float, *, observed_image_id: str | None = None) -> dict[str, object]:
    return {
        "passed": False,
        "failure_boundary": "image_contract",
        "failures": [message],
        "elapsed_s": elapsed_s,
        "observed_image_id": observed_image_id,
    }


def _diagnostic(result: CommandResult, environment: Mapping[str, str]) -> str:
    return redact("\n".join(part for part in (result.stdout, result.stderr) if part), environment)


def _required_tools(case: PreflightCase) -> tuple[str, ...]:
    if case.expanded_tools:
        return _REQUIRED_TOOLS
    return tuple(tool for tool in _REQUIRED_TOOLS if tool not in _MINIMAL_EXCLUDED_TOOLS)


async def inspect_image(
    case: PreflightCase,
    runner: CommandRunner,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Inspect one image and return an image-contract result, never raising expected failures."""
    result: dict[str, object] = {
        "name": case.name,
        "image": case.image,
        "expected_image_id": case.expected_image_id,
        "declared_miniswe_version": case.miniswe_version,
    }
    started = monotonic()
    deadline = started + _STATIC_TIMEOUT_S
    redaction_environment = environment or {}
    elapsed_s = 0.0
    observed_image_id: str | None = None

    def finish() -> dict[str, object]:
        result["elapsed_s"] = max(float(result.get("elapsed_s", 0.0)), monotonic() - started)
        return result

    try:
        inspect_timeout_s = deadline - monotonic()
        if inspect_timeout_s <= 0:
            result.update(_failure("static image timeout exhausted before inspection", elapsed_s))
            return finish()
        inspection = await runner(
            ("docker", "image", "inspect", case.image, "--format", "{{json .}}"),
            inspect_timeout_s,
            env=environment,
        )
        elapsed_s += inspection.elapsed_s
        if inspection.returncode:
            result.update(_failure(f"docker image inspect failed: {_diagnostic(inspection, redaction_environment)}", elapsed_s))
            return finish()
        image_data = _json_object(inspection.stdout, "docker image inspect")
        image_id = image_data.get("Id")
        if not isinstance(image_id, str):
            result.update(_failure("docker image inspect omitted Id", elapsed_s))
            return finish()
        observed_image_id = image_id
        result["observed_image_id"] = image_id
        if image_id != case.expected_image_id:
            result.update(_failure("image ID does not match expected_image_id", elapsed_s, observed_image_id=image_id))
            return finish()

        probe_timeout_s = deadline - monotonic()
        if probe_timeout_s <= 0:
            result.update(_failure("static image timeout exhausted before probe", elapsed_s, observed_image_id=image_id))
            return finish()
        probe = await runner(
            ("docker", "run", "--rm", "--entrypoint", "bash", case.expected_image_id, "-lc", STATIC_PROBE),
            probe_timeout_s,
            env=environment,
        )
        elapsed_s += probe.elapsed_s
        if probe.returncode:
            result.update(
                _failure(
                    f"static probe failed: {_diagnostic(probe, redaction_environment)}",
                    elapsed_s,
                    observed_image_id=image_id,
                )
            )
            return finish()
        observed = _json_object(probe.stdout, "static probe")
        miniswe_version = observed.get("miniswe_version")
        if isinstance(miniswe_version, str):
            result["observed_miniswe_version"] = miniswe_version
        if miniswe_version != case.miniswe_version:
            result.update(
                _failure("MiniSWE version does not match declared version", elapsed_s, observed_image_id=image_id)
            )
            return finish()
        commands = observed.get("commands")
        if not isinstance(commands, list) or not all(isinstance(command, str) for command in commands):
            result.update(_failure("static probe emitted invalid commands", elapsed_s, observed_image_id=image_id))
            return finish()
        missing_tools = [tool for tool in _required_tools(case) if tool not in commands]
        if missing_tools:
            result.update(
                _failure(
                    "missing required commands: " + ", ".join(missing_tools),
                    elapsed_s,
                    observed_image_id=image_id,
                )
            )
            return finish()
        if not isinstance(observed.get("python_version"), str) or not isinstance(observed.get("uv_version"), str):
            result.update(_failure("static probe omitted Python or uv version", elapsed_s, observed_image_id=image_id))
            return finish()
        if observed.get("app_exists") is not True or observed.get("app_writable") is not True:
            result.update(_failure("/app must exist and be writable", elapsed_s, observed_image_id=image_id))
            return finish()
    except TimeoutError:
        result.update(_failure("timeout while inspecting image", elapsed_s, observed_image_id=observed_image_id))
        return finish()
    except (OSError, TypeError, ValueError) as error:
        result.update(_failure(redact(str(error), redaction_environment), elapsed_s, observed_image_id=observed_image_id))
        return finish()

    result.update(
        {
            "passed": True,
            "failure_boundary": None,
            "failures": [],
            "elapsed_s": elapsed_s,
            "observed_miniswe_version": miniswe_version,
        }
    )
    return finish()


async def run_static(
    cases: Sequence[PreflightCase],
    runner: CommandRunner,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Run independent image checks concurrently and preserve matrix order."""
    started = monotonic()
    images = list(await asyncio.gather(*(inspect_image(case, runner, environment) for case in cases)))
    elapsed_s = max((float(image["elapsed_s"]) for image in images), default=0.0)
    return {
        "passed": all(image["passed"] is True for image in images),
        "elapsed_s": elapsed_s if images else monotonic() - started,
        "images": images,
    }


def _live_config(case: PreflightCase) -> dict[str, object]:
    cache_key = f"evolve-preflight-{case.name}"
    return {
        "model": {
            "model_kwargs": {
                "max_output_tokens": _LIVE_MAX_OUTPUT_TOKENS,
                "include": ["reasoning.encrypted_content"],
                "prompt_cache_key": cache_key,
                "extra_headers": {"extra": json.dumps({"session_id": cache_key}, sort_keys=True)},
            }
        }
    }


def _child_environment(environment: Mapping[str, str]) -> dict[str, str]:
    child = {name: value for name, value in environment.items() if name in _LIVE_ENVIRONMENT and value}
    child["MSWEA_CONFIGURED"] = "true"
    return child


def _sensitive_environment(environment: Mapping[str, str]) -> dict[str, str]:
    markers = ("KEY", "TOKEN", "AUTH", "SECRET", "PASSWORD", "PROXY")
    return {
        name: value
        for name, value in environment.items()
        if value and any(marker in name.upper() for marker in markers)
    }


async def _host_command(argv: tuple[str, ...], cwd: Path, timeout_s: float) -> CommandResult:
    """Run a local verifier command with a hard asynchronous deadline."""
    started = monotonic()
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_s)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise
    return CommandResult(
        process.returncode,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
        monotonic() - started,
    )


def _write_text(path: Path, value: str) -> None:
    path.write_text(value)


def _read_trajectory(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid trajectory: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("trajectory must be a JSON object")
    return value


def _changed_paths(workspace: Path) -> list[str]:
    try:
        value = json.loads((workspace / "changed.json").read_text())
    except FileNotFoundError as error:
        raise ValueError("Submitted without changed.json") from error
    except json.JSONDecodeError as error:
        raise ValueError("changed.json is not valid JSON") from error
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError("changed.json must contain changed paths")
    if any(Path(item).is_absolute() or ".." in Path(item).parts for item in value):
        raise ValueError("changed.json contains an unsafe path")
    return value


def _trajectory_details(trajectory: Mapping[str, object]) -> tuple[dict[str, object], list[dict[str, object]]]:
    info = trajectory.get("info")
    if not isinstance(info, dict):
        raise ValueError("trajectory omitted info")
    config = info.get("config")
    if not isinstance(config, dict):
        raise ValueError("trajectory omitted effective configuration")
    model = config.get("model")
    if not isinstance(model, dict):
        raise ValueError("trajectory omitted effective model configuration")
    effective = model.get("model_kwargs")
    if not isinstance(effective, dict):
        raise ValueError("trajectory omitted effective model configuration")
    reasoning = effective.get("reasoning")
    if (
        effective.get("max_output_tokens") != _LIVE_MAX_OUTPUT_TOKENS
        or effective.get("include") != ["reasoning.encrypted_content"]
        or not isinstance(reasoning, dict)
        or reasoning.get("effort") != "low"
    ):
        raise ValueError("trajectory effective model configuration does not match Responses config")
    messages = trajectory.get("messages")
    if not isinstance(messages, list) or not messages or not isinstance(messages[-1], dict):
        raise ValueError("trajectory omitted exit message")
    exit_message = messages[-1]
    extra = exit_message.get("extra")
    status = extra.get("exit_status") if isinstance(extra, dict) else None
    if exit_message.get("role") != "exit" or status != "Submitted":
        detail = json.dumps(exit_message, sort_keys=True)
        if "RepeatedFormatError" in detail or "finish_reason=length" in detail:
            raise ValueError(f"model protocol exit: {detail}")
        raise ValueError(f"unexpected trajectory exit status: {detail}")

    tool_calls: list[dict[str, object]] = []

    def collect_calls(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "function_call":
                tool_calls.append(dict(value))
            for child in value.values():
                collect_calls(child)
        elif isinstance(value, list):
            for child in value:
                collect_calls(child)

    collect_calls(messages)
    return dict(effective), tool_calls


def _executed_programs(command: str) -> set[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    programs: set[str] = set()
    at_command_start = True
    for token in lexer:
        if token and all(character in ";&|" for character in token):
            at_command_start = True
            continue
        if not at_command_start:
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            continue
        if token in {"if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done", "{"}:
            continue
        programs.add(Path(token).name)
        at_command_start = False
    return programs


def _protocol_evidence(tool_calls: Sequence[Mapping[str, object]], *, require_rg: bool) -> dict[str, object]:
    commands: list[str] = []
    for call in tool_calls:
        arguments = call.get("arguments")
        if not isinstance(arguments, str):
            continue
        try:
            decoded = json.loads(arguments)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict) and isinstance(decoded.get("command"), str):
            commands.append(decoded["command"])
    programs = set().union(*(_executed_programs(command) for command in commands), set())
    used_python = any(re.fullmatch(r"python(?:3(?:\.\d+)*)?", program) for program in programs)
    used_rg = "rg" in programs
    submission_command = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
    submitted = any(command.strip() == submission_command for command in commands)
    missing = [
        label
        for label, present in (
            ("python tool call", used_python),
            ("rg tool call", used_rg or not require_rg),
            ("exact submission command", submitted),
        )
        if not present
    ]
    if missing:
        raise ValueError("trajectory omitted required protocol evidence: " + ", ".join(missing))
    return {
        "tool_call_count": len(tool_calls),
        "used_python": used_python,
        "used_rg": used_rg,
        "submission_command": submission_command,
        "submitted": submitted,
    }


def _live_result(
    case: PreflightCase,
    container_name: str,
    case_dir: Path,
    elapsed_s: float,
    *,
    passed: bool,
    failure_boundary: str | None,
    failures: list[str],
    **details: object,
) -> dict[str, object]:
    result: dict[str, object] = {
        "name": case.name,
        "image": case.image,
        "image_id": case.expected_image_id,
        "declared_miniswe_version": case.miniswe_version,
        "requested_max_output_tokens": _LIVE_MAX_OUTPUT_TOKENS,
        "requested_reasoning_effort": "low",
        "observed_miniswe_version": None,
        "agent_exit_status": None,
        "protocol_evidence": {
            "tool_call_count": 0,
            "used_python": False,
            "used_rg": False,
            "submission_command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
            "submitted": False,
        },
        "artifact_contract": {"passed": False, "changed_paths": []},
        "verification": {"passed": False, "returncode": None},
        "changed_paths": [],
        "patch_bytes": 0,
        "container_name": container_name,
        "passed": passed,
        "failure_boundary": failure_boundary,
        "failures": failures,
        "elapsed_s": elapsed_s,
        "logs": {
            "stdout": str(case_dir / "stdout.log"),
            "stderr": str(case_dir / "stderr.log"),
            "trajectory": str(case_dir / "trajectory.json"),
            "patch": str(case_dir / "patch.diff"),
            "config": str(case_dir / "responses.yaml"),
        },
    }
    result.update(details)
    return result


async def run_live_case(
    case: PreflightCase,
    output: Path,
    runner: CommandRunner,
    environment: Mapping[str, str],
) -> dict[str, object]:
    """Run one isolated model protocol smoke and retain redacted local evidence."""
    started = monotonic()
    deadline = started + case.timeout_s
    case_dir = output / "cases" / case.name
    case_dir.mkdir(parents=True, exist_ok=False)
    _write_text(case_dir / "stdout.log", "")
    _write_text(case_dir / "stderr.log", "")
    _write_text(case_dir / "patch.diff", "")
    workspace = await asyncio.to_thread(
        create_synthetic_workspace, case_dir / "workspace", require_rg=case.expanded_tools
    )
    config = _live_config(case)
    (case_dir / "responses.yaml").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    _write_text(case_dir / "runner.py", _MINISWE_SHIM)
    nonce = uuid.uuid4().hex
    container_name = f"evolve-preflight-{case.name}-{nonce}"
    child_environment = _child_environment(environment)
    env_arguments = tuple(item for name in child_environment for item in ("--env", name))
    model = environment.get("EVOLVE_PREFLIGHT_MODEL", _LIVE_MODEL)
    command = (
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "-w",
        "/app/task/workspace",
        "-v",
        f"{workspace}:/app/task/workspace",
        "-v",
        f"{case_dir}:/app/task/output",
        *env_arguments,
        case.expected_image_id,
        "python",
        "/app/task/output/runner.py",
        "--yolo",
        f"--model={model}",
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
    docker_result = CommandResult(0, "", "", 0.0)
    try:
        remaining_s = deadline - monotonic()
        if remaining_s <= 0:
            raise TimeoutError
        docker_result = await asyncio.wait_for(
            runner(command, remaining_s, env=child_environment),
            remaining_s,
        )
        _write_text(case_dir / "stdout.log", redact(docker_result.stdout, environment))
        _write_text(case_dir / "stderr.log", redact(docker_result.stderr, environment))
        if docker_result.returncode:
            diagnostic = _diagnostic(docker_result, environment)
            boundary = "model_protocol" if (
                "RepeatedFormatError" in diagnostic or "finish_reason=length" in diagnostic
            ) else "agent_startup"
            result = _live_result(
                case, container_name, case_dir, monotonic() - started,
                passed=False, failure_boundary=boundary, failures=[diagnostic or "agent process failed"],
            )
            (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            return result
    except TimeoutError:
        try:
            await runner(("docker", "stop", container_name), min(5.0, float(case.timeout_s)), env=child_environment)
        except (OSError, TimeoutError):
            pass
        _write_text(case_dir / "stdout.log", "")
        _write_text(case_dir / "stderr.log", "agent process timeout\n")
        result = _live_result(
            case, container_name, case_dir, monotonic() - started,
            passed=False, failure_boundary="agent_startup", failures=["agent process timeout"],
        )
        (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    except (OSError, TypeError) as error:
        _write_text(case_dir / "stdout.log", "")
        _write_text(case_dir / "stderr.log", redact(str(error), environment))
        result = _live_result(
            case, container_name, case_dir, monotonic() - started,
            passed=False, failure_boundary="agent_startup", failures=[redact(str(error), environment)],
        )
        (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    try:
        trajectory = _read_trajectory(case_dir / "trajectory.json")
        effective_model_config, tool_calls = _trajectory_details(trajectory)
        protocol_evidence = _protocol_evidence(tool_calls, require_rg=case.expanded_tools)
    except ValueError as error:
        result = _live_result(
            case, container_name, case_dir, monotonic() - started,
            passed=False, failure_boundary="model_protocol", failures=[redact(str(error), environment)],
        )
        (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    try:
        changed_paths = _changed_paths(workspace)
    except ValueError as error:
        result = _live_result(
            case, container_name, case_dir, monotonic() - started,
            passed=False, failure_boundary="artifact_import", failures=[str(error)],
        )
        (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    if changed_paths != ["target/value.py"]:
        result = _live_result(
            case, container_name, case_dir, monotonic() - started,
            passed=False, failure_boundary="artifact_import",
            failures=["changed.json must contain exactly target/value.py"],
        )
        (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    try:
        remaining_s = deadline - monotonic()
        if remaining_s <= 0:
            raise TimeoutError
        check = await _host_command((sys.executable, "check.py"), workspace, remaining_s)
    except (OSError, TimeoutError) as error:
        failure = "verification timeout" if isinstance(error, TimeoutError) else str(error)
        result = _live_result(
            case, container_name, case_dir, monotonic() - started,
            passed=False, failure_boundary="verification", failures=[redact(failure, environment)],
        )
        (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    if check.returncode:
        result = _live_result(
            case, container_name, case_dir, monotonic() - started,
            passed=False, failure_boundary="verification", failures=[_diagnostic(check, environment)],
        )
        (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    try:
        remaining_s = deadline - monotonic()
        if remaining_s <= 0:
            raise TimeoutError
        patch = await _host_command(("git", "diff", "--binary"), workspace, remaining_s)
    except (OSError, TimeoutError) as error:
        result = _live_result(
            case, container_name, case_dir, monotonic() - started,
            passed=False, failure_boundary="workspace_edit", failures=[redact(str(error), environment)],
        )
        (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    patch_text = redact(patch.stdout, environment)
    _write_text(case_dir / "patch.diff", patch_text)
    if patch.returncode or not patch_text:
        result = _live_result(
            case, container_name, case_dir, monotonic() - started,
            passed=False, failure_boundary="workspace_edit", failures=[_diagnostic(patch, environment) or "no git diff"],
        )
        (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    (case_dir / "changed.json").write_text(json.dumps(changed_paths) + "\n")
    result = _live_result(
        case, container_name, case_dir, monotonic() - started,
        passed=True, failure_boundary=None, failures=[],
        observed_miniswe_version=case.miniswe_version,
        agent_exit_status="Submitted",
        protocol_evidence=protocol_evidence,
        artifact_contract={"passed": True, "changed_paths": changed_paths},
        verification={"passed": True, "returncode": check.returncode},
        effective_model_config=effective_model_config,
        tool_calls=tool_calls,
        changed_paths=changed_paths,
        patch_bytes=len(patch_text.encode()),
    )
    (case_dir / "case.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


async def run_live(
    cases: Sequence[PreflightCase],
    output: Path,
    runner: CommandRunner,
    environment: Mapping[str, str],
) -> dict[str, object]:
    """Run independent live cases concurrently without sibling cancellation."""
    if len({case.name for case in cases}) != len(cases):
        raise ValueError("live cases must have unique names")
    started = monotonic()
    results: list[dict[str, object] | None] = [None] * len(cases)

    async def collect(index: int, case: PreflightCase) -> None:
        try:
            results[index] = await run_live_case(case, output, runner, environment)
        except Exception as error:  # Expected case failures must not cancel siblings.
            results[index] = {
                "name": case.name,
                "image": case.image,
                "image_id": case.expected_image_id,
                "declared_miniswe_version": case.miniswe_version,
                "requested_max_output_tokens": _LIVE_MAX_OUTPUT_TOKENS,
                "requested_reasoning_effort": "low",
                "observed_miniswe_version": None,
                "agent_exit_status": None,
                "protocol_evidence": {
                    "tool_call_count": 0,
                    "used_python": False,
                    "used_rg": False,
                    "submission_command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
                    "submitted": False,
                },
                "artifact_contract": {"passed": False, "changed_paths": []},
                "verification": {"passed": False, "returncode": None},
                "changed_paths": [],
                "patch_bytes": 0,
                "passed": False,
                "failure_boundary": "agent_startup",
                "failures": [redact(str(error), environment)],
                "elapsed_s": 0.0,
            }

    async with asyncio.TaskGroup() as group:
        for index, case in enumerate(cases):
            group.create_task(collect(index, case))
    completed = [result for result in results if result is not None]
    return {
        "passed": all(result["passed"] is True for result in completed),
        "elapsed_s": monotonic() - started,
        "cases": completed,
    }


async def _command_runner(
    argv: tuple[str, ...],
    timeout_s: float,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    """Run an argv-only process for the preflight CLI."""
    started = monotonic()
    process_environment = os.environ.copy()
    if env is not None:
        process_environment.update(env)
    process = await asyncio.create_subprocess_exec(
        *argv,
        env=process_environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_s)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise
    return CommandResult(
        process.returncode,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
        monotonic() - started,
    )


def _report_value(value: object, environment: Mapping[str, str], key: str = "") -> object:
    if isinstance(value, str):
        return redact(value, environment)
    if isinstance(value, float) and key == "elapsed_s":
        return round(value, 3)
    if isinstance(value, list):
        return [_report_value(item, environment) for item in value]
    if isinstance(value, dict):
        return {
            str(item_key): _report_value(item_value, environment, str(item_key))
            for item_key, item_value in value.items()
        }
    return value


def _sort_results(tier: dict[str, object], key: str) -> None:
    results = tier.get(key)
    if isinstance(results, list):
        results.sort(key=lambda item: str(item.get("name", "")) if isinstance(item, dict) else "")


def _write_report(output: Path, report: Mapping[str, object]) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "report.json.tmp"
    destination = output / "report.json"
    with temporary.open("w") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(destination)
    return destination


async def run_preflight(
    matrix: Path,
    output: Path,
    *,
    static_only: bool,
    selected_case: str | None,
) -> tuple[int, dict[str, object]]:
    """Run the selected static and live tiers, then atomically retain one report."""
    started = monotonic()
    started_at = datetime.now(UTC).isoformat()
    cases = load_matrix(matrix)
    if selected_case is not None:
        cases = tuple(case for case in cases if case.name == selected_case)
        if not cases:
            raise ValueError(f"unknown case: {selected_case}")

    environment = dict(os.environ)
    redaction_environment = _sensitive_environment(environment)
    static = await run_static(cases, _command_runner, redaction_environment)
    _sort_results(static, "images")
    tiers: dict[str, object] = {"static": static}
    passed = bool(static["passed"])
    if passed and not static_only:
        live = await run_live(cases, output, _command_runner, environment)
        _sort_results(live, "cases")
        tiers["live"] = live
        live_cases = live.get("cases")
        passed = isinstance(live_cases, list) and any(
            isinstance(case, dict) and case.get("passed") is True for case in live_cases
        )

    report = _report_value(
        {
            "schema_version": 1,
            "started_at": started_at,
            "elapsed_s": monotonic() - started,
            "budget_s": 300,
            "static_only": static_only,
            "selected_case": selected_case,
            "passed": passed,
            "tiers": tiers,
        },
        redaction_environment,
    )
    assert isinstance(report, dict)
    report_path = _write_report(output, report)
    for tier_name, result_key in (("static", "images"), ("live", "cases")):
        tier = report["tiers"].get(tier_name)
        if not isinstance(tier, dict):
            continue
        for result in tier.get(result_key, []):
            if isinstance(result, dict):
                state = "PASS" if result.get("passed") is True else "FAIL"
                print(f"{tier_name} {result.get('name', 'unknown')}: {state}")
    print(f"report: {report_path}")
    return (0 if passed else 1), report


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the parallel meta-agent preflight."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--case", dest="selected_case")
    arguments = parser.parse_args(argv)
    try:
        code, _ = asyncio.run(
            run_preflight(
                arguments.matrix,
                arguments.output,
                static_only=arguments.static_only,
                selected_case=arguments.selected_case,
            )
        )
    except ValueError as error:
        parser.error(str(error))
    return code
