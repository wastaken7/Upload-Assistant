import asyncio
import hashlib
from pathlib import Path

import pytest

from bin import get_dynamic_hdr_tools
from src.dynamic_hdr_plot import _formats, _generate_plot, _source_files, dynamic_hdr_plot_enabled
from src.get_desc import DescriptionBuilder
from src.meta import Meta


def test_formats_selects_each_dynamic_metadata_type() -> None:
    assert _formats(Meta(hdr="DV HDR10+")) == ["dovi", "hdr10plus"]  # noqa: S101
    assert _formats(Meta(hdr="HDR10+")) == ["hdr10plus"]  # noqa: S101
    assert _formats(Meta(hdr="HDR")) == []  # noqa: S101


def test_source_files_limits_to_supported_existing_video_files(tmp_path: Path) -> None:
    first = tmp_path / "first.mkv"
    second = tmp_path / "second.mp4"
    ignored = tmp_path / "notes.txt"
    first.touch()
    second.touch()
    ignored.touch()

    meta = Meta(filelist=[str(first), str(ignored), str(second)])

    assert _source_files(meta, 1) == [first]  # noqa: S101
    assert _source_files(meta, 2) == [first, second]  # noqa: S101


def test_description_section_uses_dynamic_hdr_plot_images() -> None:
    meta = Meta(
        dynamic_hdr_plot=True,
        dynamic_hdr_plot_images=[{"web_url": "https://host/view", "raw_url": "https://host/plot.png"}],
    )
    builder = DescriptionBuilder("TEST", {"DEFAULT": {"dynamic_hdr_plot_header": "[b]HDR plots[/b]"}, "TRACKERS": {"TEST": {}}})

    section = asyncio.run(builder.get_dynamic_hdr_plot_section(meta))

    assert "[b]HDR plots[/b]" in section  # noqa: S101
    assert "https://host/plot.png" in section  # noqa: S101


def test_existing_versioned_binary_does_not_download(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    binary_dir = tmp_path / "bin" / "dovi_tool" / "windows" / "amd64"
    binary_dir.mkdir(parents=True)
    binary = binary_dir / "dovi_tool.exe"
    binary.touch()
    (binary_dir / "2.3.3").write_text("dovi_tool 2.3.3\n", encoding="utf-8")

    monkeypatch.setattr(get_dynamic_hdr_tools.shutil, "which", lambda _: None)
    monkeypatch.setattr(get_dynamic_hdr_tools.platform, "system", lambda: "Windows")
    monkeypatch.setattr(get_dynamic_hdr_tools.platform, "machine", lambda: "AMD64")

    class NoDownloadClient:
        def __init__(self, *_args, **_kwargs) -> None:
            raise AssertionError("The downloader must not be initialized when the versioned binary exists")

    monkeypatch.setattr(get_dynamic_hdr_tools.httpx, "AsyncClient", NoDownloadClient)

    result = asyncio.run(get_dynamic_hdr_tools.get_tool(str(tmp_path), "dovi"))

    assert result == str(binary)  # noqa: S101


def test_downloaded_asset_checksum_is_verified(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    asset = "test-asset"
    content = b"known-good"
    monkeypatch.setitem(get_dynamic_hdr_tools.ASSET_SHA256, asset, hashlib.sha256(content).hexdigest())

    get_dynamic_hdr_tools._verify_checksum(asset, content)
    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        get_dynamic_hdr_tools._verify_checksum(asset, b"tampered")


def test_mp4_is_remuxed_to_annex_b_hevc(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "release.mp4"
    source.touch()
    commands: list[list[str]] = []

    def fake_run(command: list[str]) -> None:
        commands.append(command)
        if command[-1].endswith(".png"):
            Path(command[-1]).touch()

    monkeypatch.setattr("src.dynamic_hdr_plot._run", fake_run)

    asyncio.run(_generate_plot("dovi_tool", "dovi", source, tmp_path))

    assert commands[0][-3:-1] == ["-f", "hevc"]  # noqa: S101
    assert Path(commands[0][-1]).name.startswith("release_")  # noqa: S101
    assert commands[1][2] == commands[0][-1]  # noqa: S101


def test_plot_artifacts_are_unique_for_same_named_sources(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    first = tmp_path / "first" / "release.mkv"
    second = tmp_path / "second" / "release.mkv"
    first.parent.mkdir()
    second.parent.mkdir()
    first.touch()
    second.touch()

    def fake_run(command: list[str]) -> None:
        if command[-1].endswith(".png"):
            Path(command[-1]).touch()

    monkeypatch.setattr("src.dynamic_hdr_plot._run", fake_run)

    first_plot = asyncio.run(_generate_plot("dovi_tool", "dovi", first, tmp_path))
    second_plot = asyncio.run(_generate_plot("dovi_tool", "dovi", second, tmp_path))

    assert first_plot != second_plot  # noqa: S101


def test_tracker_override_enables_dynamic_hdr_plot() -> None:
    meta = Meta(trackers=["TEST"])
    config = {"DEFAULT": {"add_dynamic_hdr_plot": False}, "TRACKERS": {"TEST": {"add_dynamic_hdr_plot": True}}}

    assert dynamic_hdr_plot_enabled(meta, config)  # noqa: S101
