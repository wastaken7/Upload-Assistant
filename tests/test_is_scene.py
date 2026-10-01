# ruff: noqa: S101

import json
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.is_scene import SceneFileMismatchError, SceneManager
from src.meta import Meta


class _Response:
    def __init__(self, payload: dict[str, Any] | None = None, content: bytes = b"") -> None:
        self.status_code = 200
        self._payload = payload
        self.content = content

    def json(self) -> dict[str, Any]:
        assert self._payload is not None
        return self._payload


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.requested_urls: list[str] = []

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, url: str, **_kwargs: Any) -> _Response:
        self.requested_urls.append(url)
        if "/v1/search/" in url:
            return _Response(
                {
                    "resultsCount": 1,
                    "results": [
                        {
                            "release": "Example.Release.2024.1080p.WEB.H264-GROUP",
                            "hasNFO": "yes",
                            "imdbId": "1234567",
                        }
                    ],
                }
            )
        if "/v1/details/" in url:
            return _Response({"files": [{"name": "example.release.2024.1080p.web.h264-group.nfo"}]})
        if "/download/file/" in url:
            return _Response(content=b"scene nfo contents")
        raise AssertionError(f"Unexpected request: {url}")


@pytest.mark.asyncio
async def test_default_meta_searches_srrdb_and_downloads_nfo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeAsyncClient()
    events: list[tuple[str, str, str]] = []

    async def record_event(family: str, **kwargs: Any) -> None:
        assert kwargs["service"] == "srrdb"
        events.append((family, kwargs["operation"], kwargs["outcome"]))

    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    monkeypatch.setattr("src.is_scene.record_event_async", record_event)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-test", category="MOVIE")

    video, scene, imdb = await SceneManager({"DEFAULT": {}}).is_scene(
        "/downloads/Example.Release.2024.1080p.WEB.H264-GROUP.mkv",
        meta,
    )

    release = "Example.Release.2024.1080p.WEB.H264-GROUP"
    nfo_path = tmp_path / "tmp" / "scene-test" / "example.release.2024.1080p.web.h264-group.nfo"

    assert client.requested_urls == [
        f"https://api.srrdb.com/v1/search/r:{release}",
        f"https://api.srrdb.com/v1/details/{release}",
        f"https://www.srrdb.com/download/file/{release}/example.release.2024.1080p.web.h264-group.nfo",
    ]
    assert (video, scene, imdb) == (f"{release}.mkv", True, 1234567)
    assert meta.scene_name == release
    assert meta.scene_nfo_file == nfo_path
    assert meta.nfo is True
    assert meta.auto_nfo is True
    assert nfo_path.read_bytes() == b"scene nfo contents"
    assert events == [("api", "search", "success"), ("api", "details", "success"), ("api", "nfo_download", "success")]

    await SceneManager({"DEFAULT": {}}).is_scene("/downloads/Example.Release.2024.1080p.WEB.H264-GROUP.mkv", meta)
    assert len(client.requested_urls) == 3
    assert len(events) == 3


_BASENAME = "generic-title.2024.1080p.bluray-examplegroup"
_RELEASE = "Generic-Title.2024.1080p.BluRay.x264-EXAMPLEGROUP"
_SEARCH_URL = f"https://api.srrdb.com/v1/search/store-real-filename:{_BASENAME}.mkv"
_DETAILS_URL = f"https://api.srrdb.com/v1/details/{_RELEASE}"
_EMPTY_SEARCH = {"resultsCount": 0, "results": [], "warnings": []}
_RESULT = {"release": _RELEASE, "hasNFO": "yes", "imdbId": "1234567"}


class _RoutedClient(_FakeAsyncClient):
    def __init__(self, routes: dict[str, _Response | Exception]) -> None:
        super().__init__()
        self.routes = routes

    async def get(self, url: str, **_kwargs: Any) -> _Response:
        self.requested_urls.append(url)
        if url not in self.routes and "/search/store-real-filename:" in url:
            return _Response(_EMPTY_SEARCH)
        response = self.routes[url]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
