import asyncio
import os
import re
import secrets
import shutil
import urllib.parse
from html.entities import codepoint2name
from typing import Any

import httpx
from bs4 import BeautifulSoup
from torf import Torrent

from src.console import console
from src.meta import Meta
from src.trackers.COMMON import COMMON

Config = dict[str, Any]

# country code mapping: ISO 3166-1 alpha-2 -> pt-br
COUNTRY_PTBR: dict[str, str] = {
    "AD": "Andorra",
    "AE": "Emirados Árabes Unidos",
    "AF": "Afeganistão",
    "SU": "União Soviética",
    "AG": "Antígua e Barbuda",
    "AL": "Albânia",
    "AM": "Armênia",
    "AO": "Angola",
    "AR": "Argentina",
    "AT": "Áustria",
    "AU": "Austrália",
    "AZ": "Azerbaijão",
    "BA": "Bósnia e Herzegovina",
    "XC": "Checoslováquia",
    "BB": "Barbados",
    "BD": "Bangladesh",
    "BE": "Bélgica",
    "BF": "Burkina Faso",
    "BG": "Bulgária",
    "BH": "Bahrain",
    "BI": "Burundi",
    "BJ": "Benin",
    "BN": "Brunei",
    "BO": "Bolívia",
    "BR": "Brasil",
    "BS": "Bahamas",
    "BT": "Butão",
    "BW": "Botsuana",
    "BY": "Bielorrússia",
    "BZ": "Belize",
    "CA": "Canadá",
    "CD": "República Democrática do Congo",
    "CF": "República Centro-Africana",
    "CG": "República do Congo",
    "CH": "Suíça",
    "CI": "Costa do Marfim",
    "CL": "Chile",
    "CM": "Camarões",
    "CN": "China",
    "CO": "Colômbia",
    "CR": "Costa Rica",
    "CU": "Cuba",
    "CV": "Cabo Verde",
    "CY": "Chipre",
    "CZ": "República Tcheca",
    "DE": "Alemanha",
    "DJ": "Djibuti",
    "DK": "Dinamarca",
    "DM": "Dominica",
    "DO": "República Dominicana",
    "DZ": "Argélia",
    "EC": "Equador",
    "EE": "Estônia",
    "EG": "Egito",
    "ER": "Eritreia",
    "ES": "Espanha",
    "ET": "Etiópia",
    "FI": "Finlândia",
    "FJ": "Fiji",
    "FR": "França",
    "GA": "Gabão",
    "GB": "Reino Unido",
    "GD": "Granada",
    "GE": "Geórgia",
    "GH": "Gana",
    "GM": "Gâmbia",
    "GN": "Guiné",
    "GQ": "Guiné Equatorial",
    "GR": "Grécia",
    "GT": "Guatemala",
    "GW": "Guiné-Bissau",
    "GY": "Guiana",
    "HN": "Honduras",
    "HR": "Croácia",
    "HT": "Haiti",
    "HU": "Hungria",
    "ID": "Indonésia",
    "IE": "Irlanda",
    "IL": "Israel",
    "IN": "Índia",
    "IQ": "Iraque",
    "IR": "Irã",
    "IS": "Islândia",
    "IT": "Itália",
    "JM": "Jamaica",
    "JO": "Jordânia",
    "JP": "Japão",
    "KE": "Quênia",
    "KG": "Quirguistão",
    "KH": "Camboja",
    "KI": "Kiribati",
    "KM": "Comores",
    "KN": "São Cristóvão e Nevis",
    "KP": "Coreia do Norte",
    "KR": "Coreia do Sul",
    "KW": "Kuwait",
    "KZ": "Cazaquistão",
    "LA": "Laos",
    "LB": "Líbano",
    "LC": "Santa Lúcia",
    "LI": "Liechtenstein",
    "LK": "Sri Lanka",
    "LR": "Libéria",
    "LS": "Lesoto",
    "LT": "Lituânia",
    "LU": "Luxemburgo",
    "LV": "Letônia",
    "LY": "Líbia",
    "MA": "Marrocos",
    "MC": "Mônaco",
    "MD": "Moldávia",
    "ME": "Montenegro",
    "MG": "Madagascar",
    "MH": "Ilhas Marshall",
    "MK": "Macedônia do Norte",
    "ML": "Mali",
    "MM": "Myanmar",
    "MN": "Mongólia",
    "MR": "Mauritânia",
    "MT": "Malta",
    "MU": "Maurício",
    "MV": "Maldivas",
    "MW": "Malaui",
    "MX": "México",
    "MY": "Malásia",
    "MZ": "Moçambique",
    "NA": "Namíbia",
    "NE": "Níger",
    "NG": "Nigéria",
    "NI": "Nicarágua",
    "NL": "Países Baixos",
    "NO": "Noruega",
    "NP": "Nepal",
    "NR": "Nauru",
    "NZ": "Nova Zelândia",
    "OM": "Omã",
    "PA": "Panamá",
    "PE": "Peru",
    "PG": "Papua Nova Guiné",
    "PH": "Filipinas",
    "PK": "Paquistão",
    "PL": "Polônia",
    "PT": "Portugal",
    "PW": "Palau",
    "PY": "Paraguai",
    "QA": "Catar",
    "RO": "Romênia",
    "RS": "Sérvia",
    "RU": "Rússia",
    "RW": "Ruanda",
    "SA": "Arábia Saudita",
    "SB": "Ilhas Salomão",
    "SC": "Seicheles",
    "SD": "Sudão",
    "SE": "Suécia",
    "SG": "Singapura",
    "SI": "Eslovênia",
    "SK": "Eslováquia",
    "SL": "Serra Leoa",
    "SM": "San Marino",
    "SN": "Senegal",
    "SO": "Somália",
    "SR": "Suriname",
    "SS": "Sudão do Sul",
    "ST": "São Tomé e Príncipe",
    "SV": "El Salvador",
    "SY": "Síria",
    "SZ": "Essuatíni",
    "TD": "Chade",
    "TG": "Togo",
    "TH": "Tailândia",
    "TJ": "Tajiquistão",
    "TL": "Timor-Leste",
    "TM": "Turcomenistão",
    "TN": "Tunísia",
    "TO": "Tonga",
    "TR": "Turquia",
    "TT": "Trinidad e Tobago",
    "TV": "Tuvalu",
    "TZ": "Tanzânia",
    "UA": "Ucrânia",
    "UG": "Uganda",
    "US": "Estados Unidos",
    "UY": "Uruguai",
    "UZ": "Uzbequistão",
    "VA": "Vaticano",
    "VC": "São Vicente e Granadinas",
    "VE": "Venezuela",
    "VN": "Vietnã",
    "VU": "Vanuatu",
    "WS": "Samoa",
    "YE": "Iêmen",
    "ZA": "África do Sul",
    "ZM": "Zâmbia",
    "ZW": "Zimbábue",
}

# genre mapping: tmdb en -> pt-br
GENRE_PTBR: dict[str, str] = {
    "Action": "Ação",
    "Adventure": "Aventura",
    "Animation": "Animação",
    "Comedy": "Comédia",
    "Crime": "Crime",
    "Documentary": "Documentário",
    "Drama": "Drama",
    "Family": "Família",
    "Fantasy": "Fantasia",
    "History": "História",
    "Horror": "Terror",
    "Music": "Música",
    "Mystery": "Mistério",
    "Romance": "Romance",
    "Science Fiction": "Ficção Científica",
    "TV Movie": "Telefilme",
    "Thriller": "Thriller",
    "War": "Guerra",
    "Western": "Faroeste",
}

# video quality mapping: UA type -> forum label
VIDEO_QUALITY_PTBR: dict[str, str] = {
    "WEBDL": "WEB-DL",
    "WEBRIP": "WEB-Rip",
    "BLURAY": "BluRay",
    "REMUX": "BluRay Remux",
    "ENCODE": "BluRay",
    "DISC": "Blu-Ray Full",
    "DVDRIP": "DVDRip",
    "HDTV": "HDTV",
    "CAM": "CAM",
}

