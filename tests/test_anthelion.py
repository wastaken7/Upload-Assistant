import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx

from src.trackers.anthelion import Anthelion


class _Response:
    status_code = 200

    def json(self):
        return {"success": False}


class _Client:
    posts = 0
    response: _Response | Exception = _Response()

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, **_kwargs):
        type(self).posts += 1
        if isinstance(type(self).response, Exception):
            raise type(self).response
        return type(self).response


def _meta(tmp_path: Path) -> SimpleNamespace:
    release_dir = tmp_path / "tmp" / "release"
    release_dir.mkdir(parents=True)
    (release_dir / "BASE.torrent").write_bytes(b"torrent")
    (release_dir / "[ANTHELION].torrent").write_bytes(b"torrent")
    (release_dir / "MEDIAINFO_CLEANPATH.txt").write_text("General\n", encoding="utf-8")
    return SimpleNamespace(
        base_dir=str(tmp_path),
        uuid="release",
        mkbrr=False,
        max_piece_size=None,
        path="",
        tracker_status={"ANTHELION": {}},
        edition="",
        audio="AAC",
        has_commentary=False,
        manual_commentary=False,
        three_d="",
        hdr="",
        distributor="",
        type="",
        is_disc="",
        scene=False,
        tmdb="1",
        tag="",
        anon=False,
        adult_media=False,
        image_list=[],
        ant_user_tags=False,
        ua_name="Upload Assistant",
        current_version=None,
        debug=False,
    )


def _tracker(monkeypatch) -> Anthelion:
    tracker = Anthelion({"DEFAULT": {"max_retries": 3}, "TRACKERS": {"ANTHELION": {"api_key": "secret"}}})

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", no_op)
    monkeypatch.setattr(tracker, "get_flags", no_op)
    monkeypatch.setattr(tracker, "get_audio", lambda _meta: asyncio.sleep(0, result="AAC"))
    monkeypatch.setattr(tracker, "get_type", lambda _meta: asyncio.sleep(0, result=0))
    monkeypatch.setattr(tracker, "get_tags", lambda _meta: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(tracker, "get_release_group", lambda _meta: asyncio.sleep(0, result=""))
    monkeypatch.setattr(tracker, "edit_desc", lambda _meta: asyncio.sleep(0, result="description"))
    monkeypatch.setattr("src.trackers.anthelion.httpx.AsyncClient", _Client)
    return tracker


def test_anthelion_rejects_false_success(tmp_path: Path, monkeypatch) -> None:
    _Client.posts = 0
    _Client.response = _Response()
    meta = _meta(tmp_path)

    assert asyncio.run(_tracker(monkeypatch).upload(meta)) is False  # noqa: S101
    assert meta.tracker_status["ANTHELION"]["status_message"] == "data error: {'success': False}"  # noqa: S101


def test_anthelion_does_not_retry_timeout_after_submission(tmp_path: Path, monkeypatch) -> None:
    _Client.posts = 0
    _Client.response = httpx.ReadTimeout("timed out")
    meta = _meta(tmp_path)

    assert asyncio.run(_tracker(monkeypatch).upload(meta)) is False  # noqa: S101
    assert _Client.posts == 1  # noqa: S101
    assert "may have uploaded" in meta.tracker_status["ANTHELION"]["status_message"]  # noqa: S101


def test_anthelion_imdb_tags_are_not_marked_as_manual() -> None:
    meta = SimpleNamespace(genres=[], imdb_info={"genres": ["Action"]}, ant_user_tags=True)
    tracker = object.__new__(Anthelion)
    tracker.tracker = "ANTHELION"

    assert asyncio.run(tracker.get_tags(meta)) == ["action"]  # noqa: S101
    assert meta.ant_user_tags is False  # noqa: S101