@pytest.mark.parametrize("cached_miss", [False, True])
@pytest.mark.parametrize("count", [1, "1"])
async def test_archived_filename_fallback_restores_release_and_reuses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cached_miss: bool, count: int | str,
) -> None:
    nfo_url = f"https://www.srrdb.com/download/file/{_RELEASE}/{_BASENAME}.nfo"
    client = _RoutedClient({
        f"https://api.srrdb.com/v1/search/r:{_BASENAME}": _Response(_EMPTY_SEARCH),
        _SEARCH_URL: _Response({"resultsCount": count, "results": [_RESULT]}),
        _DETAILS_URL: _Response({
            "archived-files": [{"name": f"{_BASENAME}.mkv"}],
            "files": [{"name": f"{_BASENAME}.nfo"}],
        }),
        nfo_url: _Response(content=b"generic scene nfo"),
    })
    events: list[tuple[str, str, str]] = []

    async def record_event(family: str, **kwargs: Any) -> None:
        assert kwargs["service"] == "srrdb"
        events.append((family, kwargs["operation"], kwargs["outcome"]))

    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    monkeypatch.setattr("src.is_scene.record_event_async", record_event)
    search_cache = tmp_path / "tmp" / "scene-test" / "srrdb" / "search" / f"{_BASENAME}.json"
    if cached_miss:
        search_cache.parent.mkdir(parents=True)
        search_cache.write_text(json.dumps(_EMPTY_SEARCH), encoding="utf-8")

    manager = SceneManager({"DEFAULT": {}})
    for _ in range(2):
        meta = Meta(base_dir=str(tmp_path), uuid="scene-test", category="MOVIE")
        result = await manager.is_scene(f"/downloads/{_BASENAME}.mkv", meta)
        assert result == (f"{_RELEASE}.mkv", True, 1234567)
        assert meta.scene_name == _RELEASE
        assert meta.we_need_tag is True
        assert meta.nfo is True
        assert meta.auto_nfo is True
        assert meta.scene_nfo_file.read_bytes() == b"generic scene nfo"

    expected = [_SEARCH_URL, _DETAILS_URL, nfo_url]
    if not cached_miss:
        expected.insert(0, f"https://api.srrdb.com/v1/search/r:{_BASENAME}")
    expected_events = [("api", "search", "success"), ("api", "details", "success"), ("api", "nfo_download", "success")]
    if not cached_miss:
        expected_events.insert(0, ("api", "search", "success"))
    assert events == expected_events
    assert client.requested_urls == expected
    assert json.loads(search_cache.read_text(encoding="utf-8")) == _EMPTY_SEARCH


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["no_candidates", "wrong_filename", "stored_file_only", "ambiguous", "details_error", "truncated", "overly_broad", "warnings"])
async def test_archived_filename_fallback_does_not_guess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str,
) -> None:
    candidate_search = {"resultsCount": 1, "results": [_RESULT]}
    details = {"archived-files": [{"name": f"{_BASENAME}.mkv"}]}
    routes = {
        f"https://api.srrdb.com/v1/search/r:{_BASENAME}": _Response(_EMPTY_SEARCH),
        _SEARCH_URL: _Response(candidate_search),
        _DETAILS_URL: _Response(details),
    }
    if case == "no_candidates":
        routes[_SEARCH_URL] = _Response(_EMPTY_SEARCH)
    elif case == "wrong_filename":
        details["archived-files"] = [{"name": f"{_BASENAME}.sample.mkv"}]
    elif case == "stored_file_only":
        details["files"] = details.pop("archived-files")
    elif case == "ambiguous":
        second = {**_RESULT, "release": f"{_RELEASE}.REPACK"}
        candidate_search.update(resultsCount=2, results=[_RESULT, second])
        routes[f"{_DETAILS_URL}.REPACK"] = _Response(details)
    elif case == "details_error":
        routes[_DETAILS_URL] = httpx.RequestError("unavailable")
    elif case == "truncated":
        candidate_search["resultsCount"] = 2
    elif case == "overly_broad":
        candidate_search.update(resultsCount=11, results=[_RESULT] * 11)
    elif case == "warnings":
        candidate_search["warnings"] = ["Search could not be completed"]

    client = _RoutedClient(routes)
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-test", category="MOVIE")
    video = f"/downloads/{_BASENAME}.mkv"
    assert await SceneManager({"DEFAULT": {}}).is_scene(video, meta, 7654321) == (video, False, 7654321)
    assert not meta.scene_name
    assert not meta.nfo
    assert not any("/download/" in url for url in client.requested_urls)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {},
    {"results": [_RESULT]},
    *[{"resultsCount": count, "results": [_RESULT]} for count in (None, "invalid", "1.5", [], {}, True, 1.0, -1)],
    {"resultsCount": 0},
    *[{"resultsCount": 0, "results": results} for results in (None, {}, "")],
    *[{"resultsCount": 1, "results": [candidate]} for candidate in (
        None, "release", [], {}, {"release": None}, {"release": 123}, {"release": ""}, {"release": "   "},
    )],
    {"resultsCount": 2, "results": [_RESULT, {"release": None}]},
])
async def test_archived_filename_fallback_rejects_malformed_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any],
) -> None:
    exact_url = f"https://api.srrdb.com/v1/search/r:{_BASENAME}"
    client = _RoutedClient({exact_url: _Response(_EMPTY_SEARCH), _SEARCH_URL: _Response(payload)})
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-test")
    video = f"{_BASENAME}.mkv"
    assert await SceneManager({"DEFAULT": {}}).is_scene(video, meta, 7654321) == (video, False, 7654321)
    assert client.requested_urls == [exact_url, _SEARCH_URL]
    assert not meta.scene_name


