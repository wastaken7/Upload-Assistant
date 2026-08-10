# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Audio category classifier for distinguishing MUSIC vs AUDIOBOOK releases."""

from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mutagen

from src.book_prep import BOOK_EXTENSIONS

AUDIOBOOK_CONTAINER_EXTENSIONS = frozenset({".m4b", ".aax", ".aaxc"})
SHARED_AUDIO_EXTENSIONS = frozenset({".mp3", ".flac", ".m4a", ".aac", ".ac3", ".dts", ".wav", ".aiff", ".alac", ".ogg", ".opus", ".ape", ".wv", ".wma"})

SPOKEN_GENRES = frozenset(
    {
        "audiobook",
        "audio book",
        "audiobooks",
        "audio books",
        "spoken word",
        "spokenword",
        "speech",
        "spoken",
        "audio drama",
        "podcast",
        "radio play",
        "story",
        "nonfiction",
        "fiction",
        "novel",
        "memoir",
        "biography",
        "lecture",
        "talk",
    }
)

MUSIC_GENRES = frozenset(
    {
        "rock",
        "pop",
        "jazz",
        "metal",
        "electronic",
        "classical",
        "hip hop",
        "hip-hop",
        "rap",
        "indie",
        "soundtrack",
        "folk",
        "blues",
        "reggae",
        "country",
        "ambient",
        "punk",
        "house",
        "techno",
        "trance",
        "disco",
        "funk",
        "soul",
        "r&b",
        "r & b",
        "alternative",
        "dance",
        "industrial",
        "instrumental",
        "heavy metal",
        "pop rock",
        "hard rock",
        "synthpop",
        "lo-fi",
        "ska",
        "grunge",
        "gospel",
        "opera",
        "symphony",
        "bluegrass",
        "new age",
    }
)

AUDIOBOOK_FILENAME_REGEX = re.compile(
    r"(?i)\b(?:chapter|part|pt|section|act|bk|book)\s*\d+|\b(?:part|ch|chapter)\d+\b|\btrack\s*\d+\s*[-_]\s*chapter\b|\b(?:audiobook|unabridged|abridged|read by|narrated by)\b"
)

MUSIC_FILENAME_REGEX = re.compile(r"^\s*\d{1,3}\s*[-._]\s*(?![cC]hapter|[pP]art|[bB]ook)\w+")


@dataclass
class AudioCategoryResult:
    category: str  # "BOOK", "MUSIC", "AMBIGUOUS", or "NONE"
    is_audiobook: bool = False
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)


def _inspect_audio_file(filepath: Path) -> dict[str, Any]:
    info_dict: dict[str, Any] = {
        "channels": 0,
        "bitrate": 0,
        "sample_rate": 0,
        "length": 0.0,
        "genres": [],
        "title": "",
        "artist": "",
        "album": "",
        "albumartist": "",
        "narrator": "",
        "author": "",
        "publisher": "",
        "isbn": "",
        "asin": "",
        "has_chapters": False,
        "has_musicbrainz": False,
        "has_discogs": False,
        "has_catalog_no": False,
        "raw_tag_text": "",
    }

    with contextlib.suppress(Exception):
        easy_audio = mutagen.File(str(filepath), easy=True)
        if easy_audio and easy_audio.tags:
            for key in ("genre",):
                vals = easy_audio.tags.get(key, [])
                info_dict["genres"].extend([str(v).strip() for v in vals if v])
            for key in ("title", "artist", "album", "albumartist"):
                vals = easy_audio.tags.get(key, [])
                if vals:
                    info_dict[key] = str(vals[0]).strip()

    with contextlib.suppress(Exception):
        audio = mutagen.File(str(filepath))
        if audio is not None:
            if hasattr(audio, "info") and audio.info:
                info_dict["channels"] = getattr(audio.info, "channels", 0) or 0
                info_dict["bitrate"] = getattr(audio.info, "bitrate", 0) or 0
                info_dict["sample_rate"] = getattr(audio.info, "sample_rate", 0) or 0
                info_dict["length"] = getattr(audio.info, "length", 0.0) or 0.0

            tags = getattr(audio, "tags", None)
            if tags:
                all_text_pieces: list[str] = []
                if hasattr(tags, "keys"):
                    for k in tags:
                        k_str = str(k)
                        k_lower = k_str.lower()
                        if k_str.startswith("CHAP") or k_str.startswith("CTOC") or "chapter" in k_lower:
                            info_dict["has_chapters"] = True

                if hasattr(tags, "items"):
                    for k, v in tags.items():
                        k_str = str(k).lower()
                        v_str = str(v)
                        all_text_pieces.append(f"{k_str}={v_str}")

                        if "narrator" in k_str or "read by" in k_str or "reader" in k_str:
                            info_dict["narrator"] = v_str
                        if "author" in k_str or "writer" in k_str:
                            info_dict["author"] = v_str
                        if "publisher" in k_str:
                            info_dict["publisher"] = v_str
                        if "isbn" in k_str:
                            info_dict["isbn"] = v_str
                        if "asin" in k_str:
                            info_dict["asin"] = v_str
                        if "musicbrainz" in k_str:
                            info_dict["has_musicbrainz"] = True
                        if "discogs" in k_str:
                            info_dict["has_discogs"] = True
                        if "catalognumber" in k_str or "catno" in k_str or "label" in k_str:
                            info_dict["has_catalog_no"] = True
                        if "genre" in k_str and not info_dict["genres"]:
                            info_dict["genres"].append(v_str)

                info_dict["raw_tag_text"] = " ".join(all_text_pieces).lower()
                if "chapter00" in info_dict["raw_tag_text"] or "chapter01" in info_dict["raw_tag_text"]:
                    info_dict["has_chapters"] = True

    return info_dict


