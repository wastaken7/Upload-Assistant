#!/usr/bin/env python3
# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Download the official MediaInfo CLI used by Upload Assistant."""

import asyncio
import os
import platform
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import aiofiles
import httpx

from bin.download_integrity import verify_downloaded_asset

try:
    from src.console import logger
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)


class MediaInfoBinaryManager:
    """Install the pinned official MediaInfo CLI into ``bin/MI``."""

    VERSION = "26.05"
    BASE_URL = "https://old.mediaarea.net/download/binary/mediainfo"

    @staticmethod
    def _is_android() -> bool:
        return sys.platform == "android" or os.environ.get("PREFIX", "").startswith("/data/data/com.termux/")

    @staticmethod
    def _is_macos() -> bool:
        return platform.system().lower() == "darwin"

    @classmethod
    def _platform_info(cls) -> tuple[str, str, str, str]:
        system = platform.system().lower()
        machine = platform.machine().lower()
        if system == "windows" and machine in {"amd64", "x86_64"}:
            return "windows", "MediaInfo_CLI_26.05_Windows_x64.zip", "MediaInfo.exe", "zip"
        if system == "windows" and machine in {"arm64", "aarch64"}:
            return "windows/arm64", "MediaInfo_CLI_26.05_Windows_ARM64.zip", "MediaInfo.exe", "zip"
        if system == "linux" and machine in {"amd64", "x86_64"}:
            return "linux", "MediaInfo_CLI_26.05_Lambda_x86_64.zip", "mediainfo", "zip"
        if system == "linux" and machine in {"arm64", "aarch64"}:
            return "linux/arm64", "MediaInfo_CLI_26.05_Lambda_arm64.zip", "mediainfo", "zip"
        if system == "darwin" and machine in {"amd64", "x86_64", "arm64", "aarch64"}:
            return "macos", "MediaInfo_CLI_26.05_Mac.dmg", "mediainfo", "dmg"
        raise RuntimeError(f"Unsupported MediaInfo platform: {system} {machine}")

    @classmethod
    def binary_path(cls, base_dir: str | Path) -> Path:
        folder, _archive, binary_name, _archive_type = cls._platform_info()
        return Path(base_dir) / "bin" / "MI" / folder / binary_name

    @classmethod
    def find_existing_binary(cls, base_dir: str | Path) -> str | None:
        if cls._is_android():
            return shutil.which("mediainfo")
        try:
            binary = cls.binary_path(base_dir)
        except RuntimeError:
            return shutil.which("mediainfo")
        if binary.is_file() and (binary.suffix.lower() == ".exe" or os.access(binary, os.X_OK)):
            return str(binary)
        return shutil.which("mediainfo")

    @classmethod
    async def ensure_mediainfo_binary(cls, base_dir: str | Path) -> str:
        if cls._is_android():
            binary = cls.find_existing_binary(base_dir)
            if binary:
                logger.debug(f"[blue]Using MediaInfo from Android PATH: {binary}[/blue]")
                return binary
            raise RuntimeError("MediaInfo is required on Android/Termux. Install it with: pkg install mediainfo")

        folder, archive_name, binary_name, archive_type = cls._platform_info()
        binary = Path(base_dir) / "bin" / "MI" / folder / binary_name
        version_marker = binary.parent / f"version_{cls.VERSION}"
        if version_marker.is_file() and binary.is_file():
            return str(binary)

        binary.parent.mkdir(parents=True, exist_ok=True)
        archive = binary.parent / f"temp_{archive_name}"
        url = f"{cls.BASE_URL}/{cls.VERSION}/{archive_name}"
        logger.info(f"[yellow]Downloading MediaInfo CLI {cls.VERSION}...[/yellow]")
        try:
            async with (
                httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                async with aiofiles.open(archive, "wb") as output:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        await output.write(chunk)

            verify_downloaded_asset(archive, archive_name)

            if archive_type == "zip":
                with zipfile.ZipFile(archive) as zip_file:
                    member = next((name for name in zip_file.namelist() if Path(name).name == binary_name), None)
                    if member is None:
                        raise RuntimeError(f"{binary_name} was not found in {archive_name}")
                    info = zip_file.getinfo(member)
                    if stat.S_ISLNK(info.external_attr >> 16) or Path(member).is_absolute() or ".." in Path(member).parts:
                        raise RuntimeError(f"Unsafe MediaInfo archive member: {member}")
                    with zip_file.open(info) as source, binary.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
            elif archive_type == "dmg":
                await cls._extract_macos_binary(archive, binary)
            else:
                raise RuntimeError(f"Unsupported MediaInfo archive type: {archive_type}")

            if binary.suffix.lower() != ".exe":
                binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
            version_marker.write_text(f"MediaInfo CLI {cls.VERSION}\n", encoding="utf-8")
            return str(binary)
        finally:
            if archive.exists():
                archive.unlink()

    @staticmethod
    async def _extract_macos_binary(archive: Path, binary: Path) -> None:
        """Mount the official DMG, expand its package, and copy the CLI executable."""
        attached = await asyncio.to_thread(
            subprocess.run,
            ["hdiutil", "attach", "-nobrowse", "-readonly", "-plist", str(archive)],
            check=True,
            capture_output=True,
        )
        mount_point: Path | None = None
        extracted_package: Path | None = None
        try:
            devices = plistlib.loads(attached.stdout).get("system-entities", [])
            mount = next((item.get("mount-point") for item in devices if item.get("mount-point")), None)
            if not mount:
                raise RuntimeError("MediaInfo DMG did not provide a mount point")
            mount_point = Path(mount)
            package = next((path for path in mount_point.rglob("mediainfo.pkg") if path.is_file()), None)
            if package is None:
                raise RuntimeError(f"mediainfo.pkg was not found in {archive.name}")
            extracted_package = Path(tempfile.mkdtemp(prefix="mediainfo-pkg-", dir=binary.parent))
            await asyncio.to_thread(
                subprocess.run,
                ["pkgutil", "--expand-full", str(package), str(extracted_package)],
                check=True,
                capture_output=True,
            )
            payload = next(extracted_package.rglob("Payload"), None)
            if payload is None:
                raise RuntimeError(f"MediaInfo package did not contain a payload: {package.name}")
            payload_root = extracted_package / "payload"
            payload_root.mkdir()
            await asyncio.to_thread(
                subprocess.run,
                ["bsdtar", "-xf", str(payload), "-C", str(payload_root)],
                check=True,
                capture_output=True,
            )
            source = next((path for path in payload_root.rglob("mediainfo") if path.is_file()), None)
            if source is None:
                raise RuntimeError(f"mediainfo was not found in {archive.name}")
            await asyncio.to_thread(shutil.copy2, source, binary)
        finally:
            if extracted_package is not None:
                await asyncio.to_thread(shutil.rmtree, extracted_package, ignore_errors=True)
            if mount_point is not None:
                await asyncio.to_thread(
                    subprocess.run,
                    ["hdiutil", "detach", str(mount_point)],
                    check=True,
                    capture_output=True,
                )
