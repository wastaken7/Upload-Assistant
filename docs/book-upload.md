# Book and Audiobook Upload Guide

The Upload Assistant supports the `BOOK` category, enabling automated metadata gathering, rendering/artwork processing, duplicate checking, and uploading of both digital books (**ebooks**) and audiobooks (**audiobooks**).

---

## 1. Overview & Supported Formats

- **Ebooks**: Supports `.pdf`, `.epub`, `.mobi`, `.cbz`, and `.cbr` formats.
- **Audiobooks**: Supports `.mp3`, `.m4b`, `.flac`, `.aac`, `.m4a`, `.ogg`, and `.wav` formats.

### Automated Type & Subcategory Detection
The assistant automatically detects the subcategory or format of a book upload using a set of rules:
- **Audiobooks**: If the file extension of the largest file in the upload directory is an audio format, the upload is treated as an audiobook.
- **Comics/Manga**: Files with `.cbz` or `.cbr` extensions are automatically classified as Comics.
- **Newspapers**: Titles are matched (case-insensitively) against a built-in list of newspapers to auto-flag the upload as a Newspaper.
- **API Tags/Categories**: If MyAnonamouse (MAM) or Google Books APIs return relevant categories or tags (e.g. `manga`, `comic`, `magazine`, `newspaper`), the assistant updates the upload classification accordingly.

---

## 2. Metadata Extraction & Priority Flow

To gather rich metadata with minimal manual input, Upload Assistant implements a hierarchical resolution flow:

$$\text{CLI Overrides} > \text{MyAnonamouse (MAM) API} > \text{Google Books API} > \text{OpenLibrary API} > \text{Local File Metadata}$$

### A. Local File Metadata
1. **EPUB**: Automatically decompresses and parses the internal OPF file (`META-INF/container.xml` or any `.opf` file) to extract `title`, `author`, `language`, `year` (from `date`), `isbn` (from `identifier`), `overview` (description), and `publisher`.
2. **CBR/CBZ**: Automatically parses the internal `ComicInfo.xml` metadata file (case-insensitively located) to extract `title` (from `<Series>` or `<Title>`), `author` (from `<Writer>` or `<Penciller>`), `publisher` (from `<Publisher>`), `year` (from `<Year>`), `book_language` (from `<LanguageISO>`), `overview` (from `<Summary>`), and `genres`/`keywords` (from `<Genre>`, normalized to space-separated commas).
3. **MOBI**: Extracts the internal OPF file using the `mobi` library to extract `title`, `author`, `language`, `year`, `isbn`, `overview` (with HTML stripped), and `publisher`.
4. **PDF**: Scans the first 30 pages and the last 30 pages using **PyMuPDF** (`fitz`). It searches for ISBN strings using regular expressions and validates them mathematically using ISBN-10 and ISBN-13 checksum algorithms to avoid false matches.
5. **MediaInfo**: Standard container tags (e.g., `Album`, `Performer`, `Composer`, `Publisher`, `Genre`, `ISBN`, `ASIN`, `Comment`, `Description`) are preserved during the extraction phase for audiobooks and ebook files.

### B. API Metadata Integrations
- **MyAnonamouse (MAM)**: If the files being uploaded correspond to an active torrent in your local client containing `myanonamouse.net` in trackers, the assistant extracts the torrent ID (`MID=(\d+)`) from the client comments. It then queries the MAM API using your configured `mam_api_key` / `mam_id` to retrieve details like title, authors, narrators, description, ISBN, language, and cover image URL.
- **Google Books**: If a valid ISBN is resolved locally or provided via CLI, the assistant calls the Google Books API (using `google_books_api_key` if configured) to fetch title, authors, publisher, publication year, genres/keywords, book description, and front cover URL.
- **OpenLibrary**: If an OpenLibrary Work ID is provided via `-openlib` / `--openlibrary` CLI flag, **or** if an ISBN is available, the assistant queries the OpenLibrary API to fetch title, authors, description, cover image, publisher, publication year, and subjects/keywords. OpenLibrary results have the lowest priority among API sources — they will not override fields already populated by MAM or Google Books.

> [!IMPORTANT]
> If `google_books_api_key` is not configured in your `config.py`, the terminal will display a warning message in red alerting you that book metadata searches will be limited and incomplete.

