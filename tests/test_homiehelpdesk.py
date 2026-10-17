import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.homiehelpdesk import HomieHelpDesk


def _tracker() -> HomieHelpDesk:
    return HomieHelpDesk({"DEFAULT": {}, "TRACKERS": {"HOMIEHELPDESK": {}}})


def test_homiehelpdesk_music_upload_uses_musicbrainz_release_id():
    meta = Meta(category="MUSIC", music_release={"external_ids": {"musicbrainz_release": "c0d17e85-3a36-4dc8-9a88-c188a5e78b0d"}})

    assert asyncio.run(_tracker().get_additional_data(meta)) == {
        "music_exists_on_musicbrainz": "1",
        "musicbrainz": "c0d17e85-3a36-4dc8-9a88-c188a5e78b0d",
    }


def test_homiehelpdesk_music_upload_uses_discogs_url_when_musicbrainz_is_unavailable():
    meta = Meta(category="MUSIC", music_release={"external_ids": {"discogs_master_url": "https://www.discogs.com/master/28700-Example"}})

    assert asyncio.run(_tracker().get_additional_data(meta)) == {
        "music_exists_on_discogs": "1",
        "discogs": "https://www.discogs.com/master/28700-Example",
    }


def test_homiehelpdesk_requires_a_music_external_id():
    meta = Meta(category="MUSIC", music_release={"external_ids": {"musicbrainz_release": "invalid"}})

    assert asyncio.run(_tracker().get_additional_checks(meta)) is False


def test_homiehelpdesk_music_type_uses_analyzed_format():
    meta = Meta(category="MUSIC", music_release={"fields": {"format": {"value": "FLAC"}}})

    assert asyncio.run(_tracker().get_type_id(meta)) == {"type_id": "7"}


def test_homiehelpdesk_audiobook_upload_sends_audiobook_fields():
    meta = Meta(
        category="BOOK",
        audiobook=True,
        asin="b0testasin",
        audible_url="https://www.audible.co.uk/pd/B0TESTASIN",
        title="The Glass Orchard",
        author="Mira Vantell",
        audible_authors=[{"name": "Mira Vantell", "asin": ""}, {"name": "Oren Lasko", "asin": ""}],
        narrator="Tess Calloway",
    )

    assert asyncio.run(_tracker().get_additional_data(meta)) == {
        "audiobook_asin": "B0TESTASIN",
        "audiobook_region": "uk",
        "audiobook_title": "The Glass Orchard",
        "audiobook_authors": "Mira Vantell, Oren Lasko",
        "audiobook_narrators": "Tess Calloway",
    }


def test_homiehelpdesk_audiobook_without_asin_still_sends_title_and_author():
    meta = Meta(category="BOOK", audiobook=True, title="The Glass Orchard", author="Mira Vantell")

    assert asyncio.run(_tracker().get_additional_data(meta)) == {
        "audiobook_title": "The Glass Orchard",
        "audiobook_authors": "Mira Vantell",
    }


def test_homiehelpdesk_ebook_upload_sends_isbn():
    meta = Meta(category="BOOK", isbn="978-0-00-000000-2")

    assert asyncio.run(_tracker().get_additional_data(meta)) == {"isbn": "9780000000002"}
