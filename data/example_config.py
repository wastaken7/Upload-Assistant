# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

config: dict[str, Any] = {
    "DEFAULT": {
        # MAIN SETTINGS

        # will print a notice if an update is available
        "update_notification": True,
        # will print the changelog if an update is available
        "verbose_notification": False,

        # tmdb api key **REQUIRED**
        # visit "https://www.themoviedb.org/settings/api" copy api key and insert below
        "tmdb_api": "",

        # Google Books API key. "" = disabled
        # You can get one here https://console.cloud.google.com/apis/library/books.googleapis.com
        "google_books_api_key": "",

        # Twitch/IGDB API credentials. "" = disabled
        # You can get them from the Twitch Developer Console (https://dev.twitch.tv/console)
        "twitch_client_id": "",
        "twitch_client_secret": "",

        # MyAnonamouse (MAM) API key / session cookie (mam_id). "" = disabled
        # You can get it from Preferences > Security > View IP locked session cookie
        "mam_api_key": "",

        # tvdb api key
        # visit "https://www.thetvdb.com/api-information/signup" copy api key and insert below
        "tvdb_api": "",

        # visit "https://thetvdb.github.io/v4-api/#/Login/post_login" enter api key, generate token and insert token below
        # the pin in the login form is not needed (don't modify), only enter your api key
        "tvdb_token": "",

        # Play the bell sound effect when asking for confirmation
        "sfx_on_prompt": True,

        # Console logging configuration
        # Show time in console logs
        "console_show_time": False,
        # Show log level in console logs
        "console_show_level": False,
        # Show file path of log source in console logs
        "console_show_path": False,
        # Enable rich markup parsing in console logs
        "console_markup": True,

        # File logging configuration
        # Set true to save a plain text log file of the upload flow in each release's tmp folder
        "write_log": False,

        # Debug configuration
        # Set true to enable debug mode globally (same as running with --debug)
        "debug": False,
        # Console logging configuration when running in debug mode
        # Show time in console logs under debug mode
        "console_debug_show_time": True,
        # Show log level in console logs under debug mode
        "console_debug_show_level": True,
        # Show file path of log source in console logs under debug mode
        "console_debug_show_path": True,
        # Enable rich markup parsing in console logs under debug mode
        "console_debug_markup": True,

        # How many trackers need to pass successful checking to continue with the upload process
        # Default = 1. If 1 (or more) tracker/s pass banned_group, content and dupe checking, uploading will continue
        # If less than the number of trackers pass the checking, exit immediately.
        "tracker_pass_checks": 1,

        # Set true to suppress config warnings on startup
        "suppress_warnings": False,

        # Set true to embed links in duplicate entries using terminal hyperlinks (OSC 8)
        # Set false to display the full raw URLs (recommended for terminals that do not support embedded links)
        "embed_dupe_links": True,

        # Set true to show size difference between duplicate and the upload in duplicate checks
        "show_dupe_size_diff": True,

        # Ignore duplicates if the size difference between the dupe and our upload is greater than or equal to this percentage
        # For example: 20 means a 20% or more difference in size (larger or smaller) will exclude the dupe
        # Set to None/null or remove to disable this feature.
        "dupe_size_difference_tolerance": None,

        # NOT RECOMMENDED UNLESS YOU KNOW WHAT YOU ARE DOING.
        # Will prevent meta.json file from being deleted before running
        "keep_meta": False,

        # IMAGE HOSTING SETTINGS

        # Order of image hosts. primary host as first with others as backup
        # Available image hosts: imgbb, imgbox, pixhost, lensdump, ptscreens, onlyimage, dalexni, zipline, passtheimage, seedpool_cdn, sharex, utppm, lostimg
        "img_host_1": "",
        "img_host_2": "",
        "img_host_3": "",
        "img_host_4": "",
        "img_host_5": "",
        "img_host_6": "",

        # image host api keys
        "imgbb_api": "",
        "lostimg_api": "",
        "lensdump_api": "",
        "ptscreens_api": "",
        "onlyimage_api": "",
        "dalexni_api": "",
        "passtheima_ge_api": "",
        # custom zipline url
        "zipline_url": "",
        "zipline_api_key": "",
        # SEEDPOOL CDN API key
        "seedpool_cdn_api": "",
        # ShareX-style image host (IMageHosting) token
        "sharex_url": "https://img.digitalcore.club/api/upload",
        "sharex_api_key": "",
        # utp.pm API key
        "utppm_api": "",

        # GETTING METADATA

        # btn api key used to get details from btn
        "btn_api": "",

        # set true to skip automated client torrent searching
        # this will search qbittorrent clients for matching torrents
        # and use found torrent id's for existing hash and site searching
        'skip_auto_torrent': False,

        # Set to true to always just use the largest playlist on a blu-ray, without selection prompt.
        "use_largest_playlist": False,

        # Set False to skip getting images from tracker descriptions
        "keep_images": True,

        # Set to True to only import metadata IDs (IMDB, TMDB, TVDB, MAL) from other trackers,
        # skipping the extraction and import of description/synopsis texts.
        # Note: Description images are still controlled by the 'keep_images' setting.
        "skip_tracker_descriptions": False,

        # set true to use argument overrides from data/templates/user-args.json
        "user_overrides": False,

        # Automatically set --personalrelease to True if the detected release group matches any of these tags (case-insensitive)
        "personal_release_groups": [],

        # If there is no region/distributor ids specified, we can use existing torrents to check
        # This will use data from matching torrents in qBitTorrent/RuTorrent to find matching site ids
        # and then try and find region/distributor ids from those sites
        # Requires "skip_auto_torrent" to be set to False
        "ping_unit3d": False,

        # If processing a dvd/bluray disc, get related information from bluray.com
        # This will set region and distribution info
        # Must have imdb id to work
        "get_bluray_info": False,

        # A release with 100% score will have complete matching details between bluray.com and bdinfo
        # Each missing Audio OR Subtitle track will reduce the score by 5
        # Partial matched audio tracks have a 2.5 score penalty
        # If only a single bdinfo audio/subtitle track, penalties are doubled
        # Video codec/resolution and disc size mismatches have huge penalties
        # Only useful in unattended mode. If not unattended you will be prompted to confirm release
        # Final score must be greater than this value to be considered a match
        # Only works with blu-ray discs, not dvd
        "bluray_score": 94.5,

        # If there is only a single release on bluray.com, you may wish to relax the score a little
        "bluray_single_score": 89.5,

        # Set true to also try searching predb for scene release
        # predb is not consistent, can timeout, but can find some releases not found on SRRDB
        "check_predb": False,

        # SCREENSHOT HANDLING

        # Number of screenshots to capture
        "screens": "4",

        # Set true to automatically capture DVD menu screenshots from menu VOBs
        "auto_dvd_menus": True,

        # Max number of disc menu screenshots to upload
        "max_menu_screens": "6",

        # Minimum successful image uploads required to continue
        "min_successful_image_uploads": "3",

        # Number of cutoff screenshots
        # If there are at least this many screenshots already, perhaps pulled from existing
        # description, skip creating and uploading any further screenshots.
        "cutoff_screens": "4",

        # Overlay Frame number/type and "Tonemapped" if applicable to screenshots
        "frame_overlay": False,

        # Overlay text size (scales with resolution)
        "overlay_text_size": "18",

        # Limit how many ffmpeg processes can run at once
        # The final value will be the minimum, between this value and number of screens being processed
        "process_limit": "4",

        # Set true to limit the amount of CPU when running ffmpeg.
        # This places an additional limitation on ffmpeg to reduce CPU usage
        "ffmpeg_limit": False,

        # Tonemap HDR - DV+HDR screenshots
        "tone_map": True,

        # Set false to disable libplacebo ffmpeg tonemapping and use ffmpeg only
        # This is a good toggle if you have any ffmpeg related issues when tonemapping, especially on seedboxes
        "use_libplacebo": True,

        # Set true to skip ffmpeg check, useful if you know your ffmpeg is compatible with libplacebo
        # Else, when tonemapping is enabled (and used), UA will run a quick check before to decide
        "ffmpeg_is_good": False,

        # Set true to skip "warming up" libplacebo
        # Some systems are slow to compile libplacebo shaders, which will cause the first screenshot to fail
        "ffmpeg_warmup": False,

        # Set ffmpeg compression level for screenshots (0-9)
        # 6 is a good balance between compression and speed
        "ffmpeg_compression": "6",

        # Optional path to the unRAR executable for CBR/CBZ extraction.
        # Leave blank to use the system PATH.
        # Example: "C:\\Program Files\\WinRAR\\UnRAR.exe"
        "unrar_path": "",

        # Tonemap screenshots with the following settings (doesn't apply when using libplacebo)
        # See https://ayosec.github.io/ffmpeg-filters-docs/7.1/Filters/Video/tonemap.html
        "algorithm": "mobius",

        # Apply desaturation for highlights that exceed this level of brightness. The higher the parameter, the more color information will be preserved. This setting helps prevent unnaturally blown-out colors for super-highlights, by (smoothly) turning into white instead. This makes images feel more natural, at the cost of reducing information about out-of-range colors.
        # The default of 2.0 is somewhat conservative and will mostly just apply to skies or directly sunlit surfaces. A setting of 0.0 disables this option.
        # This option works only if the input frame has a supported color tag.
        "desat": "10.0",

        # DESCRIPTION SETTINGS
        # Detailed documentation on how description layout settings work and affect description building:
        # https://github.com/wastaken7/Upload-Assistant/blob/development/docs/description-builder.md

        # Whether to add a logo for the show/movie from TMDB to the top of the description
        "add_logo": True,

        # Logo image size
        "logo_size": "300",

        # logo language (ISO 639-1) - default is 'en' (English)
        # If a logo with this language cannot be found, English will be used instead
        "logo_language": "",

        # Providing the option to change the size of the screenshot thumbnails where supported.
        # Default is 350, ie [img=350]
        "thumbnail_size": "350",

        # Number of screenshots per row in the description. Default is single row.
        # Only for sites that use common description
        "screens_per_row": "",

        # set true to add episode overview to description
        "episode_overview": True,

        # Add this header above screenshots in description when screens have been tonemapped (in bbcode)
        # Can be overridden in a per-tracker setting by adding this same config
        "tonemapped_header": "[center]Screenshots have been adapted for SDR viewing, for reference only.[/center]",

        # Number of screenshots to use for each (ALL) disc/episode when uploading packs to supported sites.
        # 0 equals old behavior where only the original description and images are added.
        # This setting also affects PASSTHEPOPCORN, however PASSTHEPOPCORN requires at least 2 images for each.
        # PASSTHEPOPCORN will always use a *minimum* of 2, regardless of what is set here.
        "multiScreens": "2",

        # The next options for packed content do not effect PASSTHEPOPCORN. PASSTHEPOPCORN has a set standard.
        # When uploading packs, you can specify a different screenshot thumbnail size, default 300.
        "pack_thumb_size": "300",

        # Description character count (including bbcode) cutoff for UNIT3D sites when **season packs only**.
        # After hitting this limit, only filenames and screenshots will be used for any ADDITIONAL files
        # still to be added to the description. You can set this small like 50, to only ever
        # print filenames and screenshots for each file, no mediainfo will be printed.
        # UNIT3D sites have a hard character limit for descriptions. A little over 17000
        # worked fine in a forum post at AITHER. If the description is at 1 < charLimit, the next full
        # description will be added before respecting this cutoff.
        "charLimit": "14000",

        # How many files in a season pack will be added to the description before using an additional spoiler tag.
        # Any other files past this limit will be hidden/added all within a spoiler tag.
        "fileLimit": "2",

        # Absolute limit on processed files in packs.
        # You might not want to process screens/mediainfo for 40 episodes in a season pack.
        "processLimit": "10",

        # Providing the option to add a description header, in bbcode, at the top of the description section where supported
        # Can be overridden in a per-tracker setting by adding this same config
        "custom_description_header": "",

        # Providing the option to add a header, in bbcode, above the screenshot section where supported
        # Can be overridden in a per-tracker setting by adding this same config
        "screenshot_header": "[h2]Screenshots[/h2]",

        # Applicable only to raw discs (Blu-ray/DVD).
        # Providing the option to add a header, in bbcode, above the section featuring screenshots of the Disc menus, where supported
        # Can be overridden in a per-tracker setting by adding this same config
        "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",

        # Header to add above the audio spectrograms
        "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",

        # Allows adding a custom signature, in BBCode, at the bottom of the description section
        # Can be overridden in a per-tracker setting by adding this same config
        "custom_signature": "",

        # Add bluray.com link to description
        # Requires "get_bluray_info" to be set to True
        "add_bluray_link": True,

        # Add cover/back/slip images from bluray.com to description if available
        # Requires "get_bluray_info" to be set to True
        "use_bluray_images": True,

        # Size of bluray.com cover images.
        # bbcode is width limited, cover images are mostly height dominant
        # So you probably want a smaller size than screenshots for instance
        "bluray_image_size": "250",

        # Set true to add audio spectrograms to the description
        "add_audio_spectrogram": True,
        # Set true to generate spectrograms for all audio streams
        "process_all_audio_spectrogram": False,

        # CLIENT SETUP

        # Configures the order of uploads when both torrent trackers and Usenet are selected.
        # "concurrent" (default) -> Upload to Usenet and torrent trackers at the same time.
        # "usenet"               -> Upload to Usenet first. Torrent tracker uploads will start after Usenet upload finishes.
        # "tracker"              -> Upload to torrent trackers first. Once finished, we run the bandwidth check, and then start the Usenet upload.
        "upload_order": "concurrent",

        # Enable bandwidth control to wait for lower qBittorrent upload speed before uploading next tracker
        "qbit_bandwidth_control": False,

        # Threshold in KB/s. If the average upload speed is below this value, the next upload can start.
        "qbit_bandwidth_threshold": 0,

        # The duration of time in seconds to average the upload speed over.
        "qbit_bandwidth_time": 0,

        # Which client are you using.
        "default_torrent_client": "qbittorrent",

        # A list of clients to use for injection (aka actually adding the torrent for uploading)
        # eg: ["qbittorrent", "rtorrent"]
        # Will fallback to default_torrent_client if empty
        # "injecting_client_list": [""],

        # A list of clients to search for torrents.
        # eg: ["qbittorrent", "qbittorrent_searching"]
        # will fallback to default_torrent_client if empty
        # "searching_client_list": [""],

        # ARR* INTEGRATION SETTINGS

        # set true to use sonarr for tv show searching
        "use_sonarr": False,
        "sonarr_url": "http://localhost:8989",
        "sonarr_api_key": "",

        # details for a second sonarr instance
        # additional sonarr instances can be added by adding more sonarr_url_x and sonarr_api_key_x entries
        "sonarr_url_1": "http://my-second-instance:8989",
        "sonarr_api_key_1": "",

        # set true to use radarr for movie searching
        "use_radarr": False,
        "radarr_url": "http://localhost:7878",
        "radarr_api_key": "",

        # details for a second radarr instance
        # additional radarr instances can be added by adding more radarr_url_x and radarr_api_key_x entries
        "radarr_url_1": "http://my-second-instance:7878",
        "radarr_api_key_1": "",

        # TORRENT CREATION

        # set true to use mkbrr for torrent creation
        "mkbrr": True,

        # Create using a specific number of worker threads for hashing (e.g., 8) with mkbrr
        # Experimenting with different values might yield better performance than the default automatic setting.
        # Conversely, you can set a lower amount such as 1 to protect system resources (default "0" (auto))
        "mkbrr_threads": "0",

        # Set true to prefer torrents with piece size <= 16 MiB when searching for existing torrents in clients
        # Does not override MORETHANTV preference for small pieces
        "prefer_max_16_torrent": False,

        # Tracker based rehashing cooldown.
        # For trackers that might need specific piece size rehashing, using a value higher than 0 will add the specified cooldown
        # in (seconds) before rehashing begins, to allow other tasks to complete quickly, before resources are consumed by rehashing
        "rehash_cooldown": "0",

        # POST UPLOAD

        # Delay (in seconds) before injecting the torrent to allow the tracker to register the hash and avoid 'unregistered torrent' errors.
        # Can be overridden in a per-tracker setting by adding this same config
        "inject_delay": 0,

        # Whether or not to print how long the upload process took for each tracker
        # Useful for knowing which trackers are slowing down the overall upload process
        "show_upload_duration": True,

        # Set true to print the tracker api messages from uploads
        "print_tracker_messages": False,

        # Whether or not to print direct torrent links for the uploaded content
        "print_tracker_links": True,

        # Set true to search for matching requests on supported trackers
        "search_requests": True,

        # Set false to disable adding cross-seed suitable torrents found during existing search (dupe) checking
        "cross_seeding": True,
        # Set true to cross-seed check every valid tracker defined in your config
        # regardless of whether the tracker was selected for upload or not (needs cross-seeding above to be True)
        "cross_seed_check_everything": False,

        # Use MusicBrainz only as corroborating metadata. Local file tags remain
        # authoritative and no external lookup is made unless this is enabled.
        "music_enrichment_enabled": False,

        # Optional Discogs personal access token. A supplied --music-discogs-id
        # performs a bounded read-only lookup; this token raises Discogs API
        # limits but is never written to release metadata or logs.
        "music_discogs_token": "",

    },

    # these are used for DB links on ALPHARATIO
    "IMAGES": {
        "imdb_75": 'https://i.imgur.com/Mux5ObG.png',
        "tmdb_75": 'https://i.imgur.com/r3QzUbk.png',
        "tvdb_75": 'https://i.imgur.com/UWtUme4.png',
        "tvmaze_75": 'https://i.imgur.com/ZHEF5nE.png',
        "mal_75": 'https://i.imgur.com/PBfdP3M.png'
    },

    "TRACKERS": {
        # Which trackers do you want to upload to?
        # Note: Description layout settings (like screenshot grids, logos, etc.) can be overridden per-tracker.
        # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/description-builder.md

        # Available tracker: AURA4K, ASIANCINEMA, AITHER, ANTHELION, ALPHARATIO, AMIGOSSHARE, AVISTAZ, BEYONDHD, BITHDTV, BJSHARE, BLUTOPIA, BRASILTRACKER, CAPYBARABR, CURUPIRA, SUIO, CINEMAZ, DIGITALCORE, DRUNKENSLUG, DARKPEERS, DESITORRENTS, EMUWAREZ, FUNFILE, FILELIST,
        # GREATPOSTERWALL, HDBITS, HDSPACE, HDTORRENTS, HOMIEHELPDESK, HAWKEUNO, INFINITYHD, IMMORTALSEED, ITATORRENTS, LAJIDUI, LOCADORA, LASTDIGITALUNDERGROUND, LONGPT, LST, LATTEAM, LUMINARR, MIDNIGHTSCENE, MTEAM, MORETHANTV, NEBULANCE, ONLYENCODES,
        # OLDTOONSWORLD, PRIVATEHD, PORTUGAS, PTCAFE, PTERCLUB, PTFANS, PTGTK, PASSTHEPOPCORN, PEERGARDEN, PTSKIT, POLISHTORRENT, RACING4EVERYONE, RASTASTUGAN, REELFLIX, RAILGUNPT, RETROFLIX, SAMARITANO, SHAREISLAND, SWARMAZON, SEEDPOOL, SPEEDAPP, SKIPTHECOMMERCIALS, TORRENTHR,
        # CINEMATIK, ORPHEUS, TORRENTLEECH, THELEACHZONE, THEOLDSCHOOL, TOTHEGLORY, TORRENTEROS, TVCHAOSUK, ULCX, UTOPIA, YUSCENE, ZENITH

        # Only add the trackers you want to upload to on a regular basis
        "default_trackers": "",

        "AITHER": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to AITHER modq for staff approval
            "modq": False,
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
            "custom_layout": '2',
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
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "AURA4K": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to AURA4K modq for staff approval
            "modq": False,
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
            "episode_overview": True,
            "add_audio_spectrogram": True,
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
        "CAPYBARABR": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to CAPYBARABR modq for staff approval
            "modq": False,
            # Set this to True if you want to allow external subtitles to be included in the upload
            "allow_ext_subtitles": True,
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[center]As capturas de tela foram adaptadas para visualização em SDR, apenas para referência.[/center]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Capturas de Tela[/h2]",
            "disc_menu_header": "[h2]Capturas de Tela do Menu do Disco[/h2]",
            "audio_spectrogram_header": "[h2]Espectrogramas de Áudio[/h2]",
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "CINEMATIK": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
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
            "episode_overview": True,
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "CURUPIRA": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # Your API Key, obtained from Perfil -> API Key
            "api_key": "",
            "anon": True,
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
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
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
            "custom_signature": "",
            "add_bluray_link": True,
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
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[center]As capturas de tela foram adaptadas para visualização em SDR, apenas para referência.[/center]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Capturas de Tela[/h2]",
            "disc_menu_header": "[h2]Capturas de Tela do Menu do Disco[/h2]",
            "audio_spectrogram_header": "[h2]Espectrogramas de Áudio[/h2]",
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
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "MAKINGOFF":{
            # Cookies required (export from https://www.makingoff.org/ to data/cookies/MAKINGOFF.txt).
            # See: https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md#how-to-export-cookies
            # trackers to be added on the torrents
            # one per line
            "trackers":
                """
                """,
            # Set this to True if you want to allow external subtitles to be included in the upload
            "allow_ext_subtitles": True,
        },
        "MIDNIGHTSCENE":{
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            "anon": True,
            # Send uploads to MIDNIGHTSCENE modq for staff approval
            "modq": False,
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
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "MORETHANTV": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # get from security page
            'api_key': '',
            'username': '',
            'password': '',
            'announce_url': "get from https://www.morethantv.me/upload.php",
            'anon': False,
            # read the following for more information https://github.com/google/google-authenticator/wiki/Key-Uri-Format
            'otp_uri': 'OTP URI,',
            # Skip uploading to MORETHANTV if it would require a torrent rehash because existing piece size > 8 MiB
            'skip_if_rehash': False,
            # Iterate over found torrents and prefer MORETHANTV suitable torrents if found.
            'prefer_mtv_torrent': False,
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
        "OLDTOONSWORLD": {
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            # "use_for_search": False, set to True if using this tracker for automatic ID searching or description parsing
            "use_for_search": False,
            "api_key": "",
            # Send uploads to OLDTOONSWORLD modq for staff approval
            "modq": False,
            "anon": True,
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
            "base_url": "https://orpheus.network",
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
            # Send uploads to PEERGARDEN modq for staff approval
            "modq": False,
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
            "episode_overview": True,
            "add_audio_spectrogram": True,
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
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
        },
        "PTERCLUB": {  # Does not appear to be working at all
            # Instead of using the tracker acronym for folder name when sym/hard linking, you can use a custom name
            "link_dir_name": "",
            "passkey": 'passkey',
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
            "custom_signature": "",
            "add_bluray_link": True,
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
            "custom_signature": "",
            "add_bluray_link": True,
            "use_bluray_images": True,
            "bluray_image_size": "",
            "add_audio_spectrogram": True,
            "inject_delay": 0,
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
            # The configurations below override the DEFAULT configuration
            "add_logo": True,
            "logo_size": "",
            "thumbnail_size": "",
            "screens_per_row": "",
            "episode_overview": True,
            "tonemapped_header": "[center]As capturas de tela foram adaptadas para visualização em SDR, apenas para referência.[/center]",
            "multiScreens": "",
            "pack_thumb_size": "",
            "charLimit": "",
            "fileLimit": "",
            "processLimit": "",
            "custom_description_header": "",
            "screenshot_header": "[h2]Capturas de Tela[/h2]",
            "disc_menu_header": "[h2]Capturas de Tela do Menu do Disco[/h2]",
            "audio_spectrogram_header": "[h2]Espectrogramas de Áudio[/h2]",
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
            "username": "",
            "password": "",
            "img_api": "get this from the forum post",
            "announce_url": "",
            "pronfo_api_key": "",
            "pronfo_theme": "pronfo theme code",
            "pronfo_rapi_id": "pronfo remote api id",
            "anon": True,
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
            "custom_signature": "",
            "add_bluray_link": True,
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
        # See https://github.com/Audionut/Upload-Assistant/wiki
        "qbittorrent": {
            "torrent_client": "qbit",
            # QUI reverse proxy: https://getqui.com/docs/features/reverse-proxy
            # Create a Client Proxy API Key in QUI (Settings → Client Proxy Keys), pick the instance, paste the full proxy URL here.
            # Example: "http://localhost:7476/proxy/<your-client-api-key>". Bandwidth Control still requires qbit_url/qbit_port and qbit_api_key or qbit_user/qbit_pass.
            "qui_proxy_url": "",
            # enable_search to True will automatically try and find a suitable hash to save having to rehash when creating torrents
            "enable_search": True,
            "qbit_url": "http://127.0.0.1",
            "qbit_port": "8080",
            "qbit_user": "",
            "qbit_pass": "",
            # API Key authentication (stateless, qBittorrent v5.2.0+). When set, qbit_user and qbit_pass are ignored.
            "qbit_api_key": "",
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
            # Here you can chose to use either symbolic or hard links, or None to use original path.
            # This will disable any automatic torrent management if set.
            # use either "symlink" or "hardlink"
            # on windows, symlinks needs admin privs, both link types need ntfs/refs filesytem (and same drive)
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
            # only set qBitTorrent torrent_storage_dir if API searching does not work
            # use double-backslash on windows eg: "C:\\client\\backup"
            # "torrent_storage_dir": "path/to/BT_backup folder",

            # Set to False to skip verify certificate for HTTPS connections; for instance, if the connection is using a self-signed certificate.
            # "VERIFY_WEBUI_CERTIFICATE": True,
        },
        "qbittorrent_searching": {
            # an example of using a qBitTorrent client just for searching, when using another client for injection
            "torrent_client": "qbit",
            # QUI reverse proxy: https://getqui.com/docs/features/reverse-proxy
            # Create a Client Proxy API Key in QUI (Settings → Client Proxy Keys), pick the instance, paste the full proxy URL here.
            # Example: "http://localhost:7476/proxy/<your-client-api-key>". Bandwidth Control still requires qbit_url/qbit_port and qbit_api_key or qbit_user/qbit_pass.
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
            # here you can chose to use either symbolic or hard links, or None to use original path
            # this will disable any automatic torrent management if set
            # use either "symlink" or "hardlink"
            # on windows, symlinks needs admin privs, both link types need ntfs/refs filesytem (and same drive)
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
        # Set to True to enable Usenet uploading
        "enabled": False,
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
        # Seconds to wait after EACH article posts before its first STAT check
        # (streaming, concurrent with the upload — not a single wait at the end
        # of the whole run) (pesto --check-delay)
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
        # Seconds to wait after EACH article is posted before verifying that
        # specific article (nyuu --check-delay). Unlike pesto's check_delay
        # (a single wait after the whole upload finishes), this applies
        # per-article, so keep it low — nyuu's own default is 5. A larger value
        # here backs up the check queue on big uploads and can stall posting.
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
        # Paths to binaries (defaults to looking in PATH, downloaded automatically if not found)
        # Available at: https://github.com/animetosho/nyuu
        "nyuu_path": "nyuu",
        # Available at: https://github.com/animetosho/par2cmdline-turbo
        "par2_path": "par2",
        # Available at: https://github.com/franzopl/pesto
        "pesto_path": "pesto",
        # Available at: https://www.7-zip.org/
        "7z_path": "7z",
        # Where to output generated NZB files (if empty, saves to tmp directory)
        "nzb_output_dir": "",
        # Temporary directory for Usenet uploads where compressed volumes are stored (if empty, saves to tmp directory)
        "usenet_tmp_dir": "",
    },
}
