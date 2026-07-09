"""LLM meta-agent asks an OpenAI-compatible chat endpoint for fenced file edits.

It applies full-file fenced responses and repairs out-of-surface changes.
"""

# ruff: noqa: E402

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult, OperatorContext
from evolve.git import head_tag, working_tree_changed_paths
from evolve.surface import check_paths, surface_patterns


class AdapterFailure(Exception):
    def __init__(self, message: str, *, output: str = "", usage: dict[str, Any] | None = None, returncode: int = 1):
        super().__init__(message)
        self.output = output
        self.usage = usage or {"usd": 0}
        self.returncode = returncode if isinstance(returncode, int) and returncode else 1


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _safe_usage(usage: object) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {"usd": 0}
    normalized = dict(usage)
    usd = normalized.get("usd", 0)
    normalized["usd"] = usd if isinstance(usd, (int, float)) and not isinstance(usd, bool) else 0
    return normalized


def _predicted_fixes(text: str) -> list[Any]:
    for line in text.splitlines():
        if line.strip().startswith("predicted_fixes:"):
            try:
                value = json.loads(line.split(":", 1)[1].strip())
            except Exception:
                return []
            return value if isinstance(value, list) else []
    return []


def _response_files(text: str) -> list[tuple[str, str]]:
    return [(name.strip(), body) for name, body in re.findall(r"```file:([^\n]+)\n(.*?)```", text, re.S)]


def _apply_fenced_file_response(text: str, checkout: Path | str = ".") -> list[str]:
    changed: list[str] = []
    root = Path(checkout)
    for rel, body in _response_files(text):
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"invalid meta-agent path: {rel}")
        dst = root / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(body)
        changed.append(path.as_posix())
    return changed


def _feedback_text(run_dir: Path) -> str:
    root = (run_dir / "feedback").resolve()
    index = root / "index.md"
    seen: set[Path] = set()
    parts: list[tuple[str, str]] = []
    if index.exists():
        text = index.read_text()
        parts.append(("feedback/index.md", text))
        seen.add(index.resolve())
        for rel in re.findall(r"\[[^\]]+\]\(([^)#]+)", text):
            path = (root / rel.strip()).resolve()
            if path.is_file() and (path == root or root in path.parents) and path not in seen:
                parts.append((f"feedback/{path.relative_to(root).as_posix()}", path.read_text()))
                seen.add(path)
    rules = root / "rules.md"
    if rules.exists() and rules.resolve() not in seen:
        parts.append(("feedback/rules.md", rules.read_text()))
    return "\n".join("## %s\n%s" % (name, text.rstrip()) for name, text in parts if text.strip())


def _surface_rule_lists(checkout: Path | str) -> tuple[list[str], list[str]]:
    try:
        return surface_patterns(Path(checkout))
    except Exception:
        return ["target/**"], []


def _meta_agent_surface_rules(checkout: Path | str = ".") -> str:
    include, exclude = _surface_rule_lists(checkout)
    return "- Surface include: %s\n- Surface exclude: %s" % (include, exclude)


def _meta_agent_prompt(checkout: Path, run_dir: Path) -> str:
    return (
        "\n\n".join(
            chunk
            for chunk in [
                (checkout / "operators" / "meta_agent.md").read_text().rstrip(),
                _feedback_text(run_dir),
                "# Surface Rules\n\n%s" % _meta_agent_surface_rules(checkout),
                '# Output Contract\n\nReturn full-file edits only as fenced blocks named like ```file:target/agent.py. Optional first line: predicted_fixes: ["task-id"].',
            ]
            if chunk
        )
        + "\n"
    )


def _llm_usd(prompt_tokens: int, completion_tokens: int) -> float:
    prompt_rate = float(os.environ.get("EVOLVE_LLM_USD_PER_1K_PROMPT", "0") or 0)
    completion_rate = float(os.environ.get("EVOLVE_LLM_USD_PER_1K_COMPLETION", "0") or 0)
    return round((prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1000.0, 6)


def _timeout_float(value: object) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timeout_headroom(timeout: float | None) -> float | None:
    if timeout is None or timeout <= 0:
        return timeout
    if timeout < 1:
        return max(0.001, timeout * 0.05)
    return max(0.01, timeout - min(5.0, max(0.5, timeout * 0.05)))


def _adapter_timeout(config: dict[str, Any]) -> float | None:
    timeout = _timeout_float(config.get("timeout_s"))
    inherited = _timeout_float(os.environ.get("EVOLVE_OPERATOR_TIMEOUT_S"))
    if inherited is None:
        return timeout
    cap = _timeout_headroom(inherited)
    return cap if timeout is None else min(timeout, cap)


def _llm_request(config: dict[str, Any], prompt: str) -> tuple[str, dict[str, Any]]:
    timeout = _adapter_timeout(config)
    if timeout is not None and timeout <= 0.01:
        raise AdapterFailure("llm timeout after %ss" % timeout)
    req = urllib.request.Request(
        os.environ["EVOLVE_LLM_BASE_URL"].rstrip("/") + "/chat/completions",
        data=json.dumps(
            {"model": os.environ["EVOLVE_LLM_MODEL"], "messages": [{"role": "user", "content": prompt}]}
        ).encode(),
        headers={
            "Authorization": "Bearer %s" % os.environ["EVOLVE_LLM_API_KEY"],
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode())
    except TimeoutError as exc:
        raise AdapterFailure("llm timeout after %ss" % timeout) from exc
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), TimeoutError):
            raise AdapterFailure("llm timeout after %ss" % timeout) from exc
        raise
    content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    usage = payload.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    return str(content), {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "usd": _llm_usd(prompt_tokens, completion_tokens),
    }


