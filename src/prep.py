import json
from pathlib import Path

# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, cast

from cogs.redaction import PathAwareEncoder
from src.meta import Meta

console: Any = None

try:
    import re
    import time

    import aiofiles

    import src.prep_helpers as prep_helpers
    from src.apply_overrides import ApplyOverrides
    from src.audio import AudioManager
    from src.book_prep import gather_book_prep as _gather_book_prep_fn
    from src.book_prep import resolve_book_filelist as _resolve_book_filelist_fn
    from src.console import logger
    from src.get_disc import DiscInfoManager
    from src.get_name import NameManager
    from src.get_tracker_data import TrackerDataManager
    from src.getseasonep import SeasonEpisodeManager
    from src.is_scene import SceneManager
    from src.languages import languages_manager
    from src.metadata_searching import MetadataSearchingManager
    from src.music.prep import gather_music_prep as _gather_music_prep_fn
    from src.prep_game import gather_game_prep as _gather_game_prep_fn
    from src.prep_game import resolve_game_filelist as _resolve_game_filelist_fn
    from src.radarr import RadarrManager
    from src.region import get_service
    from src.rehostimages import RehostImagesManager
    from src.sonarr import SonarrManager
    from src.tmdb import TmdbManager
    from src.tvdb import TvdbData

except ModuleNotFoundError:
    print("Missing Module Found. Please reinstall required dependencies from requirements.txt.")
    raise SystemExit(1) from None
except KeyboardInterrupt:
    exit()


