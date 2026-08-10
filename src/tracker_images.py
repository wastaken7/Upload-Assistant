"""Tracker-scoped image collections used during concurrent uploads."""

from collections.abc import Sequence
from typing import Any, Literal

from src.meta import Meta

ImageCollection = Literal["screenshots", "menu_images", "spectrograms_images", "dynamic_hdr_plot_images"]
ImageDict = dict[str, Any]

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
    meta.tracker_image_collections.setdefault(tracker, {})[collection] = [dict(image) for image in images]
