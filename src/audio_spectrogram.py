# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import hashlib
import io
import json
import subprocess
from pathlib import Path
from typing import Any, cast

import cli_ui

from src.binaries import configured_binary
from src.console import logger
from src.meta import Meta
from src.temp_paths import spectrograms_dir
from src.webui_progress import complete_progress, publish_progress

DURATION_LIMIT = 600
SAMPLE_RATE = 48000
WIDTH_INCH = 16
HEIGHT_INCH = 9
DPI_VALUE = 240
CACHE_VERSION = 2
AUDIOBOOK_EXTENSIONS = {".aac", ".aax", ".flac", ".m4a", ".m4b", ".mp3", ".ogg", ".opus", ".wav", ".wma"}
SPECTROGRAM_N_FFT = 2048
MAX_TIME_BINS = 1024


def prompt_audio_stream_positions() -> str:
    """Ask for stream positions through the prompt API supported by the WebUI."""
    return (
        cli_ui.ask_string(
            "Select audio stream positions (e.g. 0,1 or all)",
            default="all",
        )
        or "all"
    )


def get_audio_streams(file_path: str | Path) -> list[dict[str, Any]]:
    """Return the audio streams reported by ffprobe, or raise a useful error."""
    command = [
        configured_binary("ffprobe_path") or "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=index:stream_tags=language,title",
        "-select_streams",
        "a",
        "-of",
        "json",
        str(file_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Could not run ffprobe: {error}") from error

    if result.returncode:
        detail = result.stderr.strip() or "unknown ffprobe error"
        raise RuntimeError(f"ffprobe could not inspect '{file_path}': {detail}")
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except json.JSONDecodeError as error:
        raise RuntimeError(f"ffprobe returned invalid JSON for '{file_path}'") from error
    return [stream for stream in streams if isinstance(stream, dict)]


def select_audio_streams(streams: list[dict[str, Any]], choice: str) -> list[dict[str, Any]]:
    """Select streams by their displayed, zero-based position; ``all`` selects all."""
    normalized = [item.strip().lower() for item in choice.split(",") if item.strip()]
    if "all" in normalized:
        return streams

    selected: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in normalized:
        if not item.isdigit():
            logger.warning(f"Invalid audio stream selection: {item}. Use zero-based positions or 'all'.")
            continue
        position = int(item)
        if not 0 <= position < len(streams):
            logger.warning(f"Invalid audio stream position: {position}. Available positions: 0-{len(streams) - 1}.")
            continue
        if position not in seen:
            selected.append(streams[position])
            seen.add(position)
    return selected


def _positive_config_int(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get("DEFAULT", {}).get(key, default)
    try:
        value_as_int = int(value)
    except TypeError, ValueError:
        logger.warning(f"[yellow]Invalid {key!r} value {value!r}; using {default}.[/yellow]")
        return default
    if value_as_int <= 0:
        logger.warning(f"[yellow]{key!r} must be positive; using {default}.[/yellow]")
        return default
    return value_as_int


def get_spectrogram_sources(category: str, filelist: list[Any], disc_final_path: Path | None, max_source_files: int) -> list[Path]:
    """Return source files for a release, preserving all music/audiobook chapters."""
    if disc_final_path:
        return [disc_final_path]
    sources = [Path(file_path) for file_path in filelist if Path(file_path).is_file()]
    if category == "BOOK":
        sources = [source for source in sources if source.suffix.lower() in AUDIOBOOK_EXTENSIONS]
    elif category not in ("BOOK", "MUSIC"):
        sources = sources[:1]
    return sources[:max_source_files]


def get_stft_parameters(sample_count: int) -> tuple[int, int]:
    """Bound the matrix plotted by Matplotlib while retaining useful frequency detail."""
    import numpy as np

    n_fft = min(SPECTROGRAM_N_FFT, max(32, 2 ** int(np.floor(np.log2(max(sample_count, 1))))))
    hop_length = max(n_fft // 4, int(np.ceil(sample_count / MAX_TIME_BINS)))
    return n_fft, hop_length


def _cache_fingerprint(audio_sources: list[Path], duration: int, sample_rate: int, stream_indexes: list[tuple[Path, int]]) -> str:
    data: dict[str, object] = {
        "cache_version": CACHE_VERSION,
        "sources": [{"path": str(source.resolve()), "size": source.stat().st_size, "mtime_ns": source.stat().st_mtime_ns} for source in audio_sources],
        "duration": duration,
        "sample_rate": sample_rate,
        "stream_indexes": [{"path": str(source.resolve()), "index": index} for source, index in stream_indexes],
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _load_cached_images(cache_path: Path, fingerprint: str) -> list[Any]:
    if not cache_path.exists():
        return []
    try:
        content = cache_path.read_text(encoding="utf-8")
        cache: dict[str, object] = cast(dict[str, object], json.loads(content)) if content.strip() else {}
        images = cache.get("spectrograms_images")
        if cache.get("fingerprint") == fingerprint and isinstance(images, list):
            return cast(list[Any], images)
    except (OSError, json.JSONDecodeError) as error:
        logger.warning(f"[yellow]Could not load spectrogram image cache: {error!s}[/yellow]")
    return []


def generate_spectrogram(
    stream_index: int,
    stream_label: str,
    stream_lang: str,
    file_path: str | Path,
    output_dir: Path,
    duration: int,
    sample_rate: int,
    source_position: int,
    source_name: str,
) -> Path:
    """Decode one stream and generate a frequency/time image suitable for review."""
    command = [
        configured_binary("ffmpeg_path") or "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(file_path),
        "-map",
        f"0:{stream_index}",
        "-t",
        str(duration),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "wav",
        "pipe:1",
    ]
    try:
        result = subprocess.run(command, capture_output=True, check=False, timeout=duration + 120)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Could not decode audio stream {stream_index}: {error}") from error
    if result.returncode or not result.stdout:
        detail = result.stderr.decode(errors="replace").strip() or "no audio was produced"
        raise RuntimeError(f"FFmpeg could not decode audio stream {stream_index}: {detail}")

    try:
        import librosa
        import librosa.display
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as e:
        raise RuntimeError("Missing required libraries for spectrogram generation. Install librosa and matplotlib.") from e

    try:
        samples, actual_sample_rate = librosa.load(io.BytesIO(result.stdout), sr=None, mono=True)
    except Exception as error:
        raise RuntimeError(f"Could not read decoded audio for stream {stream_index}: {error}") from error
    if samples.size == 0:
        raise RuntimeError(f"Audio stream {stream_index} contains no decodable samples.")

    n_fft, hop_length = get_stft_parameters(samples.size)
    stft = np.abs(librosa.stft(samples, n_fft=n_fft, hop_length=hop_length))
    db_spectrogram = librosa.amplitude_to_db(stft, ref=np.max)  # pyright: ignore[reportUnknownMemberType]  # librosa stub has an untyped callback overload.

    figure, axis = plt.subplots(figsize=(WIDTH_INCH, HEIGHT_INCH), dpi=DPI_VALUE)  # pyright: ignore[reportUnknownMemberType]  # matplotlib stub types **fig_kw as Unknown.
    image = librosa.display.specshow(
        db_spectrogram,
        sr=actual_sample_rate,
        hop_length=hop_length,
        x_axis="time",
        y_axis="hz",
        cmap="inferno",
        ax=axis,
        rasterized=True,
    )
    figure.colorbar(image, ax=axis, format="%+2.0f dB")  # pyright: ignore[reportUnknownMemberType]  # matplotlib stub types **kwargs as Unknown.
    display_label = stream_label if stream_label and stream_label != f"Stream_{stream_index}" else source_name
    axis.set_title(display_label, fontsize=18, fontweight="bold", pad=22)  # pyright: ignore[reportUnknownMemberType]  # matplotlib stub types **kwargs as Unknown.
    axis.text(  # pyright: ignore[reportUnknownMemberType]  # matplotlib stub types **kwargs as Unknown.
        0.5,
        1.01,
        f"File: {source_name}  •  Stream {stream_index}  •  {stream_lang}  •  First {duration}s  •  mono mix @ {actual_sample_rate / 1000:g} kHz",
        transform=axis.transAxes,
        ha="center",
        va="bottom",
        fontsize=10,
    )
    axis.set_xlabel("Time (s)")  # pyright: ignore[reportUnknownMemberType]  # matplotlib stub types **kwargs as Unknown.
    axis.set_ylabel("Frequency (Hz)")  # pyright: ignore[reportUnknownMemberType]  # matplotlib stub types **kwargs as Unknown.

    output_name = output_dir / f"spectrogram_source_{source_position:02d}_stream_{stream_index}.png"
    figure.tight_layout()
    figure.savefig(output_name, dpi=DPI_VALUE, bbox_inches="tight")  # pyright: ignore[reportUnknownMemberType]  # matplotlib stub types **kwargs as Unknown.
    plt.close(figure)
    return output_name


async def process_audio_spectrograms(meta: Meta, config: dict[str, Any], uploadscreens_manager: Any = None) -> list[str]:
    if meta.spectrograms_images:
        return []

    logger.info("[yellow]Generating Audio Spectrograms...[/yellow]")
    output_dir = spectrograms_dir(meta.base_dir, meta.uuid)
    cache_path = Path(meta.base_dir) / "tmp" / meta.uuid / "audio_spectrograms_images.json"

    bdinfo = meta.bdinfo
    disc_final_path: Path | None = None
    if bdinfo:
        disc_path = bdinfo.get("path", "")
        files_list = bdinfo.get("files", [])
        disc_file = files_list[0].get("file", "") if files_list else ""
        if disc_path and disc_file:
            disc_final_path = Path(disc_path) / "STREAM" / disc_file
            logger.debug(f"disc_final_path: {disc_final_path}")

    max_source_files = _positive_config_int(config, "audio_spectrogram_max_files", 12)
    all_audio_sources = get_spectrogram_sources(meta.category, meta.filelist, disc_final_path, max(len(meta.filelist), 1))
    audio_sources = all_audio_sources[:max_source_files]
    if len(all_audio_sources) > max_source_files:
        logger.info(f"[yellow]Limiting audio spectrogram generation to the first {max_source_files} of {len(all_audio_sources)} {meta.category.lower()} audio files.[/yellow]")

    if not audio_sources:
        logger.info("[red]Could not find a valid audio or video file to process spectrograms from.[/red]")
        return []

    source_streams: list[tuple[int, Path, list[dict[str, Any]]]] = []
    for source_position, audio_path in enumerate(audio_sources, start=1):
        try:
            streams = await asyncio.to_thread(get_audio_streams, audio_path)
        except RuntimeError as error:
            logger.error(f"[red]{error}[/red]")
            continue

        if bdinfo and audio_path == disc_final_path:
            bdinfo_audios = bdinfo.get("audio", [])
            for position, stream in enumerate(streams):
                tags = stream.setdefault("tags", {})
                if position < len(bdinfo_audios):
                    if not tags.get("language") or tags.get("language") == "und":
                        tags["language"] = bdinfo_audios[position].get("language", "und")
                    tags.setdefault("title", bdinfo_audios[position].get("codec", "No Title"))
        if streams:
            source_streams.append((source_position, audio_path, streams))

    if not source_streams:
        logger.warning("No audio streams found.")
        return []

    if meta.audio_spectrogram_tracks is not None:
        choice = str(meta.audio_spectrogram_tracks)
    elif meta.unattended or len(source_streams) > 1:
        choice = "all" if config["DEFAULT"].get("process_all_audio_spectrogram", False) else "0"
    else:
        _, first_audio_path, first_streams = source_streams[0]
        logger.info(f"Available audio streams for {first_audio_path.name} (use zero-based positions):")
        for position, stream in enumerate(first_streams):
            tags = stream.get("tags", {})
            logger.info(f"[{position}] FFmpeg stream {stream.get('index')} | Lang: {tags.get('language', 'und')} | Title: {tags.get('title', 'No Title')}")
        choice = prompt_audio_stream_positions()

    selected_jobs: list[tuple[int, Path, dict[str, Any]]] = []
    for source_position, audio_path, streams in source_streams:
        selected_streams = select_audio_streams(streams, choice)
        if not selected_streams:
            logger.warning(f"[yellow]No valid streams selected for {audio_path.name}; skipping it.[/yellow]")
            continue
        selected_jobs.extend((source_position, audio_path, stream) for stream in selected_streams)

    if not selected_jobs:
        logger.warning("[yellow]No valid audio streams were selected.[/yellow]")
        return []

    duration = _positive_config_int(config, "audio_spectrogram_duration", DURATION_LIMIT)
    sample_rate = _positive_config_int(config, "audio_spectrogram_sample_rate", SAMPLE_RATE)
    fingerprint = _cache_fingerprint(audio_sources, duration, sample_rate, [(audio_path, int(stream["index"])) for _, audio_path, stream in selected_jobs])
    cached_images = await asyncio.to_thread(_load_cached_images, cache_path, fingerprint)
    if cached_images:
        meta.spectrograms_images = cached_images
        logger.debug(f"[cyan]Loaded {len(cached_images)} matching cached spectrograms.[/cyan]")
        return []

    generated_files: list[str] = []
    progress_id = f"audio-spectrogram-{meta.uuid}"
    publish_progress(progress_id, "Generating audio spectrograms", current=0, total=len(selected_jobs), detail="Preparing audio streams", group="spectrogram", unit="streams")
    for job_position, (source_position, audio_path, stream) in enumerate(selected_jobs, start=1):
        tags = stream.get("tags", {})
        label = tags.get("title", f"Stream_{stream['index']}")
        language = tags.get("language", "und")
        try:
            file_path = await asyncio.to_thread(
                generate_spectrogram, int(stream["index"]), label, language, audio_path, output_dir, duration, sample_rate, source_position, audio_path.stem
            )
        except RuntimeError as error:
            logger.error(f"[red]{error}[/red]")
            publish_progress(
                progress_id,
                "Generating audio spectrograms",
                current=job_position,
                total=len(selected_jobs),
                detail=f"{audio_path.name}: stream {stream['index']} failed",
                status="failed",
                group="spectrogram",
                unit="streams",
            )
            continue
        generated_files.append(str(file_path))
        publish_progress(
            progress_id,
            "Generating audio spectrograms",
            current=job_position,
            total=len(selected_jobs),
            detail=f"Processed {audio_path.name}: stream {stream['index']}",
            group="spectrogram",
            unit="streams",
        )

    if generated_files and uploadscreens_manager:
        logger.info("[yellow]Uploading Audio Spectrograms...[/yellow]")
        try:
            spec_images, _ = await uploadscreens_manager.upload_screens(meta, len(generated_files), 1, 0, len(generated_files), generated_files, {})
            if spec_images:
                meta.spectrograms_images = spec_images
                cache: dict[str, object] = {"cache_version": CACHE_VERSION, "fingerprint": fingerprint, "spectrograms_images": spec_images}
                await asyncio.to_thread(cache_path.write_text, json.dumps(cache, indent=4), encoding="utf-8")
                logger.debug(f"[cyan]Saved {len(spec_images)} spectrograms to audio_spectrograms_images.json[/cyan]")
        except Exception as error:
            logger.error(f"[red]Error uploading audio spectrograms: {error}[/red]")

    complete_progress(
        progress_id,
        "Audio spectrograms generated",
        current=len(generated_files),
        total=len(selected_jobs),
        detail=f"Generated {len(generated_files)} of {len(selected_jobs)} stream(s)",
        group="spectrogram",
        unit="streams",
    )
    return generated_files
