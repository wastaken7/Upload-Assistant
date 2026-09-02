# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

config: dict[str, Any] = {
    "DEFAULT": {
        # --- MAIN SETTINGS ---
        # Set to True to display a notice when an update is available.
        "update_notification": True,
        # Set to True to display the changelog when an update is available.
        "verbose_notification": False,
        # Number of hours to reuse a successful update check. Set to 0 to check every run.
        "update_notification_cache_hours": 4,
        # Set to True to play a bell sound when prompting for confirmation.
        "sfx_on_prompt": True,
        # Set to True to apply argument overrides from data/templates/user-args.json.
        "user_overrides": False,
        # Apply --personalrelease when the detected release group matches any tag (case-insensitive).
        "personal_release_groups": [],
        # Set to True to suppress configuration warnings at startup.
        "suppress_warnings": False,
        # Set to True to keep meta.json between runs instead of deleting it before processing begins.
        "keep_meta": False,
        # --- LOGGING ---
        # Console logging configuration
        # Show the time in console logs.
        "console_show_time": False,
        # Show the log level in console logs.
        "console_show_level": False,
        # Show the source file path in console logs.
        "console_show_path": False,
        # Enable Rich markup parsing in console logs.
        "console_markup": True,
        # Display terminal links as embedded hyperlinks using OSC 8.
        # Set to False to show full URLs in terminals without hyperlink support.
        "embed_links": True,
        # File logging configuration
        # Save a plain-text log of the upload flow in each release's tmp folder.
        "write_log": False,
        # Debug configuration
        # Enable debug mode globally, equivalent to running with --debug.
        "debug": False,
        # Debug console logging configuration
        # Show the time in debug console logs.
        "console_debug_show_time": True,
        # Show the log level in debug console logs.
        "console_debug_show_level": True,
        # Show the source file path in debug console logs.
        "console_debug_show_path": True,
        # Enable Rich markup parsing in debug console logs.
        "console_debug_markup": True,
        # --- METADATA API CREDENTIALS ---
        # TMDB API key (required).
        # Create a key at https://www.themoviedb.org/settings/api and paste it below.
        "tmdb_api": "",
        # TVDB API key.
        # Sign up at https://www.thetvdb.com/api-information/signup and paste the key below.
        "tvdb_api": "",
        # Generate a TVDB token at https://thetvdb.github.io/v4-api/#/Login/post_login.
        # Enter only your API key in the login form and leave the PIN unchanged.
        "tvdb_token": "",
        # Google Books API key. Leave blank to disable.
        # Obtain a key from https://console.cloud.google.com/apis/library/books.googleapis.com.
        "google_books_api_key": "",
        # Twitch/IGDB API credentials. Leave blank to disable.
        # Obtain them from the Twitch Developer Console: https://dev.twitch.tv/console.
        "twitch_client_id": "",
        "twitch_client_secret": "",
        # MyAnonamouse (MAM) API key or session cookie (mam_id). Leave blank to disable.
        # Find it under Preferences > Security > View IP locked session cookie.
        "mam_api_key": "",
        # GazelleGames API key. Leave blank to disable game metadata enrichment.
        # Create one in your GazelleGames profile settings with no write permissions required.
        "ggn_api_key": "",
        # BTN API key used to retrieve metadata from BTN.
        "btn_api": "",
        # --- ARR INTEGRATION ---
        # Set to True to use Sonarr when searching for TV shows.
        "use_sonarr": False,
        "sonarr_url": "http://localhost:8989",
        "sonarr_api_key": "",
        # Settings for a second Sonarr instance.
        # Add additional Sonarr instances by adding more sonarr_url_x and sonarr_api_key_x entries.
        "sonarr_url_1": "http://my-second-instance:8989",
        "sonarr_api_key_1": "",
        # Set to True to use Radarr when searching for movies.
        "use_radarr": False,
        "radarr_url": "http://localhost:7878",
        "radarr_api_key": "",
        # Settings for a second Radarr instance.
        # Add additional Radarr instances by adding more radarr_url_x and radarr_api_key_x entries.
        "radarr_url_1": "http://my-second-instance:7878",
        "radarr_api_key_1": "",
        # --- EXTERNAL TOOL PATHS ---
        # Optional paths to external media tools. Leave blank to use the bundled
        # tool when available, or the corresponding executable on the system PATH.
        # The DVD-specific MediaInfo executable must remain on version 23.04 because
        # newer releases do not preserve its DVD parsing behavior.
        "ffmpeg_path": "",
        "ffprobe_path": "",
        "mediainfo_path": "",
        "dvd_mediainfo_path": "",
        "bdinfo_path": "",
        "mkbrr_path": "",
        "dovi_tool_path": "",
        "hdr10plus_tool_path": "",
        # Optional path to the unRAR executable for CBR/CBZ extraction.
        # Leave blank to use the system PATH.
        # Example: "C:\\Program Files\\WinRAR\\UnRAR.exe"
        "unrar_path": "",
        # --- CLIENT SELECTION ---
        # Default client used for torrent injection and existing-torrent searches.
        "default_torrent_client": "qbittorrent",
        # The optional lists below can override this default for each operation.
        # If either list is omitted or empty, that operation uses the default above.
        # Clients used for injection (adding uploaded torrents for seeding):
        # "injecting_client_list": ["qbittorrent", "rtorrent"],
        # Clients searched for existing torrents:
        # "searching_client_list": ["qbittorrent", "qbittorrent_searching"],
        # --- METADATA CACHING ---
        # Public metadata cache
        # Cache responses from sites such as TMDB and IMDb for reuse in future runs, reducing API requests.
        # Set to False only to test fresh data or troubleshoot an outdated result.
        "metadata_cache_enabled": True,
        # Folder where cached data is saved. Relative paths are created inside
        # the Upload-Assistant folder. You normally do not need to change this.
        "metadata_cache_dir": "data/cache/metadata",
        # Number of hours a normal result can be reused.
        # 168 = 7 days. Lower this for fresher data, or raise it to reduce API
        # requests further.
        "metadata_cache_default_ttl_hours": 168,
        # Number of minutes a search with no result is remembered. This avoids
        # repeating a query that an API did not find. 60 = 1 hour.
        "metadata_cache_negative_ttl_minutes": 60,
        # Optional settings for each service. "enabled": False disables caching
        # only for that service. "ttl_hours" overrides the default above.
        # You can remove services from this list to use the default duration.
        "metadata_cache_services": {
            # Movies and TV Shows. "localized_ttl_hours" controls data in other
            # languages, such as a Portuguese overview and title.
            "tmdb": {"enabled": True, "ttl_hours": 168, "localized_ttl_hours": 168},
            # Movie and series information identified by tt1234567.
            "imdb": {"enabled": True, "ttl_hours": 72},
            # Episode guides and show names.
            "tvdb": {"enabled": True, "ttl_hours": 168},
            "tvmaze": {"enabled": True, "ttl_hours": 24},
            # Anime information, including romaji titles and MAL IDs.
            "anilist": {"enabled": True, "ttl_hours": 168},
            "douban": {"enabled": True, "ttl_hours": 168},
            "thexem": {"enabled": True, "ttl_hours": 168},
            # Game information.
            "igdb": {"enabled": True, "ttl_hours": 168},
            "steam": {"enabled": True, "ttl_hours": 72},
            # Book, audiobook, and comic metadata. This data changes rarely,
            # so the default here is 30 days (720 hours).
            "google_books": {"enabled": True, "ttl_hours": 720},
            # Work IDs, ISBNs, and author names from OpenLibrary.
            "openlibrary": {"enabled": True, "ttl_hours": 720},
            # Data fetched from a MAM account; a shorter duration reflects changes.
            "myanonamouse": {"enabled": True, "ttl_hours": 24},
            # Private-tracker game metadata can be edited, so keep this relatively fresh.
            "gazellegames": {"enabled": True, "ttl_hours": 24},
            # Music release metadata; it also uses 30 days because it changes rarely.
            "musicbrainz": {"enabled": True, "ttl_hours": 720},
            "discogs": {"enabled": True, "ttl_hours": 720},
        },
        # Tracker-ID metadata cache
        # Cache tracker metadata when you provide a specific torrent ID, such as --ptp, --hdb,
        # or a tracker link in a torrent comment. Duplicate checks and broad searches are never cached.
        "tracker_metadata_cache_enabled": True,
        # Folder for cached tracker responses. You normally do not need to
        # change this setting.
        "tracker_metadata_cache_dir": "data/cache/tracker_metadata",
        # Number of hours an explicit tracker torrent-ID response can be reused.
        # 24 = 1 day. Trackers can edit descriptions and images, so this is kept
        # shorter than the public metadata cache.
        "tracker_metadata_cache_ttl_hours": 24,
        # Number of minutes an explicit tracker ID with no result is remembered.
        # 15 minutes avoids repeated requests without hiding a newly available
        # torrent for too long.
        "tracker_metadata_cache_negative_ttl_minutes": 15,
        # --- MUSIC METADATA ---
        # Use MusicBrainz only as corroborating metadata. Local file tags remain
        # authoritative, and no external lookup is made unless this setting is enabled.
        "music_enrichment_enabled": False,
        # Optional Discogs personal access token. Automatic or supplied Discogs
        # lookups are bounded and read-only; this token raises Discogs API
        # limits but is never written to release metadata or logs.
        "music_discogs_token": "",
        # --- TRACKER SEARCH AND IMPORT ---
        # Skip automatic searches for matching torrents in configured clients.
        # When False, Upload Assistant reuses matching hashes and searches supported trackers.
        "skip_auto_torrent": False,
        # Set to True to also skip automatic torrent searches for personal releases.
        "skip_auto_torrent_personalrelease": False,
        # Set to True to prefer torrents with a piece size of 16 MiB or less when searching configured clients.
        "prefer_max_16_torrent": False,
        # Import policy for releases found on other trackers. Choose one:
        # - "ids": import only IMDb/TMDb/TVDb/MAL IDs and related release metadata.
        # - "images": import IDs, metadata, and validated description screenshots, but no text.
        # - "text": import IDs, metadata, and cleaned description text, but no screenshots.
        # - "text_and_images": import IDs, metadata, cleaned text, and validated screenshots.
        # Use --onlyID to temporarily force "ids" for one execution.
        "tracker_description_mode": "text",
        # Maximum number of tracker-ID metadata candidates queried at once.
        "tracker_search_concurrency": 4,
        # Query tracker metadata only when a torrent ID comes from a client comment or --tracker-id.
        "tracker_comment_only": True,
        # Use matching client torrents when region or distributor IDs are missing.
        # This finds corresponding Unit3D tracker entries and retrieves the missing IDs.
        # Requires "skip_auto_torrent" to be set to False.
        "ping_unit3d": False,
        # Set to True to also search PreDB for a matching scene release.
        # PreDB can be inconsistent or time out, but it may find releases absent from SRRDB.
        "check_predb": False,
        # --- IMAGE HOSTING ---
        # Order of image hosts, with the primary host first and backups after it.
        # Available image hosts: dalexni, imgbb, imgbox, lensdump, lostimg, midnightscene, onlyimage, passtheimage, pixhost, ptscreens, seedpool_cdn, sharex, utppm, zipline
        "img_host_1": "",
        "img_host_2": "",
        "img_host_3": "",
        "img_host_4": "",
        "img_host_5": "",
        "img_host_6": "",
        # Prefer one configured host accepted by every selected tracker that
        # declares an image-host policy. If none is shared, use per-tracker
        # fallback hosting as usual.
        "smart_image_host_selection": True,
        # Maximum number of image uploads running at once. Set to 0 to use host defaults.
        "image_upload_concurrency": 0,
        # Delay between starting image uploads, in seconds.
        "image_upload_delay": 0.0,
        # Minimum number of successful image uploads required to continue.
        "min_successful_image_uploads": "3",
        # Image-host credentials
        "dalexni_api": "",
        "imgbb_api": "",
        "lensdump_api": "",
        "lostimg_api": "",
        "onlyimage_api": "",
        "passtheima_ge_api": "",
        "ptscreens_api": "",
        # MidnightScene (Zipline) API key. Sign in, click your avatar, then choose
        # "Copy token" (or open Settings > User). Never share or commit this token.
        "midnightscene_api_key": "",
        # Seedpool CDN API key
        "seedpool_cdn_api": "",
        # ShareX-style image host (IMageHosting) token
        "sharex_url": "https://img.digitalcore.club/api/upload",
        "sharex_api_key": "",
        # utp.pm API key
        "utppm_api": "",
        # Custom Zipline URL and API key
        "zipline_url": "",
        "zipline_api_key": "",
        # --- SCREENSHOT CAPTURE AND PROCESSING ---
        # Number of screenshots to capture
        "screens": "4",
        # Minimum number of existing screenshots required to skip new captures and uploads.
        # Existing screenshots may come from an imported description.
        "cutoff_screens": "4",
        # Keep screenshots at the coded dimensions reported by MediaInfo.
        # Set to True only to convert non-square-pixel video to its display geometry.
        # This can change dimensions such as 1920x1040 to 1924x1040.
        "scale_screenshots_for_par": False,
        # Maximum number of FFmpeg processes that can run at once.
        # The effective limit is the lower of this value and the number of screenshots.
        "process_limit": "4",
        # Set to True to reduce CPU usage by applying an additional FFmpeg limit.
        "ffmpeg_limit": False,
        # FFmpeg compression level for screenshots (0-9).
        # A value of 6 provides a good balance between compression and speed.
        "ffmpeg_compression": "6",
        # --- SCREENSHOT ENHANCEMENTS ---
        # HDR tone mapping
        # Set to True to tone-map HDR, Dolby Vision, and HLG screenshots.
        "tone_map": True,
        # Use libplacebo for FFmpeg tone mapping when it is available and compatible.
        # Set to False if libplacebo causes FFmpeg issues, especially on seedboxes.
        "use_libplacebo": True,
        # Set to True to skip the FFmpeg compatibility check when you know libplacebo works.
        # Otherwise, Upload Assistant runs a quick check before using libplacebo.
        "ffmpeg_is_good": False,
        # Set to True to warm up libplacebo before capturing the first screenshot.
        # This can help on systems that compile libplacebo shaders slowly.
        "ffmpeg_warmup": False,
        # FFmpeg tone-mapping algorithm used when libplacebo is disabled.
        # See https://ayosec.github.io/ffmpeg-filters-docs/7.1/Filters/Video/tonemap.html
        "algorithm": "mobius",
        # Control desaturation of overly bright highlights when libplacebo is disabled.
        # Higher values preserve more color; lower values fade highlights toward white.
        # Set to 0.0 to disable. FFmpeg defaults to 2.0; this example uses 10.0.
        # Works only when the input frame has a supported color tag.
        "desat": "10.0",
        # Screenshot overlays
        # Set to True to overlay the frame number, frame type, and "Tonemapped" label when applicable.
        # Enabling overlays uses FFmpeg tone mapping instead of libplacebo.
        "frame_overlay": False,
        # Overlay text size, scaled with resolution.
        "overlay_text_size": "18",
        # --- DISC MENU SCREENSHOTS ---
        # Set to True to capture DVD menu screenshots from menu VOBs.
        "auto_dvd_menus": True,
        # Maximum number of disc menu screenshots to upload.
        "max_menu_screens": "6",
        # --- XXX CONTACT SHEETS ---
        # XXX releases generate one contact sheet per video instead of individual frames.
        # Rows are vertical and columns are horizontal: 12 x 5 produces 60 thumbnails.
        "xxx_contact_sheet_rows": "12",
        "xxx_contact_sheet_columns": "5",
        # Maximum number of video files for which to generate XXX contact sheets.
        "xxx_contact_sheet_max_videos": "6",
        # Set to True to create XXX contact sheets as animated WebP files instead of PNG.
        "xxx_contact_sheet_animated_webp": False,
        # Animation duration in seconds.
        "xxx_contact_sheet_animation_seconds": "5",
        # Add this many normal screenshots to the contact sheet for a single-video XXX release.
        "xxx_single_file_screens": "0",
        # --- GENERAL DESCRIPTION SETTINGS ---
        # See detailed documentation on how these settings affect description building:
        # https://github.com/wastaken7/Upload-Assistant/blob/development/docs/description-builder.md
        # Add a TMDB show or movie logo to the top of the description.
        "add_logo": True,
        # Logo width in pixels.
        "logo_size": "300",
        # Preferred logo language (ISO 639-1). Defaults to English ("en").
        # Falls back to English when a logo in the preferred language is unavailable.
        "logo_language": "",
        # Screenshot thumbnail width where supported. Default: 350 (for example, [img=350]).
        "thumbnail_size": "350",
        # Number of screenshots per row on sites that use the common description.
        # Leave blank to use the default of 2.
        "screens_per_row": "",
        # Set to True to add the episode overview to the description.
        "episode_overview": True,
        # --- PACK DESCRIPTIONS ---
        # Number of screenshots to use for each disc or episode in packs on supported sites.
        # Set to 0 to use only the original description and images for later items.
        # PassThePopcorn always uses at least 2 images per item, regardless of this value.
        "multiScreens": "2",
        # The following pack settings do not affect PassThePopcorn, which uses a fixed format.
        # Screenshot thumbnail width for pack descriptions. Default: 300.
        "pack_thumb_size": "300",
        # Description character-count cutoff (including BBCode) for UNIT3D season packs.
        # After reaching this limit, only filenames and screenshots are used for any
        # additional files still to be added. Set a small value, such as 50, to include
        # only filenames and screenshots for each file, without MediaInfo.
        # UNIT3D sites enforce hard description limits. A little over 17,000 characters
        # worked in an AITHER forum post. If the current character count is below
        # charLimit, the next full MediaInfo block is added before the cutoff is applied.
        "charLimit": "14000",
        # How many files in a season pack are added before using an additional spoiler tag.
        # Files past this limit are grouped within the additional spoiler tag.
        "fileLimit": "2",
        # Maximum number of files processed for screenshots and MediaInfo in a pack.
        # You may not want to process screenshots and MediaInfo for 40 episodes in a season pack.
        "processLimit": "10",
        # --- DESCRIPTION HEADERS AND OVERRIDES ---
        # Header added to the top of the description where supported.
        # Can be overridden per tracker by adding the same setting to its configuration.
        "custom_description_header": "",
        # Header added above the screenshot section where supported.
        # Can be overridden per tracker by adding the same setting to its configuration.
        "screenshot_header": "[h2]Screenshots[/h2]",
        # Header added above screenshots after HDR tone mapping.
        # Can be overridden per tracker by adding the same setting to its configuration.
        "tonemapped_header": "[center]Screenshots have been adapted for SDR viewing, for reference only.[/center]",
        # Applicable only to raw discs (Blu-ray/DVD).
        # Header added above disc menu screenshots where supported.
        # Can be overridden per tracker by adding the same setting to its configuration.
        "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
        # Header added above audio spectrograms.
        "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
        # Header added above Dolby Vision and HDR10+ metadata plots.
        "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
        # Custom signature added to the bottom of the description.
        # Can be overridden per tracker by adding the same setting to its configuration.
        "custom_signature": "",
        # Override description text fields for specific release groups. Tags are matched
        # case-insensitively, with or without their leading hyphen.
        # Per-tracker tag_overrides take precedence over these DEFAULT overrides.
        "tag_overrides": {
            "MyAwesomeGroupTag": {
                "custom_description_header": "[center]MyAwesomeGroupTag release[/center]",
                "screenshot_header": "[h2]MyAwesomeGroupTag Screenshots[/h2]",
                "disc_menu_header": "[h2]MyAwesomeGroupTag Disc Menu Screenshots[/h2]",
                "audio_spectrogram_header": "[h2]MyAwesomeGroupTag Audio Spectrogram[/h2]",
                "dynamic_hdr_plot_header": "[h2]MyAwesomeGroupTag Dynamic HDR Metadata[/h2]",
                "tonemapped_header": "[center]MyAwesomeGroupTag SDR reference screenshots[/center]",
                "custom_signature": "[center]MyAwesomeGroupTag signature[/center]",
            },
        },
        # --- BLU-RAY SETTINGS ---
        # Set to True to use the largest Blu-ray playlist without a selection prompt.
        "use_largest_playlist": False,
        # Set to True to retrieve region and distributor information from Blu-ray.com
        # when processing a DVD or Blu-ray disc. Requires an IMDb ID.
        "get_bluray_info": False,
        # Minimum Blu-ray.com match score used in unattended mode.
        # A score of 100 means the Blu-ray.com and BDInfo details match completely.
        # Each missing audio or subtitle track reduces the score by 5 points.
        # A partial audio match reduces the score by 2.5 points.
        # Penalties double when BDInfo contains only one audio or subtitle track.
        # Video codec, resolution, and disc-size mismatches receive large penalties.
        # A release must score above this value to be accepted automatically.
        # Interactive runs prompt for confirmation. Applies only to Blu-ray discs, not DVDs.
        "bluray_score": 94.5,
        # Relaxed minimum score used when Blu-ray.com returns only one release.
        "bluray_single_score": 89.5,
        # Set to True to add a Blu-ray.com link to the description.
        # Requires "get_bluray_info" to be set to True.
        "add_bluray_link": True,
        # Set to True to add available Blu-ray.com cover, back, and slip images.
        # Requires "get_bluray_info" to be set to True.
        "use_bluray_images": True,
        # Width of Blu-ray.com cover images in pixels. BBCode limits image width, and
        # covers are usually taller than screenshots, so a smaller value is preferable.
        "bluray_image_size": "250",
        # --- AUDIO SPECTROGRAMS AND HDR PLOTS ---
        # Audio spectrograms
        # Set to True to add audio spectrograms to the description.
        "add_audio_spectrogram": True,
        # Set to True to generate spectrograms for all audio streams.
        "process_all_audio_spectrogram": False,
        # Seconds from the beginning of each selected stream to analyse.
        "audio_spectrogram_duration": 600,
        # Decode at this sample rate (48 kHz retains frequencies up to 24 kHz).
        "audio_spectrogram_sample_rate": 48000,
        # For music and audiobooks, limit the number of tracks or chapters processed.
        "audio_spectrogram_max_files": 12,
        # Dynamic HDR plots
        # Set to True to generate and add Dolby Vision and HDR10+ metadata plots.
        # Required third-party tools are downloaded automatically on first use.
        # Warning: metadata extraction reads each selected video file in full and may take a while for large releases.
        "add_dynamic_hdr_plot": False,
        # Limit plots generated for multi-file releases.
        "dynamic_hdr_plot_max_files": 1,
        # --- TORRENT CREATION ---
        # Set to True to use mkbrr for torrent creation.
        "mkbrr": True,
        # Number of mkbrr worker threads used for hashing (for example, 8).
        # Different values may improve performance. Use a lower value, such as 1, to reduce resource usage.
        # Set to 0 to choose the thread count automatically.
        "mkbrr_threads": "0",
        # Cooldown, in seconds, before tracker-specific piece-size rehashing begins.
        # Values above 0 let other tasks finish before resource-intensive rehashing starts.
        "rehash_cooldown": "0",
        # --- TRACKER CHECKS AND UPLOAD ---
        # Minimum number of trackers that must pass banned-group, content, and duplicate checks before uploading continues.
        # Default: 1. Upload Assistant exits if fewer trackers pass.
        "tracker_pass_checks": 1,
        # Set to True to show the size difference between a duplicate and the upload during duplicate checks.
        "show_dupe_size_diff": True,
        # Ignore duplicates when their size differs from the upload by at least this percentage.
        # For example, 20 excludes a duplicate that is at least 20% larger or smaller.
        # Set to None or remove this setting to disable the feature.
        "dupe_size_difference_tolerance": None,
        # See docs/upload-order-and-bandwidth-control.md for workflows and qBittorrent requirements.
        "upload_order": "concurrent",
        "qbit_bandwidth_control": False,
        "qbit_bandwidth_control_after_usenet": False,
        "qbit_bandwidth_threshold": 0,
        "qbit_bandwidth_time": 0,
        # Number of retry attempts after network or server errors, such as HTTP 500 responses or timeouts.
        # Can be overridden per tracker by adding the same setting to its configuration.
        "max_retries": 3,
        # Set to True to print how long each tracker upload takes.
        # This can help identify trackers that slow down the overall upload process.
        "show_upload_duration": True,
        # Set to True to print tracker API messages returned during uploads.
        "print_tracker_messages": False,
        # Set to True to print direct torrent links for uploaded content.
        "print_tracker_links": True,
        # --- POST-UPLOAD ---
        # Delay, in seconds, before injecting the torrent. This allows the tracker to register the hash and avoid "unregistered torrent" errors.
        # Can be overridden per tracker by adding the same setting to its configuration.
        "inject_delay": 0,
        # Set to False to disable adding cross-seed-suitable torrents found during duplicate checks.
        "cross_seeding": True,
        # Set to True to check every valid configured tracker for cross-seeding, even when not selected for upload.
        # Requires "cross_seeding" to be set to True.
        "cross_seed_check_everything": False,
        # Set to True to search for matching requests on supported trackers.
        "search_requests": True,
        # Optional trusted scripts from STATE_DIR/custom_hooks/ (Docker: /state/custom_hooks/) run after each item's tracker uploads and request search.
        # Scripts receive final metadata as JSON through stdin and may write status lines to the terminal.
        # Example: ["notify.py"]
        "post_upload_hooks": [],
        # Trusted hooks loaded into Upload Assistant's process. Each must expose an async or sync on_upload_finished(meta, config) function.
        # Each hook receives deep copies of the metadata and configuration.
        "post_upload_inprocess_hooks": [],
        # Maximum time, in seconds, allowed for each subprocess post-upload script.
        # Invalid or zero values use 30 seconds. A failed hook never changes the upload result.
        "post_upload_hook_timeout": 30,
    },
    # these are used for DB links on ALPHARATIO
    "IMAGES": {
        "imdb_75": "https://i.imgur.com/Mux5ObG.png",
        "tmdb_75": "https://i.imgur.com/r3QzUbk.png",
        "tvdb_75": "https://i.imgur.com/UWtUme4.png",
        "tvmaze_75": "https://i.imgur.com/ZHEF5nE.png",
        "mal_75": "https://i.imgur.com/PBfdP3M.png",
    },
    "TRACKERS": {
        # Which trackers do you want to upload to?
        # Note: Description layout settings (like screenshot grids, logos, etc.) can be overridden per-tracker.
        # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/description-builder.md
        # Available trackers:
        #   1PTBA, AITHER, ALPHARATIO, AMIGOSSHARE, ANTHELION, ASIANCINEMA, AVISTAZ, BEYONDHD, BITHDTV, BITPORN, BJSHARE, BLUTOPIA,
        #   BRASILTRACKER, BROADCASTHENET, CAPYBARABR, CATHODERAYTUBE, CINEMATIK, CINEMAZ, CURUPIRA, DARKPEERS, DESITORRENTS, DIGITALCORE,
        #   DREADVAULT, DRUNKENSLUG, EMUWAREZ, FILELIST, FLOOD, FUNFILE, GREATPOSTERWALL, HAWKEUNO, HDBITS, HDSPACE, HDTORRENTS, HOMIEHELPDESK,
        #   IMMORTALSEED, INFINITYHD, IPTORRENTS, ITATORRENTS, LAJIDUI, LASTDIGITALUNDERGROUND, LATTEAM, LEMONHD, LOCADORA, LONGPT, LST,
        #   LUMINARR, MAKINGOFF, MIDNIGHTSCENE, MTEAM, NEBULANCE, NORDICQUALITY, NZBGEEK, OLDTOONSWORLD, ONLYENCODES, ORPHEUS, PASSTHEPOPCORN,
        #   PEERGARDEN, POLISHTORRENT, PORTUGAS, PRIVATEHD, PTCAFE, PTERCLUB, PTFANS, PTGTK, PTSKIT, PTZONE, RACING4EVERYONE, RAILGUNPT,
        #   RASTASTUGAN, REELFLIX, RETROFLIX, RETROMOVIESCLUB, ROCKETHD, SAMARITANO, SEEDPOOL, SHAREISLAND, SKIPTHECOMMERCIALS, SPEEDAPP,
        #   SUIO, SWARMAZON, THELEACHZONE, THEOLDSCHOOL, TORRENTEROS, TORRENTHR, TORRENTLEECH, TOTHEGLORY, TVCHAOSUK, ULCX, UTOPIA,
        #   XINGYUNGEPT, YUSCENE, ZENITH
        # This list is validated against the tracker blocks below by the test suite.
        # Only add the trackers you want to upload to on a regular basis
        "default_trackers": "",
        "1PTBA": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://1ptba.com/ to data/cookies/1PTBA.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "mediainfo_header": "",
            "audio_spectrogram_header": "",
            "custom_signature": "",
            "user_description": "",
            "custom_header": "",
            "custom_footer": "",
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "AITHER": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to AITHER modq for staff approval
            "modq": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Double upload duration in days
            "double_upload_until": 0,
            # For authorized users only. Do not change this unless you know what you are doing
            # Freeleech duration in days
            "freeleech_until": 0,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as refundable
            "refundable": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "ALPHARATIO": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # anon is not an option when uploading you need to change your privacy settings.
            "username": "",
            "password": "",
            "announce_url": "",
            "inject_delay": 0,
        },
        "AMIGOSSHARE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Set uploader_status to True if you have uploader permissions to automatically approve your uploads
            "uploader_status": False,
            # The custom layout default is 2
            # If you have a custom layout, you'll need to inspect the element on the upload page to find the correct layout value
            # Don't change it unless you know what you're doing
            "custom_layout": "2",
            # anon is not an option when uploading to AMIGOSSHARE
            # Cookies required (export from https://cliente.amigos-share.club/ to data/cookies/AMIGOSSHARE.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            # Set this to True if you want to allow external subtitles to be included in the upload
            "allow_ext_subtitles": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "ANTHELION": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "api_key": "",
            "announce_url": "",
            "anon": True,
            # Number of upload retry attempts for network/server errors (e.g. 500, timeouts).
            "max_retries": 5,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "ASIANCINEMA": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "AVISTAZ": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://avistaz.to to data/cookies/AVISTAZ.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # If True, the script performs a basic rules compliance check (e.g., codecs, region).
            # This does not cover all tracker rules. Set to False to disable.
            "check_for_rules": True,
            # The configurations below override the DEFAULT configuration
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "custom_description_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_audio_spectrogram": True,
            "add_dynamic_hdr_plot": True,
            "inject_delay": 0,
        },
        "BEYONDHD": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "bhd_rss_key": "",
            "announce_url": "",
            # Send uploads to BeyondHD drafts
            "draft_default": False,
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "BITHDTV": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # found under https://www.bit-hdtv.com/my.php
            "api_key": "",
            "announce_url": "https://trackerr.bit-hdtv.com/announce",
            # passkey found under https://www.bit-hdtv.com/my.php
            "my_announce_url": "https://trackerr.bit-hdtv.com/passkey/announce",
            "anon": True,
            "inject_delay": 0,
        },
        "BITPORN": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "BJSHARE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://bj-share.info to data/cookies/BJSHARE.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            # Two-factor authentication (2FA) must be enabled in your profile settings; otherwise, your session cookies will expire fairly quickly.
            "announce_url": "",
            "anon": True,
            # Set to False if during an anonymous upload you want your release group to be hidden
            "show_group_if_anon": True,
            # Set this to True if you want to allow external subtitles to be included in the upload
            "allow_ext_subtitles": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[align=center]As capturas de tela foram adaptadas para visualização em SDR, apenas para referência.[/align]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "disc_menu_header": "[size=3][b][align=center]Capturas de Tela do Menu do Disco[/align][/b][/size]",
            "audio_spectrogram_header": "[size=3][b][align=center]Espectrogramas de Áudio[/align][/b][/size]",
            "dynamic_hdr_plot_header": "[size=3][b][align=center]Metadados HDR Dinâmicos[/align][/b][/size]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "BLUTOPIA": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "BRASILTRACKER": {
            "link_dir_name": "",
            # Cookies required (export from https://brasiltracker.org/ to data/cookies/BRASILTRACKER.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # Set this to True if you want to allow external subtitles to be included in the upload
            "allow_ext_subtitles": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[align=center]As capturas de tela foram adaptadas para visualização em SDR, apenas para referência.[/align]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "inject_delay": 0,
        },
        "BROADCASTHENET": {
            # BTN accepts TV only. An API key is required for dupe searching and
            # downloading BTN's registered torrent; upload authentication uses
            # browser-exported cookies in data/cookies/BROADCASTHENET.txt.
            "link_dir_name": "",
            "use_for_search": False,
            "api_key": "",
            "announce_url": "",
            # Optional override for BTN's JSON-RPC endpoint.
            "api_url": "https://api.broadcasthe.net/",
            "inject_delay": 0,
        },
        "CAPYBARABR": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # BiOMA Zipline API key/token for rehosting screenshots when uploading releases with tag 'BiOMA' (Host: https://img.thebioma.space/)
            "bioma_api_key": "",
            # Send uploads to CAPYBARABR modq for staff approval
            "modq": False,
            # Set this to True if you want to allow external subtitles to be included in the upload
            "allow_ext_subtitles": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]As capturas de tela foram adaptadas para visualização em SDR, apenas para referência.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Capturas de Tela[/h2]",
            "disc_menu_header": "[h2]Capturas de Tela do Menu do Disco[/h2]",
            "audio_spectrogram_header": "[h2]Espectrogramas de Áudio[/h2]",
            "dynamic_hdr_plot_header": "[h2]Metadados HDR Dinâmicos[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "CATHODERAYTUBE": {
            # Cookies required (export from https://www.cathode-ray.tube/ to data/cookies/CATHODERAYTUBE.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
        },
        "CINEMATIK": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "CINEMAZ": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://cinemaz.to to data/cookies/CINEMAZ.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # If True, the script performs a basic rules compliance check (e.g., codecs, region).
            # This does not cover all tracker rules. Set to False to disable.
            "check_for_rules": True,
            # The configurations below override the DEFAULT configuration
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "custom_description_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_audio_spectrogram": True,
            "add_dynamic_hdr_plot": True,
            "inject_delay": 0,
        },
        "CURUPIRA": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Your API Key, obtained from Perfil -> API Key
            "api_key": "",
            "anon": True,
            # Only block uploads when the existing release exactly matches files.
            "exact_match_only": False,
            "inject_delay": 0,
        },
        "DARKPEERS": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to DARKPEERS modq for staff approval
            "modq": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            # Audio spectrograms will only be added for music uploads, as requested by the tracker staff.
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "DESITORRENTS": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "DIGITALCORE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # You can find your api key at Settings -> Security -> API Key -> Generate API Key
            "api_key": "",
            "anon": True,
            # If True, the script will use the metadata-based title instead of the directory/file name.
            "use_metadata_name": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "DREADVAULT": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Only block uploads when the existing release exactly matches files and size.
            "exact_match_only": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "DRUNKENSLUG": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Provide the DRUNKENSLUG API key here, can be found at https://drunkenslug.com/profile
            "api_key": "",
            # Maximum number of API hits the script may make within 24 hours for duplicate search.
            # Set to 0 to disable duplicate search via API.
            "daily_api_hit_limit": 0,
            # Only block uploads when the existing release exactly matches files.
            "exact_match_only": False,
            "inject_delay": 0,
        },
        "EMUWAREZ": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Use Spanish title instead of English title, if available
            "use_spanish_title": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "FILELIST": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "username": "",
            "passkey": "",
            "uploader_name": "https://filelist.io/Custom_Announce_URL",
            "anon": True,
            "inject_delay": 0,
        },
        "FLOOD": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "api_key": "",
            "announce_url": "https://flood.st/announce/Custom_Announce_URL",
            "anon": False,
        },
        "FUNFILE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "username": "",
            "password": "",
            # You can find your announce URL by downloading any torrent from FUNFILE, adding it to your client, and then copying the URL from the 'Trackers' tab.
            "announce_url": "",
            # Set to True if you want to check whether your upload fulfills corresponding requests. This may slightly slow down the upload process.
            "check_requests": False,
            # Set to True if you want to include the full MediaInfo in your upload description or False to include only the most relevant parts.
            "full_mediainfo": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "GREATPOSTERWALL": {
            "link_dir_name": "",
            # You can find your API key in Profile Settings -> Access Settings -> API Key. If there is no API, click "Reset your api key" and Save Profile.
            "api_key": "",
            # Optionally, export cookies from https://greatposterwall.com to data/cookies/GREATPOSTERWALL.txt to improve duplicate searches.
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            # You can find your announce URL at https://greatposterwall.com/upload.php
            "announce_url": "",
            # Upload with Exclusive flag
            "exclusive": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "HAWKEUNO": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "use_for_search": False,
            "api_key": "",
            # You can find your announce URL at https://hawke.uno/upload
            "announce_url": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "HDBITS": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            # for HDBITS you **MUST** have been granted uploading approval via Offers, you've been warned
            # Cookies required (export from https://hdbits.org/ to data/cookies/HDBITS.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "username": "",
            "passkey": "",
            "announce_url": "",
            "img_rehost": True,
            "inject_delay": 0,
        },
        "HDSPACE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://hd-space.org/ to data/cookies/HDSPACE.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # Set to True if you want to include the full MediaInfo in your upload description or False to include only the most relevant parts.
            "full_mediainfo": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "HDTORRENTS": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export to data/cookies/HDTORRENTS.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            # You can change the URL if the main site is down or if you encounter upload issues.
            # Keep in mind that changing the URL requires exporting the cookies again from the new domain.
            # Alternative domains:
            #   - https://hd-torrents.org/
            #   - https://hd-torrents.net/
            #   - https://hd-torrents.me/
            #   - https://hdts.ru/
            "url": "https://hd-torrents.me/",
            "anon": True,
            "announce_url": "",
            # Set to True if you want to include the full MediaInfo in your upload description or False to include only the most relevant parts.
            "full_mediainfo": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "HOMIEHELPDESK": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "IMMORTALSEED": {
            # Cookies required (export from https://immortalseed.me/ to data/cookies/IMMORTALSEED.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "announce_url": "",
            "anon": True,
            # Set to True if you want to include the full MediaInfo in your upload description or False to include only the most relevant parts.
            "full_mediainfo": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "INFINITYHD": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "IPTORRENTS": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export to data/cookies/IPTORRENTS.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            # By default, IPTORRENTS removes all dots from the upload name, causing audio codecs to be named incorrectly, for example, "DTS 5 1" instead of "DTS 5.1".
            # It also does not have the option to set the IMDb during upload.
            # Set this to True to edit the torrent after the upload to force the correct naming and IMDb.
            "force_data": False,
            # Set to True if you want to include the full MediaInfo in your upload description or False to include only the most relevant parts.
            "full_mediainfo": False,
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "ITATORRENTS": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "LAJIDUI": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://pt.lajidui.top/ to data/cookies/LAJIDUI.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "LASTDIGITALUNDERGROUND": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "LATTEAM": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to LATTEAM modq for staff approval
            "modq": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "LEMONHD": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://lemonhd.net/ to data/cookies/LEMONHD.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "mediainfo_header": "",
            "audio_spectrogram_header": "",
            "custom_signature": "",
            "user_description": "",
            "custom_header": "",
            "custom_footer": "",
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "LOCADORA": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Set this to True if you want to allow external subtitles to be included in the upload
            "allow_ext_subtitles": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]As capturas de tela foram adaptadas para visualização em SDR, apenas para referência.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Capturas de Tela[/h2]",
            "disc_menu_header": "[h2]Capturas de Tela do Menu do Disco[/h2]",
            "audio_spectrogram_header": "[h2]Espectrogramas de Áudio[/h2]",
            "dynamic_hdr_plot_header": "[h2]Metadados HDR Dinâmicos[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "LONGPT": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://longpt.org/ to data/cookies/LONGPT.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "LST": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to LST modq for staff approval
            "modq": False,
            # Send uploads to LST drafts
            "draft": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "LUMINARR": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to LUMINARR modq for staff approval
            "modq": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "MAKINGOFF": {
            # Cookies required (export from https://www.makingoff.org/ to data/cookies/MAKINGOFF.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # trackers to be added on the torrents
            # one per line
            "trackers": """
                """,
            # Set this to True if you want to allow external subtitles to be included in the upload
            "allow_ext_subtitles": True,
        },
        "MIDNIGHTSCENE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to MIDNIGHTSCENE modq for staff approval
            "modq": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "MTEAM": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "api_key": "",
            "anon": True,
            "base_url": "kp.m-team.cc",
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "NEBULANCE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "api_key": "",
            "announce_url": "",
            "inject_delay": 0,
        },
        "NORDICQUALITY": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "NZBGEEK": {
            "api_key": "",
            # Maximum number of API hits the script may make within 24 hours for duplicate search.
            # Set to 0 to disable duplicate search via API.
            "daily_api_hit_limit": 0,
            # Only block uploads when the existing release exactly matches files.
            "exact_match_only": False,
            "inject_delay": 0,
        },
        "OLDTOONSWORLD": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            # Send uploads to OLDTOONSWORLD modq for staff approval
            "modq": False,
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "ONLYENCODES": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "ORPHEUS": {
            # Orpheus Gazelle API token. Do not commit a real token.
            "api_key": "",
            # Obtain from https://orpheus.network/upload.php
            "announce_url": "",
            "inject_delay": 0,
        },
        "PASSTHEPOPCORN": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "add_web_source_to_desc": True,
            "ApiUser": "ptp api user",
            "api_key": "",
            "username": "",
            "password": "",
            "announce_url": "",
            "inject_delay": 5,
        },
        "PEERGARDEN": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Only block uploads when the existing release exactly matches files and size.
            "exact_match_only": True,
            # Send uploads to PEERGARDEN modq for staff approval
            "modq": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "POLISHTORRENT": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "PORTUGAS": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "PRIVATEHD": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://privatehd.to/ to data/cookies/PRIVATEHD.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # If True, the script performs a basic rules compliance check (e.g., codecs, region).
            # This does not cover all tracker rules. Set to False to disable.
            "check_for_rules": True,
            # The configurations below override the DEFAULT configuration
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "custom_description_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_audio_spectrogram": True,
            "add_dynamic_hdr_plot": True,
            "inject_delay": 0,
        },
        "PTCAFE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://ptcafe.club/ to data/cookies/PTCAFE.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        # PTERCLUB support is currently experimental and may not work reliably.
        "PTERCLUB": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "passkey": "passkey",
            "img_rehost": False,
            "username": "",
            "password": "",
            "ptgen_api": "",
            "anon": True,
            "inject_delay": 0,
        },
        "PTFANS": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://ptfans.cc/ to data/cookies/PTFANS.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "PTGTK": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://pt.gtkpw.xyz to data/cookies/PTGTK.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "PTSKIT": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://www.ptskit.org to data/cookies/PTSKIT.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "PTZONE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://ptzone.xyz/ to data/cookies/PTZONE.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "mediainfo_header": "",
            "audio_spectrogram_header": "",
            "custom_signature": "",
            "user_description": "",
            "custom_header": "",
            "custom_footer": "",
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "RACING4EVERYONE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "announce_url": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "RAILGUNPT": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://bilibili.download to data/cookies/RAILGUNPT.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "RASTASTUGAN": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "REELFLIX": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "RETROFLIX": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "username": "",
            "password": "",
            # get_it_by_running_/api/ login command from https://retroflix.club/api/doc
            "api_key": "",
            "announce_url": "",
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "RETROMOVIESCLUB": {
            # Instead of using the tracker name for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if you want to use Retro Movies Club for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to Retro Movies Club modq for staff approval
            "modq": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "ROCKETHD": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if you want to use RocketHD for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": False,
            # Use German title instead of English title, if available
            "use_german_title": False,
        },
        "SAMARITANO": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Set this to True if you want to allow external subtitles to be included in the upload
            "allow_ext_subtitles": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]As capturas de tela foram adaptadas para visualização em SDR, apenas para referência.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Capturas de Tela[/h2]",
            "disc_menu_header": "[h2]Capturas de Tela do Menu do Disco[/h2]",
            "audio_spectrogram_header": "[h2]Espectrogramas de Áudio[/h2]",
            "dynamic_hdr_plot_header": "[h2]Metadados HDR Dinâmicos[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "SEEDPOOL": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            # Only block uploads when the existing release exactly matches files and size.
            "exact_match_only": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "SHAREISLAND": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Use Italian title instead of English title, if available
            "use_italian_title": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "SKIPTHECOMMERCIALS": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "SPEEDAPP": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # You can create an API key here https://speedapp.io/profile/api-tokens. Required Permission: Upload torrents
            "api_key": "",
            # Select the upload channel, if you don't know what this is, leave it empty.
            # You can also set this manually using the args -ch or --channel, without '@'. Example: @spd -> '-ch spd'.
            "channel": "",
            # If True, the script will use the metadata-based title instead of the folder/file name.
            "use_metadata_name": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "SUIO": {
            # Secret Usenet Indexer: o[redacted]nzbs
            # Please do not share, discuss or mention this indexer's real name in issues or pull requests; nor should you ask what it is.
            # Paste the indexer's base url below (e.g., https://indexer.com)
            # Upload will only proceed if the domain matches the allowed one, protecting your credentials.
            "base_url": "",
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Your Username
            "username": "",
            # Your API Key
            "api_key": "",
            # Maximum number of API hits the script may make within 24 hours for duplicate search.
            # Set to 0 to disable duplicate search via API.
            "daily_api_hit_limit": 0,
            "anon": True,
            # Only block uploads when the existing release exactly matches files.
            "exact_match_only": False,
            # If False, the indexer will decide (uses ID "0").
            # If True, the script will resolve the audio language ID:
            #   - 1 language: uses the ID for that language.
            #   - 2 languages: uses the ID for the language different from the original language.
            #   - 3 or more languages: uses the ID for "multi" ("9").
            #   - No languages: uses "0" (Auto).
            "resolve_language": True,
            "inject_delay": 0,
        },
        "SWARMAZON": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "api_key": "",
            "announce_url": "",
            "inject_delay": 0,
        },
        "THELEACHZONE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "THEOLDSCHOOL": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Mon profil > Réglages > Clé API
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            # Mon profil > Réglages > Passkey
            "announce_url": "",
            "anon": True,
            # Upload with Exclusive flag (team of staff only)
            "exclusive": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "TORRENTEROS": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send to modq for staff approval
            "modq": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "TORRENTHR": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "TORRENTLEECH": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Set to False if you don't have access to the API (e.g., if you're a trial uploader). Note: this may not work sometimes due to Cloudflare restrictions.
            # If you are not going to use the API, you will need to export cookies from https://www.torrentleech.org/ to data/cookies/TORRENTLEECH.txt.
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "api_upload": True,
            # You can find your passkey at your profile (https://www.torrentleech.org/profile/[YourUserName]/view) -> Torrent Passkey
            "passkey": "",
            "anon": True,
            # Rehost images to the TORRENTLEECH image host. Does not work with the API upload method.
            # Keep in mind that screenshots are only anonymous if you enable the "Anonymous Gallery Uploads" option in your profile settings.
            "img_rehost": True,
            # Set to True if you want to include the full MediaInfo in your upload description or False to include only the most relevant parts.
            "full_mediainfo": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "audio_spectrogram_header": "",
            "dynamic_hdr_plot_header": "",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "TOTHEGLORY": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "username": "",
            "password": "",
            "login_question": "",
            "login_answer": "",
            "user_id": "",
            "announce_url": "",
            "anon": True,
            "inject_delay": 0,
        },
        "TVCHAOSUK": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # 2 is listed as max images in rules. Please do not change unless you have permission
            "image_count": 2,
            "api_key": "",
            "announce_url": "",
            "anon": True,
            "inject_delay": 0,
        },
        "ULCX": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send to modq for staff approval
            "modq": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "UTOPIA": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "XINGYUNGEPT": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Cookies required (export from https://pt.xingyungept.org/ to data/cookies/XINGYUNGEPT.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            "announce_url": "",
            "anon": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "",
            "disc_menu_header": "",
            "mediainfo_header": "",
            "audio_spectrogram_header": "",
            "custom_signature": "",
            "user_description": "",
            "custom_header": "",
            "custom_footer": "",
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "YUSCENE": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "ZENITH": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as featured
            "featured": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload with double upload credit
            "doubleup": False,
            # For authorized users only. Do not change this unless you know what you are doing
            # Upload as sticky/pinned
            "sticky": False,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[note]Screenshots have been adapted for SDR viewing, for reference only.[/note]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Screenshots[/h2]",
            "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
            "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
            "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "MANUAL": {
            # Replace link with filebrowser (https://github.com/filebrowser/filebrowser) link to the Upload-Assistant directory, this will link to your filebrowser instead of uploading to uguu.se
            "filebrowser": "",
        },
    },
    # enable_search to True will automatically try and find a suitable hash to save having to rehash when creating torrents
    # If you find issue, especially in local/remote path mapping, use the "--debug" argument to print out some related details
    "TORRENT_CLIENTS": {
        # Name your torrent clients here, for example, this example is named "qbittorrent" and is set as default_torrent_client above
        # All options relate to the webui, make sure you have the webui secured if it has WAN access
        # **DO NOT** modify torrent_client name, eg: "qbit"
        # See https://github.com/wastaken7/Upload-Assistant/blob/development/docs/configuration.md#torrent-clients
        "qbittorrent": {
            "torrent_client": "qbit",
            # QUI reverse proxy: https://getqui.com/docs/features/reverse-proxy
            # Create a Client Proxy API Key in QUI (Settings → Client Proxy Keys), pick the instance, paste the full proxy URL here.
            # Example: "http://localhost:7476/proxy/<your-client-api-key>".
            # QUI is not used for bandwidth measurements; see docs/upload-order-and-bandwidth-control.md.
            "qui_proxy_url": "",
            # enable_search to True will automatically try and find a suitable hash to save having to rehash when creating torrents
            "enable_search": True,
            "qbit_url": "http://127.0.0.1",
            "qbit_port": "8080",
            "qbit_user": "",
            "qbit_pass": "",
            # API Key authentication (stateless, qBittorrent v5.2.0+). When set, qbit_user and qbit_pass are ignored.
            "qbit_api_key": "",
            # Optional qBittorrent BT_backup directory. Used together with QUI/API search;
            # reading .torrent files locally can substantially speed up candidate validation.
            # Use double-backslashes on Windows, e.g. "C:\\Users\\<YOUR_USER>\\AppData\\Local\\qBittorrent\\BT_backup".
            # WARNING: this should not be used when using SQLite Mode for qBittorrent.
            "torrent_storage_dir": "",
            # List of trackers to activate "super-seed" (or "initial seeding") mode when adding the torrent.
            # https://www.bittorrent.org/beps/bep_0016.html
            # Super-seed mode is NOT recommended for general use.
            # Super-seed mode is only recommended for initial seeding servers where bandwidth management is paramount.
            "super_seed_trackers": [""],
            # Use the UA tracker acronym as a tag in qBitTorrent
            "use_tracker_as_tag": False,
            "qbit_tag": "",
            "qbit_cat": "",
            # If using cross seeding, add cross seed tag/category here
            "qbit_cross_tag": "",
            "qbit_cross_cat": "",
            "content_layout": "Original",
            # Choose symbolic links, hard links, or an empty value to use the original path.
            # This will disable any automatic torrent management if set.
            # use either "symlink" or "hardlink"
            # On Windows, symbolic links may require administrator privileges. Both link types
            # require an NTFS/ReFS filesystem, and hard links must remain on the same drive.
            "linking": "",
            # Allow fallback to inject torrent into qBitTorrent using the original path
            # when linking error. eg: unsupported file system.
            "allow_fallback": True,
            # A folder or list of folders that will contain the linked content
            # if using hardlinking, the linked folder must be on the same drive/volume as the original content,
            # with UA mapping the correct location if multiple paths are specified.
            # Use local paths, remote path mapping will be handled.
            # only single \ on windows, path will be handled by UA
            "linked_folder": [""],
            # Remote path mapping (docker/etc.) CASE SENSITIVE
            "local_path": [""],
            "remote_path": [""],
            # Set to False to skip verify certificate for HTTPS connections; for instance, if the connection is using a self-signed certificate.
            # "VERIFY_WEBUI_CERTIFICATE": True,
        },
        "qbittorrent_searching": {
            # an example of using a qBitTorrent client just for searching, when using another client for injection
            "torrent_client": "qbit",
            # QUI reverse proxy: https://getqui.com/docs/features/reverse-proxy
            # Create a Client Proxy API Key in QUI (Settings → Client Proxy Keys), pick the instance, paste the full proxy URL here.
            # Example: "http://localhost:7476/proxy/<your-client-api-key>".
            # QUI is not used for bandwidth measurements; see docs/upload-order-and-bandwidth-control.md.
            "qui_proxy_url": "",
            # enable_search to True will automatically try and find a suitable hash to save having to rehash when creating torrents
            "enable_search": True,
            "qbit_url": "http://127.0.0.1",
            "qbit_port": "8080",
            "qbit_user": "",
            "qbit_pass": "",
        },
        "rtorrent": {
            "torrent_client": "rtorrent",
            "rtorrent_url": "https://user:password@server.host.tld:443/username/rutorrent/plugins/httprpc/action.php",
            # path/to/session folder
            "torrent_storage_dir": "",
            "rtorrent_label": "",
            # Choose symbolic links, hard links, or an empty value to use the original path.
            # this will disable any automatic torrent management if set
            # use either "symlink" or "hardlink"
            # On Windows, symbolic links may require administrator privileges. Both link types
            # require an NTFS/ReFS filesystem, and hard links must remain on the same drive.
            "linking": "",
            # Allow fallback to inject torrent into qBitTorrent using the original path
            # when linking error. eg: unsupported file system.
            "allow_fallback": True,
            # A folder or list of folders that will contain the linked content
            # if using hardlinking, the linked folder must be on the same drive/volume as the original content,
            # with UA mapping the correct location if multiple paths are specified.
            # Use local paths, remote path mapping will be handled.
            # only single \ on windows, path will be handled by UA
            "linked_folder": [""],
            # Remote path mapping (docker/etc.) CASE SENSITIVE
            "local_path": [""],
            "remote_path": [""],
        },
        "deluge": {
            "torrent_client": "deluge",
            "deluge_url": "localhost",
            "deluge_port": "8080",
            "deluge_user": "username",
            "deluge_pass": "password",
            # path/to/session folder
            "torrent_storage_dir": "",
            # Remote path mapping (docker/etc.) CASE SENSITIVE
            "local_path": [""],
            "remote_path": [""],
        },
        "transmission": {
            "torrent_client": "transmission",
            # http or https
            "transmission_protocol": "http",
            "transmission_username": "username",
            "transmission_password": "password",
            "transmission_host": "localhost",
            "transmission_port": 9091,
            "transmission_path": "/transmission/rpc",
            #  path/to/config/torrents folder
            "torrent_storage_dir": "",
            "transmission_label": "",
            # Remote path mapping (docker/etc.) CASE SENSITIVE
            "local_path": [""],
            "remote_path": [""],
        },
        "watch": {
            "torrent_client": "watch",
            # /Path/To/Watch/Folder
            "watch_folder": "",
        },
    },
    "USENET": {
        # --- GENERAL SETTINGS ---
        # Set to True to enable Usenet uploading
        "enabled": False,
        # --- SERVER CONNECTION ---
        # Usenet NNTP host, port, credentials
        "host": "",
        "port": "443",
        "username": "",
        "password": "",
        "ssl": True,
        "connections": "20",
        "newsgroups": "alt.binaries.boneless",
        # Custom poster name/email. E.g. "Uploader <upload@assistant.org>"
        "poster": "Uploader <upload@assistant.org>",
        # If True, poster will be randomized for anonymity/obfuscation
        "random_poster": True,
        # --- ARCHIVING AND PARITY ---
        # Set to True to skip 7z archiving entirely and post files directly.
        # Useful with pesto, which handles obfuscation and PAR2 natively.
        "skip_archive": False,
        # Volume size for 7z splitting (e.g. "100M", "50M", or "auto" for dynamic sizing)
        "rar_volume_size": "auto",
        # Password for 7z archive. Can be a fixed string or "random" to generate a unique random password.
        # Leave empty or set to None to disable archive encryption.
        "archive_password": "random",
        # Percentage of parity recovery blocks for PAR2 (e.g. "10")
        "par2_percentage": "10",
        # Obfuscate the subject line of the NNTP post to prevent DMCA takedowns
        "obscure_subject": True,
        # --- UPLOADER AND VERIFICATION ---
        # Uploader backend: "nyuu" (default) or "pesto"
        # pesto handles PAR2 and NZB password injection internally
        "usenet_uploader": "nyuu",
        # pesto only: a streaming STAT check that runs concurrently with the
        # upload, confirming each article shortly after it posts. Missing
        # articles are reposted and reverified automatically; the upload is
        # only considered successful (and the NZB kept) once every article is
        # confirmed. Strongly recommended — without this, a "successfully
        # posted" article can still be missing/unpropagated on the server,
        # producing a broken NZB.
        "pesto_check": True,
        # Seconds to wait after each article posts before its first STAT check
        # (pesto --check-delay).
        "pesto_check_delay": 5,
        # Number of STAT attempts per article before marking it missing (pesto --check-retries)
        "pesto_check_retries": 3,
        # Dedicated parallel connections for the check queue, carved out of
        # "connections" (never opened on top of it). Empty = pesto auto-derives
        # a small pool from "connections"; if "connections" is too low to spare
        # any, the check is skipped (pesto --check-connections)
        "pesto_check_connections": "",
        # Number of repost+reverify rounds to attempt for articles still missing
        # after the check (pesto --check-post-retries). Raise this on providers
        # with slower or less reliable propagation. Unlike the other
        # pesto_check_* options, "" here does not disable this — it defers to
        # pesto's own default of 1 round instead of 3.
        "pesto_check_post_retries": 3,
        # nyuu only: verify every article is retrievable on the server while
        # posting is still in progress. Missing articles are reposted and
        # reverified automatically; the upload is only considered successful
        # (and the NZB kept) once every article is confirmed. Strongly
        # recommended — without this, a "successfully posted" article can
        # still be missing/unpropagated on the server, producing a broken NZB.
        "nyuu_check": True,
        # Seconds to wait after each article posts before verifying that article
        # (nyuu --check-delay). Keep this low; a larger value can back up the
        # check queue on large uploads and stall posting.
        "nyuu_check_delay": 5,
        # Number of check attempts per article before marking it missing (nyuu --check-tries)
        "nyuu_check_retries": 3,
        # Connections used for the verification pass (nyuu --check-connections).
        # Empty (default) splits "connections" in half between posting and
        # checking, since nyuu checks concurrently with posting and throttles
        # posting speed to match if checking can't keep up — this keeps the
        # combined connection count within what you configured. Set explicitly
        # to instead post at the full "connections" count with this many
        # additional connections dedicated to checking.
        "nyuu_check_connections": "",
        # --- BINARY PATHS ---
        # Paths to binaries (defaults to looking in PATH, downloaded automatically if not found)
        # Available at: https://github.com/animetosho/nyuu
        "nyuu_path": "nyuu",
        # Available at: https://github.com/animetosho/par2cmdline-turbo
        "par2_path": "par2",
        # Available at: https://github.com/franzopl/pesto
        "pesto_path": "pesto",
        # Available at: https://www.7-zip.org/
        "7z_path": "7z",
        # --- OUTPUT PATHS ---
        # Where to output generated NZB files (if empty, saves to tmp directory)
        "nzb_output_dir": "",
        # Temporary directory for Usenet uploads where compressed volumes are stored (if empty, saves to tmp directory)
        "usenet_tmp_dir": "",
    },
}