def _surface_check(checkout: Path | str = ".", parent: str | None = None) -> dict[str, Any]:
    root = Path(checkout).resolve()
    include, exclude = _surface_rule_lists(root)
    base = parent or head_tag(root) or "gen/0"
    mutated = working_tree_changed_paths(root, base)
    violations = check_paths(mutated, include, exclude)
    return {"ok": not violations, "mutated": mutated, "violations": violations}


def _repair_surface_path(path: str, checkout: Path | str = ".") -> str | None:
    candidate = Path(checkout) / path
    rel = Path(path)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        return None
    subprocess.run(["git", "checkout", "--", path], cwd=checkout, text=True, capture_output=True, check=False)
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", path], cwd=checkout, text=True, capture_output=True, check=False
    )
    if status.stdout.startswith("??"):
        if candidate.is_dir() and not candidate.is_symlink():
            shutil.rmtree(candidate)
        else:
            candidate.unlink()
        return "removed"
    return "reverted" if candidate.exists() else None


def _fallback_surface_check(checkout: Path | str = ".") -> dict[str, Any]:
    root = Path(checkout)
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--"], cwd=root, text=True, capture_output=True, check=False
    )
    changed = [line for line in tracked.stdout.splitlines() if line]
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=False)
    for line in status.stdout.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        if path not in changed:
            changed.append(path)
    include, exclude = _surface_rule_lists(root)
    violations = check_paths(changed, include, exclude)
    return {"ok": not violations, "mutated": changed, "violations": violations}


def _checked_surface(
    meta_agent_dir: Path, notes: list[str], changed: list[str], checkout: Path | str = "."
) -> dict[str, Any]:
    try:
        result = _surface_check(checkout)
    except Exception:
        try:
            result = _fallback_surface_check(checkout)
        except Exception as exc:
            result = {"ok": False, "mutated": changed, "violations": [], "error": "surface-check failed: %s" % exc}
            _write_json(meta_agent_dir / "surface-check.json", result)
            return result
    if result.get("violations"):
        reverted: list[str] = []
        removed: list[str] = []
        for path in result["violations"]:
            action = _repair_surface_path(path, checkout)
            if action == "reverted":
                reverted.append(path)
            elif action == "removed":
                removed.append(path)
        if reverted or removed:
            details = []
            if reverted:
                details.append("reverted: %s" % ", ".join(reverted))
            if removed:
                details.append("removed untracked: %s" % ", ".join(removed))
            notes.append("repaired surface violations by %s" % "; ".join(details))
        try:
            result = _surface_check(checkout)
        except Exception:
            try:
                result = _fallback_surface_check(checkout)
            except Exception as exc:
                result = {"ok": False, "mutated": changed, "violations": [], "error": "surface-check failed: %s" % exc}
    _write_json(meta_agent_dir / "surface-check.json", result)
    return result


def _write_meta_agent_artifacts(
    *,
    run_dir: Path,
    notes: list[str],
    output: str = "",
    usage: dict[str, Any] | None = None,
    variant: str,
    surface: dict[str, Any] | None = None,
    changed: list[str] | None = None,
) -> dict[str, Any]:
    meta_agent_dir = run_dir / "meta_agent"
    meta_agent_dir.mkdir(parents=True, exist_ok=True)
    notes.extend(["written-by: operators/meta_agent.py", "variant: %s" % variant])
    if output.strip():
        notes.append("agent-output: %s" % output.strip().splitlines()[0])
    if surface is None:
        surface = {"ok": True, "mutated": changed or [], "violations": []}
    _write_json(meta_agent_dir / "surface-check.json", surface)
    usage_payload = _safe_usage(usage or {"usd": 0})
    (meta_agent_dir / "rationale.md").write_text("\n".join(notes) + "\n")
    (meta_agent_dir / "predicted_fixes.json").write_text(json.dumps(_predicted_fixes(output)) + "\n")
    _write_json(meta_agent_dir / "usage.json", usage_payload)
    return usage_payload


class LlmMetaAgent(MetaAgentOperator):
    def run(self, checkout: Path, observation: str, ctx: OperatorContext) -> MetaAgentResult:
        notes: list[str] = []
        output = ""
        usage = {"usd": 0}
        changed: list[str] = []
        returncode = 0
        try:
            prompt = _meta_agent_prompt(checkout, ctx.run_dir)
            output, usage = _llm_request(ctx.config, prompt)
            changed = _apply_fenced_file_response(output, checkout)
        except AdapterFailure as exc:
            output = exc.output or output
            usage = _safe_usage(exc.usage or usage)
            notes.append("error: %s" % exc)
            returncode = exc.returncode
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            notes.append("error: %s" % (exc.code if exc.code else "meta-agent exited"))
            returncode = code if code else 1
        except Exception as exc:
            notes.append("error: %s: %s" % (exc.__class__.__name__, exc))
            returncode = 1
        surface = _checked_surface(ctx.run_dir / "meta_agent", notes, changed, checkout)
        usage = _write_meta_agent_artifacts(
            run_dir=ctx.run_dir,
            notes=notes,
            output=output,
            usage=usage,
            variant="llm",
            surface=surface,
            changed=changed,
        )
        if returncode:
            raise SystemExit(returncode)
        if not surface.get("ok"):
            raise SystemExit(1)
        return MetaAgentResult(changed=changed, notes=notes, usage=usage)


if __name__ == "__main__":
    sdk.main(LlmMetaAgent)
