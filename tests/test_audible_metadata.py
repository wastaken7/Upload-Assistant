# ruff: noqa: S101
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from src import audible, book_prep
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.metadata_cache import cache_for

ASIN = "B0TEST1234"


def test_audible_cache_defaults_to_24_hours(tmp_path):
    cache = cache_for(tmp_path, {"DEFAULT": {"metadata_cache_default_ttl_hours": 168}})
    assert cache.ttl("audible", "product") == 24 * 3600


def _catalog_product():
    return {
        "asin": ASIN,
        "title": "The Invented Debt",
        "authors": [{"name": "Mira Example"}, {"name": "Nora Sample", "asin": "B0AUTH1234"}],
        "narrators": [{"name": "Tara Sample"}],
        "publisher_name": "Fictional Audio",
        "publisher_summary": "An invented synopsis.",
        "isbn": "9780000000002",
        "release_date": "2025-07-22",
        "language": "portuguese",
        "format_type": "unabridged",
        "runtime_length_min": 83,
        "product_images": {"500": "https://example.org/cover.jpg"},
        "rating": {"overall_distribution": {"average_rating": 4.65, "num_ratings": 21}},
    }


def test_catalog_parses_numeric_series_sequence_and_single_contributors():
    product = _catalog_product()
    product["series"] = [{"title": "Imaginary Cycle", "sequence": 2.0}]
    product["authors"] = {"name": "Mira Example", "asin": "B0AUTH1234"}
    product["narrators"] = {"name": "Tara Sample"}
    result = audible._parse_product(product, ASIN)
    assert result["book_series_index"] == "2.0"
    assert result["author"] == "Mira Example"
    assert result["audible_authors"] == [{"name": "Mira Example", "asin": "B0AUTH1234"}]
    assert result["narrator"] == "Tara Sample"


def test_catalog_chooses_largest_available_cover():
    product = _catalog_product()
    product["product_images"] = {
        "500": "https://example.org/fictional-500.jpg",
        "1215": "https://example.org/fictional-1215.jpg",
        "900": "https://example.org/fictional-900.jpg",
    }
    assert audible._parse_product(product, ASIN)["artwork_url"] == "https://example.org/fictional-1215.jpg"
    del product["product_images"]["1215"]
    assert audible._parse_product(product, ASIN)["artwork_url"] == "https://example.org/fictional-900.jpg"


@pytest.mark.asyncio
async def test_catalog_uses_marketplace_and_cache_without_credentials(tmp_path, monkeypatch):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"product": _catalog_product()})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(audible.httpx, "AsyncClient", lambda **_kwargs: real_client(transport=httpx.MockTransport(respond)))
    first = await audible.fetch_audible_metadata(ASIN, "audible.com.br", str(tmp_path))
    second = await audible.fetch_audible_metadata(ASIN, "audible.com.br", str(tmp_path))
    await audible.fetch_audible_metadata(ASIN, "audible.com", str(tmp_path))

    assert first == second
    assert first["rating_count"] == 21
    assert first["rating_average"] == 4.7
    assert first["overview"] == "An invented synopsis."
    assert first["audible_authors"] == [{"name": "Mira Example", "asin": ""}, {"name": "Nora Sample", "asin": "B0AUTH1234"}]
    assert len(calls) == 2
    assert calls[0].url.host == "api.audible.com.br"
    assert calls[1].url.host == "api.audible.com"
    assert calls[0].url.params["image_sizes"] == "1215,900,500"
    assert all("cookie" not in request.headers and "authorization" not in request.headers for request in calls)


@pytest.mark.asyncio
async def test_legacy_cover_cache_key_is_ignored_after_image_size_upgrade(tmp_path, monkeypatch):
    legacy_url = "https://example.org/fictional-500.jpg"
    high_resolution_url = "https://example.org/fictional-1215.jpg"
    await cache_for(str(tmp_path)).set("audible", "product", f"audible.com.br:{ASIN}", {"artwork_url": legacy_url})
    product = _catalog_product()
    product["product_images"] = {"500": legacy_url, "1215": high_resolution_url}
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"product": product})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(audible.httpx, "AsyncClient", lambda **_kwargs: real_client(transport=httpx.MockTransport(respond)))
    first = await audible.fetch_audible_metadata(ASIN, "audible.com.br", str(tmp_path))
    second = await audible.fetch_audible_metadata(ASIN, "audible.com.br", str(tmp_path))

    assert first == second
    assert first["artwork_url"] == high_resolution_url
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_partial_marketplace_response_is_not_accepted(tmp_path, monkeypatch):
    urls = []

    def respond(request):
        urls.append(str(request.url))
        if request.url.host.startswith("api."):
            return httpx.Response(200, json={"product": {"asin": ASIN, "rating": {"overall_distribution": {"num_ratings": 0}}}})
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(audible.httpx, "AsyncClient", lambda **_kwargs: real_client(transport=httpx.MockTransport(respond)))
    assert await audible.fetch_audible_metadata(ASIN, "audible.com", str(tmp_path)) is None
    assert len(urls) == 2


