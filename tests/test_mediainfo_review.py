# ruff: noqa: S101
from pathlib import Path
from typing import Any

import pytest

from src.mediainfo_review import MAX_REPORT_CHARS, report_items
from web_ui import server


def test_file_release_uses_clean_path_export(tmp_path: Path) -> None:
    (tmp_path / "MEDIAINFO.txt").write_text("Complete name : /srv/media/Fictional.Film.mkv", encoding="utf-8")
    (tmp_path / "MEDIAINFO_CLEANPATH.txt").write_text("Complete name : Fictional.Film.mkv", encoding="utf-8")

    kind, reports = report_items({"is_disc": ""}, tmp_path)

    assert kind == "mediainfo"
    assert reports == [{"key": "mediainfo", "label": "MediaInfo", "content": "Complete name : Fictional.Film.mkv"}]


def test_file_release_without_export_has_no_reports(tmp_path: Path) -> None:
    assert report_items({}, tmp_path) == ("mediainfo", [])


def test_bdmv_lists_summaries_in_disc_and_playlist_order(tmp_path: Path) -> None:
    for name in (
        "BD_SUMMARY_EXT_00.txt",
        "BD_SUMMARY_00_1.txt",
        "BD_SUMMARY_00.txt",
        "BD_SUMMARY_01.txt",
        "BD_SUMMARY_00.txt.bak",
        "MEDIAINFO.txt",
    ):
        (tmp_path / name).write_text(f"Disc Title: {name}", encoding="utf-8")

    kind, reports = report_items({"is_disc": "BDMV"}, tmp_path)

    assert kind == "bdinfo"
    assert [(report["key"], report["label"]) for report in reports] == [
        ("BD_SUMMARY_00", "Summary"),
        ("BD_SUMMARY_EXT_00", "Extended summary"),
        ("BD_SUMMARY_00_1", "Summary · Playlist 2"),
        ("BD_SUMMARY_01", "Summary · Disc 2"),
    ]


def test_dvd_reports_come_from_meta_without_server_paths(tmp_path: Path) -> None:
    meta: dict[str, Any] = {
        "is_disc": "DVD",
        "discs": [
            {"name": "DISC_A", "ifo_mi": "Complete name : /srv/discs/A/VIDEO_TS/VTS_01_0.IFO", "vob_mi": "Format : MPEG-PS"},
            {"name": "DISC_B", "ifo_mi": "Complete name : C:\\discs\\B\\VTS_01_0.IFO", "vob_mi": ""},
        ],
    }

    kind, reports = report_items(meta, tmp_path)

    assert kind == "mediainfo"
    assert reports == [
        {"key": "ifo_mi_0", "label": "IFO · DISC_A", "content": "Complete name : VTS_01_0.IFO"},
        {"key": "vob_mi_0", "label": "VOB · DISC_A", "content": "Format : MPEG-PS"},
        {"key": "ifo_mi_1", "label": "IFO · DISC_B", "content": "Complete name : VTS_01_0.IFO"},
    ]


def test_hddvd_report_strips_complete_name_path(tmp_path: Path) -> None:
    meta: dict[str, Any] = {"is_disc": "HDDVD", "discs": [{"evo_mi": "General\nComplete name : /srv/discs/HVDVD_TS/FEATURE_1.EVO\nFormat : MPEG-PS"}]}

    _kind, reports = report_items(meta, tmp_path)

    assert reports[0]["content"] == "General\nComplete name : FEATURE_1.EVO\nFormat : MPEG-PS"


def test_oversized_report_is_truncated(tmp_path: Path) -> None:
    (tmp_path / "MEDIAINFO_CLEANPATH.txt").write_text("x" * (MAX_REPORT_CHARS + 10), encoding="utf-8")

    _kind, reports = report_items({}, tmp_path)

    assert reports[0]["content"].endswith("[Report truncated]")
    assert len(reports[0]["content"]) < MAX_REPORT_CHARS + 50


def test_webui_mediainfo_api_returns_reports_for_the_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "MEDIAINFO_CLEANPATH.txt").write_text("Format : Matroska", encoding="utf-8")
    monkeypatch.setattr(server, "_resolve_execution_screenshot_review", lambda _session_id: (tmp_path, {"uuid": "release"}))
    monkeypatch.setattr(server, "_webui_auth_ok", lambda: True)

    with server.app.test_client() as client:
        response = client.get("/api/execution_mediainfo?session_id=session")

    assert response.status_code == 200
    assert response.headers["Cache-Control"].startswith("no-store")
    assert response.get_json() == {
        "success": True,
        "kind": "mediainfo",
        "reports": [{"key": "mediainfo", "label": "MediaInfo", "content": "Format : Matroska"}],
    }


def test_webui_mediainfo_api_reports_pending_until_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_webui_auth_ok", lambda: True)
    with server.app.test_client() as client:
        monkeypatch.setattr(server, "_resolve_execution_screenshot_review", lambda _session_id: None)
        assert client.get("/api/execution_mediainfo?session_id=missing").status_code == 404

        monkeypatch.setattr(server, "_resolve_execution_screenshot_review", lambda _session_id: (tmp_path, {"is_disc": "BDMV"}))
        response = client.get("/api/execution_mediainfo?session_id=session")
        assert response.status_code == 404
        assert response.get_json()["kind"] == "bdinfo"

        assert client.get("/api/execution_mediainfo").status_code == 400
