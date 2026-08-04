# ruff: noqa: S101
import asyncio
from typing import Any, cast

import pytest

from src.console import logger
from src.dupe_checking import DupeChecker
from src.meta import Meta
from src.uphelper import UploadHelper

CONFIG: dict[str, Any] = {"DEFAULT": {"tmdb_api": "test-key"}, "TRACKERS": {"DARKPEERS": {}}}


def _tv_meta(name: str) -> Meta:
    return Meta(
        category="TV",
        name=name,
        uuid=name,
        type="WEBDL",
        source="WEB",
        resolution="1080p",
        season="S01",
        episode="E01",
        tag="-Kitsune",
        unattended=True,
    )


def _candidate(name: str, torrent_id: int) -> dict[str, object]:
    return {
        "name": name,
        "id": torrent_id,
        "link": f"https://darkpeers.org/torrents/{torrent_id}",
    }


def test_darkpeers_normal_release_marks_matching_repack_as_preferred() -> None:
    meta = _tv_meta("Show S01E01 1080p WEB-DL H.264-Kitsune")
    candidate = _candidate("Show S01E01 REPACK 1080p WEB-DL H.264-Kitsune", 117485)

    dupes = asyncio.run(DupeChecker({"DEFAULT": {}}).filter_dupes([candidate], meta, "DARKPEERS"))

    assert [dupe.get("id") for dupe in dupes] == [117485]
    assert meta["DARKPEERS_preferred_repack"]["id"] == 117485


def test_darkpeers_repack_keeps_existing_original_for_manual_report() -> None:
    meta = _tv_meta("Show S01E01 REPACK 1080p WEB-DL H.264-Kitsune")
    candidate = _candidate("Show S01E01 1080p WEB-DL H.264-Kitsune", 117400)

    dupes = asyncio.run(DupeChecker({"DEFAULT": {}}).filter_dupes([candidate], meta, "DARKPEERS"))

    assert [dupe.get("id") for dupe in dupes] == [117400]
    assert meta["DARKPEERS_repack_replaces"]["link"] == "https://darkpeers.org/torrents/117400"


def test_darkpeers_blocks_normal_release_when_repack_is_available() -> None:
    meta = _tv_meta("Show S01E01 1080p WEB-DL H.264-Kitsune")
    meta.dupe = True
    candidate = _candidate("Show S01E01 REPACK 1080p WEB-DL H.264-Kitsune", 117485)
    helper = UploadHelper(CONFIG)

    dupes = asyncio.run(DupeChecker({"DEFAULT": {}}).filter_dupes([candidate], meta, "DARKPEERS"))
    is_dupe, _ = asyncio.run(helper.dupe_check(cast(list[dict[str, Any] | str], dupes), meta, "DARKPEERS"))

    assert is_dupe is True


def test_darkpeers_allows_repack_and_preserves_original_report_target() -> None:
    meta = _tv_meta("Show S01E01 REPACK 1080p WEB-DL H.264-Kitsune")
    original = _candidate("Show S01E01 1080p WEB-DL H.264-Kitsune", 117400)
    helper = UploadHelper(CONFIG)

    dupes = asyncio.run(DupeChecker({"DEFAULT": {}}).filter_dupes([original], meta, "DARKPEERS"))
    is_dupe, result = asyncio.run(helper.dupe_check(cast(list[dict[str, Any] | str], dupes), meta, "DARKPEERS"))

    assert is_dupe is False
    assert result["DARKPEERS_repack_replaces"]["id"] == 117400


def test_darkpeers_repack_policy_requires_exact_release_group() -> None:
    normal = _tv_meta("Show S01E01 1080p WEB-DL H.264-Kitsune")
    other_group_repack = _candidate("Show S01E01 REPACK 1080p WEB-DL H.264-NotKitsune", 117486)
    replacement = _tv_meta("Show S01E01 REPACK 1080p WEB-DL H.264-Kitsune")
    substring_group_original = _candidate("Show S01E01 1080p WEB-DL H.264-KitsuneX", 117401)
    checker = DupeChecker({"DEFAULT": {}})

    asyncio.run(checker.filter_dupes([other_group_repack], normal, "DARKPEERS"))
    asyncio.run(checker.filter_dupes([substring_group_original], replacement, "DARKPEERS"))

    assert normal.get("DARKPEERS_preferred_repack") is None
    assert replacement.get("DARKPEERS_repack_replaces") is None