@pytest.mark.asyncio
async def test_archived_filename_fallback_checks_all_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    other = {**_RESULT, "release": "Generic-Title.2024.1080p.BluRay.x264-OTHERGROUP"}
    client = _RoutedClient({
        f"https://api.srrdb.com/v1/search/r:{_BASENAME}": _Response(_EMPTY_SEARCH),
        _SEARCH_URL: _Response({"resultsCount": 2, "results": [other, {**_RESULT, "hasNFO": "no"}]}),
        f"https://api.srrdb.com/v1/details/{other['release']}": _Response({"archived-files": [{"name": "other.mkv"}]}),
        _DETAILS_URL: _Response({"archived-files": [{"name": f"Folder\\{_BASENAME.upper()}.MKV"}]}),
    })
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-test", category="MOVIE")
    assert await SceneManager({"DEFAULT": {}}).is_scene(f"{_BASENAME}.mkv", meta) == (f"{_RELEASE}.mkv", True, 1234567)
    assert meta.scene_name == _RELEASE


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", [
    "examplegroup-generic.series.s03e01.episode-title.avi",
    "Generic Title [2024]-EXAMPLEGROUP.iso",
])
async def test_filename_match_does_not_need_sample_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str,
) -> None:
    release = "Generic.Series.S03E01.DVDRip.XviD-EXAMPLEGROUP"
    quoted_base = urllib.parse.quote(Path(filename).stem, safe="")
    quoted_filename = urllib.parse.quote(filename, safe="")
    exact_url = f"https://api.srrdb.com/v1/search/r:{quoted_base}"
    filename_url = f"https://api.srrdb.com/v1/search/store-real-filename:{quoted_filename}"
    details_url = f"https://api.srrdb.com/v1/details/{release}"
    client = _RoutedClient({
        exact_url: _Response(_EMPTY_SEARCH),
        filename_url: _Response({"resultsCount": 1, "results": [{"release": release, "hasNFO": "no", "imdbId": None}]}),
        details_url: _Response({"archived-files": [{"name": filename}]}),
    })
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-test")
    assert await SceneManager({"DEFAULT": {}}).is_scene(filename, meta) == (f"{release}.mkv", True, None)
    assert client.requested_urls == [exact_url, filename_url, details_url]


