"""Agent-command mutate delegates mutation to a configured shell command.

It passes the assembled prompt via EVOLVE_PROMPT_FILE and repairs surface leaks.
"""

# ruff: noqa: E402

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import MutateOperator, MutateResult, OperatorContext
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


def _mutate_surface_rules(checkout: Path | str = ".") -> str:
    include, exclude = _surface_rule_lists(checkout)
    return "- Surface include: %s\n- Surface exclude: %s" % (include, exclude)


def _mutate_prompt(checkout: Path, run_dir: Path) -> str:
    return (
        "\n\n".join(
            chunk
            for chunk in [
                (checkout / "operators" / "mutate.md").read_text().rstrip(),
                _feedback_text(run_dir),
                "# Surface Rules\n\n%s" % _mutate_surface_rules(checkout),
                '# Output Contract\n\nEdit the checkout directly. Do not output patches, diffs, or fenced file blocks. Optional final line: predicted_fixes: ["task-id"].',
            ]
            if chunk
        )
        + "\n"
    )


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


def _agent_command(config: dict[str, Any], prompt: str, checkout: Path | str = ".") -> tuple[str, dict[str, Any]]:
    start = time.monotonic()
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(prompt)
        prompt_file = handle.name
    env = {**os.environ, "EVOLVE_PROMPT_FILE": prompt_file}
    timeout = _adapter_timeout(config)
    try:
        if timeout is not None and timeout <= 0.01:
            usage = {"wall_s": round(time.monotonic() - start, 6), "usd": 0}
            raise AdapterFailure("agent_command timeout after %ss" % timeout, usage=usage)
        proc = subprocess.Popen(
            ["sh", "-c", str(config["command"])],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=checkout,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, 9)
            except Exception:
                proc.kill()
            stdout, stderr = proc.communicate()
            output = (stdout or "") + (
                (stderr or "") if not stderr else ("\n" if stdout and not stdout.endswith("\n") else "") + stderr
            )
            usage = {"wall_s": round(time.monotonic() - start, 6), "usd": 0}
            raise AdapterFailure("agent_command timeout after %ss" % timeout, output=output, usage=usage)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        output = stdout + (stderr if not stderr else ("\n" if stdout and not stdout.endswith("\n") else "") + stderr)
        usage = {"wall_s": round(time.monotonic() - start, 6), "usd": 0}
        raise AdapterFailure("agent_command timeout after %ss" % timeout, output=output, usage=usage)
    finally:
        Path(prompt_file).unlink(missing_ok=True)
    output = (stdout or "") + (
        (stderr or "") if not stderr else ("\n" if stdout and not stdout.endswith("\n") else "") + stderr
    )
    usage = {"wall_s": round(time.monotonic() - start, 6), "usd": 0}
    if proc.returncode != 0:
        raise AdapterFailure(
            stderr or stdout or "agent_command failed", output=output, usage=usage, returncode=proc.returncode
        )
    return output, usage


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
    mutate_dir: Path, notes: list[str], changed: list[str], checkout: Path | str = "."
) -> dict[str, Any]:
    try:
        result = _surface_check(checkout)
    except Exception:
        try:
            result = _fallback_surface_check(checkout)
        except Exception as exc:
            result = {"ok": False, "mutated": changed, "violations": [], "error": "surface-check failed: %s" % exc}
            _write_json(mutate_dir / "surface-check.json", result)
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
    _write_json(mutate_dir / "surface-check.json", result)
    return result


def _write_mutate_artifacts(
    *,
    run_dir: Path,
    notes: list[str],
    output: str = "",
    usage: dict[str, Any] | None = None,
    variant: str,
    surface: dict[str, Any] | None = None,
    changed: list[str] | None = None,
) -> dict[str, Any]:
    mutate_dir = run_dir / "mutate"
    mutate_dir.mkdir(parents=True, exist_ok=True)
    notes.extend(["written-by: operators/mutate.py", "variant: %s" % variant])
    if output.strip():
        notes.append("agent-output: %s" % output.strip().splitlines()[0])
    if surface is None:
        surface = {"ok": True, "mutated": changed or [], "violations": []}
    _write_json(mutate_dir / "surface-check.json", surface)
    usage_payload = _safe_usage(usage or {"usd": 0})
    (mutate_dir / "rationale.md").write_text("\n".join(notes) + "\n")
    (mutate_dir / "predicted_fixes.json").write_text(json.dumps(_predicted_fixes(output)) + "\n")
    _write_json(mutate_dir / "usage.json", usage_payload)
    return usage_payload


class AgentCommandMutate(MutateOperator):
    def mutate(self, checkout: Path, observation: str, ctx: OperatorContext) -> MutateResult:
        notes: list[str] = []
        output = ""
        usage = {"usd": 0}
        changed: list[str] = []
        returncode = 0
        surface = None
        timeout = _adapter_timeout(ctx.config)
        try:
            if timeout is not None and timeout <= 0.01:
                notes.append("error: agent_command timeout after %ss" % timeout)
                usage = {"wall_s": 0, "usd": 0}
                returncode = 1
                surface = {"ok": True, "mutated": [], "violations": []}
            else:
                output, usage = _agent_command(ctx.config, _mutate_prompt(checkout, ctx.run_dir), checkout)
        except AdapterFailure as exc:
            output = exc.output or output
            usage = _safe_usage(exc.usage or usage)
            notes.append("error: %s" % exc)
            returncode = exc.returncode
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            notes.append("error: %s" % (exc.code if exc.code else "mutator exited"))
            returncode = code if code else 1
        except Exception as exc:
            notes.append("error: %s: %s" % (exc.__class__.__name__, exc))
            returncode = 1
        if surface is None:
            surface = _checked_surface(ctx.run_dir / "mutate", notes, changed, checkout)
        usage = _write_mutate_artifacts(
            run_dir=ctx.run_dir,
            notes=notes,
            output=output,
            usage=usage,
            variant="agent_command",
            surface=surface,
            changed=changed,
        )
        if returncode:
            raise SystemExit(returncode)
        if not surface.get("ok"):
            raise SystemExit(1)
        return MutateResult(changed=changed, notes=notes, usage=usage)


if __name__ == "__main__":
    sdk.main(AgentCommandMutate)
