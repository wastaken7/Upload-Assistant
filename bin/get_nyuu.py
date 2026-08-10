# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
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


class NyuuBinaryManager:
    """Download Nyuu binaries for the host architecture."""

    @staticmethod
    async def ensure_nyuu_binary(base_dir: str | Path, path_7z: str | None = None, version: str = "v0.4.2") -> str:
        system = platform.system().lower()
        machine = platform.machine().lower()
        logger.debug(f"[blue]Nyuu: Detected system: {system}, architecture: {machine}[/blue]")

        platform_map: dict[str, dict[str, dict[str, str]]] = {
            "windows": {
                "x86_64": {"file": "nyuu-v0.4.2-win32.7z", "folder": "windows/x86_64"},
                "amd64": {"file": "nyuu-v0.4.2-win32.7z", "folder": "windows/x86_64"},
                "x86": {"file": "nyuu-v0.4.2-win32.7z", "folder": "windows/x86"},
                "arm64": {"file": "nyuu-v0.4.2-win32.7z", "folder": "windows/arm64"},
            },
            "darwin": {
                "arm64": {"file": "nyuu-v0.4.2-macos-x64.tar.xz", "folder": "macos/arm64"},
                "x86_64": {"file": "nyuu-v0.4.2-macos-x64.tar.xz", "folder": "macos/x86_64"},
                "amd64": {"file": "nyuu-v0.4.2-macos-x64.tar.xz", "folder": "macos/x86_64"},
            },
            "linux": {
                "x86_64": {"file": "nyuu-v0.4.2-linux-amd64.tar.xz", "folder": "linux/amd64"},
                "amd64": {"file": "nyuu-v0.4.2-linux-amd64.tar.xz", "folder": "linux/amd64"},
                "arm64": {"file": "nyuu-v0.4.2-linux-aarch64.tar.xz", "folder": "linux/arm64"},
                "aarch64": {"file": "nyuu-v0.4.2-linux-aarch64.tar.xz", "folder": "linux/arm64"},
            },
        }

        if system not in platform_map or machine not in platform_map[system]:
            raise Exception(f"Unsupported platform for Nyuu: {system} {machine}")

        platform_info = platform_map[system][machine]
        file_pattern = platform_info["file"]
        folder_path = platform_info["folder"]

        bin_dir = Path(base_dir) / "bin" / "nyuu" / folder_path
        bin_dir.mkdir(parents=True, exist_ok=True)

        binary_name = "nyuu.exe" if system == "windows" else "nyuu"
        binary_path = bin_dir / binary_name
        version_path = bin_dir / version

        binary_exists = binary_path.exists() and binary_path.is_file()
        binary_executable = system == "windows" or os.access(binary_path, os.X_OK)
        binary_valid = binary_exists and binary_executable

        if version_path.exists() and version_path.is_file() and binary_valid:
            logger.debug("[blue]Nyuu binary is up to date[/blue]")
            return str(binary_path)

        logger.info("[yellow]Binary 'nyuu' not found. Attempting to download automatically...[/yellow]")

        # Cleanup old files
        if binary_path.exists():
            binary_path.unlink()
        if version_path.exists():
            version_path.unlink()

        download_url = f"https://github.com/animetosho/Nyuu/releases/download/{version}/{file_pattern}"
        logger.debug(f"[blue]Nyuu Download URL: {download_url}[/blue]")

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

            logger.debug(f"[green]Downloaded Nyuu package: {file_pattern}[/green]")
            verify_downloaded_asset(temp_file, file_pattern)

            if file_pattern.endswith(".7z"):
                if not path_7z:
                    from bin.get_7z import SevenZipBinaryManager

                    path_7z = await SevenZipBinaryManager.ensure_7z_binary(base_dir)

                # Extract using the 7z binary
                cmd = [path_7z, "x", "-y", f"-o{bin_dir}", str(temp_file)]
                process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _stdout, stderr = await process.communicate()
                if process.returncode != 0:
                    raise Exception(f"7z extraction failed: {stderr.decode(errors='replace')}")

                # Locate nyuu.exe binary in extracted directory (Windows)
                if not binary_path.exists():
                    for p in bin_dir.rglob("nyuu.exe"):
                        if p.is_file():
                            shutil.move(str(p), str(binary_path))
                            break
                if temp_file.exists():
                    temp_file.unlink()
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

                    # Locate nyuu binary in extracted output
                    if not binary_path.exists():
                        for p in bin_dir.rglob("nyuu"):
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
                await version_file.write(f"Nyuu version {version} installed successfully.")

            return str(binary_path)

        except Exception as e:
            raise Exception(f"Failed to setup Nyuu binary: {e}") from e
