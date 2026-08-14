"""Regression tests for XXX image-upload thresholds."""

# Assertions are the idiomatic pytest checks for this focused threshold test.
# ruff: noqa: S101

from src.meta import Meta
from upload import xxx_min_successful_uploads


def test_xxx_upload_minimum_matches_one_contact_sheet_per_video():
    assert xxx_min_successful_uploads(Meta(category="XXX", screens=1), 6) == 1
    assert xxx_min_successful_uploads(Meta(category="XXX", screens=4), 6) == 4


def test_xxx_upload_still_requires_an_image_when_contact_sheet_count_is_missing():
    assert xxx_min_successful_uploads(Meta(category="XXX", screens=0), 6) == 1
