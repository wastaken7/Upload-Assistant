from src.rehostimages import _image_host
from src.trackers.digitalcore import DigitalCore


def test_uses_the_image_hosts_approved_by_digitalcore():
    assert "ptscreens" in DigitalCore.approved_image_hosts  # noqa: S101
    assert "onlyimage" not in DigitalCore.approved_image_hosts  # noqa: S101
    assert _image_host("https://img2.ptscreens.com/image.png", DigitalCore.image_host_policy.url_host_mapping) == "ptscreens"  # noqa: S101
