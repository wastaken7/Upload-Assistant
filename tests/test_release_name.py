# ruff: noqa: S101

import pytest

from src.meta import Meta
from src.release_name import (
    NameRule,
    NameSelector,
    ReleaseNameBuilder,
    TrackerNameProfile,
    collapse_whitespace,
    literal,
    spaces_to_dots,
    template,
)


@pytest.mark.asyncio
async def test_release_name_selects_most_specific_template() -> None:
    profile = TrackerNameProfile(
        rules=(
            NameRule(NameSelector(), template("base_name")),
            NameRule(NameSelector(category="MOVIE"), template("title", "year")),
            NameRule(NameSelector(category="MOVIE", type="WEBDL"), template("year", "title")),
        )
    )

    name, _missing = await ReleaseNameBuilder().render(Meta(category="MOVIE", type="WEBDL", title="Movie", year=2026), profile)

    assert name == "2026 Movie"


@pytest.mark.asyncio
async def test_release_name_applies_override_precedence() -> None:
    profile = TrackerNameProfile(
        rules=(NameRule(NameSelector(), template("title", "source", literal("REMUX"))),),
        overrides={"source": "BluRay"},
    )

    async def dynamic(_context):
        return {"source": "UHD BluRay"}

    name, _missing = await ReleaseNameBuilder().render(Meta(title="Movie", source="WEB"), profile, dynamic)

    assert name == "Movie UHD BluRay REMUX"


@pytest.mark.asyncio
async def test_release_name_dynamic_field_override_can_select_template() -> None:
    profile = TrackerNameProfile(
        rules=(
            NameRule(NameSelector(type="WEBDL"), template("title", literal("WEB-DL"))),
            NameRule(NameSelector(type="REMUX"), template("title", literal("REMUX"))),
        )
    )

    async def dynamic(_context):
        return {"type": "REMUX"}

    name, _missing = await ReleaseNameBuilder().render(Meta(title="Movie", type="WEBDL"), profile, dynamic)

    assert name == "Movie REMUX"


@pytest.mark.asyncio
async def test_release_name_filters_empty_fields_and_orders_transforms() -> None:
    profile = TrackerNameProfile(
        rules=(NameRule(NameSelector(), template("title", "alt_title", "year", transforms=(collapse_whitespace, spaces_to_dots))),),
    )

    name, _missing = await ReleaseNameBuilder().render(Meta(title="A  Movie", year=2026), profile)

    assert name == "A.Movie.2026"


@pytest.mark.asyncio
async def test_release_name_returns_template_missing_fields() -> None:
    profile = TrackerNameProfile(
        rules=(NameRule(NameSelector(type="WEBDL"), template("title", "service", potential_missing=("edition", "service"))),),
    )

    _name, missing = await ReleaseNameBuilder().render(Meta(type="WEBDL", title="Movie"), profile)

    assert missing == ("edition", "service")


@pytest.mark.asyncio
async def test_release_name_selects_book_subtype() -> None:
    profile = TrackerNameProfile(
        rules=(
            NameRule(NameSelector(category="BOOK"), template("title")),
            NameRule(NameSelector(category="BOOK", subtype="AUDIOBOOK"), template("author", "title")),
        )
    )

    name, _missing = await ReleaseNameBuilder().render(Meta(category="BOOK", audiobook=True, author="Author", title="Book"), profile)

    assert name == "Author Book"
