from datetime import datetime
import torf
from torf import Torrent
import random
import math
import os
import re
import cli_ui
import glob
import time
import subprocess
import sys
from src.console import console


def calculate_piece_size(total_size, min_size, max_size, files, meta):
    # Set piece_size_max before calling super().__init__
    if 'max_piece_size' in meta and meta['max_piece_size']:
        try:
            max_piece_size_mib = int(meta['max_piece_size']) * 1024 * 1024  # Convert MiB to bytes
            max_size = min(max_piece_size_mib, torf.Torrent.piece_size_max)
        except ValueError:
            max_size = 134217728  # Fallback to default if conversion fails
    else:
        max_size = 134217728

    file_count = len(files)
    our_min_size = 16384
    our_max_size = max_size
    if meta['debug']:
        console.print(f"Max size: {max_size}")
    piece_size = 4194304  # Start with 4 MiB

    num_pieces = math.ceil(total_size / piece_size)

    # Initial torrent_file_size calculation based on file_count
    pathname_bytes = sum(len(str(file).encode('utf-8')) for file in files)
    if file_count > 1000:
        torrent_file_size = 20 + (num_pieces * 20) + int(pathname_bytes * 71 / 100)
    elif file_count > 500:
        torrent_file_size = 20 + (num_pieces * 20) + int(pathname_bytes * 4 / 5)
    else:
        torrent_file_size = 20 + (num_pieces * 20) + pathname_bytes

    # Adjust the piece size to fit within the constraints
    while not ((750 <= num_pieces <= 2200 or num_pieces < 750 and 40960 <= torrent_file_size <= 250000) and torrent_file_size <= 250000):
        if num_pieces > 1000 and num_pieces < 2000 and torrent_file_size < 250000:
            break
        elif num_pieces < 1500 and torrent_file_size >= 250000:
            piece_size *= 2
            if piece_size > our_max_size:
                piece_size = our_max_size
                break
        elif num_pieces < 750:
            piece_size //= 2
            if piece_size < our_min_size:
                piece_size = our_min_size
                break
            elif 40960 < torrent_file_size < 250000:
                break
        elif num_pieces > 2200:
            piece_size *= 2
            if piece_size > our_max_size:
                piece_size = our_max_size
                break
            elif torrent_file_size < 2048:
                break
        elif torrent_file_size > 250000:
            piece_size *= 2
            if piece_size > our_max_size:
                piece_size = our_max_size
                cli_ui.warning('WARNING: .torrent size will exceed 250 KiB!')
                break

        # Update num_pieces
        num_pieces = math.ceil(total_size / piece_size)

        # Recalculate torrent_file_size based on file_count in each iteration
        if file_count > 1000:
            torrent_file_size = 20 + (num_pieces * 20) + int(pathname_bytes * 71 / 100)
        elif file_count > 500:
            torrent_file_size = 20 + (num_pieces * 20) + int(pathname_bytes * 4 / 5)
        else:
            torrent_file_size = 20 + (num_pieces * 20) + pathname_bytes

    return piece_size


class CustomTorrent(torf.Torrent):
    # Default piece size limits
    torf.Torrent.piece_size_min = 16384  # 16 KiB
    torf.Torrent.piece_size_max = 134217728  # 256 MiB

    def __init__(self, meta, *args, **kwargs):
        # Set meta early to avoid AttributeError
        self._meta = meta
        super().__init__(*args, **kwargs)  # Now safe to call parent constructor
        self.validate_piece_size(meta)  # Validate and set the piece size

    @property
    def piece_size(self):
        return self._piece_size

    @piece_size.setter
    def piece_size(self, value):
        if value is None:
            total_size = self._calculate_total_size()
            value = calculate_piece_size(total_size, self.piece_size_min, self.piece_size_max, self.files, self._meta)
        self._piece_size = value
        self.metainfo['info']['piece length'] = value  # Ensure 'piece length' is set

    def _calculate_total_size(self):
        return sum(file.size for file in self.files)

    def validate_piece_size(self, meta=None):
        if meta is None:
            meta = self._meta  # Use stored meta if not explicitly provided
        if not hasattr(self, '_piece_size') or self._piece_size is None:
            total_size = self._calculate_total_size()
            self.piece_size = calculate_piece_size(total_size, self.piece_size_min, self.piece_size_max, self.files, meta)
        self.metainfo['info']['piece length'] = self.piece_size  # Ensure 'piece length' is set


