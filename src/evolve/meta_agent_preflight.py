"""Deterministic checks for meta-agent container contracts."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
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

STATIC_PROBE = (
    r"""python - <<'PY'
import json
import os
import re
import shutil
import subprocess

def version(command):
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise SystemExit(completed.stderr or completed.stdout or "version command failed")
    match = re.search(r"\d+\.\d+\.\d+", completed.stdout + completed.stderr)
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
    started = time.monotonic()
    redaction_environment = environment or {}
    elapsed_s = 0.0
    observed_image_id: str | None = None

    def finish() -> dict[str, object]:
        result["elapsed_s"] = max(float(result.get("elapsed_s", 0.0)), time.monotonic() - started)
        return result

    try:
        inspection = await runner(
            ("docker", "image", "inspect", case.image, "--format", "{{json .}}"),
            _STATIC_TIMEOUT_S,
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

        probe = await runner(
            ("docker", "run", "--rm", "--entrypoint", "bash", case.image, "-lc", STATIC_PROBE),
            _STATIC_TIMEOUT_S,
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
    started = time.monotonic()
    images = list(await asyncio.gather(*(inspect_image(case, runner, environment) for case in cases)))
    elapsed_s = max((float(image["elapsed_s"]) for image in images), default=0.0)
    return {
        "passed": all(image["passed"] is True for image in images),
        "elapsed_s": elapsed_s if images else time.monotonic() - started,
        "images": images,
    }
