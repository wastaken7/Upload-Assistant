import pytest

from src.meta import Meta
from src.rehostimages import _image_host
from src.trackers.digitalcore import DigitalCore


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (Meta(category="MOVIE", audio_languages=["Russian", "English"]), "russian"),
        (Meta(category="TV", audio_languages=["pl"]), "polish"),
        (Meta(category="MOVIE", audio_languages=["pt-BR"]), "portuguese"),
        (Meta(category="MOVIE", audio_languages=["und", "French"]), "french"),
        (Meta(category="MOVIE", original_language="en", audio_languages=["English", "German"]), "german"),
        (Meta(category="TV", original_language="en", audio_languages=["en", "fr", "de"]), "french"),
        (Meta(category="MOVIE", original_language="ru", audio_languages=["Russian"]), "russian"),
        (Meta(category="MOVIE", original_language="pt", audio_languages=["pt-BR", "English"]), "english"),
        (Meta(category="MOVIE", original_language="xx", audio_languages=["Japanese", "English"]), "japanese"),
        (Meta(category="MOVIE", audio_languages=[]), ""),
        (Meta(category="BOOK", book_language="German", audio_languages=["Russian"]), "german"),
        (Meta(category="GAME", audio_languages=["Russian"]), ""),
    ],
)
def test_language_tag_follows_the_release(meta, expected):
    assert DigitalCore.get_language(DigitalCore.__new__(DigitalCore), meta) == expected  # noqa: S101


def test_uses_the_image_hosts_approved_by_digitalcore():
    assert "ptscreens" in DigitalCore.approved_image_hosts  # noqa: S101
    assert "onlyimage" not in DigitalCore.approved_image_hosts  # noqa: S101
    assert _image_host("https://img2.ptscreens.com/image.png", DigitalCore.image_host_policy.url_host_mapping) == "ptscreens"  # noqa: S101


def test_force_rehost_images_uses_digitalcore_sharex_without_changing_global_host():
    config = {
        "DEFAULT": {
            "img_host_1": "ptscreens",
            "sharex_url": "https://img.digitalcore.club/api/upload",
            "sharex_api_key": "secret",
        },
        "TRACKERS": {"DIGITALCORE": {"api_key": "tracker-key", "force_rehost_images": True}},
    }

    tracker = DigitalCore(config)

    assert tracker.image_host_policy.approved_image_hosts == ("sharex",)  # noqa: S101
    assert tracker.rehost_images_manager.default_config["img_host_1"] == "sharex"  # noqa: S101
    assert config["DEFAULT"]["img_host_1"] == "ptscreens"  # noqa: S101
