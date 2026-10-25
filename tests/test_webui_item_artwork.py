"""Queue item covers shown beside each release in the Web UI Results panel."""

import json
from pathlib import Path

import pytest

import web_ui.server as server
from src import webui_events

TEST_NONCE = "fictional-nonce"


def _item_events(output: str) -> list[dict[str, object]]:
    prefix = webui_events.event_prefix(TEST_NONCE)
    events = [json.loads(line.removeprefix(prefix)) for line in output.splitlines() if line.startswith(prefix)]
    return [event for event in events if event["kind"] == "item"]


@pytest.fixture
def gui_env(monkeypatch):
    monkeypatch.setenv(webui_events.GUI_EVENTS_ENV, "1")
    monkeypatch.setenv(webui_events.GUI_EVENT_NONCE_ENV, TEST_NONCE)
    monkeypatch.setattr(webui_events, "_current_item", None)
    monkeypatch.setattr(webui_events, "_active_stage", None)
    monkeypatch.setattr(webui_events, "_started_stages", set())


@pytest.fixture
def state_tmp(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(server, "STATE_DIR", tmp_path / "state")
    artwork = tmp_path / "state" / "tmp" / "fictional-release" / "artwork"
    artwork.mkdir(parents=True)
    return artwork


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"artwork_url": "https://images.invalid/cover.jpg", "tmdb_poster_path": "/poster.jpg"}, "https://images.invalid/cover.jpg"),
        ({"tmdb_poster_path": "/poster.jpg"}, "https://image.tmdb.org/t/p/w500/poster.jpg"),
        ({"artwork_url": "javascript:alert(1)"}, None),
        ({"tmdb_poster_path": "poster.jpg"}, None),
    ],
)
def test_public_cover_urls_are_published_with_the_item(gui_env, capsys, meta, expected) -> None:
    webui_events.begin_item("/media/Fictional.Movie.2020.mkv", 1, 1)
    webui_events.update_item(artwork=meta)

    updated = _item_events(capsys.readouterr().out)[-1]
    assert updated.get("artwork") == expected
    assert "artwork_file" not in updated


def test_local_cover_is_published_as_a_file_for_the_server_only(gui_env, capsys, tmp_path) -> None:
    cover = tmp_path / "MUSIC_COVER.jpg"
    cover.write_bytes(b"jpg")
    (tmp_path / "notes.txt").write_text("not an image")

    webui_events.begin_item("/media/Fictional Album", 1, 1)
    webui_events.update_item(artwork={"artwork_path": str(tmp_path / "notes.txt")})
    webui_events.update_item(artwork={"artwork_path": str(cover)})

    ignored, local = _item_events(capsys.readouterr().out)[1:]
    assert "artwork_file" not in ignored
    assert local["artwork_file"] == str(cover.resolve())


def test_a_found_cover_is_kept_by_later_updates_and_reset_for_the_next_item(gui_env, capsys) -> None:
    webui_events.begin_item("/media/First.mkv", 1, 2)
    webui_events.update_item(artwork={"tmdb_poster_path": "/first.jpg"})
    webui_events.update_item(artwork={"artwork_path": "/removed/POSTER.png"})
    webui_events.update_item(personal_release=True)
    webui_events.begin_item("/media/Second.mkv", 2, 2)

    *first_updates, second = _item_events(capsys.readouterr().out)
    assert [event["artwork"] for event in first_updates[1:]] == ["https://image.tmdb.org/t/p/w500/first.jpg"] * 3
    assert "artwork" not in second


def test_item_artwork_does_no_work_outside_the_web_ui(monkeypatch, capsys) -> None:
    monkeypatch.delenv(webui_events.GUI_EVENTS_ENV, raising=False)
    monkeypatch.setattr(webui_events, "_current_item", {"index": 1, "total": 1, "name": "x"})
    monkeypatch.setattr(webui_events, "_item_artwork", lambda _meta: pytest.fail("artwork resolved outside the Web UI"))

    webui_events.update_item(artwork={"artwork_url": "https://images.invalid/cover.jpg"})

    assert capsys.readouterr().out == ""


def test_server_swaps_a_local_cover_for_a_per_item_url(state_tmp) -> None:
    cover = state_tmp / "POSTER.png"
    cover.write_bytes(b"png")
    process_state: dict[str, object] = {"path": "/media/Fictional.Movie.2020.mkv"}

    event = server._resolve_gui_item_artwork("session 1", process_state, {"kind": "item", "index": 2, "artwork_file": str(cover)})

    assert "artwork_file" not in event
    assert str(event["artwork"]).startswith("/api/execution_item_cover?session_id=session%201&item=2&v=")
    assert process_state["item_covers"] == {2: cover.resolve()}


def test_server_drops_covers_outside_temp_storage_and_the_release(state_tmp, tmp_path) -> None:
    release = tmp_path / "media" / "Fictional Album"
    release.mkdir(parents=True)
    sidecar = release / "cover.jpg"
    sidecar.write_bytes(b"jpg")
    elsewhere = tmp_path / "private" / "photo.jpg"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"jpg")
    process_state: dict[str, object] = {"path": str(release)}

    accepted = server._resolve_gui_item_artwork("s", process_state, {"kind": "item", "index": 1, "artwork_file": str(sidecar)})
    rejected = server._resolve_gui_item_artwork("s", process_state, {"kind": "item", "index": 2, "artwork_file": str(elsewhere)})

    assert "artwork" in accepted
    assert rejected == {"kind": "item", "index": 2}
    assert process_state["item_covers"] == {1: sidecar.resolve()}


def test_server_leaves_other_events_untouched() -> None:
    event = {"kind": "notice", "artwork_file": "/etc/passwd"}

    assert server._resolve_gui_item_artwork("s", {}, event) is event


def test_item_cover_endpoint_serves_only_recorded_covers(state_tmp, monkeypatch) -> None:
    cover = state_tmp / "POSTER.png"
    cover.write_bytes(b"fictional-png")
    monkeypatch.setattr(server, "_webui_auth_ok", lambda: True)
    monkeypatch.setitem(server.active_processes, "session-1", {"item_covers": {1: cover}})
    client = server.app.test_client()

    served = client.get("/api/execution_item_cover?session_id=session-1&item=1&v=1")
    missing = client.get("/api/execution_item_cover?session_id=session-1&item=2")
    invalid = client.get("/api/execution_item_cover?session_id=session-1&item=%C2%B2")

    assert served.status_code == 200
    assert served.data == b"fictional-png"
    assert served.mimetype == "image/png"
    assert missing.status_code == 404
    assert invalid.status_code == 400