async def detect_audio_category(_meta: Any, path: Path | str) -> AudioCategoryResult:
    """Classify an audio directory or file as BOOK (audiobook), MUSIC, or AMBIGUOUS."""
    path_obj = Path(path)
    if not path_obj.exists():
        return AudioCategoryResult(category="NONE")

    all_files: list[Path] = []
    if path_obj.is_dir():
        for root, _, files in os.walk(path_obj):
            all_files.extend(Path(root) / file for file in files)
    else:
        all_files = [path_obj]

    video_extensions = {".mkv", ".mp4", ".ts", ".avi", ".m2ts"}
    has_video = any(f.suffix.lower() in video_extensions for f in all_files)
    if has_video:
        return AudioCategoryResult(category="NONE", evidence=["Contains video files"])

    ebook_extensions = BOOK_EXTENSIONS - {".txt", ".html", ".htm"}
    has_ebook = any(f.suffix.lower() in ebook_extensions for f in all_files)
    has_audiobook_container = any(f.suffix.lower() in AUDIOBOOK_CONTAINER_EXTENSIONS for f in all_files)

    audio_files = [f for f in all_files if f.suffix.lower() in SHARED_AUDIO_EXTENSIONS or f.suffix.lower() in AUDIOBOOK_CONTAINER_EXTENSIONS]

    if has_audiobook_container and not has_video:
        exts = {f.suffix.lower() for f in all_files if f.suffix.lower() in AUDIOBOOK_CONTAINER_EXTENSIONS}
        return AudioCategoryResult(
            category="BOOK",
            is_audiobook=True,
            confidence=1.0,
            evidence=[f"audiobook-specific container format ({', '.join(sorted(exts))})"],
        )

    if has_ebook and audio_files:
        return AudioCategoryResult(
            category="BOOK",
            is_audiobook=True,
            confidence=1.0,
            evidence=["Directory contains both eBook and audio files"],
        )

    if has_ebook and not audio_files:
        return AudioCategoryResult(
            category="BOOK",
            is_audiobook=False,
            confidence=1.0,
            evidence=["Directory contains eBook file"],
        )

    if not audio_files:
        return AudioCategoryResult(category="NONE")

    # Inspect shared audio files
    book_evidence: list[str] = [f"{len(audio_files)} audio files detected"]
    music_evidence: list[str] = [f"{len(audio_files)} audio files detected"]
    book_score = 0.0
    music_score = 0.0

    # A. Filename patterns
    chapter_part_matches = 0
    music_track_matches = 0
    for af in audio_files:
        name = af.name
        if AUDIOBOOK_FILENAME_REGEX.search(name):
            chapter_part_matches += 1
        elif MUSIC_FILENAME_REGEX.search(name):
            music_track_matches += 1

    if chapter_part_matches > 0 and chapter_part_matches >= len(audio_files) * 0.3:
        book_score += 4.0
        book_evidence.append(f"chapter/part filename pattern ({chapter_part_matches}/{len(audio_files)} files)")

    if music_track_matches > 0 and music_track_matches >= len(audio_files) * 0.5:
        music_score += 2.0
        music_evidence.append(f"standard numbered song titles ({music_track_matches}/{len(audio_files)} files)")

    parent_dir_name = path_obj.name.lower()
    if any(w in parent_dir_name for w in ("audiobook", "audiobooks", "audio book", "audio books", "readarr", "libby")):
        book_score += 2.0
        book_evidence.append(f"parent directory hint ('{path_obj.name}')")

    # B. Metadata and Technical characteristics inspection
    sample_files = audio_files[:30]
    genres_found: set[str] = set()
    has_chapters = False
    has_narrator = False
    has_author = False
    has_isbn_asin = False
    has_musicbrainz = False
    has_discogs = False
    has_catalog_no = False

    mono_count = 0
    low_bitrate_count = 0
    low_samplerate_count = 0
    long_track_count = 0

    for af in sample_files:
        parsed = _inspect_audio_file(af)
        for g in parsed["genres"]:
            if g:
                genres_found.add(g.lower())

        if parsed["has_chapters"]:
            has_chapters = True
        if parsed["narrator"]:
            has_narrator = True
        if parsed["author"]:
            has_author = True
        if parsed["isbn"] or parsed["asin"]:
            has_isbn_asin = True
        if parsed["has_musicbrainz"]:
            has_musicbrainz = True
        if parsed["has_discogs"]:
            has_discogs = True
        if parsed["has_catalog_no"]:
            has_catalog_no = True

        if parsed["channels"] == 1:
            mono_count += 1
        if parsed["bitrate"] > 0 and (parsed["bitrate"] // 1000) <= 128:
            low_bitrate_count += 1
        if parsed["sample_rate"] > 0 and parsed["sample_rate"] <= 32000:
            low_samplerate_count += 1
        if parsed["length"] >= 900:  # 15 minutes
            long_track_count += 1

    for g in genres_found:
        if any(sg in g for sg in SPOKEN_GENRES):
            book_score += 5.0
            book_evidence.append(f"spoken-word / audiobook genre ('{g}')")
            break
        if any(mg in g for mg in MUSIC_GENRES):
            music_score += 4.0
            music_evidence.append(f"recognized music genre ('{g}')")
            break

    if has_chapters:
        book_score += 5.0
        book_evidence.append("embedded chapter metadata")

    if has_narrator:
        book_score += 4.0
        book_evidence.append("narrator metadata")

    if has_author:
        book_score += 3.0
        book_evidence.append("author metadata")

    if has_isbn_asin:
        book_score += 4.0
        book_evidence.append("ISBN or ASIN metadata")

    if has_musicbrainz:
        music_score += 5.0
        music_evidence.append("MusicBrainz metadata tags")

    if has_discogs:
        music_score += 5.0
        music_evidence.append("Discogs metadata tags")

    if has_catalog_no:
        music_score += 3.0
        music_evidence.append("music label / catalogue number metadata")

    if mono_count > 0 and mono_count >= len(sample_files) * 0.5:
        book_score += 3.0
        book_evidence.append(f"mono audio ({mono_count}/{len(sample_files)} files)")

    if low_bitrate_count > 0 and low_bitrate_count >= len(sample_files) * 0.5:
        book_score += 2.0
        book_evidence.append(f"low bitrate audio ({low_bitrate_count}/{len(sample_files)} files)")

    if low_samplerate_count > 0 and low_samplerate_count >= len(sample_files) * 0.5:
        book_score += 2.0
        book_evidence.append(f"low sample rate audio ({low_samplerate_count}/{len(sample_files)} files)")

    if long_track_count > 0:
        book_score += 3.0
        book_evidence.append(f"long individual tracks (>15 min) ({long_track_count} files)")

    # C. Decision logic
    if book_score >= 3.0 and book_score > music_score:
        return AudioCategoryResult(
            category="BOOK",
            is_audiobook=True,
            confidence=min(1.0, book_score / 10.0),
            evidence=book_evidence,
        )

    if music_score >= 3.0 and music_score > book_score:
        return AudioCategoryResult(
            category="MUSIC",
            is_audiobook=False,
            confidence=min(1.0, music_score / 10.0),
            evidence=music_evidence,
        )

    return AudioCategoryResult(
        category="AMBIGUOUS",
        is_audiobook=False,
        confidence=0.0,
        evidence=[
            f"shared {audio_files[0].suffix.lower()} extension",
            "no audiobook-specific metadata",
            "no reliable music metadata",
        ],
    )
