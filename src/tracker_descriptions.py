"""Shared policy and audit data for descriptions imported from trackers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any


class TrackerDescriptionMode(StrEnum):
    """The parts of a tracker release that may be imported."""

    IDS = "ids"
    IMAGES = "images"
    TEXT = "text"
    TEXT_AND_IMAGES = "text_and_images"

    @property
    def imports_text(self) -> bool:
        return self in {self.TEXT, self.TEXT_AND_IMAGES}

    @property
    def imports_images(self) -> bool:
        return self in {self.IMAGES, self.TEXT_AND_IMAGES}


def resolve_description_mode(configured_mode: object) -> TrackerDescriptionMode:
    """Validate the required, explicit tracker-description import policy."""
    if not isinstance(configured_mode, str):
        raise ValueError("DEFAULT.tracker_description_mode must be one of: ids, images, text, text_and_images")
    try:
        return TrackerDescriptionMode(configured_mode.strip().lower())
    except ValueError as error:
        raise ValueError("DEFAULT.tracker_description_mode must be one of: ids, images, text, text_and_images") from error


@dataclass(frozen=True)
class DescriptionCandidate:
    source: str
    release_id: str = ""
    source_url: str = ""
    release_name: str = ""
    raw_description: str = ""
    cleaned_description: str = ""
    image_count: int = 0
    score: int = 0

    def audit_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["raw_sha256"] = hashlib.sha256(self.raw_description.encode("utf-8")).hexdigest()
        record["cleaned_sha256"] = hashlib.sha256(self.cleaned_description.encode("utf-8")).hexdigest()
        record.pop("raw_description")
        return record


def description_fingerprint(meta: Any, tracker: str) -> str:
    """Hash inputs which change a generated tracker description."""
    images = meta.get("image_list", []) if hasattr(meta, "get") else getattr(meta, "image_list", [])
    payload = {
        "version": 1,
        "tracker": tracker.upper(),
        "category": getattr(meta, "category", ""),
        "name": getattr(meta, "name", ""),
        "description": getattr(meta, "description", ""),
        "images": [image.get("raw_url", image.get("img_url", "")) for image in images if isinstance(image, dict)],
        "mediainfo": getattr(meta, "mediainfo", {}),
        "bdinfo": getattr(meta, "bdinfo", {}),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def score_release_name(search_term: object, release_name: object, *, explicit_id: bool = False) -> int:
    """Return a transparent 0-100 similarity score for an imported release."""
    if explicit_id:
        return 100
    if not isinstance(search_term, str) or not isinstance(release_name, str):
        return 0
    expected = re.sub(r"[^a-z0-9]+", " ", search_term.lower()).strip()
    actual = re.sub(r"[^a-z0-9]+", " ", release_name.lower()).strip()
    if not expected or not actual:
        return 0
    expected_tokens = set(expected.split())
    actual_tokens = set(actual.split())
    overlap = len(expected_tokens & actual_tokens) / len(expected_tokens | actual_tokens)
    sequence = SequenceMatcher(None, expected, actual).ratio()
    return round((sequence * 70) + (overlap * 30))


def add_candidate(meta: Any, candidate: DescriptionCandidate, *, selected: bool) -> None:
    """Keep an inspectable, credential-free history on the current Meta object."""
    candidates = list(getattr(meta, "description_candidates", []) or [])
    record = candidate.audit_record()
    record["selected"] = selected
    candidates.append(record)
    meta.description_candidates = candidates
    if selected:
        meta.description_provenance = record
