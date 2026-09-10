#!/usr/bin/env python3
"""Update one pinned binary dependency from its latest stable GitHub release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, urlparse

from bin.binary_dependencies import DEPENDENCY_REPOSITORIES, DEPENDENCY_VERSIONS
from bin.binary_dependency_pins import PINS

PIN_PATHS = {dependency: pin.path for dependency, pin in PINS.items()}


@dataclass(frozen=True)
class DependencySpec:
    assets: Callable[[str], tuple[str, ...]]


def _7zip_assets(version: str) -> tuple[str, ...]:
    compact = version.replace(".", "")
    return (
        "7zr.exe",
        f"7z{compact}-mac.tar.xz",
        f"7z{compact}-linux-x64.tar.xz",
        f"7z{compact}-linux-arm64.tar.xz",
        f"7z{compact}-linux-arm.tar.xz",
    )


def _bdinfo_assets(version: str) -> tuple[str, ...]:
    number = version.removeprefix("v")
    platforms = (
        "windows_amd64.zip",
        "darwin_amd64.tar.gz",
        "darwin_arm64.tar.gz",
        "linux_amd64.tar.gz",
        "linux_arm64.tar.gz",
        "linux_arm.tar.gz",
    )
    return tuple(f"bdinfo_{number}_{platform}" for platform in platforms)


def _mkbrr_assets(version: str) -> tuple[str, ...]:
    number = version.removeprefix("v")
    platforms = (
        "windows_x86_64.zip",
        "darwin_arm64.tar.gz",
        "darwin_x86_64.tar.gz",
        "linux_x86_64.tar.gz",
        "linux_arm64.tar.gz",
        "linux_arm.tar.gz",
        "freebsd_x86_64.tar.gz",
    )
    return tuple(f"mkbrr_{number}_{platform}" for platform in platforms)


def _nyuu_assets(version: str) -> tuple[str, ...]:
    return (
        f"nyuu-{version}-win32.7z",
        f"nyuu-{version}-linux-aarch64.tar.xz",
        f"nyuu-{version}-linux-amd64.tar.xz",
        f"nyuu-{version}-macos-x64.tar.xz",
    )


def _par2_assets(version: str) -> tuple[str, ...]:
    number = version.removeprefix("v")
    platforms = ("win-x64", "win-arm64", "macos-arm64", "macos-amd64", "linux-amd64", "linux-arm64")
    return tuple(f"par2cmdline-turbo-{number}-{platform}.zip" for platform in platforms)


def _dynamic_hdr_assets(command: str, version: str) -> tuple[str, ...]:
    return (
        f"{command}-{version}-aarch64-pc-windows-msvc.zip",
        f"{command}-{version}-aarch64-unknown-linux-musl.tar.gz",
        f"{command}-{version}-universal-macOS.zip",
        f"{command}-{version}-x86_64-pc-windows-msvc.zip",
        f"{command}-{version}-x86_64-unknown-linux-musl.tar.gz",
    )


DEPENDENCY_SPECS = {
    "7zip": DependencySpec(_7zip_assets),
    "bdinfo": DependencySpec(_bdinfo_assets),
    "dovi_tool": DependencySpec(lambda version: _dynamic_hdr_assets("dovi_tool", version)),
    "ffmpeg": DependencySpec(lambda version: (f"ffmpeg-{version}-essentials_build.zip",)),
    "hdr10plus_tool": DependencySpec(lambda version: _dynamic_hdr_assets("hdr10plus_tool", version)),
    "mkbrr": DependencySpec(_mkbrr_assets),
    "nyuu": DependencySpec(_nyuu_assets),
    "par2": DependencySpec(_par2_assets),
    "pesto": DependencySpec(lambda _version: ("pesto-windows-x86_64.exe", "pesto-linux-x86_64")),
}


def _request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=_request_headers())  # noqa: S310 - fixed GitHub API URL
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed GitHub API URL
        payload: object = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub returned malformed release metadata")
    return cast(dict[str, Any], payload)


def _request_headers(*, authenticated: bool = True) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Upload-Assistant-dependency-updater"}
    if authenticated and (token := os.environ.get("GITHUB_TOKEN")):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _download_sha256(url: str) -> str:
    request = urllib.request.Request(url, headers=_request_headers(authenticated=False))  # noqa: S310 - URL is validated GitHub release metadata
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - URL comes from GitHub release metadata
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_sha256(asset: dict[str, Any]) -> str:
    digest = asset.get("digest")
    if digest is not None:
        if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise RuntimeError(f"GitHub returned an invalid digest for {asset.get('name', 'unknown asset')}")
        return digest.removeprefix("sha256:")
    url = asset.get("browser_download_url")
    if not isinstance(url, str) or urlparse(url).scheme != "https" or urlparse(url).hostname != "github.com":
        raise RuntimeError(f"GitHub returned an invalid download URL for {asset.get('name', 'unknown asset')}")
    return _download_sha256(url)


def fetch_latest(dependency: str) -> tuple[str, dict[str, dict[str, Any]]]:
    repository = DEPENDENCY_REPOSITORIES[dependency]
    release = _request_json(f"https://api.github.com/repos/{repository}/releases/latest")
    version = release.get("tag_name")
    if not isinstance(version, str) or not version or "\n" in version or "\r" in version or release.get("draft") is not False or release.get("prerelease") is not False:
        raise RuntimeError(f"{repository} did not return a valid stable release")

    assets_payload: object = release.get("assets")
    if not isinstance(assets_payload, list):
        raise RuntimeError(f"{repository} returned malformed release assets")
    assets_by_name: dict[str, dict[str, Any]] = {}
    for raw_asset in cast(list[object], assets_payload):
        if not isinstance(raw_asset, dict):
            continue
        asset = cast(dict[str, Any], raw_asset)
        if isinstance(name := asset.get("name"), str):
            assets_by_name[name] = asset
    required = DEPENDENCY_SPECS[dependency].assets(version)
    missing = sorted(set(required) - assets_by_name.keys())
    if missing:
        raise RuntimeError(f"{repository} release {version} is missing required assets: {', '.join(missing)}")
    return version, {name: assets_by_name[name] for name in required}


def _render_pin(dependency: str, version: str, checksums: dict[str, str]) -> str:
    repository = DEPENDENCY_REPOSITORIES[dependency]
    checksum_lines = "".join(f"    {json.dumps(name)}: {json.dumps(checksums[name])},\n" for name in sorted(checksums, key=str.casefold))
    return (
        f'"""Release and integrity pins for {dependency}."""\n\n'
        f"VERSION = {json.dumps(version)}\n"
        f"REPOSITORY = {json.dumps(repository)}\n"
        f"SHA256_BY_ASSET = {{\n{checksum_lines}}}\n"
    )


def update_dependency(dependency: str) -> tuple[bool, str]:
    current_version = DEPENDENCY_VERSIONS[dependency]
    latest_version, assets = fetch_latest(dependency)
    if latest_version == current_version:
        return False, latest_version

    checksums = {name: _asset_sha256(asset) for name, asset in assets.items()}
    pin_path = PIN_PATHS[dependency]
    previous_content = pin_path.read_text(encoding="utf-8")
    try:
        pin_path.write_text(_render_pin(dependency, latest_version, checksums), encoding="utf-8")
    except Exception:
        pin_path.write_text(previous_content, encoding="utf-8")
        raise
    return True, latest_version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dependency", choices=sorted(DEPENDENCY_SPECS))
    args = parser.parse_args()
    dependency = cast(str, args.dependency)
    previous_version = DEPENDENCY_VERSIONS[dependency]
    changed, version = update_dependency(dependency)
    result: dict[str, str | bool] = {"changed": changed, "dependency": dependency, "version": version}
    print(json.dumps(result))
    if output_path := os.environ.get("GITHUB_OUTPUT"):
        repository = DEPENDENCY_REPOSITORIES[dependency]
        release_url = f"https://github.com/{repository}/releases/tag/{quote(version, safe='')}"
        asset_count = len(DEPENDENCY_SPECS[dependency].assets(version))
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"changed={str(changed).lower()}\nprevious_version={previous_version}\nversion={version}\nrelease_url={release_url}\nasset_count={asset_count}\n")


if __name__ == "__main__":
    main()
