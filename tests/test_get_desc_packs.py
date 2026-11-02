# ruff: noqa: S101

import asyncio

import pytest

from src.get_desc import DescriptionBuilder
from src.meta import Meta

HEADER = "[center][b]Screenshots[/b][/center]"


def _image(name):
    return {"web_url": f"https://example.com/{name}", "raw_url": f"https://example.com/{name}.png"}


@pytest.fixture
def pack(tmp_path, monkeypatch):
    (tmp_path / "tmp" / "pack").mkdir(parents=True)
    builder = DescriptionBuilder(
        "TEST",
        {"DEFAULT": {"screenshot_header": HEADER, "multiScreens": 1, "processLimit": 1, "fileLimit": 1}, "TRACKERS": {"TEST": {}}},
    )
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="pack",
        category="TV",
        tv_pack=True,
        filelist=["Show.S01E01.mkv", "Show.S01E02.mkv"],
        screens=1,
        image_list=[_image("first")],
        new_images_file_1=[_image("second")],
        description="Release description",
    )
    # Keep real MediaInfo formatting, but avoid running the external binary.
    monkeypatch.setattr("src.get_desc.MediaInfo.parse", lambda *_args, **_kwargs: "General\nDuration : 42 min\n")
    return builder, meta


def _render(builder, meta):
    return asyncio.run(
        builder.general_description_generator(
            meta,
            audio_spectrogram=False,
            bluray=False,
            book=False,
            custom_header=False,
            custom_signature=False,
            game=False,
            languages=False,
            logo=False,
            mediainfo=False,
            menu_screenshots=False,
            nfo=False,
            tonemapped_header=False,
            tv_info=False,
            ua_signature=False,
            user_description=False,
            music=False,
            dynamic_hdr_plot=False,
        )
    )


@pytest.mark.parametrize("hide_header", [True, False])
def test_first_file_has_filename_and_respects_lone_header_setting(pack, hide_header):
    pack[0].config["DEFAULT"]["hide_screenshot_header_if_only_section"] = hide_header
    result = _render(*pack)

    assert result.count("Show.S01E01") == 1
    assert result.count(HEADER) == (0 if hide_header else 1)
    assert result.count(_image("first")["raw_url"]) == 1
    assert "Show.S01E02" not in result


def test_later_file_keeps_mediainfo_screenshots_and_spoilers(pack):
    builder, meta = pack
    builder.config["DEFAULT"]["processLimit"] = 2

    result = _render(builder, meta)

    assert "[spoiler=Other files]" in result
    assert "[spoiler=Show.S01E02]" in result
    assert "[b]Duration:[/b] 42 min" in result
    assert _image("second")["raw_url"] in result


def test_zero_multi_screens_keeps_only_main_screenshots(pack):
    builder, meta = pack
    builder.config["DEFAULT"].update(multiScreens=0, processLimit=2)

    result = _render(builder, meta)

    assert _image("first")["raw_url"] in result
    assert _image("second")["raw_url"] not in result
    assert "Show.S01E" not in result
    assert "42 min" not in result


def test_tracker_override_replaces_main_screenshots_and_keeps_pack_layout(pack):
    builder, meta = pack
    builder.config["DEFAULT"]["processLimit"] = 2
    meta.tracker_image_collections = {"TEST": {"screenshots": [_image("override")]}}

    result = _render(builder, meta)

    assert _image("override")["raw_url"] in result
    assert _image("first")["raw_url"] not in result
    assert "Show.S01E01" in result
    assert "[spoiler=Show.S01E02]" in result
    assert _image("second")["raw_url"] in result


def test_pack_capture_does_not_run_global_cleanup(tmp_path, monkeypatch):
    (tmp_path / "tmp" / "pack").mkdir(parents=True)
    builder = DescriptionBuilder(
        "TEST",
        {"DEFAULT": {"multiScreens": 2, "processLimit": 2, "fileLimit": 1}, "TRACKERS": {"TEST": {}}},
    )
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="pack",
        category="TV",
        filelist=["Show.S01E01.mkv", "Show.S01E02.mkv"],
        screens=1,
        image_list=[_image("first")],
        skip_imghost_upload=True,
    )
    capture_kwargs = []

    async def screenshots(*_args, **kwargs):
        capture_kwargs.append(kwargs)
        return []

    monkeypatch.setattr(builder.takescreens_manager, "screenshots", screenshots)
    monkeypatch.setattr("src.get_desc.MediaInfo.parse", lambda *_args, **_kwargs: "General\nDuration : 42 min\n")

    asyncio.run(builder._handle_discs_and_screenshots(meta, [], meta.image_list, 2))

    assert capture_kwargs == [{"cleanup_after_capture": False, "capture_group": "FILE_1"}]