@pytest.mark.asyncio
async def test_page_structured_data_is_fallback_when_api_fails(tmp_path, monkeypatch):
    book = {
        "@type": "Audiobook",
        "name": "A Fictional Promise",
        "author": [{"name": "Mira Example"}],
        "duration": "PT1H23M",
        "aggregateRating": {"ratingValue": "4.5", "ratingCount": "8"},
    }
    product = {"@type": "Product", "productID": ASIN}
    markup = f'<script type="application/ld+json">{json.dumps([book, product])}</script>'

    def respond(request):
        if request.url.host.startswith("api."):
            return httpx.Response(503)
        return httpx.Response(200, text=markup)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(audible.httpx, "AsyncClient", lambda **_kwargs: real_client(transport=httpx.MockTransport(respond)))
    result = await audible.fetch_audible_metadata(ASIN, "audible.com.br", str(tmp_path))
    assert result["title"] == "A Fictional Promise"
    assert result["runtime_minutes"] == 83
    assert result["rating_count"] == 8
    assert audible._parse_page(markup.replace(ASIN, "B0OTHER123"), ASIN) is None


def test_page_structured_data_accepts_single_author_and_narrator():
    book = {"@type": "Audiobook", "name": "A Fictional Promise", "author": {"name": "Mira Example"}, "readBy": {"name": "Tara Sample"}}
    product = {"@type": "Product", "productID": ASIN}
    markup = f'<script type="application/ld+json">{json.dumps([book, product])}</script>'
    result = audible._parse_page(markup, ASIN)
    assert result["author"] == "Mira Example"
    assert result["narrator"] == "Tara Sample"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "audiobook,asin,domain,expected",
    [(True, ASIN, "audible.com.br", True), (True, "", "audible.com.br", False), (True, ASIN, "", False), (False, ASIN, "audible.com.br", False)],
)
async def test_lookup_requires_audiobook_asin_and_marketplace(tmp_path, monkeypatch, audiobook, asin, domain, expected):
    fetch = AsyncMock(return_value={"title": "A Fictional Promise"})
    monkeypatch.setattr(book_prep, "fetch_audible_metadata", fetch)
    meta = Meta(audiobook=audiobook, asin=asin, edit=True, filelist=[])
    await book_prep.gather_book_prep(meta, "fictional.m4b", str(tmp_path), {"DEFAULT": {"audible_domain": domain}})
    assert fetch.await_count == int(expected)


@pytest.mark.asyncio
async def test_embedded_asin_and_explicit_url_override_domain_and_other_sources(tmp_path, monkeypatch):
    from src.myanonamouse import myanonamouse_manager

    fetch = AsyncMock(return_value={**audible._parse_product(_catalog_product(), ASIN), "book_series": "Imaginary Cycle", "book_series_index": "2.0"})
    monkeypatch.setattr(book_prep, "fetch_audible_metadata", fetch)
    monkeypatch.setattr(myanonamouse_manager, "search_by_id", AsyncMock(return_value={"title": "MAM Title", "narrator": "MAM Narrator", "asin": "B0OTHER123"}))
    meta = Meta(
        audiobook=True,
        audible_url=f"https://www.audible.com/pd/{ASIN}",
        book_title="Manual Title",
        title="Manual Title",
        torrent_comments=[{"trackers": "myanonamouse.net", "comment": "MID=123"}],
        edit=True,
        filelist=[],
        mediainfo={"media": {"track": [{"@type": "General", "ASIN": ASIN, "Title": "Local Title"}]}},
    )
    await book_prep.gather_book_prep(meta, "fictional.m4b", str(tmp_path), {"DEFAULT": {"audible_domain": "audible.com.br", "mam_api_key": "test"}})
    fetch.assert_awaited_once_with(ASIN, "audible.com", str(tmp_path))
    assert meta.title == "Manual Title"
    assert meta.narrator == "Tara Sample"
    assert meta.asin == ASIN
    assert meta.book_series == "Imaginary Cycle"
    assert meta.book_series_index == "2"
    assert meta.audiobook_duration == 83 * 60
    assert meta.audible_rating_count == 21
    assert meta.audible_authors[1]["asin"] == "B0AUTH1234"


