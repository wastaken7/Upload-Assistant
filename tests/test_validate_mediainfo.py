# ruff: noqa: S101
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.exceptions import NoAudioMediaError, UnreadableMediaError
from src.exportmi import validate_mediainfo
from src.meta import Meta


def _meta(tracks: list[dict[str, Any]]) -> Meta:
    return cast(
        Meta,
        SimpleNamespace(
            filelist=["/media/Fictional.Movie.2020.1080p.WEB-DL-GROUP.mkv"],
            path="/media/Fictional.Movie.2020.1080p.WEB-DL-GROUP.mkv",
            ua_name="Upload-Assistant",
            mediainfo={"media": {"track": tracks}},
        ),
    )


def test_general_only_report_is_unreadable_not_no_audio() -> None:
    # MediaInfo returns only General when the MKV header was never written, e.g. a preallocated download.
    with pytest.raises(UnreadableMediaError, match="no video or audio streams"):
        validate_mediainfo(_meta([{"@type": "General", "UniqueID": "123"}]))


def test_video_without_audio_still_reports_no_audio() -> None:
    with pytest.raises(NoAudioMediaError):
        validate_mediainfo(_meta([{"@type": "General", "UniqueID": "123"}, {"@type": "Video"}]))


def test_video_with_audio_passes() -> None:
    assert validate_mediainfo(_meta([{"@type": "General", "UniqueID": "123"}, {"@type": "Video"}, {"@type": "Audio"}]))
