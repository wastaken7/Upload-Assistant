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
from typing import Any
from urllib.parse import quote, urlparse

from bin.binary_dependencies import DEPENDENCY_REPOSITORIES, DEPENDENCY_VERSIONS

ROOT = Path(__file__).resolve().parents[1]
VERSIONS_PATH = ROOT / "bin" / "binary_dependencies.py"
CHECKSUMS_PATH = ROOT / "bin" / "download_integrity.py"


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
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub returned malformed release metadata")
    return payload


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
    if (
        not isinstance(version, str)
        or not version
        or "\n" in version
        or "\r" in version
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise RuntimeError(f"{repository} did not return a valid stable release")

    assets = release.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError(f"{repository} returned malformed release assets")
    assets_by_name = {asset.get("name"): asset for asset in assets if isinstance(asset, dict) and isinstance(asset.get("name"), str)}
    required = DEPENDENCY_SPECS[dependency].assets(version)
    missing = sorted(set(required) - assets_by_name.keys())
    if missing:
        raise RuntimeError(f"{repository} release {version} is missing required assets: {', '.join(missing)}")
    return version, {name: assets_by_name[name] for name in required}


def _replace_version(content: str, dependency: str, old_version: str, new_version: str) -> str:
    old_line = f'    "{dependency}": "{old_version}",'
    new_line = f'    "{dependency}": "{new_version}",'
    if content.count(old_line) != 1:
        raise RuntimeError(f"Could not uniquely locate the {dependency} version pin")
    return content.replace(old_line, new_line)


def _replace_checksums(content: str, old_assets: tuple[str, ...], checksums: dict[str, str]) -> str:
    start_marker = "SHA256_BY_ASSET = {\n"
    end_marker = "}\n\n\ndef verify_downloaded_asset"
    if content.count(start_marker) != 1 or content.count(end_marker) != 1:
        raise RuntimeError("Could not locate the checksum table")
    before, remainder = content.split(start_marker, 1)
    old_table, after = remainder.split(end_marker, 1)
    old_asset_set = set(old_assets)
    retained_lines: list[str] = []
    insertion_index: int | None = None
    for line in old_table.splitlines(keepends=True):
        match = re.fullmatch(r'    "([^"]+)": "[0-9a-f]+",\n?', line)
        if match is None:
            raise RuntimeError("The checksum table is malformed")
        if match.group(1) in old_asset_set:
            if insertion_index is None:
                insertion_index = len(retained_lines)
            continue
        retained_lines.append(line)
    if insertion_index is None:
        raise RuntimeError("Could not locate the dependency's current checksum pins")
    new_lines = [f'    "{name}": "{checksums[name]}",\n' for name in sorted(checksums, key=str.casefold)]
    retained_lines[insertion_index:insertion_index] = new_lines
    return f"{before}{start_marker}{''.join(retained_lines)}{end_marker}{after}"


def update_dependency(dependency: str) -> tuple[bool, str]:
    current_version = DEPENDENCY_VERSIONS[dependency]
    latest_version, assets = fetch_latest(dependency)
    if latest_version == current_version:
        return False, latest_version

    checksums = {name: _asset_sha256(asset) for name, asset in assets.items()}
    versions_content = VERSIONS_PATH.read_text(encoding="utf-8")
    checksums_content = CHECKSUMS_PATH.read_text(encoding="utf-8")
    updated_versions = _replace_version(versions_content, dependency, current_version, latest_version)
    updated_checksums = _replace_checksums(checksums_content, DEPENDENCY_SPECS[dependency].assets(current_version), checksums)
    try:
        VERSIONS_PATH.write_text(updated_versions, encoding="utf-8")
        CHECKSUMS_PATH.write_text(updated_checksums, encoding="utf-8")
    except Exception:
        VERSIONS_PATH.write_text(versions_content, encoding="utf-8")
        CHECKSUMS_PATH.write_text(checksums_content, encoding="utf-8")
        raise
    return True, latest_version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dependency", choices=sorted(DEPENDENCY_SPECS))
    args = parser.parse_args()
    previous_version = DEPENDENCY_VERSIONS[args.dependency]
    changed, version = update_dependency(args.dependency)
    result = {"changed": changed, "dependency": args.dependency, "version": version}
    print(json.dumps(result))
    if output_path := os.environ.get("GITHUB_OUTPUT"):
        repository = DEPENDENCY_REPOSITORIES[args.dependency]
        release_url = f"https://github.com/{repository}/releases/tag/{quote(version, safe='')}"
        asset_count = len(DEPENDENCY_SPECS[args.dependency].assets(version))
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(
                f"changed={str(changed).lower()}\n"
                f"previous_version={previous_version}\n"
                f"version={version}\n"
                f"release_url={release_url}\n"
                f"asset_count={asset_count}\n"
            )


if __name__ == "__main__":
    main()
