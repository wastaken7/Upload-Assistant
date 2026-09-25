# ruff: noqa: S101
from types import SimpleNamespace

import pytest

from src import prep_helpers
from src.args import Args
from src.audible import build_audible_url, normalize_audible_domain, normalize_audible_url
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.region import get_service


def test_audible_url_argument_sets_asin_and_canonical_url(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse(
        [str(tmp_path), "--audible-url", "https://www.audible.co.uk/pd/Book-Title/B0TEST1234?source=tracker"],
        Meta(),
    )

    assert meta.asin == "B0TEST1234"
    assert meta.book_asin == "B0TEST1234"
    assert meta.audible_url == "https://www.audible.co.uk/pd/B0TEST1234"


def test_audible_url_argument_rejects_conflicting_asin(tmp_path):
    with pytest.raises(SystemExit):
        Args({"DEFAULT": {"screens": 1}}).parse(
            [str(tmp_path), "--asin", "B000000001", "--audible-url", "https://www.audible.com.br/pd/B000000002"],
            Meta(),
        )


def test_audible_helpers_support_regional_marketplaces():
    assert build_audible_url("B0TEST1234", "audible.com.br") == "https://www.audible.com.br/pd/B0TEST1234"
    assert normalize_audible_url("https://audible.co.uk/pd/Title/B0TEST1234") == "https://www.audible.co.uk/pd/B0TEST1234"


def test_audible_url_rejects_non_audible_host():
    with pytest.raises(ValueError):
        normalize_audible_url("https://example.com/pd/B0TEST1234")


def test_audible_domain_rejects_non_https_url():
    with pytest.raises(ValueError):
        normalize_audible_domain("http://audible.com")


def test_book_description_links_asin_using_configured_marketplace():
    builder = DescriptionBuilder("TEST", {"DEFAULT": {"audible_domain": "audible.com.br"}, "TRACKERS": {"TEST": {}}})
    meta = Meta(asin="B0TEST1234", audiobook=True)

    description = builder._build_book_desc_section(meta)

    assert "[url=https://www.audible.com.br/pd/B0TEST1234]B0TEST1234[/url]" in description


def test_explicit_audible_url_overrides_configured_marketplace():
    builder = DescriptionBuilder("TEST", {"DEFAULT": {"audible_domain": "audible.com.br"}, "TRACKERS": {"TEST": {}}})
    meta = Meta(asin="B0TEST1234", audible_url="https://www.audible.co.uk/pd/B0TEST1234", audiobook=True)

    description = builder._build_book_desc_section(meta)

    assert "[url=https://www.audible.co.uk/pd/B0TEST1234]B0TEST1234[/url]" in description


def test_asin_remains_plain_text_without_user_provided_marketplace():
    builder = DescriptionBuilder("TEST", {"DEFAULT": {"audible_domain": ""}, "TRACKERS": {"TEST": {}}})

    description = builder._build_book_desc_section(Meta(asin="B0TEST1234"))

    assert "[url=" not in description
    assert "B0TEST1234" in description


@pytest.mark.parametrize(("language", "label"), [("en", "Service"), ("pt-BR", "Serviço")])
def test_book_technical_details_include_service(language, label):
    builder = DescriptionBuilder("TEST", {"DEFAULT": {}, "TRACKERS": {"TEST": {}}}, language=language)
    meta = Meta(category="BOOK", author="Example Author", service_longname="Kobo Plus")

    description = builder._build_book_desc_section(meta)

    assert f"[tr][td][b]{label}[/b][/td][td]Kobo Plus[/td][/tr]" in description


def test_book_technical_details_omit_unknown_service():
    builder = DescriptionBuilder("TEST", {"DEFAULT": {}, "TRACKERS": {"TEST": {}}})

    description = builder._build_book_desc_section(Meta(category="BOOK", author="Example Author"))

    assert "[b]Service[/b]" not in description


@pytest.mark.parametrize(
    ("service", "longname"),
    [
        ("Audible", "Audible"),
        ("bookbeat", "BookBeat"),
        ("Kindle Unlimited", "Kindle Unlimited"),
        ("KOBO PLUS", "Kobo Plus"),
        ("Tocalivros", "Tocalivros"),
        ("Custom Books", "Custom Books"),
    ],
)
@pytest.mark.asyncio
async def test_book_service_argument_sets_longname(tmp_path, monkeypatch, service, longname):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--service", service], Meta(category="BOOK", tag=""))

    async def keep_meta(current_meta):
        return current_meta

    monkeypatch.setattr(prep_helpers, "tag_override", keep_meta)
    await prep_helpers.finalize_metadata(SimpleNamespace(config={"DEFAULT": {}}), meta, "book.m4b", {}, None, "book.m4b", "", "book.m4b")

    assert meta.service == service
    assert meta.service_longname == longname


@pytest.mark.asyncio
async def test_audible_is_not_a_video_streaming_service():
    assert "Audible" not in await get_service(get_services_only=True)
