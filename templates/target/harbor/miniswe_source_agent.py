from __future__ import annotations

from pathlib import Path

from harbor.agents.installed.mini_swe_agent import MiniSweAgent


class MiniSweSourceAgent(MiniSweAgent):
    async def install(self, environment):
        source_dir = Path(__file__).resolve().parent
        if not (source_dir / "pyproject.toml").is_file():
            raise RuntimeError("MiniSWE source target must contain target/pyproject.toml")
        if not (source_dir / "mini_swe_agent").is_dir():
            raise RuntimeError("MiniSWE source target must contain target/mini_swe_agent/")
        await environment.upload_dir(source_dir, "/installed-agent/miniswe-source")
        await self.exec_as_agent(
            environment,
            command="uv tool install --force /installed-agent/miniswe-source",
        )
        await self.exec_as_agent(
            environment,
            command=(
                "python -c \"import shutil, sys; "
                "exe = shutil.which('mini-swe-agent'); "
                "print(exe or 'missing mini-swe-agent'); "
                "sys.exit(0 if exe else 1)\""
            ),
        )
        await self.exec_as_agent(
            environment,
            command=(
                "uv run --project /installed-agent/miniswe-source "
                "python -c \"import pathlib, sys, mini_swe_agent; "
                "origin = pathlib.Path(mini_swe_agent.__file__).resolve(); "
                "print(origin); "
                "sys.exit(0 if '/installed-agent/miniswe-source' in str(origin) else 1)\""
            ),
        )
