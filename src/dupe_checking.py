# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from collections.abc import Callable, MutableMapping, Sequence
from pathlib import Path
from typing import Any, TypedDict, cast

from src.cogs.redaction import Redaction
from src.console import logger
from src.meta import Meta
from src.trackers.UNIT3D.hawkeuno import HawkeUno


class DupeEntry(TypedDict, total=False):
    name: str
    size: int | str | None
    files: list[str]
    file_count: int
    trumpable: bool
    link: str | None
    download: str | None
    flags: list[str]
    id: int | str | None
    type: str | None
    res: str | None
    internal: int | bool
    bd_info: str | None
    description: str | None


type DupeInput = str | DupeEntry | MutableMapping[str, Any]


class AttributeCheck(TypedDict):
    key: str
    uuid_flag: bool
    condition: Callable[[str], bool]
    exclude_msg: Callable[[str], str]


class DupeChecker:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def filter_dupes(self, dupes: Sequence[DupeInput], meta: Meta, tracker_name: str) -> list[DupeEntry]:
        """
        Filter duplicates by applying exclusion rules. Only non-excluded entries are returned.
        Everything is a dupe, until it matches a criteria to be excluded.
        """
        if meta.debug:
            logger.debug(f"[cyan]Pre-filtered dupes from {tracker_name}")
            # Limit dupe output for readability
            if dupes:
                dupes_to_print: list[dict[str, Any]] = []
                for dupe in dupes:
                    if isinstance(dupe, dict) and "files" in dupe and isinstance(dupe["files"], list):
                        # Limit files list to first 10 items
                        limited_dupe = Redaction.redact_private_info(dupe).copy()
                        limited_files = cast(list[str], limited_dupe.get("files", []))
                        if len(limited_files) > 10:
                            dupe_files = cast(list[str], dupe.get("files", []))
                            limited_dupe["files"] = [*limited_files[:10], f"... and {len(dupe_files) - 10} more files"]
                        dupes_to_print.append(limited_dupe)
                    else:
                        dupes_to_print.append(Redaction.redact_private_info(dupe))
                logger.debug(dupes_to_print)
            else:
                logger.debug(dupes)

        meta.trumpable_id = None
        meta.season_pack_exists = False
        meta.season_pack_id = None
        meta.season_pack_link = None
        meta.season_pack_name = ""
        processed_dupes: list[DupeEntry] = []
        for d in dupes:
            if isinstance(d, str):
                # Case 1: Simple string (just name)
                processed_dupes.append(
                    {
                        "name": d,
                        "size": None,
                        "files": [],
                        "file_count": 0,
                        "trumpable": False,
                        "link": None,
                        "download": None,
                        "flags": [],
                        "id": None,
                        "type": None,
                        "res": None,
                        "internal": 0,
                        "bd_info": None,
                        "description": None,
                    }
                )
            elif isinstance(d, dict):
                # Create a base entry with default values
                entry: DupeEntry = {
                    "name": str(d.get("name", "")),
                    "size": d.get("size"),
                    "files": [],
                    "file_count": 0,
                    "trumpable": bool(d.get("trumpable", False)),
                    "link": d.get("link", None),
                    "download": d.get("download", None),
                    "flags": d.get("flags", []),
                    "id": d.get("id", None),
                    "type": d.get("type", None),
                    "res": d.get("res", None),
                    "internal": d.get("internal", 0),
                    "bd_info": d.get("bd_info", ""),
                    "description": d.get("description", ""),
                }

                # Case 3: Dict with files and file_count
                if "files" in d:
                    if isinstance(d["files"], list):
                        entry_files = d["files"]
                        entry["files"] = [str(file) for file in entry_files]
                    elif isinstance(d["files"], str) and d["files"]:
                        entry["files"] = [d["files"]]
                    entry["file_count"] = len(entry["files"])
                if "file_count" in d:
                    try:
                        entry["file_count"] = int(d["file_count"])
                    except ValueError, TypeError:
                        entry["file_count"] = 0

                processed_dupes.append(entry)

        def coerce_int(value: Any) -> int | None:
            try:
                return int(value) if value is not None else None
            except TypeError, ValueError:
                return None

        new_dupes: list[DupeEntry]

        has_repack_in_uuid = "repack" in meta.uuid.lower()
        video_encode_value = meta.video_encode
        video_encode = video_encode_value if video_encode_value else ""
        normalized_encoder = await DupeChecker.normalize_filename(video_encode) if video_encode else ""
        video_encode_lower = video_encode.lower()

        file_size: int | None = None
        if meta.is_disc != "BDMV":
            mediainfo = meta.mediainfo
            tracks = cast(list[dict[str, Any]], mediainfo.get("media", {}).get("track", []))
            if tracks:
                file_size = coerce_int(tracks[0].get("FileSize"))

        has_is_disc = bool(meta.is_disc)
        target_hdr = await DupeChecker.refine_hdr_terms(cast(str | None, meta.hdr))
        target_season = meta.season
        target_episode = meta.episode
        target_resolution = meta.resolution
        tag = "" if not meta.tag else meta.tag.lower().replace("-", " ")
        is_dvd = meta.is_disc == "DVD"
        is_dvdrip = meta.type == "DVDRIP"
        web_dl = meta.type == "WEBDL"
        is_hdtv = meta.type == "HDTV"
        target_source = str(meta.source)
        is_sd = int(meta.sd or 0)
        is_tv_pack = meta.category == "TV" and (coerce_int(meta.tv_pack) or 0) == 1
        target_season_match = re.search(r"[sS](\d+)", str(target_season or ""))
        target_season_number = int(target_season_match.group(1)) if target_season_match else None

        filenames: list[str] = []
        filelist_value = meta.filelist
        filelist: list[str] = []
        if not meta.is_disc:
            if isinstance(filelist_value, Sequence) and not isinstance(filelist_value, (str, bytes)):
                filelist = [str(file_path) for file_path in cast(Sequence[Any], filelist_value)]
                for file_path in filelist:
                    # Extract just the filename without the path
                    filename = Path(file_path).name
                    filenames.append(filename)
            if meta.debug:
                logger.debug(f"dupe checking filenames: {filenames[:10]}{'...' if len(filenames) > 10 else ''}")

        attribute_checks: list[AttributeCheck] = [
            {
                "key": "remux",
                "uuid_flag": "remux" in meta.name.lower(),
                "condition": lambda each: "remux" in each.lower(),
                "exclude_msg": lambda each: f"Excluding result due to 'remux' mismatch: {each}",
            },
            {
                "key": "uhd",
                "uuid_flag": "uhd" in meta.name.lower(),
                "condition": lambda each: "uhd" in each.lower(),
                "exclude_msg": lambda each: f"Excluding result due to 'UHD' mismatch: {each}",
            },
        ]

        from src.trackersetup import tracker_class_map

        tracker_cls = tracker_class_map.get(tracker_name.upper())
        # Usenet releases may include optional PAR2 recovery files, so their
        # reported size can differ even when the payload files are identical.
        # Torrent releases do not have this packaging difference, so retain
        # the size check for them.
        is_usenet = bool(getattr(tracker_cls, "is_usenet", False))
        tracker_config = self.config.get("TRACKERS", {}).get(tracker_name.upper(), {})
        supports_exact_match_only = hasattr(tracker_cls, "exact_match_only")
        has_configured_exact_match_only = isinstance(tracker_config, dict) and "exact_match_only" in tracker_config
        configured_exact_match_only = tracker_config.get("exact_match_only") if has_configured_exact_match_only else None
        if has_configured_exact_match_only and not supports_exact_match_only:
            logger.warning(
                f"{tracker_name}: 'exact_match_only' is not supported by this tracker and will be ignored.",
                extra={"markup": False},
            )
        is_exact_match_only = (
            configured_exact_match_only
            if supports_exact_match_only and isinstance(configured_exact_match_only, bool)
            else bool(getattr(tracker_cls, "exact_match_only", False))
        )

        async def log_exclusion(reason: str, item: str) -> None:
            if meta.debug:
                logger.debug(f"[yellow]Excluding result due to {reason}: {item}")

        async def process_exclusion(entry: DupeEntry) -> bool:
            """
            Determine if an entry should be excluded.
            Returns True if the entry should be excluded, otherwise allowed as dupe.
            """
            each = entry.get("name", "")
            sized = entry.get("size")  # This may come as a string, such as "1.5 GB"

            if is_exact_match_only:
                is_exact = await DupeChecker.is_exact_match(entry, meta, ignore_size=is_usenet)
                if not is_exact:
                    await log_exclusion("non-exact release (allowed on exact-match-only tracker)", each)
                    return True
                return False

            # Check dupe size difference tolerance
            tolerance = meta.dupe_size_difference_tolerance
            if tolerance is None:
                tolerance = self.config.get("DEFAULT", {}).get("dupe_size_difference_tolerance")

            if tolerance is not None:
                try:
                    tolerance_val = float(tolerance)
                    upload_size = meta.source_size
                    dupe_size_raw = entry.get("size")
                    if upload_size and upload_size > 0 and dupe_size_raw is not None:
                        from src.uphelper import parse_size_to_bytes

                        dupe_size = parse_size_to_bytes(dupe_size_raw)
                        if dupe_size and dupe_size > 0:
                            diff_pct = (abs(dupe_size - upload_size) / upload_size) * 100
                            if diff_pct >= tolerance_val:
                                await log_exclusion(f"size difference ({diff_pct:.2f}%) exceeding tolerance ({tolerance_val}%)", each)
                                return True
                except Exception as e:
                    logger.debug(f"[debug] Error in dupe size tolerance check: {e}")

            files_value = cast(list[Any], entry.get("files") or [])
            files = [str(file) for file in files_value]

            # Handle case where files might be comma-separated strings in a list
            if files and len(files) == 1 and "," in files[0]:
                # Split comma-separated string into individual filenames
                files = [f.strip() for f in files[0].split(",")]

            file_count_raw = entry.get("file_count", 0)
            file_count = coerce_int(file_count_raw) or 0
            normalized = await DupeChecker.normalize_filename(each)
            type_id = entry.get("type", None)
            res_id = entry.get("res", None)

            # Use flags field if available for more accurate HDR detection
            flags_value = cast(list[Any], entry.get("flags") or [])
            flags = [str(flag) for flag in flags_value]

            if flags:
                # If flags are provided, use them directly for HDR information
                file_hdr: set[str] = set()
                for flag in flags:
                    flag_upper = flag.upper()
                    if flag_upper == "DV":
                        file_hdr.add("DV")
                    elif flag_upper in ["HDR", "HDR10", "HDR10+"]:
                        file_hdr.add("HDR")
                logger.debug(f"[debug] Using flags for HDR detection: {flags} -> {file_hdr}")
            else:
                # Fall back to parsing filename for HDR terms
                file_hdr = await DupeChecker.refine_hdr_terms(normalized)

            if meta.debug:
                logger.debug(f"[debug] Evaluating dupe: {each}")
                logger.debug(f"[debug] Normalized dupe: {normalized}")
                logger.debug(f"[debug] Target resolution: {target_resolution}")
                logger.debug(f"[debug] Target source: {target_source}")
                logger.debug(f"[debug] File HDR terms: {file_hdr}")
                logger.debug(f"[debug] Flags: {flags}")
                logger.debug(f"[debug] Target HDR terms: {target_hdr}")
                logger.debug(f"[debug] Target Season: {target_season}")
                logger.debug(f"[debug] Target Episode: {target_episode}")
                logger.debug(f"[debug] TAG: {tag}")
                logger.debug("[debug] Evaluating repack condition:")
                logger.debug(f"  has_repack_in_uuid: {has_repack_in_uuid}")
                logger.debug(f"  'repack' in each.lower(): {'repack' in each.lower()}")
                logger.debug(f"[debug] meta.uuid: {meta.uuid}")
                logger.debug(f"[debug] normalized encoder: {normalized_encoder}")
                logger.debug(f"[debug] type_id: {type_id}, res_id: {res_id}")
                logger.debug(f"[debug] link: {entry.get('link', None)}")
                logger.debug(f"[debug] files: {files[:10]}{'...' if len(files) > 10 else ''}")
                logger.debug(f"[debug] file_count: {file_count}")

            def remember_match(reason: str) -> None:
                """Persist details about the dupe that triggered a match for later use."""
                matched_name_key = f"{tracker_name}_matched_name"
                matched_link_key = f"{tracker_name}_matched_link"
                matched_download_key = f"{tracker_name}_matched_download"
                matched_reason_key = f"{tracker_name}_matched_reason"
                matched_count_key = f"{tracker_name}_matched_file_count"
                matched_torrent_id = f"{tracker_name}_matched_id"

                meta[matched_name_key] = entry.get("name")
                if entry.get("link"):
                    meta[matched_link_key] = entry.get("link")
                if entry.get("download"):
                    meta[matched_download_key] = entry.get("download")
                meta[matched_reason_key] = reason
                if file_count:
                    meta[matched_count_key] = file_count
                if entry.get("id"):
                    meta[matched_torrent_id] = entry.get("id")

            if meta.category == "GAME":
                target_title = meta.title or meta.name
                if not target_title.strip():
                    await log_exclusion("empty target game title", each)
                    return True

                def get_platform_category(p: str) -> str:
                    p_lower = p.lower()
                    nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()
                    if any(w in p_lower for w in ["playstation", "ps5", "ps4", "ps3", "ps2", "ps1", "psp", "vita"]):
                        return "playstation"
                    if "xbox" in p_lower:
                        return "xbox"
                    if any(w in p_lower for w in [f"{nin_term}", "switch", "wii", "3ds", "nds", "ds"]):
                        return nin_term
                    return "pc"

                target_platform = get_platform_category(meta.platform)
                dupe_platform = get_platform_category(str(entry.get("type", "")))
                if target_platform != dupe_platform:
                    await log_exclusion(f"game platform mismatch (expected {target_platform}, got {dupe_platform})", each)
                    return True

                # Clean game title helper
                def clean_game_title(name: str) -> str:
                    name = name.lower()

                    # Remove trailing group/tag if there is a hyphen
                    if "-" in name:
                        parts = name.split("-")
                        if len(parts) > 1:
                            last_part = parts[-1].strip()
                            if len(last_part) < 15 and " " not in last_part:
                                name = "-".join(parts[:-1])

                    # Remove versions/builds/updates (like v1.0.4, v2026.06.07, etc.)
                    name = re.sub(r"(?i)\b(?:update|patch|build|version|ver|v)\b[.:=\-_\s]*\d+[\d._-]*", "", name)
                    name = re.sub(r"(?i)\bv\d+[\d._-]*\b", "", name)

                    # Remove isolated version-like numbers (e.g., 1.15, 1.0.4)
                    name = re.sub(r"\b\d+(?:\.\d+)+\b", "", name)

                    # Remove years: 4-digit numbers between 1900 and 2100
                    name = re.sub(r"\b(19|20)\d{2}\b", "", name)

                    # Remove common platform names
                    nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()
                    platforms = [
                        "pc",
                        "windows",
                        "win",
                        "mac",
                        "osx",
                        "linux",
                        "ps1",
                        "ps2",
                        "ps3",
                        "ps4",
                        "ps5",
                        "playstation",
                        "xbox",
                        "x360",
                        "xone",
                        "xsx",
                        "switch",
                        "nsw",
                        f"{nin_term}",
                    ]
                    for p in platforms:
                        name = re.sub(rf"\b{p}\b", "", name)

                    # Remove common store / distribution / formatting keywords
                    keywords = ["gog", "steam", "epic", "multi", "multilang", "repack", "iso", "zip", "rar", "setup", "download", "cracked", "crack"]
                    for kw in keywords:
                        name = re.sub(rf"\b{kw}\b", "", name)

                    # Replace dots, underscores, brackets, parentheses with spaces
                    name = re.sub(r"[._\[\]()\-:+]", " ", name)

                    # Collapse multiple spaces and strip
                    return re.sub(r"\s+", " ", name).strip()

                clean_target = clean_game_title(target_title)
                clean_each = clean_game_title(each)

                logger.debug(f"[debug] Game title comparison: Target='{clean_target}' vs Dupe='{clean_each}'")

                is_match = False
                if (
                    clean_target == clean_each
                    or (clean_target and clean_each and re.search(rf"\b{re.escape(clean_target)}\b", clean_each))
                    or re.search(rf"\b{re.escape(clean_each)}\b", clean_target)
                ):
                    is_match = True

                if not is_match:
                    await log_exclusion("game title mismatch", each)
                    return True

                # Title match! It is a duplicate.
                remember_match("title")
                logger.debug(f"[cyan]Game duplicate matched: {each}")
                return False

            if meta.category == "BOOK":
                import unicodedata

                target_title = meta.title or meta.name
                if not target_title.strip():
                    await log_exclusion("empty target book title", each)
                    return True

                # Clean book title helper
                def clean_book_title(t: str) -> str:
                    normalized = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("utf-8").lower()
                    # Remove common book/audiobook extensions at the end of the string
                    normalized = re.sub(r"\.(pdf|epub|mobi|azw3|kfx|cbz|cbr|mp3|m4b|flac|aac|m4a|ogg|wav)$", "", normalized)
                    # Replace dots, underscores, brackets, parentheses with spaces to avoid squishing words
                    normalized = re.sub(r"[._\[\]()]", " ", normalized)
                    # Replace hyphens with spaces only if they are not surrounded by spaces
                    normalized = re.sub(r"(?<!\s)-(?!\s)", " ", normalized)
                    cleaned = re.sub(r"[^a-z0-9\s\-:]", "", normalized)
                    return cleaned.strip()

                # Get main title candidates
                def get_main_title_candidates(cleaned_t: str) -> list[str]:
                    parts = re.split(r"[:]|\s+-\s+|\s+by\s+", cleaned_t)
                    candidates = []
                    for p in parts:
                        p_clean = re.sub(r"[^a-z0-9\s]", "", p)
                        p_clean = re.sub(r"\s+", " ", p_clean).strip()
                        if len(p_clean) >= 2:
                            candidates.append(p_clean)
                    return candidates

                clean_target = clean_book_title(target_title)
                clean_each = clean_book_title(each)

                norm_target = re.sub(r"[^a-z0-9\s]", "", clean_target)
                norm_target = re.sub(r"\s+", " ", norm_target).strip()

                norm_each_str = re.sub(r"[^a-z0-9\s]", "", clean_each)
                norm_each_str = re.sub(r"\s+", " ", norm_each_str).strip()

                is_title_match = False
                if norm_target == norm_each_str:
                    is_title_match = True
                else:
                    target_candidates = get_main_title_candidates(clean_target)
                    dupe_candidates = get_main_title_candidates(clean_each)

                    if target_candidates and dupe_candidates:
                        target_main = target_candidates[0]
                        dupe_main = dupe_candidates[0]

                        if (target_main == dupe_main) or re.search(rf"\b{re.escape(target_main)}\b", norm_each_str) or re.search(rf"\b{re.escape(dupe_main)}\b", norm_target):
                            is_title_match = True

                if not is_title_match:
                    await log_exclusion("book title mismatch", each)
                    return True

                # Check format/type compatibility
                target_is_audiobook = meta.audiobook

                dupe_type = (entry.get("type") or "").lower()
                audiobook_types = {"audiobook", "mp3", "flac", "m4b", "m4a", "wav", "ogg", "aac", "ac3", "wma", "opus"}
                dupe_is_audiobook = (
                    (dupe_type in audiobook_types)
                    or ("audiobook" in each.lower())
                    or ("audio book" in each.lower())
                    or any(re.search(rf"\b{re.escape(t)}\b", each.lower()) for t in audiobook_types)
                )

                if target_is_audiobook != dupe_is_audiobook:
                    await log_exclusion("book format type mismatch (audiobook vs ebook)", each)
                    return True

                if not target_is_audiobook:
                    # Compare ebook formats (e.g. EPUB vs PDF)
                    target_type = (meta.type or "").lower()

                    # Check if formats match either by type_id/dupe_type or file extension
                    format_match = target_type == dupe_type
                    if not format_match and files:
                        format_match = any(f.lower().endswith(f".{target_type}") for f in files)
                    if not format_match:
                        # Fallback: check if the target format is in the torrent name (extension or word)
                        each_lower = each.lower()
                        if each_lower.endswith(f".{target_type}") or re.search(rf"\b{re.escape(target_type)}\b", each_lower):
                            format_match = True

                    if not format_match:
                        if tracker_name == "CAPYBARABR":
                            logger.debug("[debug] CAPYBARABR allows only one ebook format per book, so different formats are considered duplicates.")
                        else:
                            await log_exclusion(f"book format type mismatch (expected {target_type})", each)
                            return True

                # Check for exact file/filename match for cross-seeding
                if not meta.is_disc and filenames and files:
                    for file in filenames:
                        if any(file.lower() == f.lower() for f in files):
                            meta.filename_match = f"{entry.get('name')} = {entry.get('link', None)}"
                            logger.debug(f"[debug] Book filename match found: {meta.filename_match}")
                            remember_match("filename")
                            remember_match("id")
                            if file_count and file_count == len(filelist):
                                meta.file_count_match = file_count
                                logger.debug(f"[debug] Book file count match found: {meta.file_count_match}")
                                remember_match("file_count")
                                break

                # Title and format match! It is a duplicate.
                remember_match("title")
                logger.debug(f"[cyan]Book duplicate matched: {each}")
                return False

            # AITHER-specific trumping logic - no internal checking, if it's marked trumpable, it's trumpable
            if tracker_name in ["AITHER", "LST"] and entry.get("trumpable", False) and res_id and target_resolution == res_id:
                meta.trumpable_id = entry.get("id")
                remember_match("trumpable_id")

            if not meta.is_disc:
                for file in filenames:
                    if tracker_name in ["ALPHARATIO", "RETROFLIX"]:
                        if any(f.lower() in file.lower() for f in files):
                            meta.filename_match = f"{entry.get('name')} = {entry.get('link', None)}"
                            remember_match("filename")
                            if file_count and file_count == len(filelist):
                                meta.file_count_match = file_count
                                remember_match("file_count")
                                return False
                        entry_size = coerce_int(entry.get("size"))
                        source_size = coerce_int(meta.source_size)
                        if entry_size is not None and source_size is not None and entry_size == source_size:
                            meta.size_match = f"{entry.get('name')} = {entry.get('link', None)}"
                            remember_match("size")
                            return False
                        if meta.debug and entry_size is None and meta.source_size is not None:
                            logger.debug(f"[debug] Size comparison failed due to ValueError: entry_size={entry.get('size')}, source_size={meta.source_size}")
                    else:
                        logger.debug(f"[debug] Comparing file: {file} against dupe files list.")
                        logger.debug(f"[debug] Dupe files list: {files[:10]}{'...' if len(files) > 10 else ''}")
                        if any(file.lower() == f.lower() for f in files):
                            meta.filename_match = f"{entry.get('name')} = {entry.get('link', None)}"
                            logger.debug(f"[debug] Filename match found: {meta.filename_match}")
                            remember_match("filename")
                            remember_match("id")
                            if file_count and file_count == len(filelist):
                                meta.file_count_match = file_count
                                logger.debug(f"[debug] File count match found: {meta.file_count_match}")
                                remember_match("file_count")
                                return False
                if tracker_name in ["BEYONDHD"]:
                    # BEYONDHD: compare sizes
                    entry_size = coerce_int(entry.get("size"))
                    source_size = coerce_int(meta.source_size)
                    if entry_size is not None and source_size is not None:
                        logger.debug(f"[debug] Comparing sizes: Entry size {entry_size} vs Source size {source_size}")
                        if entry_size == source_size:
                            meta.size_match = f"{entry.get('name')} = {entry.get('link', None)}"
                            remember_match("size")
                            return False
                    elif meta.debug and entry_size is None and meta.source_size is not None:
                        logger.debug(f"[debug] Size comparison failed due to ValueError: entry_size={entry.get('size')}, source_size={meta.source_size}")

            else:
                entry_size = coerce_int(entry.get("size"))
                source_size = coerce_int(meta.source_size)
                if entry_size is not None and source_size is not None:
                    logger.debug(f"[debug] Comparing sizes: Entry size {entry_size} vs Source size {source_size}")
                    if entry_size == source_size:
                        meta.size_match = f"{entry.get('name')} = {entry.get('link', None)}"
                        remember_match("size")
                        return False
                elif meta.debug and entry_size is None and meta.source_size is not None:
                    logger.debug(f"[debug] Size comparison failed due to ValueError: entry_size={entry.get('size')}, source_size={meta.source_size}")

            if meta.is_disc and file_count and file_count < 2:
                await log_exclusion("file count less than 2 for disc upload", each)
                return True

            if has_repack_in_uuid and "repack" not in normalized and meta.tag and meta.tag.lower() in normalized:
                await log_exclusion("repack release", each)
                return True

            if tracker_name == "BEYONDHD":
                target_name = meta.name.replace("DD+", "DDP")
                if str(entry.get("name")) == target_name:
                    meta.filename_match = f"{entry.get('name')} = {entry.get('link', None)}"
                    return False

            if tracker_name == "HAWKEUNO":
                huno = HawkeUno(config=self.config)
                huno_name_result: Any = await huno.get_name(meta)
                huno_name_map = cast(dict[str, Any], huno_name_result)
                huno_name = str(huno_name_map.get("name", huno_name_result)) if isinstance(huno_name_result, dict) else str(huno_name_result)
                if str(entry.get("name")) == huno_name:
                    meta.filename_match = f"{entry.get('name')} = {entry.get('link', None)}"
                    return False

            if tracker_name in ["BEYONDHD", "RETROFLIX", "ALPHARATIO"] and (
                ("2160p" in target_resolution and "2160p" in each) and ("framestor" in each.lower() or "framestor" in meta.uuid.lower())
            ):
                return False

            if has_is_disc and each.lower().endswith(".m2ts"):
                return False

            if has_is_disc and re.search(r"\.\w{2,4}$", each):
                await log_exclusion("file extension mismatch (is_disc=True)", each)
                return True

            if is_sd == 1 and tracker_name in {"BEYONDHD", "AITHER"} and any(str(res) in each for res in [1080, 720, 2160]) and not has_is_disc:
                return False

            if target_hdr and "1080p" in target_resolution and "2160p" in each:
                await log_exclusion("No 1080p HDR when 4K exists", each)
                return False

            if tracker_name in ["AITHER", "LST"] and is_dvd:
                if len(each) >= 1 and tag == "":
                    return False
                return not (tag.strip() and tag.strip() in normalized)

            if web_dl:
                if "hdtv" in normalized and not any(web_term in normalized for web_term in ["web-dl", "web -dl", "webdl", "web dl"]):
                    await log_exclusion("source mismatch: WEB-DL vs HDTV", each)
                    return True
                if any(term in normalized for term in ["blu-ray", "blu ray", "bluray", "blu -ray"]) and not any(
                    web_term in normalized for web_term in ["web-dl", "web -dl", "webdl", "web dl"]
                ):
                    await log_exclusion("source mismatch: WEB-DL vs BluRay", each)
                    return True
            if not web_dl and any(web_term in normalized for web_term in ["web-dl", "web -dl", "webdl", "web dl"]):
                await log_exclusion("source mismatch: non-WEB-DL vs WEB-DL", each)
                return True

            skip_resolution_check = is_dvd or "DVD" in target_source or is_dvdrip

            if tracker_name == "OLDTOONSWORLD" and not is_tv_pack and meta.category == "TV" and target_episode and target_resolution:
                dupe_season_match = re.search(r"[sS](\d+)", each)
                dupe_has_episode = bool(re.search(r"[eE]\d{2}", each))
                same_season_episode_dupe = (
                    target_season_number is not None and dupe_season_match is not None and int(dupe_season_match.group(1)) == target_season_number and dupe_has_episode
                )

                if same_season_episode_dupe and (target_resolution.lower() not in each.lower()):
                    await log_exclusion(f"OLDTOONSWORLD same-season episode resolution mismatch: expected '{target_resolution}'", each)
                    return False

            if not skip_resolution_check:
                if target_resolution and target_resolution not in each:
                    await log_exclusion(f"resolution '{target_resolution}' mismatch", each)
                    return True
                if not await DupeChecker.has_matching_hdr(file_hdr, target_hdr, meta, tracker=tracker_name):
                    await log_exclusion(f"HDR mismatch: Expected {target_hdr}, got {file_hdr}", each)
                    return True

            if is_dvd and tracker_name != "BEYONDHD" and any(str(res) in each for res in [1080, 720, 2160]):
                await log_exclusion(f"resolution '{target_resolution}' mismatch", each)
                return False

            for check in attribute_checks:
                if check["key"] == "repack":
                    if has_repack_in_uuid and "repack" not in normalized and tag and tag in normalized:
                        await log_exclusion("missing 'repack'", each)
                        return True
                elif check["key"] == "remux":
                    # Bidirectional check: if your upload is a REMUX, dupe must be REMUX
                    # If your upload is NOT a REMUX (i.e., an encode), dupe must NOT be a REMUX
                    uuid_has_remux = check["uuid_flag"]
                    dupe_has_remux = check["condition"](normalized)

                    logger.debug(f"[debug] Remux check: uuid_has_remux={uuid_has_remux}, dupe_has_remux={dupe_has_remux}")

                    if uuid_has_remux and not dupe_has_remux:
                        await log_exclusion("missing 'remux'", each)
                        return True
                    if not uuid_has_remux and dupe_has_remux:
                        await log_exclusion("dupe is remux but upload is not", each)
                        return True

            if meta.category == "TV":
                season_episode_match, is_season = await DupeChecker.is_season_episode_match(normalized, target_season, target_episode)
                logger.debug(f"[debug] Season/Episode match result: {season_episode_match}")
                logger.debug(f"[debug] is_season: {is_season}")
                # AITHER episode trumping logic
                if is_season and tracker_name in ["AITHER", "LST"]:
                    # Null-safe normalization for comparisons
                    target_source_lower = (target_source or "").lower()
                    type_id_lower = (type_id or "").lower()
                    res_id_safe = res_id or ""
                    target_resolution_safe = target_resolution or ""

                    if type_id_lower and res_id_safe:
                        logger.debug(
                            f"[debug] Checking trumping: target_source='{target_source_lower}', type_id='{type_id_lower}', target_res='{target_resolution_safe}', res_id='{res_id_safe}'"
                        )
                        if target_source_lower in type_id_lower and target_resolution_safe == res_id_safe:
                            logger.debug(f"[debug] Episode with matching source and resolution found for trumping: {each}")

                            is_internal = False
                            if entry.get("internal", 0) == 1:
                                trackers_section: dict[str, Any] = cast(dict[str, Any], self.config.get("TRACKERS", {}))
                                aither_settings: dict[str, Any] = trackers_section.get("AITHER", {})
                                if aither_settings.get("internal") is True:
                                    internal_groups = aither_settings.get("internal_groups", [])
                                    if isinstance(internal_groups, list):
                                        tag_without_prefix = tag[1:] if tag else ""
                                        if tag_without_prefix in internal_groups and tag_without_prefix.lower() in normalized:
                                            is_internal = True
                                if not is_internal and meta.debug:
                                    logger.debug("[debug] Skipping internal episode for trumping since you're not the internal uploader.")

                            if not entry.get("internal", False) or is_internal:
                                # Store the matched episode ID/s for later use
                                # is_season=True means seasons match, which is sufficient for trump targeting
                                # (season pack can trump individual episodes from same season)
                                matched_episode_ids = cast(list[dict[str, Any]], meta.setdefault(f"{tracker_name}_matched_episode_ids", []))

                                entry_id = entry.get("id")
                                entry_link = entry.get("link")

                                # De-duplication guard: check if this entry already exists
                                already_exists = (
                                    any(
                                        existing.get("id") == entry_id or (existing.get("link") == entry_link and existing.get("tracker") == tracker_name)
                                        for existing in matched_episode_ids
                                    )
                                    if entry_id or entry_link
                                    else False
                                )

                                if entry_id and not already_exists:
                                    matched_episode_ids.append(
                                        {
                                            "id": entry_id,
                                            "name": each,
                                            "link": entry_link,
                                            "tracker": tracker_name,
                                            "internal": entry.get("internal", 0),
                                        }
                                    )
                                    logger.debug(f"[debug] Added episode ID {entry_id} to matched list")
                                    # Ensure this matched dupe is recorded for later use
                                    remember_match("season_pack_contains_episode")
                                    # Don't exclude this entry - it's a valid trump target
                                    return False
                                if already_exists and meta.debug:
                                    logger.debug(f"[debug] Skipping duplicate entry for episode ID {entry_id}")

                # Normal season/episode matching
                if not season_episode_match:
                    await log_exclusion("season/episode mismatch", each)
                    return True

                # Check if uploading an episode but a matching season pack exists
                if is_season and target_episode:
                    # We're uploading an episode and found a matching season pack
                    meta.season_pack_exists = True
                    meta.season_pack_name = each
                    meta.season_pack_link = entry.get("link")
                    meta.season_pack_id = entry.get("id")
                    logger.debug(f"[yellow]Season pack detected for episode upload: {each}")
                    logger.debug(f"[yellow]Your episode {target_season}{target_episode} is contained in existing season pack")
                    remember_match("season_pack_contains_episode")
                    return False

            if is_hdtv and any(web_term in normalized for web_term in ["web-dl", "web -dl", "webdl", "web dl"]):
                return False

            if (
                len(dupes) == 1
                and meta.is_disc != "BDMV"
                and tracker_name in ["AITHER", "BEYONDHD", "HAWKEUNO", "ONLYENCODES", "ULCX"]
                and file_size is not None
                and "1080" in target_resolution
                and "x264" in video_encode_lower
            ):
                target_size = file_size
                dupe_size = coerce_int(sized)

                if dupe_size is not None and dupe_size != 0:
                    size_difference = (target_size - dupe_size) / dupe_size
                    logger.debug(f"Your size: {target_size}, Dupe size: {dupe_size}, Size difference: {size_difference:.4f}")
                    if size_difference >= 0.20:
                        await log_exclusion(f"Your file is significantly larger ({size_difference * 100:.2f}%)", each)
                        return True
            if len(dupes) == 1 and meta.is_disc != "BDMV" and tracker_name == "REELFLIX":
                if tag.strip() and tag.strip() in normalized:
                    return False
                if tag.strip() and tag.strip() not in normalized:
                    await log_exclusion(f"Tag '{tag}' not found in normalized name", each)
                    return True

            if meta.debug:
                logger.debug(f"[cyan]Release PASSED all checks: {each}")
            return False

        new_dupes = [each for each in processed_dupes if not await process_exclusion(each)]

        if is_exact_match_only:
            if processed_dupes and not new_dupes:
                logger.info(f"{tracker_name}: related releases found, but no exact renamed release was detected.")
                logger.info(f"{tracker_name}: continuing upload.")
            elif new_dupes:
                logger.info(f"{tracker_name}: exact existing release detected from matching files and size.")

        if new_dupes and not meta.unattended and meta.debug:
            if len(processed_dupes) > 1:
                logger.debug(f"[yellow]Filtered dupes on {tracker_name}: ")
            # Limit filtered dupe output for readability
            filtered_dupes_to_print: list[dict[str, Any]] = []

            for dupe in new_dupes:
                limited_dupe = Redaction.redact_private_info(dupe).copy()
                # Limit files list to first 10 items
                limited_files = limited_dupe.get("files", [])
                if len(limited_files) > 10:
                    dupe_files = dupe.get("files", [])
                    limited_dupe["files"] = [*limited_files[:10], f"... and {len(dupe_files) - 10} more files"]

                if isinstance(limited_dupe.get("description"), str) and len(limited_dupe["description"]) > 200:
                    limited_dupe["description"] = limited_dupe["description"][:200] + "..."

                filtered_dupes_to_print.append(limited_dupe)

            if len(processed_dupes) > 1:
                logger.debug(filtered_dupes_to_print)

        return new_dupes

    @staticmethod
    async def is_exact_match(candidate: dict[str, Any] | DupeEntry, meta: Meta, *, ignore_size: bool = False) -> bool:
        """Check whether a candidate is an exact (possibly renamed) release of the local upload."""
        from pathlib import Path

        from src.uphelper import parse_size_to_bytes

        # 1. Local files and file count
        local_files: list[str] = []
        if meta.filelist and not meta.is_disc:
            local_files = [Path(str(f)).name.lower() for f in meta.filelist if f]

        # 2. Local total size
        local_size = parse_size_to_bytes(meta.source_size)
        if local_size is None and not meta.is_disc and meta.mediainfo:
            tracks = meta.mediainfo.get("media", {}).get("track", [])
            if tracks and isinstance(tracks, list) and len(tracks) > 0:
                local_size = parse_size_to_bytes(tracks[0].get("FileSize"))

        # 3. Candidate files and file count
        candidate_files: list[str] = []
        raw_files = candidate.get("files", [])
        if isinstance(raw_files, list):
            candidate_files = [Path(str(f)).name.lower() for f in raw_files if f]
        elif isinstance(raw_files, str) and raw_files:
            candidate_files = [Path(f.strip()).name.lower() for f in raw_files.split(",") if f.strip()]

        candidate_file_count_raw = candidate.get("file_count")
        try:
            candidate_file_count = int(candidate_file_count_raw) if candidate_file_count_raw is not None else len(candidate_files)
        except ValueError, TypeError:
            candidate_file_count = len(candidate_files)

        local_file_count = len(local_files) if local_files else None

        # 4. Candidate total size
        candidate_size = parse_size_to_bytes(candidate.get("size"))

        # Comparison flags
        files_match = bool(local_files and candidate_files and sorted(local_files) == sorted(candidate_files))
        same_file_count = local_file_count is not None and candidate_file_count > 0 and local_file_count == candidate_file_count
        same_size = local_size is not None and candidate_size is not None and local_size == candidate_size
        size_match = ignore_size or same_size

        # 5. Check if both have file lists
        if local_files and candidate_files:
            return files_match and size_match

        # 6. If file list unavailable for one or both (e.g. disc release)
        if not ignore_size and size_match and same_file_count:
            return True

        # Disc releases have no reliable local file count, so compare their
        # total size when neither side provides a file list.
        if not ignore_size and not local_files and not candidate_files and size_match:
            return True

        # 7. Exact name match fallback
        candidate_name = str(candidate.get("name", "")).strip().lower()
        local_name = str(meta.name or "").strip().lower()
        return bool(candidate_name and local_name and candidate_name == local_name and (size_match or local_size is None or candidate_size is None))

    @staticmethod
    async def normalize_filename(filename: str | MutableMapping[str, Any]) -> str:
        if isinstance(filename, dict):
            filename = str(filename.get("name", ""))
        if not isinstance(filename, str):
            raise ValueError(f"Expected a string or a dictionary with a 'name' key, but got: {type(filename)}")
        return filename.lower().replace("-", " -").replace(" ", " ").replace(".", " ")

    @staticmethod
    async def is_season_episode_match(
        filename: str,
        target_season: str | int | None,
        target_episode: str | int | None,
    ) -> tuple[bool, bool]:
        """
        Check if the filename matches the given season and episode.
        """
        season_match = re.search(r"[sS](\d+)", str(target_season))
        target_season_value = int(season_match.group(1)) if season_match else None

        # Handle daily-style episodes where the episode value is a date (YYYY-MM-DD / YYYY.MM.DD).
        target_episode_str = str(target_episode or "")
        date_match = re.search(r"(?<!\d)((?:19|20)\d{2})[.\-_/\s](\d{1,2})[.\-_/\s](\d{1,2})(?!\d)", target_episode_str)
        if date_match:
            year = int(date_match.group(1))
            month = int(date_match.group(2))
            day = int(date_match.group(3))
            daily_date_pattern = rf"(?<!\d){year}[.\-_/\s]?{month:02d}[.\-_/\s]?{day:02d}(?!\d)"
            if re.search(daily_date_pattern, filename, re.IGNORECASE):
                return (True, False)
            return (False, False)

        if target_episode:
            episode_matches = re.findall(r"\d+", str(target_episode))
            target_episodes = [int(ep) for ep in episode_matches]
        else:
            target_episodes = []

        season_pattern = rf"[sS]{target_season_value:02}" if target_season_value is not None else None
        episode_patterns = [rf"[eE]{ep:02}" for ep in target_episodes] if target_episodes else []

        # Determine if filename represents a season pack (no explicit episode pattern)
        is_season_pack = not re.search(r"[eE]\d{2}", filename, re.IGNORECASE)

        # If `target_episode` is empty, match only season packs
        if not target_episodes:
            season_matches = bool(season_pattern and re.search(season_pattern, filename, re.IGNORECASE))
            return (season_matches and is_season_pack, season_matches)

        # If `target_episode` is provided, match both season packs and episode files
        if season_pattern:
            if is_season_pack:
                return (bool(re.search(season_pattern, filename, re.IGNORECASE)), True)  # Match season pack
            if episode_patterns:
                return (
                    bool(re.search(season_pattern, filename, re.IGNORECASE)) and any(re.search(ep, filename, re.IGNORECASE) for ep in episode_patterns),
                    False,
                )  # Match episode file

        return (False, False)  # No match

    @staticmethod
    async def refine_hdr_terms(hdr: str | None) -> set[str]:
        """
        Normalize HDR terms for consistent comparison.
        Simplifies all HDR entries to 'HDR' and DV entries to 'DV'.
        """
        if hdr is None:
            return set()
        hdr_upper = hdr.upper()
        terms: set[str] = set()
        if "DV" in hdr_upper or "DOVI" in hdr_upper:
            terms.add("DV")
        if "HDR" in hdr_upper:  # Any HDR-related term is normalized to 'HDR'
            terms.add("HDR")
        return terms

    @staticmethod
    async def has_matching_hdr(file_hdr: set[str], target_hdr: set[str], meta: Meta, tracker: str | None = None) -> bool:
        """
        Check if the HDR terms match or are compatible.
        """

        def simplify_hdr(hdr_set: set[str], tracker_name: str | None = None) -> set[str]:
            """Simplify HDR terms to just HDR and DV."""
            simplified: set[str] = set()
            if any(h in hdr_set for h in {"HDR", "HDR10", "HDR10+"}):
                simplified.add("HDR")
            if any(h == "DV" or "DV" in h for h in hdr_set):
                simplified.add("DV")
                meta_type = str(meta.type).lower()
                if "web" not in meta_type:
                    simplified.add("HDR")
                if tracker_name == "ANTHELION":
                    simplified.add("HDR")
            return simplified

        file_hdr_simple = simplify_hdr(file_hdr, tracker)
        target_hdr_simple = simplify_hdr(target_hdr, tracker)

        if file_hdr_simple in [{"DV", "HDR"}, {"HDR", "DV"}]:
            file_hdr_simple = {"HDR"}
            if target_hdr_simple in [{"DV", "HDR"}, {"HDR", "DV"}]:
                target_hdr_simple = {"HDR"}

        return file_hdr_simple == target_hdr_simple


async def filter_dupes(dupes: Sequence[DupeInput], meta: Meta, tracker_name: str, config: dict[str, Any]) -> list[DupeEntry]:
    return await DupeChecker(config).filter_dupes(dupes, meta, tracker_name)


async def normalize_filename(filename: str | MutableMapping[str, Any]) -> str:
    return await DupeChecker.normalize_filename(filename)


async def is_season_episode_match(
    filename: str,
    target_season: str | int | None,
    target_episode: str | int | None,
) -> tuple[bool, bool]:
    return await DupeChecker.is_season_episode_match(filename, target_season, target_episode)


async def refine_hdr_terms(hdr: str | None) -> set[str]:
    return await DupeChecker.refine_hdr_terms(hdr)


async def has_matching_hdr(
    file_hdr: set[str],
    target_hdr: set[str],
    meta: Meta,
    tracker: str | None = None,
) -> bool:
    return await DupeChecker.has_matching_hdr(file_hdr, target_hdr, meta, tracker=tracker)
