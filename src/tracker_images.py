"""Tracker-scoped image collections used during concurrent uploads."""

from collections.abc import Sequence
from typing import Any, Literal

from src.meta import Meta

ImageCollection = Literal["screenshots", "menu_images", "spectrograms_images", "dynamic_hdr_plot_images"]
ImageDict = dict[str, Any]


def normalize_image_tags(value: Any) -> list[str]:
    """Return stable, case-insensitive image tags without duplicates."""
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for tag in value:
        normalized = str(tag).strip().lower()
        if not normalized:
            normalized = f"__invalid__:{tag!r}"
        if normalized not in result:
            result.append(normalized)
    return result


def image_tags(meta: Meta, *, custom: bool = False) -> list[str]:
    """Build tags for an image generated during the current upload."""
    if custom:
        return []
    tags: list[str] = []
    if meta.frame_overlay:
        tags.append("overlay")
    if meta.tonemapped:
        tags.append("tonemapped")
    return tags


def image_tag_policy(config: Any, tracker: str, required_tags: Any = None) -> tuple[list[str], list[str]]:
    """Read a tracker's optional image tag whitelist and blacklist."""
    if not isinstance(config, dict):
        return [], []
    tracker_config = config.get("TRACKERS", {}).get(tracker, {})
    if not isinstance(tracker_config, dict):
        return [], []
    whitelist = normalize_image_tags(tracker_config.get("image_tag_whitelist"))
    for tag in normalize_image_tags(required_tags):
        if tag not in whitelist:
            whitelist.append(tag)
    return whitelist, normalize_image_tags(tracker_config.get("image_tag_blacklist"))


def image_matches_tag_policy(image: ImageDict, whitelist: list[str], blacklist: list[str]) -> bool:
    """Return whether an image is known to satisfy a tag policy."""
    if not whitelist and not blacklist:
        return True
    if "tags" not in image:
        return False
    tags = set(normalize_image_tags(image.get("tags")))
    return set(whitelist).issubset(tags) and not tags.intersection(blacklist)


_BASE_COLLECTION_FIELDS: dict[ImageCollection, str] = {
    "screenshots": "image_list",
    "menu_images": "menu_images",
    "spectrograms_images": "spectrograms_images",
    "dynamic_hdr_plot_images": "dynamic_hdr_plot_images",
}


def get_tracker_image_collection(meta: Meta, tracker: str, collection: ImageCollection) -> list[Any]:
    """Return a tracker override or the release-wide collection as fallback."""
    tracker_collections = meta.tracker_image_collections.get(tracker, {})
    if collection in tracker_collections:
        return tracker_collections[collection]
    images = getattr(meta, _BASE_COLLECTION_FIELDS[collection])
    return images if isinstance(images, list) else []


def has_tracker_image_collection(meta: Meta, tracker: str, collection: ImageCollection) -> bool:
    """Return whether a tracker has an explicit collection override."""
    return collection in meta.tracker_image_collections.get(tracker, {})


def set_tracker_image_collection(meta: Meta, tracker: str, collection: ImageCollection, images: Sequence[ImageDict]) -> None:
    """Store a tracker-local image collection without mutating shared metadata."""
    copied: list[ImageDict] = []
    for image in images:
        item = dict(image)
        if "tags" in item:
            item["tags"] = normalize_image_tags(item["tags"])
        copied.append(item)
    meta.tracker_image_collections.setdefault(tracker, {})[collection] = copied
