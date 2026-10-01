# ruff: noqa: S101

from src.book_prep import clean_translator_from_author, extract_first_author, sanitize_book_author
from src.meta import Meta


def test_initial_e_is_preserved_in_author_name():
    assert clean_translator_from_author("E L Example") == ("E L Example", "")
    assert extract_first_author("E L Example") == "E L Example"

    meta = Meta(author="E L Example", category="BOOK")
    sanitize_book_author(meta)
    assert meta.author == "E L Example"

    underscored = Meta(author="E_L_Example", category="BOOK")
    sanitize_book_author(underscored)
    assert underscored.author == "E_L_Example"


def test_initial_e_survives_manual_translator_removal():
    meta = Meta(author="E L Example e Mara Fiction", book_translator="Mara Fiction", category="BOOK")
    sanitize_book_author(meta)
    assert meta.author == "E L Example"


def test_conjunction_between_authors_still_selects_first():
    meta = Meta(author="Ana Example e Bia Fiction", category="BOOK")
    sanitize_book_author(meta)
    assert meta.author == "Ana Example"