# subforum mapping: country code -> forum id
FORUM_ID_BY_COUNTRY: dict[str, int] = {
    # Africa
    "DZ": 461,
    "AO": 461,
    "BJ": 461,
    "BW": 461,
    "BF": 461,
    "BI": 461,
    "CM": 461,
    "CV": 461,
    "CF": 461,
    "TD": 461,
    "KM": 461,
    "CD": 461,
    "CG": 461,
    "CI": 461,
    "DJ": 461,
    "EG": 461,
    "GQ": 461,
    "ER": 461,
    "ET": 461,
    "GA": 461,
    "GM": 461,
    "GH": 461,
    "GN": 461,
    "GW": 461,
    "KE": 461,
    "LS": 461,
    "LR": 461,
    "LY": 461,
    "MG": 461,
    "MW": 461,
    "ML": 461,
    "MR": 461,
    "MU": 461,
    "MA": 461,
    "MZ": 461,
    "NA": 461,
    "NE": 461,
    "NG": 461,
    "RW": 461,
    "ST": 461,
    "SN": 461,
    "SC": 461,
    "SL": 461,
    "SO": 461,
    "ZA": 461,
    "SS": 461,
    "SD": 461,
    "SZ": 461,
    "TZ": 461,
    "TG": 461,
    "TN": 461,
    "UG": 461,
    "ZM": 461,
    "ZW": 461,
    # Asia
    "AF": 24,
    "AM": 24,
    "AZ": 24,
    "BD": 24,
    "BT": 24,
    "BN": 24,
    "KH": 24,
    "CN": 24,
    "GE": 24,
    "IN": 24,
    "ID": 24,
    "JP": 24,
    "KZ": 24,
    "KG": 24,
    "LA": 24,
    "MY": 24,
    "MV": 24,
    "MN": 24,
    "MM": 24,
    "NP": 24,
    "KP": 24,
    "KR": 24,
    "PK": 24,
    "PH": 24,
    "SG": 24,
    "LK": 24,
    "TW": 24,
    "TJ": 24,
    "TH": 24,
    "TL": 24,
    "TM": 24,
    "UZ": 24,
    "VN": 24,
    # Europa
    "AL": 25,
    "XC": 25,
    "AD": 25,
    "AT": 25,
    "BY": 25,
    "BE": 25,
    "BA": 25,
    "BG": 25,
    "HR": 25,
    "SU": 25,
    "CY": 25,
    "CZ": 25,
    "DK": 25,
    "EE": 25,
    "FI": 25,
    "FR": 25,
    "DE": 25,
    "GR": 25,
    "HU": 25,
    "IS": 25,
    "IE": 25,
    "IT": 25,
    "XK": 25,
    "LV": 25,
    "LI": 25,
    "LT": 25,
    "LU": 25,
    "MT": 25,
    "MD": 25,
    "MC": 25,
    "ME": 25,
    "MK": 25,
    "NL": 25,
    "NO": 25,
    "PL": 25,
    "PT": 25,
    "RO": 25,
    "RU": 25,
    "SM": 25,
    "RS": 25,
    "SK": 25,
    "SI": 25,
    "ES": 25,
    "SE": 25,
    "CH": 25,
    "UA": 25,
    "GB": 25,
    "VA": 25,
    # Latin America
    "AR": 29,
    "BO": 29,
    "CL": 29,
    "CO": 29,
    "CR": 29,
    "CU": 29,
    "DO": 29,
    "EC": 29,
    "SV": 29,
    "GT": 29,
    "HN": 29,
    "MX": 29,
    "NI": 29,
    "PA": 29,
    "PY": 29,
    "PE": 29,
    "UY": 29,
    "VE": 29,
    # Brasil
    "BR": 27,
    # North America
    "US": 26,
    "CA": 26,
    # Oceania
    "AU": 31,
    "FJ": 31,
    "KI": 31,
    "MH": 31,
    "FM": 31,
    "NR": 31,
    "NZ": 31,
    "PW": 31,
    "PG": 31,
    "WS": 31,
    "SB": 31,
    "TO": 31,
    "TV": 31,
    "VU": 31,
    # Middle East
    "BH": 30,
    "IR": 30,
    "IQ": 30,
    "IL": 30,
    "JO": 30,
    "KW": 30,
    "LB": 30,
    "OM": 30,
    "QA": 30,
    "SA": 30,
    "SY": 30,
    "AE": 30,
    "YE": 30,
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)