def test_repack_detection_change_does_not_affect_other_trackers() -> None:
    meta = _tv_meta("Show S01E01 REPACK 1080p WEB-DL H.264-Kitsune")
    meta.uuid = "show-without-marker"
    candidate = _candidate("Show S01E01 1080p WEB-DL H.264-Kitsune", 117400)

    dupes = asyncio.run(DupeChecker({"DEFAULT": {}}).filter_dupes([candidate], meta, "AITHER"))

    assert [dupe.get("id") for dupe in dupes] == [117400]


def test_darkpeers_repack_markers_are_reset_before_each_filter_pass() -> None:
    meta = _tv_meta("Show S01E01 1080p WEB-DL H.264-Kitsune")
    checker = DupeChecker({"DEFAULT": {}})
    repack = _candidate("Show S01E01 REPACK 1080p WEB-DL H.264-Kitsune", 117485)
    ordinary = _candidate("Show S01E01 1080p WEB-DL H.264-Kitsune", 117400)

    asyncio.run(checker.filter_dupes([repack], meta, "DARKPEERS"))
    assert meta.get("DARKPEERS_preferred_repack") is not None

    asyncio.run(checker.filter_dupes([ordinary], meta, "DARKPEERS"))

    assert meta.get("DARKPEERS_preferred_repack") is None
    assert meta.get("DARKPEERS_repack_replaces") is None


@pytest.mark.parametrize("torrent_id", ["²", "9" * 5000])
def test_darkpeers_repack_notice_strips_terminal_controls_and_rejects_invalid_id(monkeypatch: pytest.MonkeyPatch, torrent_id: str) -> None:
    meta = _tv_meta("Show S01E01 1080p WEB-DL H.264-Kitsune")
    malicious: dict[str, object] = {
        "name": "\x1b]8;;https://evil.invalid\x07click\x1b]8;;\x07[bold red]fake[/bold red]",
        "id": torrent_id,
        "link": "file:///etc/passwd",
    }
    meta["DARKPEERS_preferred_repack"] = malicious
    messages: list[str] = []

    def record_message(message: object, *_args: object, **_kwargs: object) -> None:
        messages.append(str(message))

    monkeypatch.setattr(logger, "info", record_message)

    is_dupe, _ = asyncio.run(UploadHelper(CONFIG).dupe_check([malicious], meta, "DARKPEERS"))

    assert is_dupe is True
    assert any(r"\[bold red]fake\[/bold red]" in message for message in messages)
    assert all("\x1b" not in message and "\x07" not in message for message in messages)
    assert all("evil.invalid" not in message for message in messages)
    assert all("file:///etc/passwd" not in message for message in messages)
    assert all("https://darkpeers.org/torrents/" not in message for message in messages)


def test_darkpeers_repack_notice_builds_trusted_url_from_numeric_id(monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _tv_meta("Show S01E01 1080p WEB-DL H.264-Kitsune")
    candidate: dict[str, object] = {"name": "[bold red]fake[/bold red]", "id": 117485, "link": "javascript:alert(1)"}
    meta["DARKPEERS_preferred_repack"] = candidate
    messages: list[str] = []

    def record_message(message: object, *_args: object, **_kwargs: object) -> None:
        messages.append(str(message))

    monkeypatch.setattr(logger, "info", record_message)

    is_dupe, _ = asyncio.run(UploadHelper(CONFIG).dupe_check([candidate], meta, "DARKPEERS"))

    assert is_dupe is True
    assert any("https://darkpeers.org/torrents/117485" in message for message in messages)
    assert all("javascript:" not in message for message in messages)
