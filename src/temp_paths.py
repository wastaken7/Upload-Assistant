"""Well-known per-release temporary asset directories.

The release temporary directory also stores metadata, torrents and logs.  Image
artifacts must not share that root: consumers often enumerate PNGs and would
otherwise mistake a poster, cover or diagnostic image for a screenshot.
"""

from __future__ import annotations

from pathlib import Path

from src.app_paths import STATE_DIR


def release_temp_dir(base_dir: str | Path | None, release_id: str) -> Path:
    """Return the root temporary directory for one release."""
    return Path(base_dir or STATE_DIR) / "tmp" / str(release_id)


def music_release_snapshot_path(base_dir: str | Path | None, release_id: str) -> Path:
    """Return the music metadata snapshot path under a user-owned state directory."""
    return release_temp_dir(base_dir, release_id) / "music_release.json"


def image_dir(base_dir: str | Path | None, release_id: str, kind: str) -> Path:
    """Return and create a typed image directory below a release's temp root."""
    path = release_temp_dir(base_dir, release_id) / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def screenshots_dir(base_dir: str | Path | None, release_id: str) -> Path:
    return image_dir(base_dir, release_id, "screenshots")


def artwork_dir(base_dir: str | Path | None, release_id: str) -> Path:
    """Return the per-release directory for all local artwork assets."""
    return image_dir(base_dir, release_id, "artwork")


def menu_screenshots_dir(base_dir: str | Path | None, release_id: str) -> Path:
    return image_dir(base_dir, release_id, "menu_screenshots")


def spectrograms_dir(base_dir: str | Path | None, release_id: str) -> Path:
    return image_dir(base_dir, release_id, "spectrograms")


def dynamic_hdr_plots_dir(base_dir: str | Path | None, release_id: str) -> Path:
    """Return the per-release directory for Dolby Vision/HDR10+ plot images."""
    return image_dir(base_dir, release_id, "dynamic_hdr_plots")
