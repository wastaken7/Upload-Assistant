# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Custom Meta class to support attribute access on metadata."""

from dataclasses import MISSING, dataclass, field, fields
from typing import Any, Optional


@dataclass(init=False)
class Meta:
    """
    Custom metadata class that behaves as a dataclass but with support
    for backward compatibility and helper dictionary methods.
    """

    libplacebo_warmed: Optional[bool] = None
    adult_media: bool = False
    aither_trumpable: Optional[list[Any]] = field(default_factory=list)
    aither: Optional[str] = None
    aka: str = ""
    anime: bool = False
    anon: bool = False
    ant_user_tags: Optional[bool] = None
    ant: Optional[int] = None
    archive_password: Optional[str] = None
    args_line_queue: Optional[bool] = None
    asian: bool = False
    asin: str = ""
    ask_dupe: bool = False
    audio_languages: Optional[list[str]] = field(default_factory=list)
    audio_spectrogram_tracks: Optional[str] = None
    audio_spectrogram: Optional[bool] = None
    audio: str = ""
    audiobook_bitrate: Optional[int] = None
    audiobook_duration_formatted: Optional[str] = None
    audiobook_duration: Optional[float] = None
    audiobook: bool = False
    author: str = ""
    auto_episode_title: Optional[str] = None
    auto_nfo: bool = False
    available_platforms: list[Any] = field(default_factory=list)
    backdrop: str = ""
    banner_path: Optional[str] = None
    base_dir: str = ""
    base_torrent_created: Optional[bool] = None
    base_torrent_piece_mb: int = 0
    basename_no_ext: str = ""
    bdinfo: dict[str, Any] = field(default_factory=dict)
    bhd_nfo: Optional[bool] = None
    bhd: Optional[str | int] = None
    bit_depth: str = ""
    bloated: bool = False
    blu: Optional[str | int] = None
    bluray_audio_skip: bool = False
    bluray_score: int = 100
    bluray_single_score: int = 100
    book_asin: Optional[str] = None
    book_author: Optional[str] = None
    book_isbn: Optional[str] = None
    book_language_iso: str = ""
    book_language: str = ""
    book_publisher: Optional[str] = None
    book_title: Optional[str] = None
    book_translator: Optional[str] = None
    btn: Optional[str | int] = None
    cast: Optional[list[str]] = None
    category_id: Optional[str] = None
    category: str = ""
    channels: str = ""
    clean_name: str = ""
    cleanup: bool = False
    client: Optional[str] = None
    combined_genres: list[str] | str = field(default_factory=list)
    comic: bool = False
    comparison_groups: dict[str, dict[str, Any]] | list[dict[str, Any]] = field(default_factory=dict)
    comparison_index: Optional[int] = None
    comparison: Optional[str] = None
    console_game: bool = False
    container: str = ""
    country: Optional[int] = None
    cover_images: dict[str, Any] = field(default_factory=dict)
    cover_path: str = ""
    cover: str = ""
    covers: Optional[list[dict[str, Any]]] = None
    current_version: str = ""
    cutoff: int = 1
    daily_episode_title: str = ""
    debug: bool = False
    delete_meta: bool = False
    delete_tmp: bool = False
    demographic: str = ""
    description_file_content: str = ""
    description_file: str = ""
    description_link_content: str = ""
    description_link: str = ""
    description_nfo_content: str = ""
    description_template_content: Optional[str] = None
    description_template: Optional[str] = None
    description: str = ""
    developer: Optional[str] = None
    directors: Optional[list[str]] = None
    discs_missing_certificate: list[Any] = field(default_factory=list)
    discs: list[Any] = field(default_factory=list)
    disctype: str = ""
    distributor_link: str = ""
    distributor: str = ""
    diy_disc: bool = False
    douban_id: int = 0
    douban_manual: Optional[int | str] = None
    douban_rating: Optional[float | str] = None
    douban_votes: Optional[int | str] = None
    downloaded_cover_images: dict[str, str] = field(default_factory=dict)
    draft: Optional[bool] = None
    dual_audio: bool = False
    dupe_again: bool = False
    dupe_checked_trackers: list[Any] = field(default_factory=list)
    dupe: bool = False
    dvd_size: str = ""
    edit: bool = False
    edition: str = ""
    eng_subs: Optional[int] = None
    entropy: Optional[int | str] = None
    episode_airdate: Optional[str] = None
    episode_int: int = 0
    episode_name: str = ""
    episode_overview: str = ""
    episode_title: str = ""
    episode_tmdb_data: dict[str, Any] = field(default_factory=dict)
    episode: str = ""
    episodes: Optional[list[dict[str, Any]]] = None
    exclusive: bool = False
    ext_torrenthash: Optional[str] = None
    extra_openlibrary_ids: Optional[int] = None
    extras: Optional[bool] = None
    ffdebug: bool = False
    file_count_match: int | bool = False
    filelist: list[Any] = field(default_factory=list)
    filename_match: str | bool = False
    filename: str = ""
    first_air_date: Optional[str] = None
    flux: bool = False
    folder_id: Optional[int] = None
    force_recheck: bool = False
    foreign: bool = False
    format: str = ""
    found_preferred_piece_size: Optional[str] = None
    found_tracker_match: Optional[bool] = None
    frame_info_map: dict[str, Any] = field(default_factory=dict)
    frame_overlay: bool = False
    frame_rate: Optional[float] = None
    framestor: Optional[bool] = None
    freeleech: int = 0
    game_region: str = ""
    game_subcategory: str = ""
    game_system: str = ""
    game_version: str = ""
    genre_ids: Optional[int] = None
    genre: str = ""
    genres: list[str] = field(default_factory=list)
    hardcoded_subs: bool = False
    has_commentary: bool = False
    has_encode_settings: bool = False
    has_languages: str = ""
    has_multiple_default_audio_tracks: bool = False
    has_multiple_default_subtitle_tracks: bool = False
    has_subs: bool | int = False
    hash_used: Optional[str] = None
    hdb_description: Optional[str] = None
    hdb_name: Optional[str] = None
    hdb: Optional[str | int] = None
    HDDVD_PLAYLIST: Optional[dict[str, Any]] = None
    hdr: str = ""
    HDR: str = ""
    hfr: Optional[bool] = None
    huno: Optional[str | int] = None
    igdb_first_release_date: str = ""
    igdb_id: int = 0
    igdb_manual: Optional[str] = None
    igdb_rating_count: int | str = ""
    igdb_rating: float | str = ""
    image_list: list[dict[str, Any]] = field(default_factory=list)
    image_sizes: dict[str, Any] = field(default_factory=dict)
    imdb_id: Optional[int] = None
    imdb_info: dict[str, Any] = field(default_factory=dict)
    imdb_manual: Optional[str | int] = None
    imdb_mismatch: bool = False
    imdb_rating: str = ""
    imdb: Optional[str] = ""
    imghost: str = ""
    infohash: str = ""
    initial_dupes: dict[str, Any] = field(default_factory=dict)
    is_disc: str = ""
    isbn: str = ""
    isdir: bool = False
    item_args: Optional[list[str]] = None
    keep_folder: bool = False
    keep_images: bool = False
    keep_nfo: bool = False
    keywords: list[str] = field(default_factory=list)
    language_checked: bool = False
    language: str = ""
    languages: dict[str, list[str]] | list[Any] = field(default_factory=list)
    libplacebo: bool = False
    limit_queue: int = 0
    linking_failed: bool = False
    localized_overviews: dict[str, Any] = field(default_factory=dict)
    logo: str = ""
    lst: Optional[str | int] = None
    magazine: bool = False
    mal_id: int = 0
    mal_manual: Optional[str | int] = None
    mal: Optional[int] = None
    manga: bool = False
    manual_category: Optional[str] = None
    manual_commentary: bool = False
    manual_data: Optional[str] = None
    manual_date: Optional[str] = None
    manual_dvds: Optional[str] = None
    manual_edition: Optional[str | list[str]] = None
    manual_episode_title: str = ""
    manual_episode: Optional[str | int] = None
    manual_frames: Optional[str | list[int] | list[str]] = None
    manual_language: Optional[str | dict[str, Any]] = None
    manual_platform: Optional[str] = None
    manual_season: Optional[str | int] = None
    manual_source: Optional[str] = None
    manual_type: Optional[str] = None
    manual_year: int = 0
    manual: bool = False
    matched_episode_ids: Optional[int] = None
    matched_tracker: str = ""
    max_piece_size: int = 0
    mediainfo: dict[str, Any] = field(default_factory=dict)
    menu_images: list[Any] = field(default_factory=list)
    mismatched_imdb_id: int = 0
    mkbrr_threads: Optional[str | int] = None
    mkbrr: bool = False
    mode: str = ""
    modq: bool = False
    mteam_description: str = ""
    mtv_timeout: Optional[bool] = None
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
    nsfw: Optional[bool] = None
    nzb_path: str = ""
    ocr: Optional[bool] = None
    oe: Optional[str | int] = None
    onlyID: Optional[bool] = None
    openlibrary_book_id: Optional[int] = None
    openlibrary_id: Optional[int] = None
    openlibrary: Optional[str] = None
    opera: bool = False
    origin_country_code: Optional[list[str]] = None
    origin_country: list[Any] = field(default_factory=list)
    original_category: str = ""
    original_imdb: int = 0
    original_language: Optional[str] = None
    original_mal: int = 0
    original_title: str = ""
    original_tmdb: int = 0
    original_tvdb: int = 0
    original_tvmaze: int = 0
    overview_meta: str = ""
    overview: str = ""
    part: str = ""
    path_to_menu_screenshots: str = ""
    path: Optional[str] = None
    personalrelease: bool = False
    piece_size_constraints_enabled: str | bool = False
    platform: str = ""
    poster: str = ""
    potential_missing: list[Any] = field(default_factory=list)
    prefer_small_pieces: bool = False
    print_tracker_links: bool = True
    print_tracker_messages: bool = False
    production_companies: list[Any] = field(default_factory=list)
    production_countries: list[Any] = field(default_factory=list)
    ptgen: dict[str, Any] = field(default_factory=dict)
    ptp_groupID: Optional[str] = None
    PTP_images_key: list[dict[str, Any]] = field(default_factory=list)
    ptp: Optional[str | int] = None
    publisher: str = ""
    qbit_bandwidth_control: bool = False
    qbit_bandwidth_threshold: int = 0
    qbit_bandwidth_time: int = 0
    qbit_cat: Optional[str] = None
    qbit_tag: Optional[str] = None
    queue: str = ""
    quickie_search: bool = False
    randomized: int = 0
    regex_secondary_title: str = ""
    regex_title: str = ""
    regex_year: str = ""
    region: str = ""
    rehash: bool = False
    rehosted_poster: Optional[str] = None
    release_date: str = ""
    release_dates: Optional[dict[str, Any]] = None
    release_url: str = ""
    remove_trackers: list[str] | bool = False
    repack: str = ""
    requested_trackers: Optional[list[str]] = None
    requirements_minimum: str = ""
    requirements_recommended: str = ""
    resolution: str = ""
    retake_call_count: Optional[int] = None
    retake: bool = False
    retrieved_aka: Optional[str] = None
    retry_count: int = 0
    rtorrent_label: Optional[str] = None
    runtime: int = 60
    saved_description: Optional[bool] = None
    scene_name: str = ""
    scene_nfo_file: str = ""
    scene: bool = False
    screens: int = 0
    screenshots_in_description: Optional[bool] = None
    screenshots_reported_torrent: Optional[list[str]] = None
    screenshots_trumping_torrent: Optional[list[str]] = None
    sd: int | bool = False
    sdh_subs: Optional[int] = None
    search_requests: bool = False
    search_year: int | str = ""
    season_air_first_date: Optional[str] = None
    season_int: int = 0
    season_name: str = ""
    season_pack_contains_episode: Optional[bool] = None
    season_pack_exists: bool = False
    season_pack_id: Optional[int | str] = None
    season_pack_link: Optional[str] = None
    season_pack_name: str = ""
    season: Optional[int | str] = 0
    secondary_title: Optional[str] = None
    service_longname: str = ""
    service: Optional[str] = None
    sfx_subtitles: bool = False
    silent: bool = False
    site_check: bool = False
    site_upload_queue: Optional[bool] = None
    site_upload: Optional[str] = None
    size_match: str | bool = False
    skip_auto_torrent: bool = False
    skip_gen_desc: bool = False
    skip_imghost_upload: bool = False
    skip_tracker_descriptions: bool = False
    skip_trackers: bool = False
    skip_upload_trackers: list[Any] = field(default_factory=list)
    skip_uploading: int | bool = False
    skipit: bool = False
    skipping: Optional[str] = None
    sorted_filelist: bool = False
    source_size: int = 0
    source: Optional[str] = None
    spd_channel: str = ""
    spectrograms_images: list[Any] = field(default_factory=list)
    steam_manual: Optional[str] = None
    steam_url: Optional[str] = None
    stream: bool = False
    studios: Optional[list[str] | str] = None
    subtitle_files: list[Any] = field(default_factory=list)
    subtitle_languages: Optional[list[str] | str] = field(default_factory=list)
    tag: Optional[str] = None
    three_d: str = ""
    title: str = ""
    tmdb_adult_media: bool = False
    tmdb_cast: list[Any] = field(default_factory=list)
    tmdb_directors: list[Any] = field(default_factory=list)
    tmdb_episode_data: Optional[dict[str, Any]] = None
    tmdb_id: Optional[int] = None
    tmdb_localized_data: dict[str, Any] = field(default_factory=dict)
    tmdb_logo: str = ""
    tmdb_manual: Optional[int | str] = None
    tmdb_poster: str = ""
    tmdb_season_data: Optional[dict[str, Any]] = None
    tmdb_type: str = ""
    tmdb: Optional[int] = None
    tonemapped: bool = False
    torrent_comments: list[Any] = field(default_factory=list)
    tracker_status: dict[str, Any] = field(default_factory=dict)
    trackers_pass: Optional[int] = None
    trackers_remove: str | bool = False
    trackers: list[str] = field(default_factory=list)
    transmission_label: Optional[str] = None
    trump_reason: Optional[str] = None
    trumpable_id: Optional[int | str] = None
    trumping_trackers: list[Any] = field(default_factory=list)
    tv_movie: bool = False
    tv_pack: bool = False
    TVC_images_key: list[dict[str, Any]] = field(default_factory=list)
    tvdb_episode_data: dict[str, Any] = field(default_factory=dict)
    tvdb_episode_id: Optional[int] = None
    tvdb_episode_int: Optional[int] = None
    tvdb_episode_name: Optional[str] = None
    tvdb_episode_year: str = ""
    tvdb_episode: Optional[int] = None
    tvdb_id: Optional[int] = None
    tvdb_imdb_id: Optional[str] = None
    tvdb_manual: Optional[str | int] = None
    tvdb_overview: Optional[str] = None
    tvdb_search_results: Optional[list[dict[str, Any]]] = None
    tvdb_season_int: Optional[int] = None
    tvdb_season_name: str = ""
    tvdb_season: Optional[int | str] = None
    tvdb_series_name: Optional[str] = None
    tvdb_series_year: Optional[int] = None
    tvdb: Optional[int] = None
    tvmaze_episode_data: dict[str, Any] = field(default_factory=dict)
    tvmaze_id: Optional[int | str] = None
    tvmaze_manual: int = 0
    tvmaze: Optional[int | str] = None
    type: Optional[str] = None
    ua_name: str = ""
    ua_signature: str = ""
    uhd: str | bool = False
    ulcx: Optional[str | int] = None
    unattended_audio_skip: bool = False
    unattended_confirm: bool = False
    unattended_subtitle_skip: bool = False
    unattended: bool = False
    unit3d: Optional[bool] = None
    untouched: bool = False
    upload_timer: bool = True
    uploader_comments: str = ""
    use_bluray_images: bool = False
    usenet_subject: Optional[str] = None
    usenet: bool = False
    uuid: str = ""
    valid_mi_settings: Optional[bool] = None
    valid_mi: Optional[bool] = None
    vapoursynth: bool = False
    video_codec: str = ""
    video_duration: Optional[int] = 0
    video_encode: str = ""
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
    webui: Optional[str] = None
    were_trumping: bool = False
    write_audio_languages: Optional[bool] = None
    write_hc_languages: Optional[bool] = None
    write_subtitle_languages: Optional[bool] = None
    xxx: Optional[bool] = None
    year: str = ""
    youtube: Optional[str] = ""

    def __init__(self, _data: Optional[dict[str, Any]] = None, **kwargs: Any) -> None:
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

    def copy(self) -> Meta:
        """Ensure copy returns a Meta instance."""
        return Meta(self.to_dict())

    def __copy__(self) -> Meta:
        return Meta(self.to_dict())

    def __deepcopy__(self, memo: Any) -> Meta:
        import copy

        copied_dict = {k: copy.deepcopy(self[k], memo) for k in self.to_dict()}
        return Meta(copied_dict)

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
            raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Bracket write access for backwards compatibility during migration."""
        setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        """Bracket delete access for backwards compatibility during migration."""
        self.pop(key)