---

## 3. Artwork & Screenshot Generation
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
---

## 4. Duplicate Checking Rules

The duplicate checking module (`dupe_checking.py`) uses custom rules for books to avoid incorrect exclusions:
- **Title Normalization**: Titles are stripped of accents (via NFKD normalization), converted to lowercase, and cleared of punctuation to ensure precise string comparison.
- **Format Distinction**: Ebooks and audiobooks of the same title are kept separate and are not flagged as duplicates of each other.
- **File Type Validation**: For ebooks, different file formats (e.g., EPUB vs PDF) are checked. Uploading an EPUB will not be marked as a duplicate of an existing PDF, allowing multiple formats of the same book to co-exist.

> [!IMPORTANT]
> **CBR Tracker Exception**: For the **CBR** tracker, different ebook formats *are* considered duplicates under the `BOOK` category because this tracker only allows one format per book.

---

## 5. Console Prompting & Output Formatting

- **Interactive Metadata Prompting**: In attended mode, if required fields (`title`, `author`, `year`, `book_language`) are missing, the console prompts the user to supply them. The release name is then automatically rebuilt.

---

## 6. CLI Arguments

You can override auto-detected values using the following command-line flags:

| Flag | Full Argument | Description |
|---|---|---|
| `-pub` | `--publisher` | Overrides the book publisher metadata |
| `-btitle` | `--book-title` | Overrides the book title |
| `-author` | `--author` | Overrides the book author |
| `-isbn` | `--isbn` | Overrides the ISBN number |
| `-asin` | `--asin` | Overrides the ASIN number |
| `-blang` | `--book-language` | Overrides the book language (e.g. English, Portuguese) |
| `-openlib` | `--openlibrary` | Specifies the OpenLibrary Work ID (e.g. `OL45883W`). Accepts a full OpenLibrary URL or just the ID. |
| `-comic` | `--comic` | Identifies the book upload as a Comic |
| `-manga` | `--manga` | Identifies the book upload as a Manga |
| `-magazine` | `--magazine` | Identifies the book upload as a Magazine |
| `-newspaper` | `--newspaper` | Identifies the book upload as a Newspaper |

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
        # Either key name is accepted: mam_api_key or mam_id
        "mam_api_key": "YOUR_MAM_SESSION_COOKIE_OR_ID",
    }
}
```

---

## 8. Supported Trackers

The following trackers support the `BOOK` category with custom metadata mapping (e.g., custom form templates, category IDs, and naming patterns):

- **ASC**: Maps book-specific metadata (author, title) and structures the torrent name as `{author} - {title}`.
- **BJS**: Fully supports books, audiobooks, comics, mangas, magazines, and newspapers with detailed metadata mappings (format, page count, publisher, ISBN, cover image, description).
- **BT**: Supports standard book metadata mapping.
- **CBR**: Supports books, audiobooks, and comics/manga. Treats different ebook formats as duplicates since only one format is allowed per book.
- **DC**: Supports ebooks and audiobooks. Generates a rich description block with cover image, author, narrator, publisher, ISBN, year, duration (for audiobooks), and synopsis.
- **HHD**: Supports books, audiobooks, comics, manga, and magazines as separate categories (UNIT3D).
- **IS**: Supports ebooks, audiobooks, comics, and magazines. Uses cookie-based authentication for uploads.
- **LDU**: Supports ebooks and audiobooks as distinct UNIT3D categories.
- **LST**: Supports books with OpenLibrary integration, submitting the OpenLibrary Work ID and ISBN alongside the torrent upload.
- **LT**: Supports ebooks, audiobooks, comics, and magazines. For audiobooks, appends the narration language to the torrent name (e.g., `(Narración en Castellano)`). Also supports volume/issue and edition info in the name.
- **SAM**: Brazilian tracker (UNIT3D). Maps books to `LIVROS`, audiobooks to `AUDIOBOOK`, and comics/manga to `HQS_E_MANGAS`.
- **SPD**: Supports the `BOOK` category as a unified type (category ID 6), without subcategory splitting.
- **TL**: Supports standard book metadata mapping.
- **YUS**: Supports ebooks and audiobooks as distinct UNIT3D categories.
