# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from datetime import UTC, datetime
from typing import Any

from src.meta import Meta
from src.trackers.AVISTAZ import AZTrackerBase
from src.trackers.common import Common


class CinemaZ(AZTrackerBase):
    """
    CZ Private Torrent Tracker
    """

    tracker = "CINEMAZ"
    display_name = "CinemaZ"
    allows_bloated_audio = True
    source_flag = "CinemaZ"
    banned_groups = ("",)
    base_url = "https://cinemaz.to"
    torrent_url = f"{base_url}/torrent/"
    requests_url = f"{base_url}/requests"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("tracker.cinemaz.to",)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name="CINEMAZ")
        self.config = config
        self.common = Common(config)

    def rules(self, meta: Meta) -> str:
        warnings: list[str] = []
        is_disc = bool(meta.is_disc)
        release_type = str(meta.type or "").strip().lower()
        video_codec = str(meta.video_codec or "").strip().lower()
        video_encode = str(meta.video_encode or "").strip().lower()
        container = str(meta.container or "").strip().lower().lstrip(".")
        resolution_value = str(meta.resolution or "").lower()
        resolution_match = re.search(r"(\d{3,4})", resolution_value)
        resolution = int(resolution_match.group(1)) if resolution_match else 0
        video_width = int(meta.video_width or 0)

        # This also checks the rule 'FANRES content is not allowed'
        if meta.category not in ("MOVIE", "TV"):
            warnings.append("The only allowed content to be uploaded are Movies and TV Shows.\nAnything else, like games, music, software and porn is not allowed!")

        if meta.anime:
            warnings.append("Upload Anime content to our sister site AnimeTorrents.me instead. If it's on AniDB, it's an anime.")

        # https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes

        africa = [
            "AO",
            "BF",
            "BI",
            "BJ",
            "BW",
            "CD",
            "CF",
            "CG",
            "CI",
            "CM",
            "CV",
            "DJ",
            "DZ",
            "EG",
            "EH",
            "ER",
            "ET",
            "GA",
            "GH",
            "GM",
            "GN",
            "GQ",
            "GW",
            "IO",
            "KE",
            "KM",
            "LR",
            "LS",
            "LY",
            "MA",
            "MG",
            "ML",
            "MR",
            "MU",
            "MW",
            "MZ",
            "NA",
            "NE",
            "NG",
            "RE",
            "RW",
            "SC",
            "SD",
            "SH",
            "SL",
            "SN",
            "SO",
            "SS",
            "ST",
            "SZ",
            "TD",
            "TF",
            "TG",
            "TN",
            "TZ",
            "UG",
            "YT",
            "ZA",
            "ZM",
            "ZW",
        ]

        america = [
            "AG",
            "AI",
            "AR",
            "AW",
            "BB",
            "BL",
            "BM",
            "BO",
            "BQ",
            "BR",
            "BS",
            "BV",
            "BZ",
            "CA",
            "CL",
            "CO",
            "CR",
            "CU",
            "CW",
            "DM",
            "DO",
            "EC",
            "FK",
            "GD",
            "GF",
            "GL",
            "GP",
            "GS",
            "GT",
            "GY",
            "HN",
            "HT",
            "JM",
            "KN",
            "KY",
            "LC",
            "MF",
            "MQ",
            "MS",
            "MX",
            "NI",
            "PA",
            "PE",
            "PM",
            "PR",
            "PY",
            "SR",
            "SV",
            "SX",
            "TC",
            "TT",
            "US",
            "UY",
            "VC",
            "VE",
            "VG",
            "VI",
        ]

        europe = [
            "AD",
            "AL",
            "AT",
            "AX",
            "BA",
            "BE",
            "BG",
            "BY",
            "CH",
            "CZ",
            "DE",
            "DK",
            "EE",
            "ES",
            "FI",
            "FO",
            "FR",
            "GB",
            "GG",
            "GI",
            "GR",
            "HR",
            "HU",
            "IE",
            "IM",
            "IS",
            "IT",
            "JE",
            "LI",
            "LT",
            "LU",
            "LV",
            "MC",
            "MD",
            "ME",
            "MK",
            "MT",
            "NL",
            "NO",
            "PL",
            "PT",
            "RO",
            "RS",
            "RU",
            "SE",
            "SI",
            "SJ",
            "SK",
            "SM",
            "SU",
            "UA",
            "VA",
            "XC",
        ]

        # Countries that belong on PRIVATEHD (unless they are old)
        phd_countries = [
            "AG",
            "AI",
            "AU",
            "BB",
            "BM",
            "BS",
            "BZ",
            "CA",
            "CW",
            "DM",
            "GB",
            "GD",
            "IE",
            "JM",
            "KN",
            "KY",
            "LC",
            "MS",
            "NZ",
            "PR",
            "TC",
            "TT",
            "US",
            "VC",
            "VG",
            "VI",
        ]

        # Countries that belong on AVISTAZ
        az_countries = ["BD", "BN", "BT", "CN", "HK", "ID", "IN", "JP", "KH", "KP", "KR", "LA", "LK", "MM", "MN", "MO", "MY", "NP", "PH", "PK", "SG", "TH", "TL", "TW", "VN"]

        # Countries normally allowed on CINEMAZ
        set_phd = set(phd_countries)
        set_europe = set(europe)
        set_america = set(america)
        middle_east = ["AE", "BH", "CY", "EG", "IR", "IQ", "IL", "JO", "KW", "LB", "OM", "PS", "QA", "SA", "SY", "TR", "YE"]

        # Combine all allowed regions for CINEMAZ
        cz_allowed_countries = list(
            (set_europe - {"GB", "IE"})  # Europe excluding UK and Ireland
            | (set_america - set_phd)  # All of America excluding the PHD countries
            | set(africa)  # All of Africa
            | set(middle_east)  # Middle East countries
            | {"RU"}  # Russia
        )

        origin_countries_codes = meta.origin_country
        try:
            year = int(meta.year)
        except (TypeError, ValueError):
            year = 0
        is_older_than_50_years = False

        if year:
            current_year = datetime.now(UTC).year
            if (current_year - year) >= 50:
                is_older_than_50_years = True

        is_sd = bool(meta.sd) or (resolution and resolution < 720)

        # Case 1: The content is from a major English-speaking country
        if any(code in phd_countries for code in origin_countries_codes):
            if is_older_than_50_years or is_sd:
                # Older and SD English-language content are allowed on CinemaZ.
                pass
            else:
                # It's new, so redirect to PRIVATEHD
                warnings.append("DO NOT upload recent mainstream English content. Upload this to our sister site PRIVATEHD.to instead.")

        # Case 2: The content is Asian, redirect to AVISTAZ
        elif any(code in az_countries for code in origin_countries_codes):
            warnings.append("DO NOT upload Asian content. Upload this to our sister site AVISTAZ.to instead.")

        # Case 3: The content is from one of the normally allowed CINEMAZ regions
        elif any(code in cz_allowed_countries for code in origin_countries_codes):
            # It's from a valid region, so it's ALLOWED on CINEMAZ
            pass

        # Case 4: Fallback for any other case (e.g., country not in any list)
        else:
            warnings.append(
                "This content is not allowed. CINEMAZ accepts content from Europe (excluding UK/IE), "
                "Africa, the Middle East, Russia, and the Americas (excluding recent mainstream English content)."
            )

        allowed_containers = {"mkv", "mp4", "avi"}
        if release_type == "hdtv":
            allowed_containers.update({"ts", "tp"})
        if not is_disc and container not in allowed_containers:
            allowed = ", ".join(sorted(allowed_containers)).upper()
            warnings.append(f"Container not allowed for this rip type: {container or 'unknown'}. Allowed: {allowed}.")

        allowed_video_codecs = {"avc", "h.264", "h.265", "x264", "x265", "hevc", "vp9", "divx", "xvid"}
        is_hdtv_mpeg2 = release_type == "hdtv" and video_codec in {"mpeg-2", "mpeg2"}
        if not is_disc and video_codec not in allowed_video_codecs and not is_hdtv_mpeg2:
            warnings.append("Video codec not allowed. CinemaZ allows H.264/x264/AVC, H.265/x265/HEVC, VP9, DivX/XviD, and MPEG-2 for HDTV recordings.")

        if not is_disc and video_width and video_width < 600:
            warnings.append(f"Video width is {video_width}px; CinemaZ requires a minimum width of 600px.")
        if video_codec in {"divx", "xvid"} and (resolution >= 720 or video_width >= 720):
            warnings.append("DivX/XviD is not allowed for HD video (720p and above).")

        conditional_rip_types = {"webrip", "vodrip", "vhsrip", "vcdrip", "vcd"}
        if release_type in conditional_rip_types:
            warnings.append(f"{release_type.upper()} is allowed only when the video is unavailable in a preferred CinemaZ rip type; verify this manually before uploading.")
        if "hybrid" in str(meta.edition or "").lower() or bool(meta.webdv):
            warnings.append("HYBRID releases require substantially improved, perfectly synchronized audio or video streams; verify this manually before uploading.")

        bitrate_thresholds = {
            "x264": {"sd": 1000, 720: 1500, 1080: 3000, 2160: 12000},
            "x265": {720: 1000, 1080: 2000, 2160: 8000},
        }
        codec_family = "x265" if any(codec in f"{video_codec} {video_encode}" for codec in ("x265", "h.265", "hevc")) else "x264"
        video_bitrate = int(meta.video_bitrate or 0)
        resolution_key: str | int = "sd" if is_sd else resolution
        required_bitrate = bitrate_thresholds[codec_family].get(resolution_key)
        if not is_disc and codec_family == "x265" and is_sd:
            warnings.append("x265/HEVC is not allowed for SD content.")
        elif not is_disc and video_bitrate and required_bitrate and video_bitrate < required_bitrate:
            warnings.append(f"Video bitrate is {video_bitrate} kbit/s; CinemaZ requires at least {required_bitrate} kbit/s for this codec and resolution.")

        audio_tracks: list[dict[str, str]] = []
        for track in meta.mediainfo.get("media", {}).get("track", []):
            if track.get("@type") == "Audio":
                codec_info = track.get("Format_Commercial_IfAny") or track.get("Format")
                codec = codec_info if isinstance(codec_info, str) else ""
                audio_tracks.append({"codec": codec, "bitrate": str(track.get("BitRate", "") or "")})

        if not is_disc:
            allowed_audio_keywords = ["AC3", "E-AC3", "E-AC-3", "Audio Layer III", "MP3", "Dolby Digital", "Dolby TrueHD", "DTS", "DTS-HD", "FLAC", "AAC", "Dolby"]
            invalid_codecs = sorted(
                {track["codec"] for track in audio_tracks if track["codec"] and not any(keyword.lower() in track["codec"].lower() for keyword in allowed_audio_keywords)}
            )
            if invalid_codecs:
                warnings.append(f"Unallowed audio codec(s) detected: {', '.join(invalid_codecs)}.")

        audio_bitrate = int(meta.audio_bitrate or 0)
        if not is_disc and audio_bitrate and audio_bitrate < 128:
            warnings.append(f"Audio bitrate is {audio_bitrate} kbit/s; CinemaZ requires at least 128 kbit/s.")

        if warnings:
            return "\n\n".join(filter(None, warnings))

        return ""

    def check_data(self, meta: Meta, data: dict[str, Any]):
        issue = super().check_data(meta, data)
        if issue or meta.debug:
            return issue

        minimum_screenshots = 6 if meta.is_disc == "BDMV" or meta.type == "REMUX" or meta.resolution == "2160p" else 3
        if len(data["screenshots[]"]) < minimum_screenshots:
            return f"UPLOAD FAILED: CinemaZ requires at least {minimum_screenshots} screenshots for this upload."

        return False
