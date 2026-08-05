const { useState, useRef, useEffect, useCallback } = React;
const THEME_KEY = "ua_config_theme";
const LEFT_SIDEBAR_WIDTH_KEY = "ua_webui_left_sidebar_width";
const RIGHT_SIDEBAR_WIDTH_KEY = "ua_webui_right_sidebar_width";
const COLLAPSED_ARGUMENT_SECTIONS_KEY = "ua_webui_collapsed_argument_sections";
const DEFAULT_SIDEBAR_WIDTH = 320;
const SIDEBAR_MIN_WIDTH = 200;
const LEFT_SIDEBAR_MAX_WIDTH = 600;
const RIGHT_SIDEBAR_MAX_WIDTH = 800;

const storage = window.UAStorage;
const getStoredTheme = window.getUAStoredTheme;
const colorThemes = window.UAThemes || [];
const getStoredColorTheme = window.getUAStoredColorTheme;
const setColorTheme = window.setUAColorTheme;
let bbcodePreviewConfigured = false;

const escapePreviewHtml = (value) =>
  String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

const isSafePreviewUrl = (value) => {
  try {
    const url = new URL(value, window.location.origin);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch (_error) {
    return false;
  }
};

const getSafeBbcodeColor = (params) => {
  const color = String(params || "")
    .replace(/^=/, "")
    .trim()
    .toLowerCase();
  if (/^#[0-9a-f]{6}$/i.test(color)) return color;
  if (/^[a-z]{3,20}$/i.test(color)) return color;
  return "";
};

const sanitizeBbcodePreview = (html) => {
  if (!window.DOMPurify) {
    return `<div>${escapePreviewHtml(html).replace(/\n/g, "<br>")}</div>`;
  }

  const sanitized = window.DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "a",
      "b",
      "blockquote",
      "br",
      "code",
      "details",
      "div",
      "em",
      "hr",
      "i",
      "img",
      "li",
      "ol",
      "p",
      "pre",
      "span",
      "strong",
      "summary",
      "table",
      "tbody",
      "td",
      "th",
      "thead",
      "tr",
      "u",
      "ul",
    ],
    ALLOWED_ATTR: [
      "alt",
      "class",
      "colspan",
      "data-bbcode-color",
      "href",
      "src",
      "title",
    ],
  });
  const preview = new DOMParser().parseFromString(sanitized, "text/html");

  preview.querySelectorAll("[data-bbcode-color]").forEach((element) => {
    const color = getSafeBbcodeColor(element.getAttribute("data-bbcode-color"));
    element.removeAttribute("data-bbcode-color");
    if (color) element.style.color = color;
  });
  preview.querySelectorAll("[class*='xbbcode-size-']").forEach((element) => {
    const size = Number(
      element.className.match(/(?:^|\s)xbbcode-size-(\d+)(?:\s|$)/)?.[1],
    );
    if (Number.isInteger(size) && size >= 4 && size <= 40) {
      element.style.fontSize = `${size}px`;
    }
  });

  preview.querySelectorAll("a[href]").forEach((link) => {
    if (!isSafePreviewUrl(link.getAttribute("href"))) {
      link.removeAttribute("href");
      return;
    }
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  });
  preview.querySelectorAll("img[src]").forEach((image) => {
    if (!isSafePreviewUrl(image.getAttribute("src"))) {
      image.remove();
      return;
    }
    image.loading = "lazy";
  });

  return preview.body.innerHTML;
};

const configureBbcodePreview = () => {
  if (!window.XBBCODE?.addTags || bbcodePreviewConfigured) return;

  window.XBBCODE.addTags({
    color: {
      openTag: (params) => {
        const color = getSafeBbcodeColor(params);
        return color ? `<span data-bbcode-color="${color}">` : "<span>";
      },
      closeTag: () => "</span>",
    },
    spoiler: {
      openTag: () =>
        '<details class="xbbcode-spoiler"><summary>Spoiler</summary>',
      closeTag: () => "</details>",
    },
  });
  bbcodePreviewConfigured = true;
};

const renderBbcodePreview = (content) => {
  const text = String(content || "");
  if (!window.XBBCODE?.process) {
    return `<div>${escapePreviewHtml(text).replace(/\n/g, "<br>")}</div>`;
  }

  configureBbcodePreview();
  return sanitizeBbcodePreview(
    window.XBBCODE.process({
      text,
      addInLineBreaks: true,
      removeMisalignedTags: false,
      escapeHtml: true,
    }).html,
  );
};

const getStoredSidebarWidth = (key, defaultWidth, maxWidth) => {
  const storedWidth = Number(storage.get(key));
  if (
    Number.isFinite(storedWidth) &&
    storedWidth >= SIDEBAR_MIN_WIDTH &&
    storedWidth <= maxWidth
  ) {
    return storedWidth;
  }
  return defaultWidth;
};

const getStoredCollapsedSections = () => {
  try {
    const storedSections = JSON.parse(
      storage.get(COLLAPSED_ARGUMENT_SECTIONS_KEY) || "[]",
    );
    return Array.isArray(storedSections)
      ? storedSections.filter((section) => typeof section === "string")
      : [];
  } catch (error) {
    return [];
  }
};

// Local CSRF cache used by fallback `apiFetch` when `uaApiFetch` isn't present.
let localCsrf = null;
const loadLocalCsrf = async (force = false) => {
  if (localCsrf && !force) return;

  let apiBase = "";
  if (typeof window !== "undefined" && window.location) {
    apiBase = window.location.origin + "/api";
  } else {
    apiBase = "/api";
  }

  try {
    const r = await fetch(`${apiBase}/csrf_token`, {
      credentials: "same-origin",
    });
    if (!r.ok) return;
    const d = await r.json();
    localCsrf = d && d.csrf_token ? String(d.csrf_token) : null;
  } catch (e) {
    // ignore
  }
};

// Prefer shared `uaApiFetch` when available (provides CSRF handling and retry-on-auth-fail),
// otherwise fall back to a local implementation.
const apiFetch =
  (typeof window !== "undefined" && window.uaApiFetch) ||
  (async (url, options = {}) => {
    // Local fallback: load CSRF token once and retry on 401/403 once.
    await loadLocalCsrf();
    const headers = { ...(options.headers || {}) };
    if (localCsrf) headers["X-CSRF-Token"] = localCsrf;
    let response = await fetch(url, {
      ...options,
      headers,
      credentials: "same-origin",
    });
    if (response.status === 401 || response.status === 403) {
      await loadLocalCsrf(true);
      const headers2 = { ...(options.headers || {}) };
      if (localCsrf) headers2["X-CSRF-Token"] = localCsrf;
      response = await fetch(url, {
        ...options,
        headers: headers2,
        credentials: "same-origin",
      });
    }
    return response;
  });

const sanitizeHtml = window.sanitizeHtml;

// Argument categories for the right sidebar (placeholders shown for info only)
const argumentCategories = [
  {
    title: "Modes / Workflows",
    args: [
      {
        label: "--queue",
        placeholder: "QUEUE_NAME",
        description: "Process a named queue from a folder path",
      },
      {
        label: "--limit-queue",
        placeholder: "N",
        description: "Limit queue successful uploads",
      },
      { label: "--site-check", description: "Site check (can it be uploaded)" },
      {
        label: "--site-upload",
        placeholder: "TRACKER",
        description: "Site upload (process site check content)",
      },
      {
        label: "--search_requests",
        description: "Search supported site for matching requests (config)",
      },
      {
        label: "--unit3d",
        description: "Upload from UNIT3D-Upload-Checker results",
      },
    ],
  },
  {
    title: "Metadata / IDs",
    subtitle: "Getting these correct is 90% of a successful upload!",
    args: [
      {
        label: "--category",
        placeholder: "MOVIE",
        description: "Override detected category",
      },
      {
        label: "--type",
        placeholder: "REMUX",
        description: "Override detected type",
      },
      {
        label: "--source",
        placeholder: "Blu-ray",
        description: "Override detected source",
      },
      {
        label: "--resolution",
        placeholder: "2160p",
        description: "Override detected resolution",
      },
      { label: "--tmdb", placeholder: "movie/123", description: "TMDb id" },
      { label: "--imdb", placeholder: "tt0111161", description: "IMDb id" },
      { label: "--mal", placeholder: "ID", description: "MAL id" },
      { label: "--tvmaze", placeholder: "ID", description: "TVMaze id" },
      { label: "--tvdb", placeholder: "ID", description: "TVDB id" },
      { label: "--douban", placeholder: "ID", description: "Douban id" },
      { label: "--igdb", placeholder: "ID", description: "IGDB id" },
      {
        label: "--steam",
        placeholder: "APP_ID_OR_URL",
        description: "Steam app id or URL",
      },
    ],
  },
  {
    title: "Music Metadata",
    args: [
      {
        label: "--music-artist",
        placeholder: "ARTIST",
        description: "Override the main artist(s)",
      },
      {
        label: "--music-album",
        placeholder: "TITLE",
        description: "Override the album or release title",
      },
      {
        label: "--music-media",
        placeholder: "MEDIUM",
        description:
          "Source medium (CD, WEB, Vinyl, DVD, BD, Soundboard, SACD, DAT, Cassette)",
      },
      {
        label: "--music-release-type",
        placeholder: "ALBUM / EP / SINGLE",
        description: "Release type",
      },
      {
        label: "--music-release-year",
        placeholder: "YYYY",
        description: "Concrete release or pressing year",
      },
      {
        label: "--music-edition-year",
        placeholder: "YYYY",
        description: "Remaster, reissue, or edition year",
      },
      {
        label: "--music-label",
        placeholder: "LABEL",
        description: "Record label",
      },
      {
        label: "--music-catalogue-number",
        placeholder: "CATALOGUE",
        description: "Catalogue number",
      },
      {
        label: "--music-genre",
        placeholder: "GENRE1,GENRE2",
        description: "Comma-separated genre override",
      },
      {
        label: "--music-cover",
        placeholder: "URL_OR_PATH",
        description: "Artwork URL or local cover path",
      },
      {
        label: "--music-discogs-id",
        placeholder: "ID_OR_URL",
        description: "Discogs release or master reference",
      },
      {
        label: "--music-discogs-release-id",
        placeholder: "ID_OR_URL",
        description: "Exact Discogs release reference",
      },
      {
        label: "--music-discogs-master-id",
        placeholder: "ID_OR_URL",
        description: "Exact Discogs master reference",
      },
      {
        label: "--no-music-discogs",
        description: "Disable Discogs lookup and metadata",
      },
      {
        label: "--music-enrich",
        description: "Enable bounded MusicBrainz enrichment",
      },
      {
        label: "--no-music-enrich",
        description: "Disable MusicBrainz enrichment",
      },
    ],
  },
  {
    title: "Podcast / Unwalled",
    args: [
      {
        label: "--podcast-title",
        placeholder: "SHOW [YEAR/FORMAT - BITRATE]",
        description: "Final Unwalled torrent title",
      },
      {
        label: "--podcast-cover",
        placeholder: "/path/to/cover.jpg",
        description: "Square JPEG cover, at least 400x400",
      },
      {
        label: "--podcast-banner",
        placeholder: "/path/to/banner.jpg",
        description: "Distinct 16:9 JPEG banner, at least 960x540",
      },
      {
        label: "--unwalled-category",
        placeholder: "Technology or 14",
        description: "Unwalled subject category name or numeric id",
      },
      {
        label: "--unwalled-type",
        placeholder: "Free Audio or 3",
        description: "Unwalled upload type name or numeric id",
      },
    ],
  },
  {
    title: "Screenshots / Images",
    args: [
      {
        label: "--screens",
        placeholder: "N",
        description: "Number of screenshots to use",
      },
      {
        label: "--manual_frames",
        placeholder: '"1,250,500"',
        description: "Manual frame numbers for screenshots",
      },
      {
        label: "--comparison",
        placeholder: "PATH",
        description: "Comparison images folder",
      },
      {
        label: "--comparison_index",
        placeholder: "N",
        description: "Comparison main index",
      },
      {
        label: "--imghost",
        placeholder: "HOST",
        description: "Specific image host to use",
      },
      {
        label: "--skip-imagehost-upload",
        description: "Skip uploading screenshots",
      },
    ],
  },
  {
    title: "TV Fields",
    args: [
      { label: "--season", placeholder: "S01", description: "Season number" },
      { label: "--episode", placeholder: "E01", description: "Episode number" },
      {
        label: "--manual-episode-title",
        placeholder: "TITLE",
        description: "Manual episode title",
      },
      {
        label: "--daily",
        placeholder: "YYYY-MM-DD",
        description: "Air date for daily shows",
      },
    ],
  },
  {
    title: "Title Shaping",
    args: [
      { label: "--year", placeholder: "YYYY", description: "Override year" },
      { label: "--no-season", description: "Remove season" },
      { label: "--no-year", description: "Remove year" },
      { label: "--no-aka", description: "Remove AKA" },
      { label: "--no-dub", description: "Remove Dubbed" },
      { label: "--no-dual", description: "Remove Dual-Audio" },
      { label: "--no-tag", description: "Remove group tag" },
      { label: "--no-edition", description: "Remove edition" },
      { label: "--dual-audio", description: "Add Dual-Audio" },
      { label: "--tag", placeholder: "GROUP", description: "Group tag" },
      {
        label: "--service",
        placeholder: "SERVICE",
        description: "Streaming service",
      },
      { label: "--region", placeholder: "REGION", description: "Disc Region" },
      {
        label: "--edition",
        placeholder: "TEXT",
        description: "Edition marker",
      },
      { label: "--repack", placeholder: "TEXT", description: "Repack" },
    ],
  },
  {
    title: "Description / NFO",
    args: [
      {
        label: "--desclink",
        placeholder: "URL",
        description: "Link to pastebin/hastebin with description",
      },
      {
        label: "--descfile",
        placeholder: "PATH",
        description: "Path to description file (.txt, .nfo, .md)",
      },
      { label: "--nfo", description: "Use .nfo for description" },
      {
        label: "--keywords",
        placeholder: "keyword1,keyword2",
        description: "Comma-separated keywords",
      },
    ],
  },
  {
    title: "Language",
    args: [
      {
        label: "--original-language",
        placeholder: "en",
        description: "Original language of content",
      },
      {
        label: "--only-if-languages",
        placeholder: "en,fr",
        description:
          "Only proceed with upload if the content has these languages",
      },
    ],
  },
  {
    title: "Misc Metadata Flags",
    args: [
      { label: "--commentary", description: "Commentary" },
      { label: "--sfx-subtitles", description: "SFX subtitles" },
      { label: "--extras", description: "Extras included" },
      {
        label: "--distributor",
        placeholder: "NAME",
        description: "Disc distributor",
      },
      {
        label: "--disctype",
        placeholder: "BD50",
        description: "Disc type override",
      },
      { label: "--untouched", description: "Mark as untouched disc" },
      { label: "--menus", description: "Path to menus screenshots (PNGs)" },
      {
        label: "--manual_dvds",
        placeholder: "2xDVD9+DVD5",
        description: "Override the default number of DVDs",
      },
      {
        label: "--sorted-filelist",
        description: "Sorted filelist (handles typical anime nonsense)",
      },
      {
        label: "--keep-folder",
        description: "Keep top folder with single file uploads",
      },
      {
        label: "--keep-nfo",
        description: "Keep nfo (extremely site specific)",
      },
    ],
  },
  {
    title: "Books / Reading",
    args: [
      {
        label: "--author",
        placeholder: "AUTHOR",
        description: "Override detected book author",
      },
      {
        label: "--book-title",
        placeholder: "TITLE",
        description: "Override detected book title",
      },
      {
        label: "--book-cover",
        placeholder: "PATH_OR_URL",
        description: "Required BOOK cover image path or public image URL",
      },
      {
        label: "--book-overview",
        placeholder: "SYNOPSIS",
        description:
          "Book/Audiobook overview/synopsis (overrides auto-detected value)",
      },
      { label: "--comic", description: "Mark upload as comic" },
      { label: "--manga", description: "Mark upload as manga" },
      { label: "--magazine", description: "Mark upload as magazine" },
      { label: "--newspaper", description: "Mark upload as newspaper" },
      {
        label: "--book-translator",
        placeholder: "NAME",
        description: "Book translator",
      },
      {
        label: "--book-language",
        placeholder: "LANG",
        description: "Book language",
      },
      { label: "--isbn", placeholder: "ISBN", description: "ISBN identifier" },
      { label: "--asin", placeholder: "ASIN", description: "Amazon ASIN" },
      {
        label: "--openlibrary",
        placeholder: "ID",
        description: "OpenLibrary id",
      },
      {
        label: "--publisher",
        placeholder: "NAME",
        description: "Book publisher",
      },
    ],
  },
  {
    title: "Games",
    args: [
      {
        label: "--platform",
        placeholder: "PC",
        description: "Primary platform override",
      },
      {
        label: "--platforms",
        placeholder: "PC,PS5",
        description: "Platforms list",
      },
      {
        label: "--game-version",
        placeholder: "v1.0",
        description: "Game version",
      },
      {
        label: "--game-subcategory",
        placeholder: "dlc",
        description: "Game subcategory",
      },
      { label: "--multi", description: "Force a MULTI language tag" },
    ],
  },
  {
    title: "Tracker References",
    subtitle:
      "Pull metadata ids, descriptions, and screenshots from these trackers",
    args: [
      {
        label: "--onlyID",
        description: "Only grab meta ids, not descriptions",
      },
      { label: "--ptp", placeholder: "ID_OR_URL", description: "PTP id/link" },
      { label: "--blu", placeholder: "ID_OR_URL", description: "BLU id/link" },
      {
        label: "--aither",
        placeholder: "ID_OR_URL",
        description: "Aither id/link",
      },
      { label: "--lst", placeholder: "ID_OR_URL", description: "LST id/link" },
      { label: "--oe", placeholder: "ID_OR_URL", description: "OE id/link" },
      { label: "--hdb", placeholder: "ID_OR_URL", description: "HDB id/link" },
      { label: "--btn", placeholder: "ID_OR_URL", description: "BTN id/link" },
      { label: "--bhd", placeholder: "ID_OR_URL", description: "BHD id/link" },
      {
        label: "--orpheus",
        placeholder: "ID_OR_URL",
        description: "Orpheus id/link for music metadata enrichment",
      },
      {
        label: "--huno",
        placeholder: "ID_OR_URL",
        description: "HUNO id/link",
      },
      {
        label: "--ulcx",
        placeholder: "ID_OR_URL",
        description: "ULCX id/link",
      },
      {
        label: "--torrenthash",
        placeholder: "HASH",
        description: "(qBitTorrent only) Get site id from Torrent hash",
      },
    ],
  },
  {
    title: "Upload Selection / Dupe",
    args: [
      {
        label: "--trackers",
        placeholder: "aither,blutopia,lst,etc",
        description: "Specific Trackers list for uploading",
      },
      {
        label: "--trackers-remove",
        placeholder: "blutopia,xyz,etc",
        description:
          "Remove these trackers from the default list for this upload",
      },
      {
        label: "--trackers-pass",
        placeholder: "N",
        description:
          "How many trackers need to pass all checks for upload to proceed",
      },
      {
        label: "--skip_auto_torrent",
        description: "Skip auto torrent searching",
      },
      { label: "--skip-dupe-check", description: "Skip dupe check" },
      {
        label: "--skip-dupe-asking",
        description: "Accept any reported dupes without prompting about it",
      },
      {
        label: "--double-dupe-check",
        description: "Run another dupe check right before upload",
      },
      {
        label: "--dupe-size-difference-tolerance",
        placeholder: "PERCENTAGE",
        description: "Ignore dupes with size difference >= percentage",
      },
      {
        label: "--draft",
        description: "Send to Draft at supported sites (config)",
      },
      {
        label: "--modq",
        description: "Send to modQ at supported sites (config)",
      },
      {
        label: "--freeleech",
        placeholder: "25%",
        description: "Mark upload as Freeleech (percentage)",
      },
    ],
  },
  {
    title: "Anonymity / Seeding / Streaming",
    args: [
      {
        label: "--anon",
        description: "Anon upload at supported sites (config)",
      },
      { label: "--no-seed", description: "Don't send torrents to client" },
      { label: "--stream", description: "Stream" },
      { label: "--webdv", description: "Dolby Vision hybrid" },
      {
        label: "--hardcoded-subs",
        description: "Release contains hardcoded subs",
      },
      { label: "--personalrelease", description: "Personal release" },
    ],
  },
  {
    title: "Tracker / Site Specific",
    args: [
      { label: "--foreign", description: "CINEMATIK foreign category" },
      { label: "--opera", description: "CINEMATIK opera and musical category" },
      { label: "--asian", description: "CINEMATIK Asian category" },
      {
        label: "--exclusive",
        placeholder: "1",
        description: "Set exclusive flag where supported",
      },
    ],
  },
  {
    title: "Torrent Creation / Hashing",
    args: [
      {
        label: "--max-piece-size",
        placeholder: "N",
        description: "Max piece size (in MiB) of created torrent (1 <> 128)",
      },
      {
        label: "--nohash",
        description: "Don't rehash torrent even if it was needed",
      },
      {
        label: "--rehash",
        description:
          "Create a fresh torrent from the actual data, not an existing .torrent file",
      },
      {
        label: "--mkbrr",
        description: "Use mkbrr for torrent creation (config)",
      },
      {
        label: "--vapoursynth",
        description: "Use VapourSynth for screenshots",
      },
      { label: "--entropy", placeholder: "N", description: "Entropy" },
      { label: "--randomized", placeholder: "N", description: "Randomized" },
      {
        label: "--infohash",
        placeholder: "HASH",
        description: "Use this Infohash as the existing torrent from client",
      },
      {
        label: "--force-recheck",
        description:
          "(qBitTorrent only) Force recheck the file in client before upload",
      },
    ],
  },
  {
    title: "Torrent Client Integration",
    args: [
      {
        label: "--client",
        placeholder: "NAME",
        description: "Client name (config)",
      },
      {
        label: "--qbit-tag",
        placeholder: "TAG",
        description: "qBittorrent tag (config)",
      },
      {
        label: "--qbit-cat",
        placeholder: "CATEGORY",
        description: "qBittorrent category (config)",
      },
      {
        label: "--qbit-bw-control",
        description: "Enable qBittorrent bandwidth control",
      },
      {
        label: "--qbit-bw-threshold",
        placeholder: "KiB/s",
        description: "qBittorrent bandwidth threshold",
      },
      {
        label: "--qbit-bw-time",
        placeholder: "SECONDS",
        description: "qBittorrent bandwidth wait time",
      },
      {
        label: "--rtorrent-label",
        placeholder: "LABEL",
        description: "rTorrent label (config)",
      },
    ],
  },
  {
    title: "Cleanup / Temp",
    args: [
      {
        label: "--delete-meta",
        description: "Delete only meta.json from tmp folder",
      },
      {
        label: "--delete-tmp",
        description: "Delete the tmp folder associated with this upload",
      },
      { label: "--cleanup", description: "Cleanup the entire UA tmp folder" },
    ],
  },
  {
    title: "Debug / Output",
    args: [
      { label: "--debug", description: "Debug mode" },
      { label: "--ffdebug", description: "FFmpeg debug" },
      {
        label: "--upload-order",
        placeholder: "tracker1,tracker2",
        description: "Preferred upload order",
      },
      { label: "--webui", description: "Launch the WebUI mode" },
      { label: "--upload-timer", description: "Upload timer (config)" },
    ],
  },
  {
    title: "Audio Spectrograms",
    subtitle:
      "The stream positions are zero-based. Choose a preset, then edit the command if you want a different list.",
    args: [
      {
        label: "First audio stream",
        insert: "--audio-spectrogram --audio-spectrogram-tracks 0",
        description:
          "Generate an upload-ready spectrogram for stream position 0.",
      },
      {
        label: "All audio streams",
        insert: "--audio-spectrogram --audio-spectrogram-tracks all",
        description: "Generate one spectrogram per available stream.",
      },
      {
        label: "--audio-spectrogram",
        description:
          "Generate spectrograms; without a stream selection, the workflow will ask which streams to use.",
      },
      {
        label: "--audio-spectrogram-tracks",
        placeholder: "0,1 or all",
        insert: "--audio-spectrogram --audio-spectrogram-tracks all",
        description:
          "Preset inserts a valid selection. Replace 'all' with zero-based positions in the command field if needed.",
      },
    ],
  },
  {
    title: "Misc Options",
    args: [
      {
        label: "--not-anime",
        description: "Can speed up tv data extraction when not anime content",
      },
      {
        label: "--channel",
        placeholder: "ID_OR_TAG",
        description: "SPD channel",
      },
      { label: "--usenet", description: "Upload files to Usenet (NNTP)" },
      {
        label: "--usenet-subject",
        placeholder: "TEXT",
        description: "Custom Usenet subject line",
      },
      {
        label: "--archive-password",
        placeholder: "PASSWORD or random",
        description: "Override the Usenet 7z archive password for this run",
      },
      {
        label: "--unattended",
        description: "Unattended (no prompts (AT ALL))",
      },
      {
        label: "--unattended_confirm",
        description:
          "Unattended confirm (use with --unattended, some prompting)",
      },
    ],
  },
];

