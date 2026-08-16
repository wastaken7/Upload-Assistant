"""Provision the pinned Windows FFmpeg build used by Upload Assistant."""

from __future__ import annotations

import platform
import shutil
import stat
import zipfile
from pathlib import Path

import aiofiles
import httpx

from bin.download_integrity import verify_downloaded_asset
from src.console import logger


class FfmpegBinaryManager:
    """Download the verified Windows FFmpeg build into the runtime ``bin`` cache."""

    VERSION = "9.0.1"
    ASSET_NAME = "ffmpeg-9.0.1-essentials_build.zip"
    DOWNLOAD_URL = f"https://github.com/GyanD/codexffmpeg/releases/download/{VERSION}/{ASSET_NAME}"

    @classmethod
    def binary_path(cls, base_dir: str | Path) -> Path:
        return Path(base_dir) / "bin" / "ffmpeg" / "windows" / "x64" / "ffmpeg.exe"

    @classmethod
    def find_existing_binary(cls, base_dir: str | Path) -> str | None:
        binary = cls.binary_path(base_dir)
        version_marker = binary.parent / f"version_{cls.VERSION}"
        if binary.is_file() and version_marker.is_file():
            return str(binary)
        binary_name = "ffmpeg.exe" if platform.system().lower() == "windows" else "ffmpeg"
        return shutil.which(binary_name)

    @classmethod
    async def ensure_ffmpeg_binary(cls, base_dir: str | Path) -> str:
        existing_binary = cls.find_existing_binary(base_dir)
        if existing_binary:
            return existing_binary

        if platform.system().lower() != "windows":
            raise RuntimeError("FFmpeg was not found on PATH; install it with your system package manager or configure ffmpeg_path.")

        binary = cls.binary_path(base_dir)
        binary.parent.mkdir(parents=True, exist_ok=True)
        archive = binary.parent / f"temp_{cls.ASSET_NAME}"
        logger.info(f"[yellow]Downloading FFmpeg {cls.VERSION}...[/yellow]")
        try:
            async with (
                httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client,
                client.stream("GET", cls.DOWNLOAD_URL) as response,
            ):
                response.raise_for_status()
                async with aiofiles.open(archive, "wb") as output:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        await output.write(chunk)

            verify_downloaded_asset(archive, cls.ASSET_NAME)
            with zipfile.ZipFile(archive) as zip_file:
                member = next((name for name in zip_file.namelist() if Path(name).name.lower() == "ffmpeg.exe"), None)
                if member is None:
                    raise RuntimeError(f"ffmpeg.exe was not found in {cls.ASSET_NAME}")
                info = zip_file.getinfo(member)
                if stat.S_ISLNK(info.external_attr >> 16) or Path(member).is_absolute() or ".." in Path(member).parts:
                    raise RuntimeError(f"Unsafe FFmpeg archive member: {member}")
                with zip_file.open(info) as source, binary.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

            (binary.parent / f"version_{cls.VERSION}").write_text(f"FFmpeg {cls.VERSION}\n", encoding="utf-8")
            return str(binary)
        finally:
            if archive.exists():
                archive.unlink()
