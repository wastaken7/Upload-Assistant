# ruff: noqa: S101

import pytest

from src.args import Args
from src.audible import build_audible_url, normalize_audible_domain, normalize_audible_url
from src.get_desc import DescriptionBuilder
from src.meta import Meta


def test_audible_url_argument_sets_asin_and_canonical_url(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse(
        [str(tmp_path), "--audible-url", "https://www.audible.co.uk/pd/Book-Title/B01N5AX3TQ?source=tracker"],
        Meta(),
    )

    assert meta.asin == "B01N5AX3TQ"
    assert meta.book_asin == "B01N5AX3TQ"
    assert meta.audible_url == "https://www.audible.co.uk/pd/B01N5AX3TQ"


def test_audible_url_argument_rejects_conflicting_asin(tmp_path):
    with pytest.raises(SystemExit):
        Args({"DEFAULT": {"screens": 1}}).parse(
            [str(tmp_path), "--asin", "B000000001", "--audible-url", "https://www.audible.com.br/pd/B000000002"],
            Meta(),
        )


def test_audible_helpers_support_regional_marketplaces():
    assert build_audible_url("B01N5AX3TQ", "audible.com.br") == "https://www.audible.com.br/pd/B01N5AX3TQ"
    assert normalize_audible_url("https://audible.co.uk/pd/Title/B01N5AX3TQ") == "https://www.audible.co.uk/pd/B01N5AX3TQ"


def test_audible_url_rejects_non_audible_host():
    with pytest.raises(ValueError):
        normalize_audible_url("https://example.com/pd/B01N5AX3TQ")


def test_audible_domain_rejects_non_https_url():
    with pytest.raises(ValueError):
        normalize_audible_domain("http://audible.com")


def test_book_description_links_asin_using_configured_marketplace():
    builder = DescriptionBuilder("TEST", {"DEFAULT": {"audible_domain": "audible.com.br"}, "TRACKERS": {"TEST": {}}})
    meta = Meta(asin="B01N5AX3TQ", audiobook=True)

    description = builder._build_book_desc_section(meta)

    assert "[url=https://www.audible.com.br/pd/B01N5AX3TQ]B01N5AX3TQ[/url]" in description


def test_explicit_audible_url_overrides_configured_marketplace():
    builder = DescriptionBuilder("TEST", {"DEFAULT": {"audible_domain": "audible.com.br"}, "TRACKERS": {"TEST": {}}})
    meta = Meta(asin="B01N5AX3TQ", audible_url="https://www.audible.co.uk/pd/B01N5AX3TQ", audiobook=True)

    description = builder._build_book_desc_section(meta)

    assert "[url=https://www.audible.co.uk/pd/B01N5AX3TQ]B01N5AX3TQ[/url]" in description


def test_asin_remains_plain_text_without_user_provided_marketplace():
    builder = DescriptionBuilder("TEST", {"DEFAULT": {"audible_domain": ""}, "TRACKERS": {"TEST": {}}})

    description = builder._build_book_desc_section(Meta(asin="B01N5AX3TQ"))

    assert "[url=" not in description
    assert "B01N5AX3TQ" in description
