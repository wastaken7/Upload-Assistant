"""Lazy downloader for the third-party dynamic HDR metadata tools."""

from __future__ import annotations

import asyncio
import platform
import shutil
import stat
import tarfile
import zipfile
from pathlib import Path

import httpx

from src.console import logger

TOOLS = {
    "dovi": {"command": "dovi_tool", "repository": "quietvoid/dovi_tool", "version": "2.3.3"},
    "hdr10plus": {"command": "hdr10plus_tool", "repository": "quietvoid/hdr10plus_tool", "version": "1.7.2"},
}


def _asset_name(tool: str) -> tuple[str, str]:
    """Return the release asset name and executable extension for this host."""
    system, machine = platform.system().lower(), platform.machine().lower()
    version = TOOLS[tool]["version"]
    arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    if system == "windows":
        return f"{tool}_tool-{version}-{arch}-pc-windows-msvc.zip", ".exe"
    if system == "darwin":
        return f"{tool}_tool-{version}-universal-macOS.zip", ""
    if system == "linux" and arch in {"x86_64", "aarch64"}:
        return f"{tool}_tool-{version}-{arch}-unknown-linux-musl.tar.gz", ""
    raise RuntimeError(f"Dynamic HDR plots are not supported on {system} {machine}")


def _safe_extract(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as contents:
            members = contents.infolist()
            for member in members:
                target = (destination / member.filename).resolve()
                if not target.is_relative_to(destination_resolved) or stat.S_ISLNK(member.external_attr >> 16):
                    raise RuntimeError(f"Unsafe archive member: {member.filename}")
            contents.extractall(destination)  # noqa: S202 - each member is validated above.
    else:
        with tarfile.open(archive, "r:gz") as contents:
            members = contents.getmembers()
            for member in members:
                target = (destination / member.name).resolve()
                if not target.is_relative_to(destination_resolved) or member.issym() or member.islnk():
                    raise RuntimeError(f"Unsafe archive member: {member.name}")
            contents.extractall(destination, members=members, filter="data")


async def get_tool(base_dir: str, tool: str) -> str:
    """Return a PATH tool or download the pinned release below ``bin/``."""
    command = TOOLS[tool]["command"]
    if installed := shutil.which(command):
        return installed

    asset, extension = _asset_name(tool)
    system = platform.system().lower()
    machine = platform.machine().lower()
    target_dir = Path(base_dir) / "bin" / command / system / machine
    binary = target_dir / f"{command}{extension}"
    version_file = target_dir / TOOLS[tool]["version"]
    if binary.is_file() and version_file.is_file():
        return str(binary)

    target_dir.mkdir(parents=True, exist_ok=True)
    staging = target_dir / ".download"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    archive = staging / asset
    url = f"https://github.com/{TOOLS[tool]['repository']}/releases/download/{TOOLS[tool]['version']}/{asset}"
    logger.info(f"[yellow]Downloading {command} for dynamic HDR plots...[/yellow]")
    try:
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        await asyncio.to_thread(archive.write_bytes, response.content)
        await asyncio.to_thread(_safe_extract, archive, staging)
        candidates = [path for path in staging.rglob(f"{command}{extension}") if path.is_file()]
        if not candidates:
            raise RuntimeError(f"{asset} did not contain {command}{extension}")
        # A prior interrupted or outdated install may leave the executable or
        # its marker behind. Windows does not allow shutil.move to replace it.
        binary.unlink(missing_ok=True)
        version_file.unlink(missing_ok=True)
        shutil.move(str(candidates[0]), binary)
        if system != "windows":
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        version_file.write_text(f"{command} {TOOLS[tool]['version']}\n", encoding="utf-8")
        return str(binary)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
