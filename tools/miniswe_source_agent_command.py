from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

PROXY_ENV = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")
_SECRET_NAME = re.compile(r"(?:api[_-]?key|token|secret|password|passwd|credential)", re.IGNORECASE)
_TOKEN_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:gh[opusr]|github_pat)_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
)
_CREDENTIAL_URL = re.compile(r"\b([A-Za-z][A-Za-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@([^\s]+)")


def _clear_proxy_env() -> None:
    for name in PROXY_ENV:
        os.environ.pop(name, None)


def _mirror_openai_base() -> None:
    api_base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") or os.environ.get("EVOLVE_LLM_BASE_URL")
    if api_base:
        os.environ["OPENAI_BASE_URL"] = api_base
        os.environ["OPENAI_API_BASE"] = api_base
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EVOLVE_LLM_API_KEY")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key


def _model_name() -> str:
    raw = (
        os.environ.get("EVOLVE_META_MODEL")
        or os.environ.get("EVOLVE_HARBOR_MODEL")
        or os.environ.get("EVOLVE_LLM_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or ""
    ).strip()
    if not raw:
        raise SystemExit("missing model: set EVOLVE_META_MODEL, EVOLVE_HARBOR_MODEL, EVOLVE_LLM_MODEL, or OPENAI_MODEL")
    return raw if "/" in raw else f"openai/{raw}"


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    return default if value in (None, "") else int(value)


def _float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    return default if value in (None, "") else float(value)


def _filtered(payload: dict[str, Any], fields: object) -> dict[str, Any]:
    names = set(fields)
    return {key: value for key, value in payload.items() if key in names}


def _build_agent(output_path: Path):
    from minisweagent.agents.default import AgentConfig, DefaultAgent
    from minisweagent.config import get_config_from_spec
    from minisweagent.environments.local import LocalEnvironment, LocalEnvironmentConfig
    from minisweagent.models.litellm_model import LitellmModel, LitellmModelConfig

    config = get_config_from_spec(os.environ.get("EVOLVE_META_MINISWE_CONFIG", "mini"))
    agent_kwargs = _filtered(dict(config.get("agent") or {}), AgentConfig.model_fields)
    env_kwargs = _filtered(dict(config.get("environment") or {}), LocalEnvironmentConfig.model_fields)
    model_kwargs = _filtered(dict(config.get("model") or {}), LitellmModelConfig.model_fields)

    agent_kwargs["step_limit"] = _int_env("EVOLVE_META_AGENT_STEP_LIMIT", int(agent_kwargs.get("step_limit") or 12))
    agent_kwargs["cost_limit"] = _float_env("EVOLVE_META_AGENT_COST_LIMIT", float(agent_kwargs.get("cost_limit") or 3.0))
    agent_kwargs["wall_time_limit_seconds"] = _int_env("EVOLVE_META_AGENT_WALL_TIME_LIMIT", 900)
    agent_kwargs["output_path"] = str(output_path)
    env_kwargs["cwd"] = str(Path.cwd())
    env_kwargs["timeout"] = _int_env("EVOLVE_META_ENV_TIMEOUT", int(env_kwargs.get("timeout") or 30))
    model_kwargs["model_name"] = _model_name()
    model_kwargs["cost_tracking"] = "ignore_errors"

    return DefaultAgent(LitellmModel(**model_kwargs), LocalEnvironment(**env_kwargs), **agent_kwargs)


def _prompt() -> str:
    path = os.environ.get("EVOLVE_PROMPT_FILE")
    if not path:
        raise SystemExit("missing EVOLVE_PROMPT_FILE")
    return Path(path).read_text()


def _sanitized_submission(result: object) -> str:
    if not isinstance(result, dict) or not isinstance(result.get("submission"), str):
        return ""
    text = result["submission"]
    secret_values = {
        value
        for name, value in os.environ.items()
        if value and (_SECRET_NAME.search(name) or name in PROXY_ENV)
    }
    for value in sorted(secret_values, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    text = _CREDENTIAL_URL.sub(r"\1[REDACTED]@\2", text)
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text.strip()


def _run() -> int:
    role = os.environ.get("EVOLVE_SOURCE_AGENT_ROLE", "evolution")
    output_path = Path(
        os.environ.get(
            "EVOLVE_SOURCE_AGENT_OUTPUT_PATH",
            str(Path.cwd() / "runs" / f"miniswe-source-{role}.trajectory.json"),
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = _build_agent(output_path).run(_prompt())
    submission = _sanitized_submission(result)
    if submission:
        print(submission)
    print(f"miniswe-source-agent-complete role={role}")
    print("predicted_fixes: []")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    _clear_proxy_env()
    _mirror_openai_base()
    os.environ.setdefault("MSWEA_CONFIGURED", "true")
    os.environ.setdefault("MSWEA_COST_TRACKING", "ignore_errors")
    if args.check:
        import minisweagent
        from minisweagent.agents.default import DefaultAgent
        from minisweagent.environments.local import LocalEnvironment
        from minisweagent.models.litellm_model import LitellmModel

        assert DefaultAgent and LocalEnvironment and LitellmModel
        print(f"miniswe-source-agent-ok {minisweagent.__version__} model={_model_name()}")
        return 0
    return _run()


if __name__ == "__main__":
    raise SystemExit(main())
