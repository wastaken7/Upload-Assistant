# ruff: noqa: S101
import ctypes
import stat
import subprocess
import sys
from contextlib import contextmanager
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
    original_hidden = server._is_hidden_browse_entry

    def hidden_entry(path):
        # Inject attributes into both Path-based search and DirEntry-based listing.
        return original_hidden(Path(path.path) if isinstance(path, server.os.DirEntry) else path)

    monkeypatch.setattr(server, "_is_hidden_browse_entry", hidden_entry)


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


def test_large_listing_reuses_metadata_and_root_resolution(browser, tmp_path, monkeypatch):
    folder = tmp_path / "Fictional Folder"
    folder.mkdir()
    first = tmp_path / "Fictional 000.txt"
    first.write_text("fictional", encoding="utf-8")
    expected_stat = first.stat()
    root_reads = []
    child_stats = []
    original_stat = Path.stat

    def roots():
        root_reads.append(True)
        return [str(tmp_path)]

    def tracked_stat(path, *args, **kwargs):
        if path.parent == tmp_path:
            child_stats.append(path.name)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(server, "_get_browse_roots", roots)
    monkeypatch.setattr(Path, "stat", tracked_stat)
    response = browser.get("/api/browse", query_string={"path": str(tmp_path)})
    assert response.status_code == 200
    small_root_reads = len(root_reads)
    for index in range(1, 64):
        (tmp_path / f"Fictional {index:03}.txt").touch()
    root_reads.clear()
    child_stats.clear()
    response = browser.get("/api/browse", query_string={"path": str(tmp_path)})
    assert response.status_code == 200
    assert len(root_reads) == small_root_reads
    assert child_stats == []
    items = response.json["items"]
    assert len(items) == 65
    assert [item["name"] for item in items] == sorted(item["name"] for item in items)
    assert items[0]["size"] == expected_stat.st_size
    assert items[0]["mtime"] == expected_stat.st_mtime
    assert items[0]["type"] == "file"
    assert items[-1]["type"] == "folder"
    assert items[-1]["size"] == 0


def test_listing_detects_replacement_link_from_nofollow_metadata(browser, tmp_path, monkeypatch):
    """A cached non-link type must not bypass validation of a replacement link."""
    entry_path = tmp_path / "Fictional Replacement.txt"
    entry_path.touch()
    inspected = []
    original_assert = server._assert_safe_resolved_path

    class ReplacedEntry:
        name = entry_path.name

        def stat(self, *, follow_symlinks=True):
            assert not follow_symlinks
            return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0, st_size=17, st_mtime=123)

        def is_symlink(self):
            return False  # Type from enumeration predates the replacement.

        def is_dir(self):
            return False

    @contextmanager
    def scandir(path):
        assert Path(path) == tmp_path
        yield iter([ReplacedEntry()])

    def validate(path):
        if Path(path) == entry_path:
            inspected.append(path)
            raise ValueError("Path outside allowed roots")
        return original_assert(path)

    monkeypatch.setattr(server.os, "scandir", scandir)
    monkeypatch.setattr(server, "_assert_safe_resolved_path", validate)
    response = browser.get("/api/browse", query_string={"path": str(tmp_path)})
    assert response.status_code == 200
    assert inspected == [entry_path]
    assert response.json["items"] == []


@pytest.mark.parametrize("directory", [False, True])
def test_listing_never_exposes_retargeted_link_metadata(browser, tmp_path, monkeypatch, directory):
    """Model a known symlink retargeted after its path passes validation."""
    entry_path = tmp_path / "Fictional Link.txt"
    entry_path.touch()
    original_assert = server._assert_safe_resolved_path
    attributes = stat.FILE_ATTRIBUTE_REPARSE_POINT | (stat.FILE_ATTRIBUTE_DIRECTORY if directory else 0)
    link_stat = SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=attributes, st_size=17, st_mtime=123)
    retargeted = False
    following_reads = []

    class LinkEntry:
        name = entry_path.name

        def stat(self, *, follow_symlinks=True):
            if not follow_symlinks:
                return link_stat
            following_reads.append(retargeted)
            return SimpleNamespace(st_size=987654, st_mtime=999999)

        def is_symlink(self):
            return True

        def is_dir(self):
            # A known symlink's following is_dir also populates its stat cache.
            self.stat()
            return directory

    @contextmanager
    def scandir(path):
        assert Path(path) == tmp_path
        yield iter([LinkEntry()])

    def validate(path):
        nonlocal retargeted
        if Path(path) == entry_path:
            retargeted = True
            return None
        return original_assert(path)

    monkeypatch.setattr(server.os, "scandir", scandir)
    monkeypatch.setattr(server, "_assert_safe_resolved_path", validate)
    response = browser.get("/api/browse", query_string={"path": str(tmp_path)})
    assert response.status_code == 200
    assert retargeted
    assert True not in following_reads
    assert response.json["items"] == [
        {
            "name": entry_path.name,
            "path": str(entry_path),
            "type": "folder" if directory else "file",
            "children": [] if directory else None,
            "mtime": link_stat.st_mtime,
            "size": 0 if directory else link_stat.st_size,
        }
    ]


def test_listing_still_validates_directory_link_targets(browser, tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    inside = root / "Fictional Inside"
    inside.mkdir()
    outside = tmp_path / "media-outside"
    outside.mkdir()
    links = [root / "Fictional Allowed Link", root / "Fictional Escaping Link"]
    try:
        for link, target in zip(links, [inside, outside], strict=True):
            if sys.platform == "win32":
                result = subprocess.run(  # noqa: S603 - only pytest-owned paths
                    ["cmd", "/c", "mklink", "/J", str(link), str(target)],  # noqa: S607 - Windows built-in
                    capture_output=True,
                    check=False,
                )
                assert result.returncode == 0, result.stderr
            else:
                link.symlink_to(target, target_is_directory=True)
        # The browser fixture normally allows tmp_path; narrow it for this request.
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(server, "_get_browse_roots", lambda: [str(root)])
            response = browser.get("/api/browse", query_string={"path": str(root)})
        assert response.status_code == 200
        assert {item["name"] for item in response.json["items"]} == {inside.name, links[0].name}
    finally:
        for link in links:
            if sys.platform == "win32" and link.exists():
                link.rmdir()
            elif link.is_symlink():
                link.unlink()


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
