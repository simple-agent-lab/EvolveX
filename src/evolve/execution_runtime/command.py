from __future__ import annotations

import argparse
import os

from .models import ExecutionRuntimeConfig
from .resolve import resolve_execution_runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("docker-host",))
    args = parser.parse_args(argv)
    runtime = resolve_execution_runtime(ExecutionRuntimeConfig(backend="docker"), os.environ)
    if args.command == "docker-host" and runtime.docker_host:
        print(runtime.docker_host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
