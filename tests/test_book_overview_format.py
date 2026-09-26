# ruff: noqa: S101

import pytest

from src.get_desc import DescriptionBuilder
from src.meta import Meta


@pytest.mark.parametrize("table", [True, False])
def test_book_overview_converts_raw_and_encoded_html(table):
    builder = DescriptionBuilder("TEST", {"DEFAULT": {}, "TRACKERS": {"TEST": {}}})
    meta = Meta(
        category="BOOK",
        overview="&lt;p&gt;An &lt;strong&gt;invented&lt;/strong&gt; tale.&lt;/p&gt;<p>Next <em>chapter</em><br>starts.</p>",
    )
    description = builder._build_book_desc_section(meta, table=table)
    assert "An [b]invented[/b] tale.\n\nNext [i]chapter[/i]\nstarts." in description
    assert "&lt;" not in description
    assert "<strong>" not in description


def test_book_overview_preserves_lists_and_safe_links_without_script():
    builder = DescriptionBuilder("TEST", {"DEFAULT": {}, "TRACKERS": {"TEST": {}}})
    meta = Meta(
        category="BOOK",
        overview='<ul><li>First</li><li>Second</li></ul><a href="https://example.org/fictional">Source</a> <a href="javascript:alert(1)">Other</a><script>bad()</script>',
    )
    description = builder._build_book_desc_section(meta)
    assert "* First\n* Second" in description
    assert "[url=https://example.org/fictional]Source[/url]" in description
    assert "Other" in description
    assert "javascript:" not in description
    assert "bad()" not in description


def test_book_overview_preserves_existing_bbcode_plain_text():
    builder = DescriptionBuilder("TEST", {"DEFAULT": {}, "TRACKERS": {"TEST": {}}})
    description = builder._build_book_desc_section(Meta(category="BOOK", overview="[b]Existing[/b] synopsis"))
    assert "[b]Existing[/b] synopsis" in description
