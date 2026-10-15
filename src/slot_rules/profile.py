# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Normalized release traits used by the slot rules.

Traits come from the upload's metadata, or from a search result's name, flags,
type/resolution fields and MediaInfo text. A trait that cannot be determined is
left as ``None`` so rules can ask the user instead of guessing.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import langcodes

from src.meta import Meta

DISC = "DISC"
REMUX = "REMUX"
ENCODE = "ENCODE"
WEBDL = "WEBDL"
WEBRIP = "WEBRIP"
HDTV = "HDTV"
DVDRIP = "DVDRIP"

H264 = "H264"
H265 = "H265"
AV1 = "AV1"
MPEG2 = "MPEG2"
VC1 = "VC1"
XVID = "XVID"
OTHER = "OTHER"

DV = "DV"
HDR10 = "HDR10"
HDR10P = "HDR10+"
HLG = "HLG"
PQ10 = "PQ10"

SD = "SD"
RES_OTHER = "OTHER"

# Edition flags a slot can be split on. Theatrical is the standard cut.
_EDITION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("directors", r"director'?s?[ .\-]*cut|\bdc\b|directors"),
    ("extended", r"extended"),
    ("uncut", r"\buncut\b"),
    ("unrated", r"unrated"),
    ("imax", r"\bimax\b"),
    ("criterion", r"criterion"),
    ("4kremaster", r"4k[ .\-]*remaster"),
    ("open_matte", r"open[ .\-]*matte"),
    ("final_cut", r"final[ .\-]*cut"),
    ("ultimate", r"ultimate"),
    ("special", r"special[ .\-]*edition"),
    ("remastered", r"(?<!4k )remaster(?:ed)?"),
)

_ANT_FLAG_EDITIONS = {
    "directors": "directors",
    "extended": "extended",
    "uncut": "uncut",
    "unrated": "unrated",
    "imax": "imax",
    "criterion": "criterion",
    "4kremaster": "4kremaster",
}

_LOSSLESS_AUDIO = re.compile(r"truehd|mlp|dts[ .\-]?hd[ .\-]?ma|dts[ .\-]?x\b|dts xll|xll|flac|lpcm|\bpcm\b", re.IGNORECASE)


@dataclass(frozen=True)
class ReleaseProfile:
    name: str
    resolution: str | None = None
    kind: str | None = None
    codec: str | None = None
    # Empty set is SDR; None means the dynamic range could not be determined.
    hdr: frozenset[str] | None = None
    hybrid: bool = False
    is_3d: bool = False
    edition: frozenset[str] = frozenset()
    provider: str | None = None
    group: str | None = None
    size: int | None = None
    video_bitrate_kbps: int | None = None
    audio_codec: str | None = None
    audio_lossless: bool | None = None
    audio_channels: str | None = None
    audio_languages: frozenset[str] | None = None
    subtitle_languages: frozenset[str] | None = None
    internal: bool = False
    scene: bool | None = None
    repack: int = 0
    hi10p: bool = False
    exact: bool = False
    entry: Mapping[str, Any] = field(default_factory=lambda: dict[str, Any](), compare=False, hash=False)

    @property
    def is_sdr(self) -> bool:
        return self.hdr is not None and not self.hdr

    @property
    def hdr_label(self) -> str:
        if self.hdr is None:
            return "unknown dynamic range"
        if not self.hdr:
            return "SDR"
        order = [DV, HDR10P, HDR10, HLG, PQ10]
        return " ".join(item for item in order if item in self.hdr)


