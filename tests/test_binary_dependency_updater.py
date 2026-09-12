# ruff: noqa: S101
import ast
import hashlib
import inspect
import sys
from pathlib import Path

import pytest

from bin.binary_dependencies import DEPENDENCY_REPOSITORIES, DEPENDENCY_VERSIONS
from bin.download_integrity import SHA256_BY_ASSET
from bin.get_7z import SevenZipBinaryManager
from bin.get_bdinfo import BDInfoBinaryManager
from bin.get_bdinfo_docker import BDINFO_VERSION
from bin.get_mkbrr import MkbrrBinaryManager
from bin.get_nyuu import NyuuBinaryManager
from scripts import update_binary_dependency as updater

WORKFLOW_PATH = Path(__file__).parents[1] / ".github" / "workflows" / "update-binary-dependencies.yml"


def _release(version: str, names: tuple[str, ...], *, digest: str | None = None) -> dict[str, object]:
    assets = [
        {
            "name": name,
            "digest": digest,
            "browser_download_url": f"https://github.com/example/releases/download/{version}/{name}",
        }
        for name in names
    ]
    return {"tag_name": version, "draft": False, "prerelease": False, "assets": assets}


def test_every_managed_dependency_has_a_repository_and_current_checksums() -> None:
    assert DEPENDENCY_VERSIONS.keys() == DEPENDENCY_REPOSITORIES.keys() == updater.DEPENDENCY_SPECS.keys()
    for dependency, version in DEPENDENCY_VERSIONS.items():
        assert set(updater.DEPENDENCY_SPECS[dependency].assets(version)) <= SHA256_BY_ASSET.keys()
    assert all(len(checksum) == 64 and set(checksum) <= set("0123456789abcdef") for checksum in SHA256_BY_ASSET.values())


def test_every_managed_dependency_has_an_independent_pin_file() -> None:
    assert updater.PIN_PATHS.keys() == updater.DEPENDENCY_SPECS.keys()
    assert len(set(updater.PIN_PATHS.values())) == len(updater.DEPENDENCY_SPECS)


def test_workflow_stages_only_independent_pin_files() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    add_paths = workflow.split("          add-paths: |\n", 1)[1]
    assert "bin/binary_dependency_pins/" in add_paths
    assert "bin/binary_dependencies.py" not in add_paths
    assert "bin/download_integrity.py" not in add_paths


def test_asset_names_apply_upstream_version_formats() -> None:
    assert updater.DEPENDENCY_SPECS["7zip"].assets("26.03")[-1] == "7z2603-linux-arm.tar.xz"
    assert updater.DEPENDENCY_SPECS["bdinfo"].assets("v0.4.2")[0] == "bdinfo_0.4.2_windows_amd64.zip"
    assert updater.DEPENDENCY_SPECS["mkbrr"].assets("v1.25.1")[0] == "mkbrr_1.25.1_windows_x86_64.zip"
    assert updater.DEPENDENCY_SPECS["par2"].assets("v1.5.0")[0] == "par2cmdline-turbo-1.5.0-win-x64.zip"


def test_runtime_and_docker_paths_share_version_pins() -> None:
    assert inspect.signature(BDInfoBinaryManager.ensure_bdinfo_binary).parameters["version"].default == DEPENDENCY_VERSIONS["bdinfo"]
    assert BDINFO_VERSION == DEPENDENCY_VERSIONS["bdinfo"]
    assert inspect.signature(MkbrrBinaryManager.ensure_mkbrr_binary).parameters["version"].default == DEPENDENCY_VERSIONS["mkbrr"]
    assert inspect.signature(MkbrrBinaryManager.download_mkbrr_for_docker).parameters["version"].default == DEPENDENCY_VERSIONS["mkbrr"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("manager", "module", "version", "expected_asset"),
    [
        (SevenZipBinaryManager.ensure_7z_binary, "bin.get_7z", "30.04", "7z3004-linux-arm64.tar.xz"),
        (NyuuBinaryManager.ensure_nyuu_binary, "bin.get_nyuu", "v9.8.7", "nyuu-v9.8.7-linux-amd64.tar.xz"),
    ],
)
async def test_runtime_download_urls_derive_asset_names_from_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manager: object,
    module: str,
    version: str,
    expected_asset: str,
) -> None:
    urls: list[str] = []

    class StopDownload(Exception):
        pass

    class Client:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def stream(self, _method: str, url: str, **_kwargs):  # type: ignore[no-untyped-def]
            urls.append(url)
            raise StopDownload("StopDownload")

    machine = "arm64" if manager == SevenZipBinaryManager.ensure_7z_binary else "x86_64"
    monkeypatch.setattr(f"{module}.platform.system", lambda: "Linux")
    monkeypatch.setattr(f"{module}.platform.machine", lambda: machine)
    monkeypatch.setattr(f"{module}.httpx.AsyncClient", lambda **_kwargs: Client())

    with pytest.raises(Exception, match="StopDownload"):
        await manager(tmp_path, version=version)  # type: ignore[operator]
    assert urls[0].endswith(f"/{version}/{expected_asset}")


def test_fetch_latest_accepts_a_complete_stable_release(monkeypatch: pytest.MonkeyPatch) -> None:
    assets = updater.DEPENDENCY_SPECS["par2"].assets("v1.5.0")
    monkeypatch.setattr(updater, "_request_json", lambda _url: _release("v1.5.0", assets))

    version, release_assets = updater.fetch_latest("par2")

    assert version == "v1.5.0"
    assert set(release_assets) == set(assets)


