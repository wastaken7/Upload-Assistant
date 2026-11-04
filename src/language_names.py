"""Name languages and look them up by name with Babel's CLDR data.

langcodes needs the language_data package for this, and language_data depends
on marisa-trie, a compiled extension that lags behind new Python releases.
langcodes still parses and normalizes the tags.
"""

import re
import unicodedata
from functools import cache
from typing import Any, cast

import langcodes
import pycountry
from babel import Locale
from babel.core import UnknownLocaleError
from babel.localedata import locale_identifiers

# Locales whose names find() recognizes, from lowest to highest priority.
FIND_LOCALES = ("it", "de", "fr", "es", "pt", "en")

_ISO_LANGUAGES = cast(Any, pycountry.languages)


@cache
def _names(locale: str, kind: str) -> dict[str, str]:
    """Babel's names of one kind ("languages", "scripts" or "territories"), keyed by code."""
    try:
        data = Locale.parse(locale)
    except UnknownLocaleError, ValueError:
        data = Locale.parse("en")
    return {str(code): str(name) for code, name in getattr(data, kind).items()}


def _iso_name(code: str) -> str | None:
    entry = _ISO_LANGUAGES.get(alpha_2=code) if len(code) == 2 else _ISO_LANGUAGES.get(alpha_3=code)
    return str(entry.name) if entry else None


def _named(names: dict[str, str], code: str, placeholder: str) -> str:
    return names.get(code) or f"{names.get(placeholder, placeholder)} [{code}]"


def language_name(lang: langcodes.Language, in_locale: str = "en") -> str:
    """Name only the language part of the tag, like ``Language.language_name``."""
    code = lang.language or "und"
    names = _names(in_locale, "languages")
    name = names.get(code) or _names("en", "languages").get(code) or _iso_name(code)
    return name or _named(names, code, "und")


def display_name(lang: langcodes.Language, in_locale: str = "en") -> str:
    """Name the whole tag, like ``Language.display_name``: "Portuguese (Brazil)"."""
    lang = lang.simplify_script()
    details: list[str] = []
    if lang.script:
        details.append(_named(_names(in_locale, "scripts"), lang.script, "Zzzz"))
    if lang.territory:
        details.append(_named(_names(in_locale, "territories"), lang.territory, "ZZ"))
    name = language_name(lang, in_locale)
    return f"{name} ({', '.join(details)})" if details else name


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(char for char in decomposed if not unicodedata.combining(char)).split())


@cache
def _name_index() -> dict[str, str]:
    index: dict[str, str] = {}
    # Each source overwrites the one before it, so the last one wins a clash.
    for entry in _ISO_LANGUAGES:
        index[_normalize(str(entry.name))] = str(getattr(entry, "alpha_2", None) or entry.alpha_3)
    for code in locale_identifiers():
        if "_" not in code and (autonym := _names(code, "languages").get(code)):
            index[_normalize(autonym)] = code
    for code in FIND_LOCALES:
        for tag, name in _names(code, "languages").items():
            index[_normalize(name)] = tag.replace("_", "-")
    return index


def find(name: str) -> langcodes.Language:
    """Look up a language by its exact name in English, a few common locales, or its own language.

    Unlike ``langcodes.find``, a name never matches a longer or shorter word,
    so "series" is not taken for the Seri language. A trailing clarification
    such as "Portuguese (Brazil)" is ignored when the full name is unknown.
    """
    key = _normalize(name)
    index = _name_index()
    tag = index.get(key) or index.get(re.sub(r"\s*\(.*\)$", "", key))
    if not tag:
        raise LookupError(f"Can't find any language named {name!r}")
    return langcodes.Language.get(tag)
