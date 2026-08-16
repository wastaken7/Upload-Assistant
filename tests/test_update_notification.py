# ruff: noqa: S101

import asyncio

import upload


def test_update_notification_reuses_successful_check_during_cooldown(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(upload, "STATE_DIR", tmp_path)
    monkeypatch.setattr(upload, "CODE_DIR", tmp_path)
    monkeypatch.setattr(upload, "get_local_version", lambda _path: "v1.0")
    monkeypatch.setattr(upload, "get_remote_version", lambda _url: ("v2.0", '__version__ = "v2.0"'))
    monkeypatch.setattr(upload, "config", {"DEFAULT": {"update_notification": True, "update_notification_cache_hours": 4}})

    assert asyncio.run(upload.update_notification()) == "v1.0"

    def fail_if_called(_url: str) -> tuple[str, str]:
        raise AssertionError("The remote version check should use the cooldown cache")

    monkeypatch.setattr(upload, "get_remote_version", fail_if_called)
    assert asyncio.run(upload.update_notification()) == "v1.0"


def test_update_notification_cache_expires_after_configured_interval(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(upload, "STATE_DIR", tmp_path)
    monkeypatch.setattr(upload, "time", type("Clock", (), {"time": staticmethod(lambda: 14_401)})())
    upload._update_notification_cache_path().write_text('{"checked_at": 0, "remote_version": "v2.0", "remote_content": "content"}', encoding="utf-8")

    assert upload._read_update_notification_cache(4) is None
