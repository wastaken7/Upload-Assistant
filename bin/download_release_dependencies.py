# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

# URLs for FFmpeg and MediaInfo
WIN_FFMPEG = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
WIN_MEDIAINFO_DLL = "https://mediaarea.net/download/binary/libmediainfo0/24.06/MediaInfo_DLL_24.06_Windows_x64_WithoutInstaller.7z"
WIN_MEDIAINFO_CLI = "https://mediaarea.net/download/binary/mediainfo/24.06/MediaInfo_CLI_24.06_Windows_x64.zip"

LINUX_FFMPEG = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
LINUX_MEDIAINFO_SO = "https://mediaarea.net/download/binary/libmediainfo0/23.04/MediaInfo_DLL_23.04_Lambda_x86_64.zip"
LINUX_MEDIAINFO_CLI = "https://mediaarea.net/download/binary/mediainfo/23.04/MediaInfo_CLI_23.04_Lambda_x86_64.zip"


def download_file(url: str, dest: Path) -> None:
    print(f"Downloading {url} to {dest}...")
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response, open(dest, "wb") as out_file:
        shutil.copyfileobj(response, out_file)
    print("Download completed.")


def _is_safe_extract(name: str, extract_to: Path, size: int, archive_path: Path, max_size: int = 500 * 1024 * 1024) -> bool:
    if os.path.isabs(name) or ".." in name or name.startswith("/"):
        return False
    full_path = os.path.realpath(os.path.join(extract_to, name))
    base_path = os.path.realpath(extract_to)
    if not full_path.startswith(base_path + os.sep) and full_path != base_path:
        return False
    if size > max_size:
        print(f"Warning: Skipping oversized member '{name}' in archive '{archive_path}' ({size} bytes, limit is {max_size} bytes)")
        return False
    return True


def extract_zip(zip_path: Path, extract_to: Path) -> None:
    print(f"Extracting {zip_path}...")
    import stat
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for member in zip_ref.namelist():
            info = zip_ref.getinfo(member)
            perm = info.external_attr >> 16
            if stat.S_ISLNK(perm):
                continue
            try:
                file_size = info.file_size
            except Exception:
                file_size = 0
            if not _is_safe_extract(member, extract_to, file_size, zip_path):
                continue
            zip_ref.extract(member, extract_to)


def extract_tar_xz(tar_path: Path, extract_to: Path) -> None:
    print(f"Extracting {tar_path}...")
    with tarfile.open(tar_path, "r:xz") as tar_ref:
        for member in tar_ref.getmembers():
            if member.islnk() or member.issym():
                continue
            if not _is_safe_extract(member.name, extract_to, member.size, tar_path):
                continue
            tar_ref.extract(member, extract_to)


def extract_7z(archive_path: Path, extract_to: Path) -> None:
    print(f"Extracting {archive_path} using bundled 7-Zip...")
    base_dir = Path(__file__).resolve().parent.parent
    is_windows = sys.platform == "win32"
    if is_windows:
        seven_zip_path = base_dir / "bin" / "7z" / "windows" / "x86_64" / "7zr.exe"
        if not seven_zip_path.exists():
            seven_zip_path = Path(shutil.which("7z") or "7z")
    else:
        # On Linux, GHA runner can have 7z installed, or we use our downloaded 7zz
        seven_zip_path = base_dir / "bin" / "7z" / "linux" / "amd64" / "7zz"
        # If it doesn't exist, try standard system 7z
        if not seven_zip_path.exists():
            seven_zip_path = Path(shutil.which("7z") or "7z")

    if not seven_zip_path.exists() and not shutil.which("7z"):
        raise FileNotFoundError("7-Zip binary not found. Please run download_all_build_binaries.py first.")

    import subprocess
    cmd = [str(seven_zip_path), "x", str(archive_path), f"-o{extract_to}", "-y"]
    subprocess.run(cmd, check=True)


