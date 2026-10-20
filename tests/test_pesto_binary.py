# ruff: noqa: S101
import hashlib
import os
from pathlib import Path

import httpx
import pytest

from bin import get_pesto
from bin.binary_dependencies import DEPENDENCY_VERSIONS
from bin.download_integrity import SHA256_BY_ASSET

PAYLOAD = b"mock pesto executable"


@pytest.fixture
def download(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    urls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, content=PAYLOAD)

    client = httpx.AsyncClient
    monkeypatch.setattr(get_pesto.httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs))
    for asset in ("pesto-linux-aarch64", "pesto-linux-x86_64", "pesto-windows-x86_64.exe"):
        monkeypatch.setitem(SHA256_BY_ASSET, asset, hashlib.sha256(PAYLOAD).hexdigest())
    return urls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("system", "machine", "asset", "folder", "name"),
    [
        ("Linux", "aarch64", "pesto-linux-aarch64", "linux/arm64", "pesto"),
        ("Linux", "arm64", "pesto-linux-aarch64", "linux/arm64", "pesto"),
        ("Linux", "x86_64", "pesto-linux-x86_64", "linux/amd64", "pesto"),
        ("Linux", "amd64", "pesto-linux-x86_64", "linux/amd64", "pesto"),
        ("Windows", "AMD64", "pesto-windows-x86_64.exe", "windows/x86_64", "pesto.exe"),
    ],
)
async def test_download_installs_matching_verified_binary_and_reuses_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    download: list[str],
    system: str,
    machine: str,
    asset: str,
    folder: str,
    name: str,
) -> None:
    monkeypatch.setattr(get_pesto.platform, "system", lambda: system)
    monkeypatch.setattr(get_pesto.platform, "machine", lambda: machine)
    version = DEPENDENCY_VERSIONS["pesto"]

    result = Path(await get_pesto.PestoBinaryManager.ensure_pesto_binary(tmp_path))

    assert result == tmp_path / "bin" / "pesto" / folder / name
    assert result.read_bytes() == PAYLOAD
    assert (result.parent / version).is_file()
    assert download == [f"https://github.com/franzopl/pesto/releases/download/{version}/{asset}"]
    if system == "Linux":
        assert os.access(result, os.X_OK)
    assert await get_pesto.PestoBinaryManager.ensure_pesto_binary(tmp_path) == str(result)
    assert len(download) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("system", "machine"), [("Linux", "armv7l"), ("Darwin", "arm64"), ("Windows", "ARM64")])
async def test_unsupported_platform_does_not_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, download: list[str], system: str, machine: str) -> None:
    monkeypatch.setattr(get_pesto.platform, "system", lambda: system)
    monkeypatch.setattr(get_pesto.platform, "machine", lambda: machine)

    with pytest.raises(Exception, match="Unsupported platform for Pesto"):
        await get_pesto.PestoBinaryManager.ensure_pesto_binary(tmp_path)

    assert download == []
    assert not (tmp_path / "bin").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("checksum", [None, "0" * 64])
async def test_arm64_integrity_failure_does_not_install_binary_or_version_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, download: list[str], checksum: str | None
) -> None:
    monkeypatch.setattr(get_pesto.platform, "system", lambda: "Linux")
    monkeypatch.setattr(get_pesto.platform, "machine", lambda: "aarch64")
    if checksum is None:
        monkeypatch.delitem(SHA256_BY_ASSET, "pesto-linux-aarch64")
    else:
        monkeypatch.setitem(SHA256_BY_ASSET, "pesto-linux-aarch64", checksum)

    with pytest.raises(Exception, match="SHA-256"):
        await get_pesto.PestoBinaryManager.ensure_pesto_binary(tmp_path)

    assert len(download) == 1
    binary_dir = tmp_path / "bin" / "pesto" / "linux" / "arm64"
    assert not (binary_dir / "pesto").exists()
    assert not (binary_dir / DEPENDENCY_VERSIONS["pesto"]).exists()
