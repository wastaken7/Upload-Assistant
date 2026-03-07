import io
import json
import os
import subprocess
from typing import Any, cast

import aiofiles
import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
from rich.prompt import Prompt

from src.console import console

DURATION_LIMIT = 600
WIDTH_INCH = 16
HEIGHT_INCH = 9
DPI_VALUE = 240

def get_audio_streams(file_path):
    """
    Uses ffprobe to list all audio streams in the MKV file.
    """
    command = [
        'ffprobe', '-v', 'error', '-show_entries',
        'stream=index:stream_tags=language,title',
        '-select_streams', 'a', '-of', 'json', file_path
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    return json.loads(result.stdout).get('streams', [])

def generate_spectrogram(stream_index, stream_label, stream_lang, file_path, output_dir):
    """
    Extracts specific stream and generates the spectrogram plot.
    """
    console.print(f"--- Processing Stream {stream_index} ({stream_label}) [{stream_lang}] ---")

    # FFmpeg command to extract specific audio stream to pipe
    command = [
        'ffmpeg', '-y', '-i', file_path,
        '-map', f'0:{stream_index}',
        '-t', str(DURATION_LIMIT),
        '-f', 'wav', '-ac', '1', '-ar', '22050', 'pipe:1'
    ]

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = process.communicate()

    # Load into librosa
    y, sr = librosa.load(io.BytesIO(stdout), sr=22050)
    stft = np.abs(librosa.stft(y))
    db_spectrogram = librosa.amplitude_to_db(stft, ref=np.max)

    # Plotting
    plt.figure(figsize=(WIDTH_INCH, HEIGHT_INCH), dpi=DPI_VALUE)
    img = librosa.display.specshow(db_spectrogram, sr=sr, x_axis='time', y_axis='hz', cmap='inferno')

    plt.colorbar(img, format='%+2.0f dB')
    plt.title(f"Spectrogram - Index: {stream_index} | Lang: {stream_lang} | Label: {stream_label} | First {DURATION_LIMIT}s", fontsize=22, pad=20)
    plt.xlabel('Time (s)', fontsize=14)
    plt.ylabel('Frequency (Hz)', fontsize=14)

    output_name = os.path.join(output_dir, f"spectrogram_stream_{stream_index}.png")
    plt.tight_layout()
    plt.savefig(output_name, dpi=DPI_VALUE, bbox_inches='tight')
    plt.close() # Free memory
    console.print(f"Saved: {output_name}")
    return output_name


async def process_audio_spectrograms(meta: dict[str, Any], config: dict[str, Any], uploadscreens_manager: Any = None) -> list[str]:
    audio_spectrograms_images = f"{meta['base_dir']}/tmp/{meta['uuid']}/audio_spectrograms_images.json"
    if os.path.exists(audio_spectrograms_images):
        try:
            async with aiofiles.open(audio_spectrograms_images, encoding="utf-8") as spec_file:
                content = await spec_file.read()
                spectrograms_image_file = cast(dict[str, Any], json.loads(content)) if content.strip() else {}

                if "spectrograms_images" in spectrograms_image_file and not meta.get("spectrograms_images"):
                    meta["spectrograms_images"] = spectrograms_image_file["spectrograms_images"]
                    if meta.get("debug"):
                        console.print(f"[cyan]Loaded {len(spectrograms_image_file['spectrograms_images'])} previously saved spectrograms")

        except Exception as e:
            console.print(f"[yellow]Could not load spectrograms image data: {str(e)}")

    if meta.get("spectrograms_images"):
        return []

    console.print("[yellow]Generating Audio Spectrograms...[/yellow]")

    output_dir = os.path.join(meta.get("base_dir", ""), "tmp", str(meta.get("uuid", "")), "spectrograms")
    os.makedirs(output_dir, exist_ok=True)

    disc_final_path = ""
    bdinfo = meta.get("bdinfo", {})
    if bdinfo:
        disc_path = bdinfo.get("path", "")
        files_list = bdinfo.get("files", [])
        disc_file = files_list[0].get("file", "") if files_list else ""
        disc_final_path = os.path.join(disc_path, "STREAM", disc_file) if disc_path and disc_file else ""
        if meta.get("debug"):
            console.print(f"disc_final_path: {disc_final_path}")

    mkv_path = ""
    filelist = meta.get("filelist", [])
    if filelist:
        mkv_path = filelist[0]

    audio_path = disc_final_path if disc_final_path else mkv_path

    generated_files = []

    if not audio_path or not os.path.exists(audio_path):
        console.print("[red]Could not find a valid audio or video file to process spectrograms from.[/red]")
        return generated_files

    streams = get_audio_streams(audio_path)

    if bdinfo and audio_path == disc_final_path:
        bdinfo_audios = bdinfo.get("audio", [])
        for i, s in enumerate(streams):
            if i < len(bdinfo_audios):
                if "tags" not in s:
                    s["tags"] = {}
                if not s["tags"].get("language") or s["tags"].get("language") == "und":
                    s["tags"]["language"] = bdinfo_audios[i].get("language", "und")
                s["tags"]["title"] = bdinfo_audios[i].get("codec", "No Title")

    if not streams:
        console.print("No audio streams found.")
    else:
        console.print("\nAvailable Audio Streams:")
        for i, s in enumerate(streams):
            lang = s.get('tags', {}).get('language', 'und')
            title = s.get('tags', {}).get('title', 'No Title')
            console.print(f"[{i}] Lang: {lang} | Title: {title}")

        unattended = meta.get("unattended", False)

        if unattended:
            choice = "all" if config["DEFAULT"].get("process_all_audio_spectrogram", False) else "0"
            console.print(f"[yellow]Unattended mode. Automatically selected option: {choice}[/yellow]")
        else:
            choice = Prompt.ask(
                "\nSelect the stream index to scan (comma-separated list e.g. [bold yellow]0,1,2[/bold yellow] or [bold yellow]all[/bold yellow])", default="all"
            )

        choices = [c.strip().lower() for c in choice.split(",")]

        if "all" in choices or str(len(streams)) in choices:
            # Scan all
            for s in streams:
                label = s.get("tags", {}).get("title", f"Stream_{s['index']}")
                lang = s.get("tags", {}).get("language", "und")
                filepath = generate_spectrogram(s["index"], label, lang, audio_path, output_dir)
                generated_files.append(filepath)
        else:
            # Scan selected
            for c in choices:
                if c.isdigit():
                    idx = int(c)
                    if 0 <= idx < len(streams):
                        target = streams[idx]
                        label = target.get("tags", {}).get("title", f"Stream_{target['index']}")
                        lang = target.get("tags", {}).get("language", "und")
                        filepath = generate_spectrogram(target["index"], label, lang, audio_path, output_dir)
                        generated_files.append(filepath)
                    else:
                        console.print(f"Invalid index: {idx}")
                else:
                    console.print(f"Invalid input: {c}")

        if generated_files and uploadscreens_manager:
            console.print("[yellow]Uploading Audio Spectrograms...[/yellow]")
            try:
                spec_images, _ = await uploadscreens_manager.upload_screens(meta, len(generated_files), 1, 0, len(generated_files), generated_files, {})
                if spec_images:
                    meta["spectrograms_images"] = spec_images
                    try:
                        spectrograms_image_file_dict = {"spectrograms_images": spec_images}
                        async with aiofiles.open(audio_spectrograms_images, "w", encoding="utf-8") as spec_file:
                            await spec_file.write(json.dumps(spectrograms_image_file_dict, indent=4))
                        if meta.get("debug"):
                            console.print(f"[cyan]Saved {len(spec_images)} spectrograms to audio_spectrograms_images.json")
                    except Exception as e:
                        console.print(f"[yellow]Failed to save spectrograms image data: {str(e)}")
            except Exception as e:
                console.print(f"[red]Error uploading audio spectrograms: {e}[/red]")

    return generated_files
