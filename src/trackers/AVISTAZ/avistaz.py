# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.AVISTAZ import AZTrackerBase
from src.trackers.common import Common


class AvistaZ(AZTrackerBase):
    """
    AZ Private Torrent Tracker
    """

    tracker = "AVISTAZ"
    display_name = "AvistaZ"
    source_flag = "AvistaZ"
    banned_groups = ("",)
    base_url = "https://avistaz.to"
    torrent_url = f"{base_url}/torrent/"
    requests_url = f"{base_url}/requests"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("tracker.avistaz.to",)

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name="AVISTAZ")
        self.config = config
        self.common = Common(config)

    def rules(self, meta: Meta) -> str:
        warnings: list[str] = []

        is_disc = False
        if meta.is_disc:
            is_disc = True

        video_codec = meta.video_codec
        if video_codec:
            video_codec = video_codec.strip().lower()

        video_encode = meta.video_encode
        if video_encode:
            video_encode = video_encode.strip().lower()

        type = meta.type
        if type:
            type = type.strip().lower()

        source = meta.source
        if source:
            source = source.strip().lower()

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
        asia = [
            "AE",
            "AF",
            "AM",
            "AZ",
            "BD",
            "BH",
            "BN",
            "BT",
            "CN",
            "CY",
            "GE",
            "HK",
            "ID",
            "IL",
            "IN",
            "IQ",
            "IR",
            "JO",
            "JP",
            "KG",
            "KH",
            "KP",
            "KR",
            "KW",
            "KZ",
            "LA",
            "LB",
            "LK",
            "MM",
            "MN",
            "MO",
            "MV",
            "MY",
            "NP",
            "OM",
            "PH",
            "PK",
            "PS",
            "QA",
            "SA",
            "SG",
            "SY",
            "TH",
            "TJ",
            "TL",
            "TM",
            "TR",
            "TW",
            "UZ",
            "VN",
            "YE",
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
        oceania = [
            "AS",
            "AU",
            "CC",
            "CK",
            "CX",
            "FJ",
            "FM",
            "GU",
            "HM",
            "KI",
            "MH",
            "MP",
            "NC",
            "NF",
            "NR",
            "NU",
            "NZ",
            "PF",
            "PG",
            "PN",
            "PW",
            "SB",
            "TK",
            "TO",
            "TV",
            "UM",
            "VU",
            "WF",
            "WS",
        ]

        az_allowed_countries = [
            "BD",
            "BN",
            "BT",
            "CN",
            "HK",
            "ID",
            "IN",
            "JP",
            "KH",
            "KP",
            "KR",
            "LA",
            "LK",
            "MM",
            "MN",
            "MO",
            "MY",
            "NP",
            "PH",
            "PK",
            "SG",
            "TH",
            "TL",
            "TW",
            "VN",
        ]

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

        all_countries = africa + america + asia + europe + oceania
        cinemaz_countries = list(set(all_countries) - set(phd_countries) - set(az_allowed_countries))

        origin_countries_codes = meta.origin_country

        if any(code in phd_countries for code in origin_countries_codes):
            warnings.append("DO NOT upload content from major English speaking countries (USA, UK, Canada, etc). Upload this to our sister site PRIVATEHD.to instead.")

        elif any(code in cinemaz_countries for code in origin_countries_codes):
            warnings.append("DO NOT upload non-allowed Asian or Western content. Upload this content to our sister site CINEMAZ.to instead.")

        if not is_disc and meta.container not in ["mkv", "mp4", "avi"]:
            warnings.append("Allowed containers: MKV, MP4, AVI.")

        if not is_disc and video_codec not in ("avc", "h.264", "h.265", "x264", "x265", "hevc", "divx", "xvid"):
            warnings.append(
                f"Video codec not allowed in your upload: {video_codec}.\n"
                "Allowed: H264/x264/AVC, H265/x265/HEVC, DivX/Xvid\n"
                "Exceptions:\n"
                "    MPEG2 for Full DVD discs and HDTV recordings\n"
                "    VC-1/MPEG2 for Bluray only if that's what is on the disc"
            )

        if is_disc:
            pass
        else:
            allowed_keywords = ["AC3", "Audio Layer III", "MP3", "Dolby Digital", "Dolby TrueHD", "DTS", "DTS-HD", "FLAC", "AAC", "Dolby"]

            is_untouched_opus = False
            audio_field = meta.audio
            if isinstance(audio_field, str) and "opus" in audio_field.lower() and meta.untouched:
                is_untouched_opus = True

            audio_tracks: list[dict[str, Any]] = []
            media_tracks = meta.mediainfo.get("media", {}).get("track", [])
            for track in media_tracks:
                if track.get("@type") == "Audio":
                    codec_info = track.get("Format_Commercial_IfAny") or track.get("Format")
                    codec = codec_info if isinstance(codec_info, str) else ""
                    audio_tracks.append({"codec": codec, "language": track.get("Language", "")})

            invalid_codecs: list[str] = []
            for track in audio_tracks:
                codec = track["codec"]
                if not codec:
                    continue

                if "opus" in codec.lower():
                    if is_untouched_opus:
                        continue
                    invalid_codecs.append(codec)
                    continue

                is_allowed = any(kw.lower() in codec.lower() for kw in allowed_keywords)
                if not is_allowed:
                    invalid_codecs.append(codec)

            if invalid_codecs:
                unique_invalid_codecs = sorted(set(invalid_codecs))
                warnings.append(
                    f"Unallowed audio codec(s) detected: {', '.join(unique_invalid_codecs)}\n"
                    f"Allowed codecs: AC3 (Dolby Digital), Dolby TrueHD, DTS, DTS-HD (MA), FLAC, AAC, MP3, etc.\n"
                    f"Exceptions: Untouched Opus from source; Uncompressed codecs from Blu-ray discs (PCM, LPCM)."
                )

        if warnings:
            return "\n\n".join(filter(None, warnings))

        return ""
