from src.get_desc import DescriptionBuilder, _clean_description_text, _safe_game_field
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


def test_portuguese_game_description_localizes_language_support_types():
    meta = Meta(category="GAME", languages={"Portuguese (Brazil)": ["&#x49;nterface", "Subtitles", "Audio"]})

    table_description = _builder("pt-BR")._build_game_desc_section(meta)
    plain_description = _builder("pt-BR")._build_game_desc_section(meta, table=False)

    assert "[td]Interface, Legendas, Áudio[/td]" in table_description  # noqa: S101
    assert "[b]Portuguese (Brazil)[/b]: Interface, Legendas, Áudio" in plain_description  # noqa: S101
    assert "&#x49;nterface" not in table_description  # noqa: S101


def test_english_game_description_preserves_language_support_types():
    meta = Meta(category="GAME", languages={"English": ["Interface", "Subtitles", "Audio"]})

    description = _builder()._build_game_desc_section(meta)

    assert "[td]Interface, Subtitles, Audio[/td]" in description  # noqa: S101


def test_description_builders_use_h2_for_trackers_with_legacy_header_formats():
    book_meta = Meta(category="BOOK", author="Author")
    game_meta = Meta(category="GAME", platform="PC")
    music_meta = Meta(category="MUSIC", music_release={"fields": {"album": {"value": "Album"}}})

    for tracker in ("TORRENTLEECH", "IMMORTALSEED", "IPTORRENTS", "SPEEDAPP", "BJSHARE", "BRASILTRACKER"):
        builder = DescriptionBuilder(tracker, {"DEFAULT": {}, "TRACKERS": {tracker: {}}})

        assert "[h2]" in builder._build_book_desc_section(book_meta)  # noqa: S101
        assert "[h2]" in builder._build_game_desc_section(game_meta)  # noqa: S101
        assert "[h2]" in builder._build_music_desc_section(music_meta)  # noqa: S101


def test_game_description_ignores_invalid_provider_links():
    meta = Meta(category="GAME", game_official_url="javascript:alert(1)", youtube="not-a-url", game_ratings={"Bad": {"score": 5, "max": 10, "url": "javascript:alert(1)"}})

    description = _builder()._build_game_desc_section(meta)

    assert "javascript:" not in description  # noqa: S101
    assert "Official Website" not in description  # noqa: S101
    assert "5/10" in description  # noqa: S101


def test_safe_game_field_strips_html_after_decoding_entities():
    value = "&lt;img src=x onerror=alert(1)&gt;Safe"

    assert _safe_game_field(value) == "Safe"  # noqa: S101


def test_clean_description_text_removes_serialization_escapes():
    value = r'\"It did not take long to make this journey.\" Extracted from the book \/My formation\/'

    assert _clean_description_text(value) == '"It did not take long to make this journey." Extracted from the book /My formation/'  # noqa: S101


def test_clean_description_text_decodes_json_string_literals():
    value = '"A description with \\"quotes\\" and a \\/slash"'

    assert _clean_description_text(value) == 'A description with "quotes" and a /slash'  # noqa: S101


def test_clean_description_text_preserves_entity_encoded_quotes():
    value = '&quot;The title&quot; is shown in the overview.'

    assert _clean_description_text(value) == '"The title" is shown in the overview.'  # noqa: S101


def test_game_description_cleans_escaped_overview():
    meta = Meta(category="GAME", overview=r'\"A story \/with quotes\"')

    description = _builder()._build_game_desc_section(meta)

    assert '"A story /with quotes"' in description  # noqa: S101
    assert r'\"' not in description  # noqa: S101