@pytest.mark.asyncio
async def test_filename_search_miss_stops_after_sample_guesses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exact_url = f"https://api.srrdb.com/v1/search/r:{_BASENAME}"
    client = _RoutedClient({exact_url: _Response(_EMPTY_SEARCH), _SEARCH_URL: _Response(_EMPTY_SEARCH)})
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-test")
    video = f"{_BASENAME}.mkv"
    assert await SceneManager({"DEFAULT": {}}).is_scene(video, meta) == (video, False, None)
    assert client.requested_urls == [exact_url, _SEARCH_URL] + [
        f"https://api.srrdb.com/v1/search/store-real-filename:{name}" for name in [
            f"{_BASENAME}.sample.mkv", f"{_BASENAME}-sample.mkv", f"sample-{_BASENAME}.mkv", f"sample.{_BASENAME}.mkv",
            "generic-title.2024.1080p.bluray.sample-examplegroup.mkv", "generic-title.2024.1080p.bluray-sample-examplegroup.mkv",
        ]
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(("filename", "sample"), [
    ("examplegroup-generic.series.s03e01.episode-title.avi", "examplegroup-generic.series.s03e01.episode-title.sample.avi"),
    ("examplegroup-generic.series.s03e01.episode-title.avi", "examplegroup-generic.series.s03e01.episode-title-sample.avi"),
    ("examplegroup-generic.series.s03e01.episode-title.avi", "sample-examplegroup-generic.series.s03e01.episode-title.avi"),
    ("examplegroup-generic.series.s03e01.episode-title.avi", "sample.examplegroup-generic.series.s03e01.episode-title.avi"),
    (f"{_BASENAME}.mkv", "generic-title.2024.1080p.bluray.sample-examplegroup.mkv"),
    (f"{_BASENAME}.mkv", "generic-title.2024.1080p.bluray-sample-examplegroup.mkv"),
    ("Generic Title [2024]-EXAMPLEGROUP.iso", "generic title [2024]-examplegroup.sample.m2ts"),
])
async def test_sample_search_verifies_archived_filename_and_reuses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str, sample: str,
) -> None:
    exact_url = f"https://api.srrdb.com/v1/search/r:{urllib.parse.quote(Path(filename).stem, safe='')}"
    sample_url = f"https://api.srrdb.com/v1/search/store-real-filename:{urllib.parse.quote(sample, safe='')}"
    client = _RoutedClient({
        exact_url: _Response(_EMPTY_SEARCH),
        sample_url: _Response({"resultsCount": 1, "results": [_RESULT]}),
        _DETAILS_URL: _Response({"archived-files": [{"name": filename}]}),
    })
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    manager = SceneManager({"DEFAULT": {}})
    for _ in range(2):
        meta = Meta(base_dir=str(tmp_path), uuid="scene-test", nfo=True)
        assert await manager.is_scene(filename, meta) == (f"{_RELEASE}.mkv", True, 1234567)
    assert client.requested_urls[0] == exact_url
    assert client.requested_urls[-2:] == [sample_url, _DETAILS_URL]
    assert len(client.requested_urls) == len(set(client.requested_urls))


@pytest.mark.asyncio
@pytest.mark.parametrize("manual", [7654321, "7654321", "tt7654321"])
async def test_scene_match_preserves_manual_imdb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manual: str | int) -> None:
    client = _FakeAsyncClient()
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-test", imdb_manual=manual, imdb_id=7654321, nfo=True)
    result = await SceneManager({"DEFAULT": {}}).is_scene("Generic.Title.2024-EXAMPLEGROUP.mkv", meta, 7654321)
    assert result[1:] == (True, 7654321)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["mkdir", "write_text"])
