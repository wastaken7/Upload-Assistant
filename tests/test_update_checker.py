from __future__ import annotations

import io
import json

from src import update_checker


def test_fetch_unreleased_changes_returns_safe_latest_first_commits(monkeypatch) -> None:
    payload = {
        "ahead_by": 2,
        "html_url": "https://github.com/wastaken7/Upload-Assistant/compare/v3.9...development",
        "commits": [
            {
                "sha": "aaaaaaaa",
                "html_url": "https://example.invalid/unsafe",
                "author": {"login": "first-author"},
                "commit": {
                    "message": "feat(core): first change\n\nLonger description",
                    "author": {"name": "Fallback Author", "date": "2026-08-29T10:00:00Z"},
                    "committer": {"date": "2026-08-29T11:00:00Z"},
                },
            },
            {
                "sha": "bbbbbbbb",
                "html_url": "https://github.com/wastaken7/Upload-Assistant/commit/bbbbbbbb",
                "author": None,
                "commit": {
                    "message": "fix(webui): second change",
                    "author": {"name": "Second Author", "date": "2026-08-30T10:00:00Z"},
                    "committer": {},
                },
            },
        ],
    }
    monkeypatch.setattr(
        update_checker.urllib.request,
        "urlopen",
        lambda _request, timeout: io.BytesIO(json.dumps(payload).encode("utf-8")),
    )

    result = update_checker.fetch_unreleased_changes("v3.9")

    assert result is not None
    assert result["available"] is True
    assert result["ahead_by"] == 2
    assert [commit["short_sha"] for commit in result["commits"]] == ["bbbbbbb", "aaaaaaa"]
    assert result["commits"][0]["author"] == "Second Author"
    assert result["commits"][1]["summary"] == "feat(core): first change"
    assert result["commits"][1]["commit_url"] == (
        "https://github.com/wastaken7/Upload-Assistant/commit/aaaaaaaa"
    )


def test_update_status_reuses_cli_compatible_cache(tmp_path, monkeypatch) -> None:
    code_dir = tmp_path / "code"
    state_dir = tmp_path / "state"
    (code_dir / "src").mkdir(parents=True)
    state_dir.mkdir()
    (code_dir / "src" / "version.py").write_text('__version__ = "v1.0"\n', encoding="utf-8")
    remote_content = '__version__ = "v2.0"\n\n"## What\'s Changed\\n* Better UI"\n'
    (state_dir / "update_notification.json").write_text(
        json.dumps(
            {
                "checked_at": 100,
                "remote_version": "v2.0",
                "remote_content": remote_content,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(update_checker.time, "time", lambda: 101)
    monkeypatch.setattr(
        update_checker,
        "fetch_remote_version",
        lambda: (_ for _ in ()).throw(AssertionError("cache should be reused")),
    )

    status = update_checker.get_update_status(
        code_dir=code_dir,
        state_dir=state_dir,
        cache_hours=4,
    )

    assert status["update_available"] is True
    assert status["current_version"] == "v1.0"
    assert status["latest_version"] == "v2.0"
    assert status["changelog"] == "## What's Changed\n* Better UI"


def test_disabled_update_status_does_not_fetch(tmp_path, monkeypatch) -> None:
    code_dir = tmp_path / "code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "version.py").write_text('__version__ = "v1.0"\n', encoding="utf-8")
    monkeypatch.setattr(
        update_checker,
        "fetch_remote_version",
        lambda: (_ for _ in ()).throw(AssertionError("disabled checks must not fetch")),
    )

    status = update_checker.get_update_status(
        enabled=False,
        code_dir=code_dir,
        state_dir=tmp_path / "state",
    )

    assert status["enabled"] is False
    assert status["update_available"] is False


def test_forced_update_status_bypasses_valid_cache(tmp_path, monkeypatch) -> None:
    code_dir = tmp_path / "code"
    state_dir = tmp_path / "state"
    (code_dir / "src").mkdir(parents=True)
    state_dir.mkdir()
    (code_dir / "src" / "version.py").write_text('__version__ = "v1.0"\n', encoding="utf-8")
    (state_dir / "update_notification.json").write_text(
        json.dumps(
            {
                "checked_at": 100,
                "remote_version": "v1.0",
                "remote_content": '__version__ = "v1.0"',
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(update_checker.time, "time", lambda: 101)
    monkeypatch.setattr(
        update_checker,
        "fetch_remote_version",
        lambda: ("v2.0", '__version__ = "v2.0"\n\n"New release"'),
    )

    status = update_checker.get_update_status(
        force=True,
        code_dir=code_dir,
        state_dir=state_dir,
        cache_hours=4,
    )

    assert status["latest_version"] == "v2.0"
    assert status["update_available"] is True


def test_changelog_history_fetches_and_reuses_cache(tmp_path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    releases = [
        {
            "version": "v2.0",
            "title": "Version 2.0",
            "changelog": "* feat(webui): add changelog viewer",
            "release_url": "https://github.com/wastaken7/Upload-Assistant/releases/tag/v2.0",
            "published_at": "2026-08-29T00:00:00Z",
            "prerelease": False,
        }
    ]
    unreleased = {
        "available": True,
        "base_version": "v2.0",
        "branch": "development",
        "compare_url": "https://github.com/wastaken7/Upload-Assistant/compare/v2.0...development",
        "ahead_by": 1,
        "commits": [
            {
                "sha": "abcdef1234567890",
                "short_sha": "abcdef1",
                "summary": "feat(webui): show unreleased changes",
                "commit_url": "https://github.com/wastaken7/Upload-Assistant/commit/abcdef1234567890",
                "author": "contributor",
                "committed_at": "2026-08-30T00:00:00Z",
            }
        ],
    }
    monkeypatch.setattr(update_checker.time, "time", lambda: 100)
    monkeypatch.setattr(update_checker, "fetch_release_history", lambda: releases)
    monkeypatch.setattr(update_checker, "fetch_unreleased_changes", lambda _base: unreleased)

    status = update_checker.get_changelog_history(state_dir=state_dir)

    assert status["success"] is True
    assert status["source"] == "github"
    assert status["releases"] == releases
    assert status["unreleased"] == unreleased

    monkeypatch.setattr(update_checker.time, "time", lambda: 101)
    monkeypatch.setattr(
        update_checker,
        "fetch_release_history",
        lambda: (_ for _ in ()).throw(AssertionError("cache should be reused")),
    )
    monkeypatch.setattr(
        update_checker,
        "fetch_unreleased_changes",
        lambda _base: (_ for _ in ()).throw(AssertionError("cache should be reused")),
    )

    cached_status = update_checker.get_changelog_history(state_dir=state_dir)

    assert cached_status["success"] is True
    assert cached_status["source"] == "cache"
    assert cached_status["releases"] == releases
    assert cached_status["unreleased"] == unreleased


def test_changelog_history_falls_back_to_bundled_release(tmp_path, monkeypatch) -> None:
    code_dir = tmp_path / "code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "version.py").write_text(
        '__version__ = "v1.0"\n\n"## What\'s Changed\\n* fix(webui): bundled notes"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(update_checker, "fetch_release_history", lambda: None)

    status = update_checker.get_changelog_history(
        code_dir=code_dir,
        state_dir=tmp_path / "state",
    )

    assert status["success"] is True
    assert status["source"] == "local"
    assert status["stale"] is True
    assert status["releases"][0]["version"] == "v1.0"
    assert "bundled notes" in status["releases"][0]["changelog"]
