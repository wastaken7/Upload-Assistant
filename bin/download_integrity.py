"""Pinned SHA-256 verification for third-party executable downloads."""

import hashlib
from pathlib import Path

from bin.binary_dependencies import DEPENDENCY_CHECKSUMS

SHA256_BY_ASSET = {
    "MediaInfo_CLI_26.10_Lambda_arm64.zip": "8b67e2a2bd22c1fc596f1f774231dd8255f38b79c9fd0a6323d46da1e4c1cb11",
    "MediaInfo_CLI_26.10_Lambda_x86_64.zip": "3087b8d4906a47d876a66a500b8a6af63de8e9da9992d295a702b4ca79fb3fdd",
    "MediaInfo_CLI_26.10_Mac.dmg": "2345a52f6e5281a15e9ef87acbe5756a9c4727d5629873c013f148a8f82525ab",
    "MediaInfo_CLI_26.10_Windows_ARM64.zip": "0667b568d96f098c3f23ef111dafa7d66f10e078ccb568b589975191131f8a0d",
    "MediaInfo_CLI_26.10_Windows_x64.zip": "4cc94bd272903914c04f4f9a9f53a6c94b5ea6c6454cf738d29fa182c41e8a29",
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
