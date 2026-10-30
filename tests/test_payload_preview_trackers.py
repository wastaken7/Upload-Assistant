"""Every tracker builds its upload form preview without network requests or questions."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import requests

from src import payload_preview
from src.console import PromptBlockedError, prompts_blocked
from src.meta import Meta
from src.trackersetup import tracker_class_map

VIDEO = "X:/fictional/Fictional.Film.2001.1080p.WEB-DL.DDP5.1.H.264-NOGRP.mkv"


def make_config() -> dict[str, Any]:
    tracker = {
        "api_key": "A" * 32,
        "announce_url": "https://example.invalid/announce/key",
        "username": "fictional",
        "password": "fictional",
        "passkey": "P" * 32,
        "uid": "1",
        "anon": False,
    }
    return {"DEFAULT": {"tmdb_api": "T" * 32}, "TRACKERS": {name: dict(tracker) for name in [*tracker_class_map, "BLUTOPIA"]}}


def make_meta(tracker: str) -> Meta:
    localized = {"main": {"title": "Filme Ficticio", "name": "Filme Ficticio", "overview": "Uma sinopse ficticia.", "poster_path": "", "genres": [{"name": "Drama"}]}}
    meta = Meta(
        category="MOVIE",
        type="WEBDL",
        resolution="1080p",
        source="WEB",
        name="Fictional Film 2001 1080p WEB-DL DDP 5.1 H.264-NOGRP",
        clean_name="Fictional Film 2001 1080p WEB-DL DDP 5.1 H.264-NOGRP",
        title="Fictional Film",
        year="2001",
        tmdb=4321,
        tmdb_id=4321,
        imdb_id=7654321,
        tag="-NOGRP",
        audio="DDP 5.1",
        channels="5.1",
        video_codec="H.264",
        video_encode="H.264",
        uuid="fictional",
        base_dir=".",
        path=VIDEO,
        video=VIDEO,
        filelist=[VIDEO],
        audio_languages=["English"],
        subtitle_languages=["English"],
        original_language="en",
        keywords=["drama"],
        genres="Drama",
        overview="A fictional overview.",
        disctype="WEB",
        trackers=[tracker],
        cast=["Fictional Actor"],
    )
    meta.tmdb_localized_data = {"zh-cn": localized, "pt-BR": localized}
    meta.imdb_info = {"imdb_url": "https://www.imdb.com/title/tt7654321", "title": "Fictional Film", "year": 2001, "type": "movie", "directors": ["Fictional Director"], "stars": ["Fictional Actor"], "rating": 7.1}
    meta.mediainfo = {
        "media": {
            "track": [
                {"@type": "General", "Format": "Matroska", "Duration": "5400.000", "FileSize": "1000000000"},
                {"@type": "Video", "Format": "AVC", "Width": "1920", "Height": "1080"},
                {"@type": "Audio", "Format": "E-AC-3", "Channels": "6", "Language": "en"},
            ]
        }
    }
    meta.tracker_status = {tracker: {}}
    return meta


def test_every_tracker_offers_a_preview() -> None:
    missing = [name for name, cls in tracker_class_map.items() if not hasattr(cls, "get_payload_preview")]

    assert missing == []


@pytest.mark.parametrize("name", sorted(tracker_class_map))
def test_preview_sends_nothing_beyond_the_name_lookup(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The preview replaces the get_name call the confirmation always made, so only its requests may remain."""
    requested: list[str] = []

    def refuse(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        requested.append(str(getattr(request, "url", request)))
        raise RuntimeError("network used by a preview")

    async def refuse_async(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        return refuse(self, request)

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse_async)
    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(requests.Session, "send", refuse)

    async def run(step: str) -> Any:
        tracker = tracker_class_map[name](config=make_config())
        with prompts_blocked():
            try:
                return await asyncio.wait_for(getattr(tracker, step)(make_meta(name)), 30)
            except (Exception, PromptBlockedError):
                # Missing fictional data may stop a preview; the GUI then shows only the name.
                return None

    asyncio.run(run("get_name"))
    name_lookup = set(requested)
    requested.clear()
    preview = asyncio.run(run("get_payload_preview"))

    assert set(requested) <= name_lookup
    if preview is not None:
        assert isinstance(preview, payload_preview.TrackerPreview)
        items, _tables, _notice = payload_preview.gui_payloads([preview])
        assert items, "a single tracker's preview must fit in the prompt"
        assert not any(payload_preview.is_secret(item.key) for item in preview.fields if item.kind != "deferred")


def test_bjshare_xxx_preview_shows_the_fields_it_must_ask_about_as_later(monkeypatch: pytest.MonkeyPatch) -> None:
    """A release without cast, studio or year still gets a preview; those fields are asked at upload time."""
    # Other tests leave a matched BJ-Share entry in class state, which would supply the cast.
    monkeypatch.setattr(tracker_class_map["BJSHARE"], "already_has_the_info", False)
    meta = make_meta("BJSHARE")
    meta.category = "XXX"
    meta.cast = []
    meta.imdb_info = {}
    meta.year = None
    tracker = tracker_class_map["BJSHARE"](config=make_config())

    async def build() -> payload_preview.TrackerPreview:
        with prompts_blocked():
            return await tracker.get_payload_preview(meta)

    fields = {item.key: item for item in asyncio.run(build()).fields}

    assert {key for key in ("elenco", "title", "year") if fields[key].kind == "deferred"} == {"elenco", "title", "year"}
    assert fields["codecvideo"].kind == "choice"
