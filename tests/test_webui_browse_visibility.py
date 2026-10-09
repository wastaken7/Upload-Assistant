# ruff: noqa: S101
import ctypes
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import web_ui.server as server


@pytest.fixture
def browser(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_get_browse_roots", lambda: [str(tmp_path)])
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server.limiter, "enabled", False)
    return server.app.test_client()


def _set_mock_attributes(monkeypatch, attributes):
    original_stat = Path.stat

    def entry_stat(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if path.name not in attributes:
            return result
        fields = {name: getattr(result, name) for name in dir(result) if name.startswith("st_")}
        fields["st_file_attributes"] = attributes[path.name]
        return SimpleNamespace(**fields)

    monkeypatch.setattr(Path, "stat", entry_stat)


@pytest.mark.parametrize("file_filter", ["video", "desc"])
def test_listing_and_search_hide_system_entries_and_do_not_descend_into_them(browser, tmp_path, monkeypatch, file_filter):
    folders = ["$RECYCLE.BIN", "System Volume Information", ".hidden-folder", "Hidden Folder", "System Folder"]
    for name in folders:
        directory = tmp_path / name
        directory.mkdir()
        (directory / "Fictional Secret.txt").touch()
    files = ["Hidden Fictional.txt", "System Fictional.txt", ".Fictional.txt", "Fictional Visible.txt", "$Fictional Visible.txt"]
    for name in files:
        (tmp_path / name).touch()
    visible_folder = tmp_path / "Fictional Folder"
    visible_folder.mkdir()
    (visible_folder / "Fictional Child.txt").touch()
    _set_mock_attributes(
        monkeypatch,
        {
            "Hidden Folder": stat.FILE_ATTRIBUTE_HIDDEN,
            "System Folder": stat.FILE_ATTRIBUTE_SYSTEM,
            "Hidden Fictional.txt": stat.FILE_ATTRIBUTE_HIDDEN,
            "System Fictional.txt": stat.FILE_ATTRIBUTE_SYSTEM,
        },
    )

    response = browser.get("/api/browse", query_string={"path": str(tmp_path), "filter": file_filter})
    assert response.status_code == 200
    assert {item["name"] for item in response.json["items"]} == {"Fictional Folder", "Fictional Visible.txt", "$Fictional Visible.txt"}
    assert response.json["count"] == 3

    visited = []
    original_walk = server.os.walk

    def tracked_walk(*args, **kwargs):
        for result in original_walk(*args, **kwargs):
            visited.append(Path(result[0]).name)
            yield result

    monkeypatch.setattr(server.os, "walk", tracked_walk)
    response = browser.get("/api/browse_search", query_string={"q": "Fictional", "filter": file_filter})
    assert response.status_code == 200
    assert {item["name"] for item in response.json["items"]} == {"Fictional Folder", "Fictional Child.txt", "Fictional Visible.txt"}
    assert not set(folders).intersection(visited)
    response = browser.get("/api/browse_search", query_string={"q": "$Fictional", "filter": file_filter})
    assert response.status_code == 200
    assert [item["name"] for item in response.json["items"]] == ["$Fictional Visible.txt"]


@pytest.mark.parametrize("name", ["$recycle.bin", "$RECYCLE.BIN", "SYSTEM VOLUME INFORMATION", ".hidden"])
def test_known_system_names_are_filtered_case_insensitively_without_reading_them(name):
    assert server._is_hidden_browse_entry(Path(name))


def test_missing_entries_are_skipped():
    assert server._is_hidden_browse_entry(Path("nonexistent-fictional-entry"))


def test_search_does_not_inspect_attributes_of_nonmatching_files(browser, tmp_path, monkeypatch):
    for name in ["Fictional Match.mkv", "Unrelated.mkv", ".Fictional Hidden.mkv"]:
        (tmp_path / name).touch()
    inspected = []
    original = server._is_hidden_browse_entry

    def inspect(path):
        inspected.append(path.name)
        return original(path)

    monkeypatch.setattr(server, "_is_hidden_browse_entry", inspect)
    response = browser.get("/api/browse_search", query_string={"q": "Fictional"})
    assert response.status_code == 200
    assert [item["name"] for item in response.json["items"]] == ["Fictional Match.mkv"]
    assert "Unrelated.mkv" not in inspected
    assert "Fictional Match.mkv" in inspected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows filesystem attributes")
def test_real_windows_hidden_and_system_attributes_are_filtered(browser, tmp_path):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    kernel.SetFileAttributesW.restype = ctypes.c_int
    original = {}
    try:
        for name, attributes in [("Fictional Hidden.txt", stat.FILE_ATTRIBUTE_HIDDEN), ("Fictional System.txt", stat.FILE_ATTRIBUTE_SYSTEM)]:
            path = tmp_path / name
            path.touch()
            original[path] = path.stat().st_file_attributes
            assert kernel.SetFileAttributesW(str(path), original[path] | attributes), ctypes.get_last_error()
        (tmp_path / "Fictional Visible.txt").touch()
        for route, query in [("/api/browse", {"path": str(tmp_path)}), ("/api/browse_search", {"q": "Fictional"})]:
            response = browser.get(route, query_string=query)
            assert response.status_code == 200
            assert [item["name"] for item in response.json["items"]] == ["Fictional Visible.txt"]
    finally:
        for path, attributes in original.items():
            assert kernel.SetFileAttributesW(str(path), attributes), ctypes.get_last_error()