def main() -> None:
    # Setup directories
    base_dir = Path(__file__).resolve().parent.parent
    bin_dir = base_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = base_dir / "tmp_build_downloads"
    temp_dir.mkdir(parents=True, exist_ok=True)

    is_windows = sys.platform == "win32"

    if is_windows:
        # Download FFmpeg for Windows
        ffmpeg_zip = temp_dir / "ffmpeg.zip"
        download_file(WIN_FFMPEG, ffmpeg_zip)
        ffmpeg_extract = temp_dir / "ffmpeg_extracted"
        extract_zip(ffmpeg_zip, ffmpeg_extract)

        # Locate ffmpeg.exe and ffprobe.exe
        for p in ffmpeg_extract.glob("**/ffmpeg.exe"):
            shutil.copy2(p, bin_dir / "ffmpeg.exe")
        for p in ffmpeg_extract.glob("**/ffprobe.exe"):
            shutil.copy2(p, bin_dir / "ffprobe.exe")

        # Download MediaInfo DLL for Windows
        mi_dll_7z = temp_dir / "mediainfo_dll.7z"
        download_file(WIN_MEDIAINFO_DLL, mi_dll_7z)
        mi_dll_extract = temp_dir / "mediainfo_dll_extracted"
        extract_7z(mi_dll_7z, mi_dll_extract)
        for p in mi_dll_extract.glob("**/MediaInfo.dll"):
            shutil.copy2(p, bin_dir / "MediaInfo.dll")

        # Download MediaInfo CLI for Windows
        mi_cli_zip = temp_dir / "mediainfo_cli.zip"
        download_file(WIN_MEDIAINFO_CLI, mi_cli_zip)
        mi_cli_extract = temp_dir / "mediainfo_cli_extracted"
        extract_zip(mi_cli_zip, mi_cli_extract)
        for p in mi_cli_extract.glob("**/MediaInfo.exe"):
            shutil.copy2(p, bin_dir / "MediaInfo.exe")

    else:
        # Download FFmpeg for Linux
        ffmpeg_tar = temp_dir / "ffmpeg.tar.xz"
        download_file(LINUX_FFMPEG, ffmpeg_tar)
        ffmpeg_extract = temp_dir / "ffmpeg_extracted"
        extract_tar_xz(ffmpeg_tar, ffmpeg_extract)

        # Locate ffmpeg and ffprobe
        for p in ffmpeg_extract.glob("**/ffmpeg"):
            shutil.copy2(p, bin_dir / "ffmpeg")
            os.chmod(bin_dir / "ffmpeg", 0o755)
        for p in ffmpeg_extract.glob("**/ffprobe"):
            shutil.copy2(p, bin_dir / "ffprobe")
            os.chmod(bin_dir / "ffprobe", 0o755)

        # Download MediaInfo SO (Lambda build) for Linux
        mi_so_zip = temp_dir / "mediainfo_so.zip"
        download_file(LINUX_MEDIAINFO_SO, mi_so_zip)
        mi_so_extract = temp_dir / "mediainfo_so_extracted"
        extract_zip(mi_so_zip, mi_so_extract)

        # Search for libmediainfo.so or libmediainfo.so.0
        found_so = False
        for p in mi_so_extract.glob("**/libmediainfo.so*"):
            shutil.copy2(p, bin_dir / "libmediainfo.so")
            os.chmod(bin_dir / "libmediainfo.so", 0o755)
            found_so = True
            break
        if not found_so:
            # Fallback search
            for root, _, files in os.walk(mi_so_extract):
                for f in files:
                    if "libmediainfo.so" in f:
                        shutil.copy2(os.path.join(root, f), bin_dir / "libmediainfo.so")
                        os.chmod(bin_dir / "libmediainfo.so", 0o755)
                        break

        # Download MediaInfo CLI for Linux
        mi_cli_zip = temp_dir / "mediainfo_cli.zip"
        download_file(LINUX_MEDIAINFO_CLI, mi_cli_zip)
        mi_cli_extract = temp_dir / "mediainfo_cli_extracted"
        extract_zip(mi_cli_zip, mi_cli_extract)

        found_cli = False
        for p in mi_cli_extract.glob("**/mediainfo"):
            shutil.copy2(p, bin_dir / "mediainfo")
            os.chmod(bin_dir / "mediainfo", 0o755)
            found_cli = True
            break
        if not found_cli:
            for root, _, files in os.walk(mi_cli_extract):
                for f in files:
                    if f == "mediainfo":
                        shutil.copy2(os.path.join(root, f), bin_dir / "mediainfo")
                        os.chmod(bin_dir / "mediainfo", 0o755)
                        break

    # Cleanup temp directory
    shutil.rmtree(temp_dir, ignore_errors=True)
    print("FFmpeg and MediaInfo dependencies downloaded successfully.")


if __name__ == "__main__":
    main()
