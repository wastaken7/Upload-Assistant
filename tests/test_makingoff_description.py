from src.trackers.makingoff import MakingOff


def test_build_bbcode_uses_current_movie_template_and_dynamic_tabs():
    tracker = MakingOff({"TRACKERS": {"MAKINGOFF": {}}})

    description = tracker._build_bbcode(
        title_br="Título Brasileiro",
        title_orig="Original Title",
        release="Original Title 2026 BluRay 1080p",
        poster_url="https://images.example/poster.jpg",
        overview="Sinopse do filme.",
        image_urls=[f"https://images.example/{index}.jpg" for index in range(1, 10)],
        cast_text="Pessoa Um, Pessoa Dois",
        genres="Ficção Científica, Mistério",
        directors="José da Silva",
        duration="110",
        year="2026",
        countries="Estados Unidos, Canadá",
        audio="Inglês",
        subs="Anexas",
        imdb_url="https://www.imdb.com/title/tt1234567/",
        homepage_url="https://movie.example",
        quality="BDRip",
        container="MKV",
        video_codec="H.264",
        video_brate="10000",
        audio_codec="E-AC-3",
        audio_brate="640",
        res_str="1920x1038",
        aspect="Widescreen (16x9)",
        fps_str="23.976 FPS",
        filesize="8.24 GB",
        crew_text="[B]Direção:[/B] José da Silva",
        audio_channels="5.1",
        tmdb_id="1234",
        youtube_url="https://www.youtube.com/watch?v=Trailer123",
        awards="2 indicações",
        critic="Uma crítica.",
    )

    assert description.startswith("[FILME]\n[PRINCIPAL]\n[DADOS]")  # noqa: S101
    assert description.endswith("[/TABS]\n[/FILME]")  # noqa: S101
    assert "[TITULOBR]Título Brasileiro[/TITULOBR] ([ANO]2026[/ANO])" in description  # noqa: S101
    assert "[DIRECAO][TAG=jose-da-silva]José da Silva[/TAG][/DIRECAO]" in description  # noqa: S101
    assert "[PAIS][TAG=estados-unidos]Estados Unidos[/TAG], [TAG=canada]Canadá[/TAG][/PAIS]" in description  # noqa: S101
    assert "[FORMATO]BDRip[/FORMATO] · [CONTAINER]MKV[/CONTAINER]" in description  # noqa: S101
    assert "[QUALIDADE]FHD · 1080p[/QUALIDADE]" in description  # noqa: S101
    assert "[RESOLUCAO]1920\u00d71038[/RESOLUCAO]" in description  # noqa: S101
    assert '[LEGENDAS="pt-BR"]Anexas[/LEGENDAS]' in description  # noqa: S101
    assert "[TABATIVA=id-screenshots]Screenshots[/TABATIVA]" in description  # noqa: S101
    assert "[TAB=id-trailer]Trailer[/TAB]" in description  # noqa: S101
    assert "[TAB=id-equipe]Equipe[/TAB]" in description  # noqa: S101
    assert "[TAB=id-elenco]Elenco[/TAB]" in description  # noqa: S101
    assert "[TAB=id-premiacoes]Premiações[/TAB]" in description  # noqa: S101
    assert "[TAB=id-critica]Crítica[/TAB]" in description  # noqa: S101
    assert "[TAB=id-extras]Extras[/TAB]" in description  # noqa: S101
    assert "[TAB=id-mediainfo]MediaInfo[/TAB]" in description  # noqa: S101
    assert description.count("[SCREENSHOT][IMG]") == 8  # noqa: S101
    assert "tablePrinc" not in description  # noqa: S101


def test_current_generator_value_normalization():
    tracker = MakingOff({"TRACKERS": {"MAKINGOFF": {}}})

    assert tracker._resolution_quality("3840x2160") == "4K · 2160p"  # noqa: S101
    assert tracker._audio_channels({"Channel(s)": "6 channels"}) == "5.1"  # noqa: S101
    assert tracker._normalize_codec("E-AC-3", tracker.AUDIO_CODEC_MAP) == "E-AC-3"  # noqa: S101
