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
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import IO, Literal, cast, overload

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


@dataclass(frozen=True)
class _RootedResource(Traversable):
    resource: Traversable
    root: Traversable

    @property
    def name(self) -> str:
        return self.resource.name

    def iterdir(self) -> Iterator[Traversable]:
        return (_RootedResource(entry, self.root) for entry in self.resource.iterdir())

    def is_dir(self) -> bool:
        return self.resource.is_dir()

    def is_file(self) -> bool:
        return self.resource.is_file()

    def joinpath(self, *descendants: str | os.PathLike[str]) -> Traversable:
        return _RootedResource(self.resource.joinpath(*descendants), self.root)

    @overload
    def open(
        self,
        mode: Literal["r"] = "r",
        *,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> IO[str]: ...

    @overload
    def open(self, mode: Literal["rb"]) -> IO[bytes]: ...

    def open(
        self,
        mode: Literal["r", "rb"] = "r",
        *,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> IO[str] | IO[bytes]:
        if mode == "rb":
            return self.resource.open("rb")
        return self.resource.open("r", encoding=encoding, errors=errors)


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


def list_operators(stage: str | None = None, root: Resource | None = None) -> list[LibraryOperator]:
    if stage is not None and stage not in OPERATOR_BY_KIND:
        raise OperatorLibraryError(f"unknown operator stage: {stage}")
    return [
        operator
        for operator in sorted(discover_operators(root).values(), key=lambda item: (item.stage, item.name))
        if stage is None or operator.stage == stage
    ]


def parse_operator_identity(identity: str) -> tuple[str, str]:
    stage, separator, name = identity.partition("/")
    if separator != "/" or "/" in name or stage not in OPERATOR_BY_KIND or not OPERATOR_NAME.fullmatch(name):
        raise OperatorLibraryError(f"invalid operator identity: {identity}")
    return stage, name


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
        source: Resource = entry if isinstance(entry, Path) else _RootedResource(entry, library)
        operator = LibraryOperator(stage=stage, name=name, source=source)
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
    try:
        serialized_config = json.dumps(config, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise _error(operator, f"config is not JSON-serializable: {error}", None) from error
    with _operator_source(operator) as (source, cwd):
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        existing_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = str(cwd) if not existing_path else f"{cwd}{os.pathsep}{existing_path}"
        launcher = "import runpy, sys; source = sys.argv.pop(1); runpy.run_path(source, run_name='__main__')"
        try:
            completed = subprocess.run(
                [sys.executable, "-c", launcher, str(source), mode, "--config", serialized_config],
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
        payload = json.loads(completed.stdout, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise _error(operator, "inspection returned malformed JSON", completed.stderr) from error
    if not isinstance(payload, dict):
        raise _error(operator, "inspection must return one JSON object", completed.stderr)
    return cast("dict[str, object]", payload)


@contextmanager
def _operator_source(operator: LibraryOperator) -> Iterator[tuple[Path, Path]]:
    source = operator.source
    if isinstance(source, Path):
        yield source, source.parent.parent.parent
        return
    root = source.root if isinstance(source, _RootedResource) else _default_library_root(operator)
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


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant: {value}")
