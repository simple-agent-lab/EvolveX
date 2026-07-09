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
                "python - <<'PY'\n"
                "import pathlib, shutil, subprocess, sys\n"
                "exe = shutil.which('mini-swe-agent')\n"
                "if not exe:\n"
                "    raise SystemExit('missing mini-swe-agent executable')\n"
                "shebang = pathlib.Path(exe).read_text(errors='ignore').splitlines()[0]\n"
                "if not shebang.startswith('#!'):\n"
                "    raise SystemExit(f'mini-swe-agent has no Python shebang: {exe}')\n"
                "python = shebang[2:].strip().split()[0]\n"
                "probe = \"\"\"\n"
                "import importlib.metadata as metadata\n"
                "import pathlib, sys\n"
                "import mini_swe_agent\n"
                "origin = pathlib.Path(mini_swe_agent.__file__).resolve()\n"
                "direct_url = metadata.distribution('mini-swe-agent').read_text('direct_url.json') or ''\n"
                "print(origin)\n"
                "print(direct_url)\n"
                "sys.exit(0 if '/installed-agent/miniswe-source' in direct_url else 1)\n"
                "\"\"\"\n"
                "raise SystemExit(subprocess.run([python, '-c', probe]).returncode)\n"
                "PY"
            ),
        )
