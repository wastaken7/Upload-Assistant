# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
import platform
import shutil
import stat
import tarfile
from pathlib import Path

import aiofiles
import httpx

from bin.download_integrity import verify_downloaded_asset

try:
    from src.console import console, logger
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    class SimpleConsole:
        def print(self, message: str, markup: bool = False) -> None:  # noqa: ARG002
            print(message)

    console = SimpleConsole()
    logger = logging.getLogger(__name__)


class SevenZipBinaryManager:
    """Download 7-Zip binaries for the host architecture."""

    @staticmethod
    async def ensure_7z_binary(base_dir: str | Path, version: str = "26.01") -> str:
        system = platform.system().lower()
        machine = platform.machine().lower()
        logger.debug(f"[blue]7-Zip: Detected system: {system}, architecture: {machine}[/blue]")

        platform_map: dict[str, dict[str, dict[str, str]]] = {
            "windows": {
                "x86_64": {"file": "7zr.exe", "folder": "windows/x86_64"},
                "amd64": {"file": "7zr.exe", "folder": "windows/x86_64"},
                "x86": {"file": "7zr.exe", "folder": "windows/x86"},
                "arm64": {"file": "7zr.exe", "folder": "windows/arm64"},
            },
            "darwin": {
                "arm64": {"file": "7z2601-mac.tar.xz", "folder": "macos/arm64"},
                "x86_64": {"file": "7z2601-mac.tar.xz", "folder": "macos/x86_64"},
                "amd64": {"file": "7z2601-mac.tar.xz", "folder": "macos/x86_64"},
            },
            "linux": {
                "x86_64": {"file": "7z2601-linux-x64.tar.xz", "folder": "linux/amd64"},
                "amd64": {"file": "7z2601-linux-x64.tar.xz", "folder": "linux/amd64"},
                "arm64": {"file": "7z2601-linux-arm64.tar.xz", "folder": "linux/arm64"},
                "aarch64": {"file": "7z2601-linux-arm64.tar.xz", "folder": "linux/arm64"},
                "arm": {"file": "7z2601-linux-arm.tar.xz", "folder": "linux/arm"},
                "armv7l": {"file": "7z2601-linux-arm.tar.xz", "folder": "linux/arm"},
                "armv6l": {"file": "7z2601-linux-arm.tar.xz", "folder": "linux/arm"},
            },
        }

        if system not in platform_map or machine not in platform_map[system]:
            raise Exception(f"Unsupported platform for 7z: {system} {machine}")

        platform_info = platform_map[system][machine]
        file_pattern = platform_info["file"]
        folder_path = platform_info["folder"]

        bin_dir = Path(base_dir) / "bin" / "7z" / folder_path
        bin_dir.mkdir(parents=True, exist_ok=True)

        binary_name = "7zr.exe" if system == "windows" else "7zz"
        binary_path = bin_dir / binary_name
        version_path = bin_dir / version

        binary_exists = binary_path.exists() and binary_path.is_file()
        binary_executable = system == "windows" or os.access(binary_path, os.X_OK)
        binary_valid = binary_exists and binary_executable

        if version_path.exists() and version_path.is_file() and binary_valid:
            logger.debug("[blue]7-Zip binary is up to date[/blue]")
            return str(binary_path)

        logger.info("[yellow]Binary '7z' not found. Attempting to download automatically...[/yellow]")

        # Cleanup old files
        if binary_path.exists():
            binary_path.unlink()
        if version_path.exists():
            version_path.unlink()

        download_url = f"https://github.com/ip7z/7zip/releases/download/{version}/{file_pattern}"
        logger.debug(f"[blue]7-Zip Download URL: {download_url}[/blue]")

        try:
            async with (
                httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client,
                client.stream("GET", download_url, timeout=60.0) as response,
            ):
                response.raise_for_status()
                temp_file = bin_dir / f"temp_{file_pattern}"
                async with aiofiles.open(temp_file, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        await f.write(chunk)

            logger.debug(f"[green]Downloaded 7-Zip package: {file_pattern}[/green]")
            verify_downloaded_asset(temp_file, file_pattern)

            if file_pattern.endswith(".exe"):
                # Windows 7zr.exe is a raw executable
                shutil.move(str(temp_file), str(binary_path))
            else:
                # Linux/macOS are tar.xz archives
                try:
                    with tarfile.open(temp_file, "r:xz") as tar_ref:
                        # Secure extract: prevent path traversal
                        for member in tar_ref.getmembers():
                            if member.islnk() or member.issym():
                                continue
                            if Path(member.name).is_absolute() or ".." in member.name or member.name.startswith("/"):
                                continue
                            full_path = os.path.realpath(Path(bin_dir) / member.name)
                            base_path = os.path.realpath(bin_dir)
                            if not full_path.startswith(base_path + os.sep) and full_path != base_path:
                                continue
                            tar_ref.extract(member, str(bin_dir))

                    # Locate 7zz binary in extracted output
                    if not binary_path.exists():
                        for p in bin_dir.rglob("7zz"):
                            if p.is_file():
                                shutil.move(str(p), str(binary_path))
                                break
                finally:
                    if temp_file.exists():
                        temp_file.unlink()

            if system != "windows" and binary_path.exists():
                binary_path.chmod(binary_path.stat().st_mode | stat.S_IEXEC)

            async with aiofiles.open(version_path, "w", encoding="utf-8") as version_file:
                await version_file.write(f"7-Zip version {version} installed successfully.")

            return str(binary_path)

        except Exception as e:
            raise Exception(f"Failed to setup 7z binary: {e}") from e
