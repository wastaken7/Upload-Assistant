"""Tests for tagged image records and tracker tag policies."""

# ruff: noqa: S101

import json

from src.meta import Meta
from src.tracker_images import image_matches_tag_policy, image_tag_policy, image_tags, normalize_image_tags, set_tracker_image_collection


def test_generated_image_tags_reflect_capture_attributes() -> None:
    assert image_tags(Meta()) == []
    assert image_tags(Meta(frame_overlay=True)) == ["overlay"]
    assert image_tags(Meta(tonemapped=True)) == ["tonemapped"]
    assert image_tags(Meta(frame_overlay=True, tonemapped=True)) == ["overlay", "tonemapped"]
    assert image_tags(Meta(frame_overlay=True), custom=True) == []


def test_image_tags_are_normalized_and_persist_as_json() -> None:
    image = {"raw_url": "https://example.test/screen.png", "tags": normalize_image_tags([" Overlay ", "TONEMAPPED", "overlay"])}
    encoded = json.dumps({"image_list": [image]})
    loaded = json.loads(encoded)
    assert loaded["image_list"][0]["tags"] == ["overlay", "tonemapped"]


def test_image_tag_policy_and_matching() -> None:
    config = {"TRACKERS": {"TEST": {"image_tag_whitelist": ["TONEMAPPED"], "image_tag_blacklist": ["Overlay"]}}}
    whitelist, blacklist = image_tag_policy(config, "TEST")
    assert whitelist == ["tonemapped"]
    assert blacklist == ["overlay"]
    assert image_matches_tag_policy({"tags": ["tonemapped"]}, whitelist, blacklist)
    assert not image_matches_tag_policy({"tags": ["overlay", "tonemapped"]}, whitelist, blacklist)
    assert not image_matches_tag_policy({"tags": ["overlay"]}, whitelist, blacklist)


def test_required_tags_are_added_to_tracker_policy() -> None:
    whitelist, blacklist = image_tag_policy({"TRACKERS": {"TEST": {}}}, "TEST", ["Tonemapped"])
    assert whitelist == ["tonemapped"]
    assert blacklist == []


def test_legacy_images_are_unknown_when_policy_is_enabled() -> None:
    assert not image_matches_tag_policy({"raw_url": "https://example.test/legacy.png"}, [], ["overlay"])
    assert not image_matches_tag_policy({"raw_url": "https://example.test/legacy.png"}, ["tonemapped"], [])
    assert image_matches_tag_policy({"raw_url": "https://example.test/legacy.png"}, [], [])


def test_invalid_whitelist_entries_fail_closed() -> None:
    whitelist, blacklist = image_tag_policy({"TRACKERS": {"TEST": {"image_tag_whitelist": [" "]}}}, "TEST")
    assert whitelist
    assert not image_matches_tag_policy({"tags": []}, whitelist, blacklist)


def test_tracker_collections_copy_and_normalize_tags() -> None:
    meta = Meta()
    source = [{"raw_url": "https://example.test/screen.png", "tags": [" Overlay ", "overlay"]}]
    set_tracker_image_collection(meta, "TEST", "screenshots", source)
    assert meta.tracker_image_collections["TEST"]["screenshots"] == [{"raw_url": "https://example.test/screen.png", "tags": ["overlay"]}]
    assert meta.tracker_image_collections["TEST"]["screenshots"][0] is not source[0]
