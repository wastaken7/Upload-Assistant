# ruff: noqa: S101
from pathlib import Path

import pytest

from web_ui import server

IGDB_IMAGE = {"img_url": "https://images.example.invalid/med.jpg", "raw_url": "https://images.example.invalid/full.jpg"}
THUMB_ONLY_IMAGE = {"img_url": "https://images.example.invalid/thumb-only.jpg"}


@pytest.mark.parametrize(
    ("meta_data", "expected"),
    [
        ({"category": "MOVIE"}, True),
        ({"category": "TV", "is_disc": "BDMV"}, True),
        ({"category": "MOVIE", "is_disc": "DVD"}, False),
        ({"category": "GAME"}, False),
        ({"category": "book"}, False),
        ({"category": "MUSIC"}, False),
    ],
)
def test_screenshot_capture_support_by_category(meta_data: dict[str, object], expected: bool) -> None:
    assert server._screenshot_capture_supported(meta_data) is expected


@pytest.fixture
def game_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    meta = {"uuid": "release", "category": "GAME", "image_list": [IGDB_IMAGE]}
    monkeypatch.setattr(server, "_resolve_execution_screenshot_review", lambda _session_id: (tmp_path, meta))
    monkeypatch.setattr(server, "_webui_auth_ok", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    return tmp_path


@pytest.mark.usefixtures("game_review")
def test_game_igdb_images_are_listed_without_capture_actions() -> None:
    with server.app.test_client() as client:
        data = client.get("/api/execution_screenshots?session_id=session").get_json()

    assert data["success"] is True
    assert data["can_add"] is False
    assert [(item["source"], item["can_replace"], item["image_url"]) for item in data["screenshots"]] == [
        ("remote", False, IGDB_IMAGE["img_url"]),
    ]


def test_game_rejects_capture_endpoints(game_review: Path) -> None:
    with server.app.test_client() as client:
        added = client.post("/api/execution_screenshots/add", json={"session_id": "session"})
        replaced = client.post("/api/execution_screenshots/remote-0/replace", json={"session_id": "session"})

    assert added.status_code == 400
    assert replaced.status_code == 400
    assert not (game_review / "screenshots").exists()


def test_remote_images_expose_thumbnail_and_full_size_urls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = {"uuid": "release", "category": "MOVIE", "image_list": [IGDB_IMAGE, THUMB_ONLY_IMAGE]}
    monkeypatch.setattr(server, "_resolve_execution_screenshot_review", lambda _session_id: (tmp_path, meta))
    monkeypatch.setattr(server, "_webui_auth_ok", lambda: True)

    with server.app.test_client() as client:
        screenshots = client.get("/api/execution_screenshots?session_id=session").get_json()["screenshots"]

    assert [(item["image_url"], item["full_image_url"]) for item in screenshots] == [
        (IGDB_IMAGE["img_url"], IGDB_IMAGE["raw_url"]),
        (THUMB_ONLY_IMAGE["img_url"], THUMB_ONLY_IMAGE["img_url"]),
    ]
