from src.rehostimages import _image_host
from src.trackers.digitalcore import DigitalCore


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
