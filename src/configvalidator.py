# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""
Config validation helper for Upload Assistant.
Validates the user's config.py against expected structure and types.
"""

import math
from pathlib import Path
from typing import Any, cast

from src.app_paths import STATE_DIR

# Required top-level sections
REQUIRED_SECTIONS = ["DEFAULT", "TRACKERS"]

# Optional top-level sections
OPTIONAL_SECTIONS = ["IMAGES", "TORRENT_CLIENTS", "USENET"]
HOOKS_DIR = STATE_DIR / "custom_hooks"

# Required keys in DEFAULT section (critical for operation)
REQUIRED_DEFAULT_KEYS: dict[str, type] = {
    "tmdb_api": str,
}

# Expected types for common DEFAULT keys (for type validation, not required)
DEFAULT_KEY_TYPES: dict[str, tuple[type, ...]] = {
    "update_notification": (bool,),
    "verbose_notification": (bool,),
    "update_notification_cache_hours": (str, int, float),
    "tmdb_api": (str,),
    "tvdb_api": (str,),
    "tvdb_token": (str,),
    "btn_api": (str,),
    "img_host_1": (str,),
    "img_host_2": (str,),
    "img_host_3": (str,),
    "smart_image_host_selection": (bool,),
    "image_upload_concurrency": (str, int),
    "image_upload_delay": (str, float, int),
    "imgbb_api": (str,),
    "lostimg_api": (str,),
    "lensdump_api": (str,),
    "ptscreens_api": (str,),
    "onlyimage_api": (str,),
    "midnightscene_api_key": (str,),
    "add_logo": (bool,),
    "logo_size": (str, int),
    "episode_overview": (bool,),
    "screens": (str, int),
    "xxx_contact_sheet_rows": (str, int),
    "xxx_contact_sheet_columns": (str, int),
    "xxx_contact_sheet_max_videos": (str, int),
    "xxx_contact_sheet_animated_webp": (bool,),
    "xxx_contact_sheet_animation_seconds": (str, int, float),
    "xxx_single_file_screens": (str, int),
    "cutoff_screens": (str, int),
    "max_menu_screens": (str, int),
    "thumbnail_size": (str, int),
    "frame_overlay": (bool,),
    "tone_map": (bool,),
    "auto_dvd_menus": (bool,),
    "scale_screenshots_for_par": (bool,),
    "use_libplacebo": (bool,),
    "ffmpeg_is_good": (bool,),
    "ffmpeg_warmup": (bool,),
    "ffmpeg_compression": (str, int),
    "ffmpeg_path": (str,),
    "ffprobe_path": (str,),
    "mediainfo_path": (str,),
    "dvd_mediainfo_path": (str,),
    "bdinfo_path": (str,),
    "mkbrr_path": (str,),
    "dovi_tool_path": (str,),
    "hdr10plus_tool_path": (str,),
    "process_limit": (str, int),
    "threads": (str, int),
    "ffmpeg_limit": (bool,),
    "multiScreens": (str, int),
    "pack_thumb_size": (str, int),
    "charLimit": (str, int),
    "fileLimit": (str, int),
    "processLimit": (str, int),
    "default_torrent_client": (str,),
    "skip_auto_torrent": (bool,),
    "skip_auto_torrent_personalrelease": (bool,),
    "sfx_on_prompt": (bool,),
    "console_show_time": (bool,),
    "console_show_level": (bool,),
    "console_show_path": (bool,),
    "console_markup": (bool,),
    "debug": (bool,),
    "console_debug_show_time": (bool,),
    "console_debug_show_level": (bool,),
    "console_debug_show_path": (bool,),
    "console_debug_markup": (bool,),
    "embed_links": (bool,),
    "embed_dupe_links": (bool,),
    "show_dupe_size_diff": (bool,),
    "dupe_size_difference_tolerance": (float, int),
    "tracker_pass_checks": (str, int),
    "use_largest_playlist": (bool,),
    "tracker_description_mode": (str,),
    "tracker_search_concurrency": (str, int),
    "tracker_comment_only": (bool,),
    "use_sonarr": (bool,),
    "use_radarr": (bool,),
    "mkbrr": (bool,),
    "mkbrr_threads": (str, int),
    "add_dynamic_hdr_plot": (bool,),
    "dynamic_hdr_plot_header": (str,),
    "dynamic_hdr_plot_max_files": (str, int),
    "user_overrides": (bool,),
    "ping_unit3d": (bool,),
    "get_bluray_info": (bool,),
    "add_bluray_link": (bool,),
    "use_bluray_images": (bool,),
    "bluray_image_size": (str, int),
    "bluray_score": (float, int),
    "bluray_single_score": (float, int),
    "keep_meta": (bool,),
    "post_upload_hooks": (list, tuple),
    "post_upload_inprocess_hooks": (list, tuple),
    "post_upload_hook_timeout": (str, int, float),
    "show_upload_duration": (bool,),
    "print_tracker_messages": (bool,),
    "print_tracker_links": (bool,),
    "search_requests": (bool,),
    "check_predb": (bool,),
    "prefer_max_16_torrent": (bool,),
    "cross_seeding": (bool,),
    "cross_seed_check_everything": (bool,),
    "auto_mode": (bool, str),
    "google_books_api_key": (str,),
    "mam_api_key": (str,),
    "mam_id": (str,),
    "twitch_client_id": (str,),
    "twitch_client_secret": (str,),
    "upload_order": (str,),
    "qbit_bandwidth_control": (bool,),
    "qbit_bandwidth_control_after_usenet": (bool,),
    "qbit_bandwidth_threshold": (str, int),
    "qbit_bandwidth_time": (str, int),
    "music_enrichment_enabled": (bool,),
    "music_discogs_token": (str,),
    "metadata_cache_enabled": (bool,),
    "metadata_cache_dir": (str,),
    "metadata_cache_default_ttl_hours": (int,),
    "metadata_cache_negative_ttl_minutes": (int,),
    "metadata_cache_services": (dict,),
    "tracker_metadata_cache_enabled": (bool,),
    "tracker_metadata_cache_dir": (str,),
    "tracker_metadata_cache_ttl_hours": (int,),
    "tracker_metadata_cache_negative_ttl_minutes": (int,),
}

# Valid image hosts
VALID_IMAGE_HOSTS = [
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
    "sharex",
    "utppm",
    "lostimg",
    "",
]

# Image hosts that require API keys and their corresponding config key names
IMAGE_HOST_API_KEYS: dict[str, str] = {
    "imgbb": "imgbb_api",
    "lostimg": "lostimg_api",
    "lensdump": "lensdump_api",
    "ptscreens": "ptscreens_api",
    "onlyimage": "onlyimage_api",
    "dalexni": "dalexni_api",
    "passtheimage": "passtheima_ge_api",
    "seedpool_cdn": "seedpool_cdn_api",
    "sharex": "sharex_api_key",
    "zipline": "zipline_api_key",
    "midnightscene": "midnightscene_api_key",
    "utppm": "utppm_api",
    # imgbox and pixhost don't require API keys
}

# Valid torrent client types (must match example_config.py)
VALID_TORRENT_CLIENTS = ["qbit", "rtorrent", "deluge", "transmission", "watch"]

# Required keys in USENET section when Usenet uploading is active
USENET_REQUIRED_KEYS = ["host", "port", "username", "password", "newsgroups"]

# Expected types for known USENET keys (must match data/example_config.py's USENET section)
USENET_KEY_TYPES: dict[str, tuple[type, ...]] = {
    "enabled": (bool,),
    "host": (str,),
    "port": (str, int),
    "username": (str,),
    "password": (str,),
    "ssl": (bool,),
    "connections": (str, int),
    "newsgroups": (str,),
    "poster": (str,),
    "random_poster": (bool,),
    "skip_archive": (bool,),
    "rar_volume_size": (str,),
    "archive_password": (str,),
    "par2_percentage": (str, int),
    "obscure_subject": (bool,),
    "usenet_uploader": (str,),
    "pesto_check": (bool,),
    "pesto_check_delay": (str, int),
    "pesto_check_retries": (str, int),
    "pesto_check_connections": (str, int),
    "pesto_check_post_retries": (str, int),
    "nyuu_check": (bool,),
    "nyuu_check_delay": (str, int),
    "nyuu_check_retries": (str, int),
    "nyuu_check_connections": (str, int),
    "nyuu_path": (str,),
    "par2_path": (str,),
    "pesto_path": (str,),
    "7z_path": (str,),
    "nzb_output_dir": (str,),
    "usenet_tmp_dir": (str,),
}

# USENET keys expected to hold a plain integer or a numeric string
USENET_NUMERIC_STRING_KEYS = [
    "port",
    "connections",
    "par2_percentage",
    "pesto_check_delay",
    "pesto_check_retries",
    "pesto_check_connections",
    "pesto_check_post_retries",
    "nyuu_check_delay",
    "nyuu_check_retries",
    "nyuu_check_connections",
]


class ConfigValidationError(Exception):
    """Raised when config validation fails with critical errors."""


class ConfigValidationWarning:
    """Represents a non-critical config warning."""

    def __init__(self, message: str, key: str = "", section: str = ""):
        """Create a warning with optional config location metadata."""
        self.message = message
        self.key = key
        self.section = section

    def __str__(self) -> str:
        """Render the warning with its section and key when available."""
        location = ""
        if self.section:
            location = f"[{self.section}]"
            if self.key:
                location += f"[{self.key}]"
        elif self.key:
            location = f"[{self.key}]"

        return f"{location} {self.message}" if location else self.message


def _as_dict(value: Any) -> dict[str, Any]:
    """Return value as a typed dictionary, or an empty dictionary."""
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _inactive_hook_files(default: dict[str, Any]) -> list[str]:
    """Return hook scripts present in state but absent from both hook settings."""
    configured: set[str] = set()
    for key in ("post_upload_hooks", "post_upload_inprocess_hooks"):
        names = default.get(key, [])
        if isinstance(names, (list, tuple)):
            configured.update(Path(name.strip()).as_posix() for name in names if isinstance(name, str) and name.strip())
    try:
        return sorted(path.relative_to(HOOKS_DIR).as_posix() for path in HOOKS_DIR.rglob("*.py") if path.relative_to(HOOKS_DIR).as_posix() not in configured)
    except OSError:
        return []


def validate_config(config: Any, active_trackers: list[str] | None = None, active_imghost: str | None = None) -> tuple[bool, list[str], list[ConfigValidationWarning]]:
    """
    Validate the config dictionary structure and types.

    Args:
        config: The config object to validate
        active_trackers: List of tracker names that will be used (from meta.trackers)
                        If None, uses default_trackers from config
        active_imghost: The image host to use (from meta.imghost)
                       If None, uses img_host_1 from config

    Returns:
        Tuple of (is_valid, errors, warnings)
        - is_valid: True if config passes critical validation
        - errors: List of critical error messages
        - warnings: List of non-critical warnings
    """
    errors: list[str] = []
    warnings: list[ConfigValidationWarning] = []

    # Check if config is a dictionary
    if not isinstance(config, dict):
        errors.append(f"Config must be a dictionary, got {type(config).__name__}")
        return False, errors, warnings

    config_dict = cast(dict[str, Any], config)

    # Check required sections
    for section in REQUIRED_SECTIONS:
        if section not in config_dict:
            errors.append(f"Missing required config section: '{section}'")
        elif not isinstance(config_dict[section], dict):
            errors.append(f"Config section '{section}' must be a dictionary, got {type(config_dict[section]).__name__}")

    # If we have critical section errors, return early
    if errors:
        return False, errors, warnings

    # Validate DEFAULT section
    default_errors, default_warnings = _validate_default_section(_as_dict(config_dict.get("DEFAULT")))
    errors.extend(default_errors)
    warnings.extend(default_warnings)
    inactive_hooks = _inactive_hook_files(_as_dict(config_dict.get("DEFAULT")))
    if inactive_hooks:
        warnings.append(
            ConfigValidationWarning(
                f"Hook scripts are present but not enabled in post_upload_hooks or post_upload_inprocess_hooks: {', '.join(inactive_hooks)}",
                key="post_upload_hooks",
                section="DEFAULT",
            )
        )

    # Validate TRACKERS section
    # Determine which trackers are active
    trackers_section = _as_dict(config_dict.get("TRACKERS"))
    if active_trackers is None:
        # Fall back to default_trackers from config
        default_trackers_val = trackers_section.get("default_trackers", "")
        if isinstance(default_trackers_val, str) and default_trackers_val.strip():
            active_trackers = [t.strip().upper() for t in default_trackers_val.split(",") if t.strip()]
        elif isinstance(default_trackers_val, list):
            active_trackers = [t.strip().upper() for t in default_trackers_val if isinstance(t, str) and t.strip()]
        else:
            active_trackers = []

    tracker_errors, tracker_warnings = _validate_trackers_section(trackers_section, active_trackers)
    errors.extend(tracker_errors)
    warnings.extend(tracker_warnings)

    # Validate TORRENT_CLIENTS section if present
    if "TORRENT_CLIENTS" in config_dict:
        client_errors, client_warnings = _validate_torrent_clients_section(_as_dict(config_dict.get("TORRENT_CLIENTS")))
        errors.extend(client_errors)
        warnings.extend(client_warnings)

    # Determine if Usenet is active (either because USENET is a target tracker, a Usenet tracker class is active, or enabled in config)
    trackers_upper = [t.upper() for t in active_trackers] if active_trackers else []
    is_usenet_tracker_active = False
    try:
        from src.trackersetup import tracker_class_map

        for t in trackers_upper:
            tracker_class = tracker_class_map.get(t)
            if tracker_class and getattr(tracker_class, "is_usenet", False):
                is_usenet_tracker_active = True
                break
    except ImportError:
        if any(ut in trackers_upper for ut in ("CURUPIRA", "SUIO", "DRUNKENSLUG", "NZBGEEK")):
            is_usenet_tracker_active = True

    if "USENET" in config_dict:
        usenet_cfg = _as_dict(config_dict.get("USENET"))
        is_usenet_active = "USENET" in trackers_upper or is_usenet_tracker_active or usenet_cfg.get("enabled", False)
        usenet_errors, usenet_warnings = _validate_usenet_section(usenet_cfg, is_usenet_active)
        errors.extend(usenet_errors)
        warnings.extend(usenet_warnings)
    else:
        if "USENET" in trackers_upper or is_usenet_tracker_active:
            errors.append("Missing required config section: 'USENET' (required for Usenet uploads)")

    # Cross-reference validation for torrent client configuration
    default_section = _as_dict(config_dict.get("DEFAULT"))
    torrent_clients = _as_dict(config_dict.get("TORRENT_CLIENTS"))
    defined_clients = list(torrent_clients.keys())

    if default_section:
        default_client = default_section.get("default_torrent_client", "")

        # Validate injecting_client_list
        injecting_list = default_section.get("injecting_client_list")
        injecting_clients: list[str] = []
        if injecting_list is not None:
            if isinstance(injecting_list, str):
                # String is valid - gets converted to single-item list at runtime
                if injecting_list.strip():
                    injecting_clients = [injecting_list.strip()]
            elif isinstance(injecting_list, list):
                # List is valid - validate each item
                for i, item in enumerate(injecting_list):
                    if item and isinstance(item, str) and item.strip():
                        injecting_clients.append(item.strip())
                    elif item and not isinstance(item, str):
                        warnings.append(
                            ConfigValidationWarning(f"Item at index {i} should be a string, got {type(item).__name__}", key="injecting_client_list", section="DEFAULT")
                        )
            else:
                warnings.append(
                    ConfigValidationWarning(
                        f"Should be a list or string, got {type(injecting_list).__name__}. "
                        "Will fall back to default_torrent_client. "
                        "Example: ['Client1', 'Client2'] or 'Client1'",
                        key="injecting_client_list",
                        section="DEFAULT",
                    )
                )

        # Validate searching_client_list
        searching_list = default_section.get("searching_client_list")
        searching_clients: list[str] = []
        if searching_list is not None:
            if isinstance(searching_list, list):
                for i, item in enumerate(searching_list):
                    if item and isinstance(item, str) and item.strip():
                        searching_clients.append(item.strip())
                    elif item and not isinstance(item, str):
                        warnings.append(
                            ConfigValidationWarning(f"Item at index {i} should be a string, got {type(item).__name__}", key="searching_client_list", section="DEFAULT")
                        )
            else:
                warnings.append(
                    ConfigValidationWarning(
                        f"Should be a list, got {type(searching_list).__name__}. Will fall back to default_torrent_client. Example: ['Client1', 'Client2']",
                        key="searching_client_list",
                        section="DEFAULT",
                    )
                )

        # Check that referenced client names exist in TORRENT_CLIENTS
        if torrent_clients:
            warnings.extend(
                [
                    ConfigValidationWarning(f"References undefined client '{client_name}'", key="injecting_client_list", section="DEFAULT")
                    for client_name in injecting_clients
                    if client_name != "none" and client_name not in torrent_clients
                ]
            )

            warnings.extend(
                [
                    ConfigValidationWarning(f"References undefined client '{client_name}'", key="searching_client_list", section="DEFAULT")
                    for client_name in searching_clients
                    if client_name != "none" and client_name not in torrent_clients
                ]
            )

        # Check default_torrent_client - only required if no client lists are populated
        if default_client:
            if default_client not in torrent_clients:
                if defined_clients:
                    warnings.append(
                        ConfigValidationWarning(
                            f"References undefined client '{default_client}'. Defined clients: {', '.join(defined_clients)}", key="default_torrent_client", section="DEFAULT"
                        )
                    )
                else:
                    warnings.append(
                        ConfigValidationWarning(f"References '{default_client}' but no clients defined in TORRENT_CLIENTS", key="default_torrent_client", section="DEFAULT")
                    )
        elif not injecting_clients and not searching_clients and defined_clients:
            # Only warn if default_torrent_client is empty AND no client lists are configured
            warnings.append(
                ConfigValidationWarning(
                    "No default_torrent_client, injecting_client_list, or searching_client_list configured", key="default_torrent_client", section="DEFAULT"
                )
            )

    # Check for unknown top-level sections (warning only)
    known_sections = set(REQUIRED_SECTIONS + OPTIONAL_SECTIONS)
    warnings.extend(
        [ConfigValidationWarning(f"Unknown config section '{section}' - this may be intentional", section=section) for section in config_dict if section not in known_sections]
    )

    # Validate image host API keys
    default_section = _as_dict(config_dict.get("DEFAULT"))
    if default_section:
        # Determine which image hosts are active
        active_hosts: list[str] = []

        # If imghost specified from command line, use that
        if active_imghost and active_imghost.strip():
            active_hosts = [active_imghost.strip()]
        else:
            # Collect all configured img_host_* values
            for i in range(1, 10):
                host_key = f"img_host_{i}"
                host_value = default_section.get(host_key, "")
                if isinstance(host_value, str) and host_value.strip():
                    active_hosts.append(host_value.strip())

        # Check that each active host has its required API key
        for host in active_hosts:
            if host in IMAGE_HOST_API_KEYS:
                api_key_name = IMAGE_HOST_API_KEYS[host]
                api_key_value = default_section.get(api_key_name, "")
                if not api_key_value or (isinstance(api_key_value, str) and not api_key_value.strip()):
                    errors.append(f"Image host '{host}' requires API key '{api_key_name}' but it is not set")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def _validate_default_section(default: dict[str, Any]) -> tuple[list[str], list[ConfigValidationWarning]]:
    """Validate the DEFAULT config section."""
    errors: list[str] = []
    warnings: list[ConfigValidationWarning] = []

    # Check required keys
    for key, expected_type in REQUIRED_DEFAULT_KEYS.items():
        if key not in default:
            errors.append(f"Missing required key in DEFAULT section: '{key}'")
        elif not isinstance(default[key], expected_type):
            errors.append(f"DEFAULT['{key}'] must be {expected_type.__name__}, got {type(default[key]).__name__}")

    # Check tmdb_api is not empty (critical)
    tmdb_api = default.get("tmdb_api", "")
    if isinstance(tmdb_api, str) and not tmdb_api.strip():
        errors.append("DEFAULT['tmdb_api'] is empty - TMDB API key is required for operation")

    # Validate types for known keys (warnings only for type mismatches)
    for key, expected_types in DEFAULT_KEY_TYPES.items():
        if key in default and default[key] is not None:
            value = default[key]
            if not isinstance(value, expected_types):
                warnings.append(
                    ConfigValidationWarning(f"Expected type {' or '.join(t.__name__ for t in expected_types)}, got {type(value).__name__}", key=key, section="DEFAULT")
                )

    # Validate upload_order value if present
    upload_order = default.get("upload_order")
    if isinstance(upload_order, str):
        upload_order_lower = upload_order.strip().lower()
        if upload_order_lower not in {"concurrent", "usenet", "tracker"}:
            warnings.append(
                ConfigValidationWarning(
                    f"Invalid value '{upload_order}' for upload_order. Must be one of: 'concurrent', 'usenet', 'tracker'", key="upload_order", section="DEFAULT"
                )
            )

    if "embed_dupe_links" in default:
        warnings.append(
            ConfigValidationWarning(
                "Deprecated; rename to 'embed_links'.",
                key="embed_dupe_links",
                section="DEFAULT",
            )
        )

    # Validate image hosts
    for i in range(1, 10):
        host_key = f"img_host_{i}"
        if host_key in default:
            host_value = default[host_key]
            if isinstance(host_value, str) and host_value and host_value not in VALID_IMAGE_HOSTS:
                warnings.append(
                    ConfigValidationWarning(f"Unknown image host '{host_value}'. Valid hosts: {', '.join(h for h in VALID_IMAGE_HOSTS if h)}", key=host_key, section="DEFAULT")
                )

    # Validate numeric string values can be parsed
    numeric_keys = [
        "screens",
        "xxx_contact_sheet_rows",
        "xxx_contact_sheet_columns",
        "xxx_contact_sheet_max_videos",
        "xxx_contact_sheet_animation_seconds",
        "xxx_single_file_screens",
        "cutoff_screens",
        "max_menu_screens",
        "thumbnail_size",
        "process_limit",
        "threads",
        "multiScreens",
        "pack_thumb_size",
        "charLimit",
        "fileLimit",
        "processLimit",
        "tracker_pass_checks",
        "mkbrr_threads",
        "ffmpeg_compression",
        "dupe_size_difference_tolerance",
    ]
    for key in numeric_keys:
        if key in default:
            value = default[key]
            if isinstance(value, str):
                try:
                    (float if key == "xxx_contact_sheet_animation_seconds" else int)(value)
                except ValueError:
                    expected = "number" if key == "xxx_contact_sheet_animation_seconds" else "integer"
                    warnings.append(ConfigValidationWarning(f"Cannot parse '{value}' as {expected}", key=key, section="DEFAULT"))

    image_upload_concurrency = default.get("image_upload_concurrency")
    if image_upload_concurrency is not None:
        try:
            parsed_concurrency = int(image_upload_concurrency)
        except OverflowError, TypeError, ValueError:
            warnings.append(
                ConfigValidationWarning(
                    f"Cannot parse '{image_upload_concurrency}' as integer",
                    key="image_upload_concurrency",
                    section="DEFAULT",
                )
            )
        else:
            if parsed_concurrency < 0:
                warnings.append(
                    ConfigValidationWarning(
                        "Value must be >= 0",
                        key="image_upload_concurrency",
                        section="DEFAULT",
                    )
                )

    image_upload_delay = default.get("image_upload_delay")
    if image_upload_delay is not None:
        try:
            parsed_delay = float(image_upload_delay)
        except TypeError, ValueError:
            warnings.append(
                ConfigValidationWarning(
                    f"Cannot parse '{image_upload_delay}' as number",
                    key="image_upload_delay",
                    section="DEFAULT",
                )
            )
        else:
            if not math.isfinite(parsed_delay) or parsed_delay < 0:
                warnings.append(
                    ConfigValidationWarning(
                        "Value must be finite and >= 0",
                        key="image_upload_delay",
                        section="DEFAULT",
                    )
                )

    return errors, warnings


def _validate_trackers_section(trackers: dict[str, Any], active_trackers: list[str]) -> tuple[list[str], list[ConfigValidationWarning]]:
    """Validate the TRACKERS config section."""
    errors: list[str] = []
    warnings: list[ConfigValidationWarning] = []

    # Normalize active trackers to uppercase for comparison
    active_set = {t.upper() for t in active_trackers}

    # Check for default_trackers key
    if "default_trackers" not in trackers:
        warnings.append(ConfigValidationWarning("No 'default_trackers' defined - you'll need to specify trackers via command line", key="default_trackers", section="TRACKERS"))

    if "DRUNKENSLUG" in active_set and "DRUNKENSLUG" not in [t.upper() for t in trackers]:
        errors.append("Missing config section for active tracker: 'DRUNKENSLUG' under 'TRACKERS'")

    # Validate individual tracker configs
    for tracker_name, tracker_config in trackers.items():
        if tracker_name == "default_trackers":
            continue

        is_active = tracker_name.upper() in active_set

        if not isinstance(tracker_config, dict):
            warnings.append(ConfigValidationWarning(f"Tracker config must be a dictionary, got {type(tracker_config).__name__}", key=tracker_name, section="TRACKERS"))
            continue
        tracker_config_dict = cast(dict[str, Any], tracker_config)

        # Check for common tracker config issues
        if "api_key" in tracker_config_dict:
            api_key = tracker_config_dict["api_key"]
            if isinstance(api_key, str) and api_key and not api_key.strip():
                warnings.append(ConfigValidationWarning("api_key is whitespace-only", key=tracker_name, section="TRACKERS"))

        # Only check announce_url placeholders for active trackers
        if is_active and "announce_url" in tracker_config_dict:
            announce = tracker_config_dict["announce_url"]
            if isinstance(announce, str) and announce and "<" in announce and ">" in announce:
                # This is an error for active trackers, not just a warning
                errors.append(f"[TRACKERS][{tracker_name}] announce_url contains placeholder (e.g., <PASSKEY>) - replace with actual value")

        # Check boolean fields are actually booleans (must be real bool, not string)
        bool_fields = [
            "anon",
            "useAPI",
            "use_for_search",
            "modq",
            "draft",
            "draft_default",
            "img_rehost",
            "allow_ext_subtitles",
            "resolve_language",
            "featured",
            "doubleup",
            "double_upload",
            "double_up",
            "refundable",
            "sticky",
            "exclusive",
            "exact_match_only",
        ]
        for field in bool_fields:
            if field in tracker_config_dict:
                value = tracker_config_dict[field]
                if not isinstance(value, bool):
                    warnings.append(
                        ConfigValidationWarning(f"'{field}' must be a boolean type (True/False), got {type(value).__name__}: {value!r}", key=tracker_name, section="TRACKERS")
                    )

        # Check integer fields
        int_fields = [
            "freeleech_until",
            "double_upload_until",
        ]
        for field in int_fields:
            if field in tracker_config_dict:
                value = tracker_config_dict[field]
                if isinstance(value, bool) or not isinstance(value, int):
                    try:
                        int_val = int(str(value))
                        if int_val < 0:
                            warnings.append(ConfigValidationWarning(f"'{field}' must be a non-negative integer, got {value!r}", key=tracker_name, section="TRACKERS"))
                    except ValueError, TypeError:
                        warnings.append(ConfigValidationWarning(f"'{field}' must be an integer, got {type(value).__name__}: {value!r}", key=tracker_name, section="TRACKERS"))
                elif isinstance(value, int) and value < 0:
                    warnings.append(ConfigValidationWarning(f"'{field}' must be a non-negative integer, got {value!r}", key=tracker_name, section="TRACKERS"))

    return errors, warnings


def _validate_torrent_clients_section(clients: dict[str, Any]) -> tuple[list[str], list[ConfigValidationWarning]]:
    """Validate the TORRENT_CLIENTS config section."""
    errors: list[str] = []
    warnings: list[ConfigValidationWarning] = []

    for client_name, client_config in clients.items():
        if not isinstance(client_config, dict):
            warnings.append(ConfigValidationWarning(f"Client config must be a dictionary, got {type(client_config).__name__}", key=client_name, section="TORRENT_CLIENTS"))
            continue
        client_config_dict = cast(dict[str, Any], client_config)

        # Check torrent_client type is valid
        client_type = client_config_dict.get("torrent_client", "")
        if client_type and client_type not in VALID_TORRENT_CLIENTS:
            warnings.append(ConfigValidationWarning(f"Unknown torrent_client type '{client_type}'", key=client_name, section="TORRENT_CLIENTS"))

        # Validate linking option
        linking = client_config_dict.get("linking", "")
        if linking and linking not in ("symlink", "hardlink", ""):
            warnings.append(
                ConfigValidationWarning(f"Invalid linking option '{linking}'. Use 'symlink', 'hardlink', or empty string", key=client_name, section="TORRENT_CLIENTS")
            )

        # Check path mappings have matching lengths
        local_paths = client_config_dict.get("local_path", [])
        remote_paths = client_config_dict.get("remote_path", [])
        if isinstance(local_paths, list) and isinstance(remote_paths, list):
            local_paths_list = local_paths
            remote_paths_list = remote_paths
            if len(local_paths_list) != len(remote_paths_list) and local_paths_list and remote_paths_list:
                warnings.append(
                    ConfigValidationWarning(
                        f"local_path ({len(local_paths_list)} items) and remote_path ({len(remote_paths_list)} items) should have matching lengths",
                        key=client_name,
                        section="TORRENT_CLIENTS",
                    )
                )

    return errors, warnings


def _validate_usenet_section(usenet: dict[str, Any], is_usenet_active: bool = False) -> tuple[list[str], list[ConfigValidationWarning]]:
    """Validate the USENET config section."""
    errors: list[str] = []
    warnings: list[ConfigValidationWarning] = []

    # Check required fields for Usenet upload
    if is_usenet_active:
        for key in USENET_REQUIRED_KEYS:
            val = usenet.get(key)
            if not val or (isinstance(val, str) and not val.strip()):
                errors.append(f"[USENET] is active but '{key}' is empty or not configured")

    # Validate types of known keys
    for key, expected_types in USENET_KEY_TYPES.items():
        if key in usenet and usenet[key] is not None:
            value = usenet[key]
            if not isinstance(value, expected_types):
                warnings.append(
                    ConfigValidationWarning(f"Expected type {' or '.join(t.__name__ for t in expected_types)}, got {type(value).__name__}", key=key, section="USENET")
                )

    # Validate numeric string values
    for key in USENET_NUMERIC_STRING_KEYS:
        if key in usenet:
            value = usenet[key]
            if isinstance(value, str) and value.strip():
                try:
                    int(value)
                except ValueError:
                    warnings.append(ConfigValidationWarning(f"Cannot parse '{value}' as integer", key=key, section="USENET"))

    return errors, warnings


def group_warnings(warnings: list[ConfigValidationWarning]) -> list[str]:
    """
    Group warnings with the same section and message, combining keys.

    For example, multiple trackers with the same warning become:
    [TRACKERS][BLUTOPIA, HDBITS] api_key is whitespace-only
    """
    from collections import defaultdict

    # Group by (section, message) -> list of keys
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)

    for warning in warnings:
        group_key = (warning.section, warning.message)
        if warning.key:
            grouped[group_key].append(warning.key)
        else:
            # Warnings without keys get their own entry
            grouped[group_key].append("")

    result: list[str] = []
    for (section, message), keys in grouped.items():
        # Filter out empty keys and deduplicate
        non_empty_keys = [k for k in keys if k]

        if section:
            if non_empty_keys:
                # Multiple keys with same message - combine them
                keys_str = ", ".join(non_empty_keys)
                result.append(f"[{section}][{keys_str}] {message}")
            else:
                result.append(f"[{section}] {message}")
        elif non_empty_keys:
            keys_str = ", ".join(non_empty_keys)
            result.append(f"[{keys_str}] {message}")
        else:
            result.append(message)

    return result


def format_validation_results(is_valid: bool, errors: list[str], warnings: list[ConfigValidationWarning], show_warnings: bool = True) -> str:
    """Format validation results for display."""
    lines: list[str] = []

    if errors:
        lines.append("Config Validation Errors:")
        lines.extend([f"  ✗ {error}" for error in errors])

    if show_warnings and warnings:
        if lines:
            lines.append("")
        lines.append("Config Validation Warnings:")
        grouped = group_warnings(warnings)
        lines.extend([f"  ⚠ {warning_str}" for warning_str in grouped])

    if is_valid and not warnings:
        lines.append("Config validation passed.")
    elif is_valid:
        lines.append(f"\nConfig validation passed with {len(warnings)} warning(s).")

    return "\n".join(lines)