def normalize_resolution(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    if text in {"sd", "480p", "480i", "576p", "576i", "540p", "360p", "ntsc", "pal"}:
        return SD
    if text in {"720p", "720i"}:
        return "720p"
    if text in {"1080p", "1080i"}:
        return "1080p"
    if text in {"1440p", "1440i"}:
        return "1440p"
    if text in {"2160p", "4k", "uhd"}:
        return "2160p"
    if text in {"4320p", "8k"}:
        return "4320p"
    return RES_OTHER


def resolution_from_name(name: str) -> str | None:
    match = re.search(r"(?<!\d)(2160|1440|1080|720|576|540|480)([pi])(?![a-z0-9])", name, re.IGNORECASE)
    if match:
        return normalize_resolution(f"{match.group(1)}{match.group(2)}")
    if re.search(r"\b(uhd|4k)\b", name, re.IGNORECASE) and re.search(r"blu-?ray|remux|web", name, re.IGNORECASE):
        return "2160p"
    if re.search(r"\b(dvd|dvdrip|ntsc|pal|dvd5|dvd9)\b", name, re.IGNORECASE):
        return SD
    return None


def kind_from_type_label(label: str | None) -> str | None:
    """Map a tracker type label (UNIT3D type, ANT media) to a release kind."""
    if not label:
        return None
    text = re.sub(r"[^a-z0-9]", "", str(label).lower())
    if text in {"fulldisc", "disc", "bluray", "bdmv", "uhdbluray", "dvd", "dvd5", "dvd9", "fulldisk", "iso"}:
        return DISC
    if text == "remux":
        return REMUX
    if text in {"encode", "bdrip", "brrip", "bdencode"}:
        return ENCODE
    if text in {"webdl", "web"}:
        return WEBDL
    if text == "webrip":
        return WEBRIP
    if text in {"hdtv", "uhdtv", "sdtv", "tv"}:
        return HDTV
    if text == "dvdrip":
        return DVDRIP
    return None


def kind_from_name(name: str) -> str | None:
    text = name.lower()
    if re.search(r"\bremux\b", text):
        return REMUX
    if re.search(r"\b(bdmv|video_ts|bd25|bd50|bd66|bd100|dvd5|dvd9|complete[ .\-]*(uhd[ .\-]*)?blu-?ray)\b", text) or text.endswith(".iso"):
        return DISC
    if re.search(r"web[ .\-]?rip", text):
        return WEBRIP
    if re.search(r"web[ .\-]?dl|\bweb\b", text):
        return WEBDL
    if re.search(r"\b(u?hdtv|pdtv|sdtv|hdtvrip)\b", text):
        return HDTV
    if re.search(r"\bdvd[ .\-]?rip\b", text):
        return DVDRIP
    if re.search(r"blu-?ray|\bbd[ .\-]?rip\b|\bbr[ .\-]?rip\b|hd[ .\-]?dvd", text):
        return ENCODE
    if re.search(r"\b(x264|x265)\b", text):
        return ENCODE
    return None


def codec_from_text(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"\bav1\b", lowered):
        return AV1
    if re.search(r"\b(x\.?265|h\.?265|hevc)\b", lowered):
        return H265
    if re.search(r"\b(x\.?264|h\.?264|avc)\b", lowered):
        return H264
    if re.search(r"\bvc-?1\b", lowered):
        return VC1
    if re.search(r"\bmpeg-?2\b", lowered):
        return MPEG2
    if re.search(r"\b(xvid|divx)\b", lowered):
        return XVID
    return None


def hdr_from_name(name: str) -> frozenset[str]:
    text = f" {re.sub(r'[._()\[\]]', ' ', name.upper())} "
    found: set[str] = set()
    if re.search(r"\b(DV|DOVI|DOLBY ?VISION)\b", text):
        found.add(DV)
    if re.search(r"HDR10(\+|P\b|PLUS\b)", text):
        found.add(HDR10P)
    elif re.search(r"\bHDR(10)?\b", text):
        found.add(HDR10)
    if re.search(r"\bHLG\b", text):
        found.add(HLG)
    if re.search(r"\bPQ10?\b", text):
        found.add(PQ10)
    return frozenset(found)


def hdr_from_meta_value(value: str | None) -> frozenset[str]:
    """Translate ``meta.hdr`` (for example "DV HDR10+", "HDR", "HLG") to HDR flags."""
    found: set[str] = set()
    text = (value or "").upper()
    if "DV" in text.split():
        found.add(DV)
    if "HDR10+" in text:
        found.add(HDR10P)
    elif re.search(r"\bHDR(10)?\b", text):
        found.add(HDR10)
    if "HLG" in text:
        found.add(HLG)
    if "PQ10" in text:
        found.add(PQ10)
    return frozenset(found)


def editions_from_text(text: str | None) -> frozenset[str]:
    if not text:
        return frozenset()
    lowered = re.sub(r"[._]", " ", text.lower())
    found = {key for key, pattern in _EDITION_PATTERNS if re.search(pattern, lowered)}
    if "4kremaster" in found:
        found.discard("remastered")
    return frozenset(found)


def group_from_name(name: str) -> str | None:
    stem = re.sub(r"\.(mkv|mp4|avi|ts|m2ts|iso)$", "", name.strip(), flags=re.IGNORECASE)
    # Site tags such as "[TGx]" may follow the group.
    stem = re.sub(r"(?:\s*\[[^\]]*\])+$", "", stem)
    match = re.search(r"-([A-Za-z0-9][A-Za-z0-9_@!.&]*)$", stem)
    if not match:
        return None
    group = match.group(1)
    # Hyphens inside source/codec tokens ("WEB-DL.H.264", "Blu-ray.x264") are not a group.
    if re.match(r"(?:dl|rip|hd|ray|ma|\d+)(?:\.|$)", group, re.IGNORECASE):
        return None
    return group.lower()


def repack_level(name: str) -> int:
    match = re.search(r"\b(?:repack|rerip|proper)(\d?)\b", name, re.IGNORECASE)
    if not match:
        return 0
    return int(match.group(1)) if match.group(1) else 1


def _language_code(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"und", "unknown", "zxx", "mul"}:
        return None
    text = re.sub(r"\s*\(.*\)$", "", text)
    try:
        if re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,4})?", text):
            return str(cast(Any, langcodes).standardize_tag(text)).split("-")[0].lower()
        return str(cast(Any, langcodes).find(text).language).lower()
    except Exception:
        return None


