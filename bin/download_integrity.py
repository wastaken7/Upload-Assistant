"""Pinned SHA-256 verification for third-party executable downloads."""

import hashlib
from pathlib import Path

from bin.binary_dependencies import DEPENDENCY_CHECKSUMS

SHA256_BY_ASSET = {
    "MediaInfo_CLI_23.04_Windows_x64.zip": "b1beafae0a15168ca37db8a3061d55eba55c1a120d6a6423ac1d3f30ed869270",
    "MediaInfo_CLI_26.05_Lambda_arm64.zip": "57268dcfc044cdcbe4641e26432392f002b7fa4bcb06e9d738be04cd047a2c1e",
    "MediaInfo_CLI_26.05_Lambda_x86_64.zip": "1ae3744a78c93492b69f0b38bb2d1de1433c3eae04030ff1ea82ee1f60ac9a99",
    "MediaInfo_CLI_26.05_Mac.dmg": "507605a7c8f1054a6996d99a4ef5b5a0711cfbf2f8ca2ef5161d6ee701ea8015",
    "MediaInfo_CLI_26.05_Windows_ARM64.zip": "6b403fa1411730672adefa8d49d97cbf7163eed7fc5c1256c9a6e9f915fde1a8",
    "MediaInfo_CLI_26.05_Windows_x64.zip": "f7f80620ce6d14f4995f0de6f98e3ef18ad29496db01899571152ee3311229f9",
    "mkbrr_1.18.0_linux_arm.tar.gz": "f622595f6afee302c72c89abdd9f31ad3197bd85d45a8b482f97ebd21930ac51",
    "mkbrr_1.18.0_linux_arm64.tar.gz": "1c187ab2b860e637296d6f0deb4c2e7754a4c1e249b0226f0be671170689de24",
    "mkbrr_1.18.0_linux_x86_64.tar.gz": "a796bd97dfb093e18a1a509c8986580498e65253582983a462b977b359f987b9",
}

for dependency, checksums in DEPENDENCY_CHECKSUMS.items():
    if duplicates := SHA256_BY_ASSET.keys() & checksums.keys():
        raise RuntimeError(f"Duplicate checksum pins for {dependency}: {', '.join(sorted(duplicates))}")
    SHA256_BY_ASSET.update(checksums)


def verify_downloaded_asset(path: Path, asset: str) -> None:
    """Fail closed unless a downloaded executable archive matches its pinned hash."""
    expected = SHA256_BY_ASSET.get(asset)
    if expected is None:
        raise RuntimeError(f"No SHA-256 checksum is pinned for {asset}")
    with path.open("rb") as asset_file:
        actual = hashlib.file_digest(asset_file, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError(f"SHA-256 checksum mismatch for {asset}")


def verify_downloaded_content(content: bytes, asset: str) -> None:
    """Fail closed unless downloaded content matches its pinned hash."""
    expected = SHA256_BY_ASSET.get(asset)
    if expected is None:
        raise RuntimeError(f"No SHA-256 checksum is pinned for {asset}")
    if hashlib.sha256(content).hexdigest() != expected:
        raise RuntimeError(f"SHA-256 checksum mismatch for {asset}")
