# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Custom Meta class to support attribute access on metadata."""

from dataclasses import MISSING, dataclass, field, fields
from typing import Any

from src.app_paths import STATE_DIR

_TRACKER_ID_ALIASES = {
    "ANT": "ANTHELION",
    "BHD": "BEYONDHD",
    "BLU": "BLUTOPIA",
    "BTN": "BROADCASTHENET",
    "DVL": "DREADVAULT",
    "BROADCASTHENET": "BROADCASTHENET",
    "HDB": "HDBITS",
    "HUNO": "HAWKEUNO",
    "OE": "ONLYENCODES",
    "PTP": "PASSTHEPOPCORN",
    "RHD": "ROCKETHD",
    "FLD": "FLOOD",
}


@dataclass(init=False)
class Meta:
    """
    Custom metadata class that behaves as a dataclass but with support
    for backward compatibility and helper dictionary methods.
    """

    adult_media: bool = False
    aither_trumpable: list[Any] | None = field(default_factory=list)
    aka: str = ""
    anime: bool = False
    anon: bool = False
    ant_user_tags: bool | None = None
    archive_password: str | None = None
    args_line_queue: bool | None = None
    artist: str = ""
    artwork_banner_path: str | None = None
    artwork_path: str = ""
    artwork_url: str = ""
    explicit_banner: str = ""
    explicit_poster: str = ""
    asian: bool = False
    asin: str = ""
    ask_dupe: bool = False
    audio_bitrate: int | None = None
    audio_languages: list[str] | None = field(default_factory=list)
    audio_spectrogram_tracks: str | None = None
    audio_spectrogram: bool | None = None
    dynamic_hdr_plot: bool | None = None
    audio: str = ""
    audiobook_bitrate: int | None = None
    audiobook_duration_formatted: str | None = None
    audiobook_duration: float | None = None
    audiobook: bool = False
    author: str = ""
    auto_episode_title: str | None = None
    auto_nfo: bool = False
    available_platforms: list[Any] = field(default_factory=list)
    backdrop: str = ""
    base_dir: str = field(default_factory=lambda: str(STATE_DIR))
    base_reuse_torrent_path: str | None = None
    base_torrent_created: bool | None = None
    base_torrent_piece_mb: int = 0
    basename_no_ext: str = ""
    bdinfo: dict[str, Any] = field(default_factory=dict)
    bhd_nfo: bool | None = None
    bit_depth: str = ""
    bloated: bool = False
    bluray_audio_skip: bool = False
    bluray_cover_urls: dict[str, Any] = field(default_factory=dict)
    bluray_score: int = 100
    bluray_single_score: int = 100
    book_asin: str | None = None
    book_author: str | None = None
    book_isbn: str | None = None
    book_language_iso: str = ""
    book_language: str = ""
    book_overview: str | None = None
    book_publisher: str | None = None
    book_series_index: str = ""
    book_series: str = ""
    book_title: str | None = None
    book_translator: str | None = None
    cast: list[str] = field(default_factory=list)
    category_id: str | None = None
    category: str = ""
    channels: str = ""
    clean_name: str = ""
    cleanup: bool = False
    client: str | None = None
    combined_genres: list[str] | str = field(default_factory=list)
    comic: bool = False
    comparison_groups: dict[str, dict[str, Any]] | list[dict[str, Any]] = field(default_factory=dict)
    comparison_index: int | None = None
    comparison: str | None = None
    console_game: bool = False
    container: str = ""
    country: int | None = None
    current_version: str = ""
    cutoff: int = 1
    daily_episode_title: str = ""
    debug: bool = False
    delete_meta: bool = False
    delete_tmp: bool = False
    demographic: str = ""
    description_file_content: str = ""
    description_file: str = ""
    description_inline: str = ""
    description_link_content: str = ""
    description_link: str = ""
    description_nfo_content: str = ""
    description_template_content: str | None = None
    description_template: str | None = None
    description: str = ""
    developer: str | None = None
    directors: list[str] | None = None
    discs_missing_certificate: list[Any] = field(default_factory=list)
    discs: list[Any] = field(default_factory=list)
    disctype: str = ""
    distributor_link: str = ""
    distributor: str = ""
    diy_disc: bool = False
    douban_id: int = 0
    douban_manual: int | str | None = None
    douban_rating: float | str | None = None
    douban_votes: int | str | None = None
    doubleup: bool = False
    double_upload_until: int = 0
    downloaded_bluray_cover_paths: dict[str, str] = field(default_factory=dict)
    draft: bool | None = None
    dual_audio: bool = False
    dupe_again: bool = False
    dupe_checked_trackers: list[Any] = field(default_factory=list)
    dupe_size_difference_tolerance: float | None = None
    dupe: bool = False
    dvd_size: str = ""
    edit: bool = False
    edition: str = ""
    eng_subs: int | None = None
    entropy: int | str | None = None
    episode_airdate: str | None = None
    episode_int: int = 0
    episode_name: str = ""
    episode_overview: str = ""
    episode_title: str = ""
    episode_tmdb_data: dict[str, Any] = field(default_factory=dict)
    episode: str = ""
    episodes: list[dict[str, Any]] | None = None
    epubmeta_output: str | None = None
    exclusive: bool = False
    ext_torrenthash: str | None = None
    extra_openlibrary_ids: int | None = None
    extras: bool | None = None
    featured: bool = False
    ffdebug: bool = False
    file_count_match: int | bool = False
    filelist: list[Any] = field(default_factory=list)
    filename_match: str | bool = False
    filename: str = ""
    first_air_date: str | None = None
    flux: bool = False
    folder_id: int | None = None
    force_recheck: bool = False
    foreign: bool = False
    format: str = ""
    found_preferred_piece_size: str | None = None
    found_tracker_match: bool | None = None
    frame_info_map: dict[str, Any] = field(default_factory=dict)
    frame_overlay: bool = False
    frame_rate: float | None = None
    framestor: bool | None = None
    freeleech: int = 0
    freeleech_until: int = 0
    game_region: str = ""
    game_subcategory: str = ""
    game_system: str = ""
    game_version: str = ""
    genre_ids: int | None = None
    genre: str = ""
    genres: list[str] = field(default_factory=list)
    hardcoded_subs: bool = False
    hardcoded_subs_language: str | None = None
    has_commentary: bool = False
    has_encode_settings: bool = False
    has_languages: str = ""
    has_multiple_default_audio_tracks: bool = False
    has_multiple_default_subtitle_tracks: bool = False
    has_subs: bool | int = False
    hash_used: str | None = None
    hdb_description: str | None = None
    hdb_name: str | None = None
    HDDVD_PLAYLIST: dict[str, Any] | None = None
    hdr: str = ""
    HDR: str = ""
    hfr: bool | None = None
    hosted_artwork: list[dict[str, Any]] | None = None
    igdb_first_release_date: str = ""
    igdb_id: int = 0
    igdb_manual: str | None = None
    igdb_rating_count: int | str = ""
    igdb_rating: float | str = ""
    image_list: list[dict[str, Any]] = field(default_factory=list)
    image_sizes: dict[str, Any] = field(default_factory=dict)
    imdb_id: int | None = None
    imdb_info: dict[str, Any] = field(default_factory=dict)
    imdb_manual: str | int | None = None
    imdb_mismatch: bool = False
    imdb_rating: str = ""
    imdb_tt: str = ""
    imdb: str | None = ""
    imghost: str = ""
    imghost_from_cli: bool = False
    infohash: str = ""
    initial_dupes: dict[str, Any] = field(default_factory=dict)
    is_disc: str = ""
    pre_release: bool = False
    isbn: str = ""
    isdir: bool = False
    item_args: list[str] | None = None
    keep_folder: bool = False
    keep_images: bool = False
    keep_nfo: bool = False
    keywords: list[str] = field(default_factory=list)
    language_checked: bool = False
    language: str = ""
    languages: dict[str, list[str]] | list[Any] = field(default_factory=list)
    last_air_date: str | None = None
    libplacebo_warmed: bool | None = None
    libplacebo: bool = False
    limit_queue: int = 0
    linking_failed: bool = False
    localized_overviews: dict[str, Any] = field(default_factory=dict)
    logo: str = ""
    magazine: bool = False
    mal_id: int = 0
    mal_manual: str | int | None = None
    mal: int | None = None
    manga: bool = False
    manual_category: str | None = None
    manual_commentary: bool = False
    manual_data: str | None = None
    manual_date: str | None = None
    manual_cast: list[str] = field(default_factory=list)
    manual_dvds: str | None = None
    manual_edition: str | list[str] | None = None
    manual_episode_title: str = ""
    manual_episode: str | int | None = None
    manual_frames: str | list[int] | list[str] | None = None
    manual_language: str | dict[str, Any] | None = None
    manual_multi: bool = False
    manual_name: str | None = None
    manual_platform: str | None = None
    manual_season: str | int | None = None
    manual_source: str | None = None
    manual_type: str | None = None
    manual_year: int = 0
    manual: bool = False
    matched_episode_ids: int | None = None
    matched_tracker: str = ""
    max_piece_size: int = 0
    mediainfo: dict[str, Any] = field(default_factory=dict)
    menu_images: list[Any] = field(default_factory=list)
    mismatched_imdb_id: int = 0
    mkbrr_threads: str | int | None = None
    mkbrr: bool = False
    mode: str = ""
    modq: bool = False
    mteam_description: str = ""
    music_album: str = ""
    music_artist: str = ""
    music_catalogue_number: str = ""
    music_discogs_enabled: bool = True
    music_discogs_id: str = ""
    music_discogs_master_id: str = ""
    music_discogs_release_id: str = ""
    music_edition_year: int = 0
    music_enrichment: bool | None = None
    music_genres: str = ""
    music_label: str = ""
    music_media: str = ""
    music_release_type: str = ""
    music_release_year: int = 0
    music_release: dict[str, Any] = field(default_factory=dict)
    name_notag: str = ""
    name: str = ""
    narrator: str = ""
    networks: str | list[dict[str, Any]] = ""
    newspaper: bool = False
    nexusphp_description: str = ""
    nfo: bool = False
    no_aka: bool = False
    no_dual: bool = False
    no_dub: bool = False
    no_edition: bool = False
    no_ids: bool = False
    no_imdb: bool = False
    no_override: bool = False
    no_season: bool = False
    no_seed: bool = False
    no_subs: bool = False
    no_tag: bool = False
    no_tracker_match: bool = False
    no_year: bool = False
    nohash: bool = False
    non_disc_has_pcm_audio_tracks: bool = False
    not_anime: bool = False
    nzb_path: str = ""
    ocr: bool | None = None
    only_id: bool | None = None
    openlibrary_book_id: int | None = None
    openlibrary_id: int | None = None
    openlibrary: str | None = None
    opera: bool = False
    origin_country_code: list[str] | None = None
    origin_country: list[Any] = field(default_factory=list)
    original_category: str = ""
    original_imdb: int = 0
    original_language: str | None = None
    original_mal: int = 0
    original_title: str = ""
    original_tmdb: int = 0
    original_tvdb: int = 0
    original_tvmaze: int = 0
    overview_meta: str = ""
    overview: str = ""
    part: str = ""
    path_to_menu_screenshots: str = ""
    path: str | None = None
    personalrelease: bool = False
    piece_size_constraints_enabled: str | bool = False
    platform: str = ""
    potential_missing: list[Any] = field(default_factory=list)
    prefer_small_pieces: bool = False
    print_tracker_links: bool = True
    print_tracker_messages: bool = False
    production_companies: list[Any] = field(default_factory=list)
    production_countries: list[Any] = field(default_factory=list)
    ptgen: dict[str, Any] = field(default_factory=dict)
    ptp_groupid: str | None = None
    publisher: str = ""
    qbit_bandwidth_control: bool = False
    qbit_bandwidth_threshold: int = 0
    qbit_bandwidth_time: int = 0
    qbit_cat: str | None = None
    qbit_tag: str | None = None
    queue: str = ""
    quickie_search: bool = False
    randomized: int = 0
    regex_secondary_title: str = ""
    regex_title: str = ""
    regex_year: str = ""
    region: str = ""
    refundable: bool = False
    rehash: bool = False
    rehosted_artwork_url: str | None = None
    release_date: str = ""
    release_dates: dict[str, Any] | None = None
    release_url: str = ""
    remove_trackers: list[str] | bool = False
    repack: str = ""
    requested_trackers: list[str] | None = None
    requirements_minimum: str = ""
    requirements_recommended: str = ""
    resolution: str = ""
    retake_call_count: int | None = None
    retake: bool = False
    retrieved_aka: str | None = None
    retry_count: int = 0
    reuse_torrent_client: str | None = None
    reuse_torrent_path: str | None = None
    rtorrent_label: str | None = None
    runtime: int = 60
    saved_description: bool | None = None
    description_candidates: list[dict[str, Any]] = field(default_factory=list)
    description_override: str = ""
    description_fingerprint: str = ""
    description_provenance: dict[str, Any] = field(default_factory=dict)
    tracker_description_raw: dict[str, str] = field(default_factory=dict)
    tracker_ids: dict[str, str] = field(default_factory=dict)
    tracker_description_mode: str = ""
    tracker_search_term: str = ""
    persist_description: bool = True
    scene_name: str = ""
    scene_nfo_file: str = ""
    scene: bool = False
    screens: int = 0
    screenshots_in_description: bool | None = None
    screenshots_reported_torrent: list[str] | None = None
    screenshots_trumping_torrent: list[str] | None = None
    sd: int | bool = False
    sdh_subs: int | None = None
    search_requests: bool = False
    search_year: int | str = ""
    season_air_first_date: str | None = None
    season_int: int = 0
    season_name: str = ""
    season_pack_contains_episode: bool | None = None
    season_pack_exists: bool = False
    season_pack_id: int | str | None = None
    season_pack_link: str | None = None
    season_pack_name: str = ""
    season: int | str | None = 0
    secondary_title: str | None = None
    service_longname: str = ""
    service: str | None = None
    sfx_subtitles: bool = False
    silent: bool = False
    site_check: bool = False
    site_upload_queue: bool | None = None
    site_upload: str | None = None
    size_match: str | bool = False
    skip_auto_torrent: bool = False
    skip_gen_desc: bool = False
    skip_imghost_upload: bool = False
    skip_tracker_descriptions: bool = False
    skip_trackers: bool = False
    skip_upload_trackers: list[Any] = field(default_factory=list)
    skip_uploading: int | bool = False
    skipit: bool = False
    skipping: str | None = None
    sorted_filelist: bool = False
    source_size: int = 0
    source: str | None = None
    spd_channel: str = ""
    spectrograms_images: list[Any] = field(default_factory=list)
    dynamic_hdr_plot_images: list[Any] = field(default_factory=list)
    steam_manual: str | None = None
    steam_url: str | None = None
    sticky: bool = False
    stream: bool = False
    studios: list[str] | str | None = None
    subs_reuse_torrent_path: str | None = None
    subtitle_files: list[Any] = field(default_factory=list)
    subtitle_languages: list[str] | str | None = field(default_factory=list)
    tag: str | None = None
    three_d: str = ""
    title: str = ""
    tmdb_adult_media: bool = False
    tmdb_cast: list[Any] = field(default_factory=list)
    tmdb_directors: list[Any] = field(default_factory=list)
    tmdb_episode_data: dict[str, Any] | None = None
    tmdb_id: int | None = None
    tmdb_localized_data: dict[str, Any] = field(default_factory=dict)
    tmdb_logo: str = ""
    tmdb_manual: int | str | None = None
    tmdb_poster_path: str = ""
    tmdb_season_data: dict[str, Any] | None = None
    tmdb_type: str = ""
    tmdb: int | None = None
    tonemapped: bool = False
    torrent_comments: list[Any] = field(default_factory=list)
    tracker_image_collections: dict[str, dict[str, list[dict[str, Any]]]] = field(default_factory=dict)
    tracker_status: dict[str, Any] = field(default_factory=dict)
    trackers_pass: int | None = None
    trackers_remove: str | bool = False
    trackers: list[str] | str = field(default_factory=list)
    transmission_label: str | None = None
    trump_reason: str | None = None
    trumpable_id: int | str | None = None
    trumping_trackers: list[Any] = field(default_factory=list)
    tv_movie: bool = False
    tv_pack: bool = False
    tvdb_episode_data: dict[str, Any] = field(default_factory=dict)
    tvdb_episode_id: int | None = None
    tvdb_episode_int: int | None = None
    tvdb_episode_name: str | None = None
    tvdb_episode_year: str = ""
    tvdb_episode: int | None = None
    tvdb_id: int | None = None
    tvdb_imdb_id: str | None = None
    tvdb_manual: str | int | None = None
    tvdb_overview: str | None = None
    tvdb_search_results: list[dict[str, Any]] | None = None
    tvdb_season_int: int | None = None
    tvdb_season_name: str = ""
    tvdb_season: int | str | None = None
    tvdb_series_name: str | None = None
    tvdb_series_year: int | None = None
    tvdb: int | None = None
    tvmaze_episode_data: dict[str, Any] = field(default_factory=dict)
    tvmaze_id: int | str | None = None
    tvmaze_manual: int = 0
    tvmaze: int | str | None = None
    type: str | None = None
    ua_name: str = ""
    ua_signature: str = ""
    uhd: str | bool = False
    unattended_audio_skip: bool = False
    unattended_confirm: bool = False
    unattended_subtitle_skip: bool = False
    unattended: bool = False
    unit3d: bool | None = None
    untouched: bool = False
    upload_order: str | None = None
    upload_timer: bool = True
    uploader_comments: str = ""
    use_bluray_images: bool = False
    usenet_archive_password_is_random: bool | None = None
    usenet_subject: str | None = None
    usenet: bool = False
    uuid: str = ""
    valid_mi_settings: bool | None = None
    valid_mi: bool | None = None
    vapoursynth: bool = False
    video_bitrate: int | None = None
    video_codec: str = ""
    video_duration: int | None = 0
    video_encode: str = ""
    video_height: int | None = None
    video_width: int | None = None
    video: str = ""
    we_are_uploading: bool = False
    we_asked_tvmaze: bool = False
    we_asked: bool = False
    we_checked_them_all: bool = False
    we_checked_tmdb: bool = False
    we_checked_tvdb: bool = False
    we_need_tag: bool = False
    we_rechecked_torrent: bool = False
    webdv: bool = False
    webui: str | None = None
    were_trumping: bool = False
    write_audio_languages: bool | None = None
    write_hc_languages: bool | None = None
    write_subtitle_languages: bool | None = None
    year: int | None = None
    youtube: str | None = ""

    def __init__(self, _data: dict[str, Any] | None = None, **kwargs: Any) -> None:
        # Initialize default values
        for f in fields(self):
            if f.default is not MISSING:
                setattr(self, f.name, f.default)
            elif f.default_factory is not MISSING:
                setattr(self, f.name, f.default_factory())
            else:
                setattr(self, f.name, None)

        # Override with data or kwargs
        if _data:
            for k, v in _data.items():
                setattr(self, k, v)
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not self.base_dir:
            self.base_dir = str(STATE_DIR)
        self.set_tracker_ids(self.tracker_ids)

    def copy(self) -> Meta:
        """Ensure copy returns a Meta instance with deep copied attributes."""
        import copy

        return copy.deepcopy(self)

    def __copy__(self) -> Meta:
        return Meta(self.to_dict())

    def __deepcopy__(self, memo: Any) -> Meta:
        import copy

        copied_dict = {k: copy.deepcopy(self[k], memo) for k in self.to_dict()}
        return Meta(copied_dict)

    def populate_cast(self, limit: int = 5) -> None:
        """Build the canonical cast list from manual, IMDb, and TMDb sources."""
        source_lists = [self.manual_cast, self.imdb_info.get("stars", []) if isinstance(self.imdb_info, dict) else [], self.tmdb_cast]
        names: list[str] = []
        seen: set[str] = set()

        for source in source_lists:
            values = source.split(",") if isinstance(source, str) else source if isinstance(source, list) else []
            for value in values:
                if not isinstance(value, str):
                    continue
                name = " ".join(value.split())
                key = name.casefold()
                if not name or key in seen:
                    continue
                seen.add(key)
                names.append(name)
                if len(names) >= limit:
                    self.cast = names
                    return

        self.cast = names

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary representing defined fields."""
        res = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if val is not None:
                res[f.name] = val
        return res

    def items(self) -> Any:
        """Return dict-like items view."""
        return self.to_dict().items()

    def keys(self) -> Any:
        """Return dict-like keys view."""
        return self.to_dict().keys()

    def values(self) -> Any:
        """Return dict-like values view."""
        return self.to_dict().values()

    def update(self, other: dict[str, Any] | Meta) -> None:
        """Update attributes from a dictionary or another Meta instance."""
        if isinstance(other, Meta):
            for f in fields(other):
                val = getattr(other, f.name)
                setattr(self, f.name, val)
        else:
            for k, v in other.items():
                setattr(self, k, v)

    @staticmethod
    def canonical_tracker_name(tracker_name: str) -> str:
        """Return the canonical tracker name for an accepted alias."""
        normalized_name = tracker_name.upper()
        return _TRACKER_ID_ALIASES.get(normalized_name, normalized_name)

    def get_tracker_id(self, tracker_name: str) -> str | None:
        """Return the known torrent ID for a tracker."""
        key = self.canonical_tracker_name(tracker_name)
        value = self.tracker_ids.get(key)
        return str(value) if value is not None else None

    def set_tracker_ids(self, tracker_ids: dict[str, str | int]) -> None:
        """Persist tracker torrent IDs under their canonical tracker names."""
        normalized: dict[str, str] = {}
        for tracker_name, torrent_id in (self.tracker_ids or {}).items():
            normalized[self.canonical_tracker_name(str(tracker_name))] = str(torrent_id)
        for tracker_name, torrent_id in (tracker_ids or {}).items():
            key = self.canonical_tracker_name(str(tracker_name))
            value = str(torrent_id)
            normalized[key] = value
        self.tracker_ids = normalized

    def clear_tracker_id(self, tracker_name: str) -> None:
        """Forget a tracker torrent ID."""
        key = self.canonical_tracker_name(tracker_name)
        self.tracker_ids.pop(key, None)

    def get(self, key: str, default: Any = None) -> Any:
        """Get attribute value by name, returning default if not set or None."""
        try:
            val = getattr(self, key)
            return val if val is not None else default
        except AttributeError:
            return default

    def setdefault(self, key: str, default: Any = None) -> Any:
        """Get or set attribute default."""
        if self.get(key) is None:
            setattr(self, key, default)
        return getattr(self, key)

    def pop(self, key: str, default: Any = None) -> Any:
        """Remove an attribute and return its value (setting to default)."""
        val = self.get(key, default)
        # Reset to default
        for f in fields(self):
            if f.name == key:
                if f.default is not MISSING:
                    setattr(self, key, f.default)
                elif f.default_factory is not MISSING:
                    setattr(self, key, f.default_factory())
                else:
                    setattr(self, key, None)
                break
        else:
            setattr(self, key, None)
        return val

    def __contains__(self, key: str) -> bool:
        """Check if an attribute is set and is not None."""
        return hasattr(self, key) and getattr(self, key) is not None

    def __getitem__(self, key: str) -> Any:
        """Bracket read access for backwards compatibility during migration."""
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None

    def __setitem__(self, key: str, value: Any) -> None:
        """Bracket write access for backwards compatibility during migration."""
        setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        """Bracket delete access for backwards compatibility during migration."""
        self.pop(key)