def _languages(values: Iterable[Any]) -> frozenset[str]:
    codes = {_language_code(str(value)) for value in values}
    return frozenset(code for code in codes if code)


def parse_mediainfo_text(text: str) -> list[tuple[str, dict[str, str]]]:
    """Split MediaInfo text output into ``(section, fields)`` pairs."""
    sections: list[tuple[str, dict[str, str]]] = []
    current: dict[str, str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            current = None
            continue
        if ":" not in line:
            current = {}
            sections.append((line.split("#")[0].strip().lower(), current))
            continue
        if current is None:
            current = {}
            sections.append(("", current))
        key, _, value = line.partition(":")
        current.setdefault(key.strip().lower(), value.strip())
    return sections


def _bitrate_kbps(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"([\d\s.,]+)\s*(kb/s|mb/s|kbps|mbps)", value.lower())
    if not match:
        return None
    number = float(match.group(1).replace(" ", "").replace(",", "."))
    return int(number * 1000) if match.group(2).startswith("m") else int(number)


def _hdr_from_format(hdr_format: str) -> frozenset[str]:
    found: set[str] = set()
    if "dolby vision" in hdr_format.lower():
        found.add(DV)
    if "HDR10+" in hdr_format or "SMPTE ST 2094 App 4" in hdr_format:
        found.add(HDR10P)
    elif "HDR10" in hdr_format or "SMPTE ST 2086" in hdr_format:
        found.add(HDR10)
    if "HLG" in hdr_format:
        found.add(HLG)
    return frozenset(found)


@dataclass
class _MediaInfoTraits:
    hdr: frozenset[str] | None = None
    video_bitrate_kbps: int | None = None
    codec: str | None = None
    hi10p: bool = False
    audio_codec: str | None = None
    audio_lossless: bool | None = None
    audio_channels: str | None = None
    audio_languages: frozenset[str] | None = None
    subtitle_languages: frozenset[str] | None = None


def _traits_from_mediainfo_text(text: str | None) -> _MediaInfoTraits:
    traits = _MediaInfoTraits()
    if not text or "video" not in text.lower():
        return traits
    sections = parse_mediainfo_text(text)
    videos = [fields for name, fields in sections if name == "video"]
    audios = [fields for name, fields in sections if name == "audio"]
    texts = [fields for name, fields in sections if name == "text"]
    if videos:
        video = videos[0]
        hdr_format = video.get("hdr format", "")
        if hdr_format:
            traits.hdr = _hdr_from_format(hdr_format)
        elif "bt.2020" not in video.get("color primaries", "").lower():
            traits.hdr = frozenset()
        elif "pq" in video.get("transfer characteristics", "").lower():
            traits.hdr = frozenset({PQ10})
        elif "hlg" in video.get("transfer characteristics", "").lower():
            traits.hdr = frozenset({HLG})
        traits.video_bitrate_kbps = _bitrate_kbps(video.get("bit rate") or video.get("nominal bit rate"))
        traits.codec = codec_from_text(f"{video.get('format', '')} {video.get('writing library', '')}")
        traits.hi10p = traits.codec == H264 and "10 bits" in video.get("bit depth", "")
    if audios:
        main = audios[0]
        commercial = main.get("commercial name", "")
        audio_format = f"{main.get('format', '')} {commercial} {main.get('format/info', '')}"
        traits.audio_codec = (commercial or main.get("format") or "").strip() or None
        traits.audio_lossless = bool(_LOSSLESS_AUDIO.search(audio_format))
        traits.audio_channels = (main.get("channel(s)") or "").split(" ")[0] or None
        languages = [fields.get("language", "") for fields in audios if "commentary" not in fields.get("title", "").lower()]
        traits.audio_languages = _languages(languages)
    traits.subtitle_languages = _languages(fields.get("language", "") for fields in texts)
    return traits


def _traits_from_mediainfo_json(mediainfo: Mapping[str, Any] | None) -> _MediaInfoTraits:
    traits = _MediaInfoTraits()
    tracks_value = cast(list[Any], cast(Mapping[str, Any], (mediainfo or {}).get("media") or {}).get("track") or [])
    tracks = [cast(dict[str, Any], track) for track in tracks_value if isinstance(track, dict)]
    general = next((track for track in tracks if track.get("@type") == "General"), {})
    video = next((track for track in tracks if track.get("@type") == "Video"), {})
    audios = [track for track in tracks if track.get("@type") == "Audio"]
    subtitles = [track for track in tracks if track.get("@type") == "Text"]
    raw_bitrate = video.get("BitRate") or video.get("BitRate_Nominal") or general.get("OverallBitRate")
    try:
        traits.video_bitrate_kbps = int(float(str(raw_bitrate)) / 1000) if raw_bitrate else None
    except ValueError:
        traits.video_bitrate_kbps = None
    traits.hi10p = str(video.get("Format", "")).upper() == "AVC" and str(video.get("BitDepth", "")) == "10"
    if audios:
        main = audios[0]
        audio_format = f"{main.get('Format', '')} {main.get('Format_Commercial_IfAny', '')} {main.get('Format_AdditionalFeatures', '')}"
        traits.audio_codec = str(main.get("Format_Commercial_IfAny") or main.get("Format") or "") or None
        traits.audio_lossless = bool(_LOSSLESS_AUDIO.search(audio_format))
        languages = [track.get("Language", "") for track in audios if "commentary" not in str(track.get("Title", "")).lower()]
        traits.audio_languages = _languages(languages)
    traits.subtitle_languages = _languages(track.get("Language", "") for track in subtitles)
    return traits


def _is_hybrid(name: str) -> bool:
    return bool(re.search(r"\bhybrid\b", name, re.IGNORECASE))


def _is_3d(name: str) -> bool:
    return bool(re.search(r"\b3d\b|\b(h-?sbs|h-?ou|half-?sbs|half-?ou|sbs|mvc)\b", name, re.IGNORECASE))


def kind_from_meta(meta: Meta) -> str | None:
    if meta.is_disc:
        return DISC
    mapping = {"REMUX": REMUX, "ENCODE": ENCODE, "WEBDL": WEBDL, "WEBRIP": WEBRIP, "HDTV": HDTV, "DVDRIP": DVDRIP, "DISC": DISC}
    return mapping.get(str(meta.type or "").upper())


def profile_from_meta(meta: Meta, *, provider: str | None = None) -> ReleaseProfile:
    name = meta.name or ""
    mi = _traits_from_mediainfo_json(cast(Mapping[str, Any], meta.mediainfo or {}))
    codec = codec_from_text(f"{meta.video_encode} {meta.video_codec}")
    tag = (meta.tag or "").lstrip("-").strip().lower() or None
    resolution = SD if meta.sd else normalize_resolution(meta.resolution)
    audio_languages = _languages(meta.audio_languages or []) or mi.audio_languages
    subtitles_value = meta.subtitle_languages
    subtitle_list: list[Any] = [subtitles_value] if isinstance(subtitles_value, str) else list(subtitles_value or [])
    subtitle_languages = _languages(subtitle_list) or mi.subtitle_languages
    return ReleaseProfile(
        name=name,
        resolution=resolution,
        kind=kind_from_meta(meta),
        codec=codec,
        hdr=hdr_from_meta_value(meta.hdr),
        hybrid=_is_hybrid(name) or _is_hybrid(meta.uuid or ""),
        is_3d=bool(meta.three_d) or _is_3d(name),
        edition=editions_from_text(meta.edition) | editions_from_text(name),
        provider=(provider or meta.service or None),
        group=tag,
        size=_int_or_none(meta.source_size),
        video_bitrate_kbps=mi.video_bitrate_kbps,
        audio_codec=meta.audio or mi.audio_codec,
        audio_lossless=bool(_LOSSLESS_AUDIO.search(meta.audio)) if meta.audio else mi.audio_lossless,
        audio_channels=meta.channels or mi.audio_channels,
        audio_languages=audio_languages,
        subtitle_languages=subtitle_languages,
        internal=False,
        scene=bool(meta.scene),
        repack=repack_level(f"{meta.repack} {meta.uuid}"),
        hi10p=mi.hi10p or bool(re.search(r"hi10p?", name, re.IGNORECASE)),
    )


def _int_or_none(value: Any) -> int | None:
    from src.uphelper import parse_size_to_bytes

    try:
        parsed = parse_size_to_bytes(value)
    except Exception:
        return None
    return parsed if parsed and parsed > 0 else None


def profile_from_entry(entry: Mapping[str, Any], *, provider: str | None = None, exact: bool = False) -> ReleaseProfile:
    """Build a profile for a search result. ``entry`` follows ``DupeEntry``."""
    name = str(entry.get("name") or "")
    flags = [str(flag) for flag in cast(list[Any], entry.get("flags") or []) if flag]
    flag_keys = {re.sub(r"[^a-z0-9+]", "", flag.lower()) for flag in flags}
    files = [str(file) for file in cast(list[Any], entry.get("files") or [])]

    mi = _traits_from_mediainfo_text(cast(str | None, entry.get("media_info")))

    kind = kind_from_type_label(cast(str | None, entry.get("type"))) or kind_from_name(name)
    if "remux" in flag_keys:
        kind = REMUX
    if kind is None and any(re.search(r"(^|/)(bdmv|video_ts)(/|$)", file, re.IGNORECASE) for file in files):
        kind = DISC

    resolution = normalize_resolution(cast(str | None, entry.get("res"))) or resolution_from_name(name)

    hdr: frozenset[str] | None
    if mi.hdr is not None:
        hdr = mi.hdr
    elif flags:
        flagged: set[str] = set()
        if flag_keys & {"dv", "dovi", "dolbyvision"}:
            flagged.add(DV)
        if flag_keys & {"hdr10+", "hdr10plus"}:
            flagged.add(HDR10P)
        elif flag_keys & {"hdr10", "hdr"}:
            flagged.add(HDR10)
        # Flags are authoritative where the tracker defines them, but the name
        # can still add HDR10+ or HLG which ANT's flags do not distinguish.
        hdr = frozenset(flagged | (hdr_from_name(name) - {DV, HDR10}))
    else:
        hdr = hdr_from_name(name)

    edition = editions_from_text(name) | {_ANT_FLAG_EDITIONS[key] for key in flag_keys if key in _ANT_FLAG_EDITIONS}

    return ReleaseProfile(
        name=name,
        resolution=resolution,
        kind=kind,
        codec=mi.codec or codec_from_text(name),
        hdr=hdr,
        hybrid=_is_hybrid(name),
        is_3d="3d" in flag_keys or _is_3d(name),
        edition=frozenset(edition),
        provider=provider,
        group=group_from_name(name),
        size=_int_or_none(entry.get("size")),
        video_bitrate_kbps=mi.video_bitrate_kbps,
        audio_codec=mi.audio_codec,
        audio_lossless=mi.audio_lossless if mi.audio_lossless is not None else (bool(_LOSSLESS_AUDIO.search(name)) if name else None),
        audio_channels=mi.audio_channels,
        audio_languages=mi.audio_languages,
        subtitle_languages=mi.subtitle_languages,
        internal=bool(entry.get("internal")),
        scene=None,
        repack=repack_level(name),
        hi10p=mi.hi10p or bool(re.search(r"hi10p?", name, re.IGNORECASE)),
        exact=exact,
        entry=entry,
    )


_AUDIO_FAMILIES: tuple[tuple[str, str], ...] = (
    ("truehd", r"truehd|mlp"),
    ("dts-hd ma", r"dts[ .\-]?hd[ .\-]?ma|dts[ .\-]?x\b|xll"),
    ("lpcm", r"lpcm|\bpcm\b"),
    ("flac", r"flac"),
    ("dd+", r"dd\+|ddp|e-?ac-?3|dolby digital plus"),
    ("dd", r"\bdd\b|\bac-?3\b|dolby digital"),
    ("dts", r"\bdts\b"),
    ("aac", r"\baac\b"),
    ("opus", r"\bopus\b"),
    ("mp3", r"\bmp3\b|mpeg audio"),
)


def audio_family(value: str | None) -> str | None:
    """Collapse audio codec names ("DD+ 5.1 Atmos", "E-AC-3") into one family name."""
    if not value:
        return None
    lowered = value.lower()
    for family, pattern in _AUDIO_FAMILIES:
        if re.search(pattern, lowered):
            return family
    return None


def channel_count(value: str | None) -> int | None:
    """Total channels from "5.1", "7.1.4", "2.0" or MediaInfo's "6"."""
    if not value:
        return None
    match = re.fullmatch(r"\s*(\d+)(?:\.(\d))?(?:\.(\d))?\s*", str(value))
    if not match:
        return None
    return sum(int(part) for part in match.groups() if part is not None)
