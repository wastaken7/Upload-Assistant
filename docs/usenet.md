# Usenet Upload Guide

Upload Assistant supports uploading files directly to Usenet (via NNTP) and generating standard NZB files. It manages the entire preparation process, including archiving/splitting files, creating parity recovery records, and posting them anonymously.

---

## 1. Prerequisites & Dependencies

To upload to Usenet, the assistant relies on the following external command-line utilities. These must be installed and available in your system's PATH, or their paths must be specified in `config.py`:

1. **7-Zip (`7z`)**: Used to split large files/folders into multiple uncompressed archives (`.7z.001`, `.7z.002`, etc.) to stay within Usenet posting limits.
2. **PAR2 (`par2`)**: Used to create Parity Volume Set archives (`.par2`). These files allow down loaders to repair any corrupted blocks/articles.
3. **Nyuu (`nyuu`)**: A high-performance Usenet posting tool that handles NNTP uploading and generates the final `.nzb` index file.

---

## 2. Upload Workflow

When Usenet uploading is triggered, Upload Assistant executes the following sequence:

1. **Binary Check**: Validates that `7z`, `par2`, and `nyuu` are installed and executable.
2. **Archiving / Splitting**:
   - If the input is a directory, if a volume size is defined, or if `archive_password` is enabled, it runs `7z` with store-only compression (`-mx=0` to save CPU resources) to archive/split the files.
   - If `archive_password` is configured, it adds `-p{password}` and `-mhe=on` to encrypt the archive and its headers (hiding file names inside the archive).
   - If the input is a single file and no volume size/password is specified, it bypasses the archiving step and copies/links the file directly.
3. **Parity File Generation**: Runs `par2` to generate recovery blocks protecting all target files. The redundancy level is controlled by configuration.
4. **Anonymity & Security Enhancements**:
   - **Obfuscated Filenames**: If `archive_password` is active, the generated `.7z` volumes and `.par2` files are named using a random 32-character hexadecimal string to keep files completely anonymous on Usenet.
   - **Poster/From Header**: Generates a randomized realistic poster name and email (e.g., `Delta Seed <delta456@anon.org>`) to keep uploads anonymous.
   - **Obfuscated Subject**: Generates a random 32-character hexadecimal string as the Usenet post subject line to protect the privacy of the post.
5. **Posting**: Uploads all prepared files (volumes and parity files) to the specified newsgroup using `nyuu` via NNTP.
6. **NZB Password Injection**: If `archive_password` is enabled, the password is automatically injected inside the `<head>` tag of the generated `.nzb` file using `<meta type="password">your_password</meta>`. This allows downloader clients (like SABnzbd) to automatically decrypt the files.
7. **Indexer Safeguard Validation**: Before uploading the NZB to each configured indexer, the script verifies that the NZB has the password metadata tag if encryption is active. If the tag is missing, the upload is aborted for safety.
8. **Cleanup**: Automatically deletes the temporary 7z volumes and PAR2 files from the disk upon successful upload.
9. **NZB Relocation**: Moves the resulting `.nzb` file to your configured output directory.

---

## 3. Configuration Options

To enable Usenet uploads, add the `USENET` section to your `config.py`. Here are the supported configuration fields:

```python
config = {
    # ... other configuration sections ...
    "USENET": {
        # General toggles
        "enabled": True,  # Enable or disable the Usenet pipeline
        # NNTP Server Details (Required if Usenet is active)
        "host": "news.yourprovider.com",  # Usenet server address
        "port": 563,  # Port (usually 563 for SSL/TLS, 119 for non-SSL)
        "username": "your_username",  # Usenet account username
        "password": "your_password",  # Usenet account password
        "newsgroups": "alt.binaries.test",  # Target newsgroup(s) to post to
        # Connections & SSL
        "ssl": True,  # Enable SSL/TLS encryption (highly recommended)
        "connections": 20,  # Number of simultaneous NNTP upload connections
        # Anonymity & Privacy
        "random_poster": True,  # Generate randomized poster name/email (default: True)
        "poster": "Uploader <up@anon.org>",  # Custom poster to use if random_poster is False
        "obscure_subject": True,  # Use a randomized hex string for the post subject (default: True)
        # Archiving & Parity & Encryption
        "rar_volume_size": "auto",  # Volume size (e.g. "100m", "500m", "1g", or "auto" for dynamic sizing)
        "archive_password": "random",  # Password for 7z archive. "random" (default/recommended) generates a unique random password,
        # a specific string (e.g. "mypass") uses a static password, and None/"" disables encryption.
        "par2_percentage": 10,  # PAR2 redundancy percentage (default: 10)
        # Binary Paths (Optional if available in system PATH)
        "7z_path": "7z",  # Custom path to 7z executable
        "par2_path": "par2",  # Custom path to par2 executable
        "nyuu_path": "nyuu",  # Custom path to nyuu executable
        # Staging & Output Directories
        "nzb_output_dir": "/path/to/nzbs",  # Directory to save the completed .nzb file
        "usenet_tmp_dir": "/path/to/staging",  # Staging directory for temporary files during upload
    }
}
```

### Dynamic Volume Size Mapping (`auto`)

When `"rar_volume_size"` is set to `"auto"`, the assistant dynamically selects the volume size based on the total payload size:

- **Payload < 2 GB**: `100m` volumes
- **Payload < 10 GB**: `200m` volumes
- **Payload < 50 GB**: `500m` volumes
- **Payload ≥ 50 GB**: `1g` volumes

---

## 4. CLI Arguments

You can control Usenet uploads directly from the command line using these arguments:

| Flag | Full Argument      | Description                                                                        |
| :--- | :----------------- | :--------------------------------------------------------------------------------- |
| `-u` | `--usenet`         | Triggers Usenet upload.                                                            |
|      | `--usenet-subject` | Specifies a custom subject line for the Usenet post (overrides `obscure_subject`). |

---

## 5. Example Commands

### Upload to Usenet Only (Skipping Torrent Trackers)

To upload content to Usenet and skip any torrent generation/client seeding:

```bash
python upload.py "/path/to/Movie.Name.2026.1080p.mkv" -u
```

_(or specify `USENET` directly as the target tracker)_:

```bash
python upload.py "/path/to/Movie.Name.2026.1080p.mkv" -tk USENET
```

### Upload to Usenet with a Custom Subject

```bash
python upload.py "/path/to/Folder_Name" -u --usenet-subject "My.Custom.Post.Subject"
```

### Upload to both Usenet and Torrent Trackers

You can combine torrent tracker uploads and Usenet posting in a single run:

```bash
python upload.py "/path/to/Movie.Name.2026.1080p.mkv" -tk BLUTOPIA,CURUPIRA
```