async def test_cache_failure_preserves_successful_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    client = _FakeAsyncClient()
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    warnings = []
    monkeypatch.setattr("src.is_scene.logger.warning", warnings.append)

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("cache is not writable")

    monkeypatch.setattr(Path, operation, fail)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-test", nfo=True)
    result = await SceneManager({"DEFAULT": {}}).is_scene("Generic.Title.2024-EXAMPLEGROUP.mkv", meta)
    assert result[1:] == (True, 1234567)
    assert any("Could not save cache" in warning for warning in warnings)
    assert not any("Request failed" in warning for warning in warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["matching", "renamed", "case_only", "size_mismatch", "renamed_and_size", "unknown_size", "multiple_files"])
@pytest.mark.parametrize("lower", [False, True])
@pytest.mark.parametrize("debug", [False, True])
async def test_scene_match_requires_confirmation_for_file_differences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, lower: bool, debug: bool,
) -> None:
    filename = f"{_RELEASE}.mkv" if case in {"renamed", "renamed_and_size", "multiple_files"} else f"{_BASENAME}.mkv"
    if case == "case_only":
        filename = filename.upper()
    video = tmp_path / filename
    video.write_bytes(b"data")
    archived = [{"name": f"{_BASENAME}.mkv", "size": "8" if case in {"size_mismatch", "renamed_and_size"} else 4}]
    if case == "unknown_size":
        archived[0].pop("size")
    if case == "multiple_files":
        archived.append({"name": "another-file.mkv", "size": 20})
    search_url = (
        "https://api.srrdb.com/v1/search/start:Generic.Title/group:EXAMPLEGROUP" if lower
        else f"https://api.srrdb.com/v1/search/r:{Path(filename).stem}"
    )
    client = _RoutedClient({
        search_url: _Response({"resultsCount": 1, "results": [_RESULT]}),
        _DETAILS_URL: _Response({"archived-files": archived}),
    })
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    warnings = []
    monkeypatch.setattr("src.is_scene.logger.warning", warnings.append)
    prompts = []

    def approve(question: str, *, default: bool) -> bool:
        prompts.append(question)
        assert default is False
        assert warnings
        return True

    monkeypatch.setattr("src.is_scene.cli_ui.ask_yes_no", approve)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-test", nfo=True, filename="Generic Title", tag="-EXAMPLEGROUP", imdb_id=1234567, debug=debug)
    result = await SceneManager({"DEFAULT": {}}).is_scene(str(video), meta, 1234567, lower=lower)
    assert result[1] is True
    assert video.read_bytes() == b"data"
    assert any("confirm whether the file was renamed" in warning for warning in warnings) == (case in {"renamed", "case_only", "renamed_and_size", "multiple_files"})
    assert any("File size mismatch" in warning for warning in warnings) == (case in {"size_mismatch", "renamed_and_size"})
    if case in {"size_mismatch", "renamed_and_size"}:
        assert any("local 4 bytes, archived 8 bytes" in warning for warning in warnings)
    if case == "multiple_files":
        assert any("File size could not be verified" in warning for warning in warnings)
    if case in {"matching", "unknown_size"}:
        assert not warnings
        assert not prompts
    else:
        assert len(prompts) == 1
        assert filename in prompts[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("lower", [False, True])
@pytest.mark.parametrize("mode", ["declined", "eof", "unattended", "unattended_confirm_yes", "unattended_confirm_no"])
async def test_unapproved_file_differences_stop_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lower: bool, mode: str,
) -> None:
    video = tmp_path / f"{_RELEASE}.mkv"
    video.write_bytes(b"data")
    search_url = (
        "https://api.srrdb.com/v1/search/start:Generic.Title/group:EXAMPLEGROUP" if lower
        else f"https://api.srrdb.com/v1/search/r:{_RELEASE}"
    )
    client = _RoutedClient({
        search_url: _Response({"resultsCount": 1, "results": [{**_RESULT, "hasNFO": "no"}]}),
        _DETAILS_URL: _Response({"archived-files": [{"name": f"{_BASENAME}.mkv", "size": 8}]}),
    })
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    prompts = []

    def respond(question: str, *, default: bool) -> bool:
        assert default is False
        prompts.append(question)
        if mode == "eof":
            raise EOFError
        return mode == "unattended_confirm_yes"

    monkeypatch.setattr("src.is_scene.cli_ui.ask_yes_no", respond)
    meta = Meta(
        base_dir=str(tmp_path), uuid="scene-test", filename="Generic Title", tag="-EXAMPLEGROUP", imdb_id=1234567,
        debug=True, unattended=mode.startswith("unattended"), unattended_confirm=mode.startswith("unattended_confirm"),
    )
    manager = SceneManager({"DEFAULT": {"check_predb": True}})

    async def unexpected_predb(*_args: Any) -> bool:
        pytest.fail("An unapproved mismatch must not fall through to another lookup")

    monkeypatch.setattr(manager, "predb_check", unexpected_predb)
    # Cached lookups must still require confirmation on retry.
    for _ in range(2):
        if mode == "unattended_confirm_yes":
            assert (await manager.is_scene(str(video), meta, 1234567, lower=lower))[1] is True
        else:
            with pytest.raises(SceneFileMismatchError, match="Upload cancelled"):
                await manager.is_scene(str(video), meta, 1234567, lower=lower)
            assert meta.scene is False
            assert not meta.scene_name
            assert not meta.nfo
    assert len(prompts) == (0 if mode == "unattended" else 2)
    assert not any("/download/" in url for url in client.requested_urls)


