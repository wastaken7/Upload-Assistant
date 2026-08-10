from src.audio_spectrogram import MAX_TIME_BINS, get_spectrogram_sources, get_stft_parameters, prompt_audio_stream_positions, select_audio_streams


def test_prompt_audio_stream_positions_uses_cli_ui_and_defaults_to_all(monkeypatch):
    recorded = {}

    def ask_string(*question, default=None):
        recorded["question"] = question
        recorded["default"] = default
        return

    monkeypatch.setattr("src.audio_spectrogram.cli_ui.ask_string", ask_string)

    assert prompt_audio_stream_positions() == "all"  # noqa: S101
    assert recorded == {"question": ("Select audio stream positions (e.g. 0,1 or all)",), "default": "all"}  # noqa: S101


def test_select_audio_streams_accepts_positions_and_removes_duplicates():
    streams = [{"index": 2}, {"index": 5}, {"index": 9}]

    assert select_audio_streams(streams, "2,0,2") == [streams[2], streams[0]]  # noqa: S101


def test_select_audio_streams_only_accepts_all_for_every_stream():
    streams = [{"index": 2}, {"index": 5}, {"index": 9}]

    assert select_audio_streams(streams, "3") == []  # noqa: S101
    assert select_audio_streams(streams, "all") == streams  # noqa: S101


def test_get_spectrogram_sources_uses_every_music_track_and_applies_limit(tmp_path):
    tracks = [tmp_path / f"track-{number}.flac" for number in range(3)]
    for track in tracks:
        track.touch()

    assert get_spectrogram_sources("MUSIC", [str(track) for track in tracks], None, 2) == tracks[:2]  # noqa: S101


def test_get_spectrogram_sources_only_uses_audio_files_for_audiobooks(tmp_path):
    chapter = tmp_path / "chapter-01.m4b"
    cover = tmp_path / "cover.jpg"
    chapter.touch()
    cover.touch()

    assert get_spectrogram_sources("BOOK", [str(cover), str(chapter)], None, 12) == [chapter]  # noqa: S101


def test_stft_parameters_bound_the_number_of_time_bins_for_long_audio():
    sample_count = 600 * 48000

    n_fft, hop_length = get_stft_parameters(sample_count)

    assert n_fft == 2048  # noqa: S101
    assert sample_count / hop_length <= MAX_TIME_BINS  # noqa: S101
