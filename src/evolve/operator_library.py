from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .config import Resource, library_root
from .frozen.interfaces import OPERATOR_BY_KIND

OPERATOR_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class LibraryOperator:
    stage: str
    name: str
    source: Resource

    @property
    def identity(self) -> str:
        return f"{self.stage}/{self.name}"


class OperatorLibraryError(ValueError):
    pass


_DISCOVERY_ROOTS: dict[int, Resource] = {}


def discover_operators(root: Resource | None = None) -> dict[tuple[str, str], LibraryOperator]:
    library = root or library_root()
    if not library.is_dir():
        raise OperatorLibraryError(f"operator library is not a directory: {library}")
    discovered: dict[tuple[str, str], LibraryOperator] = {}
    for entry in sorted(library.iterdir(), key=lambda item: item.name):
        if entry.name.startswith("_"):
            continue
        if entry.is_dir():
            if entry.name not in OPERATOR_BY_KIND:
                raise OperatorLibraryError(f"unknown operator stage directory: {entry.name}")
            _discover_stage(entry, library, discovered)
        elif entry.is_file() and entry.name.endswith(".py"):
            raise OperatorLibraryError(f"root Python helpers must be underscore-prefixed: {entry.name}")
    return discovered


def _discover_stage(
    stage_root: Resource, library: Resource, discovered: dict[tuple[str, str], LibraryOperator]
) -> None:
    stage = stage_root.name
    for entry in sorted(stage_root.iterdir(), key=lambda item: item.name):
        if entry.name.startswith("_"):
            continue
        if not entry.is_file() or not entry.name.endswith(".py"):
            continue
        name = entry.name.removesuffix(".py")
        if not OPERATOR_NAME.fullmatch(name):
            raise OperatorLibraryError(f"invalid operator name: {entry.name}")
        operator = LibraryOperator(stage=stage, name=name, source=entry)
        _DISCOVERY_ROOTS[id(entry)] = library
        discovered[(stage, name)] = operator


def resolve_operator(stage: str, name: str, root: Resource | None = None) -> LibraryOperator:
    try:
        return discover_operators(root)[(stage, name)]
    except KeyError as error:
        raise OperatorLibraryError(f"operator not found: {stage}/{name}") from error


def describe_operator(operator: LibraryOperator, timeout_s: float = 5.0) -> dict[str, object]:
    return _inspect(operator, "--describe", {}, timeout_s)


def validate_operator_config(
    operator: LibraryOperator, config: dict[str, object], timeout_s: float = 5.0
) -> dict[str, object]:
    return _inspect(operator, "--validate-config", config, timeout_s)


def _inspect(operator: LibraryOperator, mode: str, config: dict[str, object], timeout_s: float) -> dict[str, object]:
    with _operator_source(operator) as (source, cwd):
        environment = dict(os.environ)
        existing_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = str(cwd) if not existing_path else f"{cwd}{os.pathsep}{existing_path}"
        try:
            completed = subprocess.run(
                [sys.executable, str(source), mode, "--config", json.dumps(config)],
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise _error(operator, f"inspection timed out after {timeout_s}s", error.stderr) from error
    if completed.returncode != 0:
        raise _error(operator, f"inspection exited with status {completed.returncode}", completed.stderr)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise _error(operator, "inspection returned malformed JSON", completed.stderr) from error
    if not isinstance(payload, dict):
        raise _error(operator, "inspection must return one JSON object", completed.stderr)
    return cast("dict[str, object]", payload)


@contextmanager
def _operator_source(operator: LibraryOperator) -> Iterator[tuple[Path, Path]]:
    source = operator.source
    root = _DISCOVERY_ROOTS.get(id(source), _default_library_root(operator))
    if isinstance(source, Path):
        yield source, root.parent
        return
    with tempfile.TemporaryDirectory(prefix="evolvex-operator-library-") as temporary:
        destination = Path(temporary) / "library"
        _copy_tree(root, destination)
        yield destination / operator.stage / f"{operator.name}.py", destination.parent


def _default_library_root(operator: LibraryOperator) -> Resource:
    if isinstance(operator.source, Path):
        return operator.source.parent.parent
    return library_root()


def _copy_tree(source: Resource, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            _copy_tree(entry, target)
        elif entry.is_file():
            target.write_bytes(entry.read_bytes())


def _error(operator: LibraryOperator, message: str, stderr: object) -> OperatorLibraryError:
    tail = _stderr_tail(stderr)
    return OperatorLibraryError(f"{operator.identity}: {message}; stderr tail: {tail}")


def _stderr_tail(stderr: object) -> str:
    if isinstance(stderr, bytes):
        stderr = stderr.decode(errors="replace")
    text = str(stderr or "").strip()
    return text[-2000:] if text else "<empty>"
