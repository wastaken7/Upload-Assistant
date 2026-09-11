# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from __future__ import annotations

import os
import random
from functools import partial
from pathlib import Path
from typing import Any, cast

import awsmfunc as awsmfunc  # pyright: ignore[reportMissingImports] # pyrefly: ignore [missing-import]
import vapoursynth as vs  # pyright: ignore[reportMissingImports] # pyrefly: ignore [missing-import]

from src.console import logger

vs = cast(Any, vs)  # pyright: ignore[reportUnnecessaryCast]
awsmfunc = cast(Any, awsmfunc)  # pyright: ignore[reportUnnecessaryCast]
core: Any = vs.core
DynamicTonemap: Any = awsmfunc.DynamicTonemap
ScreenGen: Any = awsmfunc.ScreenGen
zresize: Any = awsmfunc.zresize

# core.std.LoadPlugin(path="/usr/local/lib/vapoursynth/libffms2.so")
# core.std.LoadPlugin(path="/usr/local/lib/vapoursynth/libsub.so")
# core.std.LoadPlugin(path="/usr/local/lib/vapoursynth/libimwri.so")


def custom_frame_info(clip: Any, options: dict[str, bool], tonemapped: bool = False, *, layout: str = "stacked", position: str = "left") -> Any:
    """Apply the selected labels to each VapourSynth frame."""
    from src.screenshot_overlays import format_timestamp, overlay_lines

    def frame_props(n: int, f: Any, clip: Any) -> Any:
        frame_type = f.props.get("_PictType", "Unknown")
        if isinstance(frame_type, bytes):
            frame_type = frame_type.decode("ascii", errors="replace")
        timestamp = format_timestamp(n * clip.fps_den / clip.fps_num)
        lines = overlay_lines(options, n, str(frame_type), timestamp, tonemapped, layout=layout)
        # The built-in bitmap font expects Windows-1252, including the bullet.
        text = "\n".join(lines).encode("cp1252", errors="replace")
        return core.text.Text(clip, text, alignment=9 if position == "right" else 7) if lines else clip

    return core.std.FrameEval(clip, partial(frame_props, clip=clip), prop_src=clip)


def optimize_images(image: str | Path, config: dict[str, Any]) -> None:
    import platform  # Ensure platform is imported here

    image_path = Path(image)

    if config.get("optimize_images", True) and image_path.exists():
        oxipng: Any | None
        try:
            pyver = platform.python_version_tuple()
            if int(pyver[0]) == 3 and int(pyver[1]) >= 7:
                import oxipng  # pyright: ignore[reportMissingImports] # pyrefly: ignore [missing-import]

                oxipng = oxipng
            else:
                oxipng = None
            if oxipng is None:
                return
            if image_path.stat().st_size >= 16000000:
                oxipng.optimize(image, level=6)
            else:
                oxipng.optimize(image, level=3)
        except Exception as e:
            logger.info(f"Image optimization failed: {e}", extra={"markup": False})
    return


def vs_screengn(
    source: str, encode: str | None = None, num: int = 5, dir: str = ".", config: dict[str, Any] | None = None, overlays_enabled: bool = True
) -> None:
    if config is None:
        config = {"optimize_images": True}  # Default configuration

    screens_file = Path(dir) / "screens.txt"

    # Check if screens.txt already exists and use it if valid
    if Path(screens_file).exists():
        with Path(screens_file).open() as txt:
            frames: list[int] = [int(line.strip()) for line in txt.readlines()]
        if len(frames) == num and all(f >= 0 for f in frames):
            logger.info(f"Using existing frame numbers from {screens_file}", extra={"markup": False})
        else:
            frames = []
    else:
        frames = []

    # Indexing the source using ffms2 or lsmash for m2ts files
    if source.endswith(".m2ts"):
        logger.info(f"Indexing {source} with LSMASHSource... This may take a while.", extra={"markup": False})
        src: Any = core.lsmas.LWLibavSource(source)
    else:
        cachefile = f"{Path(dir).resolve()!s}{os.sep}ffms2.ffms2"
        if not Path(cachefile).exists():
            logger.info(f"Indexing {source} with ffms2... This may take a while.", extra={"markup": False})
        try:
            src = core.ffms2.Source(source, cachefile=cachefile)
        except Exception as e:
            logger.info(f"Error during indexing: {e!s}", extra={"markup": False})
            raise
        if Path(cachefile).exists():
            logger.info(f"Indexing completed and cached at: {cachefile}", extra={"markup": False})
        else:
            logger.info("Indexing did not complete as expected.", extra={"markup": False})

    # Check if encode is provided
    enc: Any | None = None
    if encode:
        if not Path(encode).exists():
            logger.info(f"Encode file {encode} not found. Skipping encode processing.", extra={"markup": False})
            encode = None
        else:
            enc = core.ffms2.Source(encode)

    # Use source length if encode is not provided
    num_frames = len(src)
    start, end = 1000, num_frames - 10000

    # Generate random frame numbers for screenshots if not using existing ones
    if not frames:
        for _ in range(num):
            frames.append(random.randint(start, end))  # nosec B311  # noqa: S311
        frames = sorted(frames)
        frame_lines = [f"{x}\n" for x in frames]

        # Write the frame numbers to a file for reuse
        with Path(screens_file).open("w") as txt:
            txt.writelines(frame_lines)
        logger.info(f"Generated and saved new frame numbers to {screens_file}", extra={"markup": False})

    # If an encode exists and is provided, crop and resize
    if encode and enc is not None and (src.width != enc.width or src.height != enc.height):
        ref: Any = zresize(enc, preset=src.height)
        crop: list[float] = [(src.width - ref.width) / 2, (src.height - ref.height) / 2]
        src = src.std.Crop(left=crop[0], right=crop[0], top=crop[1], bottom=crop[1])
        width: int | None
        height: int | None
        if enc.width / enc.height > 16 / 9:
            width = enc.width
            height = None
        else:
            width = None
            height = enc.height
        src = zresize(src, width=width, height=height)

    # Apply tonemapping if the source is HDR
    tonemapped = False
    frame: Any = src.get_frame(0)
    if frame.props["_Primaries"] == 9:
        tonemapped = True
        src = DynamicTonemap(src, src_fmt=False, libplacebo=True, adjust_gamma=True)
        if encode and enc is not None:
            enc = DynamicTonemap(enc, src_fmt=False, libplacebo=True, adjust_gamma=True)

    from src.screenshot_overlays import overlay_options, overlays_active

    options = overlay_options(config) if overlays_enabled and overlays_active(config) else {}
    layout = str(config.get("overlay_layout", "stacked"))
    position = str(config.get("overlay_position", "left"))
    if any(options.values()):
        src = custom_frame_info(src, options, tonemapped, layout=layout, position=position)

    # Generate screenshots
    ScreenGen(src, dir, "a")
    if encode and enc is not None:
        if any(options.values()):
            enc = custom_frame_info(enc, options, tonemapped, layout=layout, position=position)
        ScreenGen(enc, dir, "b")

    # Optimize images
    for i in range(1, num + 1):
        image_path = Path(dir) / f"{str(i).zfill(2)}a.png"
        optimize_images(image_path, config)
