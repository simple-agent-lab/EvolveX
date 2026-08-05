"""Harbor MiniSWE adapter that transports task text through a container file."""

from __future__ import annotations

import json
import re
import shlex
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from harbor.agents.installed.mini_swe_agent import MiniSweAgent

if TYPE_CHECKING:
    from harbor.environments.base import BaseEnvironment

TASK_PATH = "/tmp/evolve-miniswe-task.md"
SHIM_PATH = "/tmp/evolve-miniswe-file-task.py"
RESPONSES_CONFIG_PATH = "/tmp/evolve-miniswe-responses.yaml"
_LAUNCH = "mini-swe-agent --yolo "
_TASK = " --task="
_OUTPUT = " --output="
_EXIT = " --exit-immediately"

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


class InstalledMiniSweAgent(MiniSweAgent):
    async def exec_as_agent(
        self,
        environment: BaseEnvironment,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ) -> Any:
        launch = command.find(_LAUNCH)
        task = command.find(_TASK, launch)
        output = command.rfind(_OUTPUT)
        if launch < 0 or task < 0 or output < task:
            return await super().exec_as_agent(
                environment, command=command, env=env, cwd=cwd, timeout_sec=timeout_sec
            )

        values = shlex.split(command[task + len(_TASK) : output])
        if len(values) != 1:
            raise RuntimeError("unable to decode MiniSWE task argument")

        uses_responses = "model.model_class=litellm_response" in command
        cache_key = f"evolve-{uuid.uuid4().hex}"
        command_tokens = shlex.split(command)
        has_output_budget = any(
            flag == "-c" and re.fullmatch(r"model\.model_kwargs\.max_output_tokens=\d+", value)
            for flag, value in zip(command_tokens, command_tokens[1:], strict=False)
        )
        model_kwargs = {
            "include": ["reasoning.encrypted_content"],
            "prompt_cache_key": cache_key,
            "extra_headers": {"extra": json.dumps({"session_id": cache_key}, separators=(",", ":"))},
        }
        if not has_output_budget:
            model_kwargs["max_output_tokens"] = 64_000
        responses_config = {"model": {"model_kwargs": model_kwargs}}
        with tempfile.TemporaryDirectory(prefix="evolve-miniswe-task-") as tempdir:
            root = Path(tempdir)
            task_file = root / "task.md"
            shim_file = root / "runner.py"
            task_file.write_text(values[0])
            shim_file.write_text(_SHIM)
            await environment.upload_file(task_file, TASK_PATH)
            await environment.upload_file(shim_file, SHIM_PATH)
            if uses_responses:
                config_file = root / "responses.yaml"
                config_file.write_text(json.dumps(responses_config))
                await environment.upload_file(config_file, RESPONSES_CONFIG_PATH)

        prefix = command[:launch]
        flags_before_task = command[launch + len("mini-swe-agent") : task]
        flags_after_task = command[output:]
        if uses_responses:
            exit_marker = flags_after_task.find(_EXIT)
            if exit_marker < 0:
                raise RuntimeError("unable to locate MiniSWE exit flag")
            flags_after_task = (
                flags_after_task[:exit_marker] + f" -c {RESPONSES_CONFIG_PATH}" + flags_after_task[exit_marker:]
            )
        file_launch = (
            'MSWEA_BIN="$(command -v mini-swe-agent)"; '
            'MSWEA_PY="$(head -n 1 "$MSWEA_BIN")"; '
            'MSWEA_PY="${MSWEA_PY#\\#!}"; '
            f'"$MSWEA_PY" {SHIM_PATH} "$MSWEA_BIN"'
        )
        rewritten = prefix + file_launch + flags_before_task + f" --task-file={TASK_PATH}" + flags_after_task
        return await super().exec_as_agent(
            environment, command=rewritten, env=env, cwd=cwd, timeout_sec=timeout_sec
        )


FileTaskMiniSweAgent = InstalledMiniSweAgent
