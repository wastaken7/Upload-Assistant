# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from __future__ import annotations

import argparse
import datetime
import re
import sys
import urllib.parse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

import argcomplete

from src.app_paths import DATA_DIR

if TYPE_CHECKING:
    from src.meta import Meta

MUSIC_MEDIA_CHOICES = ("cd", "web", "vinyl", "dvd", "bd", "soundboard", "sacd", "dat", "cassette")
MUSIC_RELEASE_TYPE_CHOICES = (
    "album",
    "soundtrack",
    "ep",
    "anthology",
    "compilation",
    "sampler",
    "single",
    "demo",
    "live album",
    "split",
    "remix",
    "bootleg",
    "interview",
    "mixtape",
    "concert recording",
    "dj mix",
    "unknown",
)

PATHS_FROM_STDIN_OPTION = "--paths-from-stdin"
TRACKER_CONFIGURATION_KEYS = ("api_key", "auth_key", "username", "password", "passkey", "cookie_file", "cookies", "ApiUser", "bioma_api_key", "ptgen_api")


def _has_configured_value(options: Mapping[str, Any]) -> bool:
    for key in TRACKER_CONFIGURATION_KEYS:
        value = options.get(key)
        if isinstance(value, str):
            value = value.strip()
        if value not in (None, "", False):
            return True
    return False


def configured_tracker_completions(config: Mapping[str, Any], cookies_dir: Path | None = None) -> dict[str, str]:
    """Return configured tracker names suitable for shell completion."""
    trackers = config.get("TRACKERS", {})
    if not isinstance(trackers, Mapping):
        return {}

    configured: dict[str, str] = {}
    default_trackers = trackers.get("default_trackers", "")
    if isinstance(default_trackers, str):
        default_names = default_trackers.split(",")
    elif isinstance(default_trackers, Sequence):
        default_names = default_trackers
    else:
        default_names = ()
    for name in default_names:
        normalized = str(name).strip()
        if normalized:
            configured[normalized.lower()] = normalized

    cookie_files: tuple[Path, ...] = ()
    cookie_root = cookies_dir or DATA_DIR / "cookies"
    try:
        if cookie_root.is_dir():
            cookie_files = tuple(path for path in cookie_root.iterdir() if path.is_file())
    except OSError:
        cookie_files = ()

    for name, options in trackers.items():
        if not isinstance(options, Mapping):
            continue
        tracker_name = str(name).strip()
        if not tracker_name:
            continue
        tracker_key = tracker_name.lower()
        has_config_value = _has_configured_value(options)
        has_cookie_file = any(tracker_key == path.stem.lower() or tracker_key in path.name.lower() for path in cookie_files)
        if has_config_value or has_cookie_file:
            configured[tracker_key] = tracker_name

    display_name_re = re.compile(r'^\s*display_name\s*=\s*(["\'])(.*?)\1', re.MULTILINE)
    supported_cats_re = re.compile(r"^\s*supported_categories\s*=\s*\((.*?)\)", re.MULTILINE | re.DOTALL)
    tracker_dir = Path(__file__).parent / "trackers"
    try:
        source_files = tracker_dir.rglob("*.py") if tracker_dir.is_dir() else ()
        for source_file in source_files:
            if source_file.name in ("__init__.py", "common.py", "routing.py") or source_file.name.endswith("_TEMPLATE.py"):
                continue
            tracker_key = source_file.stem.lower()
            if tracker_key not in configured:
                continue
            source = source_file.read_text(encoding="utf-8")
            display_match = display_name_re.search(source)
            categories_match = supported_cats_re.search(source)
            display_name = display_match.group(2) if display_match else configured[tracker_key].title()
            categories = []
            if categories_match:
                categories = [category.strip().strip("\"'") for category in categories_match.group(1).split(",") if category.strip()]
            configured[tracker_key] = f"{display_name} ({', '.join(categories)})" if categories else display_name
    except OSError, UnicodeError:
        pass

    return configured


def read_paths_from_stdin(argv: Sequence[str], stream: TextIO) -> tuple[list[str], list[str]]:
    args = list(argv)
    option_count = args.count(PATHS_FROM_STDIN_OPTION)
    if option_count == 0 or "-h" in args or "--help" in args:
        return args, []
    if option_count > 1:
        raise ValueError(f"{PATHS_FROM_STDIN_OPTION} may only be specified once")

    args.remove(PATHS_FROM_STDIN_OPTION)
    interactive = stream.isatty()
    if interactive:
        from src.console import logger

        logger.info("[cyan]Paste one full path per line, then press Enter on an empty line to start.[/cyan]")

    paths: list[str] = []
    for line in stream:
        path = line.rstrip("\r\n")
        if not path.strip():
            if interactive:
                break
            continue
        paths.append(path)

    if not paths:
        raise ValueError(f"{PATHS_FROM_STDIN_OPTION} did not receive any paths")
    return args, paths


class ShortHelpFormatter(argparse.HelpFormatter):
    """
    Custom formatter for short help (-h)
    Only displays essential options.
    """

    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=40, width=80)

    def format_help(self) -> str:
        """
        Customize short help output (only show essential arguments).
        """
        short_usage = "usage: upload.py [path...] [options]\n\n"
        short_options = """
Common options:
  -tmdb, --tmdb              Specify the TMDb id to use with movie/ or tv/ prefix
  -imdb, --imdb              Specify the IMDb id to use
  --no-imdb                  Do not search for or use IMDb metadata
  --cast                     Comma-separated cast override (takes priority over API metadata)
  -tvmaze, --tvmaze          Specify the TVMaze id to use
  -tvdb, --tvdb              Specify the TVDB id to use
  --queue (queue name)       Process an entire folder (including files/subfolders) in a queue
  -mf, --manual_frames       Comma-separated list of frame numbers to use for screenshots
  --description              Inline custom description block
  -df, --descfile            Path to custom description file
  -boverview, --book-overview  Book/Audiobook overview/synopsis (overrides auto-detected value)
  -serv, --service           Streaming service
  --no-aka                   Remove AKA from title
  -daily, --daily            Air date of a daily type episode (YYYY-MM-DD)
  -c, --category             Category (movie, tv, fanres, ebook)
  -t, --type                 Type (disc, remux, encode, webdl, etc.)
  --source                   Source (Blu-ray, BluRay, DVD, WEBDL, etc.)
  -comps, --comparison       Use comparison images from a folder (input folder path): see -comps_index
  -webui, --webui            Start the web UI server only (format: host:port, default: 127.0.0.1:5000)
  -debug, --debug            Prints more information, runs everything without actually uploading

Use --help for a full list of options.
"""
        return short_usage + short_options


class CustomArgumentParser(argparse.ArgumentParser):
    """
    Custom ArgumentParser to handle short (-h) and long (--help) help messages.
    """

    def print_help(self, file: Any = None) -> None:
        """
        Show short help for `-h` and full help for `--help`
        """
        if "--help" in sys.argv:
            super().print_help(file)  # Full help
        else:
            short_parser = argparse.ArgumentParser(formatter_class=ShortHelpFormatter, add_help=False, usage="upload.py [path...] [options]")
            short_parser.print_help(file)


