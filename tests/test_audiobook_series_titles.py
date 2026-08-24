from src.book_extractors import extract_audiobook_series_from_title
from src.book_prep import normalize_audiobook_title


def test_normalize_audiobook_title_removes_repeated_series_suffix():
    assert normalize_audiobook_title("O bobo: Os Contos de Hans Christian Andersen", "Os Contos de Hans Christian Andersen") == "O bobo"  # noqa: S101


def test_normalize_audiobook_title_keeps_title_equal_to_series():
    assert normalize_audiobook_title("Andersen", "Andersen") == "Andersen"  # noqa: S101


def test_normalize_audiobook_title_keeps_title_without_series():
    assert normalize_audiobook_title("Meu irmãozinho me atrapalha", "") == "Meu irmãozinho me atrapalha"  # noqa: S101


def test_normalize_audiobook_title_removes_repeated_series_prefix():
    assert normalize_audiobook_title("Os Contos de Hans Christian Andersen: O bobo", "Os Contos de Hans Christian Andersen") == "O bobo"  # noqa: S101


def test_extract_audiobook_series_without_comma():
    assert extract_audiobook_series_from_title("Crescendo: Hush, hush Livro 2") == ("Crescendo", "Hush, hush", "2")  # noqa: S101


def test_extract_audiobook_history_series_format():
    assert extract_audiobook_series_from_title("O Casamento de Narizinho: História 4 de Reinações de Narizinho") == (  # noqa: S101
        "O Casamento de Narizinho",
        "Reinações de Narizinho",
        "4",
    )


def test_extract_audiobook_series_keeps_regular_subtitle():
    assert extract_audiobook_series_from_title("Morte no Internato: Uma investigação") == ("Morte no Internato: Uma investigação", "", "")  # noqa: S101
