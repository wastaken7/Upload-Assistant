"""Run options the Web UI offers as toggles on the "Is this correct?" prompt.

Each option is a command-line flag that is only read after the release is
confirmed (screenshots, extra images, tracker upload data, the torrent
client), so it can be changed there without preparing the release again.
Options that change the release name (for example ``--hardcoded-subs``)
are not offered: the confirmed name would no longer be the one uploaded.

The GUI answers ``yes {"anon": true}``; only offered, unlocked options with a
value of the expected type are applied. The terminal still answers y/n.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from src.dynamic_hdr_plot import dynamic_hdr_plot_enabled
from src.meta import Meta

VIDEO_CATEGORIES = frozenset({"MOVIE", "TV", "XXX"})
# Trackers that read a flag offered only when one of them is selected.
DRAFT_TRACKERS = frozenset({"BEYONDHD", "LST"})
EXTRAS_TRACKERS = frozenset({"BJSHARE", "CATHODERAYTUBE", "GREATPOSTERWALL"})
SFX_SUBTITLE_TRACKERS = frozenset({"GREATPOSTERWALL"})


def _trackers(meta: Meta) -> set[str]:
    trackers = meta.trackers
    if isinstance(trackers, str):
        trackers = [trackers]
    return {str(tracker).upper() for tracker in trackers or []}


def _toggle(key: str, label: str, group: str, value: bool, *, hint: str = "", locked: str = "") -> dict[str, Any]:
    option: dict[str, Any] = {"key": key, "label": label, "group": group, "type": "toggle", "value": bool(value)}
    if hint:
        option["hint"] = hint
    if locked:
        # Already on through the config: turning it off here would not stop it.
        option["locked"] = locked
    return option


def _configured_image_hosts(config: Mapping[str, Any]) -> list[str]:
    default = config.get("DEFAULT", {})
    hosts: list[str] = []
    for number in range(1, 10):
        host = str(default.get(f"img_host_{number}") or "").strip().lower()
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def available(meta: Meta, config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the options relevant to this release, with their current values."""
    default = config.get("DEFAULT", {})
    category = str(meta.category or "")
    trackers = _trackers(meta)
    options: list[dict[str, Any]] = []

    hdr = str(meta.hdr or "").upper()
    if category in VIDEO_CATEGORIES and ("DV" in hdr or "DOLBY VISION" in hdr or "HDR10+" in hdr):
        # The config (globally or for a selected tracker) keeps plots on whatever the flag says.
        from_config = dynamic_hdr_plot_enabled(Meta(trackers=meta.trackers), dict(config))
        locked = "Enabled in your config" if from_config else ""
        options.append(_toggle("dynamic_hdr_plot", "Dolby Vision / HDR10+ plots", "media", bool(meta.dynamic_hdr_plot) or from_config, locked=locked))

    if category in VIDEO_CATEGORIES or category == "MUSIC" or meta.audiobook:
        from_config = bool(default.get("add_audio_spectrogram", False))
        enabled = bool(meta.audio_spectrogram or meta.audio_spectrogram_tracks) or from_config
        locked = "Enabled in your config" if from_config else ""
        options.append(_toggle("audio_spectrogram", "Audio spectrograms", "media", enabled, locked=locked))

    if meta.is_disc == "DVD":
        from_config = bool(default.get("auto_dvd_menus", False))
        menus = str(meta.path_to_menu_screenshots or "")
        locked = "Using the menus folder you set" if menus and menus.lower() != "auto" else ("Enabled in your config" if from_config else "")
        options.append(_toggle("disc_menus", "Capture DVD menu screenshots", "media", bool(menus) or from_config, locked=locked))

    if category in VIDEO_CATEGORIES and (meta.is_disc or trackers & EXTRAS_TRACKERS):
        options.append(_toggle("extras", "Contains extras", "media", bool(meta.extras)))

    if category in VIDEO_CATEGORIES and trackers & SFX_SUBTITLE_TRACKERS:
        options.append(_toggle("sfx_subtitles", "Subtitles with special effects", "media", bool(meta.sfx_subtitles), hint="Animated or styled subtitles"))

    options.append(_toggle("anon", "Anonymous", "upload", bool(meta.anon), hint="Trackers set to anonymous in your config stay anonymous"))
    if category in VIDEO_CATEGORIES:
        options.append(_toggle("personalrelease", "Personal release", "upload", bool(meta.personalrelease)))
    # A tracker's own modq setting applies only to it, so the toggle stays free for the others.
    tracker_configs = config.get("TRACKERS", {})
    modq_configured = sorted(tracker for tracker in trackers if isinstance(tracker_configs.get(tracker), dict) and tracker_configs[tracker].get("modq") is True)
    modq_hint = f"Already on for {', '.join(modq_configured)} in your config" if modq_configured else "On trackers that support it"
    options.append(_toggle("modq", "Moderation queue", "upload", bool(meta.modq), hint=modq_hint))
    if trackers & DRAFT_TRACKERS:
        options.append(_toggle("draft", "Send as draft", "upload", bool(meta.draft), hint="BeyondHD and LST"))
    options.append(_toggle("no_seed", "Don't add to the torrent client", "upload", bool(meta.no_seed)))

    hosts = _configured_image_hosts(config)
    if len(hosts) > 1 and not meta.skip_imghost_upload and category not in ("GAME", "MUSIC"):
        current = str(meta.imghost or hosts[0]).lower()
        if current not in hosts:
            hosts.insert(0, current)
        options.append({"key": "imghost", "label": "Image host", "group": "upload", "type": "choice", "value": current, "choices": hosts})
    return options


def parse_answer(text: str | None, default: bool) -> tuple[bool | None, dict[str, Any]]:
    """Split a confirm answer into yes/no and the option values sent with it.

    Returns ``(None, {})`` for an answer that is not y/n or carries invalid JSON.
    """
    answer, _, payload = (text or "").strip().partition(" ")
    word = answer.lower()
    if word in ("y", "yes"):
        confirmed: bool | None = True
    elif word in ("n", "no"):
        confirmed = False
    elif not word:
        confirmed = default
    else:
        return None, {}
    if not payload.strip():
        return confirmed, {}
    try:
        values = json.loads(payload)
    except ValueError:
        return None, {}
    if not isinstance(values, dict):
        return None, {}
    return confirmed, cast(dict[str, Any], values)


def apply(meta: Meta, options: list[dict[str, Any]], values: Mapping[str, Any]) -> list[str]:
    """Apply the offered options' new values to ``meta``; return the labels changed."""
    changed: list[str] = []
    for option in options:
        key = option["key"]
        if key not in values or option.get("locked"):
            continue
        value = values[key]
        if option["type"] == "toggle":
            if not isinstance(value, bool) or value == option["value"]:
                continue
            if key == "disc_menus":
                meta.path_to_menu_screenshots = "auto" if value else ""
            elif key == "audio_spectrogram":
                meta.audio_spectrogram = value
                if not value:
                    meta.audio_spectrogram_tracks = None
            else:
                setattr(meta, key, value)
            changed.append(f"{option['label']}: {'on' if value else 'off'}")
        elif option["type"] == "choice":
            if not isinstance(value, str) or value not in option["choices"] or value == option["value"]:
                continue
            setattr(meta, key, value)
            if key == "imghost":
                meta.imghost_from_cli = True
            changed.append(f"{option['label']}: {value}")
    return changed
