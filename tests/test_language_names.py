# ruff: noqa: S101
import langcodes
import pytest

from src import language_names
from src.languages import LanguagesManager


@pytest.mark.parametrize(
    ("tag", "locale", "expected"),
    [
        ("pt-BR", "en", "Portuguese (Brazil)"),
        ("pt-BR", "pt", "português (Brasil)"),
        ("it", "it", "italiano"),
        ("zh-Hant-TW", "en", "Chinese (Traditional, Taiwan)"),
        ("es-419", "en", "Spanish (Latin America)"),
        ("en-Latn", "en", "English"),
        ("und", "en", "Unknown language"),
        ("zxx", "en", "No linguistic content"),
        ("qaa", "en", "Unknown language [qaa]"),
        ("qaa", "pt", "idioma desconhecido [qaa]"),
    ],
)
def test_display_name(tag, locale, expected):
    assert language_names.display_name(langcodes.Language.get(tag), locale) == expected


def test_language_name_ignores_script_and_territory():
    assert language_names.language_name(langcodes.Language.get("sr-Latn-RS"), "en") == "Serbian"


def test_language_name_falls_back_to_iso_names():
    assert language_names.language_name(langcodes.Language.get("isv"), "en") == "Interslavic"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("English", "en"),
        ("portuguese", "pt"),
        ("Português", "pt"),
        ("Portugues", "pt"),
        ("Brazilian Portuguese", "pt-BR"),
        ("Portuguese (Brazil)", "pt"),
        ("Inglés", "en"),
        ("Deutsch", "de"),
        ("Nederlands", "nl"),
        ("Norwegian Bokmal", "nb"),
    ],
)
def test_find(name, expected):
    assert language_names.find(name).to_tag() == expected


@pytest.mark.parametrize("word", ["series", "music", "the", "personal", "Klingonese", ""])
def test_find_needs_an_exact_name(word):
    with pytest.raises(LookupError):
        language_names.find(word)


def test_title_language_ignores_words_that_only_resemble_language_names():
    manager = LanguagesManager()

    assert manager.extract_language_from_title("Music Series") is None
    assert manager.extract_language_from_title("Director commentary in Portuguese") == "Portuguese"