@pytest.fixture
def pipelined_pack(tmp_path, monkeypatch):
    (tmp_path / "tmp" / "pack").mkdir(parents=True)
    builder = DescriptionBuilder(
        "TEST",
        {"DEFAULT": {"multiScreens": 1, "processLimit": 3, "fileLimit": 3}, "TRACKERS": {"TEST": {}}},
    )
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="pack",
        category="TV",
        filelist=["Show.S01E01.mkv", "Show.S01E02.mkv", "Show.S01E03.mkv"],
        screens=1,
        image_list=[_image("first")],
    )
    events = []
    captured = {}

    async def screenshots(_path, group, *_args, **_kwargs):
        events.append(("capture", group))
        await asyncio.sleep(0)
        captured[group] = [tmp_path / f"{group}-0.png"]

    async def upload_screens(_meta, *args, **_kwargs):
        name = args[4][0]
        events.append(("upload_start", name))
        await asyncio.sleep(0.01)
        events.append(("upload_end", name))
        return [{"img_url": name, "raw_url": name, "web_url": name}], 1

    async def save_image_links(*_args, **_kwargs):
        return None

    monkeypatch.setattr(builder.takescreens_manager, "screenshots", screenshots)
    monkeypatch.setattr(builder.uploadscreens_manager, "upload_screens", upload_screens)
    monkeypatch.setattr(builder.common, "save_image_links", save_image_links)
    monkeypatch.setattr("src.get_desc.manifest_files", lambda _base, _uuid, group: captured.get(group, []))
    monkeypatch.setattr("src.get_desc.MediaInfo.parse", lambda *_args, **_kwargs: "General\nDuration : 42 min\n")
    return builder, meta, events


def test_pack_captures_next_file_while_hosting_current_one(pipelined_pack):
    builder, meta, events = pipelined_pack

    asyncio.run(builder._handle_discs_and_screenshots(meta, [], meta.image_list, 1))

    assert events.index(("capture", "FILE_2")) < events.index(("upload_end", "FILE_1-0.png"))
    assert [event for event in events if event[0] == "capture"] == [("capture", "FILE_1"), ("capture", "FILE_2")]
    assert meta.new_images_file_1 == [{"img_url": "FILE_1-0.png", "raw_url": "FILE_1-0.png", "web_url": "FILE_1-0.png"}]
    assert meta.new_images_file_2 == [{"img_url": "FILE_2-0.png", "raw_url": "FILE_2-0.png", "web_url": "FILE_2-0.png"}]


def test_pack_hosting_error_lets_pending_capture_finish(pipelined_pack, monkeypatch):
    builder, meta, events = pipelined_pack

    async def failing_upload(_meta, *args, **_kwargs):
        events.append(("upload_start", args[4][0]))
        raise RuntimeError("host down")

    monkeypatch.setattr(builder.uploadscreens_manager, "upload_screens", failing_upload)

    with pytest.raises(RuntimeError, match="host down"):
        asyncio.run(builder._handle_discs_and_screenshots(meta, [], meta.image_list, 1))

    # Cancelling a capture mid-way exits the process, so it must complete instead.
    assert ("capture", "FILE_2") in events


def test_pack_files_reuse_saved_images_without_capturing(pipelined_pack):
    builder, meta, events = pipelined_pack
    meta.new_images_file_1 = [_image("saved")]

    asyncio.run(builder._handle_discs_and_screenshots(meta, [], meta.image_list, 1))

    assert [event for event in events if event[0] == "capture"] == [("capture", "FILE_2")]
    assert meta.new_images_file_1 == [_image("saved")]


def test_pack_file_mediainfo_is_parsed_once_per_file_version(tmp_path, monkeypatch):
    from src import get_desc

    video = tmp_path / "Show.S01E02.mkv"
    video.write_bytes(b"x")
    calls = []

    def parse(path, **_kwargs):
        calls.append(path)
        return f"General\nComplete name : {path}\n"

    monkeypatch.setattr("src.get_desc.MediaInfo.parse", parse)
    monkeypatch.setattr(get_desc, "_pack_mediainfo_cache", {})

    first = asyncio.run(get_desc._pack_file_mediainfo(str(video)))
    second = asyncio.run(get_desc._pack_file_mediainfo(str(video)))
    video.write_bytes(b"xy")
    asyncio.run(get_desc._pack_file_mediainfo(str(video)))

    assert first == second
    assert calls == [str(video), str(video)]
