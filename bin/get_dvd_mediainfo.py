#!/usr/bin/env python3
# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Provision the legacy MediaInfo CLI required for DVD parsing."""

import platform
import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import requests

from bin.download_integrity import verify_downloaded_asset
from src.console import logger

MEDIAINFO_VERSION = "23.04"
MEDIAINFO_CLI_BASE_URL = "https://mediaarea.net/download/binary/mediainfo"
MEDIAINFO_LIB_BASE_URL = "https://mediaarea.net/download/binary/libmediainfo0"


def get_filename(system: str, arch: str, library_type: str = "cli") -> str:
    if system == "windows" and library_type == "cli" and arch == "x86_64":
        return f"MediaInfo_CLI_{MEDIAINFO_VERSION}_Windows_x64.zip"
    if system == "linux":
        if library_type == "cli":
            # MediaInfo CLI uses Lambda (pre-compiled) version
            return f"MediaInfo_CLI_{MEDIAINFO_VERSION}_Lambda_{arch}.zip"
        if library_type == "lib":
            # MediaInfo library uses DLL version
            return f"MediaInfo_DLL_{MEDIAINFO_VERSION}_Lambda_{arch}.zip"
        raise ValueError(f"Unknown library_type: {library_type}")
    return ""


def get_url(system: str, arch: str, library_type: str = "cli") -> str:
    filename = get_filename(system, arch, library_type)
    if library_type == "cli":
        return f"{MEDIAINFO_CLI_BASE_URL}/{MEDIAINFO_VERSION}/{filename}"
    if library_type == "lib":
        return f"{MEDIAINFO_LIB_BASE_URL}/{MEDIAINFO_VERSION}/{filename}"
    raise ValueError(f"Unknown library_type: {library_type}")


