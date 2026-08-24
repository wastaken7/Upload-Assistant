"""Generate dynamic HDR metadata plots with the official quietvoid tools.

The tools are downloaded lazily, like mkbrr, so a normal upload never needs an
extra dependency.  Dolby Vision and HDR10+ are deliberately kept as separate
plots: their dynamic metadata has different semantics.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from bin.get_dynamic_hdr_tools import TOOLS, get_tool
from src.binaries import configured_binary
from src.console import logger
from src.meta import Meta
from src.temp_paths import dynamic_hdr_plots_dir, release_temp_dir
from src.webui_progress import complete_progress, publish_progress

CACHE_VERSION = 1
VIDEO_EXTENSIONS = {".m2ts", ".mkv", ".mp4", ".ts", ".hevc", ".h265"}


def _positive_config_int(config: dict[str, Any], key: str, default: int) -> int:
    try:
        return max(1, int(config["DEFAULT"].get(key, default)))
    except KeyError, TypeError, ValueError:
        return default


def _source_files(meta: Meta, max_files: int) -> list[Path]:
    if meta.bdinfo:
        files = meta.bdinfo.get("files", [])
        disc_path = meta.bdinfo.get("path", "")
        if files and disc_path and (stream := files[0].get("file")):
            candidate = Path(disc_path) / "STREAM" / stream
            if candidate.is_file():
                return [candidate]
    sources = [Path(file) for file in meta.filelist if Path(file).suffix.lower() in VIDEO_EXTENSIONS and Path(file).is_file()]
    return list(dict.fromkeys(sources))[:max_files]


def _formats(meta: Meta) -> list[str]:
    hdr = str(meta.hdr or "").upper()
    formats: list[str] = []
    if "DV" in hdr or "DOLBY VISION" in hdr:
        formats.append("dovi")
    if "HDR10+" in hdr:
        formats.append("hdr10plus")
    return formats


def _fingerprint(sources: list[Path], formats: list[str]) -> str:
    digest = hashlib.sha256()
    for source in sources:
        info = source.stat()
        digest.update(f"{source.resolve()}:{info.st_size}:{info.st_mtime_ns}".encode())
    digest.update(",".join(formats).encode())
    return digest.hexdigest()


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or f"{' '.join(command[:2])} failed with exit code {result.returncode}")


async def _generate_plot(binary: str, kind: str, source: Path, output_dir: Path, ffmpeg_binary: str = "ffmpeg") -> Path:
    stem = source.stem
    artifact_id = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:12]
    artifact_name = f"{stem}_{artifact_id}"
    output = output_dir / f"dynamic_hdr_{kind}_{artifact_name}.png"
    work_dir = output_dir / ".metadata"
    work_dir.mkdir(exist_ok=True)
    input_source = source
    if source.suffix.lower() in {".m2ts", ".mp4", ".ts"}:
        # The third-party tools accept MKV or elementary HEVC streams. Convert
        # transport streams and MP4 containers with a stream copy, never a re-encode.
        input_source = work_dir / f"{artifact_name}.hevc"
        await asyncio.to_thread(
            _run,
            [ffmpeg_binary, "-y", "-i", str(source), "-map", "0:v:0", "-c:v", "copy", "-bsf:v", "hevc_mp4toannexb", "-f", "hevc", str(input_source)],
        )
    if kind == "dovi":
        rpu = work_dir / f"{artifact_name}.rpu.bin"
        await asyncio.to_thread(_run, [binary, "extract-rpu", str(input_source), "-o", str(rpu)])
        await asyncio.to_thread(_run, [binary, "plot", str(rpu), "-t", f"Dolby Vision L1 Plot - {stem}", "-o", str(output)])
    else:
        metadata = work_dir / f"{artifact_name}.hdr10plus.json"
        await asyncio.to_thread(_run, [binary, "extract", str(input_source), "-o", str(metadata)])
        await asyncio.to_thread(_run, [binary, "plot", str(metadata), "-t", f"HDR10+ Plot - {stem}", "-o", str(output)])
    if not output.is_file():
        raise RuntimeError(f"{TOOLS[kind]['command']} did not create {output.name}")
    return output


def dynamic_hdr_plot_enabled(meta: Meta, config: dict[str, Any]) -> bool:
    """Return whether plots are enabled globally, explicitly, or by an active tracker."""
    if meta.dynamic_hdr_plot or config["DEFAULT"].get("add_dynamic_hdr_plot", False):
        return True

    selected_trackers = meta.trackers
    if isinstance(selected_trackers, str):
        selected_trackers = [selected_trackers]

    tracker_configs = config.get("TRACKERS", {})
    return any(
        isinstance(tracker, str) and isinstance(tracker_configs.get(tracker.upper()), dict) and tracker_configs[tracker.upper()].get("add_dynamic_hdr_plot", False)
        for tracker in selected_trackers
    )


async def process_dynamic_hdr_plots(meta: Meta, config: dict[str, Any], uploadscreens_manager: Any = None) -> list[str]:
    """Generate, cache and upload plots for detected dynamic HDR formats."""
    if meta.dynamic_hdr_plot_images:
        return []
    formats = _formats(meta)
    if not formats:
        logger.info("[cyan]Dynamic HDR plot skipped: no Dolby Vision or HDR10+ metadata detected.[/cyan]")
        return []
    sources = _source_files(meta, _positive_config_int(config, "dynamic_hdr_plot_max_files", 1))
    if not sources:
        logger.warning("[yellow]Dynamic HDR plot skipped: no supported video source found.[/yellow]")
        return []

    output_dir = dynamic_hdr_plots_dir(meta.base_dir, meta.uuid)
    cache_path = release_temp_dir(meta.base_dir, meta.uuid) / "dynamic_hdr_plot_images.json"
    fingerprint = _fingerprint(sources, formats)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if cache.get("cache_version") == CACHE_VERSION and cache.get("fingerprint") == fingerprint and isinstance(cache.get("dynamic_hdr_plot_images"), list):
            meta.dynamic_hdr_plot_images = cache["dynamic_hdr_plot_images"]
            return []
    except OSError, ValueError, TypeError:
        pass

    jobs = [(kind, source) for source in sources for kind in formats]
    logger.info("[yellow]Generating dynamic HDR plots reads each selected video file in full; this may take a while for large releases.[/yellow]")
    progress_id = f"dynamic-hdr-plot-{meta.uuid}"
    publish_progress(progress_id, "Generating dynamic HDR plots", current=0, total=len(jobs), detail="Preparing metadata tools", group="dynamic_hdr", unit="plots")
    tools: dict[str, str] = {}
    ffmpeg_binary = configured_binary("ffmpeg_path", config) or "ffmpeg"
    generated: list[str] = []
    for position, (kind, source) in enumerate(jobs, start=1):
        try:
            if kind not in tools:
                tools[kind] = configured_binary(f"{TOOLS[kind]['command']}_path", config) or await get_tool(meta.base_dir, kind)
            binary = tools[kind]
            plot = await _generate_plot(binary, kind, source, output_dir, ffmpeg_binary)
            generated.append(str(plot))
            detail = f"Generated {kind} plot for {source.name}"
        except Exception as error:
            detail = f"{kind} plot failed for {source.name}: {error!s}"
            logger.warning(f"[yellow]{detail}[/yellow]")
        publish_progress(progress_id, "Generating dynamic HDR plots", current=position, total=len(jobs), detail=detail, group="dynamic_hdr", unit="plots")

    if generated and uploadscreens_manager and not meta.skip_imghost_upload:
        try:
            images, _ = await uploadscreens_manager.upload_screens(meta, len(generated), 1, 0, len(generated), generated, {})
            if images:
                meta.dynamic_hdr_plot_images = images
                cache_path.write_text(json.dumps({"cache_version": CACHE_VERSION, "fingerprint": fingerprint, "dynamic_hdr_plot_images": images}, indent=4), encoding="utf-8")
        except Exception as error:
            logger.error(f"[red]Error uploading dynamic HDR plots: {error!s}[/red]")
    complete_progress(
        progress_id,
        "Dynamic HDR plots generated",
        current=len(generated),
        total=len(jobs),
        detail=f"Generated {len(generated)} of {len(jobs)} plot(s)",
        group="dynamic_hdr",
        unit="plots",
    )
    return generated
