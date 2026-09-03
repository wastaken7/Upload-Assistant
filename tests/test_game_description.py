from src.get_desc import DescriptionBuilder, _safe_game_field
from src.meta import Meta


def _builder(language="en"):
    return DescriptionBuilder("TEST", {"DEFAULT": {}, "TRACKERS": {"TEST": {}}}, language=language)


def _rich_meta():
    return Meta(
        category="GAME",
        platform="PC",
        igdb_first_release_date="11/11/2011",
        game_version="v1.6",
        game_region="World",
        game_release_edition="Anniversary Edition",
        game_release_edition_year=2021,
        game_release_type="Full ISO",
        game_release_scene=True,
        genres=["Action RPG"],
        game_age_ratings={"ESRB": "M"},
        game_franchises=["The Elder Scrolls"],
        game_engines=["Creation Engine"],
        game_modes=["Single player"],
        game_player_perspectives=["First person", "Third person"],
        game_themes=["Fantasy"],
        game_features=["Controller Support"],
        developer="Bethesda Game Studios",
        publisher="Bethesda Softworks",
        game_designers=["Designer"],
        game_composers=["Composer"],
        steam_url="https://store.steampowered.com/app/72850/",
        game_official_url="https://example.com/game",
        youtube="https://www.youtube.com/watch?v=abc123",
        overview="A fantasy role-playing game.",
        game_ratings={"Metacritic": {"score": 94.0, "max": 100, "url": "https://example.com/review"}, "IGDB Users": {"score": 88.5, "max": 100, "count": 1234}},
        game_multiplayer_modes={"PC": ["Online co-op (up to 4)", "Split-screen"]},
        game_time_to_beat={"hastily": 3600, "normally": 5400, "completely": 7200},
        requirements_minimum="Minimum specs",
        requirements_recommended="Recommended specs",
        languages={"English": ["Audio", "Subtitles"]},
        game_release_notes="This must never be rendered.",
    )


def test_rich_game_description_renders_curated_sections_only():
    description = _builder()._build_game_desc_section(_rich_meta())

    assert "Release Date" in description  # noqa: S101
    assert "Anniversary Edition (2021)" in description  # noqa: S101
    assert "ESRB: M" in description  # noqa: S101
    assert "Creation Engine" in description  # noqa: S101
    assert "[url=https://example.com/review]94/100[/url]" in description  # noqa: S101
    assert "1,234 votes" in description  # noqa: S101
    assert "Online co-op (up to 4)" in description  # noqa: S101
    assert "1h 30m" in description  # noqa: S101
    assert "This must never be rendered" not in description  # noqa: S101


def test_portuguese_plain_game_description_localizes_new_labels():
    description = _builder("pt-BR")._build_game_desc_section(_rich_meta(), table=False)

    assert "Data de Lançamento" in description  # noqa: S101
    assert "Classificação Etária" in description  # noqa: S101
    assert "Lançamento Scene[/b] Sim" in description  # noqa: S101
    assert "Tempo para Concluir" in description  # noqa: S101
    assert "História Principal" in description  # noqa: S101


def test_game_description_ignores_invalid_provider_links():
    meta = Meta(category="GAME", game_official_url="javascript:alert(1)", youtube="not-a-url", game_ratings={"Bad": {"score": 5, "max": 10, "url": "javascript:alert(1)"}})

    description = _builder()._build_game_desc_section(meta)

    assert "javascript:" not in description  # noqa: S101
    assert "Official Website" not in description  # noqa: S101
    assert "5/10" in description  # noqa: S101


def test_safe_game_field_strips_html_after_decoding_entities():
    value = "&lt;img src=x onerror=alert(1)&gt;Safe"

    assert _safe_game_field(value) == "Safe"  # noqa: S101