@pytest.mark.parametrize(
    "release",
    [
        {"tag_name": "", "draft": False, "prerelease": False, "assets": []},
        {"tag_name": "v2", "draft": True, "prerelease": False, "assets": []},
        {"tag_name": "v2", "draft": False, "prerelease": True, "assets": []},
        {"tag_name": "v2\nchanged=true", "draft": False, "prerelease": False, "assets": []},
        {"tag_name": "v2", "draft": False, "prerelease": False, "assets": "invalid"},
    ],
)
def test_fetch_latest_rejects_malformed_or_unstable_releases(monkeypatch: pytest.MonkeyPatch, release: dict[str, object]) -> None:
    monkeypatch.setattr(updater, "_request_json", lambda _url: release)

    with pytest.raises(RuntimeError):
        updater.fetch_latest("nyuu")


def test_fetch_latest_rejects_missing_required_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "_request_json", lambda _url: _release("v0.5.0", ("unrelated.zip",)))

    with pytest.raises(RuntimeError, match="missing required assets"):
        updater.fetch_latest("nyuu")


def test_asset_checksum_uses_github_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = "a" * 64
    monkeypatch.setattr(updater, "_download_sha256", lambda _url: pytest.fail("asset should not be downloaded"))

    assert updater._asset_sha256({"name": "asset", "digest": f"sha256:{expected}"}) == expected


def test_asset_checksum_downloads_when_digest_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = "b" * 64
    monkeypatch.setattr(updater, "_download_sha256", lambda _url: expected)

    assert updater._asset_sha256({"name": "asset", "digest": None, "browser_download_url": "https://github.com/a/b"}) == expected


def test_asset_checksum_rejects_non_github_download_url() -> None:
    with pytest.raises(RuntimeError, match="invalid download URL"):
        updater._asset_sha256({"name": "asset", "digest": None, "browser_download_url": "https://github.com.example/asset"})


def test_asset_checksum_rejects_malformed_digest() -> None:
    with pytest.raises(RuntimeError, match="invalid digest"):
        updater._asset_sha256({"name": "asset", "digest": "sha256:nope"})


def test_current_version_is_a_no_op(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pin = tmp_path / "ffmpeg.py"
    pin.write_text("unchanged", encoding="utf-8")
    monkeypatch.setitem(updater.PIN_PATHS, "ffmpeg", pin)
    monkeypatch.setattr(updater, "fetch_latest", lambda _dependency: (DEPENDENCY_VERSIONS["ffmpeg"], {}))

    assert updater.update_dependency("ffmpeg") == (False, DEPENDENCY_VERSIONS["ffmpeg"])
    assert pin.read_text(encoding="utf-8") == "unchanged"


def test_update_replaces_version_and_complete_checksum_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pin = tmp_path / "ffmpeg.py"
    pin.write_text("old pin", encoding="utf-8")
    new_asset = "ffmpeg-10.0-essentials_build.zip"
    digest = "c" * 64
    monkeypatch.setitem(updater.PIN_PATHS, "ffmpeg", pin)
    monkeypatch.setattr(updater, "fetch_latest", lambda _dependency: ("10.0", {new_asset: {"name": new_asset, "digest": f"sha256:{digest}"}}))

    assert updater.update_dependency("ffmpeg") == (True, "10.0")
    pin_content = pin.read_text(encoding="utf-8")
    assert 'VERSION = "10.0"' in pin_content
    assert f'REPOSITORY = "{DEPENDENCY_REPOSITORIES["ffmpeg"]}"' in pin_content
    assert f'"{new_asset}": "{digest}"' in pin_content
    assert "old pin" not in pin_content
    ast.parse(pin_content)


def test_validation_failure_does_not_write_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pin = tmp_path / "ffmpeg.py"
    pin.write_text("unchanged", encoding="utf-8")
    monkeypatch.setitem(updater.PIN_PATHS, "ffmpeg", pin)

    def fail(_dependency: str) -> tuple[str, dict[str, dict[str, object]]]:
        raise RuntimeError("missing required assets")

    monkeypatch.setattr(updater, "fetch_latest", fail)
    with pytest.raises(RuntimeError, match="missing required assets"):
        updater.update_dependency("ffmpeg")
    assert pin.read_text(encoding="utf-8") == "unchanged"


def test_download_sha256_streams_content(monkeypatch: pytest.MonkeyPatch) -> None:
    content = b"release asset"

    class Response:
        def __init__(self, response_content: bytes) -> None:
            self.content = response_content

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def read(self, _size: int) -> bytes:
            result, self.content = self.content, b""
            return result

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *_args, **_kwargs: Response(content))

    assert updater._download_sha256("https://github.com/example/asset") == hashlib.sha256(content).hexdigest()


def test_main_writes_pull_request_metadata_to_github_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_path = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setattr(sys, "argv", ["update_binary_dependency.py", "ffmpeg"])
    monkeypatch.setattr(updater, "update_dependency", lambda _dependency: (True, "10.0/test"))

    updater.main()

    assert output_path.read_text(encoding="utf-8") == (
        "changed=true\n"
        f"previous_version={DEPENDENCY_VERSIONS['ffmpeg']}\n"
        "version=10.0/test\n"
        f"release_url=https://github.com/{DEPENDENCY_REPOSITORIES['ffmpeg']}/releases/tag/10.0%2Ftest\n"
        "asset_count=1\n"
    )
