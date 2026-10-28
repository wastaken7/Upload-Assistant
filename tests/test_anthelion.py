import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx

from src.meta import Meta
from src.trackers.GAZELLE.anthelion import Anthelion


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
    monkeypatch.setattr("src.trackers.GAZELLE.anthelion.httpx.AsyncClient", _Client)
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


def test_anthelion_normalizes_and_filters_tmdb_genres() -> None:
    meta = SimpleNamespace(genres=["Science Fiction", "Action", "Not A Tracker Tag"], imdb_info={}, ant_user_tags=True)
    tracker = object.__new__(Anthelion)
    tracker.tracker = "ANTHELION"

    assert asyncio.run(tracker.get_tags(meta)) == ["sci.fi", "action"]  # noqa: S101
    assert meta.ant_user_tags is False  # noqa: S101


def test_anthelion_duplicate_search_uses_discovered_imdb_id(monkeypatch) -> None:
    class SearchResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json():
            return {"item": []}

    class SearchClient:
        params = None

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, **kwargs):
            type(self).params = kwargs["params"]
            return SearchResponse()

    monkeypatch.setattr("src.trackers.GAZELLE.anthelion.httpx.AsyncClient", SearchClient)
    tracker = Anthelion({"TRACKERS": {"ANTHELION": {"api_key": "secret"}}})
    meta = Meta(tmdb=None, imdb_id=7654321, imdb="stale", resolution="1080p")

    assert asyncio.run(tracker.search_existing(meta)) == []  # noqa: S101
    assert SearchClient.params["imdbid"] == "tt7654321"  # noqa: S101


def test_anthelion_does_not_retry_refused_upload(tmp_path: Path, monkeypatch) -> None:
    class SlotFilled(_Response):
        status_code = 409
        text = '{"error": "slot is already filled", "trump_key": "key"}'

    _Client.posts = 0
    _Client.response = SlotFilled()
    meta = _meta(tmp_path)

    assert asyncio.run(_tracker(monkeypatch).upload(meta)) is False  # noqa: S101
    assert _Client.posts == 1  # noqa: S101
    assert "HTTP 409" in meta.tracker_status["ANTHELION"]["status_message"]  # noqa: S101


def test_anthelion_upload_payload_matches_api_spec(tmp_path: Path, monkeypatch) -> None:
    class Success(_Response):
        status_code = 201

        def json(self):
            return {"status": "success"}

    sent: dict = {}

    async def capture_post(_self, **kwargs):
        sent.update(kwargs["data"])
        return Success()

    _Client.response = Success()
    tracker = _tracker(monkeypatch)
    monkeypatch.setattr(_Client, "post", capture_post)
    meta = _meta(tmp_path)
    meta.scene = True

    assert asyncio.run(tracker.upload(meta)) is True  # noqa: S101
    assert sent["scene"] == 1  # noqa: S101
    assert "censored" not in sent  # noqa: S101
    assert "audioformat" not in sent  # noqa: S101
    assert "noreleasegroup" not in sent  # noqa: S101


def test_anthelion_flags_use_current_site_names() -> None:
    meta = SimpleNamespace(
        edition="4K Remaster Director's",
        audio="Dual-Audio DD+ 7.1 Atmos",
        has_commentary=False,
        manual_commentary=False,
        three_d="",
        hdr="",
        distributor="",
        type="ENCODE",
        original_language="ja",
        audio_languages=["Japanese", "English"],
    )
    tracker = object.__new__(Anthelion)

    assert asyncio.run(tracker.get_flags(meta)) == ["Directors", "Remastered", "EnglishDub", "Atmos"]  # noqa: S101


def test_anthelion_english_original_with_foreign_dub_is_not_english_dub() -> None:
    meta = SimpleNamespace(
        edition="",
        audio="Dual-Audio DD 5.1",
        has_commentary=False,
        manual_commentary=False,
        three_d="",
        hdr="",
        distributor="",
        type="ENCODE",
        original_language="en",
        audio_languages=["English", "French"],
    )
    tracker = object.__new__(Anthelion)

    assert "EnglishDub" not in asyncio.run(tracker.get_flags(meta))  # noqa: S101


def test_anthelion_retries_request_timeout_status(tmp_path: Path, monkeypatch) -> None:
    class RequestTimeout(_Response):
        status_code = 408
        text = "Request Timeout"

    _Client.posts = 0
    _Client.response = RequestTimeout()
    meta = _meta(tmp_path)
    monkeypatch.setattr("src.trackers.GAZELLE.anthelion.asyncio.sleep", _instant_sleep)

    assert asyncio.run(_tracker(monkeypatch).upload(meta)) is False  # noqa: S101
    assert _Client.posts == 3  # noqa: S101


async def _instant_sleep(_delay: float, result=None):
    return result


def test_anthelion_duplicate_search_pads_short_imdb_id(monkeypatch) -> None:
    class SearchResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json():
            return {"item": []}

    class SearchClient:
        params = None

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, **kwargs):
            type(self).params = kwargs["params"]
            return SearchResponse()

    monkeypatch.setattr("src.trackers.GAZELLE.anthelion.httpx.AsyncClient", SearchClient)
    tracker = Anthelion({"TRACKERS": {"ANTHELION": {"api_key": "secret"}}})
    meta = Meta(tmdb=None, imdb_id=12345, resolution="1080p")

    assert asyncio.run(tracker.search_existing(meta)) == []  # noqa: S101
    assert SearchClient.params["imdbid"] == "tt0012345"  # noqa: S101
    assert SearchClient.params["limit"] == "100"  # noqa: S101