@pytest.mark.asyncio
async def test_directory_is_not_compared_to_an_archived_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video = tmp_path / _RELEASE
    video.mkdir()
    warnings = []
    monkeypatch.setattr("src.is_scene.logger.warning", warnings.append)
    await SceneManager({"DEFAULT": {}})._warn_file_differences(
        str(video), _RELEASE, {"archived-files": [{"name": f"{_BASENAME}.mkv", "size": 1}]},
    )
    assert not warnings


@pytest.mark.asyncio
@pytest.mark.parametrize(("result", "expected_outcome"), [("no_match", "success"), ("http_error", "error"), ("request_error", "error")])
async def test_srrdb_search_records_no_match_and_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: str, expected_outcome: str) -> None:
    class SearchClient(_FakeAsyncClient):
        async def get(self, url: str, **_kwargs: Any) -> _Response:
            self.requested_urls.append(url)
            if result == "request_error":
                raise OSError("network unavailable")
            response = _Response({"resultsCount": 0, "results": []})
            if result == "http_error":
                response.status_code = 503
            return response

    events: list[tuple[str, str, str]] = []

    async def record_event(_family: str, **kwargs: Any) -> None:
        events.append((kwargs["service"], kwargs["operation"], kwargs["outcome"]))

    client = SearchClient()
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    monkeypatch.setattr("src.is_scene.record_event_async", record_event)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-failure", category="MOVIE")

    _, scene, _ = await SceneManager({"DEFAULT": {}}).is_scene("/downloads/Fictional.Release.mkv", meta)

    assert scene is False
    expected_requests = 6 if result == "no_match" else 1
    assert len(client.requested_urls) == expected_requests
    assert events == [("srrdb", "search", expected_outcome)] * expected_requests


@pytest.mark.asyncio
async def test_lowercase_srrdb_search_records_search_and_details(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeAsyncClient()
    operations: list[str] = []

    async def record_event(_family: str, **kwargs: Any) -> None:
        operations.append(kwargs["operation"])

    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    monkeypatch.setattr("src.is_scene.record_event_async", record_event)
    meta = Meta(base_dir=str(tmp_path), uuid="lowercase-scene", filename="Fictional.Release", tag="-GROUP", imdb_id=1234567, nfo=True)

    _, scene, _ = await SceneManager({"DEFAULT": {}}).is_scene("/downloads/fictional.release.mkv", meta, lower=True)

    assert scene is True
    assert len(client.requested_urls) == 2
    assert operations == ["search", "details"]