def download_file(url: str, output_path: Path) -> None:
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()

    with Path(output_path).open("wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def extract_linux(cli_archive: Path, lib_archive: Path, output_dir: Path) -> None:
    # Extract MediaInfo CLI from zip file
    with zipfile.ZipFile(cli_archive, "r") as zip_ref:
        mediainfo_file = output_dir / "mediainfo"
        member = next((name for name in zip_ref.namelist() if name.endswith("/mediainfo") or name == "mediainfo"), None)
        if member is None:
            raise RuntimeError("MediaInfo CLI archive does not contain mediainfo")
        with zip_ref.open(member) as source, mediainfo_file.open("wb") as destination:
            shutil.copyfileobj(source, destination)

    # Extract MediaInfo library
    with zipfile.ZipFile(lib_archive, "r") as zip_ref:
        lib_file = output_dir / "libmediainfo.so.0"
        if "lib/libmediainfo.so.0.0.0" not in zip_ref.namelist():
            raise RuntimeError("MediaInfo library archive does not contain libmediainfo.so.0.0.0")
        with zip_ref.open("lib/libmediainfo.so.0.0.0") as source, lib_file.open("wb") as destination:
            shutil.copyfileobj(source, destination)


def extract_windows(cli_archive: Path, output_dir: Path) -> None:
    """Extract the legacy Windows DVD CLI without unpacking arbitrary archive members."""
    with zipfile.ZipFile(cli_archive, "r") as zip_ref:
        member = next((name for name in zip_ref.namelist() if Path(name).name == "MediaInfo.exe"), None)
        if member is None:
            raise RuntimeError("MediaInfo CLI archive does not contain MediaInfo.exe")
        info = zip_ref.getinfo(member)
        if Path(member).is_absolute() or ".." in Path(member).parts:
            raise RuntimeError(f"Unsafe MediaInfo archive member: {member}")
        with zip_ref.open(info) as source, (output_dir / "MediaInfo.exe").open("wb") as destination:
            shutil.copyfileobj(source, destination)


def download_dvd_mediainfo(base_dir: str) -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()

    logger.debug(f"[blue]System: {system}, arch: {machine}[/blue]")

    if machine == "amd64":
        machine = "x86_64"

    if system == "windows":
        if machine != "x86_64":
            raise RuntimeError("MediaInfo 23.04 is unavailable for Windows ARM64; DVD language parsing cannot use the newer CLI")

        output_dir = Path(base_dir) / "bin" / "MI" / "windows" / "dvd"
        cli_file = output_dir / "MediaInfo.exe"
        version_file = output_dir / f"version_{MEDIAINFO_VERSION}"
        if cli_file.is_file() and version_file.is_file():
            return str(cli_file)

        output_dir.mkdir(parents=True, exist_ok=True)
        cli_filename = get_filename(system, machine)
        with TemporaryDirectory() as tmp_dir:
            cli_archive = Path(tmp_dir) / cli_filename
            download_file(get_url(system, machine), cli_archive)
            verify_downloaded_asset(cli_archive, cli_filename)
            with TemporaryDirectory(dir=output_dir.parent, prefix="mediainfo-dvd-") as staging_dir:
                staging_dir_path = Path(staging_dir)
                extract_windows(cli_archive, staging_dir_path)
                staged_cli = staging_dir_path / "MediaInfo.exe"
                if not staged_cli.is_file():
                    raise RuntimeError("Failed to extract MediaInfo CLI for DVD processing")
                staged_cli.replace(cli_file)
        version_file.write_text(f"MediaInfo {MEDIAINFO_VERSION}\n", encoding="utf-8")
        return str(cli_file)

    if system != "linux":
        return None

    if machine not in ["x86_64", "arm64"]:
        return None

    platform_dir = "linux/dvd"
    output_dir = Path(base_dir) / "bin" / "MI" / platform_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.debug(f"[blue]Output: {output_dir}[/blue]")

    cli_file = output_dir / "mediainfo"
    lib_file = output_dir / "libmediainfo.so.0"
    version_file = output_dir / f"version_{MEDIAINFO_VERSION}"

    if cli_file.exists() and lib_file.exists() and version_file.exists():
        logger.debug(f"[blue]MediaInfo CLI and Library {MEDIAINFO_VERSION} exist[/blue]")
        return str(cli_file)
    logger.info(f"[yellow]Downloading specific MediaInfo CLI and Library for DVD processing: {MEDIAINFO_VERSION}...[/yellow]")
    # Download MediaInfo CLI
    cli_url = get_url(system, machine, "cli")
    cli_filename = get_filename(system, machine, "cli")

    # Download MediaInfo Library
    lib_url = get_url(system, machine, "lib")
    lib_filename = get_filename(system, machine, "lib")

    logger.debug(f"[blue]MediaInfo CLI URL: {cli_url}[/blue]")
    logger.debug(f"[blue]MediaInfo CLI filename: {cli_filename}[/blue]")
    logger.debug(f"[blue]MediaInfo Library URL: {lib_url}[/blue]")
    logger.debug(f"[blue]MediaInfo Library filename: {lib_filename}[/blue]")

    with TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        cli_archive = tmp_dir_path / cli_filename
        lib_archive = tmp_dir_path / lib_filename

        # Download both archives
        download_file(cli_url, cli_archive)
        logger.debug(f"[green]Downloaded {cli_filename}[/green]")

        download_file(lib_url, lib_archive)
        logger.debug(f"[green]Downloaded {lib_filename}[/green]")

        with TemporaryDirectory(dir=output_dir.parent, prefix="mediainfo-dvd-") as staging_dir:
            staging_dir_path = Path(staging_dir)
            extract_linux(cli_archive, lib_archive, staging_dir_path)
            staged_cli = staging_dir_path / "mediainfo"
            staged_lib = staging_dir_path / "libmediainfo.so.0"
            if not staged_cli.is_file() or not staged_lib.is_file():
                raise RuntimeError("Failed to extract MediaInfo CLI and library for DVD processing")
            staged_cli.replace(cli_file)
            staged_lib.replace(lib_file)

        logger.debug("[green]Extracted library[/green]")

        with Path(version_file).open("w") as f:
            f.write(f"MediaInfo {MEDIAINFO_VERSION}")

        # Make CLI binary executable
        if cli_file.exists():
            Path(cli_file).chmod(0o700)  # rwx------ (owner only)

    if not cli_file.exists():
        raise Exception(f"Failed to extract CLI binary to {cli_file}")
    if not lib_file.exists():
        raise Exception(f"Failed to extract library to {lib_file}")

    return str(cli_file)