@pytest.mark.asyncio
async def test_embedded_asin_uses_configured_marketplace_and_keeps_file_duration(tmp_path, monkeypatch):
    fetch = AsyncMock(return_value=audible._parse_product(_catalog_product(), ASIN))
    monkeypatch.setattr(book_prep, "fetch_audible_metadata", fetch)
    monkeypatch.setattr(book_prep, "get_audiobook_duration", AsyncMock(return_value=(120.0, "02m 00s")))
    meta = Meta(
        audiobook=True,
        edit=True,
        filelist=[],
        mediainfo={"media": {"track": [{"@type": "General", "ASIN": ASIN, "Title": "Local Title"}]}},
    )
    await book_prep.gather_book_prep(meta, "fictional.m4b", str(tmp_path), {"DEFAULT": {"audible_domain": "audible.com.br"}})
    fetch.assert_awaited_once_with(ASIN, "audible.com.br", str(tmp_path))
    assert meta.title == "The Invented Debt"
    assert meta.audiobook_duration == 120.0
    assert meta.audiobook_duration_formatted == "02m 00s"


@pytest.mark.asyncio
async def test_asin_supplied_only_by_mam_does_not_trigger_audible(tmp_path, monkeypatch):
    from src.myanonamouse import myanonamouse_manager

    fetch = AsyncMock()
    monkeypatch.setattr(book_prep, "fetch_audible_metadata", fetch)
    monkeypatch.setattr(myanonamouse_manager, "search_by_id", AsyncMock(return_value={"asin": ASIN}))
    meta = Meta(audiobook=True, edit=True, filelist=[], torrent_comments=[{"trackers": "myanonamouse.net", "comment": "MID=123"}])
    await book_prep.gather_book_prep(meta, "fictional.m4b", str(tmp_path), {"DEFAULT": {"audible_domain": "audible.com.br", "mam_api_key": "test"}})
    fetch.assert_not_awaited()


@pytest.mark.parametrize("language,needle", [("en", "4.7/5 (21 ratings)"), ("pt-BR", "4,7/5 (21 avaliações)")])
def test_description_rating_is_plain_text_and_omitted_when_missing(language, needle):
    builder = DescriptionBuilder("TEST", {"DEFAULT": {"audible_domain": "audible.com.br"}, "TRACKERS": {"TEST": {}}}, language=language)
    meta = Meta(audiobook=True, asin=ASIN, audible_rating_average=4.7, audible_rating_count=21)
    description = builder._build_book_desc_section(meta)
    assert needle in description
    assert f"[url=https://www.audible.com.br/pd/{ASIN}]{ASIN}[/url]" in description
    assert description.count(f"[url=https://www.audible.com.br/pd/{ASIN}]") == 1
    assert needle not in builder._build_book_desc_section(Meta(audiobook=True, asin=ASIN))


@pytest.mark.parametrize("author", ["Mira Example", "Mira Example, Nora Sample"])
def test_description_links_only_authors_with_asins_on_selected_marketplace(author):
    builder = DescriptionBuilder("TEST", {"DEFAULT": {"audible_domain": "audible.com.br"}, "TRACKERS": {"TEST": {}}})
    meta = Meta(
        audiobook=True,
        asin=ASIN,
        author=author,
        audible_url=f"https://www.audible.com/pd/{ASIN}",
        audible_authors=[{"name": "Mira Example", "asin": ""}, {"name": "Nora Sample", "asin": "B0AUTH1234"}],
    )
    description = builder._build_book_desc_section(meta)
    assert "Mira Example, [url=https://www.audible.com/author/B0AUTH1234]Nora Sample[/url]" in description
    meta.author = "Manual Writer"
    assert "Nora Sample" not in builder._build_book_desc_section(meta)