// Icon components
const WebUiIcon = ({ name, className = "w-5 h-5" }) => (
  <span
    aria-hidden="true"
    className={`inline-block flex-none ${className}`}
    style={{
      backgroundColor: "currentColor",
      mask: `url(/static/img/webui-icons/${name}.svg) center / contain no-repeat`,
      WebkitMask: `url(/static/img/webui-icons/${name}.svg) center / contain no-repeat`,
    }}
  />
);

const FolderIcon = () => (
  <WebUiIcon name="file-structure" className="w-4 h-4" />
);

const ScreenshotsIcon = () => <WebUiIcon name="screenshots" />;

const FolderOpenIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z"
    />
  </svg>
);

const FileIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
    />
  </svg>
);

const TerminalIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
    />
  </svg>
);

const PaletteIcon = () => <WebUiIcon name="palette" />;

const SettingsIcon = () => <WebUiIcon name="settings" />;

const ProgressIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M4 19V5m0 14h16M8 16v-4m4 4V8m4 8v-7"
    />
  </svg>
);

const MovieIcon = () => <WebUiIcon name="movie" />;

const TvIcon = () => <WebUiIcon name="tv" />;

const GameIcon = () => <WebUiIcon name="gamepad" />;

const BookIcon = () => <WebUiIcon name="book" />;

const DiscIcon = () => <WebUiIcon name="music" />;

const mediaIconForCategory = (category) => {
  switch (String(category || "").toUpperCase()) {
    case "MOVIE":
      return <MovieIcon />;
    case "TV":
      return <TvIcon />;
    case "GAME":
      return <GameIcon />;
    case "BOOK":
      return <BookIcon />;
    case "MUSIC":
      return <DiscIcon />;
    default:
      return <FileIcon />;
  }
};

const PlayIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
    />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
  </svg>
);

const PlusIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M12 5v14m-7-7h14"
    />
  </svg>
);

const ExpandIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M8 3H3v5m13-5h5v5M8 21H3v-5m18 0v5h-5"
    />
  </svg>
);

const TrashIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
    />
  </svg>
);

const LogoIcon = ({ src, className = "w-6 h-6" }) => (
  <img
    src={src}
    alt="Upload-Assistant logo"
    className={`${className} flex-shrink-0`}
  />
);

const ChevronDownIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M19 9l-7 7-7-7"
    />
  </svg>
);

const ChevronRightIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 5l7 7-7 7"
    />
  </svg>
);

const SearchIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
    />
  </svg>
);

const CollapseAllIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
    />
  </svg>
);

const ExpandAllIcon = () => (
  <svg
    className="w-4 h-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
    />
  </svg>
);

const SpinnerIcon = () => (
  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
    <circle
      className="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="4"
    ></circle>
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    ></path>
  </svg>
);

const metadataProviderStyles = {
  tmdb: {
    light: "border-[#06B4E2] bg-transparent text-[#067A98]",
    dark: "border-[#06B4E2]/70 bg-transparent text-[#B9F3FF]",
  },
  imdb: {
    light: "border-[#F5C518] bg-transparent text-[#6F5700]",
    dark: "border-[#F5C518]/70 bg-transparent text-[#FFF3B5]",
  },
  tvdb: {
    light: "border-[#6CD591] bg-transparent text-[#2F7D49]",
    dark: "border-[#6CD591]/70 bg-transparent text-[#D9F9E4]",
  },
  tvmaze: {
    light: "border-[#6EC4BA] bg-transparent text-[#2E7B73]",
    dark: "border-[#6EC4BA]/70 bg-transparent text-[#D4F4EF]",
  },
  mal: {
    light: "border-[#2E51A1] bg-transparent text-[#2E51A1]",
    dark: "border-[#2E51A1]/75 bg-transparent text-[#C9D6F4]",
  },
  douban: {
    light: "border-[#007610] bg-transparent text-[#007610]",
    dark: "border-[#007610]/75 bg-transparent text-[#B9F2C2]",
  },
  igdb: {
    light: "border-[#9147FF] bg-transparent text-[#9147FF]",
    dark: "border-[#9147FF]/75 bg-transparent text-[#E2D2FF]",
  },
  steam: {
    light: "border-slate-300 bg-transparent text-slate-900",
    dark: "border-slate-700 bg-transparent text-slate-100",
  },
  google_books: {
    light: "border-green-300 bg-transparent text-green-900",
    dark: "border-green-900/80 bg-transparent text-green-100",
  },
  openlibrary: {
    light: "border-orange-300 bg-transparent text-orange-900",
    dark: "border-orange-900/80 bg-transparent text-orange-100",
  },
  musicbrainz: {
    light: "border-[#BA478F] bg-transparent text-[#7D205D]",
    dark: "border-[#BA478F]/75 bg-transparent text-[#F4C7E4]",
  },
  discogs: {
    light: "border-slate-400 bg-transparent text-slate-900",
    dark: "border-slate-500/80 bg-transparent text-slate-100",
  },
  default: {
    light: "border-gray-300 bg-transparent text-gray-900",
    dark: "border-gray-700 bg-transparent text-gray-100",
  },
};

const getMetadataProviderStyle = (key, isDarkMode) => {
  const providerStyle =
    metadataProviderStyles[key] || metadataProviderStyles.default;
  return isDarkMode ? providerStyle.dark : providerStyle.light;
};

const metadataProviderIcons = {
  tmdb: { src: "/static/img/providers/tmdb.svg", alt: "TMDb" },
  imdb: { src: "/static/img/providers/imdb.svg", alt: "IMDb" },
  tvdb: { src: "/static/img/providers/tvdb.svg", alt: "TVDb" },
  mal: { src: "/static/img/providers/mal.svg", alt: "MyAnimeList" },
  igdb: {
    src: "/static/img/providers/igdb.svg",
    lightSrc: "/static/img/providers/igdb_light.svg",
    alt: "IGDB",
  },
  douban: { src: "/static/img/providers/douban.svg", alt: "Douban" },
  google_books: {
    src: "/static/img/providers/google_books.svg",
    alt: "Google Books",
  },
  openlibrary: {
    src: "/static/img/providers/openlibrary.svg",
    alt: "Open Library",
  },
  musicbrainz: {
    src: "/static/img/providers/musicbrainz.ico",
    alt: "MusicBrainz",
  },
  discogs: { src: "/static/img/providers/discogs.svg", alt: "Discogs" },
  steam: { src: "/static/img/providers/steam.svg", alt: "Steam" },
  tvmaze: { src: "/static/img/providers/tvmaze.svg", alt: "TVMaze" },
};

const renderMetadataProviderIcon = (key, isDarkMode) => {
  const iconAsset = metadataProviderIcons[key];
  if (iconAsset) {
    const iconSrc =
      !isDarkMode && iconAsset.lightSrc ? iconAsset.lightSrc : iconAsset.src;
    return (
      <img
        src={iconSrc}
        alt={iconAsset.alt}
        className={`block h-3.5 w-auto max-w-[3.75rem] object-contain ${
          key === "discogs" && !isDarkMode ? "invert" : ""
        }`}
      />
    );
  }

  switch (key) {
    case "google_books":
      return (
        <svg
          className="w-4 h-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.8}
            d="M5 6.25A2.25 2.25 0 017.25 4h10.5A1.25 1.25 0 0119 5.25v13.5A1.25 1.25 0 0117.75 20H7.25A2.25 2.25 0 015 17.75V6.25z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.8}
            d="M7.5 6H18M8 9.5h6.5M8 13h7.5"
          />
        </svg>
      );
    case "openlibrary":
      return (
        <svg
          className="w-4 h-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.8}
            d="M4.5 6.5A2.5 2.5 0 017 4h11.5v15.5H7a2.5 2.5 0 010-5h11.5"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.8}
            d="M8.5 8.5h6M8.5 12h6"
          />
        </svg>
      );
    default:
      return (
        <span className="text-[11px] font-black tracking-wide">
          {String(key || "META")
            .slice(0, 4)
            .toUpperCase()}
        </span>
      );
  }
};

