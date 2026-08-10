from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from .. import __version__ as _EVOLVE_VERSION
from ..config import Resource, library_root
from .recipe import ResolvedOperator


@dataclass(frozen=True)
class OperatorMaterialization:
    files: dict[str, str | bytes]
    components: dict[str, dict[str, object]]


def materialize_operators(
    bindings: Mapping[str, ResolvedOperator],
    *,
    library: Resource | None = None,
) -> OperatorMaterialization:
    root = library or library_root()
    if isinstance(root, Path) and root.is_symlink():
        raise ValueError(f"operator library root may not be a symlink: {root}")
    files: dict[str, str | bytes] = {}
    frozen_sources: dict[str, bytes] = {}
    components: dict[str, dict[str, object]] = {}
    for stage, binding in bindings.items():
        source = binding.source.read_bytes()
        if hashlib.sha256(source).hexdigest() != binding.digest:
            raise ValueError(f"operators.{stage} source changed after recipe resolution")
        active = _with_provenance(stage, _binding_source_label(binding), source.decode()).encode()
        files[f"operators/{stage}.py"] = active
        frozen_sources[stage] = source
        components[stage] = {
            "stage": stage,
            "source": binding.source_kind,
            "name": binding.name or binding.source.name,
            "sha256": hashlib.sha256(active).hexdigest(),
            "portable": binding.portable,
        }
        if binding.source_kind == "library":
            files.update(_stage_helper_files(root, stage))
        if isinstance(binding.source, Path):
            companion = binding.source.with_suffix(".md")
            if companion.is_file():
                files[f"operators/{stage}.md"] = companion.read_text()
    files.update(_root_helper_files(root))
    files["operators/README.md"] = _operator_index(bindings, frozen_sources)
    return OperatorMaterialization(files, components)


def _stage_helper_files(root: Resource, stage: str) -> dict[str, str | bytes]:
    stage_root = root / stage
    return _prefixed_helpers(stage_root, f"library/{stage}", exclude={"_skeleton.py"})


def _root_helper_files(root: Resource) -> dict[str, str | bytes]:
    files = _prefixed_helpers(root, "library", exclude=set())
    package_boundary = root / "__init__.py"
    if package_boundary.is_file():
        files["library/__init__.py"] = package_boundary.read_bytes()
    return files


def _content(source: Resource) -> str | bytes:
    content = source.read_bytes()
    try:
        return content.decode()
    except UnicodeDecodeError:
        return content


def _walk_files(root: Resource, prefix: Path = Path("")) -> Iterator[tuple[Path, Resource]]:
    for source in sorted(root.iterdir(), key=lambda entry: entry.name):
        relative = prefix / source.name
        if any(part.startswith(".") or part == "__pycache__" or part.endswith(".pyc") for part in relative.parts):
            continue
        if isinstance(source, Path) and source.is_symlink():
            raise ValueError(f"operator asset may not be a symlink: {source}")
        if source.is_dir():
            yield from _walk_files(source, relative)
        elif source.is_file():
            yield relative, source


def _prefixed_helpers(
    root: Resource,
    destination: str,
    *,
    exclude: set[str],
) -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = {}
    for source in sorted(root.iterdir(), key=lambda entry: entry.name):
        if (
            not source.name.startswith("_")
            or source.name in exclude
            or source.name == "__pycache__"
            or source.name.endswith(".pyc")
        ):
            continue
        if isinstance(source, Path) and source.is_symlink():
            raise ValueError(f"operator asset may not be a symlink: {source}")
        if source.is_dir():
            for relative, child in _walk_files(source):
                files[f"{destination}/{source.name}/{relative.as_posix()}"] = _content(child)
        elif source.is_file():
            files[f"{destination}/{source.name}"] = _content(source)
    return files


def _operator_index(
    bindings: Mapping[str, ResolvedOperator],
    frozen_sources: Mapping[str, bytes],
) -> str:
    rows = []
    for stage, binding in bindings.items():
        active = binding.name or binding.source.name.removesuffix(".py")
        rows.append(
            f"| {stage} | {active}.py | {_first_docstring_line(frozen_sources[stage].decode())} "
            f"| {_binding_source_label(binding)} |"
        )
    return (
        "# Active operators\n\n"
        "The loop runs exactly these recipe-selected scripts. The closed root and\n"
        "selected-stage underscore helper bundles are frozen under `library/`;\n"
        "unselected catalog operators are not copied.\n\n"
        "| stage | active | what it does | source |\n"
        "| --- | --- | --- | --- |\n" + "\n".join(rows) + "\n"
    )


def _first_docstring_line(source_text: str) -> str:
    lines = source_text.splitlines()
    index = 0
    while index < len(lines) and (not lines[index].strip() or lines[index].lstrip().startswith("#")):
        index += 1
    if index < len(lines):
        line = lines[index].strip()
        for marker in ('"""', "'''"):
            if line.startswith(marker):
                inner = line[3:].split(marker, 1)[0].strip()
                if inner:
                    return inner
                return lines[index + 1].strip() if index + 1 < len(lines) else "(no description)"
    return "(no description)"


def _binding_source_label(binding: ResolvedOperator) -> str:
    if binding.name is not None:
        return f"library/{binding.stage}/{binding.name}.py"
    return f"script/{binding.source.name}"


def _with_provenance(kind: str, source: str, source_text: str) -> str:
    return (
        f"# evolve-provenance: kind={kind} source={source} framework_version={_EVOLVE_VERSION}\n"
        "# this file is yours now - mechanism will never overwrite it; evolve it.\n\n"
        f"{source_text}"
    )
