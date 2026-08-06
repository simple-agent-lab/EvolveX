#!/usr/bin/env python3
"""Prepare the frozen local SVG renderer used by poster rollout and evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

RESVG_VERSION = "0.48.1"
RELEASE_BASE = f"https://github.com/linebender/resvg/releases/download/v{RESVG_VERSION}"
FONT_COMMIT = "8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5"
FONT_BASE = f"https://raw.githubusercontent.com/google/fonts/{FONT_COMMIT}/ofl/notosans"


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    sha256: str
    archive: str
    extracted_sha256: str | None = None


RENDERER_ASSETS = {
    ("darwin", "arm64"): Asset(
        "resvg-macos-aarch64.zip",
        f"{RELEASE_BASE}/resvg-macos-aarch64.zip",
        "06440eb5aa14a28cbfc7e40ae39e1ffa71adc051b89fbaa913b4f1d9b905d09f",
        "zip",
        "50e57a945189f74ee89766a2d5b8e1a8e5254416880f9e57b36d1307e71e94ce",
    ),
    ("darwin", "x86_64"): Asset(
        "resvg-macos-x86_64.zip",
        f"{RELEASE_BASE}/resvg-macos-x86_64.zip",
        "0135923e443863db251a26bd78eabc6efb4b59d67b8cdc5469e3e1da26bc0ce2",
        "zip",
        "c1bc3012b2b94d280a943c01feea3cb1f6a14cb47107714e990d090f007390df",
    ),
    ("linux", "x86_64"): Asset(
        "resvg-linux-x86_64.tar.gz",
        f"{RELEASE_BASE}/resvg-linux-x86_64.tar.gz",
        "fa8c26495a187e592c501db15bf9e8a9fdc051d4b2b336b39703d5b59f912b9d",
        "tar.gz",
        "8d1dbe4d8e56d3d052668afc69d9d93fba7b723b06f1d3425f29418da9a816af",
    ),
}
FONT_ASSETS = (
    Asset(
        "NotoSans.ttf",
        f"{FONT_BASE}/NotoSans%5Bwdth%2Cwght%5D.ttf",
        "bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d",
        "file",
    ),
    Asset(
        "NotoSans-Italic.ttf",
        f"{FONT_BASE}/NotoSans-Italic%5Bwdth%2Cwght%5D.ttf",
        "58e6e0ebd1931b29a365aa2d3e2ee9a9e831a3af7cf3ad1462d4e72154f0b291",
        "file",
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_platform() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    machine = {"aarch64": "arm64", "amd64": "x86_64"}.get(machine, machine)
    return system, machine


def renderer_asset(system: str | None = None, machine: str | None = None) -> Asset:
    resolved_system, resolved_machine = normalized_platform()
    key = ((system or resolved_system).lower(), (machine or resolved_machine).lower())
    try:
        return RENDERER_ASSETS[key]
    except KeyError as error:
        supported = ", ".join(f"{item[0]}-{item[1]}" for item in sorted(RENDERER_ASSETS))
        raise RuntimeError(
            f"paper-poster local renderer does not support {key[0]}-{key[1]}; supported: {supported}"
        ) from error


def download(asset: Asset, destination: Path) -> None:
    request = urllib.request.Request(asset.url, headers={"User-Agent": "evolvex-paper-poster/1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    actual = sha256_file(destination)
    if actual != asset.sha256:
        raise RuntimeError(f"digest mismatch for {asset.name}: expected {asset.sha256}, got {actual}")


def extract_renderer(asset: Asset, archive: Path, destination: Path) -> None:
    if asset.archive == "zip":
        with zipfile.ZipFile(archive) as bundle:
            members = [member for member in bundle.infolist() if Path(member.filename).name == "resvg"]
            if len(members) != 1 or members[0].is_dir():
                raise RuntimeError(f"{asset.name} does not contain exactly one resvg binary")
            with bundle.open(members[0]) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    elif asset.archive == "tar.gz":
        with tarfile.open(archive, "r:gz") as bundle:
            members = [
                member for member in bundle.getmembers() if Path(member.name).name == "resvg" and member.isfile()
            ]
            if len(members) != 1:
                raise RuntimeError(f"{asset.name} does not contain exactly one resvg binary")
            source = bundle.extractfile(members[0])
            if source is None:
                raise RuntimeError(f"cannot extract resvg from {asset.name}")
            with source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    else:
        raise RuntimeError(f"unknown renderer archive format: {asset.archive}")
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if asset.extracted_sha256 is not None and sha256_file(destination) != asset.extracted_sha256:
        raise RuntimeError(f"extracted renderer digest mismatch for {asset.name}")


def descriptor(asset: Asset, wrapper_sha256: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "renderer": {
            "engine": "resvg",
            "version": RESVG_VERSION,
            "asset": asset.name,
            "archive_sha256": asset.sha256,
            "binary_sha256": asset.extracted_sha256,
        },
        "fonts": [{"name": font.name, "sha256": font.sha256} for font in FONT_ASSETS],
        "wrapper_sha256": wrapper_sha256,
        "policy": {
            "background": "#ffffff",
            "default_width": 1600,
            "font_family": "Noto Sans",
            "system_fonts": False,
        },
    }


def runtime_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def valid_runtime(root: Path, payload: dict[str, object]) -> bool:
    try:
        receipt = json.loads((root / "runtime.json").read_text())
    except (OSError, json.JSONDecodeError):
        return False
    renderer = root / "bin" / "resvg"
    wrapper = root / "bin" / "evolve-render-svg"
    renderer_config = payload.get("renderer")
    expected_renderer = renderer_config.get("binary_sha256") if isinstance(renderer_config, dict) else None
    return (
        receipt == payload
        and renderer.is_file()
        and isinstance(expected_renderer, str)
        and sha256_file(renderer) == expected_renderer
        and wrapper.is_file()
        and sha256_file(wrapper) == payload.get("wrapper_sha256")
        and all(
            (root / "fonts" / font.name).is_file() and sha256_file(root / "fonts" / font.name) == font.sha256
            for font in FONT_ASSETS
        )
    )


def install_runtime(cache_root: Path, wrapper_source: Path) -> tuple[Path, dict[str, object]]:
    import fcntl

    asset = renderer_asset()
    wrapper_sha256 = sha256_file(wrapper_source)
    payload = descriptor(asset, wrapper_sha256)
    digest = runtime_digest(payload)
    payload["runtime_digest"] = f"sha256:{digest}"
    root = cache_root / digest
    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / f".{digest}.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if valid_runtime(root, payload):
            return root, payload
        if root.exists():
            raise RuntimeError(f"paper-poster runtime cache is incomplete: {root}")
        pending = Path(tempfile.mkdtemp(prefix=f".{digest}.pending-", dir=cache_root))
        try:
            bin_dir = pending / "bin"
            fonts_dir = pending / "fonts"
            downloads = pending / "downloads"
            bin_dir.mkdir()
            fonts_dir.mkdir()
            downloads.mkdir()

            archive = downloads / asset.name
            download(asset, archive)
            extract_renderer(asset, archive, bin_dir / "resvg")
            shutil.copy2(wrapper_source, bin_dir / "evolve-render-svg")
            (bin_dir / "evolve-render-svg").chmod(
                (bin_dir / "evolve-render-svg").stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )
            for font in FONT_ASSETS:
                download(font, fonts_dir / font.name)
            shutil.rmtree(downloads)
            (pending / "runtime.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            (pending / "runtime.json").chmod(0o444)
            (bin_dir / "resvg").chmod(0o555)
            (bin_dir / "evolve-render-svg").chmod(0o555)
            for font in FONT_ASSETS:
                (fonts_dir / font.name).chmod(0o444)
            pending.replace(root)
        finally:
            if pending.exists():
                shutil.rmtree(pending)
    return root, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--env-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    wrapper = Path(__file__).with_name("render_svg.py")
    root, receipt = install_runtime(args.cache_root.resolve(), wrapper)
    renderer = (root / "bin" / "evolve-render-svg").resolve()
    args.env_out.parent.mkdir(parents=True, exist_ok=True)
    args.env_out.write_text(f"EVOLVE_SVG_RENDERER={renderer}\nEVOLVE_SVG_RUNTIME_DIGEST={receipt['runtime_digest']}\n")
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"renderer": str(renderer), "runtime_digest": receipt["runtime_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