function AudionutsUAGUI() {
  const API_BASE = window.location.origin + "/api";
  // Derive an application base path from the API base so links work under subpath deployments
  const APP_BASE = API_BASE.replace(/\/api$/, "");

  const [directories, setDirectories] = useState([
    { name: "data", type: "folder", path: "/data", children: [] },
    {
      name: "torrent_storage_dir",
      type: "folder",
      path: "/torrent_storage_dir",
      children: [],
    },
    {
      name: "Upload-Assistant",
      type: "folder",
      path: "/Upload-Assistant",
      children: [],
    },
  ]);

  const [selectedPath, setSelectedPath] = useState("");
  const [, setSelectedName] = useState("");
  const [customArgs, setCustomArgs] = useState("");
  const [argumentPresets, setArgumentPresets] = useState([]);
  const [argumentPresetName, setArgumentPresetName] = useState("");
  const [selectedArgumentPreset, setSelectedArgumentPreset] = useState("");
  const [trackers, setTrackers] = useState([]);
  const [defaultTrackers, setDefaultTrackers] = useState(new Set());
  const [selectedTrackers, setSelectedTrackers] = useState(new Set());
  const [failedFavicons, setFailedFavicons] = useState(new Set());
  const [isExecuting, setIsExecuting] = useState(false);
  const [isOutputExpanded, setIsOutputExpanded] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState(
    new Set(["/data", "/torrent_storage_dir"]),
  );
  const [sessionId, setSessionId] = useState("");
  const [sidebarWidth, setSidebarWidth] = useState(() =>
    getStoredSidebarWidth(
      LEFT_SIDEBAR_WIDTH_KEY,
      DEFAULT_SIDEBAR_WIDTH,
      LEFT_SIDEBAR_MAX_WIDTH,
    ),
  );
  const [isResizing, setIsResizing] = useState(false);
  const [rightSidebarWidth, setRightSidebarWidth] = useState(() =>
    getStoredSidebarWidth(
      RIGHT_SIDEBAR_WIDTH_KEY,
      DEFAULT_SIDEBAR_WIDTH,
      RIGHT_SIDEBAR_MAX_WIDTH,
    ),
  );
  const [isResizingRight, setIsResizingRight] = useState(false);
  const [userInput, setUserInput] = useState("");
  const [isSendingInput, setIsSendingInput] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(getStoredTheme);
  const [colorTheme, setColorThemeState] = useState(getStoredColorTheme);
  const [isThemePaletteOpen, setIsThemePaletteOpen] = useState(false);
  const [argSearchFilter, setArgSearchFilter] = useState("");
  const [collapsedSections, setCollapsedSections] = useState(
    () => new Set(getStoredCollapsedSections()),
  );
  const [executionPreview, setExecutionPreview] = useState(null);
  const [executionScreenshots, setExecutionScreenshots] = useState([]);
  const [executionDescription, setExecutionDescription] = useState(null);
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [descriptionView, setDescriptionView] = useState("edit");
  const [descriptionVersion, setDescriptionVersion] = useState(0);
  const [descriptionDirty, setDescriptionDirty] = useState(false);
  const descriptionDirtyRef = useRef(false);
  const descriptionVersionRef = useRef(0);
  const descriptionEditorRef = useRef(null);
  const [descriptionAction, setDescriptionAction] = useState("");
  const [canAddExecutionScreenshot, setCanAddExecutionScreenshot] =
    useState(false);
  const [screenshotActionId, setScreenshotActionId] = useState("");
  const [expandedScreenshot, setExpandedScreenshot] = useState(null);
  const themePaletteRef = useRef(null);
  const screenshotModalRef = useRef(null);

  useEffect(() => {
    descriptionDirtyRef.current = descriptionDirty;
  }, [descriptionDirty]);
  const screenshotModalCloseRef = useRef(null);
  const [isScreenshotReviewOpen, setIsScreenshotReviewOpen] = useState(false);
  const [isDescriptionReviewOpen, setIsDescriptionReviewOpen] = useState(false);
  const [progressItems, setProgressItems] = useState([]);
  const [selectedPaths, setSelectedPaths] = useState([]);
  const [sortBy, setSortBy] = useState("name");
  const [sortOrder, setSortOrder] = useState("asc");

  useEffect(() => {
    storage.set(
      COLLAPSED_ARGUMENT_SECTIONS_KEY,
      JSON.stringify(Array.from(collapsedSections)),
    );
  }, [collapsedSections]);

  useEffect(() => {
    let cancelled = false;
    const loadArgumentPresets = async () => {
      try {
        const response = await apiFetch(`${API_BASE}/argument_presets`);
        if (!response.ok) return;
        const data = await response.json();
        if (!cancelled && data.success && Array.isArray(data.presets)) {
          setArgumentPresets(data.presets);
        }
      } catch (error) {
        console.error("Failed to load argument presets:", error);
      }
    };
    loadArgumentPresets();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleColorThemeChange = (event) => {
      setColorThemeState(event.detail?.theme || getStoredColorTheme());
    };
    window.addEventListener("ua-theme-change", handleColorThemeChange);
    return () =>
      window.removeEventListener("ua-theme-change", handleColorThemeChange);
  }, []);

  useEffect(() => {
    if (!isThemePaletteOpen) return undefined;
    const closeWhenOutside = (event) => {
      if (!themePaletteRef.current?.contains(event.target)) {
        setIsThemePaletteOpen(false);
      }
    };
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setIsThemePaletteOpen(false);
    };
    document.addEventListener("pointerdown", closeWhenOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeWhenOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isThemePaletteOpen]);

  const handleColorThemeChange = (event) => {
    setColorThemeState(setColorTheme(event.target.value));
  };

  const renderThemePalette = () => (
    <div ref={themePaletteRef} className="relative">
      <button
        type="button"
        onClick={() => setIsThemePaletteOpen((open) => !open)}
        aria-label="Theme settings"
        aria-expanded={isThemePaletteOpen}
        title="Theme settings"
        className={`p-2 rounded-lg transition-colors ${isDarkMode ? "text-gray-200 hover:bg-gray-700" : "text-gray-600 hover:bg-gray-100"}`}
      >
        <PaletteIcon />
      </button>
      {isThemePaletteOpen && (
        <div
          className={`absolute right-0 top-full z-50 mt-2 w-56 rounded-lg border p-3 shadow-xl ${isDarkMode ? "border-gray-700 bg-gray-800 text-gray-100" : "border-gray-200 bg-white text-gray-800"}`}
        >
          <label className="block text-xs font-semibold uppercase tracking-wide opacity-70">
            Color theme
          </label>
          <select
            value={colorTheme}
            onChange={(event) => {
              handleColorThemeChange(event);
              setIsThemePaletteOpen(false);
            }}
            aria-label="Color theme"
            className="ua-theme-picker mt-1.5 w-full rounded px-2 py-1.5 text-sm"
          >
            {colorThemes.map((theme) => (
              <option key={theme.id} value={theme.id}>
                {theme.label}
              </option>
            ))}
          </select>
          <div className="mt-3 flex items-center justify-between gap-3">
            <span className="text-sm">
              {isDarkMode ? "Dark mode" : "Light mode"}
            </span>
            <button
              type="button"
              onClick={() => setIsDarkMode((dark) => !dark)}
              aria-label={
                isDarkMode ? "Switch to light mode" : "Switch to dark mode"
              }
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${isDarkMode ? "bg-purple-600" : "bg-gray-300"}`}
            >
              <span
                className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${isDarkMode ? "translate-x-5" : "translate-x-1"}`}
              />
            </button>
          </div>
        </div>
      )}
    </div>
  );

  // Mobile state
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  const [activePanel, setActivePanel] = useState("main"); // 'main' | 'files' | 'args'

  // File Browser search states
  const [fileBrowserSearch, setFileBrowserSearch] = useState("");
  const [fileBrowserSearchResults, setFileBrowserSearchResults] =
    useState(null);
  const [fileBrowserSearchLoading, setFileBrowserSearchLoading] =
    useState(false);
  const fileBrowserSearchTimer = useRef(null);
  const fileBrowserSearchQuery = useRef("");

  // Folder loading states
  const [loadingFolders, setLoadingFolders] = useState(new Set());

  // Description file/link states
  const [descDirectories, setDescDirectories] = useState([]);
  const [descExpandedFolders, setDescExpandedFolders] = useState(new Set());
  const [descLoadingFolders, setDescLoadingFolders] = useState(new Set());
  const [descLinkError, setDescLinkError] = useState("");
  const [descFileError, setDescFileError] = useState("");
  const [descBrowserCollapsed, setDescBrowserCollapsed] = useState(false);
  const [descLinkFocused, setDescLinkFocused] = useState(false);

  const richOutputRef = useRef(null);
  const lastFullHashRef = useRef("");
  const inputRef = useRef(null);
  const isSendingInputRef = useRef(false);
  const sseAbortControllerRef = useRef(null);
  const visibleProgressItems = progressItems.filter(
    (item) => item.status !== "completed",
  );

  const sortProgressItems = (items) => {
    return [...items].sort((a, b) => {
      const aRunning = a.status === "running" ? 0 : 1;
      const bRunning = b.status === "running" ? 0 : 1;
      if (aRunning !== bRunning) return aRunning - bRunning;
      return String(a.id || "").localeCompare(String(b.id || ""));
    });
  };

  const mergeProgressItemsById = (existingItems, incomingItems) => {
    const itemsById = new Map(existingItems.map((item) => [item.id, item]));
    incomingItems.forEach((item) => {
      if (!item || !item.id) return;
      const existing = itemsById.get(item.id);
      if (
        !existing ||
        Number(item.updated_at || 0) >= Number(existing.updated_at || 0)
      ) {
        itemsById.set(item.id, existing ? { ...existing, ...item } : item);
      }
    });
    return sortProgressItems([...itemsById.values()]);
  };

  const applyProgressEvent = (event) => {
    if (!event || typeof event !== "object") return;
    if (event.op === "reset") {
      setProgressItems([]);
      return;
    }
    if (!event.id) return;
    setProgressItems((prev) => {
      const existingIndex = prev.findIndex((item) => item.id === event.id);
      if (existingIndex === -1) {
        return sortProgressItems([...prev, event]);
      }
      const next = [...prev];
      next[existingIndex] = { ...next[existingIndex], ...event };
      return sortProgressItems(next);
    });
  };

  const renderProgressPanel = (compact = false) => {
    if (!visibleProgressItems.length) return null;

    return (
      <div
        className={`rounded-lg border p-3 shadow-xl backdrop-blur-sm ${isDarkMode ? "border-gray-700 bg-gray-800" : "border-gray-200 bg-white/95"}`}
      >
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h4
              className={`font-semibold ${compact ? "text-sm" : "text-base"} ${isDarkMode ? "text-white" : "text-gray-900"}`}
            >
              Binary Progress
            </h4>
            <p
              className={`text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
            >
              Live progress from external tools
            </p>
          </div>
          <span
            className={`text-xs font-medium ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
          >
            {visibleProgressItems.length} active
          </span>
        </div>
        <div
          className={`${compact ? "space-y-2" : "space-y-3"} max-h-[40vh] overflow-y-auto pr-1`}
        >
          {visibleProgressItems.map((item) => {
            const current = Number(item.current ?? 0);
            const total = Number(item.total ?? 0);
            const hasTotal = Number.isFinite(total) && total > 0;
            const clampedPercent = hasTotal
              ? Math.max(0, Math.min(100, (current / total) * 100))
              : 0;
            const isCompleted = item.status === "completed";
            const isFailed = item.status === "failed";
            const statusTone = isCompleted
              ? isDarkMode
                ? "text-emerald-300"
                : "text-emerald-700"
              : isFailed
                ? isDarkMode
                  ? "text-rose-300"
                  : "text-rose-700"
                : isDarkMode
                  ? "text-purple-300"
                  : "text-purple-700";
            const progressTone = isCompleted
              ? "bg-emerald-500"
              : isFailed
                ? "bg-rose-500"
                : "bg-purple-500";
            let summary = "";
            if (hasTotal) {
              if (item.unit === "percent")
                summary = `${Math.round(clampedPercent)}%`;
              else summary = `${Math.round(current)}/${Math.round(total)}`;
            }
            return (
              <div
                key={item.id}
                className={`rounded-lg border px-3 py-2 ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gray-50"}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p
                      className={`font-medium truncate ${compact ? "text-sm" : "text-[15px]"} ${isDarkMode ? "text-white" : "text-gray-900"}`}
                    >
                      {item.label || item.id}
                    </p>
                    {item.detail && (
                      <p
                        className={`text-xs truncate ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                      >
                        {item.detail}
                      </p>
                    )}
                  </div>
                  <div
                    className={`text-xs font-semibold whitespace-nowrap ${statusTone}`}
                  >
                    {summary ||
                      (isCompleted ? "Done" : isFailed ? "Failed" : "Running")}
                  </div>
                </div>
                <div
                  className={`mt-2 h-2.5 overflow-hidden rounded-full ${isDarkMode ? "bg-gray-700" : "bg-gray-200"}`}
                >
                  <div
                    className={`h-full rounded-full transition-[width] duration-300 ${progressTone} ${!hasTotal && !isFailed ? "animate-pulse" : ""}`}
                    style={{
                      width: `${hasTotal ? clampedPercent : isFailed ? 100 : 35}%`,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderFloatingProgressPanel = () => {
    if (isMobile || isExecuting) return null;
    const panel = renderProgressPanel(true);
    if (!panel) return null;

    return (
      <div
        className={`pointer-events-none absolute left-3 bottom-3 z-20 ${isMobile ? "right-3" : "w-[24rem] max-w-[calc(100%-1.5rem)]"}`}
      >
        <div className="pointer-events-auto">{panel}</div>
      </div>
    );
  };

  const renderProgressWorkspace = () => {
    return (
      <div className="flex flex-col h-full">
        <div
          className={`p-3 border-b flex-shrink-0 ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gradient-to-l from-cyan-50 to-sky-50"}`}
        >
          <h2
            className={`text-base font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
          >
            <ProgressIcon />
            Binary Progress
          </h2>
          <p
            className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
          >
            Live progress from external tools while the queue is running.
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          {renderProgressPanel() || (
            <div
              className={`rounded-lg border p-5 text-center text-sm ${isDarkMode ? "border-gray-700 bg-gray-800 text-gray-400" : "border-gray-200 bg-gray-50 text-gray-500"}`}
            >
              Waiting for an external tool to report progress.
            </div>
          )}
        </div>
      </div>
    );
  };

  // Detect if --descfile or --desclink is present in arguments
  const hasDescFile = customArgs.includes("--descfile");
  const hasDescLink = customArgs.includes("--desclink");

  // URL validation helper - accepts any HTTP/HTTPS URL (server fetches and parses any URL)
  const isValidUrl = (string) => {
    try {
      const url = new URL(string);
      return url.protocol === "http:" || url.protocol === "https:";
    } catch (_) {
      return false;
    }
  };

  // Path validation helper - checks if string looks like a valid file path
  const isValidDescFilePath = (path) => {
    if (!path || path.trim() === "") return { valid: false, error: "" };

    const trimmed = path.trim();

    // Check for valid description file extensions
    const validExtensions = [".txt", ".nfo", ".md"];
    const hasValidExt = validExtensions.some((ext) =>
      trimmed.toLowerCase().endsWith(ext),
    );

    // Check if it looks like a path (has separators or starts with drive letter/root)
    const hasPathSeparator = trimmed.includes("/") || trimmed.includes("\\");
    const startsWithRoot =
      /^[a-zA-Z]:/.test(trimmed) ||
      trimmed.startsWith("/") ||
      trimmed.startsWith("\\");
    const looksLikePath = hasPathSeparator || startsWithRoot;

    if (!looksLikePath) {
      return {
        valid: false,
        error:
          "Path should be a full file path (e.g., /path/to/desc.txt or C:\\path\\desc.txt)",
      };
    }

    if (!hasValidExt) {
      return {
        valid: false,
        error: "File should have a valid extension (.txt, .nfo, or .md)",
      };
    }

    return { valid: true, error: "" };
  };

  // Extract value from argument string (e.g., --descfile "path" or --desclink "url")
  // Supports both space-separated (--arg "value") and equals-separated (--arg="value") formats
  const extractArgValue = (args, argName) => {
    // First try equals-separated format: --argname="value" or --argname='value' or --argname=value
    const equalsRegex = new RegExp(
      `(?:^|\\s)${argName}=(?:"([^\\"]*)"|'([^\\']*)'|([^\\s]+))`,
      "i",
    );
    const equalsMatch = args.match(equalsRegex);
    if (equalsMatch) {
      const val =
        equalsMatch[1] !== undefined
          ? equalsMatch[1]
          : equalsMatch[2] !== undefined
            ? equalsMatch[2]
            : equalsMatch[3] || "";
      // Double-check: don't return values that look like arguments
      if (val.startsWith("--")) return "";
      return val.trim();
    }

    // Then try space-separated format: --argname "value" or --argname 'value' or --argname value
    const spaceRegex = new RegExp(
      `(?:^|\\s)${argName}\\s+(?:"([^\\"]*)"|'([^\\']*)'|([^\\s-][^\\s]*|(?!--)[^\\s]+))`,
      "i",
    );
    const spaceMatch = args.match(spaceRegex);
    if (spaceMatch) {
      const val =
        spaceMatch[1] !== undefined
          ? spaceMatch[1]
          : spaceMatch[2] !== undefined
            ? spaceMatch[2]
            : spaceMatch[3] || "";
      // Double-check: don't return values that look like arguments
      if (val.startsWith("--")) return "";
      return val.trim();
    }
    return "";
  };

  // Update argument value in string
  // Supports both space-separated (--arg "value") and equals-separated (--arg="value") formats
  const updateArgValue = (args, argName, value) => {
    // Check if argument exists
    if (!args.includes(argName)) {
      return args;
    }

    // Check which format is being used
    const hasEqualsFormat = new RegExp(`${argName}=`, "i").test(args);
    const hasSpaceValue = new RegExp(
      `${argName}\\s+(?:"[^"]*"|'[^']*'|(?!--)[^\\s]+)`,
      "i",
    ).test(args);

    // If value is empty, remove the value but keep the flag
    if (!value) {
      if (hasEqualsFormat) {
        // Remove equals-format value: --arg="value" or --arg='value' or --arg=value
        return args.replace(
          new RegExp(`(${argName})=(?:"[^"]*"|'[^']*'|[^\\s]*)`, "i"),
          "$1",
        );
      } else if (hasSpaceValue) {
        // Remove space-format value
        return args.replace(
          new RegExp(`(${argName})\\s+(?:"[^"]*"|'[^']*'|(?!--)[^\\s]+)`, "i"),
          "$1",
        );
      }
      return args;
    }

    // Quote the value if it contains spaces
    const quotedValue = value.includes(" ") ? `"${value}"` : `"${value}"`;

    if (hasEqualsFormat) {
      // Replace equals-format value: --arg="value" or --arg='value' or --arg=value
      return args.replace(
        new RegExp(`(${argName})=(?:"[^"]*"|'[^']*'|[^\\s]*)`, "i"),
        `$1=${quotedValue}`,
      );
    } else if (hasSpaceValue) {
      // Replace space-format value
      return args.replace(
        new RegExp(`(${argName})\\s+(?:"[^"]*"|'[^']*'|(?!--)[^\\s]+)`, "i"),
        `$1 ${quotedValue}`,
      );
    } else {
      // Add value after the flag (no existing value)
      return args.replace(
        new RegExp(`(${argName})(\\s|$)`, "i"),
        `$1 ${quotedValue}$2`,
      );
    }
  };

  const parseTrackersFromArgs = (argsString, defaultTrackersSet) => {
    const hasTk = /(?:^|\s)(-tk|--trackers)(?=$|=|\s)/i.test(argsString);
    if (!hasTk) {
      return new Set(defaultTrackersSet);
    }

    let val = extractArgValue(argsString, "-tk");
    if (!val) {
      val = extractArgValue(argsString, "--trackers");
    }

    if (val) {
      const list = val
        .split(",")
        .map((t) => t.trim().toUpperCase())
        .filter(Boolean);
      return new Set(list);
    }
    return new Set();
  };

  const syncTrackersToArgs = (
    argsString,
    selectedTrackersSet,
    defaultTrackersSet,
  ) => {
    const selectedList = Array.from(selectedTrackersSet).sort();
    const defaultList = Array.from(defaultTrackersSet).sort();
    const isDefault =
      selectedList.length === defaultList.length &&
      selectedList.every((val, index) => val === defaultList[index]);
    const trackersVal = selectedList.join(",");
    const hasTk = /(?:^|\s)(-tk|--trackers)(?=$|=|\s)/i.test(argsString);

    if (isDefault) {
      if (hasTk) {
        let cleaned = argsString.replace(
          /((?:^|\s)(?:-tk|--trackers))\s*=\s*(?:"[^"]*"|'[^']*'|[^\s]*)/gi,
          "",
        );
        cleaned = cleaned.replace(
          /((?:^|\s)(?:-tk|--trackers))\s+(?:"[^"]*"|'[^']*'|(?!--)[^\s]+)/gi,
          "",
        );
        cleaned = cleaned.replace(
          /((?:^|\s)(?:-tk|--trackers))(?=$|=|\s)/gi,
          "",
        );
        return cleaned.replace(/\s+/g, " ").trim();
      }
      return argsString;
    } else {
      if (hasTk) {
        const match = argsString.match(/(?:^|\s)(-tk|--trackers)(?=$|=|\s)/i);
        const flagUsed = match ? match[1] : "-tk";
        const equalsRegex = new RegExp(
          `((?:^|\\s)${flagUsed})\\s*=\\s*(?:"[^"]*"|'[^']*'|[^\\s]*)`,
          "i",
        );
        const spaceRegex = new RegExp(
          `((?:^|\\s)${flagUsed})\\s+(?:"[^"]*"|'[^']*'|(?!--)[^\\s]+)`,
          "i",
        );
        const quotedVal = `"${trackersVal}"`;
        if (equalsRegex.test(argsString)) {
          return argsString.replace(equalsRegex, `$1=${quotedVal}`);
        } else if (spaceRegex.test(argsString)) {
          return argsString.replace(spaceRegex, `$1 ${quotedVal}`);
        } else {
          return argsString.replace(
            new RegExp(`((?:^|\\s)${flagUsed})(?=$|\\s)`, "i"),
            `$1 ${quotedVal}`,
          );
        }
      } else {
        const suffix = `-tk "${trackersVal}"`;
        return argsString.trim() ? `${argsString.trim()} ${suffix}` : suffix;
      }
    }
  };

  const handleTrackerToggle = (trackerName) => {
    const nextSet = new Set(selectedTrackers);
    if (nextSet.has(trackerName)) {
      nextSet.delete(trackerName);
    } else {
      nextSet.add(trackerName);
    }
    setSelectedTrackers(nextSet);
    setCustomArgs((prev) => syncTrackersToArgs(prev, nextSet, defaultTrackers));
  };

  const renderTrackerSelector = () => {
    if (!trackers || trackers.length === 0) return null;

    const getInitialsColor = (name) => {
      let hash = 0;
      for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
      }
      const colors = [
        "#ef4444",
        "#f97316",
        "#f59e0b",
        "#10b981",
        "#06b6d4",
        "#3b82f6",
        "#6366f1",
        "#8b5cf6",
        "#ec4899",
        "#14b8a6",
      ];
      const index = Math.abs(hash) % colors.length;
      return colors[index];
    };

    return (
      <div
        className={`mt-3 space-y-2 p-3 rounded-lg border ${isDarkMode ? "bg-gray-900 border-gray-700 text-white" : "bg-gray-50 border-gray-200 text-gray-800"}`}
      >
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider opacity-75">
            Select Trackers (-tk):
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => {
                setSelectedTrackers(new Set(defaultTrackers));
                setCustomArgs(
                  syncTrackersToArgs(
                    customArgs,
                    defaultTrackers,
                    defaultTrackers,
                  ),
                );
              }}
              className="text-[10px] text-purple-500 hover:text-purple-400 underline font-medium"
              disabled={isExecuting}
            >
              Reset to Defaults
            </button>
            <button
              onClick={() => {
                const nextSet = new Set();
                setSelectedTrackers(nextSet);
                setCustomArgs(
                  syncTrackersToArgs(customArgs, nextSet, defaultTrackers),
                );
              }}
              className="text-[10px] text-purple-500 hover:text-purple-400 underline font-medium"
              disabled={isExecuting}
            >
              Clear All
            </button>
          </div>
        </div>
        <div
          className={`flex flex-wrap gap-2 pr-1 ${!isExecuting && !isOutputExpanded ? "" : "max-h-48 overflow-y-auto"}`}
        >
          {trackers.map((tracker) => {
            const isSelected = selectedTrackers.has(tracker.name);
            const isDefault = defaultTrackers.has(tracker.name);
            const hasFavicon =
              tracker.favicon && !failedFavicons.has(tracker.name);

            return (
              <button
                key={tracker.name}
                onClick={() => handleTrackerToggle(tracker.name)}
                disabled={isExecuting}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm font-medium border transition-all ${
                  isSelected
                    ? isDarkMode
                      ? "bg-purple-900/60 border-purple-500 text-purple-200 hover:bg-purple-900/80"
                      : "bg-purple-100 border-purple-300 text-purple-800 hover:bg-purple-200"
                    : isDarkMode
                      ? "bg-gray-800 border-gray-700 text-gray-400 hover:bg-gray-700 hover:text-gray-200"
                      : "bg-white border-gray-300 text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
                title={`${tracker.display_name}${isDefault ? " (Default)" : ""}`}
              >
                {hasFavicon ? (
                  <img
                    src={tracker.favicon}
                    alt=""
                    onError={() => {
                      setFailedFavicons((prev) => {
                        const next = new Set(prev);
                        next.add(tracker.name);
                        return next;
                      });
                    }}
                    className="w-4 h-4 rounded-sm object-contain"
                  />
                ) : (
                  <span
                    className="w-4 h-4 rounded-sm flex items-center justify-center text-[9px] font-bold text-white uppercase select-none"
                    style={{
                      backgroundColor: getInitialsColor(tracker.display_name),
                      minWidth: "16px",
                      height: "16px",
                      lineHeight: "16px",
                    }}
                  >
                    {tracker.display_name.charAt(0)}
                  </span>
                )}
                <span>{tracker.display_name}</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  // Update selected trackers when customArgs changes
  useEffect(() => {
    const newSet = parseTrackersFromArgs(customArgs, defaultTrackers);
    const listA = Array.from(newSet).sort();
    const listB = Array.from(selectedTrackers).sort();
    const isDifferent =
      listA.length !== listB.length || listA.some((v, i) => v !== listB[i]);
    if (isDifferent) {
      setSelectedTrackers(newSet);
    }
  }, [customArgs, defaultTrackers]);

  // Get current values from args
  const descFilePath = extractArgValue(customArgs, "--descfile");
  const descLinkUrl = extractArgValue(customArgs, "--desclink");

  // Validate desclink URL when it changes
  useEffect(() => {
    if (hasDescLink && descLinkUrl) {
      if (!isValidUrl(descLinkUrl)) {
        setDescLinkError(
          "Please enter a valid paste URL (pastebin, hastebin, etc.)",
        );
      } else {
        setDescLinkError("");
      }
    } else {
      setDescLinkError("");
    }
  }, [descLinkUrl, hasDescLink]);

  // Validate descfile path when it changes and auto-collapse when valid
  useEffect(() => {
    if (hasDescFile && descFilePath) {
      const validation = isValidDescFilePath(descFilePath);
      setDescFileError(validation.error);
      // Auto-collapse when valid file is selected
      if (validation.valid) {
        setDescBrowserCollapsed(true);
      }
    } else {
      setDescFileError("");
    }
  }, [descFilePath, hasDescFile]);

  // Reset description browser when argument is removed
  useEffect(() => {
    if (!hasDescFile) {
      setDescDirectories([]);
      setDescExpandedFolders(new Set());
      setDescFileError("");
      setDescBrowserCollapsed(false);
    }
    if (!hasDescLink) {
      setDescLinkError("");
    }
  }, [hasDescFile, hasDescLink]);

  useEffect(() => {
    if (!isExecuting || !sessionId) {
      setExecutionPreview(null);
      setProgressItems([]);
      setExecutionScreenshots([]);
      setExecutionDescription(null);
      setDescriptionDraft("");
      setDescriptionView("edit");
      descriptionVersionRef.current = 0;
      setDescriptionVersion(0);
      setDescriptionDirty(false);
      setCanAddExecutionScreenshot(false);
      setExpandedScreenshot(null);
      setIsScreenshotReviewOpen(false);
      setIsDescriptionReviewOpen(false);
      setActivePanel((panel) =>
        ["screenshots", "description"].includes(panel) ? "main" : panel,
      );
      return undefined;
    }

    let cancelled = false;
    let timeoutId;
    let activeController = null;

    const loadExecutionPreview = async () => {
      const controller = new AbortController();
      activeController = controller;
      try {
        const response = await apiFetch(
          `${API_BASE}/execution_preview?session_id=${encodeURIComponent(sessionId)}`,
          // This endpoint changes throughout a queue run.  Do not allow a
          // browser or intermediary cache to keep showing an earlier item.
          { cache: "no-store", signal: controller.signal },
        );
        if (!response.ok) {
          // Do not keep showing the previous queue item when the backend has
          // already moved on (or the session was briefly unavailable).
          if (response.status === 404 && !cancelled) {
            setExecutionPreview(null);
            setProgressItems([]);
            setExecutionScreenshots([]);
            setCanAddExecutionScreenshot(false);
            setExecutionDescription(null);
          }
          return;
        }
        const data = await response.json();
        if (!cancelled && data && data.success && data.media) {
          setExecutionPreview(data.media);
          if (Array.isArray(data.media.progress)) {
            setProgressItems((prev) =>
              mergeProgressItemsById(prev, data.media.progress),
            );
          }
        }
        const screenshotsResponse = await apiFetch(
          `${API_BASE}/execution_screenshots?session_id=${encodeURIComponent(sessionId)}`,
          { cache: "no-store", signal: controller.signal },
        );
        if (screenshotsResponse.ok) {
          const screenshotsData = await screenshotsResponse.json();
          if (!cancelled && screenshotsData?.success) {
            setExecutionScreenshots(
              Array.isArray(screenshotsData.screenshots)
                ? screenshotsData.screenshots
                : [],
            );
            setCanAddExecutionScreenshot(Boolean(screenshotsData.can_add));
          }
        }
        const descriptionResponse = await apiFetch(
          `${API_BASE}/execution_description?session_id=${encodeURIComponent(sessionId)}`,
          { cache: "no-store", signal: controller.signal },
        );
        if (descriptionResponse.ok) {
          const descriptionData = await descriptionResponse.json();
          const polledVersion = Number.isInteger(descriptionData?.version)
            ? descriptionData.version
            : null;
          if (
            !cancelled &&
            descriptionData?.success &&
            polledVersion !== null &&
            polledVersion >= descriptionVersionRef.current
          ) {
            descriptionVersionRef.current = polledVersion;
            setExecutionDescription(descriptionData);
            if (!descriptionDirtyRef.current) {
              setDescriptionDraft(descriptionData.content || "");
              setDescriptionVersion(polledVersion);
            }
          }
        }
      } catch (_error) {
        // Ignore preview polling failures while execution continues.
      } finally {
        if (activeController === controller) {
          activeController = null;
        }
        if (!cancelled) {
          timeoutId = window.setTimeout(loadExecutionPreview, 2000);
        }
      }
    };

    loadExecutionPreview();

    return () => {
      cancelled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      activeController?.abort();
    };
  }, [API_BASE, isExecuting, sessionId]);

  const refreshExecutionScreenshots = async () => {
    const refreshed = await apiFetch(
      `${API_BASE}/execution_screenshots?session_id=${encodeURIComponent(sessionId)}`,
      { cache: "no-store" },
    );
    const refreshedData = await refreshed.json().catch(() => null);
    if (!refreshed.ok || !refreshedData?.success) {
      throw new Error("Could not refresh screenshots.");
    }
    setExecutionScreenshots(refreshedData.screenshots || []);
    setCanAddExecutionScreenshot(Boolean(refreshedData.can_add));
  };

  const changeExecutionScreenshot = async (screenshotId, action) => {
    if (!sessionId || screenshotActionId) return;
    setScreenshotActionId(`${action}:${screenshotId}`);
    try {
      const response = await apiFetch(
        `${API_BASE}/execution_screenshots/${encodeURIComponent(screenshotId)}/${action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }),
        },
      );
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.success) {
        window.alert(data?.error || `Could not ${action} screenshot.`);
        return;
      }
      await refreshExecutionScreenshots();
    } catch (error) {
      console.error(`Could not ${action} screenshot:`, error);
      window.alert(`Could not ${action} screenshot. Please try again.`);
    } finally {
      setScreenshotActionId("");
    }
  };

  const addExecutionScreenshot = async (group = "main") => {
    if (!sessionId || screenshotActionId || !canAddExecutionScreenshot) return;
    setScreenshotActionId("add");
    try {
      const response = await apiFetch(`${API_BASE}/execution_screenshots/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, group }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.success) {
        window.alert(data?.error || "Could not add screenshot.");
        return;
      }
      await refreshExecutionScreenshots();
    } catch (error) {
      console.error("Could not add screenshot:", error);
      window.alert("Could not add screenshot. Please try again.");
    } finally {
      setScreenshotActionId("");
    }
  };

  useEffect(() => {
    if (!expandedScreenshot) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setExpandedScreenshot(null);
    };
    document.addEventListener("keydown", closeOnEscape);
    const focusTimer = window.setTimeout(
      () => screenshotModalCloseRef.current?.focus(),
      0,
    );
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      window.clearTimeout(focusTimer);
    };
  }, [expandedScreenshot]);

  useEffect(() => {
    if (
      expandedScreenshot &&
      !executionScreenshots.some(
        (screenshot) => screenshot.id === expandedScreenshot,
      )
    ) {
      setExpandedScreenshot(null);
    }
  }, [executionScreenshots, expandedScreenshot]);

  // Update descfile in args
  const updateDescFile = (path) => {
    setCustomArgs((prev) => updateArgValue(prev, "--descfile", path));
  };

  // Update desclink in args
  const updateDescLink = (url) => {
    setCustomArgs((prev) => updateArgValue(prev, "--desclink", url));
  };

  const appendHtmlFragment = (rawHtml) => {
    const container = richOutputRef.current;
    if (container) {
      const clean = sanitizeHtml((rawHtml || "").trim());
      const wrapper = document.createElement("div");
      wrapper.innerHTML = clean;
      container.appendChild(wrapper);
      // Use scrollIntoView to avoid clipping of the last line
      setTimeout(() => {
        const last = container.lastElementChild;
        if (last && last.scrollIntoView) last.scrollIntoView({ block: "end" });
        else container.scrollTop = container.scrollHeight;
      }, 0);
    }
  };

  const appendSystemMessage = (text, kind = "info") => {
    const rootContainer = richOutputRef.current;
    if (!rootContainer) return;
    const el = document.createElement("div");
    // Support multiple kinds: error, user-input, and default info
    if (kind === "error") el.className = "text-red-400";
    else if (kind === "user-input") el.className = "text-green-300";
    else el.className = "text-blue-300";
    el.style.whiteSpace = "pre-wrap";
    el.textContent = text;
    rootContainer.appendChild(el);
    // ensure fully visible
    setTimeout(() => {
      const last = rootContainer.lastElementChild;
      if (last && last.scrollIntoView) last.scrollIntoView({ block: "end" });
      else rootContainer.scrollTop = rootContainer.scrollHeight;
    }, 0);
  };

  const sendInput = async (session_id, input) => {
    if (isSendingInputRef.current || !session_id) return;
    isSendingInputRef.current = true;
    setIsSendingInput(true);
    // Optimistically echo the user's input locally so it appears before
    // any subsequent server-generated prompt / output.
    appendSystemMessage("> " + input, "user-input");
    setUserInput("");
    try {
      await apiFetch(`${API_BASE}/input`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id, input }),
      });
    } catch (err) {
      console.error("Failed to send input:", err);
      appendSystemMessage("Failed to send input", "error");
    } finally {
      isSendingInputRef.current = false;
      setIsSendingInput(false);
    }
  };

  // Initial welcome message in the rich output area
  useEffect(() => {
    appendSystemMessage("Upload-Assistant Interactive Output");
    appendSystemMessage(
      '\nQuick Start:\n  1. Select a file or folder from the left panel\n  2. Add Upload-Assistant arguments (optional)\n  3. Click "Execute Upload" to start\n',
    );
  }, []);

  const loadBrowseRoots = async () => {
    try {
      const response = await apiFetch(`${API_BASE}/browse_roots`);
      const data = await response.json();

      if (data.success && data.items) {
        setDirectories(data.items);
        setExpandedFolders(new Set());
      }
    } catch (error) {
      console.error("Failed to load browse roots:", error);
    }
  };

  // Load description file browser roots
  const loadDescBrowseRoots = async () => {
    try {
      const response = await apiFetch(`${API_BASE}/browse_roots`);
      const data = await response.json();

      if (data.success && data.items) {
        setDescDirectories(data.items);
        setDescExpandedFolders(new Set());
      }
    } catch (error) {
      console.error("Failed to load desc browse roots:", error);
    }
  };

  // Load description folder contents
  const loadDescFolderContents = async (path) => {
    try {
      const response = await apiFetch(
        `${API_BASE}/browse?path=${encodeURIComponent(path)}&filter=desc`,
      );
      const data = await response.json();

      if (data.success && data.items) {
        updateDescDirectoryTree(path, data.items);
      }
    } catch (error) {
      console.error("Failed to load desc folder:", error);
    }
  };

  // Update description directory tree
  const updateDescDirectoryTree = (path, items) => {
    const updateTree = (nodes) => {
      return nodes.map((node) => {
        if (node.path === path) {
          return { ...node, children: items };
        } else if (node.children) {
          return { ...node, children: updateTree(node.children) };
        }
        return node;
      });
    };

    setDescDirectories((prev) => updateTree(prev));
  };

  // Toggle description folder
  const toggleDescFolder = async (path) => {
    const newExpanded = new Set(descExpandedFolders);

    if (newExpanded.has(path)) {
      newExpanded.delete(path);
      setDescExpandedFolders(newExpanded);
    } else {
      newExpanded.add(path);
      setDescExpandedFolders(newExpanded);

      // Show loading indicator while fetching
      setDescLoadingFolders((prev) => new Set(prev).add(path));
      try {
        await loadDescFolderContents(path);
      } finally {
        setDescLoadingFolders((prev) => {
          const next = new Set(prev);
          next.delete(path);
          return next;
        });
      }
    }
  };

  // Load desc roots when --descfile is added
  useEffect(() => {
    if (hasDescFile && descDirectories.length === 0) {
      loadDescBrowseRoots();
    }
  }, [hasDescFile]);
  useEffect(() => {
    storage.set(THEME_KEY, isDarkMode ? "dark" : "light");
  }, [isDarkMode]);

  useEffect(() => {
    if (isExecuting) {
      setIsOutputExpanded(true);
    }
  }, [isExecuting]);

  useEffect(() => {
    const handleStorage = (event) => {
      if (event.key === THEME_KEY) {
        setIsDarkMode(event.newValue === "dark");
      }
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  // Mobile resize listener
  useEffect(() => {
    let resizeTimer;
    const handleResize = () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        const mobile = window.innerWidth < 768;
        setIsMobile(mobile);
        if (!mobile) setActivePanel("main");
      }, 100);
    };
    window.addEventListener("resize", handleResize);
    return () => {
      clearTimeout(resizeTimer);
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  useEffect(() => {
    loadBrowseRoots();

    const loadTrackersData = async () => {
      try {
        const response = await apiFetch(`${API_BASE}/trackers`);
        if (!response.ok) return;
        const data = await response.json();
        if (data.success && data.trackers) {
          setTrackers(data.trackers);
          const defaultSet = new Set(data.default_trackers || []);
          setDefaultTrackers(defaultSet);

          const initialSet = parseTrackersFromArgs(customArgs, defaultSet);
          setSelectedTrackers(initialSet);
        }
      } catch (err) {
        console.error("Failed to load trackers:", err);
      }
    };
    loadTrackersData();
  }, []);

  // Cleanup file browser search debounce timer on unmount
  useEffect(() => {
    return () => {
      if (fileBrowserSearchTimer.current) {
        clearTimeout(fileBrowserSearchTimer.current);
      }
    };
  }, []);

  // Focus input when executing
  useEffect(() => {
    if (isExecuting && inputRef.current) {
      setTimeout(() => {
        try {
          inputRef.current.focus();
        } catch (e) {
          /* ignore */
        }
      }, 50);
    }
  }, [isExecuting]);

  useEffect(() => {
    if (isMobile && activePanel === "progress") {
      setActivePanel(isExecuting ? "files" : "main");
    }
  }, [activePanel, isExecuting, isMobile]);

  const getVisiblePaths = () => {
    if (fileBrowserSearch) {
      if (!fileBrowserSearchResults || !fileBrowserSearchResults.items)
        return [];
      return fileBrowserSearchResults.items.map((item) => item.path);
    }

    const traverse = (nodes) => {
      let paths = [];
      for (const node of nodes) {
        paths.push(node.path);
        if (
          node.type === "folder" &&
          expandedFolders.has(node.path) &&
          node.children
        ) {
          paths = paths.concat(traverse(node.children));
        }
      }
      return paths;
    };
    return traverse(directories);
  };

  const handleToggleSelectAll = () => {
    const visible = getVisiblePaths();
    if (visible.length === 0) return;

    const allSelected = visible.every((p) =>
      selectedPaths.some((x) => x.path === p),
    );
    if (allSelected) {
      setSelectedPaths((prev) => prev.filter((p) => !visible.includes(p.path)));
    } else {
      setSelectedPaths((prev) => {
        const next = [...prev];
        visible.forEach((p) => {
          if (!next.some((x) => x.path === p)) next.push({ path: p, args: "" });
        });
        return next;
      });
    }
  };

  const handleTogglePathSelect = (path) => {
    setSelectedPaths((prev) => {
      const isSelected = prev.some((x) => x.path === path);
      let next;
      if (isSelected) {
        next = prev.filter((p) => p.path !== path);
      } else {
        next = [...prev, { path, args: "" }];
      }
      if (next.length === 1) {
        setSelectedPath(next[0].path);
        const findName = (nodes) => {
          for (const node of nodes) {
            if (node.path === next[0].path) return node.name;
            if (node.children) {
              const res = findName(node.children);
              if (res) return res;
            }
          }
          return "";
        };
        const name = findName(directories) || next[0].path.split(/[/\\]/).pop();
        setSelectedName(name);
      }
      return next;
    });
  };

  const handleUpdateItemArgs = (path, newArgs) => {
    setSelectedPaths((prev) =>
      prev.map((item) =>
        item.path === path ? { ...item, args: newArgs } : item,
      ),
    );
  };

  const formatMtime = (mtime) => {
    if (!mtime) return "";
    const d = new Date(mtime * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const formatSize = (bytes) => {
    if (!bytes) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  const sortItems = (items) => {
    if (!items) return [];
    return [...items].sort((a, b) => {
      const aIsDir = a.type === "folder" ? 0 : 1;
      const bIsDir = b.type === "folder" ? 0 : 1;
      if (aIsDir !== bIsDir) return aIsDir - bIsDir;

      let valA, valB;
      if (sortBy === "name") {
        valA = (a.name || "").toLowerCase();
        valB = (b.name || "").toLowerCase();
        return sortOrder === "asc"
          ? valA.localeCompare(valB)
          : valB.localeCompare(valA);
      } else if (sortBy === "date") {
        valA = a.mtime || 0;
        valB = b.mtime || 0;
        return sortOrder === "asc" ? valA - valB : valB - valA;
      } else if (sortBy === "size") {
        valA = a.size || 0;
        valB = b.size || 0;
        return sortOrder === "asc" ? valA - valB : valB - valA;
      }
      return 0;
    });
  };

  const renderSelectAllBar = () => {
    const visible = getVisiblePaths();
    const selectedVisible = visible.filter((p) =>
      selectedPaths.some((x) => x.path === p),
    );
    const allSelected =
      visible.length > 0 && selectedVisible.length === visible.length;
    const someSelected =
      selectedVisible.length > 0 && selectedVisible.length < visible.length;

    return (
      <div
        className={`flex flex-col gap-2 p-3 border-b text-xs flex-shrink-0 ${
          isDarkMode
            ? "border-gray-700 bg-gray-800/30"
            : "border-gray-200 bg-gray-50"
        }`}
      >
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 cursor-pointer font-medium select-none">
            <input
              type="checkbox"
              checked={allSelected}
              ref={(el) => {
                if (el) el.indeterminate = someSelected;
              }}
              onChange={handleToggleSelectAll}
              className={`w-3.5 h-3.5 rounded text-purple-600 focus:ring-purple-500 cursor-pointer ${
                isDarkMode
                  ? "bg-gray-700 border-gray-600"
                  : "bg-white border-gray-300"
              }`}
            />
            <span className={isDarkMode ? "text-gray-300" : "text-gray-600"}>
              {allSelected ? "Deselect All" : "Select All"} (
              {selectedPaths.length})
            </span>
          </label>
          {selectedPaths.length > 0 && (
            <button
              onClick={() => setSelectedPaths([])}
              className="text-purple-600 hover:text-purple-500 font-semibold transition-colors"
            >
              Clear Selection
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <span className={isDarkMode ? "text-gray-400" : "text-gray-500"}>
            Sort by:
          </span>
          <select
            value={`${sortBy}-${sortOrder}`}
            onChange={(e) => {
              const [by, order] = e.target.value.split("-");
              setSortBy(by);
              setSortOrder(order);
            }}
            className={`flex-1 px-2 py-1 text-xs border rounded focus:ring-1 focus:ring-purple-500 focus:border-transparent ${
              isDarkMode
                ? "bg-gray-800 border-gray-700 text-gray-200"
                : "bg-white border-gray-300 text-gray-700"
            }`}
          >
            <option value="name-asc">Name (A-Z)</option>
            <option value="name-desc">Name (Z-A)</option>
            <option value="date-desc">Date Modified (Newest)</option>
            <option value="date-asc">Date Modified (Oldest)</option>
            <option value="size-desc">Size (Largest)</option>
            <option value="size-asc">Size (Smallest)</option>
          </select>
        </div>
      </div>
    );
  };

  const renderSelectedPathOrQueue = (isMobileView = false) => {
    if (selectedPaths.length > 1) {
      return (
        <div
          className={`p-4 rounded-lg border ${
            isDarkMode
              ? "bg-gray-800 border-gray-700"
              : "bg-white border-gray-200 shadow-sm"
          } space-y-3`}
        >
          <div className="flex items-center justify-between border-b pb-2 border-gray-700">
            <h3
              className={`${isMobileView ? "text-xs" : "text-sm"} font-bold ${
                isDarkMode ? "text-white" : "text-gray-800"
              } flex items-center gap-2`}
            >
              <span className="flex h-2 w-2 relative">
                {isExecuting && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
                )}
                <span
                  className={`relative inline-flex rounded-full h-2 w-2 ${isExecuting ? "bg-purple-500" : "bg-gray-400"}`}
                ></span>
              </span>
              Execution Queue ({selectedPaths.length} items)
            </h3>
          </div>
          <div className="max-h-60 overflow-y-auto space-y-3 pr-1 font-mono text-[11px]">
            {selectedPaths.map((item, idx) => {
              const name = item.path.split(/[/\\]/).pop() || item.path;

              return (
                <div
                  key={item.path}
                  className={`flex flex-col gap-1.5 p-2 rounded border ${
                    isDarkMode
                      ? "bg-gray-900 border-gray-800"
                      : "bg-gray-50 border-gray-200"
                  }`}
                >
                  <div className="flex items-center justify-between min-w-0">
                    <span
                      className={`truncate font-semibold ${
                        isDarkMode ? "text-gray-200" : "text-gray-800"
                      }`}
                      title={item.path}
                    >
                      {idx + 1}. {name}
                    </span>
                    <button
                      onClick={() => handleTogglePathSelect(item.path)}
                      className="text-red-500 hover:text-red-400 font-bold ml-2 text-xs font-sans"
                      title="Remove from queue"
                      disabled={isExecuting}
                    >
                      ✕
                    </button>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label
                      className={`text-[10px] ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                    >
                      Line Arguments:
                    </label>
                    <input
                      type="text"
                      value={item.args}
                      onChange={(e) =>
                        handleUpdateItemArgs(item.path, e.target.value)
                      }
                      placeholder="e.g. --tmdb audiobook/12345 --anon"
                      className={`w-full px-2 py-1 text-xs border rounded-lg focus:ring-1 focus:ring-purple-500 focus:border-transparent ${
                        isDarkMode
                          ? "bg-gray-800 border-gray-700 text-white placeholder-gray-500"
                          : "bg-white border-gray-300 text-gray-900 placeholder-gray-400"
                      }`}
                      disabled={isExecuting}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      );
    }

    if (isMobileView) {
      return selectedPath ? (
        <div
          className={`p-2 rounded-lg ${isDarkMode ? "bg-gray-700 border-gray-600" : "bg-blue-50 border-blue-200"} border`}
        >
          <div className="flex items-center justify-between">
            <p
              className={`text-xs font-semibold ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
            >
              Selected:
            </p>
            <button
              onClick={() => setActivePanel("files")}
              className={`text-xs px-2 py-0.5 rounded ${isDarkMode ? "bg-gray-600 text-gray-200 hover:bg-gray-500" : "bg-blue-100 text-blue-700 hover:bg-blue-200"}`}
            >
              Browse
            </button>
          </div>
          <p
            className={`text-xs ${isDarkMode ? "text-white" : "text-gray-800"} break-all font-mono mt-1`}
          >
            {selectedPath}
          </p>
        </div>
      ) : (
        <button
          onClick={() => setActivePanel("files")}
          className={`w-full p-3 rounded-lg border-2 border-dashed text-center inline-flex items-center justify-center ${isDarkMode ? "border-gray-600 text-gray-400 hover:border-purple-500 hover:text-purple-400" : "border-gray-300 text-gray-500 hover:border-purple-500 hover:text-purple-600"}`}
        >
          <FolderIcon />
          <span className="text-sm ml-2">Tap to select a file or folder</span>
        </button>
      );
    }

    return (
      selectedPath && (
        <div
          className={`p-3 ${
            isDarkMode
              ? "bg-gray-700 border-gray-600"
              : "bg-blue-50 border-blue-200"
          } border rounded-lg`}
        >
          <p
            className={`text-xs font-semibold ${
              isDarkMode ? "text-gray-300" : "text-gray-600"
            } mb-1`}
          >
            Selected Path:
          </p>
          <p
            className={`text-sm ${
              isDarkMode ? "text-white" : "text-gray-800"
            } break-all font-mono`}
          >
            {selectedPath}
          </p>
        </div>
      )
    );
  };

  const toggleFolder = async (path) => {
    const newExpanded = new Set(expandedFolders);

    if (newExpanded.has(path)) {
      newExpanded.delete(path);
      setExpandedFolders(newExpanded);
    } else {
      newExpanded.add(path);
      setExpandedFolders(newExpanded);

      // Show loading indicator while fetching
      setLoadingFolders((prev) => new Set(prev).add(path));
      try {
        await loadFolderContents(path);
      } finally {
        setLoadingFolders((prev) => {
          const next = new Set(prev);
          next.delete(path);
          return next;
        });
      }
    }
  };

  const loadFolderContents = async (path) => {
    try {
      const response = await apiFetch(
        `${API_BASE}/browse?path=${encodeURIComponent(path)}`,
      );
      const data = await response.json();

      if (data.success && data.items) {
        updateDirectoryTree(path, data.items);
      }
    } catch (error) {
      console.error("Failed to load folder:", error);
    }
  };

  const updateDirectoryTree = (path, items) => {
    const updateTree = (nodes) => {
      return nodes.map((node) => {
        if (node.path === path) {
          return { ...node, children: items };
        } else if (node.children) {
          return { ...node, children: updateTree(node.children) };
        }
        return node;
      });
    };

    setDirectories((prev) => updateTree(prev));
  };

  // File Browser search
  const handleFileBrowserSearch = (value) => {
    setFileBrowserSearch(value);
    const searchQuery = value.trim();
    fileBrowserSearchQuery.current = searchQuery;
    if (fileBrowserSearchTimer.current) {
      clearTimeout(fileBrowserSearchTimer.current);
    }
    if (!searchQuery) {
      setFileBrowserSearchResults(null);
      setFileBrowserSearchLoading(false);
      return;
    }
    setFileBrowserSearchLoading(true);
    fileBrowserSearchTimer.current = setTimeout(async () => {
      try {
        const response = await apiFetch(
          `${API_BASE}/browse_search?q=${encodeURIComponent(searchQuery)}`,
        );
        if (!response.ok) {
          throw new Error(`Search request failed (${response.status})`);
        }
        const data = await response.json();
        // Early return if the search has changed since this request
        if (fileBrowserSearchQuery.current !== searchQuery) return;
        if (data.success) {
          setFileBrowserSearchResults(data);
        } else {
          setFileBrowserSearchResults({
            items: [],
            query: searchQuery,
            count: 0,
          });
        }
      } catch (error) {
        console.error("File browser search failed:", error);
        if (fileBrowserSearchQuery.current === searchQuery) {
          setFileBrowserSearchResults({
            items: [],
            query: searchQuery,
            count: 0,
          });
        }
      } finally {
        if (fileBrowserSearchQuery.current === searchQuery) {
          setFileBrowserSearchLoading(false);
        }
      }
    }, 300); //300ms debounce so we dont spam requests for every keystroke
  };

  const renderSearchResults = (results) => {
    if (!results || !results.items) return null;
    if (results.items.length === 0) {
      return (
        <div
          className={`p-4 text-center ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
        >
          <p className="text-sm">No results found</p>
        </div>
      );
    }
    const sorted = sortItems(results.items);
    return sorted.map((item, idx) => {
      const separatorIdx = Math.max(
        item.path.lastIndexOf("/"),
        item.path.lastIndexOf("\\"),
      );
      const parentPath =
        separatorIdx > 0 ? item.path.substring(0, separatorIdx) : "";
      return (
        <div key={idx}>
          <div
            className={`flex items-center gap-2 px-3 ${isMobile ? "py-3" : "py-2"} cursor-pointer transition-colors ${
              selectedPath === item.path
                ? isDarkMode
                  ? "bg-purple-900 border-l-4 border-purple-500"
                  : "bg-blue-100 border-l-4 border-blue-500"
                : isDarkMode
                  ? "hover:bg-gray-700"
                  : "hover:bg-gray-100"
            }`}
            style={{ paddingLeft: "12px" }}
            onClick={() => {
              setSelectedPath(item.path);
              setSelectedName(item.name);
              if (isMobile) setActivePanel("main");
            }}
          >
            <input
              type="checkbox"
              aria-label={`Select ${item.type === "folder" ? "folder" : "file"} ${item.name}`}
              checked={selectedPaths.some((x) => x.path === item.path)}
              onChange={(e) => {
                e.stopPropagation();
                handleTogglePathSelect(item.path);
              }}
              className={`w-4 h-4 rounded text-purple-600 focus:ring-purple-500 cursor-pointer ${
                isDarkMode
                  ? "bg-gray-700 border-gray-600"
                  : "bg-white border-gray-300"
              }`}
            />
            <span
              className={`flex-shrink-0 ${item.type === "folder" ? "text-yellow-600" : "text-blue-600"}`}
            >
              {item.type === "folder" ? <FolderIcon /> : <FileIcon />}
            </span>
            <div className="flex flex-col min-w-0 flex-1">
              <span
                className={`text-sm font-medium ${isDarkMode ? "text-gray-200" : "text-gray-700"} truncate`}
              >
                {item.name}
              </span>
              <span
                className={`text-[10px] ${isDarkMode ? "text-gray-500" : "text-gray-400"} flex items-center gap-1.5 truncate`}
                title={parentPath}
              >
                {item.mtime ? <span>{formatMtime(item.mtime)}</span> : null}
                {item.type === "file" && item.size ? (
                  <span>• {formatSize(item.size)}</span>
                ) : null}
                <span>• {parentPath}</span>
              </span>
            </div>
          </div>
        </div>
      );
    });
  };

  const renderFileTree = (items, level = 0) => {
    const sorted = sortItems(items);
    return sorted.map((item, idx) => {
      const isLoading = item.type === "folder" && loadingFolders.has(item.path);
      return (
        <div key={idx}>
          <div
            className={`flex items-center gap-2 px-3 ${isMobile ? "py-3" : "py-2"} cursor-pointer transition-colors ${
              selectedPath === item.path
                ? isDarkMode
                  ? "bg-purple-900 border-l-4 border-purple-500"
                  : "bg-blue-100 border-l-4 border-blue-500"
                : isDarkMode
                  ? "hover:bg-gray-700"
                  : "hover:bg-gray-100"
            }`}
            style={{ paddingLeft: `${level * 20 + 12}px` }}
            onClick={() => {
              if (item.type === "folder") {
                toggleFolder(item.path);
              }
              setSelectedPath(item.path);
              setSelectedName(item.name);
              if (isMobile && item.type !== "folder") setActivePanel("main");
            }}
          >
            <input
              type="checkbox"
              aria-label={`Select ${item.type === "folder" ? "folder" : "file"} ${item.name}`}
              checked={selectedPaths.some((x) => x.path === item.path)}
              onChange={(e) => {
                e.stopPropagation();
                handleTogglePathSelect(item.path);
              }}
              className={`w-4 h-4 rounded text-purple-600 focus:ring-purple-500 cursor-pointer ${
                isDarkMode
                  ? "bg-gray-700 border-gray-600"
                  : "bg-white border-gray-300"
              }`}
            />
            <span
              className={`flex-shrink-0 ${isLoading ? "text-purple-500" : "text-yellow-600"}`}
            >
              {item.type === "folder" ? (
                isLoading ? (
                  <SpinnerIcon />
                ) : expandedFolders.has(item.path) ? (
                  <FolderOpenIcon />
                ) : (
                  <FolderIcon />
                )
              ) : (
                <span className="text-blue-600">
                  <FileIcon />
                </span>
              )}
            </span>
            <div className="flex flex-col min-w-0 flex-1">
              <span
                className={`text-sm font-medium ${isDarkMode ? "text-gray-200" : "text-gray-700"} truncate`}
              >
                {item.name}
                {isLoading && (
                  <span
                    className={`ml-2 text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                  >
                    Loading...
                  </span>
                )}
              </span>
              <span
                className={`text-[10px] ${isDarkMode ? "text-gray-500" : "text-gray-400"} flex items-center gap-1.5 truncate`}
              >
                {item.mtime ? <span>{formatMtime(item.mtime)}</span> : null}
                {item.type === "file" && item.size ? (
                  <span>• {formatSize(item.size)}</span>
                ) : null}
                {item.subtitle ? (
                  <span title={item.subtitle}>• {item.subtitle}</span>
                ) : null}
              </span>
            </div>
          </div>
          {item.type === "folder" &&
            expandedFolders.has(item.path) &&
            item.children &&
            item.children.length > 0 && (
              <div>{renderFileTree(item.children, level + 1)}</div>
            )}
        </div>
      );
    });
  };

  // Render description file tree
  const renderDescFileTree = (items, level = 0) => {
    return items.map((item, idx) => {
      const isLoading =
        item.type === "folder" && descLoadingFolders.has(item.path);
      return (
        <div key={idx}>
          <div
            className={`flex items-center gap-2 px-3 ${isMobile ? "py-3" : "py-2"} cursor-pointer transition-colors ${
              descFilePath === item.path
                ? isDarkMode
                  ? "bg-green-900 border-l-4 border-green-500"
                  : "bg-green-100 border-l-4 border-green-500"
                : isDarkMode
                  ? "hover:bg-gray-700"
                  : "hover:bg-gray-100"
            }`}
            style={{ paddingLeft: `${level * 20 + 12}px` }}
            onClick={() => {
              if (item.type === "folder") {
                toggleDescFolder(item.path);
              } else {
                // Update the argument directly with the selected file path
                updateDescFile(item.path);
              }
            }}
          >
            <span
              className={`flex-shrink-0 ${isLoading ? "text-green-500" : "text-yellow-600"}`}
            >
              {item.type === "folder" ? (
                isLoading ? (
                  <SpinnerIcon />
                ) : descExpandedFolders.has(item.path) ? (
                  <FolderOpenIcon />
                ) : (
                  <FolderIcon />
                )
              ) : (
                <span className="text-green-600">
                  <FileIcon />
                </span>
              )}
            </span>
            <div className="flex flex-col min-w-0">
              <span
                className={`text-sm font-medium ${isDarkMode ? "text-gray-200" : "text-gray-700"} truncate`}
              >
                {item.name}
                {isLoading && (
                  <span
                    className={`ml-2 text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                  >
                    Loading...
                  </span>
                )}
              </span>
              {item.subtitle && (
                <span
                  className={`text-xs ${isDarkMode ? "text-gray-500" : "text-gray-400"} truncate`}
                  title={item.subtitle}
                >
                  {item.subtitle}
                </span>
              )}
            </div>
          </div>
          {item.type === "folder" &&
            descExpandedFolders.has(item.path) &&
            item.children &&
            item.children.length > 0 && (
              <div>{renderDescFileTree(item.children, level + 1)}</div>
            )}
        </div>
      );
    });
  };

  const executeSinglePath = async (path, newSessionId) => {
    // Validate --descfile: must have a valid description file path
    if (hasDescFile) {
      if (!descFilePath) {
        appendSystemMessage(
          "✗ Please select or enter a description file path when using --descfile",
          "error",
        );
        return false;
      }
      const pathValidation = isValidDescFilePath(descFilePath);
      if (!pathValidation.valid) {
        appendSystemMessage(
          `✗ Invalid description file: ${pathValidation.error}`,
          "error",
        );
        return false;
      }
    }

    // Validate --desclink: must have a valid URL
    if (hasDescLink) {
      if (!descLinkUrl) {
        appendSystemMessage(
          "✗ Please enter a description URL when using --desclink",
          "error",
        );
        return false;
      }
      if (!isValidUrl(descLinkUrl)) {
        appendSystemMessage(
          "✗ Please enter a valid paste URL for --desclink (pastebin, hastebin, etc.)",
          "error",
        );
        return false;
      }
    }

    setSessionId(newSessionId);
    setProgressItems([]);
    if (lastFullHashRef) lastFullHashRef.current = "";

    appendSystemMessage("");
    appendSystemMessage(`$ python upload.py "${path}" ${customArgs}`);
    appendSystemMessage("→ Starting execution...");

    let localController = null;

    try {
      const controller = new AbortController();
      sseAbortControllerRef.current = controller;
      localController = controller;

      const response = await apiFetch(`${API_BASE}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: path,
          args: customArgs,
          session_id: newSessionId,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errText = await response.text();
        appendSystemMessage(
          `✗ Execute failed (${response.status}): ${errText || "Request failed"}`,
          "error",
        );
        return false;
      }
      if (!response.body) {
        appendSystemMessage("✗ Execute failed: empty response body", "error");
        return false;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let exitCode = null;

      const processSSELine = (line) => {
        if (localController && localController.signal.aborted) return;
        if (!line.trim() || !line.startsWith("data: ")) return;
        try {
          const data = JSON.parse(line.substring(6));
          if (data.type === "html" || data.type === "html_full") {
            try {
              const rawHtml = data.data || "";
              const clean = sanitizeHtml(rawHtml);
              const rootContainer = richOutputRef.current;
              if (data.type === "html_full") {
                const shortSample = clean.slice(0, 200);
                const key = `${clean.length}:${shortSample}`;
                if (lastFullHashRef.current !== key) {
                  lastFullHashRef.current = key;
                  const wrapper = document.createElement("div");
                  wrapper.innerHTML = clean;
                  if (rootContainer) rootContainer.appendChild(wrapper);
                  setTimeout(() => {
                    const last =
                      rootContainer && rootContainer.lastElementChild;
                    if (last && last.scrollIntoView)
                      last.scrollIntoView({ block: "end" });
                    else if (rootContainer)
                      rootContainer.scrollTop = rootContainer.scrollHeight;
                  }, 0);
                }
                return;
              }
              appendHtmlFragment(clean);
            } catch (e) {
              console.error("Failed to render HTML fragment:", e);
            }
          } else if (data.type === "progress") {
            applyProgressEvent(data.data || {});
          } else if (data.type === "exit") {
            if (!(localController && localController.signal.aborted)) {
              appendSystemMessage("");
              appendSystemMessage(`✓ Process exited with code ${data.code}`);
              exitCode = data.code;
            }
          }
        } catch (e) {
          console.error("Parse error:", e);
        }
      };

      /* eslint-disable no-constant-condition */
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          if (buffer) {
            const finalLines = buffer.split("\n");
            for (const line of finalLines) {
              processSSELine(line);
            }
          }
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n");
        buffer = parts.pop();

        for (const line of parts) {
          processSSELine(line);
        }
      }
      /* eslint-enable no-constant-condition */

      if (!(localController && localController.signal.aborted)) {
        appendSystemMessage("✓ Execution completed");
        appendSystemMessage("");
        return exitCode === 0 || exitCode === null;
      }
      return false;
    } catch (error) {
      if (!(localController && localController.signal.aborted)) {
        appendSystemMessage("✗ Execution error: " + error.message, "error");
      }
      return false;
    } finally {
      setProgressItems([]);
      try {
        if (sseAbortControllerRef.current === localController) {
          sseAbortControllerRef.current = null;
        }
      } catch (e) {
        /* ignore */
      }
    }
  };

  const executeCommand = async () => {
    if (selectedPaths.length > 1) {
      setIsExecuting(true);
      const rootContainer = richOutputRef.current;
      if (rootContainer) {
        rootContainer.innerHTML = "";
      }

      try {
        const response = await apiFetch(`${API_BASE}/save_queue`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items: selectedPaths }),
        });

        if (!response.ok) {
          const errText = await response.text();
          appendSystemMessage(
            `✗ Failed to generate queue file: ${errText}`,
            "error",
          );
          setIsExecuting(false);
          return;
        }

        const data = await response.json();
        if (!data.success || !data.path) {
          appendSystemMessage(
            `✗ Failed to generate queue file: ${data.error || "Unknown error"}`,
            "error",
          );
          setIsExecuting(false);
          return;
        }

        const newSessionId = "session_" + Date.now();
        await executeSinglePath(data.path, newSessionId);
      } catch (error) {
        appendSystemMessage(
          `✗ Error generating queue: ${error.message}`,
          "error",
        );
      } finally {
        setIsExecuting(false);
        setSessionId("");
      }
      return;
    }

    const path =
      selectedPaths.length === 1 ? selectedPaths[0].path : selectedPath;
    if (!path) {
      appendSystemMessage("✗ Please select a file or folder first", "error");
      return;
    }

    const rootContainer = richOutputRef.current;
    setIsExecuting(true);
    if (rootContainer) {
      rootContainer.innerHTML = "";
    }

    const newSessionId = "session_" + Date.now();
    await executeSinglePath(path, newSessionId);

    setIsExecuting(false);
    setSessionId("");
  };

  const clearTerminal = async () => {
    // If a process is running, kill it first
    if (isExecuting && sessionId) {
      try {
        // Abort the SSE fetch so the client stops processing incoming events
        if (sseAbortControllerRef.current) {
          try {
            sseAbortControllerRef.current.abort();
          } catch (e) {
            /* ignore */
          }
        }
        await apiFetch(`${API_BASE}/kill`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }),
        });

        appendSystemMessage("✗ Process terminated by user", "error");

        setIsExecuting(false);
        setSessionId("");
        setProgressItems([]);
      } catch (error) {
        console.error("Failed to kill process:", error);
      }
    }

    // Clear the rich output container
    const container = richOutputRef.current;
    if (container) {
      container.innerHTML = "";
      setProgressItems([]);
      appendSystemMessage("Upload-Assistant Interactive Output");
      appendSystemMessage(
        '\nQuick Start:\n  1. Select a file or folder from the left panel\n  2. Add Upload-Assistant arguments (optional)\n  3. Click "Execute Upload" to start\n',
      );
    }
  };

  // Sidebar resizing
  const startResizing = useCallback(() => {
    setIsResizing(true);
  }, [setIsResizing]);

  const stopResizing = useCallback(() => {
    setIsResizing(false);
  }, [setIsResizing]);

  const resize = useCallback(
    (e) => {
      const newWidth = e.clientX;
      if (newWidth >= SIDEBAR_MIN_WIDTH && newWidth <= LEFT_SIDEBAR_MAX_WIDTH) {
        setSidebarWidth(newWidth);
        storage.set(LEFT_SIDEBAR_WIDTH_KEY, String(newWidth));
      }
    },
    [setSidebarWidth],
  );

  useEffect(() => {
    if (isResizing) {
      window.addEventListener("mousemove", resize);
      window.addEventListener("mouseup", stopResizing);
      return () => {
        window.removeEventListener("mousemove", resize);
        window.removeEventListener("mouseup", stopResizing);
      };
    }
  }, [isResizing, resize, stopResizing]);

  // Right sidebar resizing
  const startResizingRight = useCallback(() => {
    setIsResizingRight(true);
  }, [setIsResizingRight]);

  const stopResizingRight = useCallback(() => {
    setIsResizingRight(false);
  }, [setIsResizingRight]);

  const resizeRight = useCallback(
    (e) => {
      // Calculate width from right edge
      const newWidth = window.innerWidth - e.clientX;
      if (
        newWidth >= SIDEBAR_MIN_WIDTH &&
        newWidth <= RIGHT_SIDEBAR_MAX_WIDTH
      ) {
        setRightSidebarWidth(newWidth);
        storage.set(RIGHT_SIDEBAR_WIDTH_KEY, String(newWidth));
      }
    },
    [setRightSidebarWidth],
  );

  useEffect(() => {
    if (isResizingRight) {
      window.addEventListener("mousemove", resizeRight);
      window.addEventListener("mouseup", stopResizingRight);
      return () => {
        window.removeEventListener("mousemove", resizeRight);
        window.removeEventListener("mouseup", stopResizingRight);
      };
    }
  }, [isResizingRight, resizeRight, stopResizingRight]);

  // argumentCategories moved to module scope

  // Append only the plain argument flag to the input (no example values)
  const addArgument = (arg) => {
    setCustomArgs((prev) => (prev && prev.length ? `${prev} ${arg}` : arg));
  };

  const saveArgumentPreset = async () => {
    const name = argumentPresetName.trim();
    const argumentsValue = customArgs.trim();
    if (!name || !argumentsValue) return;

    try {
      const response = await apiFetch(`${API_BASE}/argument_presets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, arguments: argumentsValue }),
      });
      const data = await response.json();
      if (!response.ok || !data.success)
        throw new Error(data.error || "Save failed");
      setArgumentPresets(data.presets || []);
      setSelectedArgumentPreset(name);
      setArgumentPresetName("");
    } catch (error) {
      console.error("Failed to save argument preset:", error);
    }
  };

  const loadArgumentPreset = (name) => {
    setSelectedArgumentPreset(name);
    const preset = argumentPresets.find((item) => item.name === name);
    if (preset) setCustomArgs(preset.arguments);
  };

  const deleteArgumentPreset = async () => {
    if (!selectedArgumentPreset) return;

    try {
      const response = await apiFetch(`${API_BASE}/argument_presets`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: selectedArgumentPreset }),
      });
      const data = await response.json();
      if (!response.ok || !data.success)
        throw new Error(data.error || "Delete failed");
      setArgumentPresets(data.presets || []);
      setSelectedArgumentPreset("");
    } catch (error) {
      console.error("Failed to delete argument preset:", error);
    }
  };

  const renderArgumentPresetControls = (isMobileView = false) => (
    <div className={`space-y-2 ${isMobileView ? "pt-1" : ""}`}>
      <div className="flex gap-2">
        <select
          value={selectedArgumentPreset}
          onChange={(e) => loadArgumentPreset(e.target.value)}
          className={`min-w-0 flex-1 px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent ${
            isDarkMode
              ? "bg-gray-700 border-gray-600 text-white"
              : "bg-white border-gray-300 text-gray-900"
          }`}
          disabled={isExecuting || argumentPresets.length === 0}
          aria-label="Saved argument presets"
        >
          <option value="">Saved argument presets</option>
          {argumentPresets.map((preset) => (
            <option key={preset.name} value={preset.name}>
              {preset.name}
            </option>
          ))}
        </select>
        <button
          onClick={deleteArgumentPreset}
          disabled={isExecuting || !selectedArgumentPreset}
          className="px-3 py-2 text-sm font-medium rounded-lg border border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed dark:hover:bg-red-950"
          title="Delete selected preset"
        >
          Delete
        </button>
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={argumentPresetName}
          onChange={(e) => setArgumentPresetName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              saveArgumentPreset();
            }
          }}
          placeholder="Preset name"
          className={`min-w-0 flex-1 px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent ${
            isDarkMode
              ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
              : "bg-white border-gray-300 text-gray-900 placeholder-gray-400"
          }`}
          disabled={isExecuting}
        />
        <button
          onClick={saveArgumentPreset}
          disabled={
            isExecuting || !argumentPresetName.trim() || !customArgs.trim()
          }
          className="px-3 py-2 text-sm font-medium rounded-lg bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
          title="Save current arguments as a named preset"
        >
          Save
        </button>
      </div>
      <p
        className={`text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
      >
        Saving an existing name updates that preset.
      </p>
    </div>
  );

  // Toggle section collapse
  const toggleSectionCollapse = (title) => {
    setCollapsedSections((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(title)) {
        newSet.delete(title);
      } else {
        newSet.add(title);
      }
      return newSet;
    });
  };

  // Collapse all sections
  const collapseAllSections = () => {
    setCollapsedSections(new Set(argumentCategories.map((cat) => cat.title)));
  };

  // Expand all sections
  const expandAllSections = () => {
    setCollapsedSections(new Set());
  };

  // Filter argument categories based on search
  const getFilteredCategories = () => {
    if (!argSearchFilter.trim()) {
      return argumentCategories;
    }
    const searchLower = argSearchFilter.toLowerCase();
    return argumentCategories
      .map((cat) => {
        const filteredArgs = cat.args.filter(
          (a) =>
            a.label.toLowerCase().includes(searchLower) ||
            (a.description &&
              a.description.toLowerCase().includes(searchLower)) ||
            (a.placeholder &&
              a.placeholder.toLowerCase().includes(searchLower)),
        );
        if (filteredArgs.length > 0) {
          return { ...cat, args: filteredArgs };
        }
        // Also include category if title matches
        if (cat.title.toLowerCase().includes(searchLower)) {
          return cat;
        }
        return null;
      })
      .filter(Boolean);
  };

  const filteredCategories = getFilteredCategories();

  const saveExecutionDescription = async (content = descriptionDraft) => {
    if (!sessionId || descriptionAction) return;
    setDescriptionAction("save");
    try {
      const response = await apiFetch(`${API_BASE}/execution_description`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          content,
          version: descriptionVersion,
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.success) {
        if (response.status === 409 && Number.isInteger(data?.version)) {
          descriptionVersionRef.current = data.version;
          setDescriptionVersion(data.version);
          setExecutionDescription((current) => ({
            ...current,
            version: data.version,
          }));
        }
        window.alert(data?.error || "Could not save the description.");
        return;
      }
      setDescriptionDraft(data.content || "");
      descriptionVersionRef.current = data.version || 0;
      setDescriptionVersion(data.version || 0);
      setDescriptionDirty(false);
      setExecutionDescription((current) => ({
        ...current,
        content: data.content,
        version: data.version,
      }));
    } catch (error) {
      console.error("Could not save the description:", error);
      window.alert("Could not save the description.");
    } finally {
      setDescriptionAction("");
    }
  };

  const resetExecutionDescription = async (sourceKey) => {
    if (!sessionId || descriptionAction) return;
    setDescriptionAction(`reset:${sourceKey}`);
    try {
      const response = await apiFetch(
        `${API_BASE}/execution_description/reset`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            source_key: sourceKey,
            version: descriptionVersion,
          }),
        },
      );
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.success) {
        if (response.status === 409 && Number.isInteger(data?.version)) {
          descriptionVersionRef.current = data.version;
          setDescriptionVersion(data.version);
          setExecutionDescription((current) => ({
            ...current,
            version: data.version,
          }));
        }
        window.alert(
          data?.error || "Could not restore the description source.",
        );
        return;
      }
      setDescriptionDraft(data.content || "");
      descriptionVersionRef.current = data.version || 0;
      setDescriptionVersion(data.version || 0);
      setDescriptionDirty(false);
    } catch (error) {
      console.error("Could not restore the description source:", error);
      window.alert("Could not restore the description source.");
    } finally {
      setDescriptionAction("");
    }
  };

  const applyDescriptionBbcode = (openingTag, closingTag) => {
    const editor = descriptionEditorRef.current;
    if (!editor) return;

    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const selectedText = descriptionDraft.slice(start, end);
    const nextDraft = `${descriptionDraft.slice(0, start)}${openingTag}${selectedText}${closingTag}${descriptionDraft.slice(end)}`;
    const selectionStart = start + openingTag.length;
    const selectionEnd = selectionStart + selectedText.length;

    descriptionVersionRef.current = Math.max(
      descriptionVersionRef.current,
      descriptionVersion,
    );
    setDescriptionDraft(nextDraft);
    setDescriptionDirty(true);
    window.requestAnimationFrame(() => {
      editor.focus();
      editor.setSelectionRange(selectionStart, selectionEnd);
    });
  };

  const renderDescriptionPanel = () => {
    const sources = Array.isArray(executionDescription?.sources)
      ? executionDescription.sources
      : [];
    return (
      <div className="flex h-full flex-col">
        <div
          className={`border-b p-3 ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gradient-to-l from-sky-50 to-indigo-50"}`}
        >
          <h2
            className={`text-base font-bold ${isDarkMode ? "text-white" : "text-gray-800"}`}
          >
            Description review
          </h2>
          <p
            className={`mt-1 text-xs ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}
          >
            Edit the base description before tracker-specific formatting is
            applied.
          </p>
        </div>
        <div className="flex flex-1 min-h-0 flex-col gap-3 overflow-hidden p-3">
          <section
            className={`rounded-lg border p-2 ${isDarkMode ? "border-gray-700 bg-gray-800" : "border-gray-200 bg-white"}`}
          >
            <p
              className={`mb-2 text-xs font-bold uppercase tracking-wide ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
            >
              Sources
            </p>
            {sources.length ? (
              <div className="overflow-x-auto pb-1">
                <div className="flex w-max gap-2">
                  {sources.map((source) => (
                    <button
                      key={source.key}
                      onClick={() => resetExecutionDescription(source.key)}
                      disabled={Boolean(descriptionAction)}
                      className={`whitespace-nowrap rounded px-3 py-2 text-left text-xs ${isDarkMode ? "bg-gray-700 text-gray-200 hover:bg-gray-600" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}
                      title={`Restore ${source.label}`}
                    >
                      {descriptionAction === `reset:${source.key}`
                        ? "Restoring…"
                        : source.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-xs text-gray-500">
                No description sources are available yet.
              </p>
            )}
          </section>
          <section className="flex min-h-[24rem] flex-1 flex-col">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div
                className={`inline-flex rounded-md p-1 ${isDarkMode ? "bg-gray-800" : "bg-gray-100"}`}
              >
                {["edit", "preview"].map((view) => (
                  <button
                    key={view}
                    onClick={() => setDescriptionView(view)}
                    aria-pressed={descriptionView === view}
                    className={`rounded px-3 py-1 text-xs font-semibold capitalize ${descriptionView === view ? "bg-purple-600 text-white" : isDarkMode ? "text-gray-300 hover:bg-gray-700" : "text-gray-600 hover:bg-white"}`}
                  >
                    {view}
                  </button>
                ))}
              </div>
              {descriptionView === "preview" && (
                <span
                  className={`text-right text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                >
                  Preview only. Other elements such as logos and screenshots
                  will be added later.
                </span>
              )}
            </div>
            {descriptionView === "edit" ? (
              <>
                <div
                  role="toolbar"
                  aria-label="Description formatting"
                  className={`mb-2 flex flex-wrap gap-1 rounded-lg border p-1.5 ${isDarkMode ? "border-gray-700 bg-gray-800" : "border-gray-200 bg-gray-50"}`}
                >
                  {[
                    ["Bold", "B", "[b]", "[/b]"],
                    ["Italic", "I", "[i]", "[/i]"],
                    ["Underline", "U", "[u]", "[/u]"],
                    ["Strikethrough", "S", "[s]", "[/s]"],
                    ["Code", "Code", "[code]", "[/code]"],
                    ["Quote", "Quote", "[quote]", "[/quote]"],
                    ["Spoiler", "Spoiler", "[spoiler]", "[/spoiler]"],
                    ["Align left", "Left", "[left]", "[/left]"],
                    ["Align center", "Center", "[center]", "[/center]"],
                    ["Align right", "Right", "[right]", "[/right]"],
                  ].map(([label, text, openingTag, closingTag]) => (
                    <button
                      key={label}
                      type="button"
                      title={label}
                      aria-label={label}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() =>
                        applyDescriptionBbcode(openingTag, closingTag)
                      }
                      className={`rounded px-2 py-1 text-xs font-semibold hover:bg-purple-600 hover:text-white ${isDarkMode ? "text-gray-200" : "text-gray-700"}`}
                    >
                      {text}
                    </button>
                  ))}
                </div>
                <textarea
                  ref={descriptionEditorRef}
                  value={descriptionDraft}
                  onChange={(event) => {
                    descriptionVersionRef.current = Math.max(
                      descriptionVersionRef.current,
                      descriptionVersion,
                    );
                    setDescriptionDraft(event.target.value);
                    setDescriptionDirty(true);
                  }}
                  onBlur={() => {
                    if (descriptionDirty) saveExecutionDescription();
                  }}
                  spellCheck={false}
                  aria-label="Base description"
                  className={`min-h-[20rem] flex-1 resize-y rounded-lg border p-3 font-mono text-xs leading-5 ${isDarkMode ? "border-gray-700 bg-gray-950 text-gray-100" : "border-gray-300 bg-white text-gray-800"}`}
                  placeholder="The editable base description will appear here."
                />
              </>
            ) : (
              <div
                className={`bbcode-preview min-h-[20rem] flex-1 overflow-auto whitespace-pre-wrap rounded-lg border p-3 text-sm leading-6 [&_a]:text-sky-400 [&_a]:underline [&_blockquote]:my-3 [&_blockquote]:border-l-4 [&_blockquote]:border-purple-500 [&_blockquote]:pl-3 [&_details]:my-3 [&_img]:my-3 [&_img]:max-w-full [&_img]:rounded [&_pre]:overflow-auto [&_pre]:font-mono [&_table]:my-3 [&_table]:border-collapse [&_td]:border [&_td]:p-2 [&_th]:border [&_th]:p-2 ${isDarkMode ? "border-gray-700 bg-gray-950 text-gray-100 [&_td]:border-gray-700 [&_th]:border-gray-700" : "border-gray-300 bg-white text-gray-800 [&_td]:border-gray-300 [&_th]:border-gray-300"}`}
                dangerouslySetInnerHTML={{
                  __html: renderBbcodePreview(descriptionDraft),
                }}
              />
            )}
            <div className="mt-2 flex items-center justify-between gap-3">
              <span
                className={`text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
              >
                {descriptionDraft.length.toLocaleString()} characters{" "}
                {descriptionDirty ? "· Unsaved changes" : "· Saved"}
              </span>
              <button
                onClick={() => saveExecutionDescription()}
                disabled={Boolean(descriptionAction) || !descriptionDirty}
                className="rounded-md bg-purple-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-purple-700 disabled:opacity-50"
              >
                {descriptionAction === "save" ? "Saving…" : "Save description"}
              </button>
            </div>
          </section>
        </div>
      </div>
    );
  };

  const renderScreenshotsPanel = () => {
    const isWorking = Boolean(screenshotActionId);
    const expandedItem = executionScreenshots.find(
      (screenshot) => screenshot.id === expandedScreenshot,
    );
    const screenshotGroups = executionScreenshots.reduce(
      (groups, screenshot) => {
        const group = screenshot.group || "main";
        (groups[group] ||= []).push(screenshot);
        return groups;
      },
      {},
    );
    const screenshotGroupLabel = (group) => {
      if (group === "main") return "Main";
      return group.startsWith("PLAYLIST_")
        ? `Extra playlist ${group.slice("PLAYLIST_".length)}`
        : group.startsWith("FILE_")
          ? `Extra disc ${group.slice("FILE_".length)}`
          : "Extra disc";
    };
    return (
      <>
        <div className="flex flex-col h-full">
          <div
            className={`p-3 border-b flex-shrink-0 ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gradient-to-l from-purple-50 to-indigo-50"}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2
                  className={`text-base font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
                >
                  <ScreenshotsIcon />
                  Generated Screenshots
                </h2>
                <p
                  className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}
                >
                  Review frames before image hosting. Replacements use a
                  different point in the video.
                </p>
              </div>
              <button
                onClick={() => addExecutionScreenshot("main")}
                disabled={isWorking || !canAddExecutionScreenshot}
                className="p-2 rounded-md bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50"
                title="Capture an additional screenshot"
                aria-label="Capture an additional screenshot"
              >
                {screenshotActionId === "add" ? <SpinnerIcon /> : <PlusIcon />}
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            {executionScreenshots.length === 0 ? (
              <div
                className={`rounded-lg border p-5 text-center text-sm ${isDarkMode ? "border-gray-700 bg-gray-800 text-gray-400" : "border-gray-200 bg-gray-50 text-gray-500"}`}
              >
                If the media being uploaded requires screenshots, they will
                appear here as soon as the local capture is complete.
              </div>
            ) : (
              <div className="space-y-5">
                {Object.entries(screenshotGroups).map(
                  ([group, screenshots]) => (
                    <section key={group}>
                      <div
                        className={`mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
                      >
                        <span>{screenshotGroupLabel(group)}</span>
                        <span
                          className={`rounded-full px-1.5 py-0.5 normal-case tracking-normal ${isDarkMode ? "bg-gray-700 text-gray-300" : "bg-gray-100 text-gray-600"}`}
                        >
                          {screenshots.length}
                        </span>
                        <button
                          onClick={() => addExecutionScreenshot(group)}
                          disabled={isWorking || !canAddExecutionScreenshot}
                          className="ml-auto rounded-md bg-purple-600 px-2 py-1 normal-case tracking-normal text-white hover:bg-purple-700 disabled:opacity-50"
                        >
                          Add to this group
                        </button>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {screenshots.map((screenshot, index) => {
                          const replacing =
                            screenshotActionId === `replace:${screenshot.id}`;
                          const deleting =
                            screenshotActionId === `delete:${screenshot.id}`;
                          const undoing =
                            screenshotActionId === `undo:${screenshot.id}`;
                          const screenshotState =
                            screenshot.source === "remote"
                              ? "Remote"
                              : screenshot.source === "replacement"
                                ? "Pending upload"
                                : screenshot.source === "addition"
                                  ? "Pending upload"
                                  : "Local";
                          const screenshotStateClass =
                            screenshot.source === "remote"
                              ? isDarkMode
                                ? "bg-sky-950 text-sky-300"
                                : "bg-sky-100 text-sky-700"
                              : screenshot.source === "replacement"
                                ? isDarkMode
                                  ? "bg-amber-950 text-amber-300"
                                  : "bg-amber-100 text-amber-700"
                                : screenshot.source === "addition"
                                  ? isDarkMode
                                    ? "bg-emerald-950 text-emerald-300"
                                    : "bg-emerald-100 text-emerald-700"
                                  : isDarkMode
                                    ? "bg-gray-700 text-gray-300"
                                    : "bg-gray-100 text-gray-600";
                          return (
                            <article
                              key={screenshot.id}
                              className={`rounded-xl overflow-hidden border ${isDarkMode ? "border-gray-700 bg-gray-800" : "border-gray-200 bg-white"}`}
                            >
                              <img
                                src={screenshot.image_url}
                                alt={`Screenshot ${index + 1}`}
                                className={`w-full aspect-video object-contain bg-black transition-all duration-300 ${replacing ? "opacity-35 brightness-50" : "opacity-100 brightness-100"}`}
                                loading="lazy"
                              />
                              <div className="p-2.5 flex items-center justify-between gap-2">
                                <div className="min-w-0 flex-1">
                                  <span
                                    className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${screenshotStateClass}`}
                                  >
                                    {screenshotState}
                                  </span>
                                  <span
                                    className={`mt-1 block truncate text-[11px] font-mono ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                                    title={screenshot.filename}
                                  >
                                    {screenshot.filename}
                                  </span>
                                </div>
                                <div className="flex gap-1.5 flex-shrink-0">
                                  {screenshot.can_replace && (
                                    <button
                                      onClick={() =>
                                        changeExecutionScreenshot(
                                          screenshot.id,
                                          "replace",
                                        )
                                      }
                                      disabled={isWorking}
                                      className="px-2 py-1 text-xs rounded-md bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50"
                                    >
                                      {replacing ? "Generating…" : "Replace"}
                                    </button>
                                  )}
                                  <button
                                    onClick={() =>
                                      setExpandedScreenshot(screenshot.id)
                                    }
                                    disabled={isWorking}
                                    className={`p-1.5 rounded-md disabled:opacity-50 ${isDarkMode ? "text-gray-200 hover:bg-gray-700" : "text-gray-600 hover:bg-gray-100"}`}
                                    title={`Expand ${screenshot.filename}`}
                                    aria-label={`Expand ${screenshot.filename}`}
                                  >
                                    <ExpandIcon />
                                  </button>
                                  {screenshot.can_delete && (
                                    <button
                                      onClick={() =>
                                        changeExecutionScreenshot(
                                          screenshot.id,
                                          "delete",
                                        )
                                      }
                                      disabled={isWorking}
                                      className="p-1.5 rounded-md text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 disabled:opacity-50"
                                      title={`Delete ${screenshot.filename}`}
                                    >
                                      {deleting ? (
                                        <SpinnerIcon />
                                      ) : (
                                        <TrashIcon />
                                      )}
                                    </button>
                                  )}
                                  {screenshot.source === "replacement" && (
                                    <button
                                      onClick={() =>
                                        changeExecutionScreenshot(
                                          screenshot.id,
                                          "undo",
                                        )
                                      }
                                      disabled={isWorking}
                                      className={`px-2 py-1 text-xs rounded-md disabled:opacity-50 ${isDarkMode ? "bg-gray-700 text-gray-100 hover:bg-gray-600" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}
                                      title="Restore the original remote screenshot"
                                    >
                                      {undoing ? "Restoring…" : "Undo"}
                                    </button>
                                  )}
                                </div>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  ),
                )}
              </div>
            )}
          </div>
        </div>
        {expandedItem && (
          <div
            ref={screenshotModalRef}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4"
            role="dialog"
            aria-modal="true"
            aria-label={`Expanded ${expandedItem.filename}`}
            tabIndex="-1"
            onClick={() => setExpandedScreenshot(null)}
            onKeyDown={(event) => {
              if (event.key === "Tab") {
                event.preventDefault();
                screenshotModalCloseRef.current?.focus();
              }
            }}
          >
            <div
              className="relative max-h-full max-w-full"
              onClick={(event) => event.stopPropagation()}
            >
              <button
                ref={screenshotModalCloseRef}
                onClick={() => setExpandedScreenshot(null)}
                className="absolute right-2 top-2 z-10 rounded-md bg-black/70 px-3 py-1.5 text-sm text-white hover:bg-black"
              >
                Close
              </button>
              <img
                src={expandedItem.image_url}
                alt={expandedItem.filename}
                className="max-h-[90vh] max-w-[92vw] object-contain"
              />
            </div>
          </div>
        )}
      </>
    );
  };

  const renderExecutionPreviewPanel = (compact = false) => {
    const media = executionPreview;
    const category = media?.category || "";
    const previewTitle =
      media?.title ||
      media?.name ||
      media?.filename ||
      "Detecting media metadata...";
    const subtitleParts = [media?.original_title, media?.year].filter(Boolean);
    const infoBadges = [
      media?.category,
      media?.media_type,
      media?.source,
      media?.resolution,
    ].filter(Boolean);
    const metadataSources = Array.isArray(media?.metadata_sources)
      ? media.metadata_sources.filter((source) => source && source.value)
      : [];
    const previewProviders =
      metadataSources.length > 0
        ? metadataSources
        : [
            media?.tmdb
              ? { key: "tmdb", label: "TMDb", value: String(media.tmdb) }
              : null,
            media?.imdb
              ? {
                  key: "imdb",
                  label: "IMDb",
                  value: String(media.imdb).startsWith("tt")
                    ? String(media.imdb)
                    : `tt${media.imdb}`,
                }
              : null,
          ].filter(Boolean);
    const genres = Array.isArray(media?.genres)
      ? media.genres.filter(Boolean).slice(0, 4)
      : [];
    const networks = Array.isArray(media?.networks)
      ? media.networks.filter(Boolean).slice(0, 3)
      : [];
    const panelPadding = compact ? "p-3" : "p-4";
    const titleSize = compact ? "text-base" : "text-lg";
    const posterHeight = compact ? "h-64" : "h-80";
    const episodeLabel =
      media?.episode_title ||
      media?.episode_name ||
      [media?.season, media?.episode].filter(Boolean).join(" ");
    const overviewText =
      category === "TV"
        ? media?.episode_overview || media?.overview
        : media?.overview;
    const music = media?.music || {};

    const detailRows = (rows) => rows.filter((row) => row.value);
    const renderDetailGrid = (title, rows) => {
      const visibleRows = detailRows(rows);
      if (visibleRows.length === 0) return null;

      return (
        <div
          className={`rounded-xl p-3 ${isDarkMode ? "bg-gray-800 border border-gray-700" : "bg-gray-50 border border-gray-200"}`}
        >
          <p
            className={`text-xs font-semibold uppercase tracking-wide mb-2 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
          >
            {title}
          </p>
          <div className="grid grid-cols-1 gap-2">
            {visibleRows.map((row) => (
              <div
                key={row.label}
                className="flex items-start justify-between gap-3"
              >
                <span
                  className={`text-xs font-semibold ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                >
                  {row.label}
                </span>
                <span
                  className={`text-xs text-right ${isDarkMode ? "text-gray-200" : "text-gray-800"}`}
                >
                  {row.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      );
    };

    const tvRows = detailRows([
      { label: "Episode", value: episodeLabel },
      {
        label: "Format",
        value:
          typeof media?.tv_pack === "boolean"
            ? media.tv_pack
              ? "Season Pack"
              : "Single Episode"
            : "",
      },
      { label: "Service", value: media?.service },
      { label: "Network", value: networks.join(", ") },
      { label: "Audio", value: media?.audio },
    ]);
    const movieRows = detailRows([
      { label: "Audio", value: media?.audio },
      { label: "Service", value: media?.service },
      { label: "Network", value: networks.join(", ") },
    ]);
    const bookRows = detailRows([
      { label: "Author", value: media?.author },
      { label: "Narrator", value: media?.narrator },
      { label: "Language", value: media?.book_language },
      { label: "Publisher", value: media?.publisher },
      { label: "Duration", value: media?.audiobook_duration },
      { label: "Bitrate", value: media?.audiobook_bitrate },
      {
        label: "Series",
        value: media?.book_series
          ? [
              media.book_series,
              media?.book_series_index ? `#${media.book_series_index}` : "",
            ]
              .filter(Boolean)
              .join(" ")
          : "",
      },
      {
        label: "Format",
        value:
          typeof media?.audiobook === "boolean"
            ? media.audiobook
              ? "Audiobook"
              : "Book"
            : "",
      },
    ]);
    const gameRows = detailRows([
      { label: "Platform", value: media?.platform },
      { label: "Version", value: media?.game_version },
      { label: "Release Type", value: media?.game_subcategory },
      { label: "Developer", value: media?.developer },
      { label: "Publisher", value: media?.publisher },
      { label: "Region", value: media?.game_region },
      { label: "System", value: media?.game_system },
    ]);
    const musicRows = detailRows([
      {
        label: "Artist",
        value: music?.artist
          ? `${music.artist}${music.artist_source ? ` (${music.artist_source})` : ""}`
          : "",
      },
      {
        label: "Album",
        value: music?.album
          ? `${music.album}${music.album_source ? ` (${music.album_source})` : ""}`
          : "",
      },
      {
        label: "Original Year",
        value: music?.original_year
          ? `${music.original_year}${music.year_source ? ` (${music.year_source})` : ""}`
          : "",
      },
      {
        label: "Release Type",
        value: music?.release_type
          ? `${music.release_type}${music.release_type_source ? ` (${music.release_type_source})` : ""}`
          : "",
      },
      {
        label: "Media",
        value: music?.media
          ? `${music.media}${music.media_source ? ` (${music.media_source})` : ""}`
          : "",
      },
      { label: "Audio", value: music?.technical || media?.audio },
      {
        label: "Tracks / Discs",
        value:
          music?.track_count || music?.disc_count
            ? `${music.track_count || "?"} / ${music.disc_count || "1"}`
            : "",
      },
      {
        label: "This Release",
        value: [
          music?.release_year,
          music?.retail_date,
          music?.release_label,
          music?.release_catalogue_number,
        ]
          .filter(Boolean)
          .join(" • "),
      },
      {
        label: "Edition",
        value: [music?.edition, music?.edition_year]
          .filter(Boolean)
          .join(" • "),
      },
    ]);
    const musicCheckRows = detailRows([
      {
        label: "Auxiliary Files",
        value: Array.isArray(music?.auxiliary)
          ? music.auxiliary.join(", ")
          : "",
      },
      {
        label: "Metadata Conflicts",
        value: Array.isArray(music?.conflicts)
          ? music.conflicts.join(", ")
          : "",
      },
    ]);
    let categorySection = null;
    if (category === "TV")
      categorySection = renderDetailGrid("TV Details", tvRows);
    else if (category === "BOOK")
      categorySection = renderDetailGrid("Book Details", bookRows);
    else if (category === "GAME")
      categorySection = renderDetailGrid("Game Details", gameRows);
    else if (category === "MUSIC")
      categorySection = renderDetailGrid("Music Details", musicRows);
    else categorySection = renderDetailGrid("Movie Details", movieRows);

    return (
      <div className="flex flex-col h-full">
        <div
          className={`${panelPadding} border-b flex-shrink-0 ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gradient-to-l from-amber-50 to-orange-50"}`}
        >
          <h2
            className={`${titleSize} font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
          >
            Now Processing
          </h2>
          <p
            className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}
          >
            The sidebar is showing live media metadata while the upload runs.
          </p>
        </div>

        <div className={`flex-1 overflow-y-auto ${panelPadding} space-y-4`}>
          <div
            className={`rounded-2xl overflow-hidden border ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-white"} shadow-sm`}
          >
            {media?.poster_url ? (
              <div
                className={`w-full ${posterHeight} flex items-center justify-center p-3 ${isDarkMode ? "bg-gray-950" : "bg-stone-100"}`}
              >
                <img
                  src={media.poster_url}
                  alt={previewTitle}
                  className="max-w-full max-h-full object-contain"
                />
              </div>
            ) : (
              <div
                className={`w-full ${posterHeight} flex flex-col items-center justify-center gap-2 ${isDarkMode ? "bg-gray-800 text-gray-400" : "bg-gray-100 text-gray-500"}`}
              >
                <span className="text-sm">Poster not available yet</span>
              </div>
            )}

            <div className={`${panelPadding} space-y-3`}>
              <div>
                <h3
                  className={`${titleSize} font-bold leading-tight ${isDarkMode ? "text-white" : "text-gray-900"}`}
                >
                  {previewTitle}
                </h3>
                {subtitleParts.length > 0 && (
                  <p
                    className={`text-sm mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}
                  >
                    {subtitleParts.join(" • ")}
                  </p>
                )}
              </div>

              {infoBadges.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {infoBadges.map((badge) => (
                    <span
                      key={badge}
                      className={`px-2.5 py-1 rounded-full text-xs font-semibold ${isDarkMode ? "bg-gray-800 text-gray-200 border border-gray-700" : "bg-orange-50 text-orange-700 border border-orange-200"}`}
                    >
                      {badge}
                    </span>
                  ))}
                </div>
              )}

              {previewProviders.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {previewProviders.map((source) => {
                    const providerClass = getMetadataProviderStyle(
                      source.key,
                      isDarkMode,
                    );
                    const content = (
                      <>
                        <span className="inline-flex items-center justify-center min-w-[2.6rem] px-2 h-6 rounded-full">
                          {renderMetadataProviderIcon(source.key, isDarkMode)}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-[11px] font-semibold font-mono truncate">
                            {source.value}
                          </span>
                        </span>
                      </>
                    );
                    const sharedClassName = `inline-flex items-center gap-1.5 max-w-full rounded-full border px-2.5 py-1 transition-colors ${providerClass}`;

                    if (source.url) {
                      return (
                        <a
                          key={`${source.key}-${source.value}`}
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                          className={`${sharedClassName} hover:brightness-105`}
                          title={`${source.label || source.key}: ${source.value}`}
                        >
                          {content}
                        </a>
                      );
                    }

                    return (
                      <div
                        key={`${source.key}-${source.value}`}
                        className={sharedClassName}
                        title={`${source.label || source.key}: ${source.value}`}
                      >
                        {content}
                      </div>
                    );
                  })}
                </div>
              )}

              {genres.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {genres.map((genre) => (
                    <span
                      key={genre}
                      className={`px-2 py-1 rounded-md text-xs ${isDarkMode ? "bg-purple-900/40 text-purple-200 border border-purple-800" : "bg-purple-50 text-purple-700 border border-purple-200"}`}
                    >
                      {genre}
                    </span>
                  ))}
                </div>
              )}

              {categorySection}

              {category === "MUSIC" &&
                renderDetailGrid("Release Checks", musicCheckRows)}

              {category === "MUSIC" &&
                Array.isArray(music?.warnings) &&
                music.warnings.length > 0 && (
                  <div
                    className={`rounded-xl p-3 border ${isDarkMode ? "bg-amber-950/30 border-amber-900 text-amber-100" : "bg-amber-50 border-amber-200 text-amber-900"}`}
                  >
                    <p className="text-xs font-semibold uppercase tracking-wide mb-2">
                      Music Validation
                    </p>
                    <ul className="space-y-1 text-xs leading-5">
                      {music.warnings.map((warning, index) => (
                        <li key={`${warning}-${index}`}>• {warning}</li>
                      ))}
                    </ul>
                  </div>
                )}

              <div
                className={`rounded-xl p-3 ${isDarkMode ? "bg-gray-800 border border-gray-700" : "bg-gray-50 border border-gray-200"}`}
              >
                <p
                  className={`text-xs font-semibold uppercase tracking-wide mb-2 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                >
                  {category === "MUSIC"
                    ? "Release Notes"
                    : category === "TV" && media?.episode_overview
                      ? "Episode Overview"
                      : "Overview"}
                </p>
                <p
                  className={`text-sm leading-6 ${isDarkMode ? "text-gray-200" : "text-gray-700"}`}
                >
                  {overviewText ||
                    (media?.status === "waiting"
                      ? "Metadata will appear here as soon as Upload-Assistant writes the first meta snapshot."
                      : category === "MUSIC"
                        ? "No release notes were supplied. Review the music details and validation above before continuing."
                        : "No overview available for this item.")}
                </p>
              </div>

              <div
                className={`rounded-xl p-3 ${isDarkMode ? "bg-gray-800 border border-gray-700" : "bg-gray-50 border border-gray-200"}`}
              >
                <p
                  className={`text-xs font-semibold uppercase tracking-wide mb-2 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                >
                  Source Path
                </p>
                <p
                  className={`text-xs break-all font-mono ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}
                >
                  {media?.path || selectedPath}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const isAwaitingTerminalInput = Boolean(
    isExecuting && executionPreview?.awaiting_input,
  );
  const isYesNoPrompt = Boolean(
    isAwaitingTerminalInput && executionPreview?.input_type === "yes_no",
  );

  // Mobile Layout
  if (isMobile) {
    const navButton = (panel, icon, label) => (
      <button
        key={panel}
        onClick={() => setActivePanel(panel)}
        aria-current={activePanel === panel ? "page" : undefined}
        className={`flex-1 flex flex-col items-center justify-center gap-1 py-2 transition-colors ${
          activePanel === panel
            ? "text-purple-400 border-t-2 border-purple-400"
            : isDarkMode
              ? "text-gray-400"
              : "text-gray-500"
        }`}
      >
        {icon}
        <span className="text-xs font-medium">{label}</span>
      </button>
    );

    return (
      <div
        className={`flex flex-col h-screen ${isDarkMode ? "bg-gray-900" : "bg-gray-50"}`}
      >
        {/* Mobile Header */}
        <div
          className={`flex items-center justify-between px-4 py-3 border-b flex-shrink-0 ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}
        >
          <h1
            className={`text-lg font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
          >
            <LogoIcon src={`${APP_BASE}/static/img/logo.svg`} />
            Upload-Assistant
          </h1>
          <div className="flex items-center gap-2">
            {renderThemePalette()}
            <a
              href={`${APP_BASE}/config`}
              aria-label="Config"
              title="Config"
              className={`p-2 rounded-lg transition-colors ${isDarkMode ? "text-gray-200 hover:bg-gray-700" : "text-gray-600 hover:bg-gray-100"}`}
            >
              <SettingsIcon />
            </a>
          </div>
        </div>

        {/* Mobile Content Area. Main panel always mounted (hidden when inactive) to preserve terminal output ref; Files and Args panels conditionally rendered */}
        <div className="flex-1 overflow-hidden relative">
          {/* Files Panel */}
          {activePanel === "files" &&
            (isExecuting ? (
              renderProgressWorkspace()
            ) : (
              <div className="flex flex-col h-full">
                <div
                  className={`p-3 border-b flex-shrink-0 ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gradient-to-r from-purple-50 to-blue-50"}`}
                >
                  <h2
                    className={`text-base font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
                  >
                    <FolderIcon />
                    File Browser
                  </h2>
                  <div className="relative mt-2">
                    <input
                      type="text"
                      value={fileBrowserSearch}
                      onChange={(e) => handleFileBrowserSearch(e.target.value)}
                      placeholder="Search files and folders..."
                      className={`w-full pl-8 pr-8 py-1.5 text-sm rounded border ${
                        isDarkMode
                          ? "bg-gray-800 border-gray-600 text-gray-200 placeholder-gray-500 focus:border-purple-500"
                          : "bg-white border-gray-300 text-gray-700 placeholder-gray-400 focus:border-blue-500"
                      } focus:outline-none focus:ring-1 ${isDarkMode ? "focus:ring-purple-500" : "focus:ring-blue-500"}`}
                    />
                    <svg
                      className={`absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDarkMode ? "text-gray-500" : "text-gray-400"}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                      />
                    </svg>
                    {fileBrowserSearch && (
                      <button
                        onClick={() => handleFileBrowserSearch("")}
                        className={`absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
                      >
                        <svg
                          className="w-3.5 h-3.5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M6 18L18 6M6 6l12 12"
                          />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>
                {renderSelectAllBar()}
                <div
                  className={`flex-1 overflow-y-auto ${hasDescFile && !descBrowserCollapsed ? "max-h-[50%]" : ""}`}
                >
                  {fileBrowserSearch ? (
                    fileBrowserSearchLoading ? (
                      <div
                        className={`p-4 text-center ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                      >
                        <SpinnerIcon />
                        <p className="text-sm mt-2">Searching...</p>
                      </div>
                    ) : (
                      <>
                        {fileBrowserSearchResults &&
                          fileBrowserSearchResults.truncated && (
                            <div
                              className={`px-3 py-1.5 text-xs ${isDarkMode ? "text-yellow-400 bg-gray-900" : "text-yellow-700 bg-yellow-50"} border-b ${isDarkMode ? "border-gray-700" : "border-yellow-200"}`}
                            >
                              Results limited to{" "}
                              {fileBrowserSearchResults.count} items
                            </div>
                          )}
                        {renderSearchResults(fileBrowserSearchResults)}
                      </>
                    )
                  ) : (
                    renderFileTree(directories)
                  )}
                </div>

                {/* Description File Browser */}
                {hasDescFile && (
                  <>
                    <div
                      className={`p-3 border-t flex-shrink-0 ${!descBrowserCollapsed ? "border-b" : ""} ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gradient-to-r from-green-50 to-emerald-50"} ${descBrowserCollapsed ? "cursor-pointer" : ""}`}
                      onClick={
                        descBrowserCollapsed
                          ? () => setDescBrowserCollapsed(false)
                          : undefined
                      }
                    >
                      <div className="flex items-center justify-between">
                        <h2
                          className={`text-base font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
                        >
                          <FileIcon />
                          Description File
                          {descBrowserCollapsed &&
                            descFilePath &&
                            !descFileError && (
                              <span className="text-green-500 ml-1">
                                <svg
                                  className="w-4 h-4 inline"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M5 13l4 4L19 7"
                                  />
                                </svg>
                              </span>
                            )}
                        </h2>
                        {descBrowserCollapsed ? (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setDescBrowserCollapsed(false);
                            }}
                            className={`p-1 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
                          >
                            <ChevronDownIcon />
                          </button>
                        ) : (
                          descFilePath &&
                          !descFileError && (
                            <button
                              onClick={() => setDescBrowserCollapsed(true)}
                              className={`p-1 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
                            >
                              <ChevronRightIcon />
                            </button>
                          )
                        )}
                      </div>
                      {descBrowserCollapsed && descFilePath ? (
                        <div className="flex items-center gap-2 mt-1">
                          <p
                            className={`text-xs ${descFileError ? (isDarkMode ? "text-red-400" : "text-red-600") : isDarkMode ? "text-green-400" : "text-green-700"} break-all font-mono flex-1`}
                          >
                            {descFilePath}
                          </p>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              updateDescFile("");
                              setDescBrowserCollapsed(false);
                            }}
                            className={`p-1 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
                          >
                            <svg
                              className="w-4 h-4"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M6 18L18 6M6 6l12 12"
                              />
                            </svg>
                          </button>
                        </div>
                      ) : (
                        !descBrowserCollapsed && (
                          <p
                            className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                          >
                            Select a .txt, .nfo, or .md file
                          </p>
                        )
                      )}
                    </div>
                    {!descBrowserCollapsed && (
                      <div className="flex-1 overflow-y-auto">
                        {descDirectories.length > 0 ? (
                          renderDescFileTree(descDirectories)
                        ) : (
                          <div
                            className={`p-4 text-center ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                          >
                            <p className="text-sm">
                              Loading description files...
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}

          {/* Main Upload Panel */}
          <div
            className={`flex flex-col h-full ${activePanel === "main" ? "" : "hidden"}`}
          >
            {/* Top controls */}
            {!isExecuting && (
              <div
                className={`p-3 space-y-3 border-b ${!isOutputExpanded ? "flex-1 overflow-y-auto" : "flex-shrink-0"} ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}
              >
                {renderSelectedPathOrQueue(true)}

                {/* Args input */}
                <input
                  type="text"
                  value={customArgs}
                  onChange={(e) => setCustomArgs(e.target.value)}
                  placeholder="--tmdb movie/12345 --trackers passthepopcorn,aither"
                  className={`w-full px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                  disabled={isExecuting}
                />
                {renderArgumentPresetControls(true)}

                {/* Desc Link Input */}
                {hasDescLink &&
                  (!descLinkUrl || descLinkFocused || descLinkError) && (
                    <div className="space-y-1">
                      <label
                        className={`text-xs font-semibold ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}
                      >
                        Description Link URL:
                      </label>
                      <input
                        type="url"
                        value={descLinkUrl}
                        onChange={(e) => updateDescLink(e.target.value)}
                        onFocus={() => setDescLinkFocused(true)}
                        onBlur={() => setDescLinkFocused(false)}
                        placeholder="https://pastebin.com/abc123"
                        className={`w-full px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent ${
                          descLinkError
                            ? "border-red-500 focus:ring-red-500"
                            : isDarkMode
                              ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                              : "bg-white border-gray-300 text-gray-900"
                        }`}
                        disabled={isExecuting}
                      />
                      {descLinkError && (
                        <p className="text-xs text-red-500">{descLinkError}</p>
                      )}
                    </div>
                  )}

                {hasDescFile && (descFileError || !descFilePath) && (
                  <div
                    className={`p-2 rounded-lg text-xs ${
                      descFileError
                        ? isDarkMode
                          ? "bg-red-900 border border-red-700 text-red-300"
                          : "bg-red-50 border border-red-200 text-red-700"
                        : isDarkMode
                          ? "bg-yellow-900 border border-yellow-700 text-yellow-300"
                          : "bg-yellow-50 border border-yellow-200 text-yellow-700"
                    }`}
                  >
                    {descFileError ||
                      "Select a description file from the Files panel"}
                  </div>
                )}

                {/* Execute & Kill buttons */}
                <div className="flex gap-2">
                  <button
                    onClick={executeCommand}
                    disabled={
                      (!selectedPath && selectedPaths.length === 0) ||
                      isExecuting
                    }
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors font-medium"
                  >
                    <PlayIcon />
                    {isExecuting
                      ? "Executing..."
                      : selectedPaths.length > 1
                        ? "Execute Queue"
                        : "Execute Upload"}
                  </button>
                  <button
                    onClick={clearTerminal}
                    aria-label={
                      isExecuting
                        ? "Kill process and clear terminal"
                        : "Clear terminal"
                    }
                    className={`flex items-center gap-1 px-3 py-3 rounded-lg transition-colors ${
                      isExecuting
                        ? "bg-red-600 hover:bg-red-700 text-white"
                        : "bg-gray-600 hover:bg-gray-700 text-white"
                    }`}
                    title={
                      isExecuting
                        ? "Kill process and clear terminal"
                        : "Clear terminal"
                    }
                  >
                    <TrashIcon />
                  </button>
                </div>
                {renderTrackerSelector()}
              </div>
            )}

            {/* Terminal output */}
            <div
              className={`${isExecuting || isOutputExpanded ? "flex-1 p-3" : "flex-none p-2"} flex flex-col min-h-0 overflow-hidden ${isDarkMode ? "bg-gray-900" : "bg-gray-100"}`}
            >
              <div
                className={`flex items-center gap-2 ${isExecuting || isOutputExpanded ? "mb-2" : ""} flex-shrink-0`}
              >
                <span className={isDarkMode ? "text-white" : "text-gray-800"}>
                  <TerminalIcon />
                </span>
                <h3
                  className={`text-sm font-bold ${isDarkMode ? "text-white" : "text-gray-800"}`}
                >
                  Output
                </h3>
                {isExecuting && (
                  <span className="ml-auto text-xs text-green-400 animate-pulse">
                    ● Running
                  </span>
                )}
                {isExecuting && (
                  <button
                    onClick={clearTerminal}
                    aria-label="Kill process and clear terminal"
                    title="Kill process and clear terminal"
                    className="flex items-center gap-1 rounded px-2 py-1 text-xs bg-red-600 hover:bg-red-700 text-white"
                  >
                    <TrashIcon />
                    Kill
                  </button>
                )}
                {!isExecuting && (
                  <button
                    onClick={() => setIsOutputExpanded((expanded) => !expanded)}
                    aria-expanded={isOutputExpanded}
                    title={
                      isOutputExpanded ? "Collapse output" : "Expand output"
                    }
                    className={`ml-auto flex items-center gap-1 rounded px-2 py-1 text-xs ${isDarkMode ? "text-gray-300 hover:bg-gray-700" : "text-gray-600 hover:bg-gray-200"}`}
                  >
                    <span
                      className={`transition-transform ${isOutputExpanded ? "rotate-180" : ""}`}
                    >
                      <ChevronDownIcon />
                    </span>
                    {isOutputExpanded ? "Collapse" : "Expand"}
                  </button>
                )}
              </div>
              <div
                ref={richOutputRef}
                id="rich-output"
                className={`rounded-lg overflow-auto p-2 border text-sm bg-black border-gray-700 text-white ${isExecuting || isOutputExpanded ? "flex-1" : "hidden"}`}
              ></div>
              {isExecuting && (
                <div
                  className={`mt-2 flex gap-2 ${isAwaitingTerminalInput ? "animate-pulse" : ""}`}
                >
                  {isYesNoPrompt && (
                    <>
                      <button
                        onClick={() => sendInput(sessionId, "yes")}
                        disabled={!sessionId || isSendingInput}
                        className="px-3 py-2 rounded-lg text-sm text-white bg-green-600 hover:bg-green-700 disabled:opacity-50"
                      >
                        Yes
                      </button>
                      <button
                        onClick={() => sendInput(sessionId, "no")}
                        disabled={!sessionId || isSendingInput}
                        className="px-3 py-2 rounded-lg text-sm text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
                      >
                        No
                      </button>
                    </>
                  )}
                  <input
                    ref={inputRef}
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        sendInput(sessionId, userInput);
                      }
                    }}
                    placeholder="Type input and press Enter"
                    className={`flex-1 px-3 py-2 text-sm rounded-lg border focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-shadow ${isDarkMode ? "bg-gray-700 text-white" : "bg-white text-gray-900"} ${isAwaitingTerminalInput ? (isDarkMode ? "border-amber-400 shadow-[0_0_0_2px_rgba(251,191,36,0.18)]" : "border-amber-500 shadow-[0_0_0_2px_rgba(245,158,11,0.18)]") : isDarkMode ? "border-gray-600" : "border-gray-300"}`}
                  />
                  <button
                    onClick={() => sendInput(sessionId, userInput)}
                    disabled={!sessionId || !userInput || isSendingInput}
                    className={`px-3 py-2 rounded-lg text-white disabled:opacity-50 text-sm ${isAwaitingTerminalInput ? "bg-amber-600 hover:bg-amber-700" : "bg-green-600 hover:bg-green-700"}`}
                  >
                    Send
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Args Panel */}
          {activePanel === "args" &&
            (isExecuting ? (
              renderExecutionPreviewPanel(true)
            ) : (
              <div className="flex flex-col h-full">
                <div
                  className={`p-3 border-b flex-shrink-0 ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gradient-to-l from-purple-50 to-blue-50"}`}
                >
                  <h2
                    className={`text-base font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
                  >
                    <TerminalIcon />
                    Arguments
                  </h2>
                </div>

                {/* Search and Collapse Controls */}
                <div
                  className={`p-3 border-b flex-shrink-0 ${isDarkMode ? "border-gray-700" : "border-gray-200"} space-y-2`}
                >
                  <div className="relative">
                    <div
                      className={`absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                    >
                      <SearchIcon />
                    </div>
                    <input
                      type="text"
                      value={argSearchFilter}
                      onChange={(e) => setArgSearchFilter(e.target.value)}
                      placeholder="Search arguments..."
                      className={`w-full pl-10 pr-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent ${
                        isDarkMode
                          ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                          : "bg-white border-gray-300 text-gray-900 placeholder-gray-500"
                      }`}
                    />
                    {argSearchFilter && (
                      <button
                        onClick={() => setArgSearchFilter("")}
                        className={`absolute inset-y-0 right-0 pr-3 flex items-center ${isDarkMode ? "text-gray-400 hover:text-gray-200" : "text-gray-500 hover:text-gray-700"}`}
                      >
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M6 18L18 6M6 6l12 12"
                          />
                        </svg>
                      </button>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={collapseAllSections}
                      className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium rounded-md border transition-colors ${
                        isDarkMode
                          ? "bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600"
                          : "bg-gray-100 border-gray-300 text-gray-600 hover:bg-gray-200"
                      }`}
                    >
                      <CollapseAllIcon />
                      Collapse All
                    </button>
                    <button
                      onClick={expandAllSections}
                      className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium rounded-md border transition-colors ${
                        isDarkMode
                          ? "bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600"
                          : "bg-gray-100 border-gray-300 text-gray-600 hover:bg-gray-200"
                      }`}
                    >
                      <ExpandAllIcon />
                      Expand All
                    </button>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto p-3 space-y-2">
                  {filteredCategories.length === 0 ? (
                    <div
                      className={`text-center py-8 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                    >
                      <p className="text-sm">
                        No arguments found matching &quot;{argSearchFilter}
                        &quot;
                      </p>
                    </div>
                  ) : (
                    filteredCategories.map((cat) => (
                      <div
                        key={cat.title}
                        className={`rounded-lg border ${isDarkMode ? "border-gray-700" : "border-gray-200"}`}
                      >
                        <button
                          onClick={() => toggleSectionCollapse(cat.title)}
                          className={`w-full flex items-center justify-between p-3 text-left transition-colors rounded-t-lg ${
                            isDarkMode
                              ? "hover:bg-gray-700"
                              : "hover:bg-gray-50"
                          } ${collapsedSections.has(cat.title) ? "rounded-b-lg" : ""}`}
                        >
                          <div className="flex-1">
                            <div
                              className={`text-sm font-bold ${isDarkMode ? "text-gray-100" : "text-gray-900"} flex items-center gap-2`}
                            >
                              <span
                                className={
                                  isDarkMode ? "text-gray-400" : "text-gray-500"
                                }
                              >
                                {collapsedSections.has(cat.title) ? (
                                  <ChevronRightIcon />
                                ) : (
                                  <ChevronDownIcon />
                                )}
                              </span>
                              {cat.title}
                              <span
                                className={`text-xs font-normal px-1.5 py-0.5 rounded ${isDarkMode ? "bg-gray-700 text-gray-400" : "bg-gray-200 text-gray-500"}`}
                              >
                                {cat.args.length}
                              </span>
                            </div>
                            {cat.subtitle &&
                              !collapsedSections.has(cat.title) && (
                                <div
                                  className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                                >
                                  {cat.subtitle}
                                </div>
                              )}
                          </div>
                        </button>
                        {!collapsedSections.has(cat.title) && (
                          <div
                            className={`px-3 pb-3 pt-2 ${isDarkMode ? "border-t border-gray-700" : "border-t border-gray-200"}`}
                          >
                            <div className="grid grid-cols-1 gap-2">
                              {cat.args.map((a) => (
                                <div
                                  key={a.label}
                                  className={`w-full p-2 rounded-lg border ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-100"}`}
                                >
                                  <div className="flex items-start justify-between gap-3">
                                    <button
                                      onClick={() =>
                                        addArgument(a.insert || a.label)
                                      }
                                      disabled={isExecuting}
                                      className={`px-3 py-1.5 text-sm font-mono rounded-md border ${isDarkMode ? "bg-gray-700 border-gray-600 text-white hover:bg-purple-600 hover:text-white" : "bg-white border-gray-200 text-gray-800 hover:bg-purple-600 hover:text-white"} transition-colors`}
                                    >
                                      {a.label}
                                    </button>
                                    <div className="flex-1 text-right">
                                      {a.placeholder && (
                                        <div
                                          className={`text-xs ${isDarkMode ? "text-gray-300" : "text-gray-500"} font-mono`}
                                        >
                                          {a.placeholder}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                  {a.description && (
                                    <div
                                      className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                                    >
                                      {a.description}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            ))}

          {/* Screenshot Review Panel */}
          {activePanel === "screenshots" && renderScreenshotsPanel()}
          {activePanel === "description" && renderDescriptionPanel()}
        </div>

        {/* Bottom Nav */}
        <div
          className={`flex border-t flex-shrink-0 ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}
        >
          {navButton(
            "files",
            isExecuting ? <ProgressIcon /> : <FolderIcon />,
            isExecuting ? "Progress" : "Files",
          )}
          {navButton(
            "main",
            <TerminalIcon />,
            isAwaitingTerminalInput ? "Input Required" : "Upload",
          )}
          {navButton(
            "args",
            isExecuting ? (
              mediaIconForCategory(executionPreview?.category)
            ) : (
              <SettingsIcon />
            ),
            isExecuting ? "Media" : "Arguments",
          )}
          {isExecuting &&
            navButton(
              "screenshots",
              <ScreenshotsIcon />,
              `Screens${executionScreenshots.length ? ` (${executionScreenshots.length})` : ""}`,
            )}
          {isExecuting &&
            navButton("description", <TerminalIcon />, "Description")}
        </div>
      </div>
    );
  }

  // Desktop Layout
  return (
    <div
      className={`flex h-screen ${isDarkMode ? "bg-gray-900" : "bg-gray-50"} overflow-hidden`}
    >
      {/* Left Sidebar - Resizable */}
      <div
        className={`${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"} border-r flex flex-col`}
        style={{
          width: `${sidebarWidth}px`,
          minWidth: "200px",
          maxWidth: "600px",
        }}
      >
        {isExecuting ? (
          renderProgressWorkspace()
        ) : (
          <>
            <div
              className={`p-4 border-b ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gradient-to-r from-purple-50 to-blue-50"}`}
            >
              <h2
                className={`text-lg font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
              >
                <FolderIcon />
                File Browser
              </h2>
              <div className="relative mt-2">
                <input
                  type="text"
                  value={fileBrowserSearch}
                  onChange={(e) => handleFileBrowserSearch(e.target.value)}
                  placeholder="Search files and folders..."
                  className={`w-full pl-8 pr-8 py-1.5 text-sm rounded border ${
                    isDarkMode
                      ? "bg-gray-800 border-gray-600 text-gray-200 placeholder-gray-500 focus:border-purple-500"
                      : "bg-white border-gray-300 text-gray-700 placeholder-gray-400 focus:border-blue-500"
                  } focus:outline-none focus:ring-1 ${isDarkMode ? "focus:ring-purple-500" : "focus:ring-blue-500"}`}
                />
                <svg
                  className={`absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDarkMode ? "text-gray-500" : "text-gray-400"}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
                {fileBrowserSearch && (
                  <button
                    onClick={() => handleFileBrowserSearch("")}
                    className={`absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
                  >
                    <svg
                      className="w-3.5 h-3.5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M6 18L18 6M6 6l12 12"
                      />
                    </svg>
                  </button>
                )}
              </div>
            </div>
            {renderSelectAllBar()}
            <div
              className={`${hasDescFile && !descBrowserCollapsed ? "flex-1 max-h-[50%]" : "flex-1"} overflow-y-auto`}
            >
              {fileBrowserSearch ? (
                fileBrowserSearchLoading ? (
                  <div
                    className={`p-4 text-center ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                  >
                    <SpinnerIcon />
                    <p className="text-sm mt-2">Searching...</p>
                  </div>
                ) : (
                  <>
                    {fileBrowserSearchResults &&
                      fileBrowserSearchResults.truncated && (
                        <div
                          className={`px-3 py-1.5 text-xs ${isDarkMode ? "text-yellow-400 bg-gray-900" : "text-yellow-700 bg-yellow-50"} border-b ${isDarkMode ? "border-gray-700" : "border-yellow-200"}`}
                        >
                          Results limited to {fileBrowserSearchResults.count}{" "}
                          items
                        </div>
                      )}
                    {renderSearchResults(fileBrowserSearchResults)}
                  </>
                )
              ) : (
                renderFileTree(directories)
              )}
            </div>

            {/* Description File Browser - shown when --descfile is in args */}
            {hasDescFile && (
              <>
                <div
                  className={`p-4 border-t ${!descBrowserCollapsed ? "border-b" : ""} ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gradient-to-r from-green-50 to-emerald-50"} ${descBrowserCollapsed ? "cursor-pointer" : ""}`}
                  onClick={
                    descBrowserCollapsed
                      ? () => setDescBrowserCollapsed(false)
                      : undefined
                  }
                >
                  <div className="flex items-center justify-between">
                    <h2
                      className={`text-lg font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
                    >
                      <FileIcon />
                      Description File
                      {descBrowserCollapsed &&
                        descFilePath &&
                        !descFileError && (
                          <span className="text-green-500 ml-1">
                            <svg
                              className="w-4 h-4 inline"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M5 13l4 4L19 7"
                              />
                            </svg>
                          </span>
                        )}
                    </h2>
                    {descBrowserCollapsed ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDescBrowserCollapsed(false);
                        }}
                        className={`p-1 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
                        title="Expand browser"
                      >
                        <ChevronDownIcon />
                      </button>
                    ) : (
                      descFilePath &&
                      !descFileError && (
                        <button
                          onClick={() => setDescBrowserCollapsed(true)}
                          className={`p-1 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
                          title="Collapse browser"
                        >
                          <ChevronRightIcon />
                        </button>
                      )
                    )}
                  </div>
                  {descBrowserCollapsed && descFilePath ? (
                    <div className="flex items-center gap-2 mt-2">
                      <p
                        className={`text-xs ${descFileError ? (isDarkMode ? "text-red-400" : "text-red-600") : isDarkMode ? "text-green-400" : "text-green-700"} break-all font-mono flex-1`}
                      >
                        {descFilePath}
                      </p>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          updateDescFile("");
                          setDescBrowserCollapsed(false);
                        }}
                        className={`p-1 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
                        title="Clear selection"
                      >
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M6 18L18 6M6 6l12 12"
                          />
                        </svg>
                      </button>
                    </div>
                  ) : (
                    !descBrowserCollapsed && (
                      <p
                        className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                      >
                        Select a .txt, .nfo, or .md file
                      </p>
                    )
                  )}
                </div>
                {!descBrowserCollapsed && (
                  <>
                    <div className="flex-1 overflow-y-auto">
                      {descDirectories.length > 0 ? (
                        renderDescFileTree(descDirectories)
                      ) : (
                        <div
                          className={`p-4 text-center ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                        >
                          <p className="text-sm">
                            Loading description files...
                          </p>
                        </div>
                      )}
                    </div>
                    {descFilePath && (
                      <div
                        className={`p-3 border-t ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-green-50"}`}
                      >
                        <p
                          className={`text-xs font-semibold ${isDarkMode ? "text-gray-300" : "text-gray-600"} mb-1`}
                        >
                          Selected Description:
                        </p>
                        <div className="flex items-center gap-2">
                          <p
                            className={`text-xs ${isDarkMode ? "text-green-400" : "text-green-700"} break-all font-mono flex-1`}
                          >
                            {descFilePath}
                          </p>
                          <button
                            onClick={() => updateDescFile("")}
                            className={`p-1 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
                            title="Clear selection"
                          >
                            <svg
                              className="w-4 h-4"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M6 18L18 6M6 6l12 12"
                              />
                            </svg>
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* Resize Handle */}
      <div
        className={`w-1 ${isDarkMode ? "bg-gray-700 hover:bg-purple-500" : "bg-gray-300 hover:bg-purple-500"} cursor-col-resize transition-colors`}
        onMouseDown={startResizing}
        style={{ userSelect: "none" }}
      />

      {/* Main Content */}
      <div className="relative flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Panel */}
        <div
          className={`${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"} border-b ${isExecuting ? "p-3" : "p-4"} ${!isExecuting && !isOutputExpanded ? "flex-1 overflow-y-auto" : "flex-shrink-0"}`}
        >
          <div
            className={`max-w-6xl mx-auto ${isExecuting ? "" : "space-y-4"}`}
          >
            {isExecuting ? (
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-green-400 animate-pulse">
                      ● Running
                    </span>
                    {selectedPath && (
                      <span
                        className={`text-xs uppercase tracking-wide ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                      >
                        Selected path
                      </span>
                    )}
                  </div>
                  {selectedPath && (
                    <p
                      className={`mt-1 truncate font-mono text-sm ${isDarkMode ? "text-white" : "text-gray-800"}`}
                      title={selectedPath}
                    >
                      {selectedPath}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => {
                    setIsScreenshotReviewOpen((open) => !open);
                    setIsDescriptionReviewOpen(false);
                  }}
                  aria-pressed={isScreenshotReviewOpen}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors flex-shrink-0 ${isScreenshotReviewOpen ? "bg-purple-600 text-white" : isDarkMode ? "bg-gray-700 hover:bg-gray-600 text-gray-100" : "bg-gray-100 hover:bg-gray-200 text-gray-700"}`}
                  title="Review generated screenshots"
                >
                  <ScreenshotsIcon />
                  Screenshots
                  {executionScreenshots.length
                    ? ` (${executionScreenshots.length})`
                    : ""}
                </button>
                <button
                  onClick={() => {
                    setIsDescriptionReviewOpen((open) => !open);
                    setIsScreenshotReviewOpen(false);
                  }}
                  aria-pressed={isDescriptionReviewOpen}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors flex-shrink-0 ${isDescriptionReviewOpen ? "bg-purple-600 text-white" : isDarkMode ? "bg-gray-700 hover:bg-gray-600 text-gray-100" : "bg-gray-100 hover:bg-gray-200 text-gray-700"}`}
                  title="Review and edit the base description"
                >
                  <TerminalIcon />
                  Description
                </button>
                <button
                  onClick={clearTerminal}
                  aria-label="Kill process and clear terminal"
                  className="flex items-center gap-2 px-4 py-2 rounded-lg transition-colors bg-red-600 hover:bg-red-700 text-white flex-shrink-0"
                  title="Kill process and clear terminal"
                >
                  <TrashIcon />
                  Kill
                </button>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <h1
                      className={`text-2xl font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
                    >
                      <LogoIcon
                        src={`${APP_BASE}/static/img/logo.svg`}
                        className="w-8 h-8"
                      />
                      Upload-Assistant Web UI
                    </h1>
                  </div>

                  {/* Controls */}
                  <div className="flex items-center gap-3">
                    {renderThemePalette()}
                    <a
                      href={`${APP_BASE}/config`}
                      aria-label="Config"
                      title="Config"
                      className={`p-2 rounded-lg transition-colors ${isDarkMode ? "text-gray-200 hover:bg-gray-700" : "text-gray-600 hover:bg-gray-100"}`}
                    >
                      <SettingsIcon />
                    </a>
                  </div>
                </div>

                {/* Selected Path Display / Queue */}
                {renderSelectedPathOrQueue(false)}

                {/* Arguments */}
                <div className="space-y-2">
                  <label
                    className={`text-sm font-semibold ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}
                  >
                    Additional Arguments:
                  </label>
                  <input
                    type="text"
                    value={customArgs}
                    onChange={(e) => setCustomArgs(e.target.value)}
                    placeholder="--tmdb movie/12345 --trackers passthepopcorn,aither,ulcx --no-edition --no-tag"
                    className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent ${
                      isDarkMode
                        ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                        : "bg-white border-gray-300 text-gray-900"
                    }`}
                    disabled={isExecuting}
                  />
                  {renderArgumentPresetControls()}
                </div>

                {/* Description Link URL Input - shown when --desclink is in args */}
                {/* Hide when valid URL and not focused; show when empty, focused, or invalid */}
                {hasDescLink &&
                  (!descLinkUrl || descLinkFocused || descLinkError) && (
                    <div className="space-y-2">
                      <label
                        className={`text-sm font-semibold ${isDarkMode ? "text-gray-300" : "text-gray-700"} flex items-center gap-2`}
                      >
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
                          />
                        </svg>
                        Description Link URL (pastebin, hastebin, etc.):
                      </label>
                      <input
                        type="url"
                        value={descLinkUrl}
                        onChange={(e) => updateDescLink(e.target.value)}
                        onFocus={() => setDescLinkFocused(true)}
                        onBlur={() => setDescLinkFocused(false)}
                        placeholder="https://pastebin.com/abc123"
                        className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent ${
                          descLinkError
                            ? "border-red-500 focus:ring-red-500"
                            : isDarkMode
                              ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                              : "bg-white border-gray-300 text-gray-900"
                        }`}
                        disabled={isExecuting}
                      />
                      {descLinkError && (
                        <p className="text-xs text-red-500 mt-1">
                          {descLinkError}
                        </p>
                      )}
                      {descLinkUrl && !descLinkError && (
                        <p className="text-xs text-green-500 mt-1">
                          Valid paste URL
                        </p>
                      )}
                    </div>
                  )}

                {/* Description File Status - only show on error or when no file selected */}
                {hasDescFile && (descFileError || !descFilePath) && (
                  <div
                    className={`p-3 rounded-lg ${
                      descFileError
                        ? isDarkMode
                          ? "bg-red-900 border border-red-700"
                          : "bg-red-50 border border-red-200"
                        : isDarkMode
                          ? "bg-yellow-900 border border-yellow-700"
                          : "bg-yellow-50 border border-yellow-200"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <svg
                        className={`w-4 h-4 ${
                          descFileError ? "text-red-500" : "text-yellow-500"
                        }`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        {descFileError ? (
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M6 18L18 6M6 6l12 12"
                          />
                        ) : (
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                          />
                        )}
                      </svg>
                      <span
                        className={`text-sm font-medium ${
                          descFileError
                            ? isDarkMode
                              ? "text-red-300"
                              : "text-red-700"
                            : isDarkMode
                              ? "text-yellow-300"
                              : "text-yellow-700"
                        }`}
                      >
                        {descFileError
                          ? "Invalid description file path"
                          : "Select a description file from the left panel or enter a path"}
                      </span>
                    </div>
                    {descFilePath && descFileError && (
                      <p
                        className={`text-xs mt-1 break-all font-mono ${isDarkMode ? "text-red-400" : "text-red-600"}`}
                      >
                        {descFilePath}
                      </p>
                    )}
                    {descFileError && (
                      <p
                        className={`text-xs mt-1 ${isDarkMode ? "text-red-400" : "text-red-600"}`}
                      >
                        {descFileError}
                      </p>
                    )}
                  </div>
                )}

                {/* Execute Button */}
                <div className="flex gap-2">
                  <button
                    onClick={executeCommand}
                    disabled={
                      (!selectedPath && selectedPaths.length === 0) ||
                      isExecuting
                    }
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors font-medium text-lg"
                  >
                    <PlayIcon />
                    {isExecuting
                      ? "Executing..."
                      : selectedPaths.length > 1
                        ? "Execute Queue"
                        : "Execute Upload"}
                  </button>
                  <button
                    onClick={clearTerminal}
                    aria-label={
                      isExecuting
                        ? "Kill process and clear terminal"
                        : "Clear terminal"
                    }
                    className={`flex items-center gap-2 px-4 py-3 rounded-lg transition-colors ${
                      isExecuting
                        ? "bg-red-600 hover:bg-red-700 text-white"
                        : "bg-gray-600 hover:bg-gray-700 text-white"
                    }`}
                    title={
                      isExecuting
                        ? "Kill process and clear terminal"
                        : "Clear terminal"
                    }
                  >
                    <TrashIcon />
                    {isExecuting ? "Kill & Clear" : "Clear"}
                  </button>
                </div>
                {renderTrackerSelector()}
              </>
            )}
          </div>
        </div>

        {/* Execution Output */}
        <div
          className={`${isExecuting || isOutputExpanded ? "flex-1 p-4" : "flex-none p-2"} ${isDarkMode ? "bg-gray-900" : "bg-gray-100"} flex flex-col min-h-0 overflow-hidden`}
          style={
            isExecuting || isOutputExpanded
              ? undefined
              : { flex: "0 0 auto", minHeight: 0 }
          }
        >
          <div
            className={`max-w-6xl mx-auto w-full ${isExecuting || isOutputExpanded ? "flex-1" : "flex-none"} flex flex-col min-h-0`}
          >
            <div
              className={`flex items-center gap-2 ${isExecuting || isOutputExpanded ? "mb-3" : ""} flex-shrink-0`}
            >
              <span className={isDarkMode ? "text-white" : "text-gray-800"}>
                <TerminalIcon />
              </span>
              <h3
                className={`text-lg font-bold ${isDarkMode ? "text-white" : "text-gray-800"}`}
              >
                Execution Output
              </h3>
              {isExecuting && (
                <span className="ml-auto text-sm text-green-400 animate-pulse">
                  ● Running
                </span>
              )}
              {!isExecuting && (
                <button
                  onClick={() => setIsOutputExpanded((expanded) => !expanded)}
                  aria-expanded={isOutputExpanded}
                  title={isOutputExpanded ? "Collapse output" : "Expand output"}
                  className={`ml-auto flex items-center gap-1.5 rounded px-3 py-1.5 text-sm ${isDarkMode ? "text-gray-300 hover:bg-gray-800" : "text-gray-600 hover:bg-gray-200"}`}
                >
                  <span
                    className={`transition-transform ${isOutputExpanded ? "rotate-180" : ""}`}
                  >
                    <ChevronDownIcon />
                  </span>
                  {isOutputExpanded ? "Collapse" : "Expand"}
                </button>
              )}
            </div>
            {/* Rich HTML output (rendered from Rich export_html fragments) */}
            <div
              ref={richOutputRef}
              id="rich-output"
              className={`rounded-lg overflow-auto p-3 border bg-black border-gray-700 text-white ${isExecuting || isOutputExpanded ? "flex-1" : "hidden"}`}
            ></div>
            {isExecuting && (
              <div
                className={`mt-2 flex gap-2 ${isAwaitingTerminalInput ? "animate-pulse" : ""}`}
              >
                {isYesNoPrompt && (
                  <>
                    <button
                      onClick={() => sendInput(sessionId, "yes")}
                      disabled={!sessionId || isSendingInput}
                      className="px-4 py-2 rounded-lg text-white bg-green-600 hover:bg-green-700 disabled:opacity-50"
                    >
                      Yes
                    </button>
                    <button
                      onClick={() => sendInput(sessionId, "no")}
                      disabled={!sessionId || isSendingInput}
                      className="px-4 py-2 rounded-lg text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
                    >
                      No
                    </button>
                  </>
                )}
                <input
                  ref={inputRef}
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      sendInput(sessionId, userInput);
                    }
                  }}
                  placeholder="Type input and press Enter"
                  className={`flex-1 px-3 py-2 rounded-lg border focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-shadow ${isDarkMode ? "bg-gray-700 text-white" : "bg-white text-gray-900"} ${isAwaitingTerminalInput ? (isDarkMode ? "border-amber-400 shadow-[0_0_0_2px_rgba(251,191,36,0.18)]" : "border-amber-500 shadow-[0_0_0_2px_rgba(245,158,11,0.18)]") : isDarkMode ? "border-gray-600" : "border-gray-300"}`}
                />
                <button
                  onClick={() => sendInput(sessionId, userInput)}
                  disabled={!sessionId || !userInput || isSendingInput}
                  className={`px-4 py-2 rounded-lg text-white disabled:opacity-50 ${isAwaitingTerminalInput ? "bg-amber-600 hover:bg-amber-700" : "bg-green-600 hover:bg-green-700"}`}
                >
                  Send
                </button>
              </div>
            )}
          </div>
        </div>
        {renderFloatingProgressPanel()}
      </div>
      {/* Right Resize Handle */}
      <div
        className={`w-1 ${isDarkMode ? "bg-gray-700 hover:bg-purple-500" : "bg-gray-300 hover:bg-purple-500"} cursor-col-resize transition-colors`}
        onMouseDown={startResizingRight}
        style={{ userSelect: "none" }}
      />

      {/* Right Sidebar - Arguments / Execution Preview */}
      <div
        className={`${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"} border-l flex flex-col`}
        style={{
          width: `${rightSidebarWidth}px`,
          minWidth: "200px",
          maxWidth: "800px",
        }}
      >
        {isExecuting ? (
          isScreenshotReviewOpen ? (
            renderScreenshotsPanel()
          ) : isDescriptionReviewOpen ? (
            renderDescriptionPanel()
          ) : (
            renderExecutionPreviewPanel()
          )
        ) : (
          <>
            <div
              className={`p-4 border-b ${isDarkMode ? "border-gray-700 bg-gray-900" : "border-gray-200 bg-gradient-to-l from-purple-50 to-blue-50"}`}
            >
              <h2
                className={`text-lg font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
              >
                <TerminalIcon />
                Arguments
              </h2>
            </div>

            {/* Search and Collapse Controls */}
            <div
              className={`p-3 border-b ${isDarkMode ? "border-gray-700" : "border-gray-200"} space-y-2`}
            >
              {/* Search Input */}
              <div className="relative">
                <div
                  className={`absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                >
                  <SearchIcon />
                </div>
                <input
                  type="text"
                  value={argSearchFilter}
                  onChange={(e) => setArgSearchFilter(e.target.value)}
                  placeholder="Search arguments..."
                  className={`w-full pl-10 pr-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                      : "bg-white border-gray-300 text-gray-900 placeholder-gray-500"
                  }`}
                />
                {argSearchFilter && (
                  <button
                    onClick={() => setArgSearchFilter("")}
                    className={`absolute inset-y-0 right-0 pr-3 flex items-center ${isDarkMode ? "text-gray-400 hover:text-gray-200" : "text-gray-500 hover:text-gray-700"}`}
                  >
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M6 18L18 6M6 6l12 12"
                      />
                    </svg>
                  </button>
                )}
              </div>

              {/* Collapse/Expand All Buttons */}
              <div className="flex gap-2">
                <button
                  onClick={collapseAllSections}
                  className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium rounded-md border transition-colors ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600"
                      : "bg-gray-100 border-gray-300 text-gray-600 hover:bg-gray-200"
                  }`}
                >
                  <CollapseAllIcon />
                  Collapse All
                </button>
                <button
                  onClick={expandAllSections}
                  className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium rounded-md border transition-colors ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600"
                      : "bg-gray-100 border-gray-300 text-gray-600 hover:bg-gray-200"
                  }`}
                >
                  <ExpandAllIcon />
                  Expand All
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {filteredCategories.length === 0 ? (
                <div
                  className={`text-center py-8 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                >
                  <p className="text-sm">
                    No arguments found matching &quot;{argSearchFilter}&quot;
                  </p>
                </div>
              ) : (
                filteredCategories.map((cat) => (
                  <div
                    key={cat.title}
                    className={`rounded-lg border ${isDarkMode ? "border-gray-700" : "border-gray-200"}`}
                  >
                    {/* Collapsible Section Header */}
                    <button
                      onClick={() => toggleSectionCollapse(cat.title)}
                      className={`w-full flex items-center justify-between p-3 text-left transition-colors rounded-t-lg ${
                        isDarkMode ? "hover:bg-gray-700" : "hover:bg-gray-50"
                      } ${collapsedSections.has(cat.title) ? "rounded-b-lg" : ""}`}
                    >
                      <div className="flex-1">
                        <div
                          className={`text-sm font-bold ${isDarkMode ? "text-gray-100" : "text-gray-900"} flex items-center gap-2`}
                        >
                          <span
                            className={
                              isDarkMode ? "text-gray-400" : "text-gray-500"
                            }
                          >
                            {collapsedSections.has(cat.title) ? (
                              <ChevronRightIcon />
                            ) : (
                              <ChevronDownIcon />
                            )}
                          </span>
                          {cat.title}
                          <span
                            className={`text-xs font-normal px-1.5 py-0.5 rounded ${isDarkMode ? "bg-gray-700 text-gray-400" : "bg-gray-200 text-gray-500"}`}
                          >
                            {cat.args.length}
                          </span>
                        </div>
                        {cat.subtitle && !collapsedSections.has(cat.title) && (
                          <div
                            className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                          >
                            {cat.subtitle}
                          </div>
                        )}
                      </div>
                    </button>

                    {/* Collapsible Section Content */}
                    {!collapsedSections.has(cat.title) && (
                      <div
                        className={`px-3 pb-3 pt-2 ${isDarkMode ? "border-t border-gray-700" : "border-t border-gray-200"}`}
                      >
                        <div className="grid grid-cols-[repeat(auto-fit,minmax(250px,1fr))] gap-2">
                          {cat.args.map((a) => (
                            <div
                              key={a.label}
                              className={`w-full p-2 rounded-lg border ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-100"}`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <button
                                  onClick={() =>
                                    addArgument(a.insert || a.label)
                                  }
                                  disabled={isExecuting}
                                  className={`px-3 py-1 text-sm font-mono rounded-md border ${isDarkMode ? "bg-gray-700 border-gray-600 text-white hover:bg-purple-600 hover:text-white" : "bg-white border-gray-200 text-gray-800 hover:bg-purple-600 hover:text-white"} transition-colors`}
                                >
                                  {a.label}
                                </button>
                                <div className="flex-1 text-right">
                                  {a.placeholder && (
                                    <div
                                      className={`text-xs ${isDarkMode ? "text-gray-300" : "text-gray-500"} font-mono`}
                                    >
                                      {a.placeholder}
                                    </div>
                                  )}
                                </div>
                              </div>
                              {a.description && (
                                <div
                                  className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                                >
                                  {a.description}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// Render the app
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<AudionutsUAGUI />);
