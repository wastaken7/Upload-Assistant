from datetime import datetime
import torf
from torf import Torrent
import random
import math
import os
import re
import cli_ui
import glob
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
    # Handle directories and file inclusion logic
    if meta['isdir']:
        if meta['keep_folder']:
            cli_ui.info('--keep-folder was specified. Using complete folder for torrent creation.')
            path = path
        else:
            os.chdir(path)
            globs = glob.glob1(path, "*.mkv") + glob.glob1(path, "*.mp4") + glob.glob1(path, "*.ts")
            no_sample_globs = []
            for file in globs:
                if not file.lower().endswith('sample.mkv') or "!sample" in file.lower():
                    no_sample_globs.append(os.path.abspath(f"{path}{os.sep}{file}"))
            if len(no_sample_globs) == 1:
                path = meta['filelist'][0]
    if meta['is_disc']:
        include, exclude = "", ""
    else:
        exclude = ["*.*", "*sample.mkv", "!sample*.*"]
        include = ["*.mkv", "*.mp4", "*.ts"]

    # Create and write the new torrent using the CustomTorrent class
    torrent = CustomTorrent(
        meta=meta,
        path=path,
        trackers=["https://fake.tracker"],
        source="L4G",
        private=True,
        exclude_globs=exclude or [],
        include_globs=include or [],
        creation_date=datetime.now(),
        comment="Created by L4G's Upload Assistant",
        created_by="L4G's Upload Assistant"
    )

    # Ensure piece size is validated before writing
    torrent.validate_piece_size(meta)

    # Generate and write the new torrent
    torrent.generate(callback=torf_cb, interval=5)
    torrent.write(f"{meta['base_dir']}/tmp/{meta['uuid']}/{output_filename}.torrent", overwrite=True)
    torrent.verify_filesize(path)

    console.print("[bold green].torrent created", end="\r")
    return torrent


def torf_cb(torrent, filepath, pieces_done, pieces_total):
    # print(f'{pieces_done/pieces_total*100:3.0f} % done')
    cli_ui.info_progress("Hashing...", pieces_done, pieces_total)


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
