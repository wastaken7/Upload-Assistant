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

    HDDVD_PLAYLIST: Any = None
    HDR: str = ""
    PTP_images_key: list[Any] = field(default_factory=list)
    TVC_images_key: list[Any] = field(default_factory=list)
    _libplacebo_warmed: Any = None
    adult_media: bool = False
    aither: Any = None
    aither_trumpable: list[Any] = field(default_factory=list)
    aka: str = ""
    anime: bool = False
    anon: bool = False
    ant: Any = None
    ant_user_tags: Any = None
    archive_password: Any = None
    args_line_queue: Any = None
    asian: bool = False
    asin: str = ""
    ask_dupe: bool = False
    audio: str = ""
    audio_languages: list[Any] = field(default_factory=list)
    audio_spectrogram: Any = None
    audio_spectrogram_tracks: Any = None
    audiobook: bool = False
    audiobook_bitrate: Any = None
    audiobook_duration: Optional[int] = None
    audiobook_duration_formatted: Optional[int] = None
    author: str = ""
    auto_episode_title: Any = None
    auto_nfo: bool = False
    available_platforms: list[Any] = field(default_factory=list)
    backdrop: str = ""
    banner_path: Any = None
    base_dir: str = ""
    base_torrent_created: Any = None
    base_torrent_piece_mb: int = 0
    basename_no_ext: str = ""
    bdinfo: dict[str, Any] = field(default_factory=dict)
    bhd: Any = None
    bhd_nfo: Any = None
    bit_depth: str = ""
    bloated: bool = False
    blu: Any = None
    bluray_audio_skip: bool = False
    bluray_score: int = 100
    bluray_single_score: int = 100
    book_asin: Any = None
    book_author: Any = None
    book_isbn: Any = None
    book_language: str = ""
    book_language_iso: str = ""
    book_publisher: Any = None
    book_title: Any = None
    book_translator: Any = None
    btn: Any = None
    cast: Any = None
    category: Optional[str] = None
    category_id: Optional[int] = None
    channels: str = ""
    clean_name: str = ""
    cleanup: Any = None
    client: Any = None
    combined_genres: list[Any] = field(default_factory=list)
    comic: bool = False
    comparison: Optional[str] = None
    comparison_groups: dict[str, Any] = field(default_factory=dict)
    comparison_index: Optional[int] = None
    console_game: bool = False
    container: str = ""
    country: Optional[int] = None
    cover: str = ""
    cover_images: dict[str, Any] = field(default_factory=dict)
    cover_path: str = ""
    covers: Any = None
    current_version: str = ""
    cutoff: int = 1
    daily_episode_title: str = ""
    debug: bool = False
    delete_meta: bool = False
    delete_tmp: bool = False
    demographic: str = ""
    description: str = ""
    description_file: str = ""
    description_file_content: str = ""
    description_link: str = ""
    description_link_content: str = ""
    description_nfo_content: str = ""
    description_template: Any = None
    description_template_content: Any = None
    developer: Any = None
    directors: Any = None
    discs: list[Any] = field(default_factory=list)
    discs_missing_certificate: list[Any] = field(default_factory=list)
    disctype: str = ""
    distributor: str = ""
    distributor_link: str = ""
    diy_disc: bool = False
    douban_id: int = 0
    douban_manual: Any = None
    douban_rating: Any = None
    douban_votes: Any = None
    downloaded_cover_images: list[Any] = field(default_factory=list)
    draft: Any = None
    dual_audio: bool = False
    dupe: bool = False
    dupe_again: bool = False
    dupe_checked_trackers: list[Any] = field(default_factory=list)
    dvd_size: str = ""
    edit: bool = False
    edition: str = ""
    emby: bool = False
    emby_cat: Any = None
    emby_debug: bool = False
    eng_subs: Any = None
    entropy: Any = None
    episode: str = ""
    episode_airdate: Any = None
    episode_int: int = 0
    episode_name: str = ""
    episode_overview: str = ""
    episode_title: str = ""
    episode_tmdb_data: dict[str, Any] = field(default_factory=dict)
    episodes: Any = None
    exclusive: bool = False
    ext_torrenthash: Any = None
    extra_openlibrary_ids: Optional[int] = None
    extras: Any = None
    ffdebug: bool = False
    file_count_match: bool = False
    filelist: list[Any] = field(default_factory=list)
    filename: str = ""
    filename_match: bool = False
    first_air_date: Any = None
    flux: bool = False
    folder_id: Optional[int] = None
    force_recheck: bool = False
    foreign: bool = False
    format: str = ""
    found_preferred_piece_size: bool = False
    found_tracker_match: Any = None
    frame_info_map: dict[str, Any] = field(default_factory=dict)
    frame_overlay: bool = False
    frame_rate: Any = None
    framestor: Any = None
    freeleech: int = 0
    game_region: str = ""
    game_subcategory: str = ""
    game_system: str = ""
    game_version: str = ""
    genre: str = ""
    genre_ids: Optional[int] = None
    genres: list[Any] = field(default_factory=list)
    hardcoded_subs: bool = False
    has_commentary: bool = False
    has_encode_settings: bool = False
    has_languages: bool = False
    has_multiple_default_audio_tracks: bool = False
    has_multiple_default_subtitle_tracks: bool = False
    has_subs: bool = False
    hash_used: Any = None
    hdb: Any = None
    hdb_description: Any = None
    hdb_name: Any = None
    hdr: str = ""
    hfr: Any = None
    huno: Any = None
    igdb_first_release_date: str = ""
    igdb_id: int = 0
    igdb_manual: Any = None
    igdb_rating: str = ""
    igdb_rating_count: str = ""
    image_list: list[dict[str, Any]] = field(default_factory=list)
    image_sizes: dict[str, Any] = field(default_factory=dict)
    imdb: str = ""
    imdb_id: Optional[int] = None
    imdb_info: dict[str, Any] = field(default_factory=dict)
    imdb_manual: Any = None
    imdb_mismatch: bool = False
    imdb_rating: str = ""
    imghost: str = ""
    infohash: str = ""
    initial_dupes: dict[str, Any] = field(default_factory=dict)
    is_disc: bool = False
    isbn: str = ""
    isdir: bool = False
    keep_folder: bool = False
    keep_images: bool = False
    keep_nfo: bool = False
    keywords: list[Any] = field(default_factory=list)
    language: str = ""
    language_checked: bool = False
    languages: list[Any] = field(default_factory=list)
    libplacebo: bool = False
    limit_queue: Optional[int] = None
    linking_failed: bool = False
    localized_overviews: dict[str, Any] = field(default_factory=dict)
    logo: str = ""
    lst: Any = None
    magazine: bool = False
    mal: Any = None
    mal_id: int = 0
    mal_manual: Any = None
    manga: bool = False
    manual: bool = False
    manual_category: Any = None
    manual_commentary: bool = False
    manual_data: Any = None
    manual_date: Any = None
    manual_dvds: Any = None
    manual_edition: Any = None
    manual_episode: Any = None
    manual_episode_title: str = ""
    manual_frames: Optional[str] = None
    manual_language: Any = None
    manual_platform: Any = None
    manual_season: Any = None
    manual_source: Any = None
    manual_type: Any = None
    manual_year: int = 0
    matched_episode_ids: Optional[int] = None
    matched_tracker: str = ""
    max_piece_size: int = 0
    mediainfo: dict[str, Any] = field(default_factory=dict)
    menu_images: list[Any] = field(default_factory=list)
    mismatched_imdb_id: int = 0
    mkbrr: bool = False
    mkbrr_threads: Any = None
    mode: str = ""
    modq: bool = False
    mteam_description: str = ""
    mtv_timeout: Any = None
    name: str = ""
    name_notag: str = ""
    narrator: str = ""
    networks: str = ""
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
    nsfw: Any = None
    nzb_path: str = ""
    ocr: Any = None
    oe: Any = None
    onlyID: Any = None
    openlibrary: Any = None
    openlibrary_book_id: Optional[int] = None
    openlibrary_id: Optional[int] = None
    opera: bool = False
    origin_country: list[Any] = field(default_factory=list)
    origin_country_code: Optional[int] = None
    original_category: str = ""
    original_imdb: int = 0
    original_language: list[Any] = field(default_factory=list)
    original_mal: int = 0
    original_title: str = ""
    original_tmdb: int = 0
    original_tvdb: int = 0
    original_tvmaze: int = 0
    overview: str = ""
    overview_meta: str = ""
    part: str = ""
    path: Optional[str] = None
    path_to_menu_screenshots: str = ""
    personalrelease: bool = False
    piece_size_constraints_enabled: bool = False
    platform: str = ""
    poster: str = ""
    potential_missing: list[Any] = field(default_factory=list)
    prefer_small_pieces: bool = False
    print_tracker_links: bool = True
    print_tracker_messages: bool = False
    production_companies: list[Any] = field(default_factory=list)
    production_countries: list[Any] = field(default_factory=list)
    ptgen: dict[str, Any] = field(default_factory=dict)
    ptp: Any = None
    ptp_groupID: Any = None
    publisher: str = ""
    qbit_bandwidth_control: bool = False
    qbit_bandwidth_threshold: int = 0
    qbit_bandwidth_time: int = 0
    qbit_cat: Any = None
    qbit_tag: Any = None
    queue: str = ""
    quickie_search: bool = False
    randomized: int = 0
    regex_secondary_title: str = ""
    regex_title: str = ""
    regex_year: str = ""
    region: str = ""
    rehash: bool = False
    rehosted_poster: Any = None
    release_date: str = ""
    release_dates: Any = None
    release_url: str = ""
    remove_trackers: bool = False
    repack: str = ""
    requested_trackers: Any = None
    requirements_minimum: str = ""
    requirements_recommended: str = ""
    resolution: str = ""
    retake: bool = False
    retake_call_count: Optional[int] = None
    retrieved_aka: Any = None
    retry_count: int = 0
    rtorrent_label: Any = None
    runtime: int = 60
    saved_description: Any = None
    scene: bool = False
    scene_name: str = ""
    scene_nfo_file: str = ""
    screens: int = 0
    screenshots_in_description: Optional[int] = None
    screenshots_reported_torrent: Optional[int] = None
    screenshots_trumping_torrent: Optional[int] = None
    sd: bool = False
    sdh_subs: Any = None
    search_requests: bool = False
    search_year: str = ""
    season: int = 0
    season_air_first_date: Any = None
    season_int: int = 0
    season_name: str = ""
    season_pack_contains_episode: Any = None
    season_pack_exists: bool = False
    season_pack_id: Optional[int] = None
    season_pack_link: Any = None
    season_pack_name: str = ""
    secondary_title: Any = None
    service: Optional[str] = None
    service_longname: str = ""
    sfx_subtitles: bool = False
    silent: bool = False
    site_check: bool = False
    site_upload: Any = None
    site_upload_queue: Any = None
    size_match: bool = False
    skip_auto_torrent: bool = False
    skip_gen_desc: bool = False
    skip_imghost_upload: bool = False
    skip_tracker_descriptions: bool = False
    skip_trackers: bool = False
    skip_upload_trackers: list[Any] = field(default_factory=list)
    skip_uploading: bool = False
    skipit: bool = False
    skipping: Optional[str] = None
    sorted_filelist: bool = False
    source: Optional[str] = None
    source_size: int = 0
    spd_channel: str = ""
    spectrograms_images: list[Any] = field(default_factory=list)
    steam_manual: Any = None
    steam_url: Any = None
    stream: bool = False
    studios: Any = None
    subtitle_files: list[Any] = field(default_factory=list)
    subtitle_languages: list[Any] = field(default_factory=list)
    tag: str = ""
    three_d: str = ""
    title: str = ""
    tmdb: list[Any] = field(default_factory=list)
    tmdb_adult_media: bool = False
    tmdb_cast: list[Any] = field(default_factory=list)
    tmdb_directors: list[Any] = field(default_factory=list)
    tmdb_episode_data: Any = None
    tmdb_id: Optional[int] = None
    tmdb_logo: str = ""
    tmdb_manual: Any = None
    tmdb_poster: str = ""
    tmdb_season_data: Any = None
    tmdb_type: str = ""
    tonemapped: bool = False
    torrent_comments: list[Any] = field(default_factory=list)
    tracker_status: dict[str, Any] = field(default_factory=dict)
    trackers: list[Any] = field(default_factory=list)
    trackers_pass: Any = None
    trackers_remove: bool = False
    transmission_label: Any = None
    trump_reason: Any = None
    trumpable_id: Optional[int] = None
    trumping_trackers: list[Any] = field(default_factory=list)
    tv_movie: bool = False
    tv_pack: bool = False
    tvdb: Any = None
    tvdb_episode: Any = None
    tvdb_episode_data: dict[str, Any] = field(default_factory=dict)
    tvdb_episode_id: Optional[int] = None
    tvdb_episode_int: Any = None
    tvdb_episode_name: Any = None
    tvdb_episode_year: str = ""
    tvdb_id: Optional[int] = None
    tvdb_imdb_id: Optional[int] = None
    tvdb_manual: Any = None
    tvdb_overview: Any = None
    tvdb_search_results: Any = None
    tvdb_season: Any = None
    tvdb_season_int: Any = None
    tvdb_season_name: str = ""
    tvdb_series_name: Any = None
    tvdb_series_year: Optional[int] = None
    tvmaze: Any = None
    tvmaze_episode_data: dict[str, Any] = field(default_factory=dict)
    tvmaze_id: Optional[int] = None
    tvmaze_manual: int = 0
    type: Optional[str] = None
    ua_name: str = ""
    ua_signature: str = ""
    uhd: bool = False
    ulcx: Any = None
    unattended: bool = False
    unattended_audio_skip: bool = False
    unattended_confirm: bool = False
    unattended_subtitle_skip: bool = False
    unit3d: Any = None
    untouched: bool = False
    upload_timer: bool = True
    uploader_comments: str = ""
    use_bluray_images: bool = False
    usenet: bool = False
    usenet_subject: Any = None
    uuid: str = ""
    valid_mi: Any = None
    valid_mi_settings: Any = None
    vapoursynth: bool = False
    video: list[Any] = field(default_factory=list)
    video_codec: str = ""
    video_duration: int = 0
    video_encode: str = ""
    we_are_uploading: bool = False
    we_asked: bool = False
    we_asked_tvmaze: bool = False
    we_checked_them_all: bool = False
    we_checked_tmdb: bool = False
    we_checked_tvdb: bool = False
    we_need_tag: bool = False
    we_rechecked_torrent: bool = False
    webdv: bool = False
    webui: Optional[str] = None
    were_trumping: bool = False
    write_audio_languages: Any = None
    write_hc_languages: Any = None
    write_subtitle_languages: Any = None
    xxx: Any = None
    year: str = ""
    youtube: str = ""

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
                # Map legacy/invalid keys
                if k in ('3D', '3d'):
                    k = 'three_d'
                elif k == 'is disc':
                    k = 'is_disc'
                setattr(self, k, v)
        for k, v in kwargs.items():
            if k in ('3D', '3d'):
                k = 'three_d'
            elif k == 'is disc':
                k = 'is_disc'
            setattr(self, k, v)

    def __getattribute__(self, name: str) -> Any:
        # Check if attribute has been mapped
        if name in ('3D', '3d'):
            name = 'three_d'
        elif name == 'is disc':
            name = 'is_disc'
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ('3D', '3d'):
            name = 'three_d'
        elif name == 'is disc':
            name = 'is_disc'
        super().__setattr__(name, value)

    def copy(self) -> 'Meta':
        """Ensure copy returns a Meta instance."""
        return Meta(self.to_dict())

    def __copy__(self) -> 'Meta':
        return Meta(self.to_dict())

    def __deepcopy__(self, memo: Any) -> 'Meta':
        import copy
        copied_dict = {k: copy.deepcopy(getattr(self, k), memo) for k in self.to_dict()}
        return Meta(copied_dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary representing defined fields."""
        res = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if val is not None:
                res[f.name] = val
        return res

    def update(self, other: dict[str, Any]) -> None:
        """Update attributes from a dictionary."""
        for k, v in other.items():
            if k in ('3D', '3d'):
                k = 'three_d'
            elif k == 'is disc':
                k = 'is_disc'
            setattr(self, k, v)

    def setdefault(self, key: str, default: Any = None) -> Any:
        """Get or set attribute default."""
        if key in ('3D', '3d'):
            key = 'three_d'
        elif key == 'is disc':
            key = 'is_disc'
        if getattr(self, key, None) is None:
            setattr(self, key, default)
        return getattr(self, key)

    def pop(self, key: str, default: Any = None) -> Any:
        """Remove an attribute and return its value (setting to default)."""
        if key in ('3D', '3d'):
            key = 'three_d'
        elif key == 'is disc':
            key = 'is_disc'
        val = getattr(self, key, default)
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
        if key in ('3D', '3d'):
            key = 'three_d'
        elif key == 'is disc':
            key = 'is_disc'
        return hasattr(self, key) and getattr(self, key) is not None

    def __getitem__(self, key: str) -> Any:
        """Bracket read access for backwards compatibility during migration."""
        if key in ('3D', '3d'):
            key = 'three_d'
        elif key == 'is disc':
            key = 'is_disc'
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Bracket write access for backwards compatibility during migration."""
        if key in ('3D', '3d'):
            key = 'three_d'
        elif key == 'is disc':
            key = 'is_disc'
        setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        """Bracket delete access for backwards compatibility during migration."""
        self.pop(key)
