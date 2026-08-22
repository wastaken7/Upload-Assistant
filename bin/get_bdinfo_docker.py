#!/usr/bin/env python3
# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""
Docker-specific script to download bdinfo binaries for Linux containers.
"""

import os
import platform
import shutil
import sys
import tarfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


BDINFO_VERSION = "v0.4.0"
BASE_RELEASE_URL = "https://github.com/autobrr/go-bdinfo/releases/download"


def download_file(url: str, output_path: Path) -> None:
    logger.info(f"Downloading: {url}", extra={"markup": False})
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with Path(output_path).open("wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    logger.info(f"Downloaded: {output_path.name}", extra={"markup": False})


def secure_extract_tar(tar_path: Path, extract_to: Path) -> None:
    with tarfile.open(tar_path, "r:gz") as tar_ref:
        base_path = extract_to.resolve()
        for member in tar_ref.getmembers():
            if member.issym() or member.islnk():
                logger.warning(f"Warning: Skipping link: {member.name}", extra={"markup": False})
                continue
            if Path(member.name).is_absolute() or ".." in Path(member.name).parts:
                logger.warning(f"Warning: Skipping dangerous path: {member.name}", extra={"markup": False})
                continue
            try:
                final_path = (base_path / member.name).resolve()
                try:
                    os.path.commonpath([str(base_path), str(final_path)])
                    if not str(final_path).startswith(str(base_path) + os.sep) and final_path != base_path:
                        logger.warning(f"Warning: Path outside base directory: {member.name}", extra={"markup": False})
                        continue
                except ValueError:
                    logger.warning(f"Warning: Invalid path resolution: {member.name}", extra={"markup": False})
                    continue
            except (OSError, ValueError) as e:
                logger.warning(f"Warning: Path resolution failed for {member.name}: {e}", extra={"markup": False})
                continue

            if not (member.isfile() or member.isdir()):
                logger.warning(f"Warning: Skipping non-regular file: {member.name}", extra={"markup": False})
                continue

            if member.isfile() and member.size > 100 * 1024 * 1024:
                logger.warning(f"Warning: Skipping oversized file: {member.name} ({member.size} bytes)", extra={"markup": False})
                continue

            if member.isdir():
                target_dir = base_path / member.name
                target_dir.mkdir(parents=True, exist_ok=True)
                target_dir.chmod(0o700)
            elif member.isfile():
                target_file = base_path / member.name
                target_file.parent.mkdir(parents=True, exist_ok=True)
                source = tar_ref.extractfile(member)
                if source is not None:
                    with source, Path(target_file).open("wb") as out_f:
                        out_f.write(source.read())
                    target_file.chmod(0o600)


def download_bdinfo_for_docker(base_dir: Path = Path("/Upload-Assistant"), version: str = BDINFO_VERSION) -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    logger.info(f"System: {system}, Architecture: {machine}", extra={"markup": False})

    if system != "linux":
        raise Exception(f"This script is only for Linux containers, got: {system}")

    if machine in ("amd64", "x86_64"):
        asset = "linux_amd64.tar.gz"
        folder = "linux/amd64"
    elif machine in ("arm64", "aarch64"):
        asset = "linux_arm64.tar.gz"
        folder = "linux/arm64"
    elif machine.startswith("arm"):
        asset = "linux_arm.tar.gz"
        folder = "linux/arm"
    else:
        raise Exception(f"Unsupported architecture: {machine}")

    file_pattern = f"bdinfo_{version.removeprefix('v')}_{asset}"
    bin_dir = base_dir / "bin" / "bdinfo" / folder
    bin_dir.mkdir(parents=True, exist_ok=True)
    binary_path = bin_dir / "bdinfo"
    version_path = bin_dir / version

    if version_path.exists() and binary_path.exists() and os.access(binary_path, os.X_OK):
        logger.info(f"bdinfo {version} already installed", extra={"markup": False})
        return str(binary_path)

    download_url = f"{BASE_RELEASE_URL}/{version}/{file_pattern}"
    logger.info(f"Downloading bdinfo from: {download_url}", extra={"markup": False})

    temp_archive = bin_dir / f"temp_{file_pattern}"
    download_file(download_url, temp_archive)
    verify_downloaded_asset(temp_archive, file_pattern)

    logger.info(f"Extracting {temp_archive} to {bin_dir}", extra={"markup": False})
    secure_extract_tar(temp_archive, bin_dir)
    temp_archive.unlink()

    # Search for extracted bdinfo executable and move it into place if necessary
    if not binary_path.exists():
        found = None
        for p in bin_dir.rglob("bdinfo"):
            if p.is_file():
                found = p
                break
        if found:
            shutil.move(str(found), str(binary_path))

    if not binary_path.exists():
        raise Exception(f"Failed to extract bdinfo binary to {binary_path}")

    Path(binary_path).chmod(0o700)

    with Path(version_path).open("w", encoding="utf-8") as vf:
        vf.write(f"autobrr/go-bdinfo version {version} installed successfully.")

    logger.info(f"Installed bdinfo: {binary_path}", extra={"markup": False})
    return str(binary_path)


if __name__ == "__main__":
    try:
        download_bdinfo_for_docker()
        logger.info("bdinfo installation completed successfully!", extra={"markup": False})
    except Exception as exc:
        logger.info(f"ERROR: Failed to install bdinfo: {exc}", extra={"markup": False})
        raise SystemExit(1) from exc
