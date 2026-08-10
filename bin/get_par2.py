# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
import platform
import shutil
import stat
import zipfile
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


class Par2BinaryManager:
    """Download par2cmdline-turbo binaries for the host architecture."""

    @staticmethod
    async def ensure_par2_binary(base_dir: str | Path, version: str = "v1.4.0") -> str:
        system = platform.system().lower()
        machine = platform.machine().lower()
        logger.debug(f"[blue]PAR2: Detected system: {system}, architecture: {machine}[/blue]")

        # Strip 'v' from version for URLs if needed, but the tag is v1.4.0, while filenames have 1.4.0
        v_num = version.lstrip("v")

        platform_map: dict[str, dict[str, dict[str, str]]] = {
            "windows": {
                "x86_64": {"file": f"par2cmdline-turbo-{v_num}-win-x64.zip", "folder": "windows/x86_64"},
                "amd64": {"file": f"par2cmdline-turbo-{v_num}-win-x64.zip", "folder": "windows/x86_64"},
                "arm64": {"file": f"par2cmdline-turbo-{v_num}-win-arm64.zip", "folder": "windows/arm64"},
            },
            "darwin": {
                "arm64": {"file": f"par2cmdline-turbo-{v_num}-macos-arm64.zip", "folder": "macos/arm64"},
                "x86_64": {"file": f"par2cmdline-turbo-{v_num}-macos-amd64.zip", "folder": "macos/x86_64"},
                "amd64": {"file": f"par2cmdline-turbo-{v_num}-macos-amd64.zip", "folder": "macos/x86_64"},
            },
            "linux": {
                "x86_64": {"file": f"par2cmdline-turbo-{v_num}-linux-amd64.zip", "folder": "linux/amd64"},
                "amd64": {"file": f"par2cmdline-turbo-{v_num}-linux-amd64.zip", "folder": "linux/amd64"},
                "arm64": {"file": f"par2cmdline-turbo-{v_num}-linux-arm64.zip", "folder": "linux/arm64"},
                "aarch64": {"file": f"par2cmdline-turbo-{v_num}-linux-arm64.zip", "folder": "linux/arm64"},
            },
        }

        if system not in platform_map or machine not in platform_map[system]:
            raise Exception(f"Unsupported platform for PAR2: {system} {machine}")

        platform_info = platform_map[system][machine]
        file_pattern = platform_info["file"]
        folder_path = platform_info["folder"]

        bin_dir = Path(base_dir) / "bin" / "par2" / folder_path
        bin_dir.mkdir(parents=True, exist_ok=True)

        binary_name = "par2.exe" if system == "windows" else "par2"
        binary_path = bin_dir / binary_name
        version_path = bin_dir / version

        binary_exists = binary_path.exists() and binary_path.is_file()
        binary_executable = system == "windows" or os.access(binary_path, os.X_OK)
        binary_valid = binary_exists and binary_executable

        if version_path.exists() and version_path.is_file() and binary_valid:
            logger.debug("[blue]PAR2 binary is up to date[/blue]")
            return str(binary_path)

        logger.info("[yellow]Binary 'par2' not found. Attempting to download automatically...[/yellow]")

        # Cleanup old files
        if binary_path.exists():
            binary_path.unlink()
        if version_path.exists():
            version_path.unlink()

        download_url = f"https://github.com/animetosho/par2cmdline-turbo/releases/download/{version}/{file_pattern}"
        logger.debug(f"[blue]PAR2 Download URL: {download_url}[/blue]")

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

            logger.debug(f"[green]Downloaded PAR2 package: {file_pattern}[/green]")
            verify_downloaded_asset(temp_file, file_pattern)

            try:
                with zipfile.ZipFile(temp_file, "r") as zip_ref:
                    # Secure extract: prevent path traversal
                    for member in zip_ref.namelist():
                        info = zip_ref.getinfo(member)
                        perm = info.external_attr >> 16
                        if stat.S_ISLNK(perm):
                            continue
                        if Path(member).is_absolute() or ".." in member or member.startswith("/"):
                            continue
                        full_path = os.path.realpath(Path(bin_dir) / member)
                        base_path = os.path.realpath(bin_dir)
                        if not full_path.startswith(base_path + os.sep) and full_path != base_path:
                            continue
                        zip_ref.extract(member, str(bin_dir))

                # Locate par2 binary in extracted output
                if not binary_path.exists():
                    for p in bin_dir.rglob(binary_name):
                        if p.is_file():
                            shutil.move(str(p), str(binary_path))
                            break
            finally:
                if temp_file.exists():
                    temp_file.unlink()

            # Cleanup extra directories/files leftover from extraction
            for p in list(bin_dir.iterdir()):
                if p.is_dir():
                    shutil.rmtree(p)
                elif p.is_file() and p.name not in (binary_name, version):
                    p.unlink()

            if system != "windows" and binary_path.exists():
                binary_path.chmod(binary_path.stat().st_mode | stat.S_IEXEC)

            async with aiofiles.open(version_path, "w", encoding="utf-8") as version_file:
                await version_file.write(f"PAR2 version {version} installed successfully.")

            return str(binary_path)

        except Exception as e:
            raise Exception(f"Failed to setup PAR2 binary: {e}") from e