def test_game_requirements_render_steam_english_data_in_three_columns():
    meta = Meta(
        category="GAME",
        requirements_minimum=(
            '<strong>Minimum:</strong><br><ul class="bb_ul">'
            "<li><strong>OS *:</strong> Windows 7/8/10 64bit<br></li>"
            "<li><strong>Processor:</strong> Intel i3+<br></li>"
            "<li><strong>Memory:</strong> 4 GB RAM<br></li>"
            "<li><strong>Graphics:</strong> Nvidia GeForce GTX 750<br></li>"
            "<li><strong>DirectX:</strong> Version 10<br></li>"
            "<li><strong>Storage:</strong> 8 GB available space<br></li>"
            "<li><strong>Sound Card:</strong> 100% DirectX 9.0c compatible sound card</li></ul>"
        ),
        requirements_recommended=(
            '<strong>Recommended:</strong><br><ul class="bb_ul">'
            "<li><strong>OS *:</strong> Windows 7/8/10 64bit<br></li>"
            "<li><strong>Processor:</strong> Intel i5+<br></li>"
            "<li><strong>Memory:</strong> 8 GB RAM<br></li>"
            "<li><strong>Graphics:</strong> Nvidia GeForce GTX 1050<br></li>"
            "<li><strong>DirectX:</strong> Version 10<br></li>"
            "<li><strong>Storage:</strong> 8 GB available space<br></li>"
            "<li><strong>Sound Card:</strong> 100% DirectX 9.0c compatible sound card</li></ul>"
        ),
    )

    description = _builder()._build_game_desc_section(meta)

    assert "[tr][td][b]Hardware[/b][/td][td][b]Minimum[/b][/td][td][b]Recommended[/b][/td][/tr]" in description  # noqa: S101
    assert "[tr][td][b]OS[/b][/td][td]Windows 7/8/10 64bit[/td][td]Windows 7/8/10 64bit[/td][/tr]" in description  # noqa: S101
    assert "[tr][td][b]Memory[/b][/td][td]4 GB RAM[/td][td]8 GB RAM[/td][/tr]" in description  # noqa: S101
    assert "[tr][td][b]Graphics[/b][/td][td]Nvidia GeForce GTX 750[/td][td]Nvidia GeForce GTX 1050[/td][/tr]" in description  # noqa: S101
    assert "[b]Minimum:[/b]" not in description  # noqa: S101


def test_game_requirements_render_steam_portuguese_data_in_three_columns():
    meta = Meta(
        category="GAME",
        requirements_minimum=(
            '<strong>Mínimos:</strong><br><ul class="bb_ul">'
            "<li><strong>SO *:</strong> Windows 7/8/10 64bit</li>"
            "<li><strong>Processador:</strong> Intel i3+</li>"
            "<li><strong>Memória:</strong> 4 GB de RAM</li>"
            "<li><strong>Placa de vídeo:</strong> Nvidia GeForce GTX 750</li>"
            "<li><strong>DirectX:</strong> Versão 10</li>"
            "<li><strong>Armazenamento:</strong> 8 GB de espaço disponível</li>"
            "<li><strong>Placa de som:</strong> 100% DirectX 9.0c compatible sound card</li></ul>"
        ),
        requirements_recommended=(
            '<strong>Recomendados:</strong><br><ul class="bb_ul">'
            "<li><strong>SO *:</strong> Windows 7/8/10 64bit</li>"
            "<li><strong>Processador:</strong> Intel i5+</li>"
            "<li><strong>Memória:</strong> 8 GB de RAM</li>"
            "<li><strong>Placa de vídeo:</strong> Nvidia GeForce GTX 1050</li>"
            "<li><strong>DirectX:</strong> Versão 10</li>"
            "<li><strong>Armazenamento:</strong> 8 GB de espaço disponível</li>"
            "<li><strong>Placa de som:</strong> 100% DirectX 9.0c compatible sound card</li></ul>"
        ),
    )

    description = _builder("pt-BR")._build_game_desc_section(meta)

    assert "[tr][td][b]Hardware[/b][/td][td][b]Mínimo[/b][/td][td][b]Recomendado[/b][/td][/tr]" in description  # noqa: S101
    assert "[tr][td][b]SO[/b][/td][td]Windows 7/8/10 64bit[/td][td]Windows 7/8/10 64bit[/td][/tr]" in description  # noqa: S101
    assert "[tr][td][b]Processador[/b][/td][td]Intel i3+[/td][td]Intel i5+[/td][/tr]" in description  # noqa: S101
    assert "[tr][td][b]Placa de vídeo[/b][/td][td]Nvidia GeForce GTX 750[/td][td]Nvidia GeForce GTX 1050[/td][/tr]" in description  # noqa: S101
