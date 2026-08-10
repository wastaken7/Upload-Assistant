# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
import platform
import shutil
import stat
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


class PestoBinaryManager:
    """Download Pesto binaries for the host architecture."""

    @staticmethod
    async def ensure_pesto_binary(base_dir: str | Path, version: str = "pesto-v0.6.0") -> str:
        system = platform.system().lower()
        machine = platform.machine().lower()
        logger.debug(f"[blue]Pesto: Detected system: {system}, architecture: {machine}[/blue]")

        platform_map: dict[str, dict[str, dict[str, str]]] = {
            "windows": {
                "x86_64": {"file": "pesto-windows-x86_64.exe", "folder": "windows/x86_64"},
                "amd64": {"file": "pesto-windows-x86_64.exe", "folder": "windows/x86_64"},
            },
            "linux": {
                "x86_64": {"file": "pesto-linux-x86_64", "folder": "linux/amd64"},
                "amd64": {"file": "pesto-linux-x86_64", "folder": "linux/amd64"},
            },
        }

        if system not in platform_map or machine not in platform_map[system]:
            raise Exception(f"Unsupported platform for Pesto: {system} {machine}")

        platform_info = platform_map[system][machine]
        file_pattern = platform_info["file"]
        folder_path = platform_info["folder"]

        bin_dir = Path(base_dir) / "bin" / "pesto" / folder_path
        bin_dir.mkdir(parents=True, exist_ok=True)

        binary_name = "pesto.exe" if system == "windows" else "pesto"
        binary_path = bin_dir / binary_name
        version_path = bin_dir / version

        binary_exists = binary_path.exists() and binary_path.is_file()
        binary_executable = system == "windows" or os.access(binary_path, os.X_OK)
        binary_valid = binary_exists and binary_executable

        if version_path.exists() and version_path.is_file() and binary_valid:
            logger.debug("[blue]Pesto binary is up to date[/blue]")
            return str(binary_path)

        logger.info("[yellow]Binary 'pesto' not found. Attempting to download automatically...[/yellow]")

        # Cleanup old files
        if binary_path.exists():
            binary_path.unlink()
        if version_path.exists():
            version_path.unlink()

        download_url = f"https://github.com/franzopl/pesto/releases/download/{version}/{file_pattern}"
        logger.debug(f"[blue]Pesto Download URL: {download_url}[/blue]")

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

            logger.debug(f"[green]Downloaded Pesto package: {file_pattern}[/green]")
            verify_downloaded_asset(temp_file, file_pattern)

            # Pesto has raw binaries, just move it to target location
            shutil.move(str(temp_file), str(binary_path))

            if system != "windows" and binary_path.exists():
                binary_path.chmod(binary_path.stat().st_mode | stat.S_IEXEC)

            async with aiofiles.open(version_path, "w", encoding="utf-8") as version_file:
                await version_file.write(f"Pesto version {version} installed successfully.")

            return str(binary_path)

        except Exception as e:
            raise Exception(f"Failed to setup Pesto binary: {e}") from e
