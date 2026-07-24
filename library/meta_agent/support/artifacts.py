"""Shared durable-artifact paths and prompt guidance for meta-agents."""

from __future__ import annotations

import subprocess
from pathlib import Path

from evolve.frozen.interfaces import OperatorContext

ARTIFACT_ROOT = Path("artifacts")
HANDOFF_NAME = "handoff.md"


def artifact_generation_relative(genid: str) -> Path:
    """Return the generation namespace, rejecting path-like generation IDs."""
    if not genid or genid in {".", ".."} or "/" in genid or "\\" in genid:
        raise ValueError(f"invalid generation id for artifact path: {genid!r}")
    return ARTIFACT_ROOT / "generations" / genid


def artifact_generation_dir(workspace: Path, genid: str) -> Path:
    return workspace / artifact_generation_relative(genid)


def ensure_artifact_layout(workspace: Path, genid: str) -> None:
    """Create the durable host layout, including the current generation namespace."""
    (workspace / ARTIFACT_ROOT / "user").mkdir(parents=True, exist_ok=True)
    artifact_generation_dir(workspace, genid).mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "--git-path", "info/exclude"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return
    exclude = Path(result.stdout.strip())
    if not exclude.is_absolute():
        exclude = workspace / exclude
    try:
        text = exclude.read_text()
    except OSError:
        return
    if "artifacts/" not in text.splitlines():
        exclude.write_text(text + ("" if not text or text.endswith("\n") else "\n") + "artifacts/\n")


def render_artifact_guidance(ctx: OperatorContext, repository: Path) -> str:
    """Describe the durable artifact contract without inlining artifact contents."""
    current = repository / artifact_generation_relative(ctx.genid)
    lines = [
        "# Durable Artifacts",
        "",
        f"Read durable user context and prior generation files under `{repository / ARTIFACT_ROOT}`.",
        f"Your writable durable directory is `{current}`; write arbitrary useful files only within it.",
    ]
    if ctx.parent is not None:
        parent_relative = artifact_generation_relative(str(ctx.parent))
        parent_handoff_host = ctx.workspace / parent_relative / HANDOFF_NAME
        if parent_handoff_host.is_file():
            lines.append(
                f"The selected parent's handoff is `{repository / parent_relative / HANDOFF_NAME}`. "
                "Treat it as orientation, verify its claims against current evidence, and do not assume it came "
                "from the most recently executed generation."
            )
        else:
            lines.append(
                "No selected-parent handoff is available; this is non-fatal, so continue using the other evidence."
            )
    else:
        lines.append("No selected-parent handoff is available; this is non-fatal, so continue using the other evidence.")
    lines.append(
        f"At the end, you may write an optional free-form `handoff.md` at `{current / HANDOFF_NAME}` "
        "for a future child meta-agent."
    )
    return "\n".join(lines)
