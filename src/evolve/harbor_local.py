"""Minimal in-place Harbor environment for a pre-configured local agent runtime.

This backend deliberately provides execution, not isolation.  Harbor commands run
in the current process namespace and therefore share its filesystem, network, and
credentials.  Its primary use case is quickly evaluating an already installed
local agent, such as Codex iterating on a skill or another small behavior, without
starting Docker for every trial.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path, PurePath

from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import (
    EnvironmentCapabilities,
    EnvironmentResourceCapabilities,
)
from harbor.models.trial.paths import EnvironmentPaths


class LocalEnvironment(BaseEnvironment):
    """Run a Harbor trial directly in the current process environment.

    ``workdir`` defaults to the task's ``[environment].workdir`` and then the
    current directory. This backend intentionally does not provide isolation,
    resource enforcement, mount emulation, or concurrency control.
    """

    def __init__(
        self,
        *args,
        workdir: str | None = None,
        root_dir: str | None = None,
        workspace_dir: str | None = None,
        **kwargs,
    ) -> None:
        self._workdir_override = workdir
        super().__init__(*args, **kwargs)
        self._workdir = self._workdir_override or self.task_env_config.workdir or "/app"
        self._workspace_dir = Path(workspace_dir).expanduser().resolve() if workspace_dir else None
        if self._workspace_dir is not None and not self._workspace_dir.is_dir():
            raise NotADirectoryError(self._workspace_dir)
        self._root_dir = (
            Path(root_dir).expanduser().resolve()
            if root_dir
            else (self.trial_paths.trial_dir / "local-environment").resolve()
        )
        self._path_map = self._build_path_map()

    @staticmethod
    def type() -> str:
        return "evolve-local"

    @classmethod
    def resource_capabilities(cls) -> EnvironmentResourceCapabilities:
        return EnvironmentResourceCapabilities()

    @property
    def capabilities(self) -> EnvironmentCapabilities:
        return EnvironmentCapabilities(windows=os.name == "nt")

    def _validate_definition(self) -> None:
        # Dockerfiles and compose files describe container construction. A local
        # environment assumes the current process is already configured and
        # intentionally ignores them.
        return None

    def _build_path_map(self) -> dict[str, Path]:
        paths = EnvironmentPaths.for_os(self.os)
        virtual_paths = {
            str(paths.logs_dir),
            str(paths.agent_dir),
            str(paths.verifier_dir),
            str(paths.artifacts_dir),
            str(paths.tests_dir),
            str(paths.solution_dir),
            str(paths.default_skills_dir),
            self._workdir,
        }
        if os.name == "nt":
            virtual_paths.update({"C:/app", "C:/installed-agent", "C:/tmp"})
        else:
            virtual_paths.update({"/app", "/installed-agent", "/tmp"})
        mapped = {virtual: self._root_dir / self._relative_virtual_path(virtual) for virtual in virtual_paths}
        if self._workspace_dir is not None:
            mapped[self._workdir] = self._workspace_dir
        return mapped

    @staticmethod
    def _relative_virtual_path(path: str) -> Path:
        normalized = path.replace("\\", "/")
        if len(normalized) >= 2 and normalized[1] == ":":
            normalized = f"{normalized[0]}/{normalized[2:].lstrip('/')}"
        return Path(normalized.lstrip("/"))

    def _map_path(self, path: PurePath | str) -> Path:
        raw = str(path)
        normalized = raw.replace("\\", "/")
        for virtual, local in sorted(self._path_map.items(), key=lambda item: len(item[0]), reverse=True):
            prefix = virtual.replace("\\", "/").rstrip("/")
            if normalized == prefix:
                return local
            if normalized.startswith(prefix + "/"):
                return local / normalized[len(prefix) + 1 :]
        return Path(path)

    def _rewrite_command(self, command: str) -> str:
        virtual_paths = sorted(self._path_map.keys(), key=lambda path: len(path), reverse=True)
        pattern = re.compile("(?:" + "|".join(re.escape(path) for path in virtual_paths) + r")(?=$|[/\\\s'\"=:;,])")
        return pattern.sub(
            lambda match: self._quote_mapped_path(command, match.start(), str(self._path_map[match.group(0)])),
            command,
        )

    @staticmethod
    def _quote_mapped_path(command: str, offset: int, path: str) -> str:
        if os.name == "nt":
            return subprocess.list2cmdline([path])
        quote = LocalEnvironment._active_quote(command[:offset])
        if quote == "'":
            return path.replace("'", "'\"'\"'")
        if quote == '"':
            return path.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
        return shlex.quote(path)

    @staticmethod
    def _active_quote(prefix: str) -> str | None:
        quote: str | None = None
        index = 0
        while index < len(prefix):
            char = prefix[index]
            if quote == "'":
                if char == "'":
                    quote = None
            elif quote == '"':
                if char == '"':
                    quote = None
                elif char == "\\" and index + 1 < len(prefix):
                    index += 1
            elif char in {"'", '"'}:
                quote = char
            elif char == "\\" and index + 1 < len(prefix):
                index += 1
            index += 1
        return quote

    def _map_env(self, values: dict[str, str] | None) -> dict[str, str]:
        mapped: dict[str, str] = {}
        for name, value in (values or {}).items():
            local_path = str(self._map_path(value))
            mapped[name] = local_path if local_path != value else value
        return mapped

    def _local_environment_vars(self) -> dict[str, str]:
        paths = EnvironmentPaths.for_os(self.os)
        return {
            "EVOLVE_LOCAL_ROOT": str(self._root_dir),
            "HARBOR_WORKDIR": str(self._map_path(self._workdir)),
            "HARBOR_LOGS_DIR": str(self._map_path(paths.logs_dir)),
            "HARBOR_TESTS_DIR": str(self._map_path(paths.tests_dir)),
            "HARBOR_SOLUTION_DIR": str(self._map_path(paths.solution_dir)),
        }

    async def start(self, force_build: bool) -> None:
        if force_build:
            raise ValueError("evolve-local cannot build task environments")
        self._root_dir.mkdir(parents=True, exist_ok=True)
        for path in self._path_map.values():
            path.mkdir(parents=True, exist_ok=True)
        if self._mounts:
            self.logger.warning("evolve-local ignores Harbor mount configuration")

    async def stop(self, delete: bool) -> None:
        del delete  # The current process environment is caller-owned.

    @staticmethod
    def _copy_dir_contents(source: Path, target: Path) -> None:
        if not source.is_dir():
            raise FileNotFoundError(source)
        target.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            destination = target / child.name
            if child.is_dir() and not child.is_symlink():
                shutil.copytree(child, destination, dirs_exist_ok=True, symlinks=True)
            elif child.is_symlink():
                if destination.exists() or destination.is_symlink():
                    destination.unlink()
                destination.symlink_to(os.readlink(child))
            else:
                shutil.copy2(child, destination)

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        source = Path(source_path)
        target = self._map_path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    async def upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        self._copy_dir_contents(Path(source_dir), self._map_path(target_dir))

    async def download_file(self, source_path: str, target_path: Path | str) -> None:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._map_path(source_path), target)

    async def download_dir(self, source_dir: str, target_dir: Path | str) -> None:
        self._copy_dir_contents(self._map_path(source_dir), Path(target_dir))

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        if self._resolve_user(user) is not None:
            self.logger.debug("evolve-local runs commands as the current process user")
        process_env = os.environ.copy()
        process_env.update(self._local_environment_vars())
        process_env.update(self._map_env(self._merge_env(env)))

        rewritten_command = self._rewrite_command(command)
        self.logger.debug("evolve-local exec: %s", rewritten_command)
        process = await asyncio.create_subprocess_shell(
            rewritten_command,
            cwd=self._map_path(cwd or self._workdir),
            env=process_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_raw, stderr_raw = await asyncio.wait_for(process.communicate(), timeout=timeout_sec)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise

        stdout = stdout_raw.decode(errors="replace")
        stderr = stderr_raw.decode(errors="replace")
        self.logger.debug(
            "evolve-local exit=%s stdout=%r stderr=%r",
            process.returncode,
            stdout,
            stderr,
        )
        callback = self._output_callback()
        if callback is not None:
            if stdout:
                await callback(stdout, "stdout")
            if stderr:
                await callback(stderr, "stderr")
        return ExecResult(stdout=stdout, stderr=stderr, return_code=process.returncode or 0)
