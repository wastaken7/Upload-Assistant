"""Independently updatable version and integrity pins for managed binaries."""

from dataclasses import dataclass
from pathlib import Path

from bin.binary_dependency_pins import bdinfo, dovi_tool, ffmpeg, hdr10plus_tool, mkbrr, nyuu, par2, pesto, seven_zip


@dataclass(frozen=True)
class BinaryDependencyPin:
    version: str
    repository: str
    checksums: dict[str, str]
    path: Path


def _pin(module_path: str | None, version: str, repository: str, checksums: dict[str, str]) -> BinaryDependencyPin:
    if module_path is None:
        raise RuntimeError(f"Cannot update binary dependency pins without a source file for {repository}")
    return BinaryDependencyPin(version, repository, checksums, Path(module_path))


PINS = {
    "7zip": _pin(seven_zip.__file__, seven_zip.VERSION, seven_zip.REPOSITORY, seven_zip.SHA256_BY_ASSET),
    "bdinfo": _pin(bdinfo.__file__, bdinfo.VERSION, bdinfo.REPOSITORY, bdinfo.SHA256_BY_ASSET),
    "dovi_tool": _pin(dovi_tool.__file__, dovi_tool.VERSION, dovi_tool.REPOSITORY, dovi_tool.SHA256_BY_ASSET),
    "ffmpeg": _pin(ffmpeg.__file__, ffmpeg.VERSION, ffmpeg.REPOSITORY, ffmpeg.SHA256_BY_ASSET),
    "hdr10plus_tool": _pin(hdr10plus_tool.__file__, hdr10plus_tool.VERSION, hdr10plus_tool.REPOSITORY, hdr10plus_tool.SHA256_BY_ASSET),
    "mkbrr": _pin(mkbrr.__file__, mkbrr.VERSION, mkbrr.REPOSITORY, mkbrr.SHA256_BY_ASSET),
    "nyuu": _pin(nyuu.__file__, nyuu.VERSION, nyuu.REPOSITORY, nyuu.SHA256_BY_ASSET),
    "par2": _pin(par2.__file__, par2.VERSION, par2.REPOSITORY, par2.SHA256_BY_ASSET),
    "pesto": _pin(pesto.__file__, pesto.VERSION, pesto.REPOSITORY, pesto.SHA256_BY_ASSET),
}