def create_torrent(meta, path, output_filename):
    if meta['debug']:
        start_time = time.time()

    if meta['isdir']:
        if meta['keep_folder']:
            cli_ui.info('--keep-folder was specified. Using complete folder for torrent creation.')
            path = path
        else:
            os.chdir(path)
            globs = glob.glob1(path, "*.mkv") + glob.glob1(path, "*.mp4") + glob.glob1(path, "*.ts")
            no_sample_globs = [
                os.path.abspath(f"{path}{os.sep}{file}") for file in globs
                if not file.lower().endswith('sample.mkv') or "!sample" in file.lower()
            ]
            if len(no_sample_globs) == 1:
                path = meta['filelist'][0]

    exclude = ["*.*", "*sample.mkv", "!sample*.*"] if not meta['is_disc'] else ""
    include = ["*.mkv", "*.mp4", "*.ts"] if not meta['is_disc'] else ""

    # If using mkbrr, run the external application
    if meta.get('mkbrr'):
        third_party_exe = os.path.join(meta['base_dir'], "bin", "mkbrr", "mkbrr.exe")
        output_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/{output_filename}.torrent"

        if sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
            cmd = ["mono", third_party_exe, "create", path, "-o", output_path]
        else:
            cmd = [third_party_exe, "create", path, "-o", output_path]

        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            total_pieces = 100  # Default to 100% for scaling progress
            pieces_done = 0
            mkbrr_start_time = time.time()

            for line in process.stdout:
                line = line.strip()

                # Detect hashing progress, speed, and percentage
                match = re.search(r"Hashing pieces.*?\[(\d+\.\d+ MB/s)\]\s+(\d+)%", line)
                if match:
                    speed = match.group(1)  # Extract speed (e.g., "12734.21 MB/s")
                    pieces_done = int(match.group(2))  # Extract percentage (e.g., "60")

                    # Estimate ETA (Time Remaining)
                    elapsed_time = time.time() - mkbrr_start_time
                    if pieces_done > 0:
                        estimated_total_time = elapsed_time / (pieces_done / 100)
                        eta_seconds = max(0, estimated_total_time - elapsed_time)
                        eta = time.strftime("%M:%S", time.gmtime(eta_seconds))
                    else:
                        eta = "--:--"  # Placeholder if we can't estimate yet

                    cli_ui.info_progress(f"mkbrr hashing... {speed} | ETA: {eta}", pieces_done, total_pieces)

                # Detect final output line
                if "Wrote" in line and ".torrent" in line:
                    console.print(f"[bold cyan]{line}")  # Print the final torrent file creation message

            process.wait()
            return output_path
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]Error creating torrent: {e.stderr}")
            return None

    # Fallback to CustomTorrent if mkbrr is not used
    torrent = CustomTorrent(
        meta=meta,
        path=path,
        trackers=["https://fake.tracker"],
        source="Audionut UA",
        private=True,
        exclude_globs=exclude or [],
        include_globs=include or [],
        creation_date=datetime.now(),
        comment="Created by Audionut's Upload Assistant",
        created_by="Audionut's Upload Assistant"
    )

    torrent.validate_piece_size(meta)
    torrent.generate(callback=torf_cb, interval=5)
    torrent.write(f"{meta['base_dir']}/tmp/{meta['uuid']}/{output_filename}.torrent", overwrite=True)
    torrent.verify_filesize(path)

    if meta['debug']:
        finish_time = time.time()
        console.print(f"torrent created in {finish_time - start_time:.4f} seconds")

    console.print("[bold green].torrent created", end="\r")
    return torrent


torf_start_time = time.time()


def torf_cb(torrent, filepath, pieces_done, pieces_total):
    global torf_start_time

    if pieces_done == 0:
        torf_start_time = time.time()  # Reset start time when hashing starts

    elapsed_time = time.time() - torf_start_time

    # Calculate percentage done
    if pieces_total > 0:
        percentage_done = (pieces_done / pieces_total) * 100
    else:
        percentage_done = 0

    # Estimate ETA (if at least one piece is done)
    if pieces_done > 0:
        estimated_total_time = elapsed_time / (pieces_done / pieces_total)
        eta_seconds = max(0, estimated_total_time - elapsed_time)
        eta = time.strftime("%M:%S", time.gmtime(eta_seconds))
    else:
        eta = "--:--"

    # Calculate hashing speed (MB/s)
    if elapsed_time > 0 and pieces_done > 0:
        piece_size = torrent.piece_size / (1024 * 1024)
        speed = (pieces_done * piece_size) / elapsed_time
        speed_str = f"{speed:.2f} MB/s"
    else:
        speed_str = "-- MB/s"

    # Display progress with percentage, speed, and ETA
    cli_ui.info_progress(f"Hashing... {speed_str} | ETA: {eta}", int(percentage_done), 100)


def create_random_torrents(base_dir, uuid, num, path):
    manual_name = re.sub(r"[^0-9a-zA-Z\[\]\'\-]+", ".", os.path.basename(path))
    base_torrent = Torrent.read(f"{base_dir}/tmp/{uuid}/BASE.torrent")
    for i in range(1, int(num) + 1):
        new_torrent = base_torrent
        new_torrent.metainfo['info']['entropy'] = random.randint(1, 999999)
        Torrent.copy(new_torrent).write(f"{base_dir}/tmp/{uuid}/[RAND-{i}]{manual_name}.torrent", overwrite=True)


async def create_base_from_existing_torrent(torrentpath, base_dir, uuid):
    if os.path.exists(torrentpath):
        base_torrent = Torrent.read(torrentpath)
        base_torrent.trackers = ['https://fake.tracker']
        base_torrent.comment = "Created by L4G's Upload Assistant"
        base_torrent.created_by = "Created by L4G's Upload Assistant"
        # Remove Un-whitelisted info from torrent
        for each in list(base_torrent.metainfo['info']):
            if each not in ('files', 'length', 'name', 'piece length', 'pieces', 'private', 'source'):
                base_torrent.metainfo['info'].pop(each, None)
        for each in list(base_torrent.metainfo):
            if each not in ('announce', 'comment', 'creation date', 'created by', 'encoding', 'info'):
                base_torrent.metainfo.pop(each, None)
        base_torrent.source = 'L4G'
        base_torrent.private = True
        Torrent.copy(base_torrent).write(f"{base_dir}/tmp/{uuid}/BASE.torrent", overwrite=True)
