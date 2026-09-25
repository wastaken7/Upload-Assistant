from src.book_extractors import extract_audiobook_series_from_title
from src.book_prep import normalize_audiobook_title


def test_normalize_audiobook_title_removes_repeated_series_suffix():
    assert normalize_audiobook_title("Livro Exemplo: Série Imaginária", "Série Imaginária") == "Livro Exemplo"  # noqa: S101


def test_normalize_audiobook_title_keeps_title_equal_to_series():
    assert normalize_audiobook_title("Série Exemplo", "Série Exemplo") == "Série Exemplo"  # noqa: S101


def test_normalize_audiobook_title_keeps_title_without_series():
    assert normalize_audiobook_title("Livro Sem Série", "") == "Livro Sem Série"  # noqa: S101


def test_normalize_audiobook_title_removes_repeated_series_prefix():
    assert normalize_audiobook_title("Série Imaginária: Livro Exemplo", "Série Imaginária") == "Livro Exemplo"  # noqa: S101


def test_normalize_audiobook_title_removes_repeated_series_volume_suffix():
    assert (  # noqa: S101
        normalize_audiobook_title(
            "3. Tema Exemplo - Livro Inventado: Coleção Fictícia - Vol. 7",
            "Coleção Fictícia",
            "7",
        )
        == "3. Tema Exemplo - Livro Inventado"
    )


def test_extract_audiobook_series_without_comma():
    assert extract_audiobook_series_from_title("Livro Exemplo: Série Imaginária Livro 2") == ("Livro Exemplo", "Série Imaginária", "2")  # noqa: S101


def test_extract_audiobook_history_series_format():
    assert extract_audiobook_series_from_title("Capítulo Exemplo: História 4 de Série Imaginária") == (  # noqa: S101
        "Capítulo Exemplo",
        "Série Imaginária",
        "4",
    )


def test_extract_audiobook_series_keeps_regular_subtitle():
    assert extract_audiobook_series_from_title("Livro Exemplo: Uma investigação fictícia") == ("Livro Exemplo: Uma investigação fictícia", "", "")  # noqa: S101
