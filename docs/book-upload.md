# Book and Audiobook Upload Guide

The Upload Assistant supports the `BOOK` category, enabling automated metadata gathering, rendering/artwork processing, duplicate checking, and uploading of both digital books (**ebooks**) and audiobooks (**audiobooks**).

---

## 1. Overview & Supported Formats

- **Ebooks**: Supports `.pdf`, `.epub`, `.mobi`, `.cbz`, and `.cbr` formats.
- **Audiobooks**: Supports `.mp3`, `.m4b`, `.flac`, `.aac`, `.m4a`, `.ogg`, and `.wav` formats.

The script automatically detects if a release is an audiobook by checking the file extensions of the largest file in the upload directory. If it is an audio format, it treats the upload as an audiobook.

---

## 2. Metadata Extraction & Priority Flow

To gather rich metadata with minimal manual input, Upload Assistant implements a hierarchical resolution flow:

$$\text{CLI Overrides} > \text{MyAnonamouse (MAM) API} > \text{Google Books API} > \text{Local File Metadata}$$

### A. Local File Metadata
1. **EPUB**: Automatically decompresses and parses the internal OPF file (`META-INF/container.xml` or any `.opf` file) to extract `title`, `author`, `language`, `year` (from `date`), `isbn` (from `identifier`), `overview` (description), and `publisher`.
2. **PDF**: Scans the first 30 pages and the last 30 pages using **PyMuPDF** (`fitz`). It searches for ISBN strings using regular expressions and validates them mathematically using ISBN-10 and ISBN-13 checksum algorithms to avoid false matches.
3. **MediaInfo**: Standard container tags (e.g., `Album`, `Performer`, `Composer`, `Publisher`, `Genre`, `ISBN`, `Comment`, `Description`) are preserved during the extraction phase for audiobooks and ebook files.

### B. API Metadata Integrations
- **MyAnonamouse (MAM)**: If the files being uploaded correspond to an active torrent in your local client containing `myanonamouse.net` in trackers, the assistant extracts the torrent ID (`MID=(\d+)`) from the client comments. It then queries the MAM API using your configured `mam_api_key` / `mam_id` to retrieve details like title, authors, narrators, description, ISBN, language, and cover image URL.
- **Google Books**: If a valid ISBN is resolved locally or provided via CLI, the assistant calls the Google Books API (using `google_books_api_key` if configured) to fetch title, authors, publisher, publication year, genres/keywords, book description, and front cover URL.

---

## 3. Artwork & Screenshot Generation

Instead of using FFmpeg frame extraction, the `BOOK` category utilizes specialized image workflows:

### A. Ebooks (PDF, EPUB, MOBI)
- Uses **PyMuPDF** (`fitz`) to render pages at double resolution (`matrix=Matrix(2.0, 2.0)`) into PNG files.
- Randomly samples a configured number of pages (e.g., 5) to generate gallery screenshots.
- Renders page 0 as `POSTER.png` (Cover) and the last page as `POSTER_BANNER.png`.

### B. Comics & Manga (CBR, CBZ)
- Unpacks the ZIP/RAR archive to access internal images.
- Dynamically sorts filenames using natural/alphanumeric order (e.g., `page-2` before `page-10`).
- Randomly samples internal images for screenshots, converting non-PNG files to PNG.
- Assigns the first page as `POSTER.png` and the last page as `POSTER_BANNER.png`.

### C. Audiobooks
- The assistant first searches for local images (e.g., `cover.jpg`) in the source directory.
- If not found, it attempts to extract embutted/embedded cover art using **mutagen** (supports FLAC pictures, MP3 ID3 APIC frames, and MP4/M4B `covr` boxes).
- If no embedded art exists, it attempts to download the cover image using poster URLs resolved from MAM or Google Books.

### D. Image Upload Controls
- The `book_screens` utility counts the actual screenshots generated and overrides the configured `min_successful_image_uploads` value dynamically. This prevents the script from blocking the upload if a short book has fewer pages than the global minimum image requirement.

---

## 4. Duplicate Checking Rules

The duplicate checking module (`dupe_checking.py`) uses custom rules for books to avoid incorrect exclusions:
- **Title Normalization**: Titles are stripped of accents (via NFKD normalization), converted to lowercase, and cleared of punctuation to ensure precise string comparison.
- **Format Distinction**: Ebooks and audiobooks of the same title are kept separate and are not flagged as duplicates of each other.
- **File Type Validation**: For ebooks, different file formats (e.g., EPUB vs PDF) are checked. Uploading an EPUB will not be marked as a duplicate of an existing PDF, allowing multiple formats of the same book to co-exist.

---

## 5. Console Prompting & Output Formatting

- **Interactive Metadata Prompting**: In attended mode, if required fields (`title`, `author`, `year`, `book_language`) are missing, the console prompts the user to supply them. The release name is then automatically rebuilt.

---

## 6. CLI Arguments

You can override auto-detected values using the following command-line flags:

| Flag | Full Argument | Description |
|---|---|---|
| `-pub` | `--publisher` | Overrides the book publisher metadata |
| `-btitle` | `--book_title` | Overrides the book title |
| `-author` | `--book_author` | Overrides the book author |
| `-isbn` | `--book_isbn` | Overrides the ISBN number |
| `-blang` | `--book_language` | Overrides the book language (e.g. English, Portuguese) |

---

## 7. Configuration Options

Add the following keys to your `config.py` file to enable external API integrations:

```python
config = {
    "DEFAULT": {
        # Google Books API Key (https://console.cloud.google.com/apis/library/books.googleapis.com)
        "google_books_api_key": "YOUR_GOOGLE_BOOKS_API_KEY",
        # MyAnonamouse API key / session cookie (mam_id)
        # Found in MAM Preferences > Security > View IP locked session cookie
        "mam_api_key": "YOUR_MAM_SESSION_COOKIE_OR_ID",
    }
}
```