class HTMDBClient:
    """
    Helper class:
        Handles all TMDB API calls needed by MKO.
    """

    _TMDB_BASE = "https://api.themoviedb.org/3"

    def __init__(self, session: httpx.AsyncClient, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    def _params(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Return base query params, optionally merged with extra."""

        p: dict[str, str] = {"api_key": self._api_key}
        if extra:
            p.update(extra)
        return p

    async def _get(
        self, path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Perform a GET request against the TMDB API."""

        try:
            resp = await self._session.get(
                f"{self._TMDB_BASE}{path}",
                params=self._params(params),
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {}

    async def get_translations(self, tmdb_id: int) -> list[dict[str, Any]]:
        """Return the translations list for a movie."""

        data = await self._get(f"/movie/{tmdb_id}/translations")
        return data.get("translations", [])

    async def get_credits(
        self, tmdb_id: int, language: str | None = None
    ) -> dict[str, Any]:
        """Return cast and crew for a movie."""

        params = {"language": language} if language else None
        return await self._get(f"/movie/{tmdb_id}/credits", params)

    async def fetch_title(
        self, tmdb_id: int, iso_639_1: str, iso_3166_1: str | None = None
    ) -> str:
        """
        Return the localised title for a given language/region pair.

        Falls back to any entry matching iso_639_1 if the region-specific
        entry is absent.
        """

        translations = await self.get_translations(tmdb_id)
        primary = next(
            (
                t
                for t in translations
                if t.get("iso_639_1") == iso_639_1
                and (iso_3166_1 is None or t.get("iso_3166_1") == iso_3166_1)
            ),
            None,
        )
        if not primary and iso_3166_1:
            primary = next(
                (t for t in translations if t.get("iso_639_1") == iso_639_1),
                None,
            )
        return (primary or {}).get("data", {}).get("title", "") or ""

    async def fetch_overview(self, tmdb_id: int) -> str:
        """
        Fetches the PT-BR synopsis of a movie.
        """

        translations = await self.get_translations(tmdb_id)
        for iso_3166_1 in ("BR", None):
            match = next(
                (
                    t
                    for t in translations
                    if t.get("iso_639_1") == "pt"
                    and (iso_3166_1 is None or t.get("iso_3166_1") == iso_3166_1)
                ),
                None,
            )
            if match:
                overview = match.get("data", {}).get("overview", "")
                if overview:
                    return overview
        return ""

    async def fetch_cast(self, tmdb_id: int, limit: int = 15) -> list[str]:
        """Return up to limit cast names in PT-BR."""

        data = await self.get_credits(tmdb_id, language="pt-BR")
        return [m["name"] for m in data.get("cast", [])[:limit] if m.get("name")]

    async def fetch_directors(self, tmdb_id: int) -> list[str]:
        """
        Return director names from the crew list.

        Filters strictly by job == "Director" to avoid including people
        whose known_for_department is "Directing" but who acted in this title.
        """

        data = await self.get_credits(tmdb_id)
        return [m["name"] for m in data.get("crew", []) if m.get("job") == "Director"]


class HLocalizer:
    """
    Helper class:
        Converts raw metadata values to Brazilian Portuguese strings.
    """

    _LANG_NAME_MAP: dict[str, str] = {
        "portuguese": "Português",
        "português": "Português",
        "english": "Inglês",
        "spanish": "Espanhol",
        "french": "Francês",
        "german": "Alemão",
        "italian": "Italiano",
        "japanese": "Japonês",
        "korean": "Coreano",
        "chinese": "Chinês",
        "russian": "Russo",
        "arabic": "Árabe",
    }

    _ISO_LANG_MAP: dict[str, str] = {
        "pt": "Português",
        "en": "Inglês",
        "es": "Espanhol",
        "fr": "Francês",
        "de": "Alemão",
        "it": "Italiano",
        "ja": "Japonês",
        "ko": "Coreano",
        "zh": "Chinês",
        "ru": "Russo",
        "ar": "Árabe",
        "hy": "Armênio",
        "ka": "Georgiano",
        "az": "Azerbaijano",
        "uk": "Ucraniano",
        "pl": "Polonês",
        "cs": "Tcheco",
        "ro": "Romeno",
        "hu": "Húngaro",
        "tr": "Turco",
        "fa": "Persa",
        "he": "Hebraico",
        "hi": "Hindi",
        "bn": "Bengali",
        "th": "Tailandês",
        "vi": "Vietnamita",
        "id": "Indonésio",
        "nl": "Holandês",
        "sv": "Sueco",
        "no": "Norueguês",
        "da": "Dinamarquês",
        "fi": "Finlandês",
        "el": "Grego",
        "sr": "Sérvio",
        "hr": "Croata",
        "sk": "Eslovaco",
        "bg": "Búlgaro",
        "lt": "Lituano",
        "lv": "Letão",
        "et": "Estoniano",
        "sq": "Albanês",
        "mk": "Macedônio",
        "sl": "Esloveno",
    }

    _ISO3_TO_ISO1: dict[str, str] = {
        "por": "pt",
        "eng": "en",
        "spa": "es",
        "fra": "fr",
        "deu": "de",
        "ita": "it",
        "jpn": "ja",
        "kor": "ko",
        "zho": "zh",
        "rus": "ru",
        "ara": "ar",
        "hye": "hy",
        "kat": "ka",
        "ukr": "uk",
        "pol": "pl",
        "ces": "cs",
        "ron": "ro",
        "hun": "hu",
        "tur": "tr",
        "fas": "fa",
        "heb": "he",
        "hin": "hi",
        "ben": "bn",
        "tha": "th",
        "vie": "vi",
        "ind": "id",
        "nld": "nl",
        "swe": "sv",
        "nor": "no",
        "dan": "da",
        "fin": "fi",
        "ell": "el",
        "srp": "sr",
        "hrv": "hr",
        "slk": "sk",
        "bul": "bg",
        "lit": "lt",
        "lav": "lv",
        "est": "et",
        "sqi": "sq",
        "mkd": "mk",
        "slv": "sl",
    }

    def countries(self, meta: Meta) -> str:
        """Convert production country codes to PT-BR names."""

        prod_countries = getattr(meta, "production_countries", None) or []
        origin_countries = getattr(meta, "origin_country", None) or []

        if prod_countries:
            codes = [
                c.get("iso_3166_1", "") for c in prod_countries if c.get("iso_3166_1")
            ]
        else:
            codes = [c for c in origin_countries if c]

        names = [COUNTRY_PTBR.get(code, code) for code in codes if code]
        return ", ".join(names) if names else "Desconhecido"

    def genres(self, meta: Meta) -> str:
        """Convert genre names to PT-BR.

        Accepts both a comma-separated string and a list, as the Meta
        object may expose genres in either form depending on UA version.
        """

        genres_raw = (
            getattr(meta, "genres", None)
            or getattr(meta, "combined_genres", None)
            or ""
        )
        if not genres_raw:
            return "Desconhecido"
        if isinstance(genres_raw, list):
            genre_list = [g.strip() for g in genres_raw if g.strip()]
        else:
            genre_list = [g.strip() for g in genres_raw.split(",") if g.strip()]
        if not genre_list:
            return "Desconhecido"
        return ", ".join(GENRE_PTBR.get(g, g) for g in genre_list)

    def audio_language(self, meta: Meta) -> str:
        """
        Determine audio language(s) in PT-BR.

        Resolution order: meta audio_languages, mediainfo audio tracks,
        then meta original_language as last resort.
        """

        audio_langs = getattr(meta, "audio_languages", None) or []
        if audio_langs:
            return ", ".join(
                self._LANG_NAME_MAP.get(lang.lower().strip(), lang)
                for lang in audio_langs
            )

        mi_tracks = (getattr(meta, "mediainfo", None) or {}).get("media", {}).get(
            "track", []
        ) or []
        seen: list[str] = []
        for track in mi_tracks:
            if track.get("@type") != "Audio":
                continue
            lang_raw = (track.get("Language") or "").lower().strip()
            if not lang_raw:
                continue
            code = self._ISO3_TO_ISO1.get(
                lang_raw.split("-")[0], lang_raw.split("-")[0]
            )
            if code not in seen:
                seen.append(code)

        if seen:
            return ", ".join(self._ISO_LANG_MAP.get(c, c) for c in seen)

        orig = (
            (getattr(meta, "original_language", "") or "").lower().strip().split("-")[0]
        )
        return self._ISO_LANG_MAP.get(orig, "Desconhecido")

    def video_quality(self, meta: Meta) -> str:
        """Convert release type to a localised video quality label."""

        type_raw = getattr(meta, "type", "") or ""
        return VIDEO_QUALITY_PTBR.get(type_raw.upper(), type_raw)


class HMediaInfo:
    """
    Helper class:
        Extracts and normalises technical metadata from mediainfo and meta fields.
    """

    _VIDEO_CODEC_MAP: list[tuple[list[str], str]] = [
        (["avc", "h.264", "h264"], "H.264"),
        (["hevc", "h.265", "h265"], "H.265 (HEVC)"),
        (["av1"], "AV1"),
        (["vp9"], "VP9"),
        (["xvid"], "XviD"),
        (["divx"], "DivX"),
        (["mpeg-4"], "MPEG-4"),
        (["mpeg"], "MPEG-2"),
    ]

    _AUDIO_CODEC_MAP: list[tuple[list[str], str]] = [
        (["aac"], "AAC"),
        (["e-ac-3", "eac3"], "E-AC-3 (Dolby Digital Plus)"),
        (["ac-3", "ac3"], "AC-3 (Dolby Digital)"),
        (["truehd"], "Dolby TrueHD"),
        (["dts"], "DTS"),
        (["mp3", "mpeg audio"], "MP3"),
        (["flac"], "FLAC"),
        (["opus"], "Opus"),
    ]

    def __init__(self, meta: Meta) -> None:
        tracks = (getattr(meta, "mediainfo", None) or {}).get("media", {}).get(
            "track", []
        ) or []
        self._video = next((t for t in tracks if t.get("@type") == "Video"), {})
        self._audio = next((t for t in tracks if t.get("@type") == "Audio"), {})
        self._general = next((t for t in tracks if t.get("@type") == "General"), {})
        self._meta = meta

    def _normalize_codec(self, fmt: str, mapping: list[tuple[list[str], str]]) -> str:
        f = fmt.lower()
        for keys, label in mapping:
            if any(k in f for k in keys):
                return label
        return fmt

    def video_codec(self) -> str:
        """Return the normalised video codec label."""

        fmt = self._video.get("Format", "").strip()
        if not fmt:
            fmt = (
                getattr(self._meta, "video_encode", "")
                or getattr(self._meta, "video_codec", "")
                or ""
            ).strip()
        return self._normalize_codec(fmt, self._VIDEO_CODEC_MAP) if fmt else ""

    def audio_codec(self) -> str:
        """Return the normalised audio codec label."""

        fmt = self._audio.get("Format", "").strip()
        if not fmt:
            fmt = (
                getattr(self._meta, "audio", "")
                or getattr(self._meta, "audio_codec", "")
                or ""
            ).strip()
        return self._normalize_codec(fmt, self._AUDIO_CODEC_MAP) if fmt else ""

    def _kbps(self, raw: Any) -> str:
        try:
            return f"{int(raw) // 1000}"
        except (TypeError, ValueError):
            return ""

    def video_bitrate(self) -> str:
        """Return video bitrate in Kbps."""

        return self._kbps(
            self._video.get("BitRate") or self._video.get("NominalBitRate")
        ) or self._kbps(getattr(self._meta, "video_bitrate", None))

    def audio_bitrate(self) -> str:
        """Return audio bitrate in Kbps."""

        return self._kbps(
            self._audio.get("BitRate") or self._audio.get("NominalBitRate")
        ) or self._kbps(getattr(self._meta, "audio_bitrate", None))

    def resolution(self) -> tuple[str, str]:
        """Return (width, height) strings, preferring mediainfo over meta."""

        width = str(
            self._video.get("Width", "") or getattr(self._meta, "width", "") or ""
        )
        height = str(
            self._video.get("Height", "") or getattr(self._meta, "height", "") or ""
        )
        return width, height

    def frame_rate(self) -> str:
        """Return frame rate as a formatted FPS string."""

        raw = (
            self._video.get("FrameRate")
            or self._general.get("FrameRate")
            or getattr(self._meta, "frame_rate", "")
            or ""
        )
        try:
            return f"{float(raw):.3f} FPS"
        except (TypeError, ValueError):
            return str(raw)

    def container(self, fallback: str = "") -> str:
        """Return the container format, preferring mediainfo General track."""

        fmt = (self._general.get("Format", "") or "").lower()
        if "matroska" in fmt:
            return "MKV"
        if "avi" in fmt:
            return "AVI"
        if "mp4" in fmt or "mpeg-4" in fmt:
            return "MP4"
        if fmt:
            return self._general.get("Format", fallback)
        return fallback

    def filesize(self) -> str:
        """Return a human-readable file size (GB or MB)."""

        raw = (
            self._general.get("FileSize")
            or getattr(self._meta, "content_size", None)
            or getattr(self._meta, "total_size", None)
            or (
                int(self._video.get("StreamSize", 0) or 0)
                + int(self._audio.get("StreamSize", 0) or 0)
            )
            or None
        )
        try:
            b = int(raw)
        except (TypeError, ValueError):
            return "N/A"
        gb = b / 1024**3
        return f"{gb:.2f} GB" if gb >= 1 else f"{b / 1024**2:.0f} MB"

    def duration(self) -> str:
        """Return duration in minutes from mediainfo General track."""

        raw = self._general.get("Duration") or self._video.get("Duration") or ""
        try:
            return str(int(float(raw)) // 60)
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def aspect_ratio(width: Any, height: Any) -> str:
        """Return an aspect ratio category from video dimensions."""

        try:
            r = int(width) / int(height)
            if r < 1.4:
                return "Tela Cheia (4x3)"
            if r < 1.8:
                return "Widescreen (16x9)"
            if r < 2.3:
                return "Widescreen (2.35:1)"
            return "Widescreen (2.39:1)"
        except (TypeError, ValueError, ZeroDivisionError):
            return "Widescreen (16x9)"


class HBBCodeBuilder:
    """
    Helper class:
        Assembles the BBCode body for a MakingOff forum post.
    """

    @staticmethod
    def html_encode(text: str) -> str:
        """Replace non-ASCII codepoints with named HTML entities where possible."""

        result = []
        for ch in text:
            cp = ord(ch)
            if cp > 127 and cp in codepoint2name:
                result.append(f"&{codepoint2name[cp]};")
            else:
                result.append(ch)
        return "".join(result)

    @staticmethod
    def _screen_rows(image_urls: list[str]) -> str:
        """Pair screenshot URLs into two-column BBCode rows."""

        rows = ""
        for i in range(0, len(image_urls), 2):
            left = image_urls[i]
            right = image_urls[i + 1] if i + 1 < len(image_urls) else ""
            cells = (
                f"[screenLeft][screenIma]{left}[/screenIma][/screenLeft]"
                f"[screenRight][screenIma]{right}[/screenIma][/screenRight][/tr]"
            )
            rows += cells if i == 0 else f"[tr]{cells}"
        return rows

    def build(
        self,
        *,
        title_br: str,
        title_orig: str,
        release: str,
        poster_url: str,
        overview: str,
        image_urls: list[str],
        cast_text: str,
        genres: str,
        directors: str,
        duration: str,
        year: str,
        countries: str,
        audio: str,
        subs: str,
        imdb_url: str,
        quality: str,
        container: str,
        video_codec: str,
        video_brate: str,
        audio_codec: str,
        audio_brate: str,
        res_str: str,
        aspect: str,
        fps_str: str,
        filesize: str,
    ) -> str:
        """Render and return the complete BBCode post body."""

        screen_rows = self._screen_rows(image_urls)

        if imdb_url:
            imdb_line = (
                f'<div><strong class="bbc">IMDB: </strong>'
                f'<a class="bbc_url" href="{imdb_url}" title="Link externo">{imdb_url}</a>'
                f"[/info]</div>\n"
            )
        else:
            imdb_line = "<div>[/info]</div>\n"

        bbcode = (
            f"<div>[tablePrinc][tr][titMasc]Título do Filme[/titMasc][/tr]</div>\n"
            f"<div>[tr][titTrad]{title_br}[/titTrad][titOri]{title_orig}[/titOri]"
            f"[release]{release}[/release][/tr]</div>\n"
            f"<div>[tr][posterMasc]Poster[/posterMasc]</div>\n"
            f"<div>[sinopseMasc]Sinopse[/sinopseMasc][/tr]</div>\n"
            f"<div>[tr][poster][posterIma]{poster_url}[/posterIma][/poster]</div>\n"
            f"<div>[sinopse]{overview}[/sinopse]</div>\n"
            f"<div>[tableScreen]Screenshots[/tableScreen]</div>\n"
            f"<div>{screen_rows}"
            f"[closeTab][/closeTab][/tablePrinc]</div>\n"
            f"<div>[tablePrinc][tr][posterMasc]Elenco[/posterMasc]</div>\n"
            f"<div>[infoMasc]Informações sobre o filme[/infoMasc]</div>\n"
            f"<div>[infoMasc]Informações sobre o release[/infoMasc]</div>\n"
            f"<div>[/tr][tr][elenco]\n{cast_text}\n[/elenco]</div>\n"
            f'<div>[info]<strong class="bbc">Gênero: </strong>{genres}</div>\n'
            f'<div><strong class="bbc">Diretor: </strong>{directors}</div>\n'
            f'<div><strong class="bbc">Duração: </strong>{duration} minutos</div>\n'
            f'<div><strong class="bbc">Ano de Lançamento: </strong>{year}</div>\n'
            f'<div><strong class="bbc">País de Origem: </strong>{countries}</div>\n'
            f'<div><strong class="bbc">Idioma do Áudio: </strong>{audio}</div>\n'
            f"{imdb_line}"
            f'<div>[info]<strong class="bbc">Qualidade de Vídeo: </strong>{quality}</div>\n'
            f'<div><strong class="bbc">Container: </strong>{container}</div>\n'
            f'<div><strong class="bbc">Vídeo Codec: </strong>{video_codec}</div>\n'
            f'<div><strong class="bbc">Vídeo Bitrate: </strong>{video_brate} Kbps</div>\n'
            f'<div><strong class="bbc">Áudio Codec: </strong>{audio_codec}</div>\n'
            f'<div><strong class="bbc">Áudio Bitrate: </strong>{audio_brate} Kbps</div>\n'
            f'<div><strong class="bbc">Resolução: </strong>{res_str}</div>\n'
            f'<div><strong class="bbc">Formato de Tela: </strong>{aspect}</div>\n'
            f'<div><strong class="bbc">Frame Rate: </strong>{fps_str}</div>\n'
            f'<div><strong class="bbc">Tamanho: </strong>{filesize}</div>\n'
            f'<div><strong class="bbc">Legendas: </strong>{subs}[/info]</div>\n'
            f"<div>[/tr][tr][rodape]Coopere, deixe semeando ao menos duas vezes o tamanho do arquivo que baixar.[/rodape]"
            f"[/tr][/tablePrinc]</div>"
        )

        return self.html_encode(bbcode)


class HIPBClient:
    """
    Helper class:
        Manages the IPB forum session, token retrieval, and post creation.
    """

    def __init__(
        self,
        session: httpx.AsyncClient,
        base_url: str,
        tracker_name: str,
    ) -> None:
        self._session = session
        self._base_url = base_url
        self._tracker = tracker_name

    def live_session_id(self) -> str:
        """Return the most recent session_id cookie value."""

        values = [
            c.value
            for c in self._session.cookies.jar
            if c.name == "session_id" and c.value
        ]
        return values[-1] if values else ""

    async def refresh_session(self) -> bool:
        """
        Refresh the IPB session token.

        IPB rotates the 's' token on each authenticated request. Sends a
        lightweight GET and verifies the response is not an anonymous session.

        Returns:
            bool: True if an authenticated session_id was obtained.
        """

        try:
            resp = await self._session.get(f"{self._base_url}/index.php?")
            resp.raise_for_status()
        except httpx.HTTPError as e:
            console.print(
                f"[cyan]{self._tracker}:[/cyan] Error validating session: {e}"
            )
            return False

        live = self.live_session_id()
        if not live:
            match = re.search(r"[?&]s=([a-f0-9]{32})", resp.text)
            if match:
                live = match.group(1)
                self._session.cookies.set("session_id", live, domain="makingoff.org")
                self._session.cookies.set(
                    "session_id", live, domain="indice.makingoff.org"
                )

        if not live:
            return False

        if "id='login_form'" in resp.text or 'id="login_form"' in resp.text:
            console.print(
                f"[cyan]{self._tracker}:[/cyan] The session is unauthenticated. "
                "Check member_id and pass_hash on the configuration."
            )
            return False

        return True

    async def get_new_post_tokens(self, forum_id: int) -> tuple[str, str, str]:
        """
        Retrieve tokens required to create a new forum topic.

        Args:
            forum_id (int): Target forum ID.

        Returns:
            tuple[str, str, str]: Session ID, auth key, attachment post key.
        """

        url = (
            f"{self._base_url}/index.php?"
            f"app=forums&module=post&section=post&do=new_post&f={forum_id}"
        )
        try:
            resp = await self._session.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            console.print(
                f"[cyan]{self._tracker}:[/cyan] Failed loading topic new page: {e}"
            )
            return "", "", ""

        soup = BeautifulSoup(resp.text, "html.parser")

        def _val(name: str) -> str:
            tag = soup.find("input", {"name": name})
            return str(tag.get("value", "")) if tag and hasattr(tag, "get") else ""  # type: ignore[union-attr]

        session_id = self.live_session_id() or _val("s")
        auth_key = _val("auth_key")
        attach_post_key = _val("attach_post_key")

        if "id='sign_in'" in resp.text or 'id="sign_in"' in resp.text:
            console.print(
                f"[cyan]{self._tracker}:[/cyan] Unauthenticated session detected on this page. "
                "Copy new headers from the browser."
            )
            return "", "", ""

        if not auth_key or not attach_post_key:
            console.print(
                f"[cyan]{self._tracker}:[/cyan] It wasn't possible to extract auth_key or "
                "attach_post_key. Check if the session is valid."
            )

        return session_id, auth_key, attach_post_key

    async def get_post_resolution(self, topic_url: str) -> int:
        """
        Fetches the topic resolution

        Returns:
            int: its resolution.
        """

        topic_url = re.sub(
            r"^https?://(www\.)?makingoff\.org", "https://makingoff.org", topic_url
        )

        try:
            resp = await self._session.get(topic_url, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError:
            return ("", "")

        soup = BeautifulSoup(resp.content, "html.parser", from_encoding="iso-8859-1")

        resolution = ""
        first_post = soup.find("div", attrs={"itemprop": "commentText"})
        if first_post:
            text = first_post.get_text(" ", strip=True)
            m = re.search(r"Resolu[^\s:]*[:\s]+(\d{3,4})\s*[xX×]\s*(\d{3,4})", text)
            if m:
                resolution = f"{m.group(1)}x{m.group(2)}"

        return int(resolution.split("x")[1])

    async def upload_attachment(
        self,
        torrent_path: str,
        session_id: str,
        attach_post_key: str,
        forum_id: int,
    ) -> bool:
        """
        Upload a torrent file as a forum attachment.

        TODO: add support to attach external subtitles,
              also extract pt/pt-br ones and attach them.

        Args:
            torrent_path (str): Path to the torrent file.
            session_id (str): Active forum session ID.
            attach_post_key (str): Attachment post key.
            forum_id (int): Target forum ID.

        Returns:
            bool: True if the upload succeeded.
        """

        url = (
            f"{self._base_url}/index.php?"
            f"s={session_id}"
            f"&app=core&module=attach&section=attach"
            f"&do=attachUploadiFrame"
            f"&attach_rel_module=post&attach_rel_id=0"
            f"&attach_post_key={attach_post_key}"
            f"&forum_id={forum_id}"
            f"&fetch_all=1"
        )
        try:
            with open(torrent_path, "rb") as f:
                data = f.read()
            filename = torrent_path.split("/")[-1]
            resp = await self._session.post(
                url,
                files={"FILE_UPLOAD": (filename, data, "application/x-bittorrent")},
            )
            resp.raise_for_status()
        except FileNotFoundError:
            console.print(
                f"[cyan]{self._tracker}:[/cyan] [bold red]Torrent file not found[/bold red]: {torrent_path}"
            )
            return False
        except httpx.HTTPError as e:
            console.print(
                f"[cyan]{self._tracker}:[/cyan] [bold red]Failed uploading attachment:[/bold red] {e}"
            )
            return False

        if '"is_error":0' in resp.text or '"msg":"upload_ok"' in resp.text:
            console.print(
                f"[cyan]{self._tracker}:[/cyan] [green]Attachment sent successfully.[/green]"
            )
            return True

        console.print(
            f"[cyan]{self._tracker}:[/cyan] [bold red]Unwanted response while uploading attachment:[/bold red]\n"
            f"{resp.text[:500]}"
        )
        return False

    async def search(self, index_url: str, phrase: str) -> dict[str, str] | None:
        """
        Performs a search on the given index url

        Args:
            index_url (str): The index url (e.g. "https://indice.makingoff.org").
            text (str): The text to be searched.

        Returns:
            dict[str, str]: A dictionary mapping title -> topic URL.
            None: if the search results nothing.
        """

        # do the search operation
        response_url = index_url.rstrip("/") + "/response.php"
        payload = {
            "current": "1",
            "rowCount": "50",
            "sort[tid]": "desc",
            "searchPhrase": phrase,
            "id": "b0df282a-0d67-40e5-8558-c9e93b7befed",
        }
        try:
            resp = await self._session.post(
                response_url,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": index_url,
                    "Origin": index_url,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            console.print(
                f"[cyan]{self._tracker}:[/cyan] Error on the search:[/bold red] {e}"
            )
            return None
        except Exception as e:
            console.print(
                f"[cyan]{self._tracker}:[/cyan] [bold red]Unwanted response while searching:[/bold red] {e}"
            )
            return None

        rows = data.get("rows") or []
        if not rows:
            return None

        # parse the dict from the response
        # title -> url
        results: dict[str, str] = {}
        for row in rows:
            title = row.get("title", "").strip()
            link_html = row.get("link", "")
            url_match = re.search(r'href=["\']([^"\']+)["\']', link_html)
            if title and url_match:
                results[title] = url_match.group(1)

        return results or None

    async def create_topic(
        self,
        forum_id: int,
        session_id: str,
        auth_key: str,
        attach_post_key: str,
        topic_title: str,
        post_body: str,
    ) -> str:
        """
        Create a new forum topic and return its URL.

        The forum uses ISO-8859-1. Form fields are encoded as Latin-1 with
        HTML numeric entities for out-of-range characters, matching what a
        browser would submit.

        Args:
            forum_id (int): Target forum ID.
            session_id (str): Active forum session ID.
            auth_key (str): Forum authentication key.
            attach_post_key (str): Attachment post key.
            topic_title (str): Topic title.
            post_body (str): Topic content.

        Returns:
            str: Topic URL, or an empty string if creation failed.
        """

        fields = {
            "enableemo": "yes",
            "enablesig": "yes",
            "TopicTitle": topic_title,
            "isRte": "1",
            "noSmilies": "0",
            "noCKEditor": "0",
            "Post": post_body,
            "st": "0",
            "app": "forums",
            "module": "post",
            "section": "post",
            "do": "new_post_do",
            "s": session_id,
            "p": "0",
            "t": "",
            "f": str(forum_id),
            "parent_id": "0",
            "attach_post_key": attach_post_key,
            "auth_key": auth_key,
            "removeattachid": "0",
            "return": "",
            "_from": "",
            "dosubmit": "Criar novo tópico",
        }

        body = "&".join(
            f"{urllib.parse.quote_plus(str(k))}="
            f"{urllib.parse.quote_plus(str(v).encode('latin-1', errors='xmlcharrefreplace').decode('latin-1'), encoding='latin-1')}"
            for k, v in fields.items()
        )

        try:
            resp = await self._session.post(
                f"{self._base_url}/index.php?",
                content=body.encode("latin-1"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=ISO-8859-1"
                },
                follow_redirects=True,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            console.print(f"[cyan]{self._tracker}:[/cyan] Failed creating topic: {e}")
            return ""

        topic_url = str(resp.url)
        if "showtopic=" in topic_url or "topic/" in topic_url:
            return topic_url

        match = re.search(r"showtopic=(\d+)", resp.text)
        if match:
            return f"{self._base_url}/index.php?showtopic={match.group(1)}"

        console.print(
            f"[yellow]{self._tracker}:[/yellow] Topic possibly created, "
            "but it wasn't possible to get the url."
        )
        return topic_url


class MKO:
    """
    MakingOff (makingoff.org).
    Cinema forum with public torrents (DHT).
    Platform: Invision Power Board (IPB).
    """

    supported_categories = ["MOVIE"]

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = COMMON(config)
        self.tracker = "MKO"
        self.source_flag = ""
        self.base_url = "https://makingoff.org/forum"
        self.index_url = "https://indice.makingoff.org/"
        self.banned_groups: list[str] = []
        

        # Cache for the resolved PT-BR display title, keyed by meta.uuid.
        self._display_title_cache: dict[str, str] = {}

        tracker_config = dict(dict(config.get("TRACKERS", {})).get("MKO", {}))
        public_trackers_raw = tracker_config.get("trackers", [])
        if isinstance(public_trackers_raw, str):
            self._public_trackers: list[str] = [
                t.strip() for t in public_trackers_raw.splitlines() if t.strip()
            ]
        else:
            self._public_trackers = list(public_trackers_raw)

        self.session = httpx.AsyncClient(
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,image/apng,*/*;q=0.8,"
                    "application/signed-exchange;v=b3;q=0.7"
                ),
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate",
                "Sec-Ch-Ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
            timeout=60.0,
        )

        tmdb_api_key = (
            dict(self.config.get("DEFAULT", {})).get("tmdb_api", "") or ""
        ).strip()

        self._tmdb = HTMDBClient(self.session, tmdb_api_key)
        self._localizer = HLocalizer()
        self._bbcode = HBBCodeBuilder()
        self._ipb = HIPBClient(self.session, self.base_url, self.tracker)

    def _tmdb_id(self, meta: Meta) -> int | None:
        """Extract TMDB ID from meta."""

        return getattr(meta, "tmdb_id", None) or getattr(meta, "tmdb", None) or None

    # -- credentials

    async def validate_credentials(self, meta: Meta) -> bool:
        """
        Validate tracker credentials and configure the authenticated session.

        Accepts either a full ``cookie_header`` string (recommended, copied
        directly from the browser) or individual ``member_id`` / ``pass_hash``
        fields.  The ``session_id`` cookie is always generated automatically
        as a random 32-character hex token — IPB rotates it on every
        authenticated response, so the first value just needs to exist.

        Args:
            meta: Release metadata.

        Returns:
            bool: True if the credentials are valid.
        """

        tracker_config = dict(
            dict(self.config.get("TRACKERS", {})).get(self.tracker, {})
        )

        raw_cookie_header = tracker_config.get("cookie_header", "").strip()
        if raw_cookie_header:
            for part in raw_cookie_header.split(";"):
                if "=" not in part:
                    continue
                name, _, value = part.strip().partition("=")
                if name:
                    self.session.cookies.set(name, value, domain="makingoff.org")
                    self.session.cookies.set(name, value, domain="indice.makingoff.org")
        else:
            member_id = tracker_config.get("member_id", "").strip()
            pass_hash = tracker_config.get("pass_hash", "").strip()

            if not member_id or not pass_hash:
                console.print(
                    f"[cyan]{self.tracker}:[/cyan] [bold red]Incomplete credentials on configuration.[/bold red] "
                    f"Fill 'cookie_header' (recommended) or 'member_id' and 'pass_hash' "
                    f"in config['TRACKERS']['{self.tracker}'].[/bold red]"
                )
                return False

            # Generate a fresh random session_id; IPB replaces it after the
            # first authenticated request, so the exact value does not matter.
            session_id = secrets.token_hex(16)

            for domain in ("makingoff.org", "indice.makingoff.org"):
                self.session.cookies.set("session_id", session_id, domain=domain)
                self.session.cookies.set("member_id", member_id, domain=domain)
                self.session.cookies.set("pass_hash", pass_hash, domain=domain)

        if not await self._ipb.refresh_session():
            console.print(
                f"[cyan]{self.tracker}:[/cyan] [bold red]Session couldn't be validated.[/bold red] "
                "Cookies may be expired."
            )
            return False

        return True

    # -- torrent

    async def create_public_torrent(self, meta: Meta) -> str:
        """
        Create a public torrent from BASE.torrent by stripping tracker URLs
        and the private flag.

        The announce list is sourced from ``config['TRACKERS']['MKO']['trackers']``
        so it can be maintained without touching the source code.

        Args:
            meta: Release metadata.

        Returns:
            str: Path to the generated public torrent file.
        """

        base_dir: str = meta.base_dir
        uuid: str = meta.uuid
        base_path = f"{base_dir}/tmp/{uuid}/BASE.torrent"

        video_path = getattr(meta, "video", "") or ""
        media_filename = os.path.basename(video_path) if video_path else ""
        release_name = media_filename or getattr(meta, "name", "") or uuid
        out_path = f"{base_dir}/tmp/{uuid}/{release_name.replace(' ', '.')}.torrent"

        loop = asyncio.get_running_loop()
        torrent = await loop.run_in_executor(None, Torrent.read, base_path)

        if self._public_trackers:
            torrent.metainfo["announce"] = self._public_trackers[0]
            torrent.metainfo["announce-list"] = [[t] for t in self._public_trackers]
        else:
            torrent.metainfo.pop("announce", None)
            torrent.metainfo.pop("announce-list", None)

        torrent.metainfo.get("info", {}).pop("private", None)
        torrent.metainfo["comment"] = ""

        await loop.run_in_executor(
            None, lambda: Torrent.copy(torrent).write(out_path, overwrite=True)
        )

        console.print(
            f"[cyan]{self.tracker}:[/cyan] [green]Public torrent created.[/green]"
        )

        for extra_name in ["[MKO].torrent", "MKO.torrent"]:
            extra_path = f"{base_dir}/tmp/{uuid}/{extra_name}"
            shutil.copy2(out_path, extra_path)

        return out_path

    async def search_existing(
        self, meta: Meta, disctype: str = ""
    ) -> list[dict[str, str]]:
        """
        Search for existing releases on the forum before uploading.

        Args:
            meta: Release metadata.
            disctype: Unused; kept for interface compatibility.

        Returns:
            list[dict[str, str]]: Detected duplicate entries.
        """

        duplicates: list[dict[str, str]] = []

        if not await self.validate_credentials(meta):
            return duplicates

        hidef_resolutions = {"720p", "1080i", "1080p", "2160p", "4320p"}
        resolution_str = getattr(meta, "resolution", "") or ""
        uploading_hidef = resolution_str in hidef_resolutions
        upload_year = str(getattr(meta, "year", "") or "")

        title_ptbr = await self._resolve_display_title(meta)
        title_orig = getattr(meta, "original_title", "") or ""
        title_en = getattr(meta, "title", "") or ""

        if self._is_brazilian(meta):
            candidates = [title_ptbr]
        else:
            candidates = []
            for t in [title_ptbr, title_en, title_orig]:
                if t and t not in candidates:
                    candidates.append(t)

        results: dict[str, str] = {}
        for candidate in candidates:
            term = candidate.strip()
            console.print(
                f"[cyan]{self.tracker}:[/cyan] [yellow]Searching for:[/yellow] {term}"
            )
            found = await self._ipb.search(self.index_url, term)
            if found:
                results = found
                break

        if not results:
            return duplicates

        for title, url in results.items():
            existing_hidef = title.strip().startswith("[Hidef]")

            if upload_year:
                year_int = int(upload_year)
                if not any(f"({y})" in title for y in (year_int - 1, year_int, year_int + 1)):
                    console.print(
                        f"[cyan]{self.tracker}:[/cyan] [yellow]Skipping: different year in existing release:[/yellow] {title}"
                    )                
                    continue

            # Uploading SD while a Hidef exists → block immediately.
            if not uploading_hidef and existing_hidef:
                console.print(
                    f"[cyan]{self.tracker}:[/cyan] [bold red]Aborting: A Hidef release exists:[/bold red] {title}"
                )
                meta.skipping = self.tracker
                duplicates.append({"name": title, "size": "", "link": url})
                continue

            # Uploading Hidef over an existing SD → allowed.
            if uploading_hidef and not existing_hidef:
                continue

            # Same tier (SD vs SD or Hidef vs Hidef) → compare resolution.
            resolution = await self._ipb.get_post_resolution(url)

            try:
                upload_height = int(resolution_str.replace("p", "").replace("i", ""))
            except (ValueError, TypeError):
                upload_height = 0

            if resolution <= upload_height:
                console.print(
                    f"[cyan]{self.tracker}:[/cyan] [bold red]Aborting: A better or equivalent "
                    f"Hidef release exists:[/bold red] {title}"
                )
                meta.skipping = self.tracker
                duplicates.append({"name": title, "size": str(resolution), "link": url})
                continue

        return duplicates

    # -- forum routing

    def get_forum_id(self, meta: Meta) -> int:
        """
        Determine the target forum ID based on content type and country of origin.

        Args:
            meta: Release metadata.

        Returns:
            int: Selected forum ID.
        """

        genres_raw = (
            getattr(meta, "genres", None)
            or getattr(meta, "combined_genres", None)
            or ""
        )
        if isinstance(genres_raw, list):
            genres_str = ", ".join(genres_raw)
        else:
            genres_str = genres_raw
        if "documentary" in genres_str.lower() or "documentário" in genres_str.lower():
            return 28

        try:
            duration = int(getattr(meta, "runtime", 0) or 0)
        except (TypeError, ValueError):
            duration = 0

        if 0 < duration < 40:
            return 77

        origin_countries: list[str] = getattr(meta, "origin_country", None) or []
        if not origin_countries:
            prod_countries = getattr(meta, "production_countries", None) or []
            origin_countries = [
                c.get("iso_3166_1", "") for c in prod_countries if c.get("iso_3166_1")
            ]

        for code in origin_countries:
            if code in FORUM_ID_BY_COUNTRY:
                return FORUM_ID_BY_COUNTRY[code]

        console.print(
            f"[cyan]{self.tracker}:[/cyan] [bold yellow]Unmapped origin country [/bold yellow]"
            f"({origin_countries}). [bold yellow]Select the subforum manually:[/bold yellow]"
        )
        forum_options = {
            "1": (461, "África"),
            "2": (24, "Asiático"),
            "3": (77, "Curtas"),
            "4": (28, "Documentários"),
            "5": (25, "Europeu"),
            "6": (29, "Latino Americano"),
            "7": (27, "Nacional (Brasil)"),
            "8": (26, "Norte-Americano"),
            "9": (31, "Oceania"),
            "10": (30, "Oriente Médio"),
        }
        for k, (fid, name) in forum_options.items():
            console.print(f"  {k}) {name} (ID: {fid})")

        choice = input("Escolha: ").strip()
        if choice in forum_options:
            return forum_options[choice][0]

        console.print(
            f"[cyan]{self.tracker}:[/cyan] [yellow]Invalid option, using North-American (26) as default.[/yellow]"
        )
        return 26

    # -- title resolution

    def _is_brazilian(self, meta: Meta) -> bool:
        """
        Detect whether the release is a Brazilian production.

        Checks origin_country and production_countries first; falls back to
        original_language == 'pt' for older/regional titles.

        Args:
            meta: Release metadata.

        Returns:
            bool: True if the release is considered Brazilian.
        """

        origin_countries: list[str] = getattr(meta, "origin_country", None) or []
        prod_codes = [
            c.get("iso_3166_1", "")
            for c in (getattr(meta, "production_countries", None) or [])
            if c.get("iso_3166_1")
        ]
        if "BR" in origin_countries or "BR" in prod_codes:
            return True
        return (getattr(meta, "original_language", "") or "").lower() == "pt"

    async def _resolve_display_title(self, meta: Meta) -> str:
        """
        Resolve the display title, preferring PT-BR.

        For Brazilian films, tries PT-BR first then falls back to
        original_title. For foreign films, tries PT-BR then English
        when the native and original titles are identical.

        The resolved title is cached on the tracker instance (keyed by
        ``meta.uuid``) so that repeated calls within the same upload do
        not trigger extra TMDB requests.

        Args:
            meta: Release metadata.

        Returns:
            str: Resolved display title.
        """

        cache_key: str = getattr(meta, "uuid", "") or ""
        if cache_key and cache_key in self._display_title_cache:
            return self._display_title_cache[cache_key]

        tmdb_id = self._tmdb_id(meta)
        title_native = getattr(meta, "title", "") or ""
        title_orig = getattr(meta, "original_title", "") or ""

        if self._is_brazilian(meta):
            if tmdb_id:
                ptbr = await self._tmdb.fetch_title(tmdb_id, "pt", "BR")
                if ptbr:
                    title_native = ptbr
                elif title_orig:
                    title_native = title_orig
        else:
            if tmdb_id:
                ptbr = await self._tmdb.fetch_title(tmdb_id, "pt", "BR")
                if ptbr and ptbr.lower() != title_orig.lower():
                    title_native = ptbr
                elif title_native.lower() == title_orig.lower():
                    en = await self._tmdb.fetch_title(tmdb_id, "en", "US")
                    if en and en.lower() != title_orig.lower():
                        title_native = en

        if cache_key:
            self._display_title_cache[cache_key] = title_native
        return title_native

    # -- topic title

    async def get_topic_title(self, meta: Meta) -> str:
        """
        Generate the forum topic title.

        Format for Brazilian films:  [Hidef] PT-BR Title (Year)
        Format for foreign films:    [Hidef] PT-BR Title / Original Title (Year)

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            str: Formatted topic title.
        """

        hidef_resolutions = {"720p", "1080i", "1080p", "2160p", "4320p"}
        prefix = (
            "[Hidef] "
            if (getattr(meta, "resolution", "") or "") in hidef_resolutions
            else ""
        )

        title_ptbr = await self._resolve_display_title(meta)
        year = str(getattr(meta, "year", "") or "")

        if self._is_brazilian(meta):
            title_part = title_ptbr
        else:
            title_orig = getattr(meta, "original_title", "") or ""
            title_part = (
                f"{title_ptbr} / {title_orig}"
                if title_orig and title_orig.lower() != title_ptbr.lower()
                else title_ptbr
            )

        return f"{prefix}{title_part} ({year})" if year else f"{prefix}{title_part}"

    # -- description generation

    def _extract_image_urls(self, meta: Meta) -> list[str]:
        """
        Extract screenshot URLs from meta image_list.

        Handles both plain URL strings and dict entries produced by
        various image host modules.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            list[str]: Resolved image URLs.
        """

        urls: list[str] = []
        for img in meta.get("image_list", []) or []:
            if isinstance(img, str):
                urls.append(img)
            elif isinstance(img, dict):
                url = (
                    img.get("raw_url")
                    or img.get("img_url")
                    or img.get("url")
                    or img.get("web_url")
                    or ""
                )
                if url:
                    urls.append(url)
        return urls

    def _subtitles_ptbr(self) -> str:
        """
        Prompt the user to select a subtitle type.

        Returns:
            str: Selected subtitle type label.
        """

        options = {"1": "Anexas", "2": "Embutidas", "3": "Fixas", "4": "Sem Legenda"}
        console.print(f"[cyan]{self.tracker}:[/cyan] [yellow]Any subtitles?[/yellow]")
        for k, v in options.items():
            console.print(f"  {k}) {v}")
        return options.get(input("Choose: ").strip(), "")

    async def generate_description(self, meta: Meta) -> str:
        """
        Generate the BBCode description for the forum post.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            str: Formatted BBCode description.
        """

        tmdb_id = self._tmdb_id(meta)

        title_br = await self._resolve_display_title(meta)
        title_orig = (
            title_br
            if self._is_brazilian(meta)
            else (getattr(meta, "original_title", "") or title_br)
        )

        video_path = getattr(meta, "video", "") or ""
        media_filename = os.path.basename(video_path) if video_path else ""
        release_name = media_filename or getattr(meta, "name", "") or meta.uuid
        release = release_name.replace(" ", ".").rsplit(".", 1)[0]

        poster_raw = getattr(meta, "poster", "") or ""
        poster_url = (
            poster_raw
            if poster_raw.startswith("http")
            else f"https://image.tmdb.org/t/p/original{poster_raw}"
            if poster_raw
            else ""
        )

        # Prefer TMDB PT-BR overview already cached by the UA; fall back to
        # a fresh TMDB fetch, then to whatever the UA stored in meta.overview.
        ptbr_main = (
            (getattr(meta, "tmdb_localized_data", None) or {})
            .get("pt-BR", {})
            .get("main", {})
        )
        overview = (
            ptbr_main.get("overview")
            or (await self._tmdb.fetch_overview(tmdb_id) if tmdb_id else "")
            or getattr(meta, "overview", "")
            or ""
        )

        cast_names = await self._tmdb.fetch_cast(tmdb_id) if tmdb_id else []
        cast_text = "".join(
            f"<div>{name.strip()}</div>\n" for name in cast_names if name.strip()
        )

        tmdb_dirs = await self._tmdb.fetch_directors(tmdb_id) if tmdb_id else []
        imdb_dirs = (getattr(meta, "imdb_info", None) or {}).get("directors", []) or []
        directors = ", ".join(tmdb_dirs if tmdb_dirs else imdb_dirs)

        imdb_id_raw = str(getattr(meta, "imdb_id", "") or "").strip()
        if imdb_id_raw:
            digits = imdb_id_raw.lstrip("t") or imdb_id_raw
            imdb_url = f"https://www.imdb.com/title/tt{digits.zfill(7)}/"
        else:
            imdb_url = ""

        mi = HMediaInfo(meta)
        width, height = mi.resolution()
        res_str = (
            f"{width}x{height}"
            if width and height
            else (getattr(meta, "resolution", "") or "")
        )

        # Duration: prefer TMDB/IMDB runtime from meta; fall back to mediainfo.
        duration = str(getattr(meta, "runtime", "") or mi.duration() or "")

        return self._bbcode.build(
            title_br=title_br,
            title_orig=title_orig,
            release=release,
            poster_url=poster_url,
            overview=overview,
            image_urls=self._extract_image_urls(meta),
            cast_text=cast_text,
            genres=self._localizer.genres(meta),
            directors=directors,
            duration=duration,
            year=str(getattr(meta, "year", "") or ""),
            countries=self._localizer.countries(meta),
            audio=self._localizer.audio_language(meta),
            subs=self._subtitles_ptbr(),
            imdb_url=imdb_url,
            quality=self._localizer.video_quality(meta),
            container=mi.container(
                fallback=(getattr(meta, "container", "") or "").upper()
            ),
            video_codec=mi.video_codec(),
            video_brate=mi.video_bitrate(),
            audio_codec=mi.audio_codec(),
            audio_brate=mi.audio_bitrate(),
            res_str=res_str,
            aspect=HMediaInfo.aspect_ratio(width, height),
            fps_str=mi.frame_rate(),
            filesize=mi.filesize(),
        )

    # -- validation and upload

    async def get_additional_checks(self, meta: Meta) -> bool:
        """
        Validate tracker-specific requirements before uploading.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            bool: True if the release meets all requirements.
        """

        if getattr(meta, "category", "") != "MOVIE":
            console.print(
                f"[cyan]{self.tracker}:[/cyan] [bold red]Only movies (MOVIE) are allowed on this forum.[/bold red]"
            )
            return False

        if getattr(meta, "resolution", "") == "2160p":
            console.print(
                f"[cyan]{self.tracker}:[/cyan] [bold red]4K Resolution (2160p) isn't allowed on this forum.[/bold red]"
            )
            return False

        video = (getattr(meta, "video", "") or "").upper()
        if not any(c in video for c in ("H264", "H.264", "AVC")):
            console.print(
                f"[cyan]{self.tracker}:[/cyan] [bold red]Only H.264 codec is allowed on this forum.[/bold red]"
            )
            return False

        if (getattr(meta, "container", "") or "").upper() not in ("MKV", "AVI"):
            console.print(
                f"[cyan]{self.tracker}:[/cyan] [bold red]Only MKV/AVI containers are allowed on this forum.[/bold red]"
            )
            return False

        return True

    async def upload(self, meta: Meta, _: Any = None) -> bool:
        """
        Upload a release by creating a forum topic with the torrent as attachment.

        Args:
            meta (dict[str, Any]): Release metadata.
            _ (Any): Unused argument.

        Returns:
            bool: True if the upload succeeded.
        """

        # The UA instantiates a fresh tracker object for the upload step,
        # so credentials must be loaded again here.
        if not await self.validate_credentials(meta):
            meta["tracker_status"][self.tracker]["status_message"] = (
                "Failed to validate credentials before upload."
            )
            return False

        forum_id = self.get_forum_id(meta)
        console.print(
            f"[cyan]{self.tracker}:[/cyan] [green]Selected subforum:[/green] {forum_id} "
        )

        session_id, auth_key, attach_post_key = await self._ipb.get_new_post_tokens(
            forum_id
        )
        if not auth_key or not attach_post_key:
            meta["tracker_status"][self.tracker]["status_message"] = (
                "Failed to retrieve IPB session tokens."
            )
            return False

        torrent_path = await self.create_public_torrent(meta)

        if not await self._ipb.upload_attachment(
            torrent_path, session_id, attach_post_key, forum_id
        ):
            meta["tracker_status"][self.tracker]["status_message"] = (
                "Failed to upload .torrent attachment."
            )
            return False

        topic_title = await self.get_topic_title(meta)
        post_body = await self.generate_description(meta)

        if meta.get("debug", False):
            for k in sorted(meta.keys()):
                if any(
                    x in k.lower()
                    for x in ["name", "title", "folder", "release", "torrent"]
                ):
                    console.print(f"  {k}: {meta[k]}")
            txt_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/MKO_bbcode.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"TITULO: {topic_title}\n\n")
                f.write(post_body)
            console.print(
                f"[cyan]{self.tracker}:[/cyan] [yellow]BBCode saved.[/yellow] {txt_path}"
            )
            return True

        topic_url = await self._ipb.create_topic(
            forum_id=forum_id,
            session_id=session_id,
            auth_key=auth_key,
            attach_post_key=attach_post_key,
            topic_title=topic_title,
            post_body=post_body,
        )

        if topic_url:
            console.print(
                f"[cyan]{self.tracker}:[/cyan] [green]Topic created.[/green] {topic_url}"
            )
            meta["tracker_status"][self.tracker]["status_message"] = (
                f"Upload successful: {topic_url}"
            )
            return True

        meta["tracker_status"][self.tracker]["status_message"] = (
            "Failed creating the forum topic."
        )
        return False