class Args:
    """
    Parse Args
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def parse(self, argv: Sequence[str], meta: Meta) -> tuple[Meta, CustomArgumentParser, list[str]]:
        input = list(argv)
        parser = CustomArgumentParser(
            usage="upload.py [path...] [options]",
        )

        def make_dict_completer(choices_dict):
            def completer(prefix: str, **_: Any):
                return {k: v for k, v in choices_dict.items() if k.lower().startswith(prefix.lower())}

            return completer

        category_completer = make_dict_completer(
            {"movie": "Movie", "tv": "TV Show", "fanres": "Fan Restoration", "book": "E-Book or Audiobook", "game": "Video Game", "music": "Music Release"}
        )

        music_media_completer = make_dict_completer(
            {
                "cd": "Compact Disc",
                "web": "Web Release",
                "vinyl": "Vinyl Record",
                "dvd": "DVD Audio / Video",
                "bd": "Blu-ray Disc",
                "soundboard": "Soundboard Recording",
                "sacd": "Super Audio CD",
                "dat": "Digital Audio Tape",
                "cassette": "Cassette Tape",
            }
        )

        music_release_type_completer = make_dict_completer(
            {
                "album": "Studio Album",
                "soundtrack": "Original Soundtrack",
                "ep": "Extended Play",
                "anthology": "Anthology Collection",
                "compilation": "Compilation Album",
                "sampler": "Label Sampler",
                "single": "Single Release",
                "demo": "Demo Recording",
                "live album": "Live Concert Album",
                "split": "Split Release",
                "remix": "Remix Album",
                "bootleg": "Unofficial Bootleg",
                "interview": "Artist Interview",
                "mixtape": "Mixtape",
                "concert recording": "Live Concert Recording",
                "dj mix": "DJ Mix",
                "unknown": "Unknown Type",
            }
        )

        type_completer = make_dict_completer(
            {
                "disc": "Full Disc (BDMV/ISO)",
                "remux": "Remuxed MKV",
                "encode": "Encoded Release",
                "web-dl": "Web-DL (untouched)",
                "webrip": "Web-Rip (re-encoded)",
                "hdtv": "HDTV Capture",
                "dvdrip": "DVD Rip",
            }
        )

        source_completer = make_dict_completer(
            {
                "BluRay": "Blu-ray Disc",
                "DVD": "Standard DVD",
                "DVD5": "Single-layer DVD",
                "DVD9": "Dual-layer DVD",
                "HDDVD": "HD-DVD",
                "WEB": "Web Release",
                "HDTV": "HDTV Broadcast",
                "UHDTV": "UHDTV Broadcast",
                "LaserDisc": "LaserDisc",
                "DCP": "Digital Cinema Package",
            }
        )

        resolution_completer = make_dict_completer(
            {
                "2160p": "4K UHD (3840x2160)",
                "1080p": "Full HD (1920x1080)",
                "1080i": "Full HD Interlaced",
                "720p": "HD (1280x720)",
                "576p": "SD PAL (720x576)",
                "576i": "SD PAL Interlaced",
                "480p": "SD NTSC (720x480)",
                "480i": "SD NTSC Interlaced",
                "8640p": "16K Resolution",
                "4320p": "8K UHD (7680x4320)",
                "other": "Other/Unknown Resolution",
            }
        )

        platform_completer = make_dict_completer(
            {
                "pc": "Windows PC",
                "ps5": "PlayStation 5",
                "ps4": "PlayStation 4",
                "ps3": "PlayStation 3",
                "ps2": "PlayStation 2",
                "xbox": "Original Xbox",
                "x360": "Xbox 360",
                "xone": "Xbox One",
                "xsx": "Xbox Series X/S",
                "switch": "Nintendo Switch",
                "3ds": "Nintendo 3DS",
                "nds": "Nintendo DS",
                "wiiu": "Nintendo Wii U",
                "wii": "Nintendo Wii",
                "mac": "macOS",
                "linux": "Linux",
            }
        )

        imghost_completer = make_dict_completer(
            {
                "imgbb": "ImgBB",
                "imgbox": "Imgbox",
                "pixhost": "Pixhost",
                "lensdump": "Lensdump",
                "ptscreens": "PTScreens",
                "onlyimage": "OnlyImage",
                "dalexni": "Dalexni",
                "zipline": "Zipline",
                "midnightscene": "MidnightScene",
                "passtheimage": "PassTheImage",
                "seedpool_cdn": "Seedpool CDN",
                "utppm": "UTPPM",
                "lostimg": "LostImg",
            }
        )

        game_subcategory_completer = make_dict_completer({"full_game": "Base Game", "full_game_dlc": "Game + DLCs", "dlc": "DLC Only", "update": "Game Update/Patch"})

        max_piece_size_completer = make_dict_completer(
            {"1": "1 MiB", "2": "2 MiB", "4": "4 MiB", "8": "8 MiB", "16": "16 MiB", "32": "32 MiB", "64": "64 MiB", "128": "128 MiB"}
        )

        upload_order_completer = make_dict_completer({"concurrent": "Upload to both simultaneously", "usenet": "Upload to Usenet first", "tracker": "Upload to Trackers first"})

        parser.add_argument("path", nargs="*", help="Path to file/directory (in single/double quotes is best)")
        parser.add_argument(
            PATHS_FROM_STDIN_OPTION,
            action="store_true",
            required=False,
            help="Read one full path per line from standard input (finish an interactive paste with an empty line)",
        )
        parser.add_argument("--queue", nargs=1, required=False, help="(--queue queue_name) Process an entire folder (files/subfolders) in a queue")
        parser.add_argument("-lq", "--limit-queue", dest="limit_queue", nargs=1, required=False, help="Limit the amount of queue files processed", default=0)
        parser.add_argument(
            "-sc",
            "--site-check",
            dest="site_check",
            action="store_true",
            required=False,
            help="Just search sites for suitable uploads and create log file, no uploading",
            default=False,
        )
        parser.add_argument(
            "-su",
            "--site-upload",
            dest="site_upload",
            nargs=1,
            required=False,
            help="Specify a single tracker, and it will process the site searches and upload.",
            type=str,
            default=None,
        )
        parser.add_argument("--unit3d", action="store_true", required=False, help="[parse a txt output file from UNIT3D-Upload-Checker]")
        parser.add_argument("-s", "--screens", nargs=1, required=False, help="Number of screenshots", default=int(self.config["DEFAULT"]["screens"]))
        parser.add_argument(
            "-comps",
            "--comparison",
            nargs="+",
            required=False,
            help="Use comparison images from a folder (input folder path). See: https://github.com/Audionut/Upload-Assistant/pull/487",
            default=None,
        )
        parser.add_argument(
            "-comps_index",
            "--comparison_index",
            nargs=1,
            required=False,
            help="Which of your comparison indexes is the main images (required when comps)",
            default=None,
        )
        parser.add_argument("-mf", "--manual_frames", nargs=1, required=False, help="Comma-separated frame numbers to use as screenshots", type=str, default=None)
        parser.add_argument("--poster", nargs=1, required=False, help="Public artwork URL or local poster image path", dest="explicit_poster")
        parser.add_argument("--banner", nargs=1, required=False, help="Public artwork URL or local banner image path", dest="explicit_banner")
        action_c = parser.add_argument(
            "-c",
            "--category",
            nargs=1,
            required=False,
            help="Category [movie, tv, fanres, book, game, music]",
            choices=["movie", "tv", "fanres", "book", "game", "music"],
            dest="manual_category",
        )
        action_c.completer = category_completer
        parser.add_argument("--music-artist", nargs=1, required=False, help="MUSIC: main artist(s), separated by &", dest="music_artist")
        parser.add_argument("--music-album", nargs=1, required=False, help="MUSIC: album/release title", dest="music_album")
        action_music_media = parser.add_argument(
            "--music-media",
            nargs=1,
            required=False,
            type=str.casefold,
            choices=MUSIC_MEDIA_CHOICES,
            help="MUSIC: source medium (CD, WEB, Vinyl, DVD, BD, Soundboard, SACD, DAT, Cassette)",
            dest="music_media",
        )
        action_music_media.completer = music_media_completer
        action_music_rel_type = parser.add_argument(
            "--music-release-type",
            nargs=1,
            required=False,
            type=str.casefold,
            choices=MUSIC_RELEASE_TYPE_CHOICES,
            help="MUSIC: Orpheus release type (album, ep, single, compilation, live album, etc.)",
            dest="music_release_type",
        )
        action_music_rel_type.completer = music_release_type_completer
        parser.add_argument(
            "--music-release-year", nargs=1, required=False, help="MUSIC: concrete release/pressing year (not the original group year)", dest="music_release_year"
        )
        parser.add_argument("--music-edition-year", nargs=1, required=False, help="MUSIC: remaster/reissue/edition year", dest="music_edition_year")
        parser.add_argument("--music-label", nargs=1, required=False, help="MUSIC: label for this release", dest="music_label")
        parser.add_argument("--music-catalogue-number", nargs=1, required=False, help="MUSIC: catalogue number for this release", dest="music_catalogue_number")
        parser.add_argument("--music-genre", nargs=1, required=False, help="MUSIC: comma-separated genre override", dest="music_genres")
        parser.add_argument(
            "--music-discogs-id",
            nargs=1,
            required=False,
            help="MUSIC: Discogs release ID, release/master URL, or master/ID reference (plain IDs mean a release)",
            dest="music_discogs_id",
        )
        parser.add_argument("--music-discogs-release-id", nargs=1, required=False, help="MUSIC: exact Discogs release ID or URL", dest="music_discogs_release_id")
        parser.add_argument("--music-discogs-master-id", nargs=1, required=False, help="MUSIC: Discogs master ID or URL", dest="music_discogs_master_id")
        parser.add_argument("--no-music-discogs", dest="music_discogs_enabled", action="store_false", default=True, help="MUSIC: disable Discogs lookup and metadata")
        parser.add_argument("--music-enrich", dest="music_enrichment", action="store_true", default=None, help="MUSIC: enable bounded MusicBrainz enrichment for this run")
        parser.add_argument("--no-music-enrich", dest="music_enrichment", action="store_false", help="MUSIC: disable MusicBrainz enrichment for this run")
        action_t = parser.add_argument(
            "-t",
            "--type",
            nargs=1,
            required=False,
            help="Type [DISC, REMUX, ENCODE, WEBDL, WEBRIP, HDTV, DVDRIP]",
            choices=["disc", "remux", "encode", "webdl", "web-dl", "webrip", "hdtv", "dvdrip"],
            dest="manual_type",
        )
        action_t.completer = type_completer
        action_source = parser.add_argument(
            "--source",
            nargs=1,
            required=False,
            help="Source [Blu-ray, BluRay, DVD, DVD5, DVD9, HDDVD, WEB, HDTV, UHDTV, LaserDisc, DCP]",
            choices=["Blu-ray", "BluRay", "DVD", "DVD5", "DVD9", "HDDVD", "WEB", "HDTV", "UHDTV", "LaserDisc", "DCP"],
            dest="manual_source",
        )
        action_source.completer = source_completer
        action_res = parser.add_argument(
            "-res",
            "--resolution",
            nargs=1,
            required=False,
            help="Resolution [2160p, 1080p, 1080i, 720p, 576p, 576i, 480p, 480i, 8640p, 4320p, OTHER]",
            choices=["2160p", "1080p", "1080i", "720p", "576p", "576i", "480p", "480i", "8640p", "4320p", "other"],
        )
        action_res.completer = resolution_completer
        parser.add_argument("-tmdb", "--tmdb", nargs=1, required=False, help="TMDb ID (use movie/ or tv/ prefix)", type=str, dest="tmdb_manual")
        imdb_group = parser.add_mutually_exclusive_group()
        imdb_group.add_argument("-imdb", "--imdb", nargs=1, required=False, help="IMDb ID", type=str, dest="imdb_manual")
        imdb_group.add_argument("--no-imdb", action="store_true", required=False, help="Do not search for or use IMDb metadata")
        parser.add_argument("--cast", nargs=1, required=False, help="Comma-separated cast override (takes priority over API metadata)", type=str, dest="manual_cast")
        parser.add_argument("-mal", "--mal", nargs=1, required=False, help="MAL ID", type=str, dest="mal_manual")
        parser.add_argument("-tvmaze", "--tvmaze", nargs=1, required=False, help="TVMAZE ID", type=str, dest="tvmaze_manual")
        parser.add_argument("-tvdb", "--tvdb", nargs=1, required=False, help="TVDB ID", type=str, dest="tvdb_manual")
        parser.add_argument("-douban", "--douban", nargs=1, required=False, help="Douban ID (Number only)", dest="douban_manual", default=0)
        parser.add_argument("--no-metadata-cache", action="store_true", required=False, help="Do not read or write the persistent metadata cache", dest="no_metadata_cache")
        parser.add_argument("-igdb", "--igdb", nargs=1, required=False, help="IGDB ID", type=str, dest="igdb_manual")
        parser.add_argument("-steam", "--steam", nargs=1, required=False, help="Steam App ID or URL", type=str, dest="steam_manual")
        parser.add_argument("-g", "--tag", nargs="*", required=False, help="Group Tag", type=str)
        parser.add_argument("-serv", "--service", nargs="*", required=False, help="Streaming Service", type=str)
        parser.add_argument("-dist", "--distributor", nargs="*", required=False, help="Disc Distributor e.g.(Criterion, BFI, etc.)", type=str)
        parser.add_argument(
            "-edition",
            "--edition",
            "--repack",
            nargs="*",
            required=False,
            help="Edition/Repack String e.g.(Director's Cut, Uncut, Hybrid, REPACK, REPACK3)",
            type=str,
            dest="manual_edition",
        )
        parser.add_argument("-season", "--season", nargs=1, required=False, help="Season (number)", type=str)
        parser.add_argument("-episode", "--episode", nargs=1, required=False, help="Episode (number)", type=str)
        parser.add_argument("--not-anime", dest="not_anime", action="store_true", required=False, help="This is not an Anime release")
        parser.add_argument(
            "-met", "--manual-episode-title", nargs="*", required=False, help="Set episode title, empty = empty", type=str, dest="manual_episode_title", default=None
        )
        parser.add_argument("-daily", "--daily", nargs=1, required=False, help="Air date of this episode (YYYY-MM-DD)", type=datetime.date.fromisoformat, dest="manual_date")
        parser.add_argument("--no-season", dest="no_season", action="store_true", required=False, help="Remove Season from title")
        parser.add_argument("--no-year", dest="no_year", action="store_true", required=False, help="Remove Year from title")
        parser.add_argument("--no-aka", dest="no_aka", action="store_true", required=False, help="Remove AKA from title")
        parser.add_argument("--no-dub", dest="no_dub", action="store_true", required=False, help="Remove Dubbed from title")
        parser.add_argument("--no-dual", dest="no_dual", action="store_true", required=False, help="Remove Dual-Audio from title")
        parser.add_argument("--no-tag", dest="no_tag", action="store_true", required=False, help="Remove Group Tag from title")
        parser.add_argument("--name", nargs=1, required=False, help="Override the generated release name", type=str, dest="manual_name")
        parser.add_argument("--no-edition", dest="no_edition", action="store_true", required=False, help="Remove Edition from title")
        parser.add_argument("--dual-audio", dest="dual_audio", action="store_true", required=False, help="Add Dual-Audio to the title")
        parser.add_argument("-ol", "--original-language", dest="manual_language", nargs=1, required=False, help="Set original audio language")
        parser.add_argument(
            "-oil",
            "--only-if-languages",
            dest="has_languages",
            nargs="*",
            required=False,
            help="Require at least one of the languages to upload. Comma separated list e.g. 'English, French, Spanish'",
            type=str,
        )
        parser.add_argument("-ns", "--no-seed", action="store_true", required=False, help="Do not add torrent to the client")
        parser.add_argument("-year", "--year", dest="manual_year", nargs=1, required=False, help="Override the year found", default=0)
        parser.add_argument("-author", "--author", nargs="*", required=False, help="Book/Audiobook author name (overrides auto-detected value)", type=str, dest="book_author")
        parser.add_argument("-btitle", "--book-title", nargs="*", required=False, help="Book/Audiobook title (overrides auto-detected value)", type=str, dest="book_title")
        parser.add_argument("--comic", "-comic", action="store_true", required=False, help="Identify the book upload as a Comic", dest="comic", default=False)
        parser.add_argument("--manga", "-manga", action="store_true", required=False, help="Identify the book upload as a Manga", dest="manga", default=False)
        parser.add_argument("--magazine", "-magazine", action="store_true", required=False, help="Identify the book upload as a Magazine", dest="magazine", default=False)
        parser.add_argument("--newspaper", "-newspaper", action="store_true", required=False, help="Identify the book upload as a Newspaper", dest="newspaper", default=False)
        parser.add_argument(
            "-btra",
            "--book-translator",
            nargs="*",
            required=False,
            help="Book/Audiobook translator",
            type=str,
            dest="book_translator",
        )
        parser.add_argument(
            "-blang",
            "--book-language",
            nargs="*",
            required=False,
            help="Book/Audiobook language (overrides auto-detected value, e.g. 'English', 'Portuguese', 'pt')",
            type=str,
            dest="book_language",
        )
        parser.add_argument(
            "-isbn",
            "--isbn",
            nargs=1,
            required=False,
            help="Book/Audiobook ISBN (overrides auto-detected value)",
            type=str,
            dest="book_isbn",
        )
        parser.add_argument(
            "-asin",
            "--asin",
            nargs=1,
            required=False,
            help="Book/Audiobook ASIN (overrides auto-detected value)",
            type=str,
            dest="book_asin",
        )
        parser.add_argument(
            "-openlib",
            "--openlibrary",
            nargs=1,
            required=False,
            help="Book/Audiobook OpenLibrary Work ID (e.g. OL45883W)",
            type=str,
            dest="openlibrary",
        )
        parser.add_argument(
            "-pub",
            "--publisher",
            nargs="*",
            required=False,
            help="Book/Audiobook publisher (overrides auto-detected value)",
            type=str,
            dest="book_publisher",
        )
        action_plat = parser.add_argument(
            "-plat",
            "--platform",
            "--platforms",
            nargs=1,
            required=False,
            help="Game platform (PC, PS5, PS4, PS3, PS2, Xbox, X360, XOne, XSX, Switch, 3DS, NDS, WiiU, Wii, Mac, Linux)",
            type=str.lower,
            choices=["pc", "ps5", "ps4", "ps3", "ps2", "xbox", "x360", "xone", "xsx", "switch", "3ds", "nds", "wiiu", "wii", "mac", "linux"],
            dest="manual_platform",
        )
        action_plat.completer = platform_completer
        parser.add_argument(
            "-gv",
            "--game-version",
            nargs="*",
            required=False,
            help="Game version (overrides auto-detected value, e.g. 'v1.15')",
            type=str,
            dest="game_version",
        )
        parser.add_argument(
            "--multi",
            dest="manual_multi",
            action="store_true",
            required=False,
            help="Force a MULTI language tag for GAME releases",
        )
        action_gsc = parser.add_argument(
            "-gsc",
            "--game-subcategory",
            nargs=1,
            required=False,
            help="Game subcategory (full_game, full_game_dlc, dlc, update)",
            type=str.lower,
            choices=["full_game", "full_game_dlc", "dlc", "update"],
            dest="game_subcategory",
        )
        action_gsc.completer = game_subcategory_completer
        parser.add_argument(
            "-mc", "--commentary", dest="manual_commentary", action="store_true", required=False, help="Manually indicate whether commentary tracks are included"
        )
        parser.add_argument(
            "-sfxs",
            "--sfx-subtitles",
            dest="sfx_subtitles",
            action="store_true",
            required=False,
            help="Manually indicate whether subtitles with visual enhancements like animations, effects, or backgrounds are included",
        )
        parser.add_argument("-e", "--extras", dest="extras", action="store_true", required=False, help="Indicates that extras are included. Mainly used for Blu-rays discs")
        parser.add_argument(
            "-sort",
            "--sorted-filelist",
            dest="sorted_filelist",
            action="store_true",
            required=False,
            help="Use the largest video file for processing instead of the first video file found",
        )
        parser.add_argument(
            "--tracker-id",
            action="append",
            metavar="TRACKER=ID|URL",
            help="Tracker torrent ID, as TRACKER=ID, TRACKER=URL, or a tracker torrent URL. May be repeated.",
        )
        parser.add_argument("-req", "--search_requests", action="store_true", required=False, help="Search for matching requests on supported trackers", default=None)
        parser.add_argument("-sat", "--skip_auto_torrent", action="store_true", required=False, help="Skip automated qbittorrent client torrent searching", default=None)
        parser.add_argument(
            "-onlyID",
            "--onlyID",
            dest="only_id",
            action="store_true",
            required=False,
            help="Only grab meta ids (tmdb/imdb/etc) from tracker, not description/image links.",
            default=None,
        )
        parser.add_argument("--foreign", dest="foreign", action="store_true", required=False, help="Set for CINEMATIK Foreign category")
        parser.add_argument("--opera", dest="opera", action="store_true", required=False, help="Set for CINEMATIK Opera & Musical category")
        parser.add_argument("--asian", dest="asian", action="store_true", required=False, help="Set for CINEMATIK Asian category")
        parser.add_argument(
            "-disctype",
            "--disctype",
            nargs=1,
            required=False,
            help="Type of disc for CINEMATIK (BD100, BD66, BD50, BD25, NTSC DVD9, NTSC DVD5, PAL DVD9, PAL DVD5, Custom, 3D)",
            type=str,
        )
        parser.add_argument("--untouched", dest="untouched", action="store_true", required=False, help="Set when a completely untouched disc at CINEMATIK")
        parser.add_argument(
            "-manual_dvds",
            "--manual_dvds",
            nargs=1,
            required=False,
            help="Override the default number of DVD's (eg: use 2xDVD9+DVD5 instead)",
            type=str,
            dest="manual_dvds",
            default="",
        )
        parser.add_argument(
            "-pb",
            "--desclink",
            dest="description_link",
            nargs=1,
            required=False,
            help="Custom description block to insert (link to hastebin/pastebin). This is added as a section inside the final description and does NOT replace the auto-generated description (MediaInfo, screenshots, etc.)",
        )
        parser.add_argument(
            "--description",
            dest="description_inline",
            nargs=1,
            required=False,
            help="Inline custom description block to insert. This is added as a section inside the final description and does NOT replace auto-generated sections (MediaInfo, screenshots, etc.)",
        )
        parser.add_argument(
            "-df",
            "--descfile",
            dest="description_file",
            nargs=1,
            required=False,
            help="Custom description block to insert (path to file OR filename in current working directory). This is added as a section inside the final description and does NOT replace the auto-generated description (MediaInfo, screenshots, etc.)",
        )
        parser.add_argument(
            "-boverview",
            "--book-overview",
            "-ov",
            "--overview",
            dest="book_overview",
            nargs="*",
            required=False,
            help="Book/Audiobook overview/synopsis (overrides auto-detected value)",
            type=str,
        )
        parser.add_argument(
            "-menus",
            "--menus",
            "-menu",
            "--menu",
            dest="path_to_menu_screenshots",
            nargs=1,
            required=False,
            help="Raw Disc only (Blu-ray/DVD). Path to the folder containing screenshots of the disc menus (or pass 'auto' to automatically capture DVD menu screenshots). All image files found in the folder will be used. Files should preferably be in PNG format (due to restrictions on some trackers), but other formats can be used (jpg, jpeg, webp)",
            type=str,
            default="",
        )
        action_ih = parser.add_argument(
            "-ih",
            "--imghost",
            nargs=1,
            required=False,
            help="Image Host",
            choices=[
                "imgbb",
                "imgbox",
                "pixhost",
                "lensdump",
                "ptscreens",
                "onlyimage",
                "dalexni",
                "zipline",
                "midnightscene",
                "passtheimage",
                "seedpool_cdn",
                "utppm",
                "lostimg",
            ],
        )
        action_ih.completer = imghost_completer
        parser.add_argument("-siu", "--skip-imagehost-upload", dest="skip_imghost_upload", action="store_true", required=False, help="Skip Uploading to an image host")
        parser.add_argument("-th", "--torrenthash", nargs=1, required=False, help="Torrent Hash to re-use from your client's session directory")
        parser.add_argument("-nfo", "--nfo", action="store_true", required=False, help="Use .nfo in directory for description")
        parser.add_argument("-k", "--keywords", nargs=1, required=False, help="Add comma separated keywords e.g. 'keyword, keyword2, etc'")
        parser.add_argument(
            "-kf",
            "--keep-folder",
            action="store_true",
            required=False,
            help="Keep the folder containing the single file. Works only when supplying a directory as input. For uploads with poor filenames, like some scene.",
        )
        parser.add_argument(
            "-knfo",
            "--keep-nfo",
            action="store_true",
            required=False,
            help="For specific trackers only, allows to keep nfo files. With single files, must be used in conjuction with --keep-folder to find the nfo in the same folder as the file.",
            dest="keep_nfo",
        )
        parser.add_argument("-reg", "--region", nargs=1, required=False, help="Region for discs")
        parser.add_argument("-a", "--anon", action="store_true", required=False, help="Upload anonymously")
        parser.add_argument("-st", "--stream", action="store_true", required=False, help="Stream Optimized Upload")
        parser.add_argument("-webdv", "--webdv", action="store_true", required=False, help="Contains a Dolby Vision layer converted using dovi_tool (HYBRID)")
        parser.add_argument("-hc", "--hardcoded-subs", action="store_true", required=False, help="Contains hardcoded subs", dest="hardcoded_subs")
        parser.add_argument("-hcl", "--hardcoded-subs-language", nargs=1, required=False, help="Language/s of hardcoded subtitles", dest="hardcoded_subs_language")
        parser.add_argument("-pr", "--personalrelease", action="store_true", required=False, help="Personal Release")
        parser.add_argument("-sdc", "--skip-dupe-check", action="store_true", required=False, help="Ignore dupes and upload anyway (Skips dupe check)", dest="dupe")
        parser.add_argument(
            "-sda", "--skip-dupe-asking", action="store_true", required=False, help="Don't prompt about dupes, just treat dupes as actual dupes", dest="ask_dupe"
        )
        parser.add_argument(
            "-ddc",
            "--double-dupe-check",
            action="store_true",
            required=False,
            help="May be useful when trying to race. Will run another dupe checking pass on any trackers that previously passed upload check, right before uploading",
            dest="dupe_again",
        )
        parser.add_argument(
            "-dsdt",
            "--dupe-size-difference-tolerance",
            dest="dupe_size_difference_tolerance",
            nargs=1,
            required=False,
            help="Ignore dupes if their size difference is greater than or equal to this percentage (e.g. 20)",
        )
        parser.add_argument(
            "-debug", "--debug", action="store_true", required=False, help="Debug Mode, will run through all the motions providing extra info, but will not upload to trackers."
        )
        parser.add_argument("-ffdebug", "--ffdebug", action="store_true", required=False, help="Will show info from ffmpeg while taking screenshots.")
        parser.add_argument(
            "-uptimer", "--upload-timer", action="store_true", required=False, help="Prints the time it takes to upload to each individual site.", dest="upload_timer"
        )
        action_mps = parser.add_argument(
            "-mps",
            "--max-piece-size",
            nargs=1,
            required=False,
            help="Set max piece size allowed in MiB for default torrent creation (default 128 MiB)",
            choices=["1", "2", "4", "8", "16", "32", "64", "128"],
        )
        action_mps.completer = max_piece_size_completer
        parser.add_argument("-nh", "--nohash", action="store_true", required=False, help="Don't hash .torrent")
        parser.add_argument("-rh", "--rehash", action="store_true", required=False, help="DO hash .torrent")
        parser.add_argument("-mkbrr", "--mkbrr", action="store_true", required=False, help="Use mkbrr for torrent hashing")
        parser.add_argument(
            "-frc",
            "--force-recheck",
            action="store_true",
            required=False,
            help="(qBitTorrent only with auto torrent searching) Force recheck torrent in client before uploading",
            dest="force_recheck",
        )
        parser.add_argument("-dr", "--draft", action="store_true", required=False, help="Send to drafts (BEYONDHD, LST)")
        parser.add_argument("-mq", "--modq", action="store_true", required=False, help="Send to modQ")
        parser.add_argument("-feat", "--featured", action="store_true", required=False, help="Featured torrent")
        parser.add_argument(
            "-dup",
            "--double-upload",
            action="store_true",
            required=False,
            help="Double upload (UNIT3D internal/staff only)",
            dest="doubleup",
        )
        parser.add_argument(
            "-dupuntil",
            "--double-upload-until",
            nargs=1,
            required=False,
            help="Double upload duration in days (Aither, internal/staff only)",
            default=0,
            dest="double_upload_until",
        )
        parser.add_argument("-stk", "--sticky", action="store_true", required=False, help="Sticky torrent (Pinned)")
        parser.add_argument("-ref", "--refundable", action="store_true", required=False, help="Refundable torrent (Aither, internal/staff only)")
        parser.add_argument("-client", "--client", nargs=1, required=False, help="Use this torrent client instead of default")
        parser.add_argument("-qbt", "--qbit-tag", dest="qbit_tag", nargs=1, required=False, help="Add to qbit with this tag")
        parser.add_argument("-qbc", "--qbit-cat", dest="qbit_cat", nargs=1, required=False, help="Add to qbit with this category")
        parser.add_argument("-qbcon", "--qbit-bw-control", action="store_true", required=False, help="Enable all qBittorrent bandwidth checks", dest="qbit_bandwidth_control")
        parser.add_argument(
            "--qbit-bw-control-after-usenet",
            action="store_true",
            required=False,
            help="Keep bandwidth checks enabled for torrent trackers uploaded after Usenet",
            dest="qbit_bandwidth_control_after_usenet",
        )
        parser.add_argument("-qbcrl", "--qbit-bw-threshold", nargs=1, required=False, help="qBittorrent bandwidth limit threshold (KB/s)", dest="qbit_bandwidth_threshold")
        parser.add_argument("-qbctime", "--qbit-bw-time", nargs=1, required=False, help="Time to stay under qBittorrent threshold (seconds)", dest="qbit_bandwidth_time")
        action_uo = parser.add_argument(
            "-uo",
            "--upload-order",
            dest="upload_order",
            nargs=1,
            required=False,
            choices=["concurrent", "usenet", "tracker"],
            help="Set the upload order when both torrent trackers and Usenet are selected ('concurrent', 'usenet', 'tracker')",
        )
        action_uo.completer = upload_order_completer
        parser.add_argument("-rtl", "--rtorrent-label", dest="rtorrent_label", nargs=1, required=False, help="Add to rtorrent with this label")

        def _tracker_completer(prefix: str, **_: Any) -> dict[str, str]:
            configured = configured_tracker_completions(self.config)

            if "," in prefix:
                base, current = prefix.rsplit(",", 1)
                return {f"{base},{t}": desc for t, desc in configured.items() if t.startswith(current.lower())}
            return {t: desc for t, desc in configured.items() if t.startswith(prefix.lower())}

        tk_action = parser.add_argument("-tk", "--trackers", nargs=1, required=False, help="Upload to these trackers, comma separated (--trackers blu,bhd) including manual")
        tk_action.completer = _tracker_completer

        rtk_action = parser.add_argument(
            "-rtk",
            "--trackers-remove",
            dest="trackers_remove",
            nargs=1,
            required=False,
            help="Remove these trackers when processing default trackers, comma separated (--trackers-remove blu,bhd)",
        )
        rtk_action.completer = _tracker_completer
        parser.add_argument(
            "-tpc",
            "--trackers-pass",
            dest="trackers_pass",
            nargs=1,
            required=False,
            help="How many trackers need to pass all checks (dupe/banned group/etc) to actually proceed to uploading",
        )
        parser.add_argument("-rt", "--randomized", nargs=1, required=False, help="Number of extra, torrents with random infohash", default=0)
        parser.add_argument(
            "-entropy",
            "--entropy",
            dest="entropy",
            nargs=1,
            required=False,
            help="Use entropy in created torrents. (32 or 64) bits (ie: -entropy 32). Not supported at all sites, you many need to redownload the torrent",
            default=0,
        )
        parser.add_argument("-ua", "--unattended", action="store_true", required=False, help=argparse.SUPPRESS)
        parser.add_argument("-uac", "--unattended_confirm", action="store_true", required=False, help=argparse.SUPPRESS)
        parser.add_argument("-vs", "--vapoursynth", action="store_true", required=False, help="Use vapoursynth for screens (requires vs install)")
        parser.add_argument(
            "-webui", "--webui", nargs="?", const="127.0.0.1:5000", metavar="HOST:PORT", help="Start the web UI server only (format: host:port, default: 127.0.0.1:5000)"
        )
        parser.add_argument("-dm", "--delete-meta", action="store_true", required=False, dest="delete_meta", help="Delete only meta.json from tmp directory")
        parser.add_argument("-dtmp", "--delete-tmp", action="store_true", required=False, dest="delete_tmp", help="Delete tmp directory for the working file/folder")
        parser.add_argument("-cleanup", "--cleanup", action="store_true", required=False, help="Clean up tmp directory")
        parser.add_argument(
            "-fl",
            "--freeleech",
            nargs=1,
            required=False,
            help="Freeleech Percentage. Any value 1-100 works, but site search is limited to certain values",
            default=0,
            dest="freeleech",
        )
        parser.add_argument(
            "-fl-until",
            "--freeleech-until",
            nargs=1,
            required=False,
            help="Freeleech duration in days (Aither, internal/staff only)",
            default=0,
            dest="freeleech_until",
        )
        parser.add_argument("--infohash", nargs=1, required=False, help="V1 Info Hash")
        parser.add_argument(
            "-ch",
            "--channel",
            nargs=1,
            required=False,
            help="SPEEDAPP only: Channel ID number or tag to upload to (preferably the ID), without '@'. Example: '-ch spd' when using a tag, or '-ch 1' when using an ID.",
            type=str,
            dest="spd_channel",
            default="",
        )
        parser.add_argument("-excl", "--exclusive", nargs=1, required=False, help="Set exclusive flag on all supported trackers", dest="exclusive")
        parser.add_argument(
            "-as", "--audio-spectrogram", action="store_true", required=False, help="Generate and upload audio spectrograms", dest="audio_spectrogram", default=None
        )
        parser.add_argument(
            "-ast",
            "--audio-spectrogram-tracks",
            nargs=1,
            required=False,
            help="Select zero-based displayed audio stream positions for spectrograms (comma-separated, e.g. '0,1', or 'all')",
            type=str,
            dest="audio_spectrogram_tracks",
            default=None,
        )
        parser.add_argument(
            "-dhp",
            "--dynamic-hdr-plot",
            action="store_true",
            required=False,
            help="Generate and upload Dolby Vision and HDR10+ dynamic metadata plots",
            dest="dynamic_hdr_plot",
            default=None,
        )
        parser.add_argument("-u", "--usenet", action="store_true", required=False, help="Upload files to Usenet (NNTP)")
        parser.add_argument("--usenet-subject", nargs=1, required=False, help="Custom subject line for Usenet post", type=str, dest="usenet_subject", default=None)
        parser.add_argument(
            "--archive-password",
            nargs=1,
            required=False,
            help="Override the Usenet 7z archive password for this run; use 'random' to generate one",
            type=str,
            dest="archive_password",
        )
        argcomplete.autocomplete(parser)
        from src.console import logger

        parsed_args_ns, before_args = parser.parse_known_args(input)
        parsed_args: dict[str, Any] = vars(parsed_args_ns)
        # console.print(args)

        # Validation: require either path, site_upload, or webui
        if not parsed_args.get("path") and not parsed_args.get("site_upload") and not parsed_args.get("webui"):
            logger.error("[red]Error: Either a path must be provided, --site-upload must be specified, or --webui must be specified.[/red]")
            parser.print_help()
            sys.exit(1)

        # For site upload mode, provide a dummy path if none given
        if (parsed_args.get("site_upload") or parsed_args.get("webui")) and not parsed_args.get("path"):
            parsed_args["path"] = ["dummy_path_for_site_upload"]

        # manual_frames parsing happens after parsed_args are merged into meta
        if len(before_args) >= 1 and not Path(" ".join(parsed_args["path"])).exists():
            for each in before_args:
                parsed_args["path"].append(each)
                if Path(" ".join(parsed_args["path"])).exists():
                    if any(".mkv" in x for x in before_args):
                        if ".mkv" in " ".join(parsed_args["path"]):
                            break
                    else:
                        break

        if meta.tmdb_manual is not None or meta.imdb_manual is not None:
            meta.tmdb_manual = meta.tmdb_id = meta.tmdb = meta.imdb_id = meta.imdb = None
        for key in parsed_args:
            value = parsed_args[key]
            if value not in (None, []):
                if isinstance(value, list):
                    value_list = [str(item) for item in value]
                    value2 = self.list_to_string(value_list)
                    if key == "manual_type":
                        meta.manual_type = value2.upper().replace("-", "")
                    elif key == "tag":
                        meta[key] = f"-{value2}"
                    elif key == "description_file" or key == "comparison":
                        meta[key] = str(Path(value2).resolve())
                    elif key == "screens":
                        try:
                            meta[key] = int(value2)
                        except ValueError, TypeError:
                            meta[key] = int(self.config.get("DEFAULT", {}).get("screens", 1))
                    elif key in ("trackers_pass", "comparison_index"):
                        try:
                            meta[key] = int(value2)
                        except ValueError, TypeError:
                            meta[key] = None
                    elif key in (
                        "limit_queue",
                        "randomized",
                        "max_piece_size",
                        "entropy",
                        "douban_manual",
                        "music_release_year",
                        "music_edition_year",
                        "qbit_bandwidth_threshold",
                        "qbit_bandwidth_time",
                    ):
                        try:
                            meta[key] = int(value2)
                        except ValueError, TypeError:
                            meta[key] = 0
                    elif key == "imghost":
                        meta.imghost = value2
                        meta.imghost_from_cli = True
                    elif key == "season":
                        meta.manual_season = value2
                    elif key == "episode":
                        meta.manual_episode = value2
                    elif key == "manual_date":
                        meta.manual_date = value2
                    elif key == "tmdb_manual":
                        meta.category, meta.tmdb_manual = self.parse_tmdb_id(value2, meta.category)
                    elif key == "tracker_id":
                        for tracker_id_value in value_list:
                            tracker_name, torrent_id = self.parse_tracker_id(tracker_id_value)
                            meta.set_tracker_ids({tracker_name: torrent_id})
                    elif key == "manual_cast":
                        meta.manual_cast = [name.strip() for name in value2.split(",") if name.strip()]
                    elif key == "openlibrary":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                path_parts = parsed.path.strip("/").split("/")
                                for part in path_parts:
                                    if part.upper().startswith("OL") and (part.upper().endswith("W") or part.upper().endswith("M")):
                                        meta.openlibrary = part
                                        break
                                else:
                                    meta.openlibrary = path_parts[-1]
                            except Exception:
                                logger.info("[red]Unable to parse OpenLibrary ID from url")
                                logger.info("[red]Continuing without --openlibrary")
                        else:
                            meta.openlibrary = value2
                    elif key == "steam_manual":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                match = re.search(r"/app/(\d+)", parsed.path)
                                if match:
                                    meta.steam_manual = match.group(1)
                                else:
                                    meta.steam_manual = value2
                            except Exception:
                                logger.info("[red]Unable to parse Steam ID from URL. Using raw value.[/red]")
                                meta.steam_manual = value2
                        else:
                            meta.steam_manual = value2

                    else:
                        meta[key] = value2
                else:
                    meta[key] = value
            if key == "site_upload":
                if isinstance(value, list):
                    value_list = [str(item) for item in value]
                    if len(value_list) == 1:
                        meta[key] = (value_list[0]).upper()  # Extract the tracker acronym and normalize it
                    elif value_list:
                        meta[key] = str(value_list).upper()
                    else:
                        meta[key] = None
                elif value is not None:
                    meta[key] = (value).upper()
                else:
                    meta[key] = None
            if key == "manual_year":
                if isinstance(value, list):
                    value_list = [str(item) for item in value]
                    if len(value_list) == 1 and value_list[0] != "":
                        try:
                            meta[key] = int(value_list[0])
                        except ValueError, TypeError:
                            meta[key] = 0
                    else:
                        meta[key] = 0
                elif value not in (None, [], 0, ""):
                    try:
                        meta[key] = int(str(value))
                    except ValueError, TypeError:
                        meta[key] = 0
                else:
                    meta[key] = 0
            if key in ("manual_edition"):
                if isinstance(value, list):
                    value_list = [str(item) for item in value]
                    if len(value_list) == 1:
                        meta[key] = value_list[0]
                    else:
                        meta[key] = value_list
                else:
                    meta[key] = value
            if key in ("manual_dvds"):
                if isinstance(value, list):
                    value_list = [str(item) for item in value]
                    if len(value_list) == 1:
                        meta[key] = value_list[0]
                    elif value_list:
                        meta[key] = value_list
                    else:
                        meta[key] = ""
                elif value not in (None, [], ""):
                    meta[key] = value
                else:
                    meta[key] = ""
            if key == "dupe_size_difference_tolerance":
                if isinstance(value, list):
                    value_list = [str(item) for item in value]
                    if len(value_list) == 1 and value_list[0] != "":
                        try:
                            meta[key] = float(value_list[0])
                        except ValueError, TypeError:
                            meta[key] = None
                    else:
                        meta[key] = None
                elif value not in (None, [], ""):
                    try:
                        meta[key] = float(str(value))
                    except ValueError, TypeError:
                        meta[key] = None
                else:
                    meta[key] = None
            if key in ("freeleech", "freeleech_until", "double_upload_until"):
                if isinstance(value, list):
                    value_list = [str(item) for item in value]
                    if len(value_list) == 1 and value_list[0] != "":
                        try:
                            parsed_int = int(value_list[0])
                            meta[key] = parsed_int if parsed_int >= 0 else 0
                        except ValueError, TypeError:
                            meta[key] = 0
                    else:
                        meta[key] = 0
                elif value not in (None, [], 0, ""):
                    try:
                        parsed_int = int(str(value))
                        meta[key] = parsed_int if parsed_int >= 0 else 0
                    except ValueError, TypeError:
                        meta[key] = 0
                else:
                    meta[key] = 0
            if key in ["manual_episode_title"] and value == []:
                meta[key] = ""
            if key in ["tvmaze_manual"]:
                if isinstance(value, list):
                    value_list = [str(item) for item in value]
                    if len(value_list) == 1:
                        meta[key] = value_list[0]
                    else:
                        meta[key] = value_list
                elif value not in (None, []):
                    meta[key] = value
            if key == "trackers":
                if value:
                    # Extract from list if it's a single-item list (from nargs=1)
                    if isinstance(value, list):
                        value_list = value
                        tracker_value: Any = value_list[0] if len(value_list) == 1 else value_list
                    else:
                        tracker_value = value

                    if isinstance(tracker_value, str):
                        tracker_value = tracker_value.strip("\"'")

                        # Split by comma if present
                        if "," in tracker_value:
                            meta[key] = [(t).upper() for t in tracker_value.split(",")]
                        else:
                            meta[key] = [(tracker_value).upper()]
                    elif isinstance(tracker_value, list):
                        # Handle list of strings
                        expanded: list[str] = []
                        for t in tracker_value:
                            t_str = str(t)
                            if "," in t_str:
                                expanded.extend([(x).upper() for x in t_str.split(",")])
                            else:
                                expanded.append((t_str).upper())
                        meta[key] = expanded
                    else:
                        meta[key] = [(str(tracker_value)).upper()]
                else:
                    meta[key] = []
            else:
                meta[key] = meta.get(key)
            # if key == 'help' and value == True:
            # parser.print_help()

        if parsed_args.get("archive_password"):
            meta.usenet_archive_password_is_random = str(meta.archive_password).lower() == "random"

        manual_frames_value = meta.manual_frames
        if manual_frames_value is not None:
            try:
                frames_str = str(manual_frames_value)
                meta.manual_frames = [int(t.strip()) for t in frames_str.split(",") if t.strip()]
            except ValueError:
                logger.info("[red]Invalid format for manual_frames. Please provide a comma-separated list of integers.")
                logger.info(f"Processed manual_frames: {manual_frames_value}")
                sys.exit(1)
        else:
            meta.manual_frames = None

        # Apply book metadata overrides: --author and --book-title map to meta keys
        # used by trackers like CAPYBARABR when constructing the torrent name for BOOK category.
        self._apply_book_meta_overrides(meta)

        # Apply game metadata overrides: --platform maps to platforms key
        self._apply_game_meta_overrides(meta)

        return meta, parser, before_args

    @staticmethod
    def _apply_book_meta_overrides(meta: Meta) -> None:
        """Normalise CLI book arguments (--author, --book-title, --blang, --isbn) into *meta*.

        Maps ``book_author`` / ``book_title`` to the ``author`` / ``title`` keys
        expected by trackers like CAPYBARABR.  Maps ``book_isbn`` to ``isbn``.
        Resolves the ``book_language`` value via
        *langcodes* so both a human-readable name and the ISO 639-3 code are stored.
        Falls back gracefully when *langcodes* is unavailable or the code is unknown.
        """
        book_overview_arg = meta.book_overview or meta.overview
        if book_overview_arg not in (None, "", []):
            overview_str = " ".join(str(x) for x in book_overview_arg if str(x)).strip() if isinstance(book_overview_arg, list) else str(book_overview_arg).strip()
            meta.overview = overview_str
            meta.book_overview = overview_str
        else:
            meta.overview = ""
            meta.book_overview = ""

        book_author_arg = meta.book_author
        if book_author_arg not in (None, ""):
            meta.author = str(book_author_arg).strip()

        book_title_arg = meta.book_title
        if book_title_arg not in (None, ""):
            meta.title = str(book_title_arg).strip()

        book_isbn_arg = meta.book_isbn
        if book_isbn_arg not in (None, ""):
            meta.isbn = str(book_isbn_arg).strip()

        book_asin_arg = meta.book_asin
        if book_asin_arg not in (None, ""):
            meta.asin = str(book_asin_arg).strip()

        openlibrary_arg = meta.openlibrary
        if openlibrary_arg not in (None, ""):
            meta.openlibrary = str(openlibrary_arg).strip()

        book_publisher_arg = meta.book_publisher
        if book_publisher_arg not in (None, ""):
            meta.publisher = str(book_publisher_arg).strip()

        book_translator_arg = meta.book_translator
        if book_translator_arg not in (None, ""):
            meta.book_translator = str(book_translator_arg).strip()

        book_language_arg = meta.book_language
        if book_language_arg not in (None, ""):
            raw_lang = book_language_arg.strip()
            try:
                import langcodes

                # Try get() first (ISO 639-1/3 codes like "pt", "por")
                try:
                    lc = langcodes.get(raw_lang.lower())
                    full_name = lc.display_name("en") or raw_lang.title()
                    alpha3 = lc.to_alpha3() or ""
                    if full_name and full_name.lower() != raw_lang.lower():
                        meta.book_language = full_name
                        meta.book_language_iso = alpha3
                    else:
                        raise LookupError("no display name change")
                except Exception:
                    # Fall back to find() for natural language names ("Portuguese")
                    lc = langcodes.find(raw_lang)
                    meta.book_language = lc.display_name("en") or raw_lang.title()
                    meta.book_language_iso = lc.to_alpha3() or ""
            except Exception:
                meta.book_language = raw_lang.title()
                meta.book_language_iso = ""

        manual_year_arg = meta.manual_year
        if manual_year_arg not in (None, "", 0, "0"):
            meta.year = int(manual_year_arg)
            meta.search_year = manual_year_arg

        # Detect newspapers in overridden titles
        from src.book_prep import detect_newspaper, sanitize_book_author, sanitize_book_language

        detect_newspaper(meta)
        sanitize_book_language(meta)
        sanitize_book_author(meta)

    @staticmethod
    def _apply_game_meta_overrides(meta: Meta) -> None:
        """Normalise CLI game arguments (--platform) into *meta*."""
        manual_platform_arg = meta.manual_platform
        if manual_platform_arg not in (None, ""):
            plat = str(manual_platform_arg).strip().lower()
            mapping = {
                "pc": "PC",
                "ps5": "PS5",
                "ps4": "PS4",
                "ps3": "PS3",
                "ps2": "PS2",
                "ps1": "PS1",
                "psp": "PSP",
                "psvita": "PSVITA",
                "xbox": "XBOX",
                "x360": "X360",
                "xone": "XONE",
                "xsx": "XSX",
                "switch": "SWITCH",
                "3ds": "3DS",
                "nds": "NDS",
                "ds": "NDS",
                "wiiu": "WIIU",
                "wii": "WII",
                "mac": "MAC",
                "linux": "LINUX",
            }
            clean_plat = mapping.get(plat, plat.upper())
            meta.manual_platform = clean_plat
            meta.platform = clean_plat

        steam_manual_arg = meta.steam_manual
        if steam_manual_arg not in (None, ""):
            meta.steam_manual = str(steam_manual_arg).strip()

        game_version_arg = meta.game_version
        if game_version_arg not in (None, ""):
            meta.game_version = game_version_arg.strip()

        game_subcategory_arg = meta.game_subcategory
        if game_subcategory_arg not in (None, ""):
            meta.game_subcategory = game_subcategory_arg.strip().lower()

        manual_year_arg = meta.manual_year
        if manual_year_arg not in (None, "", 0, "0"):
            meta.year = int(manual_year_arg)
            meta.search_year = manual_year_arg

    def list_to_string(self, list: list[str]) -> str:
        if len(list) == 1:
            return list[0]
        try:
            result = " ".join(list)
        except Exception:
            result = "None"
        return result

    def parse_tracker_id(self, value: str) -> tuple[str, str]:
        """Normalize ``--tracker-id`` values without exposing tracker-specific CLI flags."""
        from src.meta import Meta
        from src.trackersetup import get_tracker_comment_hosts, tracker_class_map

        candidate = value.strip()
        tracker_name = ""
        id_value = candidate
        if "=" in candidate and not candidate.startswith(("http://", "https://")):
            tracker_name, id_value = (part.strip() for part in candidate.split("=", 1))
            tracker_name = Meta.canonical_tracker_name(tracker_name)

        if id_value.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(id_value)
            host = (parsed.hostname or "").lower()
            matched_trackers = [
                name for name, domains in get_tracker_comment_hosts(self.config).items() if any(host == domain or host.endswith(f".{domain}") for domain in domains)
            ]
            if len(matched_trackers) != 1:
                raise ValueError(f"--tracker-id URL host is unknown or ambiguous: {host or id_value}")
            url_tracker = Meta.canonical_tracker_name(matched_trackers[0])
            if tracker_name and tracker_name != url_tracker:
                raise ValueError(f"--tracker-id tracker {tracker_name} does not match URL host {host}")
            tracker_name = url_tracker
            query = urllib.parse.parse_qs(parsed.query)
            id_value = (query.get("torrentid") or query.get("id") or [""])[0]
            if not id_value:
                path = parsed.path.rstrip("/")
                dotted_id = re.search(r"\.(\d+)$", path)
                id_value = dotted_id.group(1) if dotted_id else path.split("/")[-1]

        if tracker_name not in tracker_class_map:
            raise ValueError(f"--tracker-id requires a supported tracker name, got: {tracker_name or value}")
        if not id_value or not id_value.isdigit():
            raise ValueError(f"--tracker-id requires a numeric torrent ID, got: {value}")
        return tracker_name, id_value

    def parse_tmdb_id(self, id_str: str, category: str | None) -> tuple[str, int]:
        if category is None:
            category = ""
        parsed_id: str = id_str.lower().strip()
        if parsed_id.startswith("http"):
            parsed = urllib.parse.urlparse(parsed_id)
            path = parsed.path.strip("/")

            if "/" in path:
                parts = path.split("/")
                if len(parts) >= 2:
                    type_part = parts[-2]
                    id_part = parts[-1]

                    if type_part == "tv":
                        category = "TV"
                    elif type_part == "movie":
                        category = "MOVIE"

                    parsed_id = id_part

        if parsed_id.startswith("tv"):
            parsed_id = parsed_id.split("/")[1]
            category = "TV"
        elif parsed_id.startswith("movie"):
            parsed_id = parsed_id.split("/")[1]
            category = "MOVIE"
        else:
            parsed_id = parsed_id

        parsed_id_int = int(parsed_id) if parsed_id.isdigit() else 0

        return category, parsed_id_int
