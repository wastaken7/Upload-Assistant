from typing import Any

BOOK_LABELS = {
    "en": {
        "author": "Author",
        "average_bitrate": "Average Bitrate",
        "book_translator": "Translator",
        "duration": "Duration",
        "edition": "Edition",
        "narrator": "Narrator",
        "overview": "Overview",
        "publisher": "Publisher",
        "technical_details": "Technical Details",
        "year": "Release Year",
    },
    "pt-BR": {
        "author": "Autor",
        "average_bitrate": "Bitrate Médio",
        "book_translator": "Tradutor",
        "duration": "Duração",
        "edition": "Edição",
        "narrator": "Narrador",
        "overview": "Visão Geral",
        "publisher": "Editora",
        "technical_details": "Detalhes Técnicos",
        "year": "Ano de Lançamento",
    },
}


def get_book_labels(language: str) -> dict[str, str]:
    try:
        return BOOK_LABELS[language]
    except KeyError as error:
        raise ValueError(f"Unsupported description language: {language}") from error


GAME_LABELS = {
    "en": {
        "technical_details": "Technical Details",
        "overview": "Overview",
        "platform": "Platform",
        "version": "Version",
        "genre": "Genre",
        "developer": "Developer",
        "publisher": "Publisher",
        "system_requirements": "System Requirements",
        "minimum": "Minimum",
        "recommended": "Recommended",
        "official_supported_languages": "Officially Supported Languages",
        "language": "Language",
        "support": "Support",
    },
    "pt-BR": {
        "technical_details": "Detalhes Técnicos",
        "overview": "Visão Geral",
        "platform": "Plataforma",
        "version": "Versão",
        "genre": "Gênero",
        "developer": "Desenvolvedor",
        "publisher": "Distribuidora",
        "system_requirements": "Requisitos do Sistema",
        "minimum": "Mínimo",
        "recommended": "Recomendado",
        "official_supported_languages": "Idiomas Oficialmente Suportados",
        "language": "Idioma",
        "support": "Suporte",
    },
}

MUSIC_LABELS = {
    "en": {
        "details": "Music Details",
        "artist": "Artist",
        "album": "Album",
        "year": "Original Release Year",
        "release_year": "Release Year",
        "edition": "Edition",
        "edition_year": "Edition Year",
        "type": "Release Type",
        "media": "Media",
        "label": "Label",
        "catalogue": "Catalogue Number",
        "genres": "Genres",
        "tracks": "Tracks",
        "discs": "Discs",
        "format": "Format",
        "codec": "Codec",
        "bit_depth": "Bit Depth",
        "sample_rate": "Sample Rate",
        "channels": "Channels",
        "bitrate": "Bitrate",
        "external_ids": "External IDs",
        "external_id_labels": {
            "musicbrainz_release": "MusicBrainz Release",
            "musicbrainz_release_group": "MusicBrainz Release Group",
            "discogs_release": "Discogs Release",
            "discogs_master": "Discogs Master",
        },
    },
    "pt-BR": {
        "details": "Detalhes da Música",
        "artist": "Artista",
        "album": "Álbum",
        "year": "Ano de Lançamento Original",
        "release_year": "Ano desta Edição",
        "edition": "Edição",
        "edition_year": "Ano da Edição",
        "type": "Tipo de Lançamento",
        "media": "Mídia",
        "label": "Gravadora",
        "catalogue": "Número de Catálogo",
        "genres": "Gêneros",
        "tracks": "Faixas",
        "discs": "Discos",
        "format": "Formato",
        "codec": "Codec",
        "bit_depth": "Profundidade de Bits",
        "sample_rate": "Taxa de Amostragem",
        "channels": "Canais",
        "bitrate": "Bitrate",
        "external_ids": "IDs Externos",
        "external_id_labels": {
            "musicbrainz_release": "Lançamento MusicBrainz",
            "musicbrainz_release_group": "Grupo de Lançamentos MusicBrainz",
            "discogs_release": "Lançamento Discogs",
            "discogs_master": "Master Discogs",
        },
    },
}

COMMON_LABELS = {
    "en": {
        "audio_languages": "Audio Language/s",
        "subtitle_languages": "Subtitle Language/s",
        "hardcoded_subtitles": "Hardcoded Subtitle Language/s",
    },
    "pt-BR": {
        "audio_languages": "Idioma(s) de Áudio",
        "subtitle_languages": "Idioma(s) das Legendas",
        "hardcoded_subtitles": "Idioma(s) das Legendas Queimadas (HC)",
    },
}


def get_labels(labels: dict[str, dict[str, Any]], language: str) -> dict[str, Any]:
    try:
        return labels[language]
    except KeyError as error:
        raise ValueError(f"Unsupported description language: {language}") from error
