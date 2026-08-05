# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import argparse
import datetime
import re
import sys
import urllib.parse
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from src.book_prep import detect_newspaper, sanitize_book_author, sanitize_book_language
from src.console import logger
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
  -tvmaze, --tvmaze          Specify the TVMaze id to use
  -tvdb, --tvdb              Specify the TVDB id to use
  --queue (queue name)       Process an entire folder (including files/subfolders) in a queue
  -mf, --manual_frames       Comma-separated list of frame numbers to use for screenshots
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

        parser.add_argument("path", nargs="*", help="Path to file/directory (in single/double quotes is best)")
        parser.add_argument(
            PATHS_FROM_STDIN_OPTION,
            action="store_true",
            required=False,
            help="Read one full path per line from standard input (finish an interactive paste with an empty line)",
        )
        parser.add_argument("--queue", nargs=1, required=False, help="(--queue queue_name) Process an entire folder (files/subfolders) in a queue")
        parser.add_argument("-lq", "--limit-queue", dest="limit_queue", nargs=1, required=False, help="Limit the amount of queue files processed", type=int, default=0)
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
            type=int,
            default=None,
        )
        parser.add_argument("-mf", "--manual_frames", nargs=1, required=False, help="Comma-separated frame numbers to use as screenshots", type=str, default=None)
        parser.add_argument(
            "-c",
            "--category",
            nargs=1,
            required=False,
            help="Category [movie, tv, fanres, book, game, music]",
            choices=["movie", "tv", "fanres", "book", "game", "music"],
            dest="manual_category",
        )
        parser.add_argument("--music-artist", nargs=1, required=False, help="MUSIC: main artist(s), separated by &", dest="music_artist")
        parser.add_argument("--music-album", nargs=1, required=False, help="MUSIC: album/release title", dest="music_album")
        parser.add_argument(
            "--music-media",
            nargs=1,
            required=False,
            type=str.casefold,
            choices=MUSIC_MEDIA_CHOICES,
            help="MUSIC: source medium (CD, WEB, Vinyl, DVD, BD, Soundboard, SACD, DAT, Cassette)",
            dest="music_media",
        )
        parser.add_argument(
            "--music-release-type",
            nargs=1,
            required=False,
            type=str.casefold,
            choices=MUSIC_RELEASE_TYPE_CHOICES,
            help="MUSIC: Orpheus release type (album, ep, single, compilation, live album, etc.)",
            dest="music_release_type",
        )
        parser.add_argument(
            "--music-release-year", nargs=1, required=False, type=int, help="MUSIC: concrete release/pressing year (not the original group year)", dest="music_release_year"
        )
        parser.add_argument("--music-edition-year", nargs=1, required=False, type=int, help="MUSIC: remaster/reissue/edition year", dest="music_edition_year")
        parser.add_argument("--music-label", nargs=1, required=False, help="MUSIC: label for this release", dest="music_label")
        parser.add_argument("--music-catalogue-number", nargs=1, required=False, help="MUSIC: catalogue number for this release", dest="music_catalogue_number")
        parser.add_argument("--music-genre", nargs=1, required=False, help="MUSIC: comma-separated genre override", dest="music_genres")
        parser.add_argument("--music-cover", nargs=1, required=False, help="MUSIC: public artwork URL or local cover image path", dest="music_cover")
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
        parser.add_argument(
            "-t",
            "--type",
            nargs=1,
            required=False,
            help="Type [DISC, REMUX, ENCODE, WEBDL, WEBRIP, HDTV, DVDRIP]",
            choices=["disc", "remux", "encode", "webdl", "web-dl", "webrip", "hdtv", "dvdrip"],
            dest="manual_type",
        )
        parser.add_argument(
            "--source",
            nargs=1,
            required=False,
            help="Source [Blu-ray, BluRay, DVD, DVD5, DVD9, HDDVD, WEB, HDTV, UHDTV, LaserDisc, DCP]",
            choices=["Blu-ray", "BluRay", "DVD", "DVD5", "DVD9", "HDDVD", "WEB", "HDTV", "UHDTV", "LaserDisc", "DCP"],
            dest="manual_source",
        )
        parser.add_argument(
            "-res",
            "--resolution",
            nargs=1,
            required=False,
            help="Resolution [2160p, 1080p, 1080i, 720p, 576p, 576i, 480p, 480i, 8640p, 4320p, OTHER]",
            choices=["2160p", "1080p", "1080i", "720p", "576p", "576i", "480p", "480i", "8640p", "4320p", "other"],
        )
        parser.add_argument("-tmdb", "--tmdb", nargs=1, required=False, help="TMDb ID (use movie/ or tv/ prefix)", type=str, dest="tmdb_manual")
        parser.add_argument("-imdb", "--imdb", nargs=1, required=False, help="IMDb ID", type=str, dest="imdb_manual")
        parser.add_argument("-mal", "--mal", nargs=1, required=False, help="MAL ID", type=str, dest="mal_manual")
        parser.add_argument("-tvmaze", "--tvmaze", nargs=1, required=False, help="TVMAZE ID", type=str, dest="tvmaze_manual")
        parser.add_argument("-tvdb", "--tvdb", nargs=1, required=False, help="TVDB ID", type=str, dest="tvdb_manual")
        parser.add_argument("-douban", "--douban", nargs=1, required=False, help="Douban ID (Number only)", type=int, dest="douban_manual", default=0)
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
        parser.add_argument("-year", "--year", dest="manual_year", nargs=1, required=False, help="Override the year found", type=int, default=0)
        parser.add_argument("-author", "--author", nargs="*", required=False, help="Book/Audiobook author name (overrides auto-detected value)", type=str, dest="book_author")
        parser.add_argument("-btitle", "--book-title", nargs="*", required=False, help="Book/Audiobook title (overrides auto-detected value)", type=str, dest="book_title")
        parser.add_argument("--book-cover", nargs=1, required=False, help="BOOK: public artwork URL or local cover image path", dest="book_cover")
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
        parser.add_argument(
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
        parser.add_argument(
            "-gsc",
            "--game-subcategory",
            nargs=1,
            required=False,
            help="Game subcategory (full_game, full_game_dlc, dlc, update)",
            type=str.lower,
            choices=["full_game", "full_game_dlc", "dlc", "update"],
            dest="game_subcategory",
        )
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
        parser.add_argument("-ptp", "--ptp", nargs=1, required=False, help="PASSTHEPOPCORN torrent id/permalink", type=str)
        parser.add_argument("-blu", "--blu", nargs=1, required=False, help="BLUTOPIA torrent id/link", type=str)
        parser.add_argument("-aither", "--aither", nargs=1, required=False, help="AITHER torrent id/link", type=str)
        parser.add_argument("-lst", "--lst", nargs=1, required=False, help="LST torrent id/link", type=str)
        parser.add_argument("-oe", "--oe", nargs=1, required=False, help="ONLYENCODES torrent id/link", type=str)
        parser.add_argument("-hdb", "--hdb", nargs=1, required=False, help="HDBITS torrent id/link", type=str)
        parser.add_argument("-btn", "--btn", nargs=1, required=False, help="BTN torrent id/link", type=str)
        parser.add_argument("-bhd", "--bhd", nargs=1, required=False, help="BEYONDHD torrent_id/link", type=str)
        parser.add_argument("--orpheus", nargs=1, required=False, help="Orpheus torrent id/permalink (MUSIC metadata enrichment)", type=str)
        parser.add_argument("-huno", "--huno", nargs=1, required=False, help="HAWKEUNO torrent id/link", type=str)
        parser.add_argument("-ulcx", "--ulcx", nargs=1, required=False, help="ULCX torrent id/link", type=str)
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
        parser.add_argument(
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
            type=float,
        )
        parser.add_argument(
            "-debug", "--debug", action="store_true", required=False, help="Debug Mode, will run through all the motions providing extra info, but will not upload to trackers."
        )
        parser.add_argument("-ffdebug", "--ffdebug", action="store_true", required=False, help="Will show info from ffmpeg while taking screenshots.")
        parser.add_argument(
            "-uptimer", "--upload-timer", action="store_true", required=False, help="Prints the time it takes to upload to each individual site.", dest="upload_timer"
        )
        parser.add_argument(
            "-mps",
            "--max-piece-size",
            nargs=1,
            required=False,
            help="Set max piece size allowed in MiB for default torrent creation (default 128 MiB)",
            choices=["1", "2", "4", "8", "16", "32", "64", "128"],
        )
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
        parser.add_argument("-client", "--client", nargs=1, required=False, help="Use this torrent client instead of default")
        parser.add_argument("-qbt", "--qbit-tag", dest="qbit_tag", nargs=1, required=False, help="Add to qbit with this tag")
        parser.add_argument("-qbc", "--qbit-cat", dest="qbit_cat", nargs=1, required=False, help="Add to qbit with this category")
        parser.add_argument(
            "-qbcon", "--qbit-bw-control", action="store_true", required=False, help="Enable qBittorrent bandwidth control logic before upload", dest="qbit_bandwidth_control"
        )
        parser.add_argument(
            "-qbcrl", "--qbit-bw-threshold", nargs=1, required=False, help="qBittorrent bandwidth limit threshold (KB/s)", type=int, dest="qbit_bandwidth_threshold"
        )
        parser.add_argument(
            "-qbctime", "--qbit-bw-time", nargs=1, required=False, help="Time to stay under qBittorrent threshold (seconds)", type=int, dest="qbit_bandwidth_time"
        )
        parser.add_argument(
            "-uo",
            "--upload-order",
            dest="upload_order",
            nargs=1,
            required=False,
            choices=["concurrent", "usenet", "tracker"],
            help="Set the upload order when both torrent trackers and Usenet are selected ('concurrent', 'usenet', 'tracker')",
        )
        parser.add_argument("-rtl", "--rtorrent-label", dest="rtorrent_label", nargs=1, required=False, help="Add to rtorrent with this label")
        parser.add_argument("-tk", "--trackers", nargs=1, required=False, help="Upload to these trackers, comma separated (--trackers blu,bhd) including manual")
        parser.add_argument(
            "-rtk",
            "--trackers-remove",
            dest="trackers_remove",
            nargs=1,
            required=False,
            help="Remove these trackers when processing default trackers, comma separated (--trackers-remove blu,bhd)",
        )
        parser.add_argument(
            "-tpc",
            "--trackers-pass",
            dest="trackers_pass",
            nargs=1,
            required=False,
            help="How many trackers need to pass all checks (dupe/banned group/etc) to actually proceed to uploading",
            type=int,
        )
        parser.add_argument("-rt", "--randomized", nargs=1, required=False, help="Number of extra, torrents with random infohash", default=0)
        parser.add_argument(
            "-entropy",
            "--entropy",
            dest="entropy",
            nargs=1,
            required=False,
            help="Use entropy in created torrents. (32 or 64) bits (ie: -entropy 32). Not supported at all sites, you many need to redownload the torrent",
            type=int,
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
                        meta[key] = int(value2)
                    elif key == "season":
                        meta.manual_season = value2
                    elif key == "episode":
                        meta.manual_episode = value2
                    elif key == "manual_date":
                        meta.manual_date = value2
                    elif key == "tmdb_manual":
                        meta.category, meta.tmdb_manual = self.parse_tmdb_id(value2, meta.category)
                    elif key == "ptp":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                meta.ptp = urllib.parse.parse_qs(parsed.query)["torrentid"][0]
                            except Exception:
                                logger.info("[red]Your terminal ate  part of the url, please surround in quotes next time, or pass only the torrentid")
                                logger.info("[red]Continuing without -ptp")
                        else:
                            meta.ptp = value2
                    elif key == "blu":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                blupath = parsed.path
                                if blupath.endswith("/"):
                                    blupath = blupath[:-1]
                                meta.blu = blupath.split("/")[-1]
                            except Exception:
                                logger.info("[red]Unable to parse id from url")
                                logger.info("[red]Continuing without --blu")
                        else:
                            meta.blu = value2
                    elif key == "aither":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                aitherpath = parsed.path
                                if aitherpath.endswith("/"):
                                    aitherpath = aitherpath[:-1]
                                meta.aither = aitherpath.split("/")[-1]
                            except Exception:
                                logger.info("[red]Unable to parse id from url")
                                logger.info("[red]Continuing without --aither")
                        else:
                            meta.aither = value2
                    elif key == "lst":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                lstpath = parsed.path
                                if lstpath.endswith("/"):
                                    lstpath = lstpath[:-1]
                                meta.lst = lstpath.split("/")[-1]
                            except Exception:
                                logger.info("[red]Unable to parse id from url")
                                logger.info("[red]Continuing without --lst")
                        else:
                            meta.lst = value2
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
                    elif key == "oe":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                oepath = parsed.path
                                if oepath.endswith("/"):
                                    oepath = oepath[:-1]
                                meta.oe = oepath.split("/")[-1]
                            except Exception:
                                logger.info("[red]Unable to parse id from url")
                                logger.info("[red]Continuing without --oe")
                        else:
                            meta.oe = value2
                    elif key == "ulcx":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                ulcxpath = parsed.path
                                if ulcxpath.endswith("/"):
                                    ulcxpath = ulcxpath[:-1]
                                meta.ulcx = ulcxpath.split("/")[-1]
                            except Exception:
                                logger.info("[red]Unable to parse id from url")
                                logger.info("[red]Continuing without --ulcx")
                        else:
                            meta.ulcx = value2
                    elif key == "hdb":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                meta.hdb = urllib.parse.parse_qs(parsed.query)["id"][0]
                            except Exception:
                                logger.info("[red]Your terminal ate  part of the url, please surround in quotes next time, or pass only the torrentid")
                                logger.info("[red]Continuing without -hdb")
                        else:
                            meta.hdb = value2

                    elif key == "btn":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                meta.btn = urllib.parse.parse_qs(parsed.query)["id"][0]
                            except Exception:
                                logger.info("[red]Your terminal ate  part of the url, please surround in quotes next time, or pass only the torrentid")
                                logger.info("[red]Continuing without -hdb")
                        else:
                            meta.btn = value2

                    elif key == "bhd":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                bhdpath = parsed.path
                                if bhdpath.endswith("/"):
                                    bhdpath = bhdpath[:-1]

                                if "/download/" in bhdpath or "/torrents/" in bhdpath:
                                    torrent_id_match = re.search(r"\.(\d+)$", bhdpath)
                                    if torrent_id_match:
                                        meta.bhd = torrent_id_match.group(1)
                                    else:
                                        meta.bhd = bhdpath.split("/")[-1]
                                else:
                                    meta.bhd = bhdpath.split("/")[-1]

                                logger.info(f"[green]Parsed BEYONDHD torrent ID: {meta.bhd}")
                            except Exception as e:
                                logger.info(f"[red]Unable to parse id from url: {e}")
                                logger.info("[red]Continuing without --bhd")
                        else:
                            meta.bhd = value2

                    elif key == "orpheus":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            torrent_id = urllib.parse.parse_qs(parsed.query).get("torrentid", [""])[0]
                            if torrent_id.isdigit():
                                meta.orpheus = torrent_id
                            else:
                                logger.info("[red]Unable to parse torrentid from --orpheus URL; pass a torrent ID or permalink.[/red]")
                        elif value2.isdigit():
                            meta.orpheus = value2
                        else:
                            logger.info("[red]Invalid --orpheus value; pass a numeric torrent ID or permalink.[/red]")

                    elif key == "huno":
                        if value2.startswith("http"):
                            parsed = urllib.parse.urlparse(value2)
                            try:
                                hunopath = parsed.path
                                if hunopath.endswith("/"):
                                    hunopath = hunopath[:-1]
                                meta.huno = hunopath.split("/")[-1]
                            except Exception:
                                logger.info("[red]Unable to parse id from url")
                                logger.info("[red]Continuing without --huno")
                        else:
                            meta.huno = value2

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
                        meta[key] = int(value_list[0])
                    else:
                        meta[key] = 0
                elif value not in (None, [], 0, ""):
                    meta[key] = int(str(value))
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
                        meta[key] = float(value_list[0])
                    else:
                        meta[key] = None
                elif value not in (None, [], ""):
                    meta[key] = float(str(value))
                else:
                    meta[key] = None
            if key in ("freeleech"):
                if isinstance(value, list):
                    value_list = [str(item) for item in value]
                    if len(value_list) == 1 and value_list[0] != "":
                        meta[key] = int(value_list[0])
                    else:
                        meta[key] = 0
                elif value not in (None, [], 0, ""):
                    meta[key] = int(str(value))
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

        book_cover_arg = meta.book_cover
        if book_cover_arg not in (None, "", []):
            cover = " ".join(str(x) for x in book_cover_arg if str(x)).strip() if isinstance(book_cover_arg, list) else str(book_cover_arg).strip()
            if cover.startswith(("http://", "https://")):
                meta.artwork_url = cover
            elif cover:
                cover_path = Path(cover).expanduser()
                if cover_path.is_file():
                    meta.artwork_path = str(cover_path.resolve())
                else:
                    logger.warning("[yellow]BOOK: --book-cover is neither a public HTTP(S) URL nor an existing image file; ignoring it.[/yellow]")

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
