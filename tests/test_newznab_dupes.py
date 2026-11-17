from src.trackers.USENET.search_helpers import parse_newznab_dupes

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Fictional.Movie.2020.1080p-FICTIONAL</title><guid>0123456789abcdef0123456789abcdef</guid></item>
<item><title>Fictional.Show.S01-FICTIONAL</title><guid>fedcba9876543210fedcba9876543210</guid>
<link>https://fictional.example/getnzb/fedcba9876543210fedcba9876543210.nzb</link></item>
</channel></rss>"""


def test_release_pages_built_from_the_guid_carry_it_as_the_id() -> None:
    built, linked = parse_newznab_dupes(FEED, "https://fictional.example/releases/")

    assert built["link"] == "https://fictional.example/releases/0123456789abcdef0123456789abcdef"
    assert built["id"] == "0123456789abcdef0123456789abcdef"
    # A link from the feed may be a download link with a key in it, so its hashes stay hidden.
    assert linked["link"] == "https://fictional.example/getnzb/fedcba9876543210fedcba9876543210.nzb"
    assert linked["id"] is None