class Prep:
    """
    Prepare for upload:
        Mediainfo/BDInfo
        Screenshots
        Database Identifiers (TMDB/IMDB/MAL/etc)
        Create Name
    """

    def __init__(self, screens: int, img_host: str, config: dict[str, Any]) -> None:
        self.screens = screens
        self.config = config
        self.img_host = img_host.lower()
        self.tvdb_handler = TvdbData(config)
        self.overrides = ApplyOverrides(config)
        self.audio_manager = AudioManager(config)
        self.disc_info_manager = DiscInfoManager(config)
        self.name_manager = NameManager(config)
        self.tracker_data_manager = TrackerDataManager(config)
        self.scene_manager = SceneManager(config)
        self.metadata_searching_manager = MetadataSearchingManager(config)
        self.tmdb_manager = TmdbManager(config)
        self.season_episode_manager = SeasonEpisodeManager(config)
        self.radarr_manager = RadarrManager(config)
        self.sonarr_manager = SonarrManager(config)
        self.rehost_images_manager = RehostImagesManager(config)

    @staticmethod
    def _resolve_book_filelist(
        meta: Meta,
        videoloc: str,
    ) -> tuple[str, list[str], str, str]:
        """Delegate to :func:`src.book_prep.resolve_book_filelist`."""
        return _resolve_book_filelist_fn(meta, videoloc)

    async def _gather_book_prep(
        self,
        meta: Meta,
        videopath: str,
        base_dir: str,
    ) -> None:
        """Delegate to :func:`src.book_prep.gather_book_prep`."""
        await _gather_book_prep_fn(meta, videopath, base_dir, self.config)

    @staticmethod
    def _resolve_game_filelist(
        meta: Meta,
        videoloc: str,
    ) -> tuple[str, list[str], str, str]:
        """Delegate to :func:`src.prep_game.resolve_game_filelist`."""
        return _resolve_game_filelist_fn(meta, videoloc)

    async def _gather_game_prep(
        self,
        meta: Meta,
        videopath: str,
        base_dir: str,
    ) -> None:
        """Delegate to :func:`src.prep_game.gather_game_prep`."""
        await _gather_game_prep_fn(meta, videopath, base_dir, self.config)

    async def _gather_music_prep(self, meta: Meta) -> None:
        """Run the non-destructive MUSIC pipeline instead of video preparation."""
        await _gather_music_prep_fn(meta, self.config)

    async def gather_prep(self, meta: Meta, mode: str) -> Meta:
        meta_start_time = time.time()

        # 1. Init metadata settings
        use_sonarr, use_radarr, client, skip_tracker_descriptions, hash_ids, tracker_ids = prep_helpers.init_meta(self, meta, mode)

        # 2. Disc and Category Detection
        videoloc, bdinfo = await prep_helpers.detect_disc_and_category(self, meta)

        # Music has its own release-oriented metadata pipeline.  It must not flow
        # through video/media-info, TMDB, screenshots or episode handling. It
        # still needs the shared tracker/client stage: qBittorrent path matching
        # supplies an existing infohash, which the later base-torrent reuse
        # stage exports and validates without rehashing the music release.
        if meta.category == "MUSIC":
            await self._gather_music_prep(meta)
            await prep_helpers.process_trackers_and_torrent(self, meta, client, hash_ids, tracker_ids, "", "")
            logger.debug(f"Music metadata processed in {time.time() - meta_start_time:.2f} seconds")
            return meta

        # 3. File information and basic media processing
        filename, untouched_filename, videopath, search_term, search_file_folder, mi, video = await prep_helpers.process_media_files(self, meta, videoloc, bdinfo)

        # 4. Calculate source size
        prep_helpers.calculate_source_size(self, meta, videopath)

        # 5. Conformance and validation
        await prep_helpers.validate_media(self, meta)

        # 6. Tracker and Existing Torrent Info
        await prep_helpers.process_trackers_and_torrent(self, meta, client, hash_ids, tracker_ids, search_term, search_file_folder)

        # 7. Sonarr, Radarr and Metadata Searches
        await prep_helpers.search_metadata(
            self, meta, filename, untouched_filename, videopath, search_term, search_file_folder, use_sonarr, use_radarr, skip_tracker_descriptions, client, bdinfo, mi
        )

        # 8. Set Final Metadata and tags
        await prep_helpers.finalize_metadata(self, meta, videopath, bdinfo, mi, filename, untouched_filename, video)

        await languages_manager.process_desc_language(meta)

        if meta.category == "BOOK":
            await self.rehost_images_manager.takescreens_manager.prepare_book_cover(videopath, meta.uuid, meta.base_dir, meta)
            meta_path = Path(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json")
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(meta_path, "w", encoding="utf-8") as meta_file:
                await meta_file.write(json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder))

        logger.debug(f"Metadata processed in {time.time() - meta_start_time:.2f} seconds")

        return meta

    def check_adult_media(self, meta) -> bool:
        adult_keywords = ["xxx", "erotic", "porn", "adult", "orgy"]
        if meta.tmdb_adult_media:
            return True
        keywords_str = ", ".join(meta.keywords)
        combined_genres_str = ", ".join(meta.combined_genres) if isinstance(meta.combined_genres, list) else str(meta.combined_genres)
        searchable = ", ".join(part for part in (keywords_str, combined_genres_str) if part)
        return any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", searchable, re.IGNORECASE) for keyword in adult_keywords)

    async def get_cat(self, _video: str, meta: Meta) -> str | None:
        if meta.manual_category:
            manual_category = meta.manual_category
            return manual_category.upper() if isinstance(manual_category, str) else None

        music_extensions = {".flac", ".mp3", ".m4a", ".mp4", ".aac", ".ac3", ".dts", ".wav", ".aiff", ".alac", ".ogg", ".opus", ".ape", ".wv"}
        candidate = Path(meta.path or "")
        if candidate.suffix.lower() in music_extensions:
            return "MUSIC"

        path_patterns = [
            r"(?i)[\\/](?:tv|tvshows|tv.shows|series|shows)[\\/]",
            r"(?i)[\\/](?:season\s*\d+|s\d+)[\\/]",
            r"(?i)[\\/](?:s\d{1,2}e\d{1,2}|s\d{1,2}|season\s*\d+)",
            r"(?i)(?:tv pack|season\s*\d+)",
        ]

        filename_patterns = [
            r"(?i)s\d{1,2}e\d{1,2}",
            r"(?i)s\d{1,2}",
            r"(?i)\b\d{1,2}x\d{2}\b",
            r"(?i)(?:season|series)\s*\d+",
            r"(?i)e\d{2,3}\s*\-",
            r"(?i)\d{4}\.\d{1,2}\.\d{1,2}",
        ]

        path = meta.path or ""
        uuid = meta.uuid
        logger.debug(f"[cyan]Checking category for path: {path} and uuid: {uuid}[/cyan]")

        for pattern in path_patterns:
            if re.search(pattern, path):
                logger.debug(f"[cyan]Matched TV pattern in path: {pattern}[/cyan]")
                return "TV"

        for pattern in filename_patterns:
            if re.search(pattern, uuid) or re.search(pattern, Path(path).name):
                logger.debug(f"[cyan]Matched TV pattern in filename: {pattern}[/cyan]")
                return "TV"

        if "subsplease" in path.lower() or "subsplease" in uuid.lower():
            anime_pattern = r"(?:\s-\s)?(\d{1,3})\s*\((?:\d+p|480p|480i|576i|576p|720p|1080i|1080p|2160p)\)"
            if re.search(anime_pattern, path.lower()) or re.search(anime_pattern, uuid.lower()):
                logger.debug(f"[cyan]Matched Anime pattern for SubsPlease: {anime_pattern}[/cyan]")
                return "TV"

        return "MOVIE"

    async def stream_optimized(self, stream_opt: bool) -> int:
        return 1 if stream_opt is True else 0

    async def parse_scene_nfo(self, meta: Meta) -> None:
        try:
            nfo_file = meta.scene_nfo_file

            if not nfo_file:
                logger.debug("[yellow]No NFO file found for scene release[/yellow]")
                return

            logger.debug(f"[cyan]Parsing NFO file: {nfo_file}[/cyan]")

            async with aiofiles.open(nfo_file, encoding="utf-8", errors="ignore") as f:
                nfo_content = await f.read()

            # Parse Source field
            source_match = re.search(r"^Source\s*:\s*(.+?)$", nfo_content, re.MULTILINE | re.IGNORECASE)
            if source_match:
                nfo_source = source_match.group(1).strip()
                logger.debug(f"[cyan]Found source in NFO: {nfo_source}[/cyan]")

                # Check if source matches any service
                services = cast(dict[str, str], await get_service(get_services_only=True))

                # Exact match
                for service_name, service_code in services.items():
                    if nfo_source.upper() == service_name.upper() or nfo_source.upper() == service_code.upper():
                        meta.service = service_code
                        meta.service_longname = service_name
                        logger.debug(f"[green]Matched service: {service_code} ({service_name})[/green]")
                        break

        except Exception as e:
            logger.debug(f"[red]Error parsing NFO file: {e}[/red]")
