"""Folder-scoped search uses the existing authenticated browse contract."""

from pathlib import Path
import os
import subprocess

import pytest

import web_ui.server as server
from tests.test_webui_browse_limits import HEADERS, browser  # noqa: F401


def search(browser, **params):
    return browser.get("/api/browse_search", query_string={"q": "movie", **params}, headers=HEADERS)


def test_scope_walks_only_selected_folder(browser, monkeypatch):
    root = Path(server._get_browse_roots()[0])
    child = root / "selected"
    (child / "nested").mkdir(parents=True)
    (child / "nested" / "movie.mkv").touch()
    visited = []
    walk = server.os.walk

    def record(path, **kwargs):
        visited.append(Path(path))
        yield from walk(path, **kwargs)

    monkeypatch.setattr(server.os, "walk", record)
    response = search(browser, path=str(child))
    assert response.status_code == 200
    assert [item["path"] for item in response.json["items"]] == [str(child / "nested" / "movie.mkv")]
    assert visited == [child]


@pytest.mark.parametrize("limit", [None, 150, 900])
def test_folders_displace_earlier_files_across_roots(browser, monkeypatch, tmp_path, limit):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for index in range(510):
        (first / f"movie {index}.mkv").touch()
    for index in range(110):
        (second / f"movie {index}").mkdir()
    monkeypatch.setenv("UA_BROWSE_ROOTS", f"{first},{second}")
    response = search(browser, **({} if limit is None else {"max_results": limit}))
    items = response.json["items"]
    expected = 100 if limit is None else min(limit, 500)
    assert len(items) == expected
    assert sum(item["type"] == "folder" for item in items) == min(expected, 110)
    assert response.json["truncated"] is True


@pytest.mark.parametrize("scope", ["", "missing", "outside", "file", "duplicate"])
def test_invalid_scope_does_not_walk(browser, monkeypatch, tmp_path, scope):
    root = Path(server._get_browse_roots()[0])
    values = {"": "", "missing": str(root / "missing"), "outside": str(tmp_path), "file": str(root / "Movie" / "movie.mkv"), "duplicate": [str(root), str(root)]}

    def no_walk(*args, **kwargs):
        pytest.fail("Invalid scope must not start a filesystem walk")

    monkeypatch.setattr(server.os, "walk", no_walk)
    assert search(browser, path=values[scope]).status_code == 400


def test_links_are_not_searched_or_accepted_as_scope(browser, tmp_path):
    root = Path(server._get_browse_roots()[0])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "movie secret.mkv").touch()
    link = root / "movie link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires OS permission")
    assert all(not Path(item["path"]).is_relative_to(link) for item in search(browser).json["items"])
    assert search(browser, path=str(link)).status_code == 400


@pytest.mark.skipif(os.name != "nt", reason="Real Windows junction creation")
def test_windows_junction_is_pruned_and_rejected_as_scope(browser, tmp_path):
    root = Path(server._get_browse_roots()[0])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "movie secret.mkv").touch()
    junction = root / "movie junction"
    subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(outside)], check=True, capture_output=True)
    try:
        assert junction.is_junction()
        assert all(not Path(item["path"]).is_relative_to(junction) for item in search(browser).json["items"])
        assert search(browser, path=str(junction)).status_code == 400
    finally:
        junction.rmdir()


def test_unreadable_selection_is_an_error(browser, monkeypatch):
    root = Path(server._get_browse_roots()[0])
    original = server.os.scandir

    def denied(path):
        if Path(path) == root:
            raise PermissionError("Test denial")
        return original(path)

    monkeypatch.setattr(server.os, "scandir", denied)
    assert search(browser, path=str(root)).status_code == 400


def test_desc_filter_hidden_entries_and_overlapping_roots(browser, monkeypatch):
    root = Path(server._get_browse_roots()[0])
    movie = root / "Movie"
    (movie / "movie.txt").touch()
    (movie / ".movie.txt").touch()
    (movie / ".hidden" / "movie").mkdir(parents=True)
    monkeypatch.setenv("UA_BROWSE_ROOTS", f"{root},{movie}")
    items = search(browser, filter="desc").json["items"]
    assert [item["name"] for item in items] == ["Movie", "movie.txt"]
    assert search(browser, q="no match").json["items"] == []


def test_nested_folders_displace_files(browser):
    root = Path(server._get_browse_roots()[0])
    child = root / "selected"
    nested = child / "nested"
    nested.mkdir(parents=True)
    for index in range(120):
        (child / f"movie {index}.mkv").touch()
    for index in range(100):
        (nested / f"movie {index}").mkdir()
    items = search(browser, path=str(child)).json["items"]
    assert len(items) == 100
    assert all(item["type"] == "folder" for item in items)


def test_internal_link_is_not_an_alternative_scope(browser):
    root = Path(server._get_browse_roots()[0])
    link = root / "alias"
    try:
        link.symlink_to(root / "Movie", target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires OS permission")
    assert search(browser, path=str(link)).status_code == 400
