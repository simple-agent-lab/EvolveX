"""Harbor MiniSWE adapter that transports task text through a container file."""

from __future__ import annotations

import shlex
import tempfile
from pathlib import Path

from harbor.agents.installed.mini_swe_agent import MiniSweAgent

TASK_PATH = "/tmp/evolve-miniswe-task.md"
SHIM_PATH = "/tmp/evolve-miniswe-file-task.py"
_LAUNCH = "mini-swe-agent --yolo "
_TASK = " --task="
_OUTPUT = " --output="

_SHIM = """from pathlib import Path
import runpy
import sys

entrypoint = sys.argv[1]
args = sys.argv[2:]
task_index = next(index for index, value in enumerate(args) if value.startswith("--task-file="))
task_path = args[task_index].split("=", 1)[1]
args[task_index] = "--task=" + Path(task_path).read_text()
sys.argv = [entrypoint, *args]
runpy.run_path(entrypoint, run_name="__main__")
"""


class FileTaskMiniSweAgent(MiniSweAgent):
    async def exec_as_agent(self, environment, command: str, env=None, **kwargs):
        launch = command.find(_LAUNCH)
        task = command.find(_TASK, launch)
        output = command.rfind(_OUTPUT)
        if launch < 0 or task < 0 or output < task:
            return await super().exec_as_agent(environment, command=command, env=env, **kwargs)

        values = shlex.split(command[task + len(_TASK) : output])
        if len(values) != 1:
            raise RuntimeError("unable to decode MiniSWE task argument")

        with tempfile.TemporaryDirectory(prefix="evolve-miniswe-task-") as tempdir:
            root = Path(tempdir)
            task_file = root / "task.md"
            shim_file = root / "runner.py"
            task_file.write_text(values[0])
            shim_file.write_text(_SHIM)
            await environment.upload_file(task_file, TASK_PATH)
            await environment.upload_file(shim_file, SHIM_PATH)

        prefix = command[:launch]
        flags_before_task = command[launch + len("mini-swe-agent") : task]
        flags_after_task = command[output:]
        file_launch = (
            'MSWEA_BIN="$(command -v mini-swe-agent)"; '
            'MSWEA_PY="$(head -n 1 "$MSWEA_BIN")"; '
            'MSWEA_PY="${MSWEA_PY#\\#!}"; '
            f'"$MSWEA_PY" {SHIM_PATH} "$MSWEA_BIN"'
        )
        rewritten = prefix + file_launch + flags_before_task + f" --task-file={TASK_PATH}" + flags_after_task
        return await super().exec_as_agent(environment, command=rewritten, env=env, **kwargs)
