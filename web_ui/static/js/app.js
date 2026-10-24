const parseUploadPaths = (text) => {
  const seen = new Set();
  return text.split(/\r?\n/).flatMap((line, index) => {
    let path = line.trim();
    if (
      path.length >= 2 &&
      ((path.startsWith('"') && path.endsWith('"')) ||
        (path.startsWith("'") && path.endsWith("'")))
    ) {
      path = path.slice(1, -1);
    }
    if (!path || seen.has(path)) return [];
    seen.add(path);
    return [{ path, line: index + 1, args: "" }];
  });
};

/** True when `path` lies below `folder` (either separator style). */
const isInsidePath = (path, folder) =>
  path !== folder &&
  (path.startsWith(`${folder}/`) || path.startsWith(`${folder}\\`));

const getPreviewLanguageFlag = window.getUAPreviewLanguageFlag;

const { useState, useRef, useEffect, useLayoutEffect, useCallback } = React;
const screenshotMode = window.UAScreenshotMode;
const SCREENSHOT_POSTER_KEY = "ua_screenshot_poster";
const SCREENSHOT_BACKDROP_KEY = "ua_screenshot_backdrop";

const getStoredScreenshotArtwork = (key) => {
  try {
    const image = localStorage.getItem(key) || "";
    return /^data:image\/(png|jpeg|webp);base64,/.test(image) ? image : "";
  } catch (_error) {
    return "";
  }
};

function ScreenshotModeControls({ onPoster, onBackdrop }) {
  const [visible, setVisible] = useState(true);
  const [message, setMessage] = useState("");
  useEffect(() => {
    const toggle = (event) => {
      if (
        event.key.toLowerCase() === "h" &&
        !event.ctrlKey &&
        !event.altKey &&
        !event.metaKey &&
        !event.target.closest("input, textarea, select, [contenteditable]")
      )
        setVisible((value) => !value);
    };
    document.addEventListener("keydown", toggle);
    return () => document.removeEventListener("keydown", toggle);
  }, []);

  const selectArtwork = (event, label, storageKey, onSelect) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (
      !["image/png", "image/jpeg", "image/webp"].includes(file.type) ||
      file.size > 4 * 1024 * 1024
    ) {
      setMessage("Choose a PNG, JPEG or WebP image up to 4 MiB.");
      return;
    }
    const reader = new FileReader();
    reader.onerror = () =>
      setMessage(`Unable to read this ${label.toLowerCase()}.`);
    reader.onload = () => {
      onSelect(reader.result);
      try {
        localStorage.setItem(storageKey, reader.result);
        setMessage(`${label} saved in this browser.`);
      } catch (_error) {
        setMessage(
          `${label} loaded for this tab; browser storage is unavailable or full.`,
        );
      }
    };
    reader.readAsDataURL(file);
  };

  if (!visible) return null;
  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 rounded-lg border border-gray-600 bg-gray-900 text-white px-4 py-3 shadow-xl text-sm max-w-[90vw]">
      <div className="flex flex-wrap items-center gap-3">
        <strong>Screenshot mode</strong>
        <label className="cursor-pointer rounded bg-gray-700 px-3 py-1">
          Choose poster
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(event) =>
              selectArtwork(event, "Poster", SCREENSHOT_POSTER_KEY, onPoster)
            }
            className="sr-only"
          />
        </label>
        <label className="cursor-pointer rounded bg-gray-700 px-3 py-1">
          Choose backdrop
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(event) =>
              selectArtwork(
                event,
                "Backdrop",
                SCREENSHOT_BACKDROP_KEY,
                onBackdrop,
              )
            }
            className="sr-only"
          />
        </label>
        <button
          onClick={() => setVisible(false)}
          className="rounded bg-gray-700 px-3 py-1"
        >
          Hide controls (H)
        </button>
        <a href={window.location.pathname} className="underline">
          Exit demo
        </a>
      </div>
      <p className="mt-1 text-xs text-gray-300">
        Frozen fictional data · API actions disabled · Press H to show/hide
        controls.
      </p>
      {message && (
        <p role="status" className="mt-1 text-xs">
          {message}
        </p>
      )}
    </div>
  );
}
const THEME_KEY = "ua_config_theme";
const LEFT_SIDEBAR_WIDTH_KEY = "ua_webui_left_sidebar_width_v2";
const RIGHT_SIDEBAR_WIDTH_KEY = "ua_webui_right_sidebar_width";
const COLLAPSED_ARGUMENT_SECTIONS_KEY = "ua_webui_collapsed_argument_sections";
const ARGUMENT_VIEW_KEY = "ua_webui_argument_view";
const FAVORITE_ARGUMENTS_KEY = "ua_webui_favorite_arguments";
const FILE_BROWSER_CUSTOM_ORDER_KEY = "ua_webui_file_browser_custom_order";
const FILE_BROWSER_EXPANDED_KEY = "ua_webui_file_browser_expanded";
const FILE_BROWSER_SCROLL_KEY = "ua_webui_file_browser_scroll_top";
const FILE_BROWSER_SORT_KEY = "ua_webui_file_browser_sort";
const SHOW_AUDIO_TRACKS_KEY = "ua_webui_show_audio_tracks";
const SHOW_SUBTITLE_TRACKS_KEY = "ua_webui_show_subtitle_tracks";
const OUTPUT_MODE_KEY = "ua_webui_output_mode";
const RUN_GUI_RESULTS_COLLAPSED_KEY = "ua_webui_run_gui_results_collapsed";
const REVIEW_PANELS_IN_MODAL_KEY = "ua_webui_review_panels_in_modal";
const DEFAULT_LEFT_SIDEBAR_WIDTH = 256;
const DEFAULT_RIGHT_SIDEBAR_WIDTH = 320;
const APPLICATION_RAIL_WIDTH = 80;
const LEFT_SIDEBAR_MAX_WIDTH = 600;
const RIGHT_SIDEBAR_MAX_WIDTH = 800;
const COMPACT_LAYOUT_BREAKPOINT = 768;

const isMobileBrowserSession = () => {
  const clientHint = navigator.userAgentData?.mobile;
  if (clientHint === true) return true;

  return /Android.*Mobile|iPhone|iPod|BlackBerry|IEMobile|Opera Mini|Mobile.*Firefox/i.test(
    navigator.userAgent || "",
  );
};

const shouldUseMobileLayout = () =>
  window.innerWidth < COMPACT_LAYOUT_BREAKPOINT || isMobileBrowserSession();

// Each running tab holds one SSE stream; the server enforces the same limit.
// Idle tabs are cheap; only running uploads hold connections and server slots.
const MAX_UPLOAD_TABS = 24;
// Provided by the server; it enforces the limit even when this is missing.
const MAX_UPLOAD_PATHS = Number.isInteger(window.UA_MAX_UPLOAD_PATHS)
  ? window.UA_MAX_UPLOAD_PATHS
  : null;
const DEFAULT_MAX_RUNNING_UPLOADS = 4;
const SCHEDULE_POLL_MS = 3000;
// One /api/sessions request per interval serves every scheduled tab.
const sharedSessionsPoll = { promise: null, at: 0 };
const UPLOAD_TAB_DRAFTS_KEY = "ua.uploadTabDrafts.v1";
const BUSY_UPLOAD_STATUSES = ["running", "waiting", "input"];
// The server sends a keepalive every second; silence this long means a dead connection.
const SESSION_STREAM_STALL_MS = 20000;
const SESSION_RECONNECT_ATTEMPTS = 60;

const UPLOAD_TAB_STATUS_LABELS = {
  idle: "Idle",
  running: "Running",
  waiting: "Waiting for another tab to free a shared resource",
  input: "Waiting for your input",
  scheduled: "Scheduled: starts when an upload slot frees",
  done: "Finished",
  error: "Failed",
};

const createUploadTabForm = () => ({
  selectedPath: "",
  selectedPaths: [],
  manualPathsText: null,
  customArgs: "",
  pathInputError: "",
  selectedArgumentPreset: "",
  userInput: "",
});

const RunGui = window.UARunGui;

/** GUI state for a new view; the screenshot demo starts with its frozen events. */
const initialRunGuiState = () =>
  (screenshotMode?.guiEvents || []).reduce(
    RunGui.reduceRunGuiEvent,
    RunGui.createRunGuiState(),
  );

/** Per-tab state that must survive while the tab is not displayed. */
const createUploadTabRuntime = () => ({
  output: document.createElement("div"),
  controller: null,
  lastFullHash: "",
  // Last session event applied, so reconnects replay only what was missed.
  lastSeq: 0,
  // Server session shown in this tab; dismissed when the tab moves on.
  sessionRecord: "",
  // Waiting on the server for a free upload slot.
  scheduled: false,
  // Authoritative for every tab; React state mirrors only the active tab.
  run: { sessionId: "", isExecuting: false },
  // Snapshot of view state, read while the tab is in the background.
  view: {
    isTerminalView: false,
    progressItems: [],
    form: createUploadTabForm(),
  },
  awaiting: false,
  waiting: new Set(),
  result: "",
  // Structured run state for the GUI output mode; kept even while hidden.
  gui: RunGui.createRunGuiState(),
});

const getUploadTabStatus = (runtime) => {
  if (!runtime.run.isExecuting) return runtime.result || "idle";
  if (runtime.scheduled) return "scheduled";
  if (runtime.awaiting) return "input";
  return runtime.waiting.size ? "waiting" : "running";
};

const uploadTabFormHasContent = (form) =>
  Boolean(
    form &&
    (form.selectedPath ||
      form.selectedPaths?.length ||
      form.manualPathsText ||
      form.customArgs),
  );

/** Read prepared-but-not-started tab forms saved by this browser. */
const loadUploadTabDrafts = () => {
  try {
    const drafts = JSON.parse(
      window.localStorage.getItem(UPLOAD_TAB_DRAFTS_KEY) || "[]",
    );
    return Array.isArray(drafts)
      ? drafts.filter((draft) => uploadTabFormHasContent(draft?.form))
      : [];
  } catch (error) {
    return [];
  }
};

const saveUploadTabDrafts = (drafts) => {
  try {
    if (drafts.length) {
      window.localStorage.setItem(
        UPLOAD_TAB_DRAFTS_KEY,
        JSON.stringify(drafts),
      );
    } else {
      window.localStorage.removeItem(UPLOAD_TAB_DRAFTS_KEY);
    }
  } catch (error) {
    /* Storage can be unavailable (private mode, quota); drafts are a convenience. */
  }
};

const getUploadTabTitle = (items) => {
  if (items.length !== 1) return `Queue (${items.length})`;
  const parts = String(items[0].path || "")
    .split(/[\\/]/)
    .filter(Boolean);
  return parts[parts.length - 1] || items[0].path;
};

const storage = window.UAStorage;
const getStoredTheme = window.getUAStoredTheme;
const getStoredColorTheme = window.getUAStoredColorTheme;
const setColorTheme = window.setUAColorTheme;
const getStoredInterfaceStyle = window.getUAStoredInterfaceStyle;
const setInterfaceStyle = window.setUAInterfaceStyle;
const useModalFocus = window.useUAModalFocus;
const unit3dBbcode = window.UAUnit3dBbcode;
const YOUTUBE_EMBED_PREFIX = "https://www.youtube-nocookie.com/embed/";

const escapePreviewHtml = (value) =>
  String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

// Only absolute web URLs: tracker-relative links have no target in a preview.
const isSafePreviewUrl = (value) => {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch (_error) {
    return false;
  }
};

const sanitizeBbcodePreview = (html) => {
  if (!window.DOMPurify) {
    return `<div>${escapePreviewHtml(html).replace(/\n/g, "<br>")}</div>`;
  }

  // The parser escapes the source first, so inline styles only carry the
  // values its tag patterns accept (sizes, colors, fonts and alignment).
  const sanitized = window.DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "a",
      "b",
      "blockquote",
      "br",
      "button",
      "cite",
      "code",
      "details",
      "div",
      "figcaption",
      "figure",
      "h1",
      "h2",
      "h3",
      "h4",
      "h5",
      "h6",
      "hr",
      "i",
      "iframe",
      "img",
      "li",
      "ol",
      "p",
      "pre",
      "s",
      "small",
      "span",
      "sub",
      "summary",
      "sup",
      "table",
      "td",
      "th",
      "tr",
      "u",
      "ul",
    ],
    ALLOWED_ATTR: [
      "allow",
      "allowfullscreen",
      "class",
      "height",
      "href",
      "loading",
      "src",
      "style",
      "title",
      "type",
      "width",
    ],
  });
  const preview = new DOMParser().parseFromString(sanitized, "text/html");

  preview.querySelectorAll("iframe").forEach((frame) => {
    if (!frame.getAttribute("src")?.startsWith(YOUTUBE_EMBED_PREFIX)) {
      frame.remove();
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

const renderBbcodePreview = (content) => {
  const text = String(content || "");
  if (!unit3dBbcode) {
    return `<div>${escapePreviewHtml(text).replace(/\n/g, "<br>")}</div>`;
  }
  return sanitizeBbcodePreview(unit3dBbcode.parseUnit3dBbcode(text));
};

// Copy buttons on rendered [code] blocks, as on UNIT3D sites.
const handleBbcodePreviewClick = (event) => {
  const button = event.target.closest?.(".bbcode-rendered__clipboard-button");
  if (!button) return;
  const code = button
    .closest(".bbcode-rendered__clipboard")
    ?.querySelector("pre")?.textContent;
  if (code == null || !navigator.clipboard?.writeText) return;
  navigator.clipboard.writeText(code).then(
    () => {
      button.classList.add("bbcode-rendered__clipboard-button--copied");
      window.setTimeout(
        () =>
          button.classList.remove("bbcode-rendered__clipboard-button--copied"),
        1500,
      );
    },
    (error) => console.error("Could not copy the code block:", error),
  );
};

// Pointer coordinates are fractional under browser zoom or OS display scaling.
// Keeping panel widths on whole device pixels stops right-aligned mask icons
// from being resampled at a different sub-pixel offset on every resize step,
// which made them appear to grow and shrink while dragging.
const snapToDevicePixels = (width) => {
  const ratio = window.devicePixelRatio || 1;
  return Math.round(width * ratio) / ratio;
};

const getStoredSidebarWidth = (
  key,
  defaultWidth,
  maxWidth,
  minWidth = defaultWidth,
) => {
  const storedWidth = Number(storage.get(key));
  if (
    Number.isFinite(storedWidth) &&
    storedWidth >= minWidth &&
    storedWidth <= maxWidth
  ) {
    return snapToDevicePixels(storedWidth);
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

const getStoredFavoriteArguments = () => {
  try {
    const stored = JSON.parse(storage.get(FAVORITE_ARGUMENTS_KEY) || "[]");
    return Array.isArray(stored)
      ? stored.filter((id) => typeof id === "string")
      : [];
  } catch (error) {
    return [];
  }
};

const getStoredFileBrowserCustomOrder = () => {
  try {
    const storedOrder = JSON.parse(
      storage.get(FILE_BROWSER_CUSTOM_ORDER_KEY) || "[]",
    );
    return Array.isArray(storedOrder)
      ? storedOrder.filter((path) => typeof path === "string" && path)
      : [];
  } catch (error) {
    return [];
  }
};

const getStoredExpandedFolders = () => {
  try {
    const paths = JSON.parse(storage.get(FILE_BROWSER_EXPANDED_KEY) || "[]");
    return new Set(
      Array.isArray(paths)
        ? paths.filter((path) => typeof path === "string" && path)
        : [],
    );
  } catch (_error) {
    return new Set();
  }
};

const sortFolderPathsByDepth = (paths) =>
  [...paths].sort(
    (a, b) =>
      a.split(/[\\/]/).filter(Boolean).length -
      b.split(/[\\/]/).filter(Boolean).length,
  );

const getFileBrowserRestorePaths = (paths, roots) => {
  const restorePaths = new Set();
  for (const path of paths) {
    for (const root of roots) {
      const prefix = root.path.replace(/[\\/]+$/, "");
      const suffix = path.slice(prefix.length);
      if (
        path !== root.path &&
        (!path.startsWith(prefix) || !/^[\\/]/.test(suffix))
      )
        continue;
      restorePaths.add(root.path);
      // A collapsed ancestor may still contain a previously open descendant.
      for (const separator of suffix.matchAll(/[\\/]/g)) {
        const parent = path.slice(0, prefix.length + separator.index);
        if (parent.length > prefix.length) restorePaths.add(parent);
      }
      restorePaths.add(path);
    }
  }
  return sortFolderPathsByDepth(restorePaths);
};

const getStoredFileBrowserSort = () => {
  const storedSort = storage.get(FILE_BROWSER_SORT_KEY) || "name-asc";
  const [by, order] = storedSort.split("-");
  const validSorts = new Set(["name", "date", "size", "custom"]);
  const validOrders = new Set(["asc", "desc"]);
  return {
    by: validSorts.has(by) ? by : "name",
    order: validOrders.has(order) ? order : "asc",
  };
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
  screenshotMode?.apiFetch ||
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

const createUploadOutputFragment = (html) => {
  const wrapper = document.createElement("div");
  wrapper.innerHTML = sanitizeHtml(html);
  // Rich output is dynamic HTML; apply targets after the sanitizer strips them.
  wrapper.querySelectorAll("a[href]").forEach((link) => {
    try {
      const url = new URL(link.getAttribute("href"), window.location.href);
      if (
        (url.protocol === "http:" || url.protocol === "https:") &&
        url.origin !== window.location.origin
      ) {
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
    } catch (_error) {
      // Leave malformed and non-HTTP links to the existing sanitizer.
    }
  });
  return wrapper;
};

// The CLI parser owns option names, help text and value shapes. Keep only WebUI
// grouping, examples and pickers here. A row is a flag name, or an object that
// adds an example placeholder, a path picker ("file" or "folder"), a prefixed
// entry of a repeatable option, or a preset that inserts several options.
const argumentSections = [
  {
    id: "release",
    title: "Release",
    subtitle: "Getting these correct is 90% of a successful upload!",
    entries: [
      { flag: "--category", placeholder: "MOVIE" },
      { flag: "--type", placeholder: "REMUX" },
      { flag: "--source", placeholder: "Blu-ray" },
      { flag: "--resolution", placeholder: "2160p" },
      { flag: "--tag", placeholder: "GROUP" },
      { flag: "--service", placeholder: "SERVICE" },
      { flag: "--edition", placeholder: "TEXT" },
      { flag: "--region", placeholder: "REGION" },
      { flag: "--distributor", placeholder: "NAME" },
    ],
  },
  {
    id: "video-ids",
    title: "Metadata IDs",
    entries: [
      { flag: "--tmdb", placeholder: "movie/123" },
      { flag: "--imdb", placeholder: "tt0111161" },
      "--no-imdb",
      { flag: "--tvdb", placeholder: "ID" },
      { flag: "--tvmaze", placeholder: "ID" },
      { flag: "--mal", placeholder: "ID" },
      { flag: "--douban", placeholder: "ID" },
      "--no-metadata-cache",
    ],
  },
  {
    id: "tv",
    title: "TV Episode",
    entries: [
      { flag: "--season", placeholder: "S01" },
      { flag: "--episode", placeholder: "E01" },
      { flag: "--daily", placeholder: "YYYY-MM-DD" },
      { flag: "--manual-episode-title", placeholder: "TITLE" },
      "--no-season",
      "--not-anime",
    ],
  },
  {
    id: "title",
    title: "Title Shaping",
    entries: [
      { flag: "--name", placeholder: "RELEASE_NAME" },
      { flag: "--year", placeholder: "YYYY" },
      "--no-year",
      "--no-aka",
      "--no-dub",
      "--no-dual",
      "--dual-audio",
      "--no-tag",
      "--no-edition",
    ],
  },
  {
    id: "details",
    title: "Metadata Overrides",
    entries: [
      { flag: "--overview", placeholder: "SYNOPSIS" },
      { flag: "--genres", placeholder: "GENRE1,GENRE2" },
      { flag: "--cast", placeholder: "NAME1,NAME2" },
      { flag: "--keywords", placeholder: "keyword1,keyword2" },
      { flag: "--original-language", placeholder: "en" },
      { flag: "--only-if-languages", placeholder: "en,fr" },
      { flag: "--poster", placeholder: "URL_OR_PATH", path: "file" },
      { flag: "--banner", placeholder: "URL_OR_PATH", path: "file" },
    ],
  },
  {
    id: "disc",
    title: "Disc / Content Flags",
    entries: [
      { flag: "--disctype", placeholder: "BD50" },
      { flag: "--manual_dvds", placeholder: "2xDVD9+DVD5" },
      { flag: "--menus", placeholder: "FOLDER or auto", path: "folder" },
      "--untouched",
      "--extras",
      "--commentary",
      "--sfx-subtitles",
      "--hardcoded-subs",
      { flag: "--hardcoded-subs-language", placeholder: "LANG" },
      "--webdv",
      "--sorted-filelist",
      "--keep-folder",
    ],
  },
  {
    id: "screens",
    title: "Screenshots / Images",
    entries: [
      { flag: "--screens", placeholder: "N" },
      { flag: "--manual_frames", placeholder: "1,250,500" },
      { flag: "--comparison", placeholder: "FOLDER", path: "folder" },
      { flag: "--comparison_index", placeholder: "N" },
      "--imghost",
      "--skip-imagehost-upload",
      "--vapoursynth",
    ],
  },
  {
    id: "analysis",
    title: "Audio Spectrograms / HDR",
    subtitle:
      "Stream positions are zero-based. Plots for dynamic HDR are made only when the release has Dolby Vision or HDR10+ metadata.",
    entries: [
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
      "--audio-spectrogram",
      { flag: "--audio-spectrogram-tracks", placeholder: "0,1 or all" },
      "--dynamic-hdr-plot",
    ],
  },
  {
    id: "description",
    title: "Description / NFO",
    entries: [
      { flag: "--description", placeholder: "TEXT" },
      { flag: "--descfile", placeholder: "PATH" },
      { flag: "--desclink", placeholder: "URL" },
      "--nfo",
      "--keep-nfo",
    ],
  },
  {
    id: "music-release",
    title: "Music Release",
    entries: [
      { flag: "--music-artist", placeholder: "ARTIST" },
      { flag: "--music-album", placeholder: "TITLE" },
      "--music-release-type",
      "--music-media",
      { flag: "--music-release-year", placeholder: "YYYY" },
      { flag: "--music-edition-year", placeholder: "YYYY" },
      "--music-unknown-release",
      { flag: "--music-artist-role", placeholder: "NAME=ROLE; NAME=ROLE" },
    ],
  },
  {
    id: "music-edition",
    title: "Music Edition / Catalogue",
    entries: [
      { flag: "--music-label", placeholder: "LABEL" },
      { flag: "--music-catalogue-number", placeholder: "CATALOGUE" },
      { flag: "--music-genre", placeholder: "GENRE1,GENRE2" },
      { flag: "--music-watermark", placeholder: "NOTE" },
      { flag: "--music-lineage", placeholder: "PATH", path: "file" },
      "--music-showcase",
    ],
  },
  {
    id: "music-lookup",
    title: "Discogs / MusicBrainz",
    entries: [
      { flag: "--music-discogs-id", placeholder: "ID_OR_URL" },
      { flag: "--music-discogs-release-id", placeholder: "ID_OR_URL" },
      { flag: "--music-discogs-master-id", placeholder: "ID_OR_URL" },
      "--no-music-discogs",
      "--music-enrich",
      "--no-music-enrich",
    ],
  },
  {
    id: "music-orpheus",
    title: "Orpheus",
    entries: [
      { flag: "--music-request-id", placeholder: "ID_OR_URL" },
      { flag: "--music-group-id", placeholder: "ID_OR_URL" },
      "--music-check-log",
      {
        label: "Orpheus reference",
        flag: "--tracker-id",
        prefix: "ORPHEUS=",
        placeholder: "TORRENT_ID",
        description: "Orpheus torrent ID for music metadata enrichment",
      },
    ],
  },
  {
    id: "book",
    title: "Book / Audiobook",
    entries: [
      { flag: "--author", placeholder: "AUTHOR" },
      { flag: "--book-title", placeholder: "TITLE" },
      { flag: "--book-narrator", placeholder: "NAME" },
      { flag: "--book-translator", placeholder: "NAME" },
      { flag: "--book-language", placeholder: "LANG" },
      { flag: "--publisher", placeholder: "NAME" },
      { flag: "--isbn", placeholder: "ISBN" },
      { flag: "--asin", placeholder: "ASIN" },
      { flag: "--audible-url", placeholder: "URL" },
      { flag: "--openlibrary", placeholder: "ID" },
      "--comic",
      "--manga",
      "--magazine",
      "--newspaper",
      { flag: "--overview", placeholder: "SYNOPSIS" },
      { flag: "--genres", placeholder: "GENRE1,GENRE2" },
    ],
  },
  {
    id: "game",
    title: "Game",
    entries: [
      { flag: "--game-title", placeholder: "TITLE" },
      { flag: "--developer", placeholder: "NAME" },
      { flag: "--publisher", placeholder: "NAME" },
      "--platforms",
      { flag: "--game-version", placeholder: "v1.0" },
      "--game-subcategory",
      "--multi",
      { flag: "--igdb", placeholder: "ID" },
      { flag: "--steam", placeholder: "APP_ID_OR_URL" },
      { flag: "--overview", placeholder: "SYNOPSIS" },
      { flag: "--genres", placeholder: "GENRE1,GENRE2" },
    ],
  },
  {
    id: "tracker-refs",
    title: "Tracker References",
    subtitle:
      "Pull metadata ids, descriptions, and screenshots from these trackers",
    entries: [
      "--onlyID",
      { flag: "--tracker-id", placeholder: "TRACKER=ID or URL" },
      ...[
        ["PTP", "PTP"],
        ["BLU", "BLU"],
        ["Aither", "AITHER"],
        ["LST", "LST"],
        ["OE", "OE"],
        ["HDB", "HDB"],
        ["BTN", "BTN"],
        ["BHD", "BHD"],
        ["HUNO", "HUNO"],
        ["ULCX", "ULCX"],
      ].map(([name, tracker]) => ({
        label: `${name} reference`,
        flag: "--tracker-id",
        prefix: `${tracker}=`,
        placeholder: "TORRENT_ID",
        description: `${name} torrent ID`,
      })),
      { flag: "--torrenthash", placeholder: "HASH" },
    ],
  },
  {
    id: "upload-selection",
    title: "Trackers / Dupe Check",
    entries: [
      { flag: "--trackers", placeholder: "aither,blutopia,lst,etc" },
      { flag: "--trackers-remove", placeholder: "blutopia,xyz,etc" },
      { flag: "--trackers-pass", placeholder: "N" },
      "--skip-dupe-check",
      "--skip-dupe-asking",
      "--double-dupe-check",
      { flag: "--dupe-size-difference-tolerance", placeholder: "PERCENTAGE" },
      "--search_requests",
    ],
  },
  {
    id: "upload-flags",
    title: "Upload Flags / Site Specific",
    entries: [
      "--anon",
      "--personalrelease",
      "--stream",
      "--draft",
      "--modq",
      { flag: "--freeleech", placeholder: "25%" },
      { flag: "--freeleech-until", placeholder: "N" },
      { flag: "--exclusive", placeholder: "1" },
      "--featured",
      "--double-upload",
      { flag: "--double-upload-until", placeholder: "N" },
      "--sticky",
      "--refundable",
      "--foreign",
      "--opera",
      "--asian",
      { flag: "--channel", placeholder: "ID_OR_TAG" },
    ],
  },
  {
    id: "torrent",
    title: "Torrent Creation / Hashing",
    entries: [
      "--max-piece-size",
      "--nohash",
      "--rehash",
      "--mkbrr",
      { flag: "--entropy", placeholder: "N" },
      { flag: "--randomized", placeholder: "N" },
      { flag: "--infohash", placeholder: "HASH" },
      "--skip_auto_torrent",
      "--force-recheck",
    ],
  },
  {
    id: "client",
    title: "Torrent Client",
    entries: [
      "--no-seed",
      { flag: "--client", placeholder: "NAME" },
      { flag: "--qbit-tag", placeholder: "TAG" },
      { flag: "--qbit-cat", placeholder: "CATEGORY" },
      "--qbit-bw-control",
      "--qbit-bw-control-after-usenet",
      { flag: "--qbit-bw-threshold", placeholder: "KiB/s" },
      { flag: "--qbit-bw-time", placeholder: "SECONDS" },
      { flag: "--rtorrent-label", placeholder: "LABEL" },
    ],
  },
  {
    id: "usenet",
    title: "Usenet",
    entries: [
      "--usenet",
      { flag: "--usenet-subject", placeholder: "TEXT" },
      { flag: "--archive-password", placeholder: "PASSWORD or random" },
      { flag: "--usenet-episodes-only", placeholder: "CURUPIRA,NZBNEST" },
      "--upload-order",
    ],
  },
  {
    id: "workflow",
    title: "Modes / Workflows",
    entries: [
      { flag: "--queue", placeholder: "QUEUE_NAME" },
      { flag: "--limit-queue", placeholder: "N" },
      "--site-check",
      { flag: "--site-upload", placeholder: "TRACKER" },
      "--unit3d",
      {
        flag: "--unattended",
        description: "Unattended (no prompts (AT ALL))",
      },
      {
        flag: "--unattended_confirm",
        description:
          "Unattended confirm (use with --unattended, some prompting)",
      },
    ],
  },
  {
    id: "debug",
    title: "Debug / Cleanup",
    entries: [
      "--debug",
      "--ffdebug",
      "--upload-timer",
      "--delete-meta",
      "--delete-tmp",
      "--cleanup",
    ],
  },
];

// Every view ends with the options that apply to any upload.
const COMMON_ARGUMENT_SECTIONS = [
  "upload-selection",
  "upload-flags",
  "torrent",
  "client",
  "usenet",
  "workflow",
  "debug",
];
const VIDEO_ARGUMENT_SECTIONS = [
  "release",
  "video-ids",
  "title",
  "details",
  "description",
  "screens",
  "disc",
  "analysis",
  "tracker-refs",
];
const argumentViews = [
  { id: "all", label: "All", icon: "list" },
  {
    id: "movie",
    label: "Movie",
    icon: "clapperboard",
    sections: [...VIDEO_ARGUMENT_SECTIONS, ...COMMON_ARGUMENT_SECTIONS],
  },
  {
    id: "tv",
    label: "TV",
    icon: "tv",
    sections: [
      "release",
      "video-ids",
      "tv",
      ...VIDEO_ARGUMENT_SECTIONS.slice(2),
      ...COMMON_ARGUMENT_SECTIONS,
    ],
  },
  {
    id: "music",
    label: "Music",
    icon: "music-2",
    sections: [
      "music-release",
      "music-edition",
      "music-lookup",
      "music-orpheus",
      "description",
      ...COMMON_ARGUMENT_SECTIONS,
    ],
  },
  {
    id: "book",
    label: "Book",
    icon: "book-open",
    sections: ["book", "description", ...COMMON_ARGUMENT_SECTIONS],
  },
  {
    id: "game",
    label: "Game",
    icon: "gamepad-2",
    sections: ["game", "description", "screens", ...COMMON_ARGUMENT_SECTIONS],
  },
  {
    id: "other",
    label: "Other",
    icon: "shapes",
    description: "Sports, fan resyncs and adult releases",
    sections: [
      ...VIDEO_ARGUMENT_SECTIONS.filter((id) => id !== "analysis"),
      ...COMMON_ARGUMENT_SECTIONS,
    ],
  },
];
// --category values pick the matching view automatically.
const ARGUMENT_VIEW_FOR_CATEGORY = {
  movie: "movie",
  tv: "tv",
  music: "music",
  book: "book",
  game: "game",
  sports: "other",
  fanres: "other",
  xxx: "other",
};

const argumentBuilder = window.UAArgumentBuilder;
const cliArguments = Array.isArray(window.UA_CLI_ARGUMENTS)
  ? window.UA_CLI_ARGUMENTS
  : [];
const cliArgumentsByLabel = new Map(
  cliArguments.map((arg) => [arg.label, arg]),
);
const argumentIndex = argumentBuilder.createArgumentIndex(cliArguments);

const toArgumentRow = (entry) => {
  const spec = typeof entry === "string" ? { flag: entry } : entry;
  if (spec.insert) {
    return {
      id: `insert:${spec.label}`,
      type: "insert",
      label: spec.label,
      insert: spec.insert,
      description: spec.description || "",
    };
  }
  // Options the running CLI no longer has are left out.
  const key = argumentBuilder.keyForOption(argumentIndex, spec.flag);
  if (!key) return null;
  const item = argumentIndex.items.get(key);
  const cli = cliArgumentsByLabel.get(spec.flag) || item;
  return {
    id: spec.prefix ? `${spec.flag}#${spec.prefix}` : spec.flag,
    type: spec.prefix ? "value" : item.kind || "value",
    key,
    flag: spec.flag,
    label: spec.label || spec.flag,
    prefix: spec.prefix || "",
    placeholder: spec.placeholder || cli.placeholder || "",
    description: spec.description || cli.description || "",
    choices: spec.prefix ? [] : item.choices || [],
    caseInsensitive: !spec.prefix && Boolean(item.case_insensitive),
    path: spec.path || "",
  };
};

const argumentSectionList = argumentSections.map((section) => ({
  id: section.id,
  title: section.title,
  subtitle: section.subtitle,
  rows: section.entries.map(toArgumentRow).filter(Boolean),
}));
{
  // New CLI options appear here until they are given a section.
  const groupedKeys = new Set(
    argumentSectionList.flatMap((section) =>
      section.rows.map((row) => row.key).filter(Boolean),
    ),
  );
  const remaining = [...argumentIndex.items.entries()]
    .filter(([key, item]) => !groupedKeys.has(key) && item.description)
    .map(([, item]) => toArgumentRow(item.label));
  if (remaining.length > 0) {
    argumentSectionList.push({
      id: "other-cli",
      title: "Other CLI options",
      rows: remaining,
    });
  }
}
const argumentSectionsById = new Map(
  argumentSectionList.map((section) => [section.id, section]),
);
// Favorites and the "In command" list look rows up by id or option.
const argumentRowsById = new Map();
const argumentRowsByKey = new Map();
argumentSectionList.forEach((section) =>
  section.rows.forEach((row) => {
    if (!argumentRowsById.has(row.id)) argumentRowsById.set(row.id, row);
    if (row.key && !row.prefix && !argumentRowsByKey.has(row.key)) {
      argumentRowsByKey.set(row.key, row);
    }
  }),
);
const getArgumentViewSections = (viewId) => {
  const view = argumentViews.find((item) => item.id === viewId);
  if (!view?.sections) return argumentSectionList;
  return view.sections
    .map((id) => argumentSectionsById.get(id))
    .filter(Boolean);
};

// Icon components
const LucideIcon = window.UALucideIcon;

/**
 * A queue item's cover in Results, fitted within 96x64 at the image's own
 * shape (posters, square album art, wide game banners); a missing image falls
 * back to the category icon.
 */
const RunGuiItemCover = ({ src, category, name }) => {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  return (
    <div
      className={`ua-run-gui-cover flex shrink-0 items-center justify-center overflow-hidden rounded border ${failed ? "h-16 w-11" : ""}`}
      title={name || undefined}
    >
      {failed ? (
        <span className="ua-run-gui-muted">
          {mediaIconForCategory(category)}
        </span>
      ) : (
        <img
          src={src}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          className="block h-auto max-h-16 w-auto max-w-24"
          onError={() => setFailed(true)}
        />
      )}
    </div>
  );
};

/** A native popover escapes the scroll panel and dismisses on Escape or outside click. */
const RunGuiDebugBadge = ({ options }) => {
  const triggerRef = useRef(null);
  const popoverRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [popoverId] = useState(
    () => `ua-debug-${Math.random().toString(36).slice(2)}`,
  );
  /** Keep an open panel anchored to its badge and inside the viewport. */
  const positionPopover = useCallback(() => {
    const popover = popoverRef.current;
    const trigger = triggerRef.current;
    if (!popover || !trigger || !popover.matches(":popover-open")) return;
    popover.style.width = `${Math.min(384, window.innerWidth - 24)}px`;
    const bounds = popover.getBoundingClientRect();
    const anchor = trigger.getBoundingClientRect();
    const below = anchor.bottom + 8;
    const top =
      below + bounds.height <= window.innerHeight - 12
        ? below
        : Math.max(12, anchor.top - bounds.height - 8);
    const left = Math.max(
      12,
      Math.min(
        anchor.right - bounds.width,
        window.innerWidth - bounds.width - 12,
      ),
    );
    popover.style.top = `${top}px`;
    popover.style.left = `${left}px`;
  }, []);
  useEffect(() => {
    const popover = popoverRef.current;
    const onToggle = (event) => {
      setOpen(event.newState === "open");
      if (event.newState === "open") positionPopover();
    };
    popover.addEventListener("toggle", onToggle);
    window.addEventListener("resize", positionPopover);
    window.addEventListener("scroll", positionPopover, true);
    return () => {
      popover.removeEventListener("toggle", onToggle);
      window.removeEventListener("resize", positionPopover);
      window.removeEventListener("scroll", positionPopover, true);
    };
  }, [positionPopover]);
  useEffect(() => {
    if (open) positionPopover();
  }, [open, options, positionPopover]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        popovertarget={popoverId}
        aria-label="Debug Run details"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={popoverId}
        data-tone="attention"
        className="ua-run-gui-chip inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium"
      >
        <LucideIcon
          name="square-terminal"
          className="ua-run-gui-tone-icon h-3 w-3"
        />
        Debug Run
        <LucideIcon name="chevron-down" className="h-3 w-3" />
      </button>
      <div
        ref={popoverRef}
        id={popoverId}
        popover="auto"
        role="dialog"
        aria-label="Debug run details"
        className="ua-run-gui-debug-popover rounded-lg border p-4 shadow-xl"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <h4 className="text-sm font-semibold">Debug Run</h4>
          <button
            type="button"
            popovertarget={popoverId}
            popovertargetaction="hide"
            aria-label="Close debug run details"
            className="ua-run-gui-muted rounded p-1"
          >
            <LucideIcon name="x" className="h-4 w-4" />
          </button>
        </div>
        <dl className="space-y-3">
          {window.UARunGui.getDebugRunRows(options).map((row) => (
            <div key={row.flag}>
              <dt className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                <code className="min-w-0 break-all font-semibold">
                  {row.flag}
                </code>
                <span
                  className="ml-auto inline-flex items-center gap-1"
                  data-tone={row.enabled ? "success" : "muted"}
                >
                  <LucideIcon
                    name={row.enabled ? "circle-check" : "circle-x"}
                    className="ua-run-gui-tone-icon h-3.5 w-3.5"
                  />
                  {row.enabled ? "Applied" : "Not applied"}
                </span>
              </dt>
              <dd className="mt-1 text-xs">
                <span className="font-medium">{row.label}</span>
                <p className="ua-run-gui-muted mt-0.5">{row.detail}</p>
              </dd>
            </div>
          ))}
        </dl>
        {options.prepDirectory && (
          <div className="mt-4">
            <p className="mb-1 text-xs font-semibold">Prep material</p>
            <p className="ua-run-gui-muted break-all font-mono text-xs">
              {options.prepDirectory}
            </p>
          </div>
        )}
      </div>
    </>
  );
};
const WebUiIcon = LucideIcon;

const FolderIcon = () => (
  <WebUiIcon name="file-structure" className="w-4 h-4" />
);

const ScreenshotsIcon = () => <WebUiIcon name="screenshots" />;

const FolderOpenIcon = () => (
  <LucideIcon name="folder-open" className="w-4 h-4" />
);

const FileIcon = () => <LucideIcon name="file-text" className="w-4 h-4" />;

const TerminalIcon = () => (
  <LucideIcon name="square-terminal" className="w-5 h-5" />
);

const DescriptionIcon = () => (
  <LucideIcon name="text-initial" className="w-5 h-5" />
);

const MediaInfoIcon = () => (
  <LucideIcon name="file-search" className="w-5 h-5" />
);

const PaletteIcon = () => <WebUiIcon name="palette" />;

const SettingsIcon = () => <WebUiIcon name="config" />;

const HelpIcon = () => <WebUiIcon name="help" />;

const UpdateIcon = () => <LucideIcon name="download" className="h-5 w-5" />;

const ChangelogIcon = () => <WebUiIcon name="changelog" />;

const StatsIcon = () => <WebUiIcon name="stats" />;

const UploadRailIcon = () => <WebUiIcon name="upload" />;

const LogoutIcon = () => <WebUiIcon name="logout" />;

const WorkspaceSwitcher = ({
  activeWorkspace,
  appBase,
  isDarkMode,
  stretch,
}) => {
  const workspaces = [
    { id: "upload", label: "Upload", href: `${appBase}/` },
    { id: "config", label: "Configuration", href: `${appBase}/config` },
    { id: "stats", label: "Stats", href: `${appBase}/stats` },
  ];

  return (
    <nav
      className="ua-workspace-switcher rounded-lg"
      data-mode={isDarkMode ? "dark" : "light"}
      data-stretch={stretch ? "true" : "false"}
      aria-label="Workspace"
    >
      {workspaces.map((workspace) => {
        const isActive = workspace.id === activeWorkspace;
        return (
          <a
            key={workspace.id}
            href={workspace.href}
            className="ua-workspace-link rounded-md"
            data-active={isActive ? "true" : "false"}
            aria-current={isActive ? "page" : undefined}
            onClick={isActive ? (event) => event.preventDefault() : undefined}
          >
            {workspace.label}
          </a>
        );
      })}
    </nav>
  );
};

const ApplicationRail = ({
  trackers,
  activeWorkspace,
  appBase,
  appearanceControl,
  updateStatus,
  onOpenUpdate,
  onOpenHelp,
  onLogout,
}) => {
  const workspaceLinks = [
    {
      id: "upload",
      label: "Upload",
      href: `${appBase}/`,
      icon: <UploadRailIcon />,
    },
    {
      id: "config",
      label: "Config",
      href: `${appBase}/config`,
      icon: <SettingsIcon />,
    },
    {
      id: "stats",
      label: "Stats",
      href: `${appBase}/stats`,
      icon: <StatsIcon />,
    },
  ];

  return (
    <aside
      className="ua-app-rail relative z-40 hidden h-full min-h-0 w-20 shrink-0 flex-col border-r md:flex"
      aria-label="Application navigation"
    >
      <div className="ua-app-rail-brand flex h-20 shrink-0 flex-col items-center justify-center gap-1 border-b px-2">
        <img
          src={`${appBase}/static/img/logo.svg`}
          alt="Upload Assistant"
          className="h-8 w-8"
        />
        {window.UA_APP_VERSION && (
          <span className="text-[0.65rem] font-semibold opacity-60">
            {window.UA_APP_VERSION}
          </span>
        )}
      </div>

      <nav className="grid gap-1 p-2" aria-label="Workspaces">
        {workspaceLinks.map((workspace) => {
          const isActive = workspace.id === activeWorkspace;
          return (
            <a
              key={workspace.id}
              href={workspace.href}
              className="ua-app-rail-button rounded-lg"
              data-active={isActive ? "true" : "false"}
              aria-current={isActive ? "page" : undefined}
              onClick={isActive ? (event) => event.preventDefault() : undefined}
            >
              {workspace.icon}
              <span>{workspace.label}</span>
            </a>
          );
        })}
      </nav>

      <div className="min-h-4 flex-1"></div>

      <div className="ua-app-rail-footer grid shrink-0 gap-1 border-t p-2">
        <window.UAApiKeyAlerts trackers={trackers} appBase={appBase} />
        <button
          type="button"
          className={`ua-app-rail-button rounded-lg ${updateStatus?.update_available ? "ua-update-rail-button" : ""}`}
          onClick={onOpenUpdate}
          aria-haspopup="dialog"
          title={
            updateStatus?.update_available
              ? `${updateStatus.latest_version} is available`
              : "View release history"
          }
        >
          {updateStatus?.update_available ? <UpdateIcon /> : <ChangelogIcon />}
          <span>{updateStatus?.update_available ? "Update" : "Changelog"}</span>
        </button>
        <button
          type="button"
          className="ua-app-rail-button rounded-lg"
          onClick={onOpenHelp}
          aria-haspopup="dialog"
        >
          <HelpIcon />
          <span>Help</span>
        </button>
        {appearanceControl}
        <button
          type="button"
          className="ua-app-rail-button rounded-lg text-red-500"
          onClick={onLogout}
        >
          <LogoutIcon />
          <span>Log out</span>
        </button>
      </div>
    </aside>
  );
};

const UploadWorkspaceBrand = ({
  appBase,
  isDarkMode,
  isExecuting,
  compact,
  contextOnly = false,
}) => (
  <div className="flex min-w-0 items-center gap-2 sm:gap-3">
    {!contextOnly && (
      <LogoIcon
        src={`${appBase}/static/img/logo.svg`}
        className={compact ? "h-7 w-7" : "h-8 w-8"}
      />
    )}
    <div className="min-w-0">
      {!contextOnly && (
        <div
          className={`flex min-w-0 items-baseline gap-1 font-semibold uppercase opacity-60 ${
            compact
              ? "text-[0.68rem] tracking-[0.12em]"
              : "text-xs tracking-widest"
          }`}
        >
          <span className="truncate">Upload Assistant</span>
          {window.UA_APP_VERSION && (
            <span className="shrink-0 normal-case tracking-normal">
              <span aria-hidden="true">·</span> {window.UA_APP_VERSION}
            </span>
          )}
        </div>
      )}
      <div
        className={`${contextOnly ? "" : "mt-0.5"} flex min-w-0 items-center gap-2`}
      >
        <h1
          className={`truncate font-bold ${compact ? "text-base" : "text-xl"} ${
            isDarkMode ? "text-white" : "text-gray-800"
          }`}
        >
          Upload
        </h1>
        {isExecuting && (
          <span
            className="ua-workspace-run-status shrink-0 rounded-full"
            role="status"
          >
            <span
              className="ua-workspace-run-dot animate-pulse"
              aria-hidden="true"
            ></span>
            Running
          </span>
        )}
      </div>
    </div>
  </div>
);

function UploadHelpResourcesModal({
  updateStatus,
  isCheckingForUpdates,
  onCheckForUpdates,
  onOpenChangelog,
  onClose,
}) {
  const resourceGroups = window.UAHelpResourceGroups || [];
  const dialogRef = useModalFocus(onClose);
  const updateMessage = isCheckingForUpdates
    ? "Checking GitHub for the latest release… This can take up to 15 seconds."
    : !updateStatus
      ? "No update check has completed yet."
      : !updateStatus.success
        ? updateStatus.error || "Unable to check for updates."
        : updateStatus.enabled === false
          ? "Automatic update notifications are disabled. You can still check manually."
          : updateStatus.update_available
            ? `${updateStatus.latest_version} is available. You have ${updateStatus.current_version}.`
            : `You’re up to date (${updateStatus.current_version || window.UA_APP_VERSION}).`;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-3 sm:p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="ua-upload-help-modal flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-help-resources-title"
        tabIndex="-1"
      >
        <div className="ua-upload-panel-header flex items-start justify-between gap-4 border-b px-4 py-3 sm:px-5 sm:py-4">
          <div>
            <h2
              id="upload-help-resources-title"
              className="text-lg font-semibold"
            >
              Help &amp; Resources
            </h2>
            <p className="ua-upload-muted mt-1 text-sm">
              Official Upload Assistant documentation and setup guides.
            </p>
          </div>
          <button
            type="button"
            className="ua-upload-header-action h-10 w-10 shrink-0 rounded-lg p-0"
            aria-label="Close help and resources"
            data-ua-modal-initial-focus
            onClick={onClose}
          >
            <LucideIcon name="x" className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
          <div className="ua-upload-help-card mb-4 rounded-lg border p-3 text-sm">
            These links open GitHub in a new tab, keeping guidance aligned with
            the upstream development documentation.
          </div>
          <section className="ua-upload-help-card mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
            <div className="min-w-0">
              <h3 className="text-sm font-semibold">Updates</h3>
              <p className="ua-upload-muted mt-1 text-xs">{updateMessage}</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <button
                type="button"
                className="ua-upload-modal-action rounded-lg px-3 py-2 text-sm font-semibold"
                onClick={onOpenChangelog}
              >
                View changelog
              </button>
              <button
                type="button"
                className="ua-upload-modal-action rounded-lg px-3 py-2 text-sm font-semibold disabled:cursor-wait disabled:opacity-60"
                disabled={isCheckingForUpdates}
                onClick={onCheckForUpdates}
              >
                {isCheckingForUpdates ? "Checking…" : "Check now"}
              </button>
            </div>
          </section>
          <div className="grid gap-4 md:grid-cols-2">
            {resourceGroups.map((group) => (
              <section
                key={group.title}
                className="ua-upload-help-card rounded-xl border p-3 sm:p-4"
              >
                <h3 className="mb-3 text-sm font-semibold">{group.title}</h3>
                <div className="space-y-2">
                  {group.links.map((link) => (
                    <a
                      key={link.href}
                      href={link.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ua-upload-help-link flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5"
                    >
                      <span className="min-w-0">
                        <span className="block text-sm font-semibold">
                          {link.label}
                        </span>
                        <span className="ua-upload-muted mt-0.5 block text-xs">
                          {link.description}
                        </span>
                      </span>
                      <LucideIcon
                        name="external-link"
                        className="h-4 w-4 shrink-0"
                      />
                    </a>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>

        <div className="ua-upload-modal-footer flex justify-end border-t px-4 py-3 sm:px-5">
          <a
            href="https://github.com/wastaken7/Upload-Assistant/tree/development/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="ua-upload-modal-action rounded-lg px-4 py-2 text-sm font-semibold"
          >
            Browse all documentation
            <LucideIcon name="external-link" className="ml-2 h-4 w-4" />
          </a>
        </div>
      </section>
    </div>
  );
}

const ProgressIcon = () => (
  <LucideIcon name="chart-column-increasing" className="w-5 h-5" />
);

const MovieIcon = () => <WebUiIcon name="movie" />;

const TvIcon = () => <WebUiIcon name="tv" />;

const GameIcon = () => <WebUiIcon name="gamepad" />;

const BookIcon = () => <WebUiIcon name="book" />;

const DiscIcon = () => <WebUiIcon name="music" />;

const PepperIcon = () => <WebUiIcon name="pepper" />;

// The review grid groups frames by disc/playlist; navigation follows that order.
const orderScreenshotsByGroup = (screenshots) =>
  Object.values(
    screenshots.reduce((groups, screenshot) => {
      const group = screenshot.group || "main";
      (groups[group] ||= []).push(screenshot);
      return groups;
    }, {}),
  ).flat();

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
    case "XXX":
      return <PepperIcon />;
    default:
      return <FileIcon />;
  }
};

const PlayIcon = () => <LucideIcon name="circle-play" className="w-4 h-4" />;

const PlusIcon = () => <LucideIcon name="plus" className="w-4 h-4" />;

const ExpandIcon = () => <LucideIcon name="maximize-2" className="w-4 h-4" />;

const TrashIcon = () => <LucideIcon name="trash-2" className="w-4 h-4" />;

const LogoIcon = ({ src, className = "w-6 h-6" }) => (
  <img
    src={src}
    alt="Upload-Assistant logo"
    className={`${className} flex-shrink-0`}
  />
);

const ChevronDownIcon = () => (
  <LucideIcon name="chevron-down" className="w-4 h-4" />
);

const ChevronRightIcon = () => (
  <LucideIcon name="chevron-right" className="w-4 h-4" />
);

const SearchIcon = () => <LucideIcon name="search" className="w-4 h-4" />;

const CollapseAllIcon = () => (
  <LucideIcon name="minimize-2" className="w-4 h-4" />
);

const ExpandAllIcon = () => (
  <LucideIcon name="maximize-2" className="w-4 h-4" />
);

const SpinnerIcon = () => (
  <LucideIcon name="loader-circle" className="w-4 h-4 animate-spin" />
);

const RefreshIcon = () => <LucideIcon name="refresh-cw" className="w-4 h-4" />;

const metadataProviderStyles = {
  tmdb: {
    light: "border-[#06B4E2]/70 bg-[#06B4E2]/10 text-[#067A98]",
    dark: "border-[#06B4E2]/60 bg-[#06B4E2]/20 text-[#B9F3FF]",
  },
  imdb: {
    light: "border-[#F5C518]/70 bg-[#F5C518]/10 text-[#6F5700]",
    dark: "border-[#F5C518]/60 bg-[#F5C518]/20 text-[#FFF3B5]",
  },
  tvdb: {
    light: "border-[#6CD591]/70 bg-[#6CD591]/10 text-[#2F7D49]",
    dark: "border-[#6CD591]/60 bg-[#6CD591]/20 text-[#D9F9E4]",
  },
  tvmaze: {
    light: "border-[#6EC4BA]/70 bg-[#6EC4BA]/10 text-[#2E7B73]",
    dark: "border-[#6EC4BA]/60 bg-[#6EC4BA]/20 text-[#D4F4EF]",
  },
  mal: {
    light: "border-[#2E51A1]/70 bg-[#2E51A1]/10 text-[#2E51A1]",
    dark: "border-[#2E51A1]/60 bg-[#2E51A1]/20 text-[#C9D6F4]",
  },
  douban: {
    light: "border-[#007610]/70 bg-[#007610]/10 text-[#007610]",
    dark: "border-[#007610]/60 bg-[#007610]/20 text-[#B9F2C2]",
  },
  igdb: {
    light: "border-[#9147FF]/70 bg-[#9147FF]/10 text-[#9147FF]",
    dark: "border-[#9147FF]/60 bg-[#9147FF]/20 text-[#E2D2FF]",
  },
  steam: {
    light: "border-sky-600/80 bg-sky-600/15 text-sky-900",
    dark: "border-sky-400/80 bg-sky-500/30 text-sky-100",
  },
  google_books: {
    light: "border-green-300/70 bg-green-300/10 text-green-900",
    dark: "border-green-900/60 bg-green-900/20 text-green-100",
  },
  openlibrary: {
    light: "border-orange-300/70 bg-orange-300/10 text-orange-900",
    dark: "border-orange-900/60 bg-orange-900/20 text-orange-100",
  },
  audible: {
    light: "border-[#F7991C]/70 bg-[#F7991C]/10 text-[#9A4F00]",
    dark: "border-[#F7991C]/60 bg-[#F7991C]/20 text-[#FFD6A3]",
  },
  musicbrainz: {
    light: "border-[#BA478F]/70 bg-[#BA478F]/10 text-[#7D205D]",
    dark: "border-[#BA478F]/60 bg-[#BA478F]/20 text-[#F4C7E4]",
  },
  discogs: {
    light: "border-slate-400/70 bg-slate-400/10 text-slate-900",
    dark: "border-slate-500/60 bg-slate-500/20 text-slate-100",
  },
  default: {
    light: "border-gray-300/70 bg-gray-300/10 text-gray-900",
    dark: "border-gray-700/60 bg-gray-700/20 text-gray-100",
  },
};

const getMetadataProviderStyle = (key, isDarkMode) => {
  const normalizedKey = String(key || "").startsWith("discogs_")
    ? "discogs"
    : key;
  const providerStyle =
    metadataProviderStyles[normalizedKey] || metadataProviderStyles.default;
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
  audible: {
    src: "/static/img/providers/audible.svg",
    alt: "Audible",
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
  const normalizedKey = String(key || "").startsWith("discogs_")
    ? "discogs"
    : key;
  const iconAsset = metadataProviderIcons[normalizedKey];
  if (iconAsset) {
    const iconSrc =
      !isDarkMode && iconAsset.lightSrc ? iconAsset.lightSrc : iconAsset.src;
    return (
      <img
        src={iconSrc}
        alt={iconAsset.alt}
        className={`block h-[0.7rem] w-auto max-w-[3rem] object-contain ${
          normalizedKey === "discogs" && !isDarkMode ? "invert" : ""
        }`}
      />
    );
  }

  switch (key) {
    case "google_books":
      return <LucideIcon name="book-open" className="w-[0.8rem] h-[0.8rem]" />;
    case "openlibrary":
      return <LucideIcon name="book-open" className="w-[0.8rem] h-[0.8rem]" />;
    default:
      return (
        <span className="text-[8.8px] font-black tracking-wide">
          {String(key || "META")
            .slice(0, 4)
            .toUpperCase()}
        </span>
      );
  }
};

// Inline browser for argument values that take a server path. It lists the
// same browse roots as the File Browser, so only permitted paths are offered.
function ArgumentPathBrowser({ mode, apiBase, isDarkMode, onPick }) {
  const [nodes, setNodes] = useState([]);
  const [expanded, setExpanded] = useState(() => new Set());
  const [loading, setLoading] = useState(() => new Set());
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await apiFetch(`${apiBase}/browse_roots`);
        const data = await response.json();
        if (cancelled) return;
        if (data.success && data.items) setNodes(data.items);
        else setError("Could not load the browse roots.");
      } catch (_error) {
        if (!cancelled) setError("Could not load the browse roots.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  const toggleFolder = async (path) => {
    if (expanded.has(path)) {
      setExpanded((prev) => {
        const next = new Set(prev);
        next.delete(path);
        return next;
      });
      return;
    }
    setExpanded((prev) => new Set(prev).add(path));
    setLoading((prev) => new Set(prev).add(path));
    try {
      const response = await apiFetch(
        `${apiBase}/browse?path=${encodeURIComponent(path)}&filter=video`,
      );
      const data = await response.json();
      if (data.success && data.items) {
        const attach = (items) =>
          items.map((node) =>
            node.path === path
              ? { ...node, children: data.items }
              : node.children
                ? { ...node, children: attach(node.children) }
                : node,
          );
        setNodes((prev) => attach(prev));
      } else {
        setError("Could not open that folder.");
      }
    } catch (_error) {
      setError("Could not open that folder.");
    } finally {
      setLoading((prev) => {
        const next = new Set(prev);
        next.delete(path);
        return next;
      });
    }
  };

  const renderNodes = (items, level = 0) =>
    items
      .filter((item) => mode === "file" || item.type === "folder")
      .map((item) => {
        const isFolder = item.type === "folder";
        const isOpen = expanded.has(item.path);
        return (
          <div key={item.path}>
            <div
              className={`flex items-center gap-1 rounded ${isDarkMode ? "hover:bg-gray-700" : "hover:bg-gray-100"}`}
              style={{ paddingLeft: `${level * 14 + 4}px` }}
            >
              <button
                type="button"
                onClick={() =>
                  isFolder ? toggleFolder(item.path) : onPick(item.path)
                }
                className="flex min-w-0 flex-1 items-center gap-1.5 py-1 text-left text-xs"
                aria-label={
                  isFolder
                    ? `${isOpen ? "Collapse" : "Expand"} folder ${item.name}`
                    : `Use file ${item.name}`
                }
                aria-expanded={isFolder ? isOpen : undefined}
              >
                <span className="flex-none text-yellow-600">
                  {isFolder ? (
                    loading.has(item.path) ? (
                      <SpinnerIcon />
                    ) : isOpen ? (
                      <FolderOpenIcon />
                    ) : (
                      <FolderIcon />
                    )
                  ) : (
                    <FileIcon />
                  )}
                </span>
                <span className="truncate">{item.name}</span>
              </button>
              {isFolder && mode === "folder" && (
                <button
                  type="button"
                  onClick={() => onPick(item.path)}
                  className="ua-accent-link flex-none px-1.5 text-xs font-medium"
                  aria-label={`Use folder ${item.name}`}
                >
                  Use
                </button>
              )}
            </div>
            {isFolder && isOpen && item.children && (
              <div>{renderNodes(item.children, level + 1)}</div>
            )}
          </div>
        );
      });

  return (
    <div
      className={`mt-2 max-h-64 overflow-y-auto rounded-md border p-1 ${isDarkMode ? "border-gray-600 bg-gray-900/40 text-gray-200" : "border-gray-200 bg-gray-50 text-gray-800"}`}
    >
      {error && <p className="px-1 py-1 text-xs text-red-500">{error}</p>}
      {nodes.length === 0 && !error ? (
        <p className="px-1 py-1 text-xs opacity-70">Loading…</p>
      ) : (
        renderNodes(nodes)
      )}
    </div>
  );
}

function AudionutsUAGUI() {
  const API_BASE = window.location.origin + "/api";
  // Derive an application base path from the API base so links work under subpath deployments
  const APP_BASE = API_BASE.replace(/\/api$/, "");

  useEffect(() => {
    const root = document.documentElement;
    const viewport = window.visualViewport;
    let animationFrame = 0;

    root.classList.add("ua-upload-document");

    const updateViewportHeight = () => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(() => {
        const visibleHeight = Math.round(
          viewport?.height || window.innerHeight,
        );
        if (visibleHeight > 0) {
          root.style.setProperty(
            "--ua-upload-viewport-height",
            `${visibleHeight}px`,
          );
        }
      });
    };

    updateViewportHeight();
    window.addEventListener("resize", updateViewportHeight);
    viewport?.addEventListener("resize", updateViewportHeight);
    viewport?.addEventListener("scroll", updateViewportHeight);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      window.removeEventListener("resize", updateViewportHeight);
      viewport?.removeEventListener("resize", updateViewportHeight);
      viewport?.removeEventListener("scroll", updateViewportHeight);
      root.style.removeProperty("--ua-upload-viewport-height");
      root.classList.remove("ua-upload-document");
    };
  }, []);

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
  const [manualPathsText, setManualPathsText] = useState(null);
  const [pathInputError, setPathInputError] = useState("");
  // Queue items whose per-line arguments are expanded for editing.
  const [expandedQueueArgs, setExpandedQueueArgs] = useState(new Set());
  // Last checkbox toggled in the file browser, the start of a Shift+click range.
  const selectionAnchorRef = useRef("");
  const queueListRef = useRef(null);
  const [, setSelectedName] = useState("");
  const [customArgs, setCustomArgs] = useState("");
  const [argumentPresets, setArgumentPresets] = useState([]);
  const [argumentPresetName, setArgumentPresetName] = useState("");
  const [selectedArgumentPreset, setSelectedArgumentPreset] = useState("");
  const [trackers, setTrackers] = useState([]);
  const [defaultTrackers, setDefaultTrackers] = useState(new Set());
  const [selectedTrackers, setSelectedTrackers] = useState(new Set());
  const [trackerAliases, setTrackerAliases] = useState({});
  const [trackerAliasError, setTrackerAliasError] = useState("");
  const [trackerStatuses, setTrackerStatuses] = useState({});
  const [isCheckingTrackerStatuses, setIsCheckingTrackerStatuses] =
    useState(false);
  const [trackerStatusError, setTrackerStatusError] = useState("");
  const [expandedTrackerStatusDetails, setExpandedTrackerStatusDetails] =
    useState(new Set());
  const [showAllSupportedTrackers, setShowAllSupportedTrackers] =
    useState(false);
  const [failedFavicons, setFailedFavicons] = useState(new Set());
  const [isExecuting, setIsExecuting] = useState(Boolean(screenshotMode));
  const [isTerminalView, setIsTerminalView] = useState(Boolean(screenshotMode));
  const [expandedFolders, setExpandedFolders] = useState(
    getStoredExpandedFolders,
  );
  const [sessionId, setSessionId] = useState("");
  const [uploadTabs, setUploadTabs] = useState(() =>
    screenshotMode
      ? screenshotMode.tabs.map((tab, index) => ({
          ...tab,
          id: `tab-${index + 1}`,
          number: index + 1,
        }))
      : [{ id: "tab-1", number: 1, title: "", status: "idle" }],
  );
  const [activeTabId, setActiveTabId] = useState("tab-1");
  const [pendingCloseTabId, setPendingCloseTabId] = useState("");
  const [maxRunningUploads, setMaxRunningUploads] = useState(
    DEFAULT_MAX_RUNNING_UPLOADS,
  );
  const [schedulingEnabled, setSchedulingEnabled] = useState(true);
  const [uploadTabsRestored, setUploadTabsRestored] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(() =>
    getStoredSidebarWidth(
      LEFT_SIDEBAR_WIDTH_KEY,
      DEFAULT_LEFT_SIDEBAR_WIDTH,
      LEFT_SIDEBAR_MAX_WIDTH,
    ),
  );
  const [isResizing, setIsResizing] = useState(false);
  const [rightSidebarWidth, setRightSidebarWidth] = useState(() =>
    getStoredSidebarWidth(
      RIGHT_SIDEBAR_WIDTH_KEY,
      DEFAULT_RIGHT_SIDEBAR_WIDTH,
      RIGHT_SIDEBAR_MAX_WIDTH,
    ),
  );
  const [isResizingRight, setIsResizingRight] = useState(false);
  const [userInput, setUserInput] = useState("");
  // Options ticked in the open multiple-choice prompt. Prompt ids restart
  // in every upload process, so the key also names the session.
  const [runGuiSelected, setRunGuiSelected] = useState({
    key: null,
    values: [],
  });
  // Run options changed on the open "Is this correct?" prompt, by option key;
  // only values that differ from what the run reported are kept.
  const [runGuiRunOptions, setRunGuiRunOptions] = useState({
    key: null,
    values: {},
  });
  const [isSendingInput, setIsSendingInput] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(getStoredTheme);
  const [colorTheme, setColorThemeState] = useState(getStoredColorTheme);
  const [interfaceStyle, setInterfaceStyleState] = useState(
    getStoredInterfaceStyle,
  );
  const [isThemePaletteOpen, setIsThemePaletteOpen] = useState(false);
  const [isHelpResourcesOpen, setIsHelpResourcesOpen] = useState(false);
  const [isChangelogOpen, setIsChangelogOpen] = useState(false);
  const [updateStatus, setUpdateStatus] = useState(null);
  const [isUpdateStatusOpen, setIsUpdateStatusOpen] = useState(false);
  const [isCheckingForUpdates, setIsCheckingForUpdates] = useState(false);
  const [dismissedUpdateVersion, setDismissedUpdateVersion] = useState(
    () => window.getUADismissedUpdateVersion?.() || "",
  );
  const [argSearchFilter, setArgSearchFilter] = useState("");
  const [collapsedSections, setCollapsedSections] = useState(
    () => new Set(getStoredCollapsedSections()),
  );
  const [argumentView, setArgumentView] = useState(() => {
    const stored = storage.get(ARGUMENT_VIEW_KEY);
    return argumentViews.some((view) => view.id === stored) ? stored : "all";
  });
  const [favoriteArguments, setFavoriteArguments] = useState(
    getStoredFavoriteArguments,
  );
  // The row whose inline path browser is open, if any.
  const [argumentPathRowId, setArgumentPathRowId] = useState("");
  const [executionPreview, setExecutionPreview] = useState(() => {
    if (!screenshotMode) return null;
    return {
      ...screenshotMode.media,
      poster_url: getStoredScreenshotArtwork(SCREENSHOT_POSTER_KEY),
      backdrop_url: getStoredScreenshotArtwork(SCREENSHOT_BACKDROP_KEY),
    };
  });
  const [showAudioTracks, setShowAudioTracks] = useState(
    () => storage.get(SHOW_AUDIO_TRACKS_KEY) === "true",
  );
  const [showSubtitleTracks, setShowSubtitleTracks] = useState(
    () => storage.get(SHOW_SUBTITLE_TRACKS_KEY) === "true",
  );
  const [outputMode, setOutputMode] = useState(() =>
    storage.get(OUTPUT_MODE_KEY) === "terminal" ? "terminal" : "gui",
  );
  const [runGuiResultsCollapsed, setRunGuiResultsCollapsed] = useState(
    () => storage.get(RUN_GUI_RESULTS_COLLAPSED_KEY) === "true",
  );
  // Mirrors the active tab's runtime.gui; background tabs update only their runtime.
  const [runGui, setRunGui] = useState(initialRunGuiState);
  const [executionScreenshots, setExecutionScreenshots] = useState(
    () => screenshotMode?.screenshots || [],
  );
  const [executionDescription, setExecutionDescription] = useState(
    () => screenshotMode?.description || null,
  );
  const [descriptionDraft, setDescriptionDraft] = useState(
    () => screenshotMode?.description.content || "",
  );
  const [descriptionView, setDescriptionView] = useState("edit");
  const [descriptionVersion, setDescriptionVersion] = useState(
    () => screenshotMode?.description.version || 0,
  );
  const [descriptionDirty, setDescriptionDirty] = useState(false);
  const descriptionDirtyRef = useRef(false);
  const descriptionVersionRef = useRef(
    screenshotMode?.description.version || 0,
  );
  const descriptionEditorRef = useRef(null);
  const [descriptionAction, setDescriptionAction] = useState("");
  const [canAddExecutionScreenshot, setCanAddExecutionScreenshot] = useState(
    Boolean(screenshotMode),
  );
  const [screenshotActionId, setScreenshotActionId] = useState("");
  const [coverAction, setCoverAction] = useState("");
  const coverRequestRef = useRef(0);
  const [expandedScreenshot, setExpandedScreenshot] = useState(null);
  const [isScreenshotZoomed, setIsScreenshotZoomed] = useState(false);
  const [expandedScreenshotSize, setExpandedScreenshotSize] = useState(null);
  const [screenshotError, setScreenshotError] = useState("");
  const [pendingDeleteScreenshot, setPendingDeleteScreenshot] = useState("");
  const expandedScreenshotIndexRef = useRef(0);
  const themePaletteRef = useRef(null);
  const screenshotModalRef = useModalFocus(
    () => setExpandedScreenshot(null),
    Boolean(expandedScreenshot),
  );

  useEffect(() => {
    descriptionDirtyRef.current = descriptionDirty;
  }, [descriptionDirty]);
  const [isScreenshotReviewOpen, setIsScreenshotReviewOpen] = useState(false);
  const [isDescriptionReviewOpen, setIsDescriptionReviewOpen] = useState(false);
  const [isMediaInfoOpen, setIsMediaInfoOpen] = useState(false);
  const [executionMediaInfo, setExecutionMediaInfo] = useState(
    () => screenshotMode?.mediainfo || null,
  );
  const [mediaInfoStatus, setMediaInfoStatus] = useState(
    screenshotMode ? "ready" : "idle",
  );
  const [selectedMediaInfoKey, setSelectedMediaInfoKey] = useState(
    () => screenshotMode?.mediainfo.reports[0]?.key || "",
  );
  const [mediaInfoCopied, setMediaInfoCopied] = useState(false);
  const mediaInfoTargetRef = useRef("");
  // Desktop-only enlarged view of one review panel; the sidebar keeps showing
  // the media preview meanwhile so a panel is never mounted twice.
  const [expandedReviewPanel, setExpandedReviewPanel] = useState("");
  // Remembers whether the user last chose the larger view, so the header
  // buttons open review panels straight into it.
  const [reviewPanelsInModal, setReviewPanelsInModal] = useState(
    () => storage.get(REVIEW_PANELS_IN_MODAL_KEY) === "true",
  );
  const [progressItems, setProgressItems] = useState(
    screenshotMode?.media.progress || [],
  );
  const [selectedPaths, setSelectedPaths] = useState([]);
  const [sortBy, setSortBy] = useState(() => getStoredFileBrowserSort().by);
  const [sortOrder, setSortOrder] = useState(
    () => getStoredFileBrowserSort().order,
  );
  const [customFolderOrder, setCustomFolderOrder] = useState(
    getStoredFileBrowserCustomOrder,
  );
  const [isCustomOrderEditing, setIsCustomOrderEditing] = useState(false);
  const [draggedRootFolderPath, setDraggedRootFolderPath] = useState("");
  const [rootFolderDropTarget, setRootFolderDropTarget] = useState(null);

  const visibleUpdateStatus =
    updateStatus?.update_available &&
    updateStatus.latest_version !== dismissedUpdateVersion
      ? updateStatus
      : null;

  useEffect(() => {
    if (screenshotMode) return undefined;
    if (!window.loadUAUpdateStatus) return undefined;
    let cancelled = false;
    const loadUpdateStatus = () => {
      if (document.visibilityState === "hidden") return;
      window
        .loadUAUpdateStatus()
        .then((status) => {
          if (!cancelled) setUpdateStatus(status);
        })
        .catch(() => {});
    };
    loadUpdateStatus();
    const pollTimer = window.setInterval(loadUpdateStatus, 30 * 60 * 1000);
    document.addEventListener("visibilitychange", loadUpdateStatus);
    return () => {
      cancelled = true;
      window.clearInterval(pollTimer);
      document.removeEventListener("visibilitychange", loadUpdateStatus);
    };
  }, []);

  const checkForUpdatesNow = async () => {
    if (!window.loadUAUpdateStatus || isCheckingForUpdates) return;
    setIsCheckingForUpdates(true);
    try {
      const status = await window.loadUAUpdateStatus(true);
      setUpdateStatus(status);
      if (status?.update_available) {
        storage.remove("ua_dismissed_update_version");
        setDismissedUpdateVersion("");
        setIsHelpResourcesOpen(false);
        setIsUpdateStatusOpen(true);
      }
    } catch (error) {
      setUpdateStatus((currentStatus) => ({
        ...(currentStatus || {}),
        success: false,
        error: error?.message || "Unable to check for updates.",
      }));
    } finally {
      setIsCheckingForUpdates(false);
    }
  };

  const dismissCurrentUpdate = () => {
    const version = updateStatus?.latest_version;
    if (version) {
      window.dismissUAUpdateVersion?.(version);
      setDismissedUpdateVersion(version);
    }
    setIsUpdateStatusOpen(false);
  };

  const openChangelog = () => {
    setIsHelpResourcesOpen(false);
    setIsUpdateStatusOpen(false);
    setIsChangelogOpen(true);
  };

  useEffect(() => {
    storage.set(SHOW_AUDIO_TRACKS_KEY, showAudioTracks ? "true" : "false");
  }, [showAudioTracks]);

  useEffect(() => {
    storage.set(
      SHOW_SUBTITLE_TRACKS_KEY,
      showSubtitleTracks ? "true" : "false",
    );
  }, [showSubtitleTracks]);

  useEffect(() => {
    storage.set(OUTPUT_MODE_KEY, outputMode);
    // Hidden output cannot scroll; show the latest lines when it reappears.
    if (outputMode === "terminal") {
      const host = richOutputRef.current;
      if (host) host.scrollTop = host.scrollHeight;
    }
  }, [outputMode]);

  useEffect(() => {
    storage.set(RUN_GUI_RESULTS_COLLAPSED_KEY, String(runGuiResultsCollapsed));
  }, [runGuiResultsCollapsed]);

  // A new question opens at the top of the GUI panel, so its Yes/No buttons
  // are always in the same place even if the panel was scrolled down.
  const runGuiPromptId = runGui.prompt?.id ?? null;
  useEffect(() => {
    if (runGuiPromptId === null) return;
    document.querySelectorAll(".ua-run-gui").forEach((panel) => {
      panel.scrollTop = 0;
    });
  }, [runGuiPromptId]);

  useEffect(() => {
    storage.set(
      COLLAPSED_ARGUMENT_SECTIONS_KEY,
      JSON.stringify(Array.from(collapsedSections)),
    );
  }, [collapsedSections]);

  useEffect(() => {
    storage.set(ARGUMENT_VIEW_KEY, argumentView);
  }, [argumentView]);

  useEffect(() => {
    storage.set(FAVORITE_ARGUMENTS_KEY, JSON.stringify(favoriteArguments));
  }, [favoriteArguments]);

  useEffect(() => {
    storage.set(
      FILE_BROWSER_CUSTOM_ORDER_KEY,
      JSON.stringify(customFolderOrder),
    );
  }, [customFolderOrder]);

  useEffect(() => {
    storage.set(FILE_BROWSER_SORT_KEY, `${sortBy}-${sortOrder}`);
  }, [sortBy, sortOrder]);

  useEffect(() => {
    let cancelled = false;
    const loadArgumentPresets = async () => {
      if (screenshotMode) return;
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
    const handleInterfaceStyleChange = (event) => {
      setInterfaceStyleState(event.detail?.style || getStoredInterfaceStyle());
    };
    window.addEventListener("ua-shape-change", handleInterfaceStyleChange);
    return () =>
      window.removeEventListener("ua-shape-change", handleInterfaceStyleChange);
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

  const AppearanceControls = window.UAAppearanceControls;
  const renderAppearanceControls = (labelClassName) => (
    <AppearanceControls
      colorTheme={colorTheme}
      onColorThemeChange={(themeId) =>
        setColorThemeState(setColorTheme(themeId))
      }
      interfaceStyle={interfaceStyle}
      onInterfaceStyleChange={(styleId) =>
        setInterfaceStyleState(setInterfaceStyle(styleId))
      }
      isDarkMode={isDarkMode}
      onToggleMode={() => setIsDarkMode((dark) => !dark)}
      labelClassName={labelClassName}
    />
  );

  const renderThemePalette = () => (
    <div ref={themePaletteRef} className="relative">
      <button
        type="button"
        onClick={() => setIsThemePaletteOpen((open) => !open)}
        aria-label="Theme settings"
        aria-expanded={isThemePaletteOpen}
        title="Theme settings"
        className={`ua-upload-header-action p-2 rounded-lg transition-colors ${isDarkMode ? "text-gray-200 hover:bg-gray-700" : "text-gray-600 hover:bg-gray-100"}`}
      >
        <PaletteIcon />
      </button>
      {isThemePaletteOpen && (
        <div
          className={`ua-upload-panel absolute right-0 top-full z-50 mt-2 w-56 rounded-lg border p-3 shadow-xl ${isDarkMode ? "border-gray-700 bg-gray-800 text-gray-100" : "border-gray-200 bg-white text-gray-800"}`}
        >
          {renderAppearanceControls("opacity-70")}
        </div>
      )}
    </div>
  );

  const renderHelpButton = () => (
    <button
      type="button"
      onClick={() => setIsHelpResourcesOpen(true)}
      aria-label="Help and resources"
      aria-haspopup="dialog"
      title="Help and resources"
      className="ua-upload-header-action gap-2 rounded-lg p-2 text-sm font-semibold"
    >
      <HelpIcon />
    </button>
  );

  const renderUpdateButton = () => (
    <button
      type="button"
      onClick={() =>
        visibleUpdateStatus ? setIsUpdateStatusOpen(true) : openChangelog()
      }
      aria-label={
        visibleUpdateStatus
          ? `Update ${visibleUpdateStatus.latest_version} is available`
          : "View changelog"
      }
      aria-haspopup="dialog"
      title={
        visibleUpdateStatus
          ? `Update ${visibleUpdateStatus.latest_version} is available`
          : "View changelog"
      }
      className={`ua-upload-header-action gap-2 rounded-lg p-2 text-sm font-semibold ${visibleUpdateStatus ? "ua-update-mobile-button" : ""}`}
    >
      {visibleUpdateStatus ? <UpdateIcon /> : <ChangelogIcon />}
    </button>
  );

  const handleLogout = async () => {
    try {
      const response = await apiFetch(`${APP_BASE}/logout`, { method: "POST" });
      window.location = response?.redirected
        ? response.url
        : `${APP_BASE}/login`;
    } catch (_error) {
      window.location = `${APP_BASE}/login`;
    }
  };

  const renderRailAppearance = () => (
    <div ref={themePaletteRef} className="relative min-w-0 w-full">
      <button
        type="button"
        className="ua-app-rail-button rounded-lg"
        onClick={() => setIsThemePaletteOpen((open) => !open)}
        aria-label="Appearance"
        aria-expanded={isThemePaletteOpen}
      >
        <PaletteIcon />
        <span>Appearance</span>
      </button>
      {isThemePaletteOpen && (
        <div className="ua-app-rail-popover absolute bottom-0 left-full z-[60] ml-2 w-64 rounded-xl border p-4 shadow-2xl">
          <h2 className="text-sm font-semibold">Appearance</h2>
          {renderAppearanceControls("ua-app-rail-popover-label")}
        </div>
      )}
    </div>
  );

  // Mobile state
  const [isMobile, setIsMobile] = useState(() => shouldUseMobileLayout());
  const [activePanel, setActivePanel] = useState("main"); // 'main' | 'files' | 'args'

  // File Browser search states
  const [fileBrowserSearch, setFileBrowserSearch] = useState("");
  const [fileBrowserSearchResults, setFileBrowserSearchResults] =
    useState(null);
  const [fileBrowserSearchLoading, setFileBrowserSearchLoading] =
    useState(false);
  const [fileBrowserRefreshing, setFileBrowserRefreshing] = useState(false);
  const fileBrowserSearchTimer = useRef(null);
  const fileBrowserSearchCompletion = useRef(null);
  const fileBrowserSearchQuery = useRef("");
  const fileBrowserSearchId = useRef(0);

  // Preserve the desktop file browser scroll position while the
  // browser is temporarily unmounted or rerendered.
  const [fileBrowserRestoring, setFileBrowserRestoring] = useState(true);
  const [fileBrowserScrollTop] = useState(() => {
    const saved = Number(storage.get(FILE_BROWSER_SCROLL_KEY));
    return Number.isFinite(saved) && saved >= 0 ? saved : 0;
  });
  const fileBrowserScrollTopRef = useRef(fileBrowserScrollTop);
  const fileBrowserRef = useRef(null);
  const expandedFoldersRef = useRef(expandedFolders);

  useEffect(() => {
    expandedFoldersRef.current = expandedFolders;
    storage.set(
      FILE_BROWSER_EXPANDED_KEY,
      JSON.stringify([...expandedFolders]),
    );
  }, [expandedFolders]);

  useLayoutEffect(() => {
    if (fileBrowserRef.current && !fileBrowserRestoring) {
      fileBrowserRef.current.scrollTop = fileBrowserScrollTopRef.current;
    }
  });

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
  const inputRef = useRef(null);
  // The GUI prompt's text field, focused when a correction chip fills it.
  const runGuiAnswerRef = useRef(null);
  const isSendingInputRef = useRef(false);
  const activeTabIdRef = useRef("tab-1");
  const uploadTabCounterRef = useRef(1);
  const tabRuntimeRef = useRef(null);
  if (tabRuntimeRef.current === null) {
    const firstTab = createUploadTabRuntime();
    firstTab.run.isExecuting = Boolean(screenshotMode);
    firstTab.gui = initialRunGuiState();
    tabRuntimeRef.current = new Map([["tab-1", firstTab]]);
    // Demo background tabs only feed the tab bar; switching to them is disabled.
    screenshotMode?.tabs.slice(1).forEach((tab, index) => {
      const runtime = createUploadTabRuntime();
      runtime.run.isExecuting = ["running", "input", "scheduled"].includes(
        tab.status,
      );
      runtime.awaiting = tab.status === "input";
      runtime.scheduled = tab.status === "scheduled";
      if (!runtime.run.isExecuting) runtime.result = tab.status;
      tabRuntimeRef.current.set(`tab-${index + 2}`, runtime);
    });
    uploadTabCounterRef.current = tabRuntimeRef.current.size;
  }

  const getTabRuntime = (tabId) => tabRuntimeRef.current.get(tabId);

  const refreshUploadTabStatus = (tabId) => {
    const runtime = getTabRuntime(tabId);
    if (!runtime) return;
    const status = getUploadTabStatus(runtime);
    setUploadTabs((tabs) =>
      tabs.map((tab) =>
        tab.id === tabId && tab.status !== status ? { ...tab, status } : tab,
      ),
    );
  };

  /**
   * Update a tab's run state. Background tabs keep it in their runtime; the
   * active tab also mirrors it into React state so the existing UI renders it.
   */
  const updateTabRun = (tabId, patch) => {
    const runtime = getTabRuntime(tabId);
    if (!runtime) return;
    const isActive = tabId === activeTabIdRef.current;
    if ("sessionId" in patch) {
      runtime.run.sessionId = patch.sessionId;
      if (isActive) setSessionId(patch.sessionId);
    }
    if ("isExecuting" in patch) {
      runtime.run.isExecuting = patch.isExecuting;
      if (isActive) setIsExecuting(patch.isExecuting);
    }
    if ("progressItems" in patch) {
      const value = patch.progressItems;
      if (isActive) setProgressItems(value);
      else
        runtime.view.progressItems =
          typeof value === "function"
            ? value(runtime.view.progressItems)
            : value;
    }
    refreshUploadTabStatus(tabId);
  };

  const scrollTabOutput = (tabId) => {
    if (tabId !== activeTabIdRef.current) return;
    const host = richOutputRef.current;
    if (!host) return;
    // Scroll only the terminal, including while its view is hidden.
    setTimeout(() => {
      host.scrollTop = host.scrollHeight;
    }, 0);
  };

  const mountActiveTabOutput = () => {
    const host = richOutputRef.current;
    const runtime = getTabRuntime(activeTabIdRef.current);
    if (!host || !runtime) return;
    if (host.firstChild !== runtime.output || host.childNodes.length !== 1) {
      host.replaceChildren(runtime.output);
    }
    host.scrollTop = host.scrollHeight;
  };

  // Each tab owns a detached output node; the visible terminal shows the active one.
  const attachRichOutputHost = useCallback((node) => {
    richOutputRef.current = node;
    if (node) mountActiveTabOutput();
  }, []);

  useEffect(() => {
    mountActiveTabOutput();
  }, [activeTabId]);

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

  /** Fold one session event into a tab's GUI state; only the active tab re-renders. */
  const applyRunGuiEvent = (event, tabId = activeTabIdRef.current) => {
    const runtime = getTabRuntime(tabId);
    if (!runtime) return;
    const next = RunGui.reduceRunGuiEvent(runtime.gui, event);
    if (next === runtime.gui) return;
    runtime.gui = next;
    if (tabId === activeTabIdRef.current) setRunGui(next);
  };

  const resetRunGui = (tabId = activeTabIdRef.current) => {
    const runtime = getTabRuntime(tabId);
    if (!runtime) return;
    runtime.gui = RunGui.createRunGuiState();
    if (tabId === activeTabIdRef.current) setRunGui(runtime.gui);
  };

  const applyProgressEvent = (event, tabId = activeTabIdRef.current) => {
    if (!event || typeof event !== "object") return;
    const runtime = getTabRuntime(tabId);
    if (event.op === "reset") {
      runtime?.waiting.clear();
      updateTabRun(tabId, { progressItems: [] });
      return;
    }
    if (!event.id) return;
    // The backend reports cross-tab resource waits as "wait-<resource>" items.
    if (runtime && String(event.id).startsWith("wait-")) {
      if (event.status === "waiting") runtime.waiting.add(event.id);
      else runtime.waiting.delete(event.id);
    }
    updateTabRun(tabId, {
      progressItems: (prev) => {
        const existingIndex = prev.findIndex((item) => item.id === event.id);
        if (existingIndex === -1) {
          return sortProgressItems([...prev, event]);
        }
        const next = [...prev];
        next[existingIndex] = { ...next[existingIndex], ...event };
        return sortProgressItems(next);
      },
    });
  };

  const renderProgressPanel = (compact = false, showHeader = true) => {
    if (!visibleProgressItems.length) return null;

    return (
      <div
        className={`rounded-lg border p-3 shadow-xl backdrop-blur-sm ${isDarkMode ? "border-gray-700 bg-gray-800" : "border-gray-200 bg-white/95"}`}
      >
        {showHeader && (
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
        )}
        {/* Only the floating panel caps its height; the sidebar already scrolls. */}
        <div
          className={
            compact
              ? "space-y-2 max-h-[40vh] overflow-y-auto pr-1"
              : "space-y-3"
          }
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
            // Speed meters show a rate against a limit: green when under it, amber when over.
            const isSpeedMeter = item.unit === "kbps";
            const isOverLimit = isSpeedMeter && hasTotal && current > total;
            const statusTone = isCompleted
              ? isDarkMode
                ? "text-emerald-300"
                : "text-emerald-700"
              : isFailed
                ? isDarkMode
                  ? "text-rose-300"
                  : "text-rose-700"
                : isSpeedMeter
                  ? isOverLimit
                    ? isDarkMode
                      ? "text-amber-300"
                      : "text-amber-700"
                    : isDarkMode
                      ? "text-emerald-300"
                      : "text-emerald-700"
                  : "ua-accent-text";
            const progressTone = isCompleted
              ? "bg-emerald-500"
              : isFailed
                ? "bg-rose-500"
                : isSpeedMeter
                  ? isOverLimit
                    ? "bg-amber-500"
                    : "bg-emerald-500"
                  : "ua-accent-indicator";
            let summary = "";
            if (hasTotal) {
              if (item.unit === "percent")
                summary = `${Math.round(clampedPercent)}%`;
              else if (isSpeedMeter)
                summary = `${Math.round(current)} / ${Math.round(total)} KB/s`;
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
        <div className="ua-upload-panel-header p-3 border-b flex-shrink-0">
          <div className="flex items-center justify-between gap-3">
            <h2
              className={`text-base font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
            >
              <ProgressIcon />
              Binary Progress
            </h2>
            {visibleProgressItems.length > 0 && (
              <span
                className={`text-xs font-medium ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
              >
                {visibleProgressItems.length} active
              </span>
            )}
          </div>
          <p
            className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
          >
            Live progress from external tools while the queue is running.
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          {renderProgressPanel(false, false) || (
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

  const parseTrackersFromArgs = (
    argsString,
    defaultTrackersSet,
    aliases = trackerAliases,
  ) => {
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
        .map((name) => (Object.hasOwn(aliases, name) ? aliases[name] : name))
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

  const toggleTrackerStatusDetails = (trackerName) => {
    setExpandedTrackerStatusDetails((current) => {
      const next = new Set(current);
      if (next.has(trackerName)) next.delete(trackerName);
      else next.add(trackerName);
      return next;
    });
  };

  const checkTrackerStatuses = async (trackerNames) => {
    if (!window.checkUATrackerStatuses || trackerNames.length === 0) return;
    setIsCheckingTrackerStatuses(true);
    setTrackerStatusError("");
    try {
      const payload = await window.checkUATrackerStatuses(trackerNames);
      setTrackerStatuses((current) => ({
        ...current,
        ...(payload.statuses || {}),
      }));
    } catch (error) {
      setTrackerStatusError(
        error?.message || "The tracker status check failed.",
      );
    } finally {
      setIsCheckingTrackerStatuses(false);
    }
  };

  const renderTrackerSelector = () => {
    if (!trackers || trackers.length === 0) return null;

    const hasConfiguredMetadata = trackers.some(
      (tracker) => typeof tracker.configured === "boolean",
    );
    const visibleTrackers =
      showAllSupportedTrackers || !hasConfiguredMetadata
        ? trackers
        : trackers.filter(
            (tracker) =>
              tracker.configured || selectedTrackers.has(tracker.name),
          );
    const statusTargets = trackers
      .filter(
        (tracker) => tracker.configured || selectedTrackers.has(tracker.name),
      )
      .map((tracker) => tracker.name);
    const selectedStatusIssues = trackers.filter((tracker) => {
      const status = trackerStatuses[tracker.name];
      const state = status?.state;
      return (
        selectedTrackers.has(tracker.name) &&
        !status?.stale &&
        (state === "issue" || state === "unavailable")
      );
    });
    const relevantStatuses = Object.fromEntries(
      statusTargets
        .filter((name) => trackerStatuses[name]?.checked_at)
        .map((name) => [name, trackerStatuses[name]]),
    );
    const checkedAge = window.formatUATrackerStatusAge
      ? window.formatUATrackerStatusAge(relevantStatuses)
      : "Not checked";

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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider opacity-75">
            Select Trackers (-tk):
          </span>
          <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => checkTrackerStatuses(statusTargets)}
                className="ua-tracker-status-check rounded-md border px-2 py-1 text-[10px] font-semibold"
                disabled={
                  isExecuting ||
                  isCheckingTrackerStatuses ||
                  statusTargets.length === 0
                }
              >
                {isCheckingTrackerStatuses ? "Checking…" : "Check status"}
              </button>
              <span className="text-[10px] opacity-60">{checkedAge}</span>
            </div>
            <label className="inline-flex cursor-pointer items-center gap-1.5 text-[10px] font-medium">
              <input
                type="checkbox"
                checked={showAllSupportedTrackers}
                onChange={(event) =>
                  setShowAllSupportedTrackers(event.target.checked)
                }
                className="ua-theme-checkbox h-3.5 w-3.5"
                disabled={isExecuting}
              />
              <span>Show all supported trackers</span>
            </label>
            <div className="flex gap-2">
              <button
                type="button"
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
                className="ua-accent-link text-[10px] underline font-medium"
                disabled={isExecuting}
              >
                Reset to Defaults
              </button>
              <button
                type="button"
                onClick={() => {
                  const nextSet = new Set();
                  setSelectedTrackers(nextSet);
                  setCustomArgs(
                    syncTrackersToArgs(customArgs, nextSet, defaultTrackers),
                  );
                }}
                className="ua-accent-link text-[10px] underline font-medium"
                disabled={isExecuting}
              >
                Clear All
              </button>
            </div>
          </div>
        </div>
        {trackerAliasError && (
          <div
            className="ua-tracker-status-advisory rounded-md border px-3 py-2 text-xs"
            data-tone="danger"
            role="alert"
          >
            {trackerAliasError}. Update CLI Alias in tracker configuration
            before using -tk or --trackers.
          </div>
        )}
        {trackerStatusError && (
          <div
            className="ua-tracker-status-advisory rounded-md border px-3 py-2 text-xs"
            data-tone="danger"
            role="alert"
          >
            {trackerStatusError}
          </div>
        )}
        {selectedStatusIssues.length > 0 && (
          <div className="space-y-2" role="status">
            {selectedStatusIssues.map((tracker) => {
              const status = trackerStatuses[tracker.name];
              const displayName = tracker.display_name || tracker.name;
              const summary = window.getUATrackerStatusSummary
                ? window.getUATrackerStatusSummary(displayName, status)
                : `${displayName} reported an issue`;
              const statusAge = window.formatUATrackerStatusAge
                ? window.formatUATrackerStatusAge({
                    [tracker.name]: status,
                  })
                : "Just checked";
              const ageText =
                statusAge === "Just checked"
                  ? "just now"
                  : statusAge.toLowerCase();
              const isExpanded = expandedTrackerStatusDetails.has(tracker.name);
              const detailId = `tracker-status-details-${String(tracker.name)
                .toLowerCase()
                .replace(/[^a-z0-9_-]+/g, "-")}`;
              const checkedAt = window.formatUATrackerStatusTimestamp
                ? window.formatUATrackerStatusTimestamp(status)
                : "";

              return (
                <div
                  key={tracker.name}
                  className="ua-tracker-status-advisory ua-tracker-status-warning-row rounded-md border px-3 py-2 text-xs"
                  data-tone="warning"
                >
                  <div className="flex min-w-0 flex-1 items-start gap-2">
                    <span
                      className="ua-tracker-status-warning-icon"
                      aria-hidden="true"
                    >
                      ⚠
                    </span>
                    <p className="min-w-0 flex-1">
                      <span className="font-semibold">{summary}</span> {ageText}
                      .{" "}
                      <span className="ua-tracker-status-warning-guidance">
                        Verify it before uploading or deselect it.
                      </span>
                    </p>
                  </div>
                  <div className="ua-tracker-status-warning-actions flex shrink-0 items-center gap-3">
                    <button
                      type="button"
                      className="ua-tracker-status-warning-action"
                      aria-expanded={isExpanded}
                      aria-controls={detailId}
                      onClick={() => toggleTrackerStatusDetails(tracker.name)}
                    >
                      {isExpanded ? "Hide details" : "Details"}
                    </button>
                    <button
                      type="button"
                      className="ua-tracker-status-warning-action"
                      disabled={isExecuting}
                      onClick={() => handleTrackerToggle(tracker.name)}
                    >
                      Deselect
                    </button>
                  </div>
                  {isExpanded && (
                    <div
                      id={detailId}
                      className="ua-tracker-status-warning-details"
                    >
                      {status?.message ||
                        "No additional details are available."}
                      {checkedAt ? ` Checked ${checkedAt}.` : ""}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
        <div
          className={`ua-tracker-chip-list grid gap-2 pr-1 ${!isExecuting && !isTerminalView ? "" : "max-h-48 overflow-y-auto"}`}
        >
          {visibleTrackers.length === 0 && (
            <span className="text-xs opacity-70">
              No configured trackers. Turn on Show all supported trackers to
              choose one.
            </span>
          )}
          {visibleTrackers.map((tracker) => {
            const isSelected = selectedTrackers.has(tracker.name);
            const isDefault = defaultTrackers.has(tracker.name);
            const isConfigured = tracker.configured !== false;
            const hasFavicon =
              tracker.favicon && !failedFavicons.has(tracker.name);
            const trackerStatus = trackerStatuses[tracker.name] || {
              state: "not_checked",
              message: "Not checked yet.",
            };
            const trackerStatusText = window.getUATrackerStatusText
              ? window.getUATrackerStatusText(trackerStatus)
              : "Not checked";

            return (
              <button
                type="button"
                key={tracker.name}
                onClick={() => handleTrackerToggle(tracker.name)}
                disabled={isExecuting}
                data-color-mode={isDarkMode ? "dark" : "light"}
                className={`ua-tracker-chip flex min-w-0 items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm font-medium border transition-all ${
                  isSelected
                    ? "ua-tracker-chip-selected"
                    : isDarkMode
                      ? "bg-gray-800 border-gray-700 text-gray-400 hover:bg-gray-700 hover:text-gray-200"
                      : "bg-white border-gray-300 text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
                title={`${tracker.display_name}${isDefault ? " (Default)" : ""}${
                  !isConfigured ? " (Not configured)" : ""
                } — ${trackerStatusText}`}
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
                <span className="ua-tracker-chip-label min-w-0 flex-1 truncate text-left">
                  {tracker.display_name}
                </span>
                <span
                  className="ua-tracker-health-dot"
                  data-state={
                    trackerStatus.stale
                      ? "not_checked"
                      : trackerStatus.state || "not_checked"
                  }
                  role="img"
                  aria-label={trackerStatusText}
                />
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
  }, [customArgs, defaultTrackers, trackerAliases]);

  // Get current values from args
  const descFilePath = argumentBuilder.getArgumentState(
    argumentBuilder.parseArguments(customArgs, argumentIndex),
    argumentBuilder.keyForOption(argumentIndex, "--descfile"),
  ).value;
  const descLinkUrl = argumentBuilder.getArgumentState(
    argumentBuilder.parseArguments(customArgs, argumentIndex),
    argumentBuilder.keyForOption(argumentIndex, "--desclink"),
  ).value;

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
    if (screenshotMode) return undefined;
    coverRequestRef.current += 1;
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
      setCoverAction("");
      setExpandedScreenshot(null);
      setScreenshotError("");
      setPendingDeleteScreenshot("");
      setIsScreenshotReviewOpen(false);
      setIsDescriptionReviewOpen(false);
      setIsMediaInfoOpen(false);
      setExpandedReviewPanel("");
      setExecutionMediaInfo(null);
      setMediaInfoStatus("idle");
      setActivePanel((panel) =>
        ["screenshots", "description", "mediainfo"].includes(panel)
          ? "main"
          : panel,
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

  useEffect(() => {
    coverRequestRef.current += 1;
    setCoverAction("");
  }, [executionPreview?.media_id]);

  const isMediaInfoVisible = isMediaInfoOpen || activePanel === "mediainfo";
  const mediaInfoLabel =
    executionMediaInfo?.kind === "bdinfo" ? "BDInfo" : "MediaInfo";
  // Hide review panels a category never produces. While the category is still
  // unknown every button stays visible so nothing that will exist is hidden.
  const executionCategory = String(
    executionPreview?.category || "",
  ).toUpperCase();
  const showScreenshotsButton = !(
    executionCategory === "MUSIC" ||
    (executionCategory === "BOOK" && executionPreview?.audiobook)
  );
  const showMediaInfoButton = executionCategory !== "GAME";

  useEffect(() => {
    if (!showScreenshotsButton) {
      setExpandedScreenshot(null);
      setIsScreenshotReviewOpen(false);
      setExpandedReviewPanel((panel) => (panel === "screenshots" ? "" : panel));
      setActivePanel((panel) => (panel === "screenshots" ? "main" : panel));
    }
  }, [showScreenshotsButton]);

  useEffect(() => {
    if (!showMediaInfoButton) {
      setIsMediaInfoOpen(false);
      setExpandedReviewPanel((panel) => (panel === "mediainfo" ? "" : panel));
      setActivePanel((panel) => (panel === "mediainfo" ? "main" : panel));
    }
  }, [showMediaInfoButton]);

  useEffect(() => {
    // Reports are large and rarely change, so load them only while the panel
    // is visible and retry until the run has generated them.
    if (screenshotMode || !isExecuting || !sessionId || !isMediaInfoVisible) {
      return undefined;
    }
    let cancelled = false;
    let timeoutId;
    const controller = new AbortController();

    const loadMediaInfo = async () => {
      try {
        const response = await apiFetch(
          `${API_BASE}/execution_mediainfo?session_id=${encodeURIComponent(sessionId)}`,
          { cache: "no-store", signal: controller.signal },
        );
        const data = await response.json().catch(() => null);
        if (cancelled) return;
        if (response.ok && data?.success && Array.isArray(data.reports)) {
          setExecutionMediaInfo(data);
          setMediaInfoStatus("ready");
          setSelectedMediaInfoKey((key) =>
            data.reports.some((report) => report.key === key)
              ? key
              : data.reports[0]?.key || "",
          );
          return;
        }
        setExecutionMediaInfo(null);
        setMediaInfoStatus(response.status === 404 ? "pending" : "error");
      } catch (_error) {
        if (cancelled) return;
        setMediaInfoStatus("error");
      }
      timeoutId = window.setTimeout(loadMediaInfo, 3000);
    };

    // Reopening the panel keeps the cached report; a different execution or
    // file must not show (or copy) the previous release's report meanwhile.
    const mediaInfoTarget = `${sessionId}\n${executionPreview?.path || ""}`;
    if (mediaInfoTargetRef.current !== mediaInfoTarget) {
      mediaInfoTargetRef.current = mediaInfoTarget;
      setExecutionMediaInfo(null);
      setMediaInfoStatus("loading");
    } else {
      setMediaInfoStatus((status) => (status === "ready" ? status : "loading"));
    }
    loadMediaInfo();

    return () => {
      cancelled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      controller.abort();
    };
  }, [
    API_BASE,
    isExecuting,
    sessionId,
    isMediaInfoVisible,
    executionPreview?.path,
  ]);

  const setReviewPanelOpen = (panel, open) => {
    setIsScreenshotReviewOpen(open && panel === "screenshots");
    setIsDescriptionReviewOpen(open && panel === "description");
    setIsMediaInfoOpen(open && panel === "mediainfo");
    setExpandedReviewPanel(
      open && reviewPanelsInModal && !isMobile ? panel : "",
    );
  };

  const rememberReviewPanelsInModal = (inModal) => {
    setReviewPanelsInModal(inModal);
    storage.set(REVIEW_PANELS_IN_MODAL_KEY, inModal ? "true" : "false");
  };

  // Closing the larger view also closes the panel when it was opened there,
  // unless the user asked to return it to the sidebar.
  const closeReviewModal = ({ toSidebar = false } = {}) => {
    // The screenshot lightbox handles its own Escape key first.
    if (expandedScreenshot) return;
    if (expandedReviewPanel === "description" && descriptionDirty) {
      saveExecutionDescription();
    }
    if (toSidebar) {
      rememberReviewPanelsInModal(false);
      setExpandedReviewPanel("");
    } else if (reviewPanelsInModal) {
      setReviewPanelOpen(expandedReviewPanel, false);
    } else {
      setExpandedReviewPanel("");
    }
  };
  const reviewModalRef = useModalFocus(
    closeReviewModal,
    Boolean(expandedReviewPanel),
  );

  useEffect(() => {
    if (isMobile) setExpandedReviewPanel("");
  }, [isMobile]);

  // The file browser can open in a larger modal, like the review panels.
  const [isFileBrowserExpanded, setIsFileBrowserExpanded] = useState(false);
  const fileBrowserModalRef = useModalFocus(
    () => setIsFileBrowserExpanded(false),
    isFileBrowserExpanded,
  );
  useEffect(() => {
    // Starting an upload replaces the sidebar browser with the run's progress.
    if (isMobile || isExecuting) setIsFileBrowserExpanded(false);
  }, [isMobile, isExecuting]);

  // The Arguments panel opens in the same kind of modal.
  const [isArgumentsExpanded, setIsArgumentsExpanded] = useState(false);
  const argumentsModalRef = useModalFocus(
    () => setIsArgumentsExpanded(false),
    isArgumentsExpanded,
  );
  useEffect(() => {
    if (isMobile || isExecuting) setIsArgumentsExpanded(false);
  }, [isMobile, isExecuting]);

  const renderReviewExpandButton = (panel) => {
    if (isMobile) return null;
    const isExpanded = expandedReviewPanel === panel;
    const label = isExpanded ? "Return to sidebar" : "Open in a larger view";
    const buttonClassName = `flex-none rounded-md p-2 transition-colors ${isDarkMode ? "text-gray-300 hover:bg-gray-700" : "text-gray-600 hover:bg-gray-100"}`;
    return (
      <div className="flex flex-none items-center gap-0.5">
        <button
          type="button"
          onClick={() => {
            if (isExpanded) {
              closeReviewModal({ toSidebar: true });
            } else {
              rememberReviewPanelsInModal(true);
              setExpandedReviewPanel(panel);
            }
          }}
          className={buttonClassName}
          title={label}
          aria-label={label}
        >
          <LucideIcon
            name={isExpanded ? "minimize-2" : "maximize-2"}
            className="w-4 h-4"
          />
        </button>
        {isExpanded && (
          <button
            type="button"
            onClick={() => closeReviewModal()}
            className={buttonClassName}
            title="Close"
            aria-label="Close"
          >
            <LucideIcon name="x" className="w-4 h-4" />
          </button>
        )}
      </div>
    );
  };

  const copyMediaInfoReport = async (content) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(content);
      } else {
        // navigator.clipboard only exists in secure contexts; plain-HTTP LAN access needs the legacy path.
        const area = document.createElement("textarea");
        area.value = content;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        const copied = document.execCommand("copy");
        area.remove();
        if (!copied) throw new Error("Copy failed");
      }
      setMediaInfoCopied(true);
      window.setTimeout(() => setMediaInfoCopied(false), 1500);
    } catch (_error) {
      setMediaInfoCopied(false);
    }
  };

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
    setScreenshotError("");
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
        setScreenshotError(data?.error || `Could not ${action} screenshot.`);
        return;
      }
      await refreshExecutionScreenshots();
    } catch (error) {
      console.error(`Could not ${action} screenshot:`, error);
      setScreenshotError(`Could not ${action} screenshot. Please try again.`);
    } finally {
      setScreenshotActionId("");
    }
  };

  const regenerateExecutionCover = async () => {
    const mediaId = executionPreview?.media_id;
    if (!sessionId || !mediaId || coverAction) return;
    const requestToken = ++coverRequestRef.current;
    setCoverAction("regenerate");
    try {
      const response = await apiFetch(
        `${API_BASE}/execution_preview_cover/regenerate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, media_id: mediaId }),
        },
      );
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.success) {
        window.alert(data?.error || "Could not regenerate the XXX cover.");
        return;
      }
      if (coverRequestRef.current === requestToken) {
        setExecutionPreview((previous) =>
          previous?.media_id === mediaId
            ? { ...previous, poster_url: data.poster_url }
            : previous,
        );
      }
    } catch (error) {
      console.error("Could not regenerate XXX cover:", error);
      window.alert("Could not regenerate the XXX cover. Please try again.");
    } finally {
      if (coverRequestRef.current === requestToken) setCoverAction("");
    }
  };

  const addExecutionScreenshot = async (group = "main") => {
    if (!sessionId || screenshotActionId || !canAddExecutionScreenshot) return;
    setScreenshotActionId("add");
    setScreenshotError("");
    try {
      const response = await apiFetch(`${API_BASE}/execution_screenshots/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, group }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.success) {
        setScreenshotError(data?.error || "Could not add screenshot.");
        return;
      }
      await refreshExecutionScreenshots();
    } catch (error) {
      console.error("Could not add screenshot:", error);
      setScreenshotError("Could not add screenshot. Please try again.");
    } finally {
      setScreenshotActionId("");
    }
  };

  useEffect(() => {
    if (!expandedScreenshot) return;
    const ordered = orderScreenshotsByGroup(executionScreenshots);
    const index = ordered.findIndex(
      (screenshot) => screenshot.id === expandedScreenshot,
    );
    if (index >= 0) {
      expandedScreenshotIndexRef.current = index;
      return;
    }
    // Deleting a frame removes its ID; stay on the neighbour that took its
    // place instead of closing the review.
    const fallback =
      ordered[Math.min(expandedScreenshotIndexRef.current, ordered.length - 1)];
    setExpandedScreenshot(fallback ? fallback.id : null);
  }, [executionScreenshots, expandedScreenshot]);

  useEffect(() => {
    setIsScreenshotZoomed(false);
    setExpandedScreenshotSize(null);
  }, [expandedScreenshot]);

  useEffect(() => {
    if (!pendingDeleteScreenshot) return undefined;
    const timeoutId = window.setTimeout(
      () => setPendingDeleteScreenshot(""),
      4000,
    );
    return () => window.clearTimeout(timeoutId);
  }, [pendingDeleteScreenshot]);

  useEffect(() => {
    if (!expandedScreenshot) return undefined;
    const handleKeyDown = (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      if (event.target.closest?.("input, textarea, select")) return;
      const ordered = orderScreenshotsByGroup(executionScreenshots);
      const index = ordered.findIndex(
        (screenshot) => screenshot.id === expandedScreenshot,
      );
      const next = ordered[index + (event.key === "ArrowRight" ? 1 : -1)];
      if (index < 0 || !next) return;
      event.preventDefault();
      setExpandedScreenshot(next.id);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [executionScreenshots, expandedScreenshot]);

  // Update descfile in args
  const updateDescFile = (path) => {
    setCustomArgs((prev) =>
      argumentBuilder.setArgumentValue(
        prev || "",
        argumentIndex,
        argumentBuilder.keyForOption(argumentIndex, "--descfile"),
        path,
      ),
    );
  };

  // Update desclink in args
  const updateDescLink = (url) => {
    setCustomArgs((prev) =>
      argumentBuilder.setArgumentValue(
        prev || "",
        argumentIndex,
        argumentBuilder.keyForOption(argumentIndex, "--desclink"),
        url,
      ),
    );
  };

  const appendHtmlFragment = (rawHtml, tabId = activeTabIdRef.current) => {
    const runtime = getTabRuntime(tabId);
    if (!runtime) return;
    runtime.output.appendChild(
      createUploadOutputFragment((rawHtml || "").trim()),
    );
    scrollTabOutput(tabId);
  };

  const appendSystemMessage = (
    text,
    kind = "info",
    tabId = activeTabIdRef.current,
  ) => {
    const runtime = getTabRuntime(tabId);
    if (!runtime) return;
    const el = document.createElement("div");
    // Support multiple kinds: error, user-input, and default info
    if (kind === "error") el.className = "text-red-400";
    else if (kind === "user-input") el.className = "text-green-300";
    else el.className = "text-blue-300";
    el.style.whiteSpace = "pre-wrap";
    el.textContent = text;
    runtime.output.appendChild(el);
    scrollTabOutput(tabId);
  };

  const appendWelcomeMessage = (tabId = activeTabIdRef.current) => {
    appendSystemMessage("Upload-Assistant Interactive Output", "info", tabId);
    appendSystemMessage(
      '\nQuick Start:\n  1. Select a file or folder from the left panel\n  2. Add Upload-Assistant arguments (optional)\n  3. Click "Execute Upload" to start\n',
      "info",
      tabId,
    );
  };

  const sendInput = async (session_id, input) => {
    if (isSendingInputRef.current || !session_id) return;
    isSendingInputRef.current = true;
    setIsSendingInput(true);
    const tabId = activeTabIdRef.current;
    const runtime = getTabRuntime(tabId);
    const promptId = runtime?.gui.prompt?.id ?? null;
    if (runtime) {
      runtime.awaiting = false;
      runtime.gui = RunGui.markRunGuiPromptAnswered(runtime.gui);
      setRunGui(runtime.gui);
      refreshUploadTabStatus(tabId);
    }
    // Reopen the GUI prompt so the answer can be sent again.
    const restorePrompt = () => {
      const current = getTabRuntime(tabId);
      if (!current || promptId === null) return;
      current.gui = RunGui.markRunGuiPromptAnswered(
        current.gui,
        false,
        promptId,
      );
      current.awaiting = true;
      if (tabId === activeTabIdRef.current) setRunGui(current.gui);
      refreshUploadTabStatus(tabId);
    };
    // Optimistically echo the user's input locally so it appears before
    // any subsequent server-generated prompt / output.
    appendSystemMessage("> " + input, "user-input");
    setUserInput("");
    try {
      const response = await apiFetch(`${API_BASE}/input`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id, input }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    } catch (err) {
      console.error("Failed to send input:", err);
      appendSystemMessage("Failed to send input", "error", tabId);
      restorePrompt();
    } finally {
      isSendingInputRef.current = false;
      setIsSendingInput(false);
    }
  };

  // Initial welcome message in the rich output area
  useEffect(() => {
    if (screenshotMode) {
      appendHtmlFragment(screenshotMode.output);
      return;
    }
    appendWelcomeMessage();
  }, []);

  const loadBrowseRoots = async () => {
    try {
      const response = await apiFetch(`${API_BASE}/browse_roots`);
      const data = await response.json();

      if (data.success && data.items) {
        setDirectories(data.items);
        // Parents must be populated before their saved descendants can be found.
        for (const path of getFileBrowserRestorePaths(
          expandedFoldersRef.current,
          data.items,
        )) {
          await loadFolderContents(path);
        }
      }
    } catch (error) {
      console.error("Failed to load browse roots:", error);
    } finally {
      setFileBrowserRestoring(false);
    }
  };

  /** Reload visible file-browser data without resetting navigation state. */
  const refreshFileBrowser = async () => {
    if (fileBrowserRefreshing) return;
    setFileBrowserRefreshing(true);
    try {
      setFileBrowserRestoring(true);
      await loadBrowseRoots();
      if (fileBrowserSearchQuery.current) {
        await handleFileBrowserSearch(fileBrowserSearchQuery.current);
      }
    } finally {
      setFileBrowserRefreshing(false);
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
    window.setUAThemeMode(isDarkMode);
  }, [isDarkMode]);

  useEffect(() => {
    if (isExecuting) {
      setIsTerminalView(true);
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
        const mobile = shouldUseMobileLayout();
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
    if (screenshotMode) return;
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
          const aliases = data.tracker_aliases || {};
          setTrackerAliases(aliases);
          setTrackerAliasError(data.alias_error || "");
          const initialSet = parseTrackersFromArgs(
            customArgs,
            defaultSet,
            aliases,
          );
          setSelectedTrackers(initialSet);

          if (window.loadUATrackerStatuses) {
            window
              .loadUATrackerStatuses()
              .then((statusPayload) =>
                setTrackerStatuses(statusPayload.statuses || {}),
              )
              .catch(() => {
                // Cached status is optional; a manual check surfaces errors.
              });
          }
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
      fileBrowserSearchCompletion.current?.();
      fileBrowserSearchCompletion.current = null;
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

  /** Paths in the order the file browser displays them. */
  const getVisiblePaths = () => {
    if (fileBrowserSearch) {
      if (!fileBrowserSearchResults || !fileBrowserSearchResults.items)
        return [];
      return sortItems(fileBrowserSearchResults.items).map((item) => item.path);
    }

    // Sort like renderFileTree so Shift+click ranges match what is on screen.
    const traverse = (nodes, level) => {
      let paths = [];
      for (const node of sortItems(nodes, level)) {
        paths.push(node.path);
        if (
          node.type === "folder" &&
          expandedFolders.has(node.path) &&
          node.children
        ) {
          paths = paths.concat(traverse(node.children, level + 1));
        }
      }
      return paths;
    };
    return traverse(directories, 0);
  };

  const handleToggleSelectAll = () => {
    setManualPathsText(null);
    setPathInputError("");
    const visible = getVisiblePaths();
    if (visible.length === 0) return;

    const allSelected = visible.every((p) =>
      selectedPaths.some((x) => x.path === p),
    );
    const next = allSelected
      ? selectedPaths.filter((p) => !visible.includes(p.path))
      : [...selectedPaths];
    if (!allSelected) {
      visible.forEach((p) => {
        if (!next.some((x) => x.path === p)) next.push({ path: p, args: "" });
      });
    }
    setSelectedPaths(next);
    setSelectedPath(next[0]?.path || "");
  };

  const handleTogglePathSelect = (path, extendRange = false) => {
    setManualPathsText(null);
    setPathInputError("");
    const isSelected = selectedPaths.some((x) => x.path === path);
    const visible = extendRange ? getVisiblePaths() : [];
    const anchorIndex = visible.indexOf(selectionAnchorRef.current);
    const targetIndex = visible.indexOf(path);
    selectionAnchorRef.current = path;
    let next;
    if (
      anchorIndex !== -1 &&
      targetIndex !== -1 &&
      anchorIndex !== targetIndex
    ) {
      // Shift+click applies the clicked item's new state to the whole range.
      const range = visible.slice(
        Math.min(anchorIndex, targetIndex),
        Math.max(anchorIndex, targetIndex) + 1,
      );
      if (isSelected) {
        next = selectedPaths.filter((p) => !range.includes(p.path));
      } else {
        // The server rejects a folder together with its contents, so skip a
        // candidate that is inside, or contains, a path already in the queue.
        next = [...selectedPaths];
        range.forEach((candidate) => {
          const overlaps = next.some(
            (p) =>
              p.path === candidate ||
              isInsidePath(candidate, p.path) ||
              isInsidePath(p.path, candidate),
          );
          if (!overlaps) next.push({ path: candidate, args: "" });
        });
      }
    } else {
      next = isSelected
        ? selectedPaths.filter((p) => p.path !== path)
        : [...selectedPaths, { path, args: "" }];
    }
    setSelectedPaths(next);
    setSelectedPath(next[0]?.path || "");
    if (next.length === 1) {
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
  };

  const handleUpdateItemArgs = (path, newArgs) => {
    setSelectedPaths((prev) =>
      prev.map((item) =>
        item.path === path ? { ...item, args: newArgs } : item,
      ),
    );
  };

  const moveQueueItem = (index, delta) => {
    const target = index + delta;
    if (target < 0 || target >= selectedPaths.length) return;
    const next = [...selectedPaths];
    [next[index], next[target]] = [next[target], next[index]];
    // The list now defines the order; regenerate the path text from it.
    setManualPathsText(null);
    setPathInputError("");
    setSelectedPaths(next);
    setSelectedPath(next[0].path);
  };

  const clearQueue = () => {
    setManualPathsText(null);
    setPathInputError("");
    setSelectedPaths([]);
    setSelectedPath("");
    setSelectedName("");
    setExpandedQueueArgs(new Set());
    selectionAnchorRef.current = "";
  };

  const toggleQueueItemArgs = (path) => {
    setExpandedQueueArgs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
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

  const getEffectiveRootFolderOrder = () => {
    const rootPaths = (directories || [])
      .filter((item) => item.type === "folder")
      .sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")))
      .map((item) => item.path);
    const rootPathSet = new Set(rootPaths);
    return [
      ...customFolderOrder.filter((path) => rootPathSet.has(path)),
      ...rootPaths.filter((path) => !customFolderOrder.includes(path)),
    ];
  };

  const moveRootFolder = (path, offset) => {
    const nextOrder = getEffectiveRootFolderOrder();
    const currentIndex = nextOrder.indexOf(path);
    const targetIndex = currentIndex + offset;
    if (
      currentIndex < 0 ||
      targetIndex < 0 ||
      targetIndex >= nextOrder.length
    ) {
      return;
    }
    [nextOrder[currentIndex], nextOrder[targetIndex]] = [
      nextOrder[targetIndex],
      nextOrder[currentIndex],
    ];
    setCustomFolderOrder(nextOrder);
  };

  const placeRootFolder = (sourcePath, targetPath, position) => {
    if (!sourcePath || sourcePath === targetPath) return;
    const nextOrder = getEffectiveRootFolderOrder().filter(
      (path) => path !== sourcePath,
    );
    const targetIndex = nextOrder.indexOf(targetPath);
    if (targetIndex < 0) return;
    const insertionIndex = targetIndex + (position === "after" ? 1 : 0);
    nextOrder.splice(insertionIndex, 0, sourcePath);
    setCustomFolderOrder(nextOrder);
  };

  const getRootFolderDropPosition = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return event.clientY < bounds.top + bounds.height / 2 ? "before" : "after";
  };

  const finishCustomOrderEditing = () => {
    setIsCustomOrderEditing(false);
    setDraggedRootFolderPath("");
    setRootFolderDropTarget(null);
  };

  const sortItems = (items, level = 0) => {
    if (!items) return [];
    const customOrder =
      sortBy === "custom" && level === 0
        ? new Map(
            getEffectiveRootFolderOrder().map((path, index) => [path, index]),
          )
        : null;
    return [...items].sort((a, b) => {
      const aIsDir = a.type === "folder" ? 0 : 1;
      const bIsDir = b.type === "folder" ? 0 : 1;
      if (aIsDir !== bIsDir) return aIsDir - bIsDir;

      if (customOrder && a.type === "folder" && b.type === "folder") {
        return (
          (customOrder.get(a.path) ?? Number.MAX_SAFE_INTEGER) -
          (customOrder.get(b.path) ?? Number.MAX_SAFE_INTEGER)
        );
      }

      let valA, valB;
      if (sortBy === "name" || sortBy === "custom") {
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
              className={`ua-theme-checkbox w-3.5 h-3.5 rounded cursor-pointer ${
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
              onClick={() => {
                setSelectedPaths([]);
                setSelectedPath("");
                setManualPathsText(null);
                setPathInputError("");
              }}
              className="ua-accent-link font-semibold"
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
            aria-label="Sort files and folders"
            value={`${sortBy}-${sortOrder}`}
            onChange={(e) => {
              const [by, order] = e.target.value.split("-");
              setSortBy(by);
              setSortOrder(order);
              if (by !== "custom") finishCustomOrderEditing();
            }}
            className={`min-w-0 flex-1 px-2 py-1 text-xs border rounded ${
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
            <option value="custom-asc">Custom</option>
          </select>
          {sortBy === "custom" && (
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                className="ua-file-order-toggle shrink-0 rounded px-2 py-1 font-semibold"
                onClick={() => {
                  if (isCustomOrderEditing) {
                    finishCustomOrderEditing();
                  } else {
                    setIsCustomOrderEditing(true);
                  }
                }}
                aria-pressed={isCustomOrderEditing}
              >
                {isCustomOrderEditing ? "Done" : "Reorder"}
              </button>
              {isCustomOrderEditing && (
                <button
                  type="button"
                  className="ua-file-order-reset shrink-0 rounded px-2 py-1 font-semibold"
                  onClick={() => setCustomFolderOrder([])}
                  title="Reset root folders to alphabetical order"
                >
                  Reset
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  const handlePathInputChange = (text) => {
    setManualPathsText(text);
    setPathInputError("");
    const parsed = parseUploadPaths(text);
    const parsedPaths = new Set(parsed.map((item) => item.path));
    const previousArgs = new Map(
      selectedPaths.map((item) => [item.path, item.args]),
    );
    const items = parsed.map((item, index) => {
      // A path edited in place keeps the arguments of the line it replaced.
      const replaced = selectedPaths[index];
      const inherited =
        replaced && !parsedPaths.has(replaced.path) ? replaced.args : "";
      return { ...item, args: previousArgs.get(item.path) ?? inherited };
    });
    setSelectedPaths(items);
    setSelectedPath(items[0]?.path || "");
    setSelectedName(items[0]?.path.split(/[/\\]/).pop() || "");
  };

  const renderSelectedPathOrQueue = (isMobileView = false) => {
    const pathText =
      manualPathsText !== null
        ? manualPathsText
        : selectedPaths.length
          ? selectedPaths.map((item) => item.path).join("\n")
          : selectedPath;
    const duplicateLines =
      manualPathsText !== null
        ? manualPathsText.split(/\r?\n/).filter((line) => line.trim()).length -
          selectedPaths.length
        : 0;
    const pathEditor = (
      <div
        className={`p-3 border rounded-lg ${isDarkMode ? "bg-gray-700 border-gray-600" : "bg-blue-50 border-blue-200"}`}
      >
        <label
          htmlFor="upload-paths"
          className={`block text-xs font-semibold mb-1 ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
        >
          Upload paths:
        </label>
        <textarea
          id="upload-paths"
          value={pathText}
          onChange={(event) => handlePathInputChange(event.target.value)}
          rows={Math.min(6, Math.max(2, pathText.split("\n").length))}
          placeholder="Paste a server file or folder path, one per line"
          disabled={isExecuting}
          spellCheck={false}
          aria-invalid={!!pathInputError}
          aria-describedby={
            pathInputError
              ? "upload-paths-help upload-paths-error"
              : "upload-paths-help"
          }
          className={`w-full px-2 py-2 text-sm font-mono border rounded-lg resize-y ${isDarkMode ? "bg-gray-800 border-gray-600 text-white placeholder-gray-400" : "bg-white border-gray-300 text-gray-900"}`}
        />
        <p
          id="upload-paths-help"
          className={`text-xs mt-1 ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
        >
          Enter adds a line. Multiple paths create a queue. Only permitted
          server folders are accepted
          {MAX_UPLOAD_PATHS ? ` (maximum ${MAX_UPLOAD_PATHS} paths)` : ""}.
          {!isMobileView &&
            " Shift+click checkboxes in the file browser to select a range."}
        </p>
        {duplicateLines > 0 && (
          <p
            className={`text-xs mt-1 ${isDarkMode ? "text-yellow-300" : "text-yellow-700"}`}
          >
            {duplicateLines === 1
              ? "1 repeated line is ignored."
              : `${duplicateLines} repeated lines are ignored.`}
          </p>
        )}
        {pathInputError && (
          <p
            id="upload-paths-error"
            role="alert"
            className="text-xs text-red-500 mt-1"
          >
            {pathInputError}
          </p>
        )}
        {isMobileView && (
          <button
            onClick={() => setActivePanel("files")}
            className="ua-accent-link text-xs mt-2"
          >
            Browse files
          </button>
        )}
      </div>
    );
    if (selectedPaths.length > 1) {
      return (
        <>
          {pathEditor}
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
                    <span className="ua-accent-indicator animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"></span>
                  )}
                  <span
                    className={`relative inline-flex rounded-full h-2 w-2 ${isExecuting ? "ua-accent-indicator" : "bg-gray-400"}`}
                  ></span>
                </span>
                Execution Queue ({selectedPaths.length} items)
              </h3>
              <button
                type="button"
                onClick={clearQueue}
                disabled={isExecuting}
                className={`flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold ${isDarkMode ? "text-gray-300 hover:bg-gray-700" : "text-gray-600 hover:bg-gray-100"}`}
                title="Remove every item from the queue"
              >
                <LucideIcon name="trash-2" className="h-3.5 w-3.5" />
                Clear
              </button>
            </div>
            <ol
              ref={queueListRef}
              aria-label="Execution queue"
              className="max-h-80 overflow-y-auto space-y-1 pr-1 text-xs"
            >
              {selectedPaths.map((item, idx) => {
                const separator = Math.max(
                  item.path.lastIndexOf("/"),
                  item.path.lastIndexOf("\\"),
                );
                const name = item.path.slice(separator + 1) || item.path;
                const parent =
                  separator > 0 ? item.path.slice(0, separator) : "";
                // Queued items usually share a long root; show where they differ.
                const parentParts = parent.split(/[/\\]/).filter(Boolean);
                const shortParent =
                  parentParts.length > 2
                    ? `…${item.path[separator]}${parentParts.slice(-2).join(item.path[separator])}`
                    : parent;
                const invalid = !!pathInputError && item.invalid;
                const argsOpen = expandedQueueArgs.has(item.path);
                const argsId = `queue-args-${idx}`;
                const iconButton = `flex h-6 w-6 shrink-0 items-center justify-center rounded disabled:opacity-30 ${isDarkMode ? "text-gray-400 hover:bg-gray-700 hover:text-white" : "text-gray-500 hover:bg-gray-200 hover:text-gray-900"}`;

                return (
                  <li
                    key={item.path}
                    data-queue-invalid={invalid ? "true" : undefined}
                    className={`rounded border px-2 py-1 ${
                      invalid
                        ? "border-red-500 bg-red-500/10"
                        : isDarkMode
                          ? "bg-gray-900 border-gray-800"
                          : "bg-gray-50 border-gray-200"
                    }`}
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span
                        className={`w-7 shrink-0 text-right font-mono tabular-nums ${isDarkMode ? "text-gray-500" : "text-gray-400"}`}
                      >
                        {idx + 1}.
                      </span>
                      <span
                        className="flex min-w-0 flex-1 flex-col"
                        title={item.path}
                      >
                        <span
                          className={`truncate font-semibold ${
                            isDarkMode ? "text-gray-200" : "text-gray-800"
                          }`}
                        >
                          {name}
                        </span>
                        {parent && (
                          <span
                            className={`truncate font-mono text-[10px] ${isDarkMode ? "text-gray-500" : "text-gray-400"}`}
                          >
                            {shortParent}
                          </span>
                        )}
                      </span>
                      {item.args && !argsOpen && (
                        <button
                          type="button"
                          onClick={() => toggleQueueItemArgs(item.path)}
                          disabled={isExecuting}
                          className={`max-w-[40%] truncate rounded px-1.5 py-0.5 font-mono text-[10px] ${isDarkMode ? "bg-gray-700 text-gray-200" : "bg-gray-200 text-gray-700"}`}
                          title={`Line arguments: ${item.args}`}
                        >
                          {item.args}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => toggleQueueItemArgs(item.path)}
                        disabled={isExecuting}
                        className={iconButton}
                        aria-expanded={argsOpen}
                        aria-controls={argsOpen ? argsId : undefined}
                        title={
                          argsOpen
                            ? "Hide line arguments"
                            : "Edit line arguments"
                        }
                      >
                        <LucideIcon
                          name="sliders-horizontal"
                          className="h-3.5 w-3.5"
                        />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveQueueItem(idx, -1)}
                        disabled={isExecuting || idx === 0}
                        className={iconButton}
                        title="Move up"
                      >
                        <LucideIcon name="chevron-up" className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveQueueItem(idx, 1)}
                        disabled={
                          isExecuting || idx === selectedPaths.length - 1
                        }
                        className={iconButton}
                        title="Move down"
                      >
                        <LucideIcon
                          name="chevron-down"
                          className="h-3.5 w-3.5"
                        />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleTogglePathSelect(item.path)}
                        className={`flex h-6 w-6 shrink-0 items-center justify-center rounded text-red-500 hover:text-red-400 disabled:opacity-30 ${isDarkMode ? "hover:bg-gray-700" : "hover:bg-gray-200"}`}
                        title="Remove from queue"
                        disabled={isExecuting}
                      >
                        <LucideIcon name="x" className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    {argsOpen && (
                      <input
                        id={argsId}
                        type="text"
                        value={item.args}
                        onChange={(e) =>
                          handleUpdateItemArgs(item.path, e.target.value)
                        }
                        aria-label={`Line arguments for ${name}`}
                        autoFocus
                        placeholder="e.g. --tmdb audiobook/12345 --anon"
                        className={`mt-1 mb-1 w-full px-2 py-1 font-mono text-xs border rounded-lg ${
                          isDarkMode
                            ? "bg-gray-800 border-gray-700 text-white placeholder-gray-500"
                            : "bg-white border-gray-300 text-gray-900 placeholder-gray-400"
                        }`}
                        disabled={isExecuting}
                      />
                    )}
                  </li>
                );
              })}
            </ol>
          </div>
        </>
      );
    }

    return pathEditor;
  };

  const collapseFileBrowser = () => {
    setExpandedFolders(new Set());
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

  const loadFolderContents = async (path, signal) => {
    if (signal?.aborted) return;
    try {
      const response = await apiFetch(
        `${API_BASE}/browse?path=${encodeURIComponent(path)}`,
        { signal },
      );
      if (signal?.aborted) return;
      const data = await response.json();
      if (signal?.aborted) return;

      if (data.success && data.items) {
        updateDirectoryTree(path, data.items);
      }
    } catch (error) {
      if (!signal?.aborted) console.error("Failed to load folder:", error);
    }
  };

  const updateDirectoryTree = (path, items) => {
    const updateTree = (nodes) => {
      return nodes.map((node) => {
        if (node.path === path) {
          // Keep loaded descendants while refreshing a parent to avoid
          // collapsing the visible tree (and clamping its scroll position).
          const previousChildren = new Map(
            (node.children || []).map((child) => [child.path, child]),
          );
          return {
            ...node,
            children: items.map((item) => {
              const previous = previousChildren.get(item.path);
              return item.type === "folder" && previous?.type === "folder"
                ? { ...item, children: previous.children || item.children }
                : item;
            }),
          };
        } else if (node.children) {
          return { ...node, children: updateTree(node.children) };
        }
        return node;
      });
    };

    setDirectories((prev) => updateTree(prev));
  };

  // File Browser search
  const handleFileBrowserSearch = (value, signal) => {
    if (signal?.aborted) return Promise.resolve();
    fileBrowserSearchCompletion.current?.();
    if (fileBrowserSearchTimer.current) {
      clearTimeout(fileBrowserSearchTimer.current);
    }
    return new Promise((resolve) => {
      const searchId = ++fileBrowserSearchId.current;
      let settled = false;
      const settle = () => {
        if (settled) return;
        settled = true;
        if (fileBrowserSearchCompletion.current === settle) {
          fileBrowserSearchCompletion.current = null;
        }
        resolve();
      };
      fileBrowserSearchCompletion.current = settle;
      setFileBrowserSearch(value);
      const searchQuery = value.trim();
      fileBrowserSearchQuery.current = searchQuery;
      if (!searchQuery) {
        setFileBrowserSearchResults(null);
        setFileBrowserSearchLoading(false);
        settle();
        return;
      }
      setFileBrowserSearchLoading(true);
      const onAbort = () => {
        if (fileBrowserSearchId.current === searchId) {
          clearTimeout(fileBrowserSearchTimer.current);
          setFileBrowserSearchLoading(false);
        }
        signal?.removeEventListener("abort", onAbort);
        settle();
      };
      signal?.addEventListener("abort", onAbort, { once: true });
      fileBrowserSearchTimer.current = setTimeout(async () => {
        if (signal?.aborted) {
          settle();
          return;
        }
        try {
          const response = await apiFetch(
            `${API_BASE}/browse_search?q=${encodeURIComponent(searchQuery)}`,
            { signal },
          );
          if (signal?.aborted) return;
          if (!response.ok) {
            throw new Error(`Search request failed (${response.status})`);
          }
          const data = await response.json();
          if (signal?.aborted) return;
          // Early return if the search has changed since this request
          if (fileBrowserSearchId.current !== searchId) return;
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
          if (signal?.aborted) return;
          console.error("File browser search failed:", error);
          if (fileBrowserSearchId.current === searchId) {
            setFileBrowserSearchResults({
              items: [],
              query: searchQuery,
              count: 0,
            });
          }
        } finally {
          signal?.removeEventListener("abort", onAbort);
          if (!signal?.aborted && fileBrowserSearchId.current === searchId) {
            setFileBrowserSearchLoading(false);
          }
          settle();
        }
      }, 300); //300ms debounce so we dont spam requests for every keystroke
    });
  };

  const refreshFileBrowserAfterUpload = async (signal) => {
    // Give the completed process's filesystem changes time to settle.
    await new Promise((resolve) => setTimeout(resolve, 500));
    if (signal?.aborted) return;
    if (fileBrowserSearchQuery.current) {
      handleFileBrowserSearch(fileBrowserSearchQuery.current, signal);
    }
    for (const path of sortFolderPathsByDepth(expandedFoldersRef.current)) {
      if (signal?.aborted) return;
      if (expandedFoldersRef.current.has(path)) {
        await loadFolderContents(path, signal);
        if (signal?.aborted) return;
      }
    }
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
      const activateSearchResult = () => {
        setManualPathsText(null);
        setPathInputError("");
        if (manualPathsText !== null || selectedPaths.length <= 1)
          setSelectedPaths([]);
        setSelectedPath(item.path);
        setSelectedName(item.name);
        if (isMobile) setActivePanel("main");
      };
      return (
        <div key={item.path || idx}>
          <div
            className={`ua-file-browser-item flex items-center gap-2 px-3 ${isMobile ? "py-3" : "py-2"} cursor-pointer transition-colors`}
            data-selected={selectedPath === item.path ? "true" : "false"}
            style={{ paddingLeft: "12px" }}
            onClick={activateSearchResult}
          >
            <input
              type="checkbox"
              aria-label={`Select ${item.type === "folder" ? "folder" : "file"} ${item.name}`}
              checked={selectedPaths.some((x) => x.path === item.path)}
              onClick={(event) => event.stopPropagation()}
              onChange={(e) => {
                e.stopPropagation();
                handleTogglePathSelect(
                  item.path,
                  e.nativeEvent?.shiftKey === true,
                );
              }}
              className={`ua-theme-checkbox w-4 h-4 rounded cursor-pointer ${
                isDarkMode
                  ? "bg-gray-700 border-gray-600"
                  : "bg-white border-gray-300"
              }`}
            />
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-2 bg-transparent p-0 text-left"
              aria-label={`Use ${item.type === "folder" ? "folder" : "file"} ${item.name}`}
              onClick={(event) => {
                event.stopPropagation();
                activateSearchResult();
              }}
            >
              <span
                className={`flex-shrink-0 ${item.type === "folder" ? "text-yellow-600" : "text-blue-600"}`}
              >
                {item.type === "folder" ? <FolderIcon /> : <FileIcon />}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
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
              </span>
            </button>
          </div>
        </div>
      );
    });
  };

  const renderFileTree = (items, level = 0) => {
    const sorted = sortItems(items, level);
    const rootFolderPaths =
      level === 0
        ? sorted
            .filter((item) => item.type === "folder")
            .map((item) => item.path)
        : [];
    return sorted.map((item, idx) => {
      const isLoading = item.type === "folder" && loadingFolders.has(item.path);
      const isCustomRootFolder =
        sortBy === "custom" &&
        isCustomOrderEditing &&
        level === 0 &&
        item.type === "folder";
      const rootFolderIndex = rootFolderPaths.indexOf(item.path);
      const activateTreeItem = () => {
        setManualPathsText(null);
        setPathInputError("");
        if (manualPathsText !== null || selectedPaths.length <= 1)
          setSelectedPaths([]);
        if (item.type === "folder") {
          toggleFolder(item.path);
        }
        setSelectedPath(item.path);
        setSelectedName(item.name);
        if (isMobile && item.type !== "folder") setActivePanel("main");
      };
      return (
        <div key={item.path || idx}>
          <div
            className={`ua-file-browser-item flex items-center gap-2 px-3 ${isMobile ? "py-3" : "py-2"} cursor-pointer transition-colors`}
            data-selected={selectedPath === item.path ? "true" : "false"}
            data-dragging={
              draggedRootFolderPath === item.path ? "true" : "false"
            }
            data-drag-position={
              rootFolderDropTarget?.path === item.path
                ? rootFolderDropTarget.position
                : undefined
            }
            style={{ paddingLeft: `${level * 20 + 12}px` }}
            onDragOver={
              isCustomRootFolder
                ? (event) => {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = "move";
                    if (draggedRootFolderPath === item.path) {
                      setRootFolderDropTarget(null);
                      return;
                    }
                    const nextTarget = {
                      path: item.path,
                      position: getRootFolderDropPosition(event),
                    };
                    setRootFolderDropTarget((currentTarget) =>
                      currentTarget?.path === nextTarget.path &&
                      currentTarget?.position === nextTarget.position
                        ? currentTarget
                        : nextTarget,
                    );
                  }
                : undefined
            }
            onDragLeave={
              isCustomRootFolder
                ? (event) => {
                    if (!event.currentTarget.contains(event.relatedTarget)) {
                      setRootFolderDropTarget((currentTarget) =>
                        currentTarget?.path === item.path
                          ? null
                          : currentTarget,
                      );
                    }
                  }
                : undefined
            }
            onDrop={
              isCustomRootFolder
                ? (event) => {
                    event.preventDefault();
                    placeRootFolder(
                      draggedRootFolderPath,
                      item.path,
                      getRootFolderDropPosition(event),
                    );
                    setDraggedRootFolderPath("");
                    setRootFolderDropTarget(null);
                  }
                : undefined
            }
            onClick={activateTreeItem}
          >
            <input
              type="checkbox"
              aria-label={`Select ${item.type === "folder" ? "folder" : "file"} ${item.name}`}
              checked={selectedPaths.some((x) => x.path === item.path)}
              onClick={(event) => event.stopPropagation()}
              onChange={(e) => {
                e.stopPropagation();
                handleTogglePathSelect(
                  item.path,
                  e.nativeEvent?.shiftKey === true,
                );
              }}
              className={`ua-theme-checkbox w-4 h-4 rounded cursor-pointer ${
                isDarkMode
                  ? "bg-gray-700 border-gray-600"
                  : "bg-white border-gray-300"
              }`}
            />
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-2 bg-transparent p-0 text-left"
              aria-label={
                item.type === "folder"
                  ? `${expandedFolders.has(item.path) ? "Collapse" : "Expand"} folder ${item.name}`
                  : `Use file ${item.name}`
              }
              aria-expanded={
                item.type === "folder"
                  ? expandedFolders.has(item.path)
                  : undefined
              }
              onClick={(event) => {
                event.stopPropagation();
                activateTreeItem();
              }}
            >
              <span
                className={`flex-shrink-0 ${isLoading ? "ua-accent-text" : "text-yellow-600"}`}
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
              <span className="flex min-w-0 flex-1 flex-col">
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
              </span>
            </button>
            {isCustomRootFolder && (
              <div
                className="ua-file-order-controls ml-auto flex shrink-0 items-center gap-1"
                onClick={(event) => event.stopPropagation()}
              >
                <span
                  className="ua-file-order-handle rounded"
                  draggable={true}
                  title="Drag to reorder"
                  onDragStart={(event) => {
                    const row = event.currentTarget.closest(
                      ".ua-file-browser-item",
                    );
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", item.path);
                    if (row) {
                      event.dataTransfer.setDragImage(
                        row,
                        18,
                        Math.round(row.getBoundingClientRect().height / 2),
                      );
                    }
                    setDraggedRootFolderPath(item.path);
                    setRootFolderDropTarget(null);
                  }}
                  onDragEnd={() => {
                    setDraggedRootFolderPath("");
                    setRootFolderDropTarget(null);
                  }}
                >
                  <LucideIcon name="grip-vertical" className="h-4 w-4" />
                </span>
                <button
                  type="button"
                  className="ua-file-order-control rounded px-1.5 py-1"
                  disabled={rootFolderIndex <= 0}
                  aria-label={`Move ${item.name} up`}
                  title="Move up"
                  onClick={() => moveRootFolder(item.path, -1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="ua-file-order-control rounded px-1.5 py-1"
                  disabled={rootFolderIndex >= rootFolderPaths.length - 1}
                  aria-label={`Move ${item.name} down`}
                  title="Move down"
                  onClick={() => moveRootFolder(item.path, 1)}
                >
                  ↓
                </button>
              </div>
            )}
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
          <button
            type="button"
            className={`flex w-full items-center gap-2 px-3 text-left ${isMobile ? "py-3" : "py-2"} cursor-pointer transition-colors ${
              descFilePath === item.path
                ? isDarkMode
                  ? "bg-green-900 border-l-4 border-green-500"
                  : "bg-green-100 border-l-4 border-green-500"
                : isDarkMode
                  ? "hover:bg-gray-700"
                  : "hover:bg-gray-100"
            }`}
            style={{ paddingLeft: `${level * 20 + 12}px` }}
            aria-label={
              item.type === "folder"
                ? `${descExpandedFolders.has(item.path) ? "Collapse" : "Expand"} folder ${item.name}`
                : `Use description file ${item.name}`
            }
            aria-expanded={
              item.type === "folder"
                ? descExpandedFolders.has(item.path)
                : undefined
            }
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
            <span className="flex min-w-0 flex-col">
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
            </span>
          </button>
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

  /** Show the server's label (e.g. "Title (2024)") and full release name for a tab. */
  const setUploadTabTitle = (tabId, title, detail = "") => {
    if (!title) return;
    setUploadTabs((tabs) =>
      tabs.map((tab) =>
        tab.id === tabId
          ? { ...tab, title: String(title), detail: String(detail || "") }
          : tab,
      ),
    );
  };

  /** Wait without blocking an abort of the tab's session. */
  const waitForReconnect = (milliseconds, signal) =>
    new Promise((resolve) => {
      // An already-aborted signal never fires "abort" again.
      if (signal.aborted) {
        resolve();
        return;
      }
      const timer = setTimeout(resolve, milliseconds);
      signal.addEventListener(
        "abort",
        () => {
          clearTimeout(timer);
          resolve();
        },
        { once: true },
      );
    });

  /** Read one chunk, giving up on a connection that stopped sending keepalives. */
  const readSessionChunk = (reader) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reader.cancel().catch(() => {});
        reject(new Error("Session stream stalled"));
      }, SESSION_STREAM_STALL_MS);
      reader.read().then(
        (chunk) => {
          clearTimeout(timer);
          resolve(chunk);
        },
        (error) => {
          clearTimeout(timer);
          reject(error);
        },
      );
    });

  /**
   * Apply one SSE response to a tab. Events before "replay_done" are history
   * from the server's session log, so they do not replay prompt sounds.
   */
  const readSessionStream = async (tabId, response, controller) => {
    const outcome = {
      exitCode: null,
      finished: false,
      error: false,
      started: false,
    };
    const runtime = getTabRuntime(tabId);
    if (!runtime) return outcome;
    let live = false;

    const handleEvent = (data) => {
      if (Number.isInteger(data.seq)) {
        // Reconnects replay from the last sequence number; skip any overlap.
        if (data.seq <= runtime.lastSeq) return;
        runtime.lastSeq = data.seq;
        outcome.started = true;
      }
      if (data.type === "html" || data.type === "html_full") {
        try {
          const clean = sanitizeHtml(data.data || "");
          if (data.type === "html_full") {
            const key = `${clean.length}:${clean.slice(0, 200)}`;
            if (runtime.lastFullHash !== key) {
              runtime.lastFullHash = key;
              runtime.output.appendChild(createUploadOutputFragment(clean));
              scrollTabOutput(tabId);
            }
            return;
          }
          appendHtmlFragment(clean, tabId);
        } catch (e) {
          console.error("Failed to render HTML fragment:", e);
        }
      } else if (data.type === "progress") {
        applyProgressEvent(data.data || {}, tabId);
      } else if (data.type === "gui") {
        applyRunGuiEvent(data, tabId);
      } else if (data.type === "prompt_sound") {
        if (live) window.uaPromptSound?.play();
      } else if (data.type === "prompt_state") {
        runtime.awaiting = Boolean(data.awaiting);
        applyRunGuiEvent(data, tabId);
        refreshUploadTabStatus(tabId);
      } else if (data.type === "replay_done") {
        live = true;
        outcome.started = true;
      } else if (data.type === "label") {
        setUploadTabTitle(tabId, data.label, data.detail);
      } else if (data.type === "truncated") {
        appendSystemMessage(
          "Earlier output was trimmed on the server.",
          "info",
          tabId,
        );
      } else if (data.type === "error") {
        outcome.error = true;
        appendSystemMessage(`Error: ${data.data}`, "error", tabId);
      } else if (data.type === "exit") {
        applyRunGuiEvent(data, tabId);
        appendSystemMessage("", "info", tabId);
        appendSystemMessage(
          `Success: Process exited with code ${data.code}`,
          "info",
          tabId,
        );
        outcome.exitCode = data.code;
      } else if (data.type === "scheduled") {
        outcome.scheduled = true;
      } else if (data.type === "started") {
        appendSystemMessage("Scheduled upload started.", "info", tabId);
      } else if (data.type === "finished") {
        applyRunGuiEvent(data, tabId);
        outcome.finished = true;
        if (outcome.exitCode === null && Number.isInteger(data.exit_code)) {
          outcome.exitCode = data.exit_code;
        }
      }
    };

    const processSSELine = (line) => {
      if (controller.signal.aborted) return;
      if (!line.trim() || !line.startsWith("data: ")) return;
      try {
        handleEvent(JSON.parse(line.substring(6)));
      } catch (e) {
        console.error("Parse error:", e);
      }
    };

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    /* eslint-disable no-constant-condition */
    while (true) {
      const { done, value } = await readSessionChunk(reader);
      if (done) {
        if (buffer) buffer.split("\n").forEach(processSSELine);
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n");
      buffer = parts.pop();
      parts.forEach(processSSELine);
      if (outcome.finished) {
        // Release the connection now instead of waiting for garbage collection.
        Promise.resolve(reader.cancel?.()).catch(() => {});
        break;
      }
    }
    /* eslint-enable no-constant-condition */
    return outcome;
  };

  /**
   * Follow a tab's session until the upload ends. A dropped connection only
   * detaches the browser; the server keeps the upload running, so reconnect
   * and replay whatever was missed.
   */
  const followSession = async (tabId, controller, firstResponse = null) => {
    const { signal } = controller;
    const result = { exitCode: null, error: false, lost: false };
    let response = firstResponse;
    let failures = 0;
    for (;;) {
      const runtime = getTabRuntime(tabId);
      if (signal.aborted || !runtime) return { ...result, aborted: true };
      if (response) {
        let outcome = null;
        try {
          outcome = await readSessionStream(tabId, response, controller);
        } catch (error) {
          if (signal.aborted) return { ...result, aborted: true };
        }
        if (signal.aborted) return { ...result, aborted: true };
        if (outcome) {
          if (outcome.exitCode !== null) result.exitCode = outcome.exitCode;
          if (outcome.error) result.error = true;
          if (outcome.scheduled) return { ...result, scheduled: true };
          if (outcome.finished || outcome.exitCode !== null) return result;
          // Rejected before a session existed (limit, duplicate content, ...).
          if (!outcome.started && outcome.error) return result;
          if (outcome.started) failures = 0;
        }
      }

      if (response || failures > 0) {
        failures += 1;
        if (failures > SESSION_RECONNECT_ATTEMPTS) {
          result.lost = true;
          appendSystemMessage(
            "Error: Lost the connection to this upload. It keeps running on the server; reload the page to reattach.",
            "error",
            tabId,
          );
          return result;
        }
        if (failures === 1) {
          appendSystemMessage(
            "Connection lost; reconnecting to the upload...",
            "info",
            tabId,
          );
        }
        await waitForReconnect(Math.min(10000, 1000 * failures), signal);
        if (signal.aborted) return { ...result, aborted: true };
      } else {
        failures = 1;
      }

      response = null;
      try {
        const candidate = await apiFetch(
          `${API_BASE}/session_stream?session_id=${encodeURIComponent(runtime.run.sessionId)}&after=${runtime.lastSeq}`,
          { cache: "no-store", signal },
        );
        if (candidate.status === 404) {
          result.lost = true;
          appendSystemMessage(
            "Error: This upload is no longer available on the server.",
            "error",
            tabId,
          );
          return result;
        }
        if (candidate.ok && candidate.body) response = candidate;
      } catch (error) {
        if (signal.aborted) return { ...result, aborted: true };
      }
    }
  };

  /** Fetch the session list at most once per poll interval, shared by all tabs. */
  const pollSessionsShared = () => {
    if (
      sharedSessionsPoll.promise &&
      Date.now() - sharedSessionsPoll.at < SCHEDULE_POLL_MS / 2
    ) {
      return sharedSessionsPoll.promise;
    }
    sharedSessionsPoll.at = Date.now();
    sharedSessionsPoll.promise = apiFetch(`${API_BASE}/sessions`, {
      cache: "no-store",
    })
      .then((response) => (response.ok ? response.json() : null))
      .catch(() => null);
    return sharedSessionsPoll.promise;
  };

  /**
   * Poll the session list until a scheduled upload starts ("started"), is
   * cancelled elsewhere ("gone"), or this tab stops waiting ("aborted").
   */
  const waitForScheduledStart = async (tabId, controller) => {
    const { signal } = controller;
    const runtime = getTabRuntime(tabId);
    if (!runtime) return "aborted";
    runtime.scheduled = true;
    refreshUploadTabStatus(tabId);
    try {
      for (;;) {
        await waitForReconnect(SCHEDULE_POLL_MS, signal);
        if (signal.aborted || !getTabRuntime(tabId)) return "aborted";
        const data = await pollSessionsShared();
        if (signal.aborted) return "aborted";
        if (!data || !Array.isArray(data.sessions)) continue;
        const session = data.sessions.find(
          (item) => item.session_id === runtime.run.sessionId,
        );
        if (!session) return "gone";
        if (!session.scheduled) return "started";
      }
    } finally {
      runtime.scheduled = false;
      refreshUploadTabStatus(tabId);
    }
  };

  /** Follow a session through an optional scheduled wait until it ends. */
  const followScheduledSession = async (tabId, controller, result) => {
    if (!result.scheduled) return result;
    appendSystemMessage(
      "All upload slots are busy. This upload is scheduled and starts automatically when one frees, even if you close the page.",
      "info",
      tabId,
    );
    const state = await waitForScheduledStart(tabId, controller);
    if (state === "aborted") return { ...result, aborted: true };
    if (state === "gone") {
      appendSystemMessage("Scheduled upload was cancelled.", "error", tabId);
      return { exitCode: null, error: true, lost: false };
    }
    return followSession(tabId, controller);
  };

  const finishTabSession = async (
    tabId,
    controller,
    result,
    { refreshFiles = false } = {},
  ) => {
    const runtime = getTabRuntime(tabId);
    if (!runtime || result.aborted || controller.signal.aborted) return false;
    if (!result.lost && (result.exitCode !== null || !result.error)) {
      appendSystemMessage("Success: Execution completed", "info", tabId);
    }
    appendSystemMessage("", "info", tabId);
    if (refreshFiles && result.exitCode === 0) {
      await refreshFileBrowserAfterUpload(controller.signal);
    }
    const succeeded =
      !result.lost &&
      (result.exitCode === 0 || (result.exitCode === null && !result.error));
    runtime.result = succeeded ? "done" : "error";
    return succeeded;
  };

  /** Forget this tab's finished server session so it is not restored again. */
  const dismissTabSession = (tabId) => {
    const runtime = getTabRuntime(tabId);
    const sessionId = runtime?.sessionRecord;
    if (!sessionId || runtime.run.isExecuting) return;
    runtime.sessionRecord = "";
    apiFetch(`${API_BASE}/session_dismiss`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    }).catch((error) => console.error("Failed to dismiss session:", error));
  };

  const executeSinglePath = async (
    path,
    newSessionId,
    itemArgs = "",
    tabId = activeTabIdRef.current,
    label = "",
  ) => {
    const executionArgs = [customArgs, itemArgs].filter(Boolean).join(" ");
    const reportError = (message) => {
      appendSystemMessage(message, "error", tabId);
      return false;
    };
    // Validate --descfile: must have a valid description file path
    if (hasDescFile) {
      if (!descFilePath) {
        return reportError(
          "Error: Please select or enter a description file path when using --descfile",
        );
      }
      const pathValidation = isValidDescFilePath(descFilePath);
      if (!pathValidation.valid) {
        return reportError(
          `Error: Invalid description file: ${pathValidation.error}`,
        );
      }
    }

    // Validate --desclink: must have a valid URL
    if (hasDescLink) {
      if (!descLinkUrl) {
        return reportError(
          "Error: Please enter a description URL when using --desclink",
        );
      }
      if (!isValidUrl(descLinkUrl)) {
        return reportError(
          "Error: Please enter a valid paste URL for --desclink (pastebin, hastebin, etc.)",
        );
      }
    }

    const runtime = getTabRuntime(tabId);
    // The tab was closed while its queue was being prepared.
    if (!runtime) return false;
    dismissTabSession(tabId);
    runtime.lastFullHash = "";
    runtime.lastSeq = 0;
    runtime.awaiting = false;
    runtime.waiting.clear();
    runtime.result = "";
    runtime.sessionRecord = newSessionId;
    updateTabRun(tabId, { sessionId: newSessionId, progressItems: [] });

    appendSystemMessage("", "info", tabId);
    appendSystemMessage(
      `$ python upload.py "${path}" ${executionArgs}`,
      "info",
      tabId,
    );
    appendSystemMessage("Starting execution...", "info", tabId);

    const controller = new AbortController();
    runtime.controller = controller;

    try {
      const response = await apiFetch(`${API_BASE}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: path,
          args: executionArgs,
          session_id: newSessionId,
          label,
          // The server starts it now, or schedules it if every slot is busy.
          schedule: schedulingEnabled,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errText = await response.text();
        runtime.result = "error";
        return reportError(
          `Error: Execute failed (${response.status}): ${errText || "Request failed"}`,
        );
      }
      if (!response.body) {
        runtime.result = "error";
        return reportError("Error: Execute failed: empty response body");
      }
      const result = await followScheduledSession(
        tabId,
        controller,
        await followSession(tabId, controller, response),
      );
      return await finishTabSession(tabId, controller, result, {
        refreshFiles: true,
      });
    } catch (error) {
      if (!controller.signal.aborted) {
        runtime.result = "error";
        appendSystemMessage(
          "Error: Execution failed: " + error.message,
          "error",
          tabId,
        );
      }
      return false;
    } finally {
      runtime.awaiting = false;
      runtime.waiting.clear();
      if (runtime.controller === controller) runtime.controller = null;
      updateTabRun(tabId, { progressItems: [] });
    }
  };

  /** Show a server session in a tab and follow it until it ends. */
  const attachRestoredSession = async (tabId) => {
    const runtime = getTabRuntime(tabId);
    if (!runtime) return;
    const controller = new AbortController();
    runtime.controller = controller;
    try {
      const result = runtime.scheduled
        ? await followScheduledSession(tabId, controller, { scheduled: true })
        : await followSession(tabId, controller);
      await finishTabSession(tabId, controller, result);
    } finally {
      runtime.awaiting = false;
      runtime.waiting.clear();
      if (runtime.controller === controller) runtime.controller = null;
      updateTabRun(tabId, {
        isExecuting: false,
        sessionId: "",
        progressItems: [],
      });
    }
  };

  /**
   * Recreate tabs for uploads still known to the server, plus forms this
   * browser had prepared, so closing or reloading the page loses neither.
   */
  const restoreUploadSessions = async () => {
    let sessions = [];
    try {
      const response = await apiFetch(`${API_BASE}/sessions`, {
        cache: "no-store",
      });
      const data = await response.json();
      if (response.ok && Array.isArray(data.sessions)) sessions = data.sessions;
      if (Number.isInteger(data.max_running) && data.max_running > 0) {
        setMaxRunningUploads(data.max_running);
      }
      if (typeof data.scheduling === "boolean") {
        setSchedulingEnabled(data.scheduling);
      }
    } catch (error) {
      console.error("Failed to load upload sessions:", error);
    }
    const drafts = loadUploadTabDrafts();

    const firstTab = getTabRuntime("tab-1");
    const replaceFirstTab =
      firstTab &&
      !firstTab.run.isExecuting &&
      !firstTab.sessionRecord &&
      !uploadTabFormHasContent({
        selectedPath,
        selectedPaths,
        manualPathsText,
        customArgs,
      });
    const room = MAX_UPLOAD_TABS - (replaceFirstTab ? 0 : 1);
    const newTab = (runtime, title = "", detail = "") => {
      uploadTabCounterRef.current += 1;
      const number = uploadTabCounterRef.current;
      const id = `tab-${number}`;
      tabRuntimeRef.current.set(id, runtime);
      return { id, number, title, detail, status: getUploadTabStatus(runtime) };
    };
    const restoredSessions = sessions.slice(0, room).map((session) => {
      const runtime = createUploadTabRuntime();
      runtime.run = {
        sessionId: String(session.session_id),
        isExecuting: Boolean(session.running),
      };
      runtime.sessionRecord = String(session.session_id);
      runtime.scheduled = Boolean(session.scheduled);
      runtime.awaiting = Boolean(session.awaiting_input);
      if (!session.running)
        runtime.result = session.exit_code === 0 ? "done" : "error";
      return newTab(
        runtime,
        String(session.label || ""),
        String(session.label_detail || ""),
      );
    });
    const restoredDrafts = drafts
      .slice(0, room - restoredSessions.length)
      .map((draft) => {
        const runtime = createUploadTabRuntime();
        runtime.view.form = { ...createUploadTabForm(), ...draft.form };
        return newTab(runtime);
      });
    const restored = [...restoredSessions, ...restoredDrafts];

    if (restored.length && replaceFirstTab) {
      switchUploadTab(restored[0].id);
      tabRuntimeRef.current.delete("tab-1");
      setUploadTabs(restored);
    } else if (restored.length) {
      setUploadTabs((tabs) => [...tabs, ...restored]);
    }
    // Run state must reach React for the visible tab; background tabs keep it in their runtime.
    const visible = getTabRuntime(activeTabIdRef.current);
    if (visible) {
      setSessionId(visible.run.sessionId);
      setIsExecuting(visible.run.isExecuting);
    }
    restoredSessions.forEach((tab) => attachRestoredSession(tab.id));
    setUploadTabsRestored(true);
  };

  useEffect(() => {
    if (screenshotMode) return;
    restoreUploadSessions();
  }, []);

  useEffect(() => {
    if (screenshotMode || !uploadTabsRestored) return;
    const drafts = [];
    uploadTabs.forEach((tab) => {
      const runtime = getTabRuntime(tab.id);
      // Running and finished tabs are restored from the server instead.
      if (!runtime || runtime.run.isExecuting || runtime.sessionRecord) return;
      const form =
        tab.id === activeTabId
          ? { selectedPath, selectedPaths, manualPathsText, customArgs }
          : runtime.view.form;
      if (!uploadTabFormHasContent(form)) return;
      drafts.push({
        form: {
          selectedPath: form.selectedPath || "",
          selectedPaths: form.selectedPaths || [],
          manualPathsText: form.manualPathsText ?? null,
          customArgs: form.customArgs || "",
        },
      });
    });
    saveUploadTabDrafts(drafts);
  }, [
    uploadTabsRestored,
    uploadTabs,
    activeTabId,
    selectedPath,
    selectedPaths,
    manualPathsText,
    customArgs,
  ]);

  /** Show a path error; `itemNumber` (1-based) marks the queue item it names. */
  const reportTabPathError = (tabId, message, itemNumber = 0) => {
    const markInvalid = (paths) =>
      paths.map((item, index) => ({
        ...item,
        invalid: index === itemNumber - 1,
      }));
    // Nothing ran; return to the form where the error is shown.
    if (tabId === activeTabIdRef.current) {
      setPathInputError(message);
      setSelectedPaths(markInvalid);
      setIsTerminalView(false);
      return;
    }
    const runtime = getTabRuntime(tabId);
    if (runtime) {
      runtime.view.isTerminalView = false;
      runtime.view.form.pathInputError = message;
      runtime.view.form.selectedPaths = markInvalid(
        runtime.view.form.selectedPaths,
      );
    }
  };

  useEffect(() => {
    if (!pathInputError) return;
    queueListRef.current
      ?.querySelector('[data-queue-invalid="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [pathInputError]);

  const executeCommand = async () => {
    if (screenshotMode) return;
    window.uaPromptSound?.unlock();
    if (isExecuting) return;
    const tabId = activeTabIdRef.current;
    const previousArgs = new Map(
      selectedPaths.map((item) => [item.path, item.args]),
    );
    const items =
      manualPathsText !== null
        ? parseUploadPaths(manualPathsText).map((item) => ({
            ...item,
            args: previousArgs.get(item.path) || "",
          }))
        : selectedPaths.length
          ? selectedPaths
          : selectedPath
            ? [{ path: selectedPath, args: "" }]
            : [];
    if (
      !items.length ||
      (MAX_UPLOAD_PATHS && items.length > MAX_UPLOAD_PATHS)
    ) {
      const error = items.length
        ? `Maximum ${MAX_UPLOAD_PATHS} paths per upload`
        : "Enter or select a file or folder first";
      setPathInputError(error);
      return;
    }
    setPathInputError("");
    updateTabRun(tabId, { isExecuting: true });
    setUploadTabs((tabs) =>
      tabs.map((tab) =>
        tab.id === tabId
          ? { ...tab, title: getUploadTabTitle(items), detail: "" }
          : tab,
      ),
    );
    try {
      const response = await apiFetch(`${API_BASE}/save_queue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items, return_single_path: items.length === 1 }),
      });
      const data = await response.json();
      if (!response.ok || !data.success || !data.path) {
        const line = items[data.item - 1]?.line;
        const error = `${line ? `Line ${line}: ` : ""}${data.error || "Could not validate upload paths"}`;
        reportTabPathError(tabId, error, Number(data.item) || 0);
        return;
      }
      const runtime = getTabRuntime(tabId);
      if (!runtime) return;
      runtime.output.replaceChildren();
      resetRunGui(tabId);
      await executeSinglePath(
        data.path,
        `session_${tabId}_${Date.now()}`,
        items.length === 1 ? items[0].args : "",
        tabId,
        getUploadTabTitle(items),
      );
    } catch (error) {
      reportTabPathError(tabId, `Could not prepare upload: ${error.message}`);
    } finally {
      updateTabRun(tabId, { isExecuting: false, sessionId: "" });
    }
  };

  const clearTerminal = async () => {
    if (screenshotMode) return;
    const tabId = activeTabIdRef.current;
    const runtime = getTabRuntime(tabId);
    if (!runtime) return;
    // If a process is running, kill it first
    if (isExecuting && sessionId) {
      try {
        // Abort the SSE fetch so the client stops processing incoming events
        try {
          runtime.controller?.abort();
        } catch (e) {
          /* ignore */
        }
        await apiFetch(`${API_BASE}/kill`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }),
        });

        appendSystemMessage(
          "Error: Process terminated by user",
          "error",
          tabId,
        );

        runtime.result = "";
        updateTabRun(tabId, {
          isExecuting: false,
          sessionId: "",
          progressItems: [],
        });
      } catch (error) {
        console.error("Failed to kill process:", error);
      }
    }

    dismissTabSession(tabId);

    // Clear this tab's output
    runtime.output.replaceChildren();
    resetRunGui(tabId);
    updateTabRun(tabId, { progressItems: [] });
    appendWelcomeMessage(tabId);
  };

  /** Show another tab: park the current view state and restore the target's. */
  const switchUploadTab = (nextId) => {
    if (screenshotMode) return;
    const currentId = activeTabIdRef.current;
    const next = getTabRuntime(nextId);
    if (nextId === currentId || !next) return;
    const current = getTabRuntime(currentId);
    if (current) {
      current.view = {
        isTerminalView,
        progressItems,
        form: {
          selectedPath,
          selectedPaths,
          manualPathsText,
          customArgs,
          pathInputError,
          selectedArgumentPreset,
          userInput,
        },
      };
    }
    activeTabIdRef.current = nextId;
    const { form } = next.view;
    setSessionId(next.run.sessionId);
    setIsExecuting(next.run.isExecuting);
    setIsTerminalView(next.view.isTerminalView);
    setProgressItems(next.view.progressItems);
    setRunGui(next.gui);
    setSelectedPath(form.selectedPath);
    setSelectedPaths(form.selectedPaths);
    setManualPathsText(form.manualPathsText);
    setCustomArgs(form.customArgs);
    setPathInputError(form.pathInputError);
    setSelectedArgumentPreset(form.selectedArgumentPreset);
    setUserInput(form.userInput);
    setActiveTabId(nextId);
  };

  /** Create an empty tab's runtime; the caller adds it to the tab bar. */
  const createEmptyUploadTab = (number = null) => {
    uploadTabCounterRef.current += 1;
    const id = `tab-${uploadTabCounterRef.current}`;
    tabRuntimeRef.current.set(id, createUploadTabRuntime());
    appendWelcomeMessage(id);
    return {
      id,
      number: number ?? uploadTabCounterRef.current,
      title: "",
      status: "idle",
    };
  };

  const addUploadTab = () => {
    if (screenshotMode || uploadTabs.length >= MAX_UPLOAD_TABS) return;
    const tab = createEmptyUploadTab();
    setUploadTabs((tabs) => [...tabs, tab]);
    switchUploadTab(tab.id);
  };

  const closeUploadTab = async (tabId) => {
    setPendingCloseTabId("");
    const runtime = getTabRuntime(tabId);
    const index = uploadTabs.findIndex((tab) => tab.id === tabId);
    if (!runtime || index === -1) return;
    if (!runtime.run.isExecuting) dismissTabSession(tabId);
    if (uploadTabs.length <= 1) {
      // The bar always keeps one tab, so "closing" the last one resets it.
      const replacement = createEmptyUploadTab(uploadTabs[index].number);
      switchUploadTab(replacement.id);
      tabRuntimeRef.current.delete(tabId);
      setUploadTabs([replacement]);
    } else {
      if (tabId === activeTabIdRef.current) {
        const neighbor = uploadTabs[index + 1] || uploadTabs[index - 1];
        switchUploadTab(neighbor.id);
      }
      tabRuntimeRef.current.delete(tabId);
      setUploadTabs((tabs) => tabs.filter((tab) => tab.id !== tabId));
    }
    if (!runtime.run.isExecuting) return;
    try {
      runtime.controller?.abort();
    } catch (e) {
      /* ignore */
    }
    if (!runtime.run.sessionId) return;
    try {
      await apiFetch(`${API_BASE}/kill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: runtime.run.sessionId }),
      });
    } catch (error) {
      console.error("Failed to kill closed tab process:", error);
    }
  };

  const requestCloseUploadTab = (tabId) => {
    if (screenshotMode) return;
    if (getTabRuntime(tabId)?.run.isExecuting) {
      setPendingCloseTabId(tabId);
      return;
    }
    closeUploadTab(tabId);
  };

  const getUploadTabLabel = (tab) => tab.title || `Upload ${tab.number}`;

  const busyUploadCount = uploadTabs.filter((tab) =>
    BUSY_UPLOAD_STATUSES.includes(tab.status),
  ).length;
  const uploadSlotsFull = busyUploadCount >= maxRunningUploads;
  const activeTabScheduled =
    uploadTabs.find((tab) => tab.id === activeTabId)?.status === "scheduled";
  const executeDisabled =
    (!selectedPath && selectedPaths.length === 0) ||
    isExecuting ||
    (uploadSlotsFull && !schedulingEnabled);
  const executeButtonTitle = uploadSlotsFull
    ? schedulingEnabled
      ? `All ${maxRunningUploads} upload slots are busy; this upload starts automatically when one frees.`
      : `All ${maxRunningUploads} upload slots are busy; wait for an upload to finish.`
    : undefined;
  const getExecuteButtonLabel = () => {
    if (isExecuting) return activeTabScheduled ? "Scheduled" : "Executing...";
    const noun =
      selectedPaths.length > 1 ? `Queue (${selectedPaths.length})` : "Upload";
    if (!uploadSlotsFull) return `Execute ${noun}`;
    return schedulingEnabled ? `Schedule ${noun}` : "All upload slots busy";
  };
  const killButtonLabel = activeTabScheduled ? "Cancel" : "Kill";

  const renderCloseUploadTabDialog = () => {
    const tab = uploadTabs.find((item) => item.id === pendingCloseTabId);
    if (!tab) return null;
    const isLastTab = uploadTabs.length <= 1;
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ua-close-tab-title"
        onClick={() => setPendingCloseTabId("")}
      >
        <div
          className="ua-upload-tab-dialog w-full max-w-sm rounded-lg border p-5 shadow-xl"
          onClick={(event) => event.stopPropagation()}
        >
          <h2 id="ua-close-tab-title" className="text-base font-semibold">
            Stop this upload?
          </h2>
          <p className="ua-upload-tab-dialog-text mt-2 text-sm">
            &ldquo;{getUploadTabLabel(tab)}&rdquo; is still running.{" "}
            {isLastTab
              ? "Resetting the tab kills its process."
              : "Closing the tab kills its process."}
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <button
              onClick={() => setPendingCloseTabId("")}
              className="ua-upload-tab-dialog-cancel rounded-md px-3 py-1.5 text-sm"
              data-ua-modal-initial-focus
            >
              Keep running
            </button>
            <button
              onClick={() => closeUploadTab(tab.id)}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700"
            >
              {isLastTab ? "Kill and reset" : "Kill and close"}
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderUploadTabs = () => {
    const canAddTab = uploadTabs.length < MAX_UPLOAD_TABS;
    return (
      <>
        <div className="ua-upload-tabs" role="tablist" aria-label="Uploads">
          {uploadTabs.map((tab) => {
            const isActive = tab.id === activeTabId;
            const label = getUploadTabLabel(tab);
            const statusLabel = UPLOAD_TAB_STATUS_LABELS[tab.status] || "";
            return (
              <div
                key={tab.id}
                className="ua-upload-tab"
                data-active={isActive ? "true" : "false"}
              >
                <button
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => switchUploadTab(tab.id)}
                  className="ua-upload-tab-button"
                  title={[label, tab.detail, statusLabel]
                    .filter(Boolean)
                    .join("\n")}
                >
                  <span
                    className="ua-upload-tab-dot"
                    data-status={tab.status}
                    role="img"
                    aria-label={statusLabel}
                  />
                  <span className="ua-upload-tab-label">{label}</span>
                </button>
                <button
                  onClick={() => requestCloseUploadTab(tab.id)}
                  className="ua-upload-tab-close"
                  aria-label={
                    uploadTabs.length > 1 ? `Close ${label}` : `Reset ${label}`
                  }
                  title={
                    uploadTabs.length > 1
                      ? "Close tab"
                      : "Reset tab (kills a running upload)"
                  }
                >
                  <LucideIcon name="x" className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
          <button
            onClick={addUploadTab}
            disabled={!canAddTab}
            className="ua-upload-tab-add"
            aria-label="New upload tab"
            title={
              canAddTab
                ? "New upload tab"
                : `Up to ${MAX_UPLOAD_TABS} upload tabs`
            }
          >
            <LucideIcon name="plus" className="h-4 w-4" />
          </button>
        </div>
        {renderCloseUploadTabDialog()}
      </>
    );
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
      const requestedWidth = e.clientX - APPLICATION_RAIL_WIDTH;
      const newWidth = snapToDevicePixels(
        Math.min(
          LEFT_SIDEBAR_MAX_WIDTH,
          Math.max(DEFAULT_LEFT_SIDEBAR_WIDTH, requestedWidth),
        ),
      );
      setSidebarWidth(newWidth);
      storage.set(LEFT_SIDEBAR_WIDTH_KEY, String(newWidth));
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
      const requestedWidth = window.innerWidth - e.clientX;
      const newWidth = snapToDevicePixels(
        Math.min(
          RIGHT_SIDEBAR_MAX_WIDTH,
          Math.max(DEFAULT_RIGHT_SIDEBAR_WIDTH, requestedWidth),
        ),
      );
      setRightSidebarWidth(newWidth);
      storage.set(RIGHT_SIDEBAR_WIDTH_KEY, String(newWidth));
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
          className={`min-w-0 flex-1 px-3 py-2 text-sm border rounded-lg ${
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
          aria-label="Preset name"
          value={argumentPresetName}
          onChange={(e) => setArgumentPresetName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              saveArgumentPreset();
            }
          }}
          placeholder="Preset name"
          className={`min-w-0 flex-1 px-3 py-2 text-sm border rounded-lg ${
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
          className="ua-accent-action px-3 py-2 text-sm font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
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
  const toggleSectionCollapse = (id) => {
    setCollapsedSections((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  // The Arguments panel reads and edits customArgs in place, so the text
  // field, presets and queue lines stay the single source of the command.
  const parsedArguments = argumentBuilder.parseArguments(
    customArgs,
    argumentIndex,
  );
  const argumentIssues = argumentBuilder.findArgumentIssues(
    customArgs,
    argumentIndex,
  );
  const categoryKey = argumentBuilder.keyForOption(argumentIndex, "--category");
  const commandCategoryView = categoryKey
    ? ARGUMENT_VIEW_FOR_CATEGORY[
        argumentBuilder
          .getArgumentState(parsedArguments, categoryKey)
          .value.toLowerCase()
      ] || ""
    : "";
  // A --category in the command picks its view; a manual choice holds
  // until the category changes.
  useEffect(() => {
    if (commandCategoryView) setArgumentView(commandCategoryView);
  }, [commandCategoryView]);

  const occurrencesOf = (text, key) =>
    argumentBuilder
      .parseArguments(text, argumentIndex)
      .occurrences.filter((occurrence) => occurrence.key === key);

  // nth targets one occurrence in the "In command" list; rows otherwise
  // edit the first occurrence of their option (and prefix).
  const setArgumentRowValue = (row, value, nth = null) => {
    setCustomArgs((prev) => {
      const text = prev || "";
      const occurrence =
        nth === null ? null : occurrencesOf(text, row.key)[nth];
      if (nth !== null && !occurrence) return text;
      return argumentBuilder.setArgumentValue(
        text,
        argumentIndex,
        row.key,
        value,
        { prefix: row.prefix, occurrence, option: row.flag },
      );
    });
  };

  const setArgumentRowFlag = (row, enabled) => {
    setCustomArgs((prev) =>
      argumentBuilder.setArgumentFlag(
        prev || "",
        argumentIndex,
        row.key,
        enabled,
        row.flag,
      ),
    );
  };

  const removeArgumentRow = (row, nth = null) => {
    setCustomArgs((prev) => {
      const text = prev || "";
      if (nth === null) {
        return argumentBuilder.removeArgument(
          text,
          argumentIndex,
          row.key,
          row.prefix,
        );
      }
      const occurrence = occurrencesOf(text, row.key)[nth];
      return occurrence
        ? argumentBuilder.removeOccurrence(text, occurrence)
        : text;
    });
  };

  const toggleFavoriteArgument = (id) => {
    setFavoriteArguments((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  const renderArgumentRow = (row, nth = null, sectionId = "") => {
    const rowKey = `${sectionId}:${row.id}:${nth ?? ""}`;
    const isFavorite = favoriteArguments.includes(row.id);
    const favoriteButton = (
      <button
        type="button"
        onClick={() => toggleFavoriteArgument(row.id)}
        className={`flex-none text-base leading-none ${isFavorite ? "ua-accent-text" : isDarkMode ? "text-gray-500 hover:text-gray-300" : "text-gray-400 hover:text-gray-600"}`}
        title={isFavorite ? "Remove from favorites" : "Add to favorites"}
        aria-label={`${isFavorite ? "Remove" : "Add"} ${row.label} ${isFavorite ? "from" : "to"} favorites`}
        aria-pressed={isFavorite}
      >
        {isFavorite ? "★" : "☆"}
      </button>
    );
    const description = row.description && (
      <div
        className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
      >
        {row.description}
      </div>
    );
    const cardClass = (active) =>
      `w-full rounded-lg border p-2 ${active ? "ua-accent-chip" : isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-100"}`;
    const fieldClass = `min-w-0 flex-1 rounded-md border px-2 py-1 text-sm font-mono ${
      isDarkMode
        ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
        : "bg-white border-gray-300 text-gray-900 placeholder-gray-400"
    }`;

    if (row.type === "insert") {
      return (
        <div key={rowKey} className={cardClass(false)}>
          <div className="flex items-start gap-2">
            {favoriteButton}
            <div className="min-w-0 flex-1">
              <div
                className={`text-sm font-medium ${isDarkMode ? "text-gray-100" : "text-gray-800"}`}
              >
                {row.label}
              </div>
              <code
                className={`block break-all text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
              >
                {row.insert}
              </code>
            </div>
            <button
              type="button"
              onClick={() => addArgument(row.insert)}
              disabled={isExecuting}
              className={`ua-accent-hover flex-none rounded-md border px-2 py-1 text-xs font-medium ${isDarkMode ? "bg-gray-700 border-gray-600 text-white" : "bg-white border-gray-200 text-gray-800"}`}
            >
              Add
            </button>
          </div>
          {description}
        </div>
      );
    }

    const occurrence =
      nth === null
        ? null
        : parsedArguments.occurrences.filter((item) => item.key === row.key)[
            nth
          ];
    const state = occurrence
      ? { present: true, value: occurrence.value }
      : argumentBuilder.getArgumentState(parsedArguments, row.key, row.prefix);
    const flagLabel = (
      <span
        className={`min-w-0 break-all text-sm font-mono ${isDarkMode ? "text-gray-100" : "text-gray-800"}`}
      >
        {nth !== null && occurrence ? occurrence.option : row.label}
      </span>
    );

    if (row.type === "flag") {
      return (
        <div key={rowKey} className={cardClass(state.present)}>
          <div className="flex items-center gap-2">
            {favoriteButton}
            <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={state.present}
                onChange={(event) =>
                  setArgumentRowFlag(row, event.target.checked)
                }
                disabled={isExecuting}
                className="h-4 w-4 flex-none"
              />
              {flagLabel}
            </label>
          </div>
          {description}
        </div>
      );
    }

    const removeButton = state.present && (
      <button
        type="button"
        onClick={() => removeArgumentRow(row, nth)}
        disabled={isExecuting}
        className={`flex-none rounded p-0.5 ${isDarkMode ? "text-gray-400 hover:bg-gray-700 hover:text-gray-100" : "text-gray-500 hover:bg-gray-100 hover:text-gray-800"}`}
        title="Remove from the command"
        aria-label={`Remove ${row.label} from the command`}
      >
        <LucideIcon name="x" className="h-4 w-4" />
      </button>
    );
    // "PC" selects "pc" when the parser lower-cases the value; other
    // unknown values stay listed so the select shows what is typed.
    const selectedChoice =
      argumentBuilder.matchChoice(
        { choices: row.choices, case_insensitive: row.caseInsensitive },
        state.value,
      ) || state.value;
    const choices =
      state.present && selectedChoice && !row.choices.includes(selectedChoice)
        ? [...row.choices, selectedChoice]
        : row.choices;
    const isPathOpen = argumentPathRowId === rowKey;

    return (
      <div key={rowKey} className={cardClass(state.present)}>
        <div className="flex items-center gap-2">
          {favoriteButton}
          {flagLabel}
          <span className="flex-1" />
          {removeButton}
        </div>
        <div className="mt-1.5 flex items-center gap-1.5">
          {row.type === "choice" ? (
            <select
              value={selectedChoice}
              onChange={(event) =>
                setArgumentRowValue(row, event.target.value, nth)
              }
              disabled={isExecuting}
              aria-label={`${row.label} value`}
              className={fieldClass}
            >
              <option value="">Not set</option>
              {choices.map((choice) => (
                <option key={choice} value={choice}>
                  {choice}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={state.value}
              onChange={(event) =>
                setArgumentRowValue(row, event.target.value, nth)
              }
              disabled={isExecuting}
              placeholder={row.placeholder}
              aria-label={`${row.label} value`}
              spellCheck={false}
              className={fieldClass}
            />
          )}
          {row.path && (
            <button
              type="button"
              onClick={() => setArgumentPathRowId(isPathOpen ? "" : rowKey)}
              data-ua-arg-browse={rowKey}
              disabled={isExecuting}
              className={`flex-none rounded-md border p-1.5 ${isDarkMode ? "border-gray-600 text-gray-300 hover:bg-gray-700" : "border-gray-300 text-gray-600 hover:bg-gray-100"}`}
              title={row.path === "folder" ? "Browse folders" : "Browse files"}
              aria-label={`Browse for ${row.label}`}
              aria-expanded={isPathOpen}
            >
              <LucideIcon name="folder-open" className="h-4 w-4" />
            </button>
          )}
        </div>
        {isPathOpen && (
          <ArgumentPathBrowser
            mode={row.path}
            apiBase={API_BASE}
            isDarkMode={isDarkMode}
            onPick={(path) => {
              setArgumentRowValue(row, path, nth);
              setArgumentPathRowId("");
              // The picked entry unmounts; keep focus in the panel (and modal).
              window.requestAnimationFrame(() =>
                document
                  .querySelector(`[data-ua-arg-browse="${CSS.escape(rowKey)}"]`)
                  ?.focus(),
              );
            }}
          />
        )}
        {description}
      </div>
    );
  };

  const renderArgumentSection = (section, rows, { count, note } = {}) => {
    const isCollapsed = collapsedSections.has(section.id);
    return (
      <div
        key={section.id}
        className={`rounded-lg border ${isDarkMode ? "border-gray-700" : "border-gray-200"}`}
      >
        <button
          type="button"
          onClick={() => toggleSectionCollapse(section.id)}
          aria-expanded={!isCollapsed}
          className={`w-full flex items-center justify-between p-3 text-left transition-colors rounded-t-lg ${
            isDarkMode ? "hover:bg-gray-700" : "hover:bg-gray-50"
          } ${isCollapsed ? "rounded-b-lg" : ""}`}
        >
          <div className="flex-1">
            <div
              className={`text-sm font-bold ${isDarkMode ? "text-gray-100" : "text-gray-900"} flex items-center gap-2`}
            >
              <span className={isDarkMode ? "text-gray-400" : "text-gray-500"}>
                {isCollapsed ? <ChevronRightIcon /> : <ChevronDownIcon />}
              </span>
              {section.title}
              <span
                className={`text-xs font-normal px-1.5 py-0.5 rounded ${isDarkMode ? "bg-gray-700 text-gray-400" : "bg-gray-200 text-gray-500"}`}
              >
                {count ?? rows.length}
              </span>
            </div>
            {section.subtitle && !isCollapsed && (
              <div
                className={`text-xs mt-1 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
              >
                {section.subtitle}
              </div>
            )}
          </div>
        </button>
        {!isCollapsed && (
          <div
            className={`px-3 pb-3 pt-2 ${isDarkMode ? "border-t border-gray-700" : "border-t border-gray-200"}`}
          >
            {note}
            <div className="grid grid-cols-[repeat(auto-fit,minmax(250px,1fr))] gap-2">
              {rows}
            </div>
          </div>
        )}
      </div>
    );
  };

  // Searching looks through every section, listing each option once.
  const getSearchedArgumentSections = () => {
    const searchLower = argSearchFilter.trim().toLowerCase();
    const seen = new Set();
    return argumentSectionList
      .map((section) => {
        const titleMatches = section.title.toLowerCase().includes(searchLower);
        const rows = section.rows.filter((row) => {
          if (seen.has(row.id)) return false;
          const matches =
            titleMatches ||
            [row.label, row.flag, row.insert, row.description, row.placeholder]
              .filter(Boolean)
              .some((text) => text.toLowerCase().includes(searchLower));
          if (matches) seen.add(row.id);
          return matches;
        });
        return rows.length ? { ...section, rows } : null;
      })
      .filter(Boolean);
  };

  const renderArgumentIssues = () =>
    argumentIssues.length > 0 && (
      <ul
        className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs"
        aria-label="Argument warnings"
      >
        {argumentIssues.map((issue, index) => (
          <li
            key={`${issue.type}-${index}`}
            className={`flex items-start gap-2 ${isDarkMode ? "text-amber-200" : "text-amber-800"}`}
          >
            <LucideIcon
              name="triangle-alert"
              className="mt-0.5 h-3.5 w-3.5 flex-none"
            />
            <span>{issue.message}</span>
          </li>
        ))}
      </ul>
    );

  const renderArgumentsPanel = ({ inModal = false } = {}) => {
    const searching = argSearchFilter.trim() !== "";
    const sections = searching
      ? getSearchedArgumentSections()
      : getArgumentViewSections(argumentView);
    const favoriteRows = favoriteArguments
      .map((id) => argumentRowsById.get(id))
      .filter(Boolean);
    const commandRows = parsedArguments.occurrences.map((occurrence) => {
      const nth = parsedArguments.occurrences
        .filter((item) => item.key === occurrence.key)
        .indexOf(occurrence);
      const row =
        argumentRowsByKey.get(occurrence.key) ||
        toArgumentRow(argumentIndex.items.get(occurrence.key).label);
      return renderArgumentRow(row, nth, "command");
    });
    const visibleSectionIds = [
      "command",
      "favorites",
      ...sections.map((section) => section.id),
    ];
    const toolbarButtonClass = `flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium rounded-md border transition-colors ${
      isDarkMode
        ? "bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600"
        : "bg-gray-100 border-gray-300 text-gray-600 hover:bg-gray-200"
    }`;
    const activeView = argumentViews.find((view) => view.id === argumentView);

    return (
      <div className="flex min-h-0 flex-1 flex-col">
        {/* In the sidebar, match the h-20 context header so the borders form one line. */}
        <div
          className={`ua-upload-panel-header flex flex-shrink-0 items-center justify-between gap-2 border-b ${isMobile ? "p-3" : inModal ? "p-4" : "h-20 px-4"}`}
        >
          <h2
            className={`${isMobile ? "text-base" : "text-lg"} font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex min-w-0 items-center gap-2 whitespace-nowrap`}
          >
            <TerminalIcon />
            Arguments
            {parsedArguments.occurrences.length > 0 && (
              <span
                className={`rounded px-1.5 text-xs font-normal leading-5 ${isDarkMode ? "bg-gray-700 text-gray-300" : "bg-gray-200 text-gray-600"}`}
              >
                {parsedArguments.occurrences.length} in command
              </span>
            )}
          </h2>
          <div className="flex flex-none items-center gap-0.5">
            {!isMobile && (
              <button
                type="button"
                onClick={() => setIsArgumentsExpanded(!inModal)}
                className={`flex-none rounded p-1 transition-colors ${isDarkMode ? "text-gray-400 hover:bg-gray-700 hover:text-gray-200" : "text-gray-500 hover:bg-gray-200 hover:text-gray-700"}`}
                title={inModal ? "Return to sidebar" : "Open in a larger view"}
                aria-label={
                  inModal ? "Return to sidebar" : "Open in a larger view"
                }
              >
                <LucideIcon
                  name={inModal ? "minimize-2" : "maximize-2"}
                  className="w-4 h-4"
                />
              </button>
            )}
            {inModal && (
              <button
                type="button"
                onClick={() => setIsArgumentsExpanded(false)}
                className={`flex-none rounded p-1 transition-colors ${isDarkMode ? "text-gray-400 hover:bg-gray-700 hover:text-gray-200" : "text-gray-500 hover:bg-gray-200 hover:text-gray-700"}`}
                title="Close"
                aria-label="Close"
              >
                <LucideIcon name="x" className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        <div
          className={`flex-shrink-0 space-y-2 border-b p-3 ${isDarkMode ? "border-gray-700" : "border-gray-200"}`}
        >
          <div
            className="flex flex-wrap gap-1.5"
            role="group"
            aria-label="Argument categories"
          >
            {argumentViews.map((view) => {
              const selected = view.id === argumentView && !searching;
              return (
                <button
                  key={view.id}
                  type="button"
                  onClick={() => {
                    setArgumentView(view.id);
                    setArgSearchFilter("");
                  }}
                  aria-pressed={selected}
                  title={view.description || view.label}
                  className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                    selected
                      ? "ua-accent-chip"
                      : isDarkMode
                        ? "border-gray-600 text-gray-300 hover:bg-gray-700"
                        : "border-gray-300 text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  <LucideIcon name={view.icon} className="h-3.5 w-3.5" />
                  {view.label}
                </button>
              );
            })}
          </div>
          {commandCategoryView && commandCategoryView === argumentView && (
            <p
              className={`text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
            >
              Showing {activeView?.label} options from --category.
            </p>
          )}
          <div className="relative">
            <div
              className={`absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
            >
              <SearchIcon />
            </div>
            <input
              type="text"
              aria-label="Search arguments"
              value={argSearchFilter}
              onChange={(e) => setArgSearchFilter(e.target.value)}
              placeholder="Search all arguments..."
              className={`w-full pl-10 pr-3 py-2 text-sm border rounded-lg ${
                isDarkMode
                  ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                  : "bg-white border-gray-300 text-gray-900 placeholder-gray-500"
              }`}
            />
            {argSearchFilter && (
              <button
                type="button"
                aria-label="Clear argument search"
                onClick={() => setArgSearchFilter("")}
                className={`absolute inset-y-0 right-0 pr-3 flex items-center ${isDarkMode ? "text-gray-400 hover:text-gray-200" : "text-gray-500 hover:text-gray-700"}`}
              >
                <LucideIcon name="x" className="h-4 w-4" />
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setCollapsedSections(new Set(visibleSectionIds))}
              className={toolbarButtonClass}
            >
              <CollapseAllIcon />
              Collapse All
            </button>
            <button
              type="button"
              onClick={() => setCollapsedSections(new Set())}
              className={toolbarButtonClass}
            >
              <ExpandAllIcon />
              Expand All
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {!searching &&
            commandRows.length > 0 &&
            renderArgumentSection(
              { id: "command", title: "In command" },
              commandRows,
            )}
          {!searching &&
            renderArgumentSection(
              { id: "favorites", title: "★ Favorites" },
              favoriteRows.map((row) =>
                renderArgumentRow(row, null, "favorites"),
              ),
              {
                note: favoriteRows.length === 0 && (
                  <p
                    className={`text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                  >
                    Choose ☆ on any argument to keep it here.
                  </p>
                ),
              },
            )}
          {sections.length === 0 ? (
            <div
              className={`text-center py-8 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
            >
              <p className="text-sm">
                No arguments found matching &quot;{argSearchFilter}&quot;
              </p>
            </div>
          ) : (
            sections.map((section) =>
              renderArgumentSection(
                section,
                section.rows.map((row) =>
                  renderArgumentRow(row, null, section.id),
                ),
              ),
            )
          )}
        </div>
      </div>
    );
  };

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

    const {
      value: nextDraft,
      selectionStart,
      selectionEnd,
    } = unit3dBbcode.insertBbcodeTags(
      descriptionDraft,
      editor.selectionStart,
      editor.selectionEnd,
      openingTag,
      closingTag,
    );

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
    const isSplitView = expandedReviewPanel === "description";
    const showEditor = isSplitView || descriptionView === "edit";
    const showPreview = isSplitView || descriptionView === "preview";
    const sources = Array.isArray(executionDescription?.sources)
      ? executionDescription.sources
      : [];
    return (
      <div className="flex h-full flex-col">
        <div className="ua-upload-panel-header border-b p-3">
          <div className="flex items-start justify-between gap-3">
            <div>
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
            {renderReviewExpandButton("description")}
          </div>
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
                className={`inline-flex rounded-md p-1 ${isSplitView ? "invisible" : ""} ${isDarkMode ? "bg-gray-800" : "bg-gray-100"}`}
              >
                {["edit", "preview"].map((view) => (
                  <button
                    key={view}
                    onClick={() => setDescriptionView(view)}
                    aria-pressed={descriptionView === view}
                    className={`rounded px-3 py-1 text-xs font-semibold capitalize ${descriptionView === view ? "ua-accent-action" : isDarkMode ? "text-gray-300 hover:bg-gray-700" : "text-gray-600 hover:bg-white"}`}
                  >
                    {view === "edit" ? "Write" : view}
                  </button>
                ))}
              </div>
              {showPreview && (
                <span
                  className={`text-right text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                >
                  Preview only. Other elements such as logos and screenshots
                  will be added later.
                </span>
              )}
            </div>
            <div
              className={
                isSplitView
                  ? "grid min-h-0 flex-1 grid-cols-2 gap-3"
                  : "flex min-h-0 flex-1 flex-col"
              }
            >
              {showEditor && (
                <div className="flex min-h-0 flex-1 flex-col">
                  <div
                    role="toolbar"
                    aria-label="Description formatting"
                    className={`mb-2 flex flex-wrap items-center gap-0.5 rounded-lg border p-1.5 ${isDarkMode ? "border-gray-700 bg-gray-800" : "border-gray-200 bg-gray-50"}`}
                  >
                    {unit3dBbcode.UNIT3D_BBCODE_TOOLBAR.map((group, index) => (
                      <React.Fragment key={group[0].title}>
                        {index > 0 && (
                          <span
                            aria-hidden="true"
                            className={`mx-1 h-5 w-px ${isDarkMode ? "bg-gray-600" : "bg-gray-300"}`}
                          />
                        )}
                        {group.map((tool) => (
                          <button
                            key={tool.title}
                            type="button"
                            title={
                              tool.key
                                ? `${tool.title} (Ctrl+${tool.key.toUpperCase()})`
                                : tool.title
                            }
                            aria-label={tool.title}
                            onMouseDown={(event) => event.preventDefault()}
                            onClick={() =>
                              applyDescriptionBbcode(tool.open, tool.close)
                            }
                            className={`ua-accent-hover rounded p-1.5 ${isDarkMode ? "text-gray-200" : "text-gray-700"}`}
                          >
                            <LucideIcon name={tool.icon} className="h-4 w-4" />
                          </button>
                        ))}
                      </React.Fragment>
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
                    onKeyDown={(event) => {
                      if (!event.ctrlKey || event.altKey || event.shiftKey) {
                        return;
                      }
                      const tool =
                        unit3dBbcode.UNIT3D_BBCODE_TOOLBAR.flat().find(
                          ({ key }) => key === event.key.toLowerCase(),
                        );
                      if (!tool) return;
                      event.preventDefault();
                      applyDescriptionBbcode(tool.open, tool.close);
                    }}
                    spellCheck={false}
                    aria-label="Base description"
                    className={`min-h-[20rem] flex-1 resize-y rounded-lg border p-3 font-mono text-xs leading-5 ${isDarkMode ? "border-gray-700 bg-gray-950 text-gray-100" : "border-gray-300 bg-white text-gray-800"}`}
                    placeholder="The editable base description will appear here."
                  />
                </div>
              )}
              {showPreview && (
                <div
                  data-mode={isDarkMode ? "dark" : "light"}
                  onClick={handleBbcodePreviewClick}
                  className={`bbcode-rendered min-h-[20rem] flex-1 overflow-auto rounded-lg border p-3 ${isDarkMode ? "border-gray-700 bg-gray-950" : "border-gray-300 bg-white"}`}
                  dangerouslySetInnerHTML={{
                    __html: renderBbcodePreview(descriptionDraft),
                  }}
                />
              )}
            </div>
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
                className="ua-accent-action rounded-md px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
              >
                {descriptionAction === "save" ? "Saving…" : "Save description"}
              </button>
            </div>
          </section>
        </div>
      </div>
    );
  };

  const renderMediaInfoPanel = () => {
    const reports = Array.isArray(executionMediaInfo?.reports)
      ? executionMediaInfo.reports
      : [];
    const selectedReport =
      reports.find((report) => report.key === selectedMediaInfoKey) ||
      reports[0];
    const emptyMessage =
      mediaInfoStatus === "error"
        ? "Could not load the report. Retrying…"
        : mediaInfoStatus === "pending"
          ? "The report has not been generated yet."
          : "Loading…";
    return (
      <div className="flex h-full flex-col">
        <div className="ua-upload-panel-header border-b p-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2
                className={`text-base font-bold ${isDarkMode ? "text-white" : "text-gray-800"}`}
              >
                {mediaInfoLabel}
              </h2>
              <p
                className={`mt-1 text-xs ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}
              >
                Read-only report generated for the current release.
              </p>
            </div>
            {renderReviewExpandButton("mediainfo")}
          </div>
        </div>
        <div className="flex flex-1 min-h-0 flex-col gap-3 overflow-hidden p-3">
          {reports.length > 1 && (
            <div className="overflow-x-auto pb-1">
              <div
                className={`inline-flex w-max rounded-md p-1 ${isDarkMode ? "bg-gray-800" : "bg-gray-100"}`}
              >
                {reports.map((report) => (
                  <button
                    key={report.key}
                    onClick={() => setSelectedMediaInfoKey(report.key)}
                    aria-pressed={selectedReport?.key === report.key}
                    className={`whitespace-nowrap rounded px-3 py-1 text-xs font-semibold ${selectedReport?.key === report.key ? "ua-accent-action" : isDarkMode ? "text-gray-300 hover:bg-gray-700" : "text-gray-600 hover:bg-white"}`}
                  >
                    {report.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {selectedReport ? (
            <>
              <pre
                aria-label={`${selectedReport.label} report`}
                className={`min-h-[20rem] flex-1 overflow-auto whitespace-pre rounded-lg border p-3 font-mono text-xs leading-5 ${isDarkMode ? "border-gray-700 bg-gray-950 text-gray-100" : "border-gray-300 bg-white text-gray-800"}`}
              >
                {selectedReport.content}
              </pre>
              <div className="flex items-center justify-between gap-3">
                <span
                  className={`text-xs ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                >
                  {selectedReport.content.length.toLocaleString()} characters
                </span>
                <button
                  onClick={() => copyMediaInfoReport(selectedReport.content)}
                  className="ua-accent-action rounded-md px-3 py-1.5 text-xs font-semibold"
                >
                  {mediaInfoCopied ? "Copied" : "Copy"}
                </button>
              </div>
            </>
          ) : (
            <p className="text-xs text-gray-500">{emptyMessage}</p>
          )}
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
    const orderedScreenshots = orderScreenshotsByGroup(executionScreenshots);
    const expandedIndex = expandedItem
      ? orderedScreenshots.findIndex(
          (screenshot) => screenshot.id === expandedItem.id,
        )
      : -1;
    const previousScreenshot =
      expandedIndex > 0 ? orderedScreenshots[expandedIndex - 1] : null;
    const nextScreenshot =
      expandedIndex >= 0 ? orderedScreenshots[expandedIndex + 1] : null;
    const isGeneratingFrame =
      screenshotActionId === "add" || screenshotActionId.startsWith("replace:");
    const screenshotStateLabel = {
      remote: "Remote",
      replacement: "Replacement",
      addition: "Added",
    };
    const renderScreenshotActions = (screenshot, inLightbox = false) => {
      const replacing = screenshotActionId === `replace:${screenshot.id}`;
      const deleting = screenshotActionId === `delete:${screenshot.id}`;
      const undoing = screenshotActionId === `undo:${screenshot.id}`;
      const confirmingDelete = pendingDeleteScreenshot === screenshot.id;
      const neutralButtonClass = inLightbox
        ? "bg-white/10 text-gray-100 hover:bg-white/20"
        : isDarkMode
          ? "bg-gray-700 text-gray-100 hover:bg-gray-600"
          : "bg-gray-100 text-gray-700 hover:bg-gray-200";
      return (
        <>
          {screenshot.can_replace && (
            <button
              type="button"
              onClick={() =>
                changeExecutionScreenshot(screenshot.id, "replace")
              }
              disabled={isWorking}
              className="ua-accent-action px-2 py-1 text-xs rounded-md disabled:opacity-50"
            >
              {replacing ? "Generating…" : "Replace"}
            </button>
          )}
          {screenshot.source === "replacement" && (
            <button
              type="button"
              onClick={() => changeExecutionScreenshot(screenshot.id, "undo")}
              disabled={isWorking}
              className={`px-2 py-1 text-xs rounded-md disabled:opacity-50 ${neutralButtonClass}`}
              title="Restore the original remote screenshot"
              aria-label="Restore the original remote screenshot"
            >
              {undoing ? "Restoring…" : "Undo"}
            </button>
          )}
          {screenshot.can_delete && (
            <button
              type="button"
              onClick={() => {
                if (confirmingDelete) {
                  setPendingDeleteScreenshot("");
                  changeExecutionScreenshot(screenshot.id, "delete");
                } else {
                  setPendingDeleteScreenshot(screenshot.id);
                }
              }}
              disabled={isWorking}
              className={`rounded-md disabled:opacity-50 ${confirmingDelete ? "bg-rose-600 px-2 py-1 text-xs font-semibold text-white hover:bg-rose-700" : `p-1.5 text-rose-500 ${inLightbox ? "hover:bg-white/10" : "hover:bg-rose-50 dark:hover:bg-rose-950/40"}`}`}
              title={
                confirmingDelete
                  ? "Click again to delete"
                  : `Delete ${screenshot.filename}`
              }
              aria-label={
                confirmingDelete
                  ? `Confirm deleting ${screenshot.filename}`
                  : `Delete ${screenshot.filename}`
              }
            >
              {deleting ? (
                <SpinnerIcon />
              ) : confirmingDelete ? (
                "Confirm delete"
              ) : (
                <TrashIcon />
              )}
            </button>
          )}
        </>
      );
    };
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
          <div className="ua-upload-panel-header p-3 border-b flex-shrink-0">
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
                {isGeneratingFrame && (
                  <p
                    className={`mt-1 flex items-center gap-1.5 text-xs font-semibold ${isDarkMode ? "text-gray-200" : "text-gray-700"}`}
                    role="status"
                  >
                    <SpinnerIcon />
                    Generating a new frame…
                  </p>
                )}
              </div>
              <button
                onClick={() => addExecutionScreenshot("main")}
                disabled={isWorking || !canAddExecutionScreenshot}
                className="ua-accent-action p-2 rounded-md disabled:opacity-50"
                title="Capture an additional screenshot"
                aria-label="Capture an additional screenshot"
              >
                {screenshotActionId === "add" ? <SpinnerIcon /> : <PlusIcon />}
              </button>
              {renderReviewExpandButton("screenshots")}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            {screenshotError && (
              <div
                className="mb-3 flex items-start justify-between gap-3 rounded-lg bg-rose-600 px-3 py-2 text-xs text-white"
                role="alert"
              >
                <span>{screenshotError}</span>
                <button
                  type="button"
                  onClick={() => setScreenshotError("")}
                  className="font-semibold underline"
                >
                  Dismiss
                </button>
              </div>
            )}
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
                          className="ua-accent-action ml-auto rounded-md px-2 py-1 normal-case tracking-normal disabled:opacity-50"
                        >
                          Add to this group
                        </button>
                      </div>
                      <div className="ua-upload-screenshot-grid grid gap-3">
                        {screenshots.map((screenshot, index) => {
                          const replacing =
                            screenshotActionId === `replace:${screenshot.id}`;
                          const screenshotState =
                            screenshotStateLabel[screenshot.source] || "Local";
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
                              <button
                                type="button"
                                onClick={() =>
                                  setExpandedScreenshot(screenshot.id)
                                }
                                className="block w-full cursor-zoom-in"
                                aria-label={`Expand ${screenshot.filename}`}
                              >
                                <img
                                  src={screenshot.image_url}
                                  alt={`Screenshot ${index + 1}`}
                                  className={`w-full aspect-video object-contain bg-black transition-all duration-300 ${replacing ? "opacity-35 brightness-50" : "opacity-100 brightness-100"}`}
                                  loading="lazy"
                                />
                              </button>
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
                                    {screenshot.size
                                      ? ` · ${formatSize(screenshot.size)}`
                                      : ""}
                                  </span>
                                </div>
                                <div className="flex gap-1.5 flex-shrink-0">
                                  {renderScreenshotActions(screenshot)}
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setExpandedScreenshot(screenshot.id)
                                    }
                                    className={`p-1.5 rounded-md ${isDarkMode ? "text-gray-200 hover:bg-gray-700" : "text-gray-600 hover:bg-gray-100"}`}
                                    title={`Expand ${screenshot.filename}`}
                                    aria-label={`Expand ${screenshot.filename}`}
                                  >
                                    <ExpandIcon />
                                  </button>
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
            className="fixed inset-0 z-50 flex flex-col bg-black/90"
            role="dialog"
            aria-modal="true"
            aria-label={`Expanded ${expandedItem.filename}`}
            tabIndex="-1"
          >
            <div className="flex flex-none flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2 text-sm text-gray-100">
              <span className="font-semibold tabular-nums">
                {expandedIndex + 1} / {orderedScreenshots.length}
              </span>
              <span className="min-w-0 truncate font-mono text-xs text-gray-300">
                {expandedItem.filename}
              </span>
              <span className="text-xs text-gray-400 tabular-nums">
                {[
                  expandedScreenshotSize
                    ? `${expandedScreenshotSize.width}×${expandedScreenshotSize.height}`
                    : "",
                  expandedItem.size ? formatSize(expandedItem.size) : "",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
              <div className="ml-auto flex flex-wrap items-center gap-1.5">
                {renderScreenshotActions(expandedItem, true)}
                <button
                  type="button"
                  onClick={() => setIsScreenshotZoomed((zoomed) => !zoomed)}
                  aria-pressed={isScreenshotZoomed}
                  className="rounded-md bg-white/10 px-2 py-1 text-xs text-gray-100 hover:bg-white/20"
                  title={
                    isScreenshotZoomed
                      ? "Fit the image to the window"
                      : "Show at full size"
                  }
                >
                  {isScreenshotZoomed ? "Fit" : "100%"}
                </button>
                <button
                  type="button"
                  onClick={() => setExpandedScreenshot(null)}
                  className="rounded-md bg-white/10 px-3 py-1 text-xs text-gray-100 hover:bg-white/20"
                  data-ua-modal-initial-focus
                >
                  Close
                </button>
              </div>
            </div>
            {screenshotError && (
              <div
                className="mx-4 mb-2 flex-none rounded-md bg-rose-600 px-3 py-1.5 text-xs text-white"
                role="alert"
              >
                {screenshotError}
              </div>
            )}
            <div className="relative flex min-h-0 flex-1">
              <div
                className={`h-full w-full ${isScreenshotZoomed ? "overflow-auto" : "flex items-center justify-center p-4"}`}
                onClick={(event) => {
                  if (event.target === event.currentTarget) {
                    setExpandedScreenshot(null);
                  }
                }}
              >
                <img
                  key={expandedItem.full_image_url || expandedItem.image_url}
                  src={expandedItem.full_image_url || expandedItem.image_url}
                  alt={expandedItem.filename}
                  onLoad={(event) =>
                    setExpandedScreenshotSize({
                      width: event.currentTarget.naturalWidth,
                      height: event.currentTarget.naturalHeight,
                    })
                  }
                  onClick={() => setIsScreenshotZoomed((zoomed) => !zoomed)}
                  className={
                    isScreenshotZoomed
                      ? "m-auto block max-w-none cursor-zoom-out"
                      : "max-h-full max-w-full cursor-zoom-in object-contain"
                  }
                />
              </div>
              {previousScreenshot && (
                <button
                  type="button"
                  onClick={() => setExpandedScreenshot(previousScreenshot.id)}
                  className="absolute left-3 top-1/2 -translate-y-1/2 rounded-full bg-black/60 p-2 text-white hover:bg-black"
                  title="Previous screenshot (←)"
                  aria-label="Previous screenshot"
                >
                  <LucideIcon name="chevron-left" className="h-6 w-6" />
                </button>
              )}
              {nextScreenshot && (
                <button
                  type="button"
                  onClick={() => setExpandedScreenshot(nextScreenshot.id)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full bg-black/60 p-2 text-white hover:bg-black"
                  title="Next screenshot (→)"
                  aria-label="Next screenshot"
                >
                  <LucideIcon name="chevron-right" className="h-6 w-6" />
                </button>
              )}
            </div>
          </div>
        )}
      </>
    );
  };

  const renderExecutionPreviewPanel = (compact = false) => {
    const media = executionPreview;
    const category = String(media?.category || "").toUpperCase();
    const showTrackDetails = category === "MOVIE" || category === "TV";
    const baseTitle =
      media?.title ||
      media?.name ||
      media?.filename ||
      "Detecting media metadata...";
    const previewTitle = media?.year
      ? `${baseTitle} (${media.year})`
      : baseTitle;
    const originalTitle = String(media?.original_title || "").trim();
    const showOriginalTitle =
      originalTitle &&
      originalTitle.localeCompare(baseTitle, undefined, {
        sensitivity: "accent",
      }) !== 0;
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
    const panelPadding = compact ? "p-3" : "p-4";
    const titleSize = compact ? "text-[1.4rem]" : "text-[1.575rem]";
    const posterHeight = compact ? "h-64" : "h-80";
    const backdropUrl = media?.backdrop_url || media?.poster_url;
    const overviewText =
      category === "TV"
        ? media?.episode_overview || media?.overview
        : media?.overview;
    const music = media?.music || {};
    // Music shows its artist(s) above the album title, as on a record sleeve.
    const titleArtist =
      category === "MUSIC" ? String(music.artist || "").trim() : "";
    const artistSize = compact ? "text-base" : "text-lg";
    const detailSections = Array.isArray(media?.detail_sections)
      ? media.detail_sections.filter(
          (section) =>
            section && Array.isArray(section.items) && section.items.length > 0,
        )
      : [];

    const audioTracks = Array.isArray(media?.audio_tracks)
      ? media.audio_tracks
      : [];
    const subtitleTracks = Array.isArray(media?.subtitle_tracks)
      ? media.subtitle_tracks
      : [];

    const renderMediaTrack = (track, kind) => {
      const badges = [];
      const languageFlag = getPreviewLanguageFlag(
        track.language,
        track.language_code,
      );

      if (track.format) badges.push({ label: track.format });
      if (kind === "audio" && track.channels)
        badges.push({ label: track.channels });
      if (kind === "audio" && track.bitrate)
        badges.push({ label: track.bitrate });
      if (track.default) badges.push({ label: "Default", status: true });
      if (track.forced) badges.push({ label: "Forced", status: true });
      if (track.hearing_impaired)
        badges.push({ label: "SDH/HI", status: true });
      if (track.commentary) badges.push({ label: "Commentary", status: true });
      const languageLabel =
        track.language_code || track.language || "Unknown language";

      return (
        <div
          key={`${kind}-${track.index}`}
          className="ua-processing-track rounded-xl border px-3 py-3"
          data-default={Boolean(track.default)}
        >
          <div className="flex items-start gap-2">
            <span className="ua-processing-track-index ua-processing-muted shrink-0 text-sm font-semibold">
              {track.index}.
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="ua-processing-track-language inline-flex items-center gap-2 text-sm font-semibold">
                  {languageFlag && (
                    <img
                      src={languageFlag}
                      alt=""
                      aria-hidden="true"
                      width="24"
                      height="18"
                      className="ua-language-flag shrink-0 object-contain"
                    />
                  )}
                  {languageLabel}
                </span>
                {badges.map((badge, index) => (
                  <span
                    key={`${badge.label}-${index}`}
                    className={`ua-processing-track-badge rounded-md ${badge.status ? "ua-processing-track-status" : ""}`}
                  >
                    {badge.label}
                  </span>
                ))}
              </div>
              {track.language && track.language !== languageLabel && (
                <p className="ua-processing-muted mt-2 break-words text-xs">
                  {track.language}
                </p>
              )}
              {track.title && (
                <p className="ua-processing-muted mt-1 break-words text-xs">
                  {track.title}
                </p>
              )}
            </div>
          </div>
        </div>
      );
    };

    const renderMediaTrackFlags = (tracks, kind) => {
      const flags = tracks.flatMap((track, index) => {
        const src = getPreviewLanguageFlag(track.language, track.language_code);
        const language = String(track.language || "").trim();
        const code = String(track.language_code || "").trim();
        const label =
          language &&
          /[-_]/.test(code) &&
          !language
            .toLowerCase()
            .replace(/_/g, "-")
            .includes(code.toLowerCase().replace(/_/g, "-"))
            ? `${language} (${code})`
            : language || code;
        return src ? [{ src, language: label, index }] : [];
      });
      if (flags.length === 0) return null;

      return (
        <div
          role="group"
          aria-label={`${kind === "audio" ? "Audio" : "Subtitle"} track languages`}
          className="flex flex-wrap items-center gap-1.5 pb-2"
        >
          {flags.map((flag) => (
            <img
              key={`${kind}-${flag.index}`}
              src={flag.src}
              alt={flag.language}
              title={flag.language}
              width="24"
              height="18"
              className="ua-language-flag h-[18px] w-6 shrink-0 object-contain"
            />
          ))}
        </div>
      );
    };

    const renderPreviewSection = (section) => (
      <section key={section.key} className="ua-processing-section">
        <h4 className="ua-processing-section-title">{section.label}</h4>
        <dl className="ua-processing-detail-list">
          {section.items.map((item) => (
            <div key={item.key} className="ua-processing-detail-row">
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      </section>
    );

    const renderedDetailSections = detailSections.map(renderPreviewSection);

    return (
      <div className="ua-processing-preview flex h-full flex-col">
        <div className="flex-1 overflow-y-auto">
          <div
            className="ua-processing-card min-h-full overflow-hidden"
            style={{
              "--ua-processing-artwork-height": compact ? "16rem" : "20rem",
            }}
          >
            {backdropUrl && (
              <div className="ua-processing-backdrop" aria-hidden="true">
                <img
                  src={backdropUrl}
                  alt=""
                  onError={(event) => {
                    if (
                      media?.poster_url &&
                      event.currentTarget.getAttribute("src") !==
                        media.poster_url
                    ) {
                      event.currentTarget.src = media.poster_url;
                    }
                  }}
                />
              </div>
            )}
            {media?.poster_url ? (
              <div
                className={`ua-processing-artwork relative flex w-full items-center justify-center ${posterHeight}`}
              >
                <div className="flex h-full min-w-0 flex-1 items-center justify-center p-3">
                  <img
                    src={media.poster_url}
                    alt={previewTitle}
                    className="ua-processing-poster max-h-full max-w-full object-contain"
                  />
                </div>
                {category === "XXX" &&
                  String(media.poster_url).startsWith(
                    "/api/execution_preview_cover?",
                  ) && (
                    <button
                      type="button"
                      onClick={regenerateExecutionCover}
                      disabled={Boolean(coverAction)}
                      aria-label={
                        coverAction === "regenerate"
                          ? "Generating a new XXX cover"
                          : "Generate a new XXX cover"
                      }
                      className="ua-processing-cover-action ua-accent-action absolute right-3 top-3 inline-flex flex-shrink-0 items-center gap-1.5 rounded-full p-2.5 text-xs font-semibold disabled:cursor-wait disabled:opacity-60"
                      title="Generate another cover from a different video frame"
                    >
                      <span aria-hidden="true">
                        {coverAction === "regenerate" ? (
                          <SpinnerIcon />
                        ) : (
                          <RefreshIcon />
                        )}
                      </span>
                    </button>
                  )}
              </div>
            ) : (
              <div
                className={`ua-processing-artwork relative flex w-full ${posterHeight} flex-col items-center justify-center gap-3`}
              >
                <span
                  className="ua-processing-placeholder-icon"
                  aria-hidden="true"
                >
                  {mediaIconForCategory(category)}
                </span>
                <span className="ua-processing-muted text-sm">
                  {media?.status === "waiting"
                    ? "Reading media metadata…"
                    : "Artwork not available"}
                </span>
              </div>
            )}

            <div className={`${panelPadding} space-y-4`}>
              <div>
                <div className="ua-processing-eyebrow mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.12em]">
                  {mediaIconForCategory(category)}
                  <span>{category || "Media"}</span>
                </div>
                {titleArtist && (
                  <p
                    className={`ua-processing-artist ${artistSize} mb-0.5 font-semibold leading-snug`}
                  >
                    {titleArtist}
                  </p>
                )}
                <h3
                  className={`ua-processing-title ${titleSize} font-bold leading-tight`}
                >
                  {baseTitle}
                  {media?.year && (
                    <span className="ua-processing-year"> ({media.year})</span>
                  )}
                </h3>
                {showOriginalTitle && (
                  <p className="ua-processing-muted mt-1 text-sm">
                    Original title: {originalTitle}
                  </p>
                )}
              </div>

              {previewProviders.length > 0 && (
                <section className="ua-processing-provider-section">
                  <h4 className="sr-only">Metadata providers</h4>
                  <div className="flex flex-wrap gap-2">
                    {previewProviders.map((source) => {
                      const providerClass = getMetadataProviderStyle(
                        source.key,
                        isDarkMode,
                      );
                      const content = (
                        <>
                          <span className="inline-flex shrink-0 items-center justify-center h-[1.2rem]">
                            {renderMetadataProviderIcon(source.key, isDarkMode)}
                          </span>
                          <span className="min-w-0">
                            <span className="block text-[0.7rem] leading-4 font-bold tabular-nums truncate">
                              {source.value}
                            </span>
                          </span>
                        </>
                      );
                      const sharedClassName = `ua-processing-provider inline-flex items-center gap-2 max-w-full rounded-full border-[1.6px] px-[0.8rem] py-[0.3rem] transition-colors ${providerClass}`;

                      if (source.url) {
                        return (
                          <a
                            key={`${source.key}-${source.value}`}
                            href={source.url}
                            target="_blank"
                            rel="noopener noreferrer"
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
                </section>
              )}

              {genres.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {genres.map((genre) => (
                    <span key={genre} className="ua-processing-genre">
                      {genre}
                    </span>
                  ))}
                </div>
              )}

              {(overviewText || media?.status === "waiting") && (
                <section className="ua-processing-section">
                  <h4 className="ua-processing-section-title">
                    {category === "MUSIC"
                      ? "Release Notes"
                      : category === "TV" && media?.episode_overview
                        ? "Episode Overview"
                        : "Overview"}
                  </h4>
                  <p className="ua-processing-overview text-sm leading-6">
                    {overviewText ||
                      "Upload Assistant is analyzing this item. Metadata will appear as soon as the first snapshot is ready."}
                  </p>
                </section>
              )}

              {showTrackDetails && media?.status !== "waiting" && (
                <section className="ua-processing-section">
                  <h4 className="ua-processing-section-title">Track Details</h4>
                  <div className="ua-processing-track-controls space-y-2">
                    <button
                      type="button"
                      onClick={() => setShowAudioTracks((value) => !value)}
                      aria-pressed={showAudioTracks}
                      className="ua-processing-track-toggle flex w-full items-center justify-between gap-3 rounded-lg py-2 text-left transition-colors"
                    >
                      <span>
                        <span className="block text-sm font-medium">
                          Show audio tracks
                        </span>
                        <span className="ua-processing-muted block text-xs">
                          {audioTracks.length} track
                          {audioTracks.length === 1 ? "" : "s"} detected
                        </span>
                      </span>
                      <span
                        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
                          showAudioTracks
                            ? "ua-accent-indicator"
                            : isDarkMode
                              ? "bg-gray-700"
                              : "bg-gray-300"
                        }`}
                      >
                        <span
                          className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                            showAudioTracks ? "translate-x-6" : "translate-x-1"
                          }`}
                        />
                      </span>
                    </button>

                    {!showAudioTracks &&
                      renderMediaTrackFlags(audioTracks, "audio")}

                    <button
                      type="button"
                      onClick={() => setShowSubtitleTracks((value) => !value)}
                      aria-pressed={showSubtitleTracks}
                      className="ua-processing-track-toggle flex w-full items-center justify-between gap-3 rounded-lg py-2 text-left transition-colors"
                    >
                      <span>
                        <span className="block text-sm font-medium">
                          Show subtitle tracks
                        </span>
                        <span className="ua-processing-muted block text-xs">
                          {subtitleTracks.length} track
                          {subtitleTracks.length === 1 ? "" : "s"} detected
                        </span>
                      </span>
                      <span
                        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
                          showSubtitleTracks
                            ? "ua-accent-indicator"
                            : isDarkMode
                              ? "bg-gray-700"
                              : "bg-gray-300"
                        }`}
                      >
                        <span
                          className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                            showSubtitleTracks
                              ? "translate-x-6"
                              : "translate-x-1"
                          }`}
                        />
                      </span>
                    </button>
                    {!showSubtitleTracks &&
                      renderMediaTrackFlags(subtitleTracks, "subtitle")}
                  </div>
                </section>
              )}

              {showTrackDetails &&
                showAudioTracks &&
                audioTracks.length > 0 && (
                  <section className="ua-processing-section">
                    <h4 className="ua-processing-section-title">
                      Audio Tracks ({audioTracks.length})
                    </h4>
                    <div className="ua-processing-track-list space-y-2">
                      {audioTracks.map((track) =>
                        renderMediaTrack(track, "audio"),
                      )}
                    </div>
                  </section>
                )}

              {showTrackDetails &&
                showSubtitleTracks &&
                subtitleTracks.length > 0 && (
                  <section className="ua-processing-section">
                    <h4 className="ua-processing-section-title">
                      Subtitle Tracks ({subtitleTracks.length})
                    </h4>
                    <div className="ua-processing-track-list space-y-2">
                      {subtitleTracks.map((track) =>
                        renderMediaTrack(track, "subtitle"),
                      )}
                    </div>
                  </section>
                )}

              {renderedDetailSections}

              {category === "MUSIC" &&
                Array.isArray(music?.warnings) &&
                music.warnings.length > 0 && (
                  <section className="ua-processing-warning rounded-xl border p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide mb-2">
                      Music Validation
                    </p>
                    <ul className="space-y-1 text-xs leading-5">
                      {music.warnings.map((warning, index) => (
                        <li key={`${warning}-${index}`}>• {warning}</li>
                      ))}
                    </ul>
                  </section>
                )}

              {(media?.path || selectedPath) && (
                <footer className="ua-processing-source border-t pt-3">
                  <p className="ua-processing-section-title mb-1">
                    Source Path
                  </p>
                  <p className="break-all font-mono text-xs">
                    {media?.path || selectedPath}
                  </p>
                </footer>
              )}
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

  const isGuiOutput = outputMode === "gui";

  const renderOutputModeToggle = (compact = false) => (
    <div
      role="radiogroup"
      aria-label="Output view"
      className="ua-run-gui-mode-toggle inline-flex shrink-0 rounded-lg border p-0.5"
    >
      {[
        { mode: "terminal", icon: "square-terminal", label: "Terminal" },
        { mode: "gui", icon: "layout-dashboard", label: "GUI" },
      ].map((option) => (
        <button
          key={option.mode}
          type="button"
          role="radio"
          aria-checked={outputMode === option.mode}
          onClick={() => setOutputMode(option.mode)}
          title={
            option.mode === "gui"
              ? "Show errors, prompts and results as panels"
              : "Show the raw terminal output"
          }
          className={`ua-run-gui-mode-option flex items-center gap-1.5 rounded-md ${compact ? "px-2 py-1 text-xs" : "px-2.5 py-1 text-sm"} font-medium`}
          data-active={outputMode === option.mode}
        >
          <LucideIcon name={option.icon} className="h-4 w-4" />
          {option.label}
        </button>
      ))}
    </div>
  );

  const RUN_GUI_TRACKER_STATUS = {
    success: { icon: "circle-check", label: "Uploaded", tone: "success" },
    failed: { icon: "circle-x", label: "Failed", tone: "error" },
    pending: { icon: "clock", label: "Queued", tone: "info" },
    dupe: { icon: "copy-check", label: "Dupe", tone: "attention" },
    banned: { icon: "ban", label: "Banned", tone: "error" },
    skipped: { icon: "circle-minus", label: "Skipped", tone: "muted" },
  };

  const RUN_GUI_SLOT_ICONS = {
    allow: "circle-check",
    block: "circle-x",
    review: "triangle-alert",
  };

  const renderRunGuiTrackerIcon = (name) => {
    const tracker = trackers.find((entry) => entry.name === name);
    if (tracker?.favicon && !failedFavicons.has(name)) {
      return (
        <img
          src={tracker.favicon}
          alt=""
          onError={() => setFailedFavicons((prev) => new Set(prev).add(name))}
          className="h-4 w-4 shrink-0 rounded-sm object-contain"
        />
      );
    }
    return (
      <span
        aria-hidden="true"
        className="ua-run-gui-tracker-fallback flex h-4 w-4 shrink-0 items-center justify-center rounded-sm text-[9px] font-bold uppercase"
      >
        {String(name || "?").slice(0, 1)}
      </span>
    );
  };

  const runGuiTrackerName = (name) =>
    trackers.find((entry) => entry.name === name)?.display_name || name;

  const renderRunGuiTracker = (name) =>
    name ? (
      <span className="inline-flex min-w-0 items-center gap-1.5 font-semibold">
        {renderRunGuiTrackerIcon(name)}
        <span className="truncate">{runGuiTrackerName(name)}</span>
      </span>
    ) : null;

  const renderRunGuiTrackerChips = (names, tone = "muted") => (
    <div className="flex flex-wrap gap-1.5">
      {names.map((name) => (
        <span
          key={name}
          className="ua-run-gui-chip inline-flex items-center rounded-md px-2 py-0.5 text-xs"
          data-tone={tone}
        >
          {renderRunGuiTracker(name)}
        </span>
      ))}
    </div>
  );

  const renderRunGuiLink = (href, label, className = "") =>
    /^https?:\/\//i.test(href || "") ? (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={`ua-run-gui-link inline-flex min-w-0 items-center gap-1 ${className}`}
      >
        <span className="truncate">{label}</span>
        <LucideIcon name="external-link" className="h-3.5 w-3.5 shrink-0" />
      </a>
    ) : (
      <span className={`min-w-0 truncate ${className}`}>{label}</span>
    );

  /** A titled panel; pass onToggle to let the user collapse it to its header. */
  const renderRunGuiBlock = ({
    tone,
    icon,
    title,
    count,
    aside,
    children,
    collapsed = false,
    onToggle = null,
  }) => (
    <section
      className="ua-run-gui-block rounded-xl border shadow-sm"
      data-tone={tone}
    >
      <header
        className={`ua-run-gui-block-header flex items-center gap-2 px-3 py-2 ${collapsed ? "" : "border-b"}`}
      >
        <LucideIcon name={icon} className="ua-run-gui-tone-icon h-4 w-4" />
        <h3 className="text-sm font-semibold">{title}</h3>
        {count > 0 && (
          <span className="ua-run-gui-count rounded-full px-2 text-xs font-semibold">
            {count}
          </span>
        )}
        {aside && <div className="ml-auto min-w-0">{aside}</div>}
        {onToggle && (
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={!collapsed}
            aria-label={`${collapsed ? "Expand" : "Collapse"} ${title}`}
            title={collapsed ? "Expand" : "Collapse"}
            className={`ua-run-gui-collapse flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${aside ? "" : "ml-auto"}`}
          >
            <LucideIcon
              name={collapsed ? "chevron-down" : "chevron-up"}
              className="h-4 w-4"
            />
          </button>
        )}
      </header>
      {!collapsed && <div className="px-3 py-2">{children}</div>}
    </section>
  );

  const renderRunGuiSectionLabel = (label) => (
    <p className="ua-run-gui-section-label text-[0.68rem] font-semibold uppercase tracking-wider">
      {label}
    </p>
  );

  /** Every release on a site, coloured like the terminal: red means nearly your size. */
  const renderRunGuiReleaseList = (entries) => (
    <ul className="mt-1 space-y-1">
      {entries.map((entry, index) => (
        <li
          key={`${entry.link || entry.name}-${index}`}
          className="flex min-w-0 items-center gap-2 text-sm"
        >
          {renderRunGuiLink(entry.link, entry.name, "flex-1")}
          {entry.size ? (
            <span className="shrink-0 text-xs tabular-nums">
              <span className="ua-run-gui-muted">{formatSize(entry.size)}</span>
              {entry.diffPct !== null && (
                <span
                  className="ua-run-gui-size-diff ml-1.5 rounded px-1.5 py-0.5 font-semibold"
                  style={
                    entry.color
                      ? { "--ua-run-gui-diff": entry.color }
                      : undefined
                  }
                  title={
                    Math.abs(entry.diffPct) < 2
                      ? "About the same size as yours"
                      : `${Math.abs(entry.diffPct)}% ${entry.diffPct < 0 ? "smaller" : "larger"} than yours`
                  }
                >
                  {entry.diffPct > 0 ? "+" : ""}
                  {entry.diffPct}%
                </span>
              )}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );

  const renderRunGuiSlot = (slot) => (
    <div
      className="ua-run-gui-slot space-y-2 rounded-md px-3 py-2.5"
      data-verdict={slot.verdict}
    >
      <div className="flex items-start gap-2">
        <LucideIcon
          name={RUN_GUI_SLOT_ICONS[slot.verdict] || "circle-help"}
          className="ua-run-gui-slot-icon mt-0.5 h-4 w-4 shrink-0"
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold">{slot.title}</p>
          {slot.reason && <p className="text-sm">{slot.reason}</p>}
        </div>
      </div>
      {slot.slot && (
        <p className="text-sm">
          <span className="ua-run-gui-muted">Slot: </span>
          {slot.slot}
        </p>
      )}
      {slot.why && (
        <div>
          {renderRunGuiSectionLabel("Why")}
          <p className="text-sm">{slot.why}</p>
        </div>
      )}
      {slot.conflicts.length > 0 && (
        <div>
          {renderRunGuiSectionLabel("Already on the site")}
          {renderRunGuiReleaseList(slot.conflicts)}
        </div>
      )}
      {slot.notes.map((note, index) => (
        <p key={index} className="text-sm">
          <span className="font-semibold">Note: </span>
          {note}
        </p>
      ))}
      {slot.rules && <p className="ua-run-gui-muted text-xs">{slot.rules}</p>}
    </div>
  );

  const renderRunGuiDupe = (dupe) => (
    <div>
      {renderRunGuiSectionLabel(
        dupe.trumpable
          ? "Trumpable releases on the site"
          : "Possible dupes on the site",
      )}
      {dupe.note && <p className="ua-run-gui-muted text-xs">{dupe.note}</p>}
      {renderRunGuiReleaseList(dupe.entries)}
    </div>
  );

  const renderRunGuiNotice = (notice) => (
    <li key={notice.id} className="flex min-w-0 items-start gap-2 py-1 text-sm">
      {notice.tracker ? (
        <span className="shrink-0">{renderRunGuiTracker(notice.tracker)}</span>
      ) : null}
      <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">
        {notice.text}
      </span>
      {notice.count > 1 && (
        <span className="ua-run-gui-count shrink-0 rounded-full px-1.5 text-xs font-semibold">
          ×{notice.count}
        </span>
      )}
    </li>
  );

  /** Slot check, dupes and notices kept for one tracker. */
  const renderRunGuiTrackerCard = (card, { showTracker = true } = {}) => (
    <div key={card.key} className="space-y-2">
      {showTracker && renderRunGuiTracker(card.tracker)}
      {card.slot && renderRunGuiSlot(card.slot)}
      {card.dupe && renderRunGuiDupe(card.dupe)}
      {card.notices.length > 0 && (
        <ul>
          {card.notices.map((notice) =>
            renderRunGuiNotice({ ...notice, tracker: "" }),
          )}
        </ul>
      )}
    </div>
  );

  const runGuiCardSummary = (card) =>
    [
      card.slot && (card.slot.title || "Slot check"),
      card.dupe &&
        (card.dupe.trumpable
          ? "trumpable release"
          : `${card.dupe.entries.length} possible dupe${card.dupe.entries.length === 1 ? "" : "s"}`),
      card.notices.length &&
        `${card.notices.length} note${card.notices.length === 1 ? "" : "s"}`,
    ]
      .filter(Boolean)
      .join(" · ");

  const getLastTerminalLine = () => {
    const output = getTabRuntime(activeTabIdRef.current)?.output;
    const nodes = output ? Array.from(output.childNodes || []) : [];
    for (let index = nodes.length - 1; index >= 0; index -= 1) {
      const line = String(nodes[index].textContent || "").trim();
      if (line) return line.split("\n").pop().trim();
    }
    return "";
  };

  /**
   * The last lines printed before the current question. A free-text prompt
   * often refers to a list printed just before it, which the GUI would
   * otherwise not show.
   */
  const getRecentTerminalLines = (question, limit = 40) => {
    const output = getTabRuntime(activeTabIdRef.current)?.output;
    const nodes = output ? Array.from(output.childNodes || []) : [];
    const lines = [];
    for (
      let index = nodes.length - 1;
      index >= 0 && lines.length < limit;
      index -= 1
    ) {
      const nodeLines = String(nodes[index].textContent || "").split("\n");
      for (
        let line = nodeLines.length - 1;
        line >= 0 && lines.length < limit;
        line -= 1
      ) {
        const text = nodeLines[line].trimEnd();
        if (text.trim()) lines.unshift(text);
      }
    }
    // Drop the question itself and the input marker, which the card shows.
    const asked = String(question || "").trim();
    while (lines.length) {
      const last = lines[lines.length - 1].trim();
      if (last === ">" || last.startsWith("> ") || (asked && last === asked)) {
        lines.pop();
      } else {
        break;
      }
    }
    return lines;
  };

  const splitTrackers = (value) =>
    String(value || "")
      .split(",")
      .map((name) => name.trim())
      .filter(Boolean);

  /** Add ``flag value`` to the GUI answer, unless the flag is already there. */
  const insertRunGuiArg = (flag, value) => {
    const text = String(value || "");
    const quoted = /[\s"']/.test(text)
      ? `"${text.replace(/"/g, '\\"')}"`
      : text;
    setUserInput((current) => {
      const existing = String(current || "").trim();
      if (existing.split(/\s+/).includes(flag)) return current;
      const part = text ? `${flag} ${quoted}` : `${flag} `;
      return existing ? `${existing} ${part}` : part;
    });
    window.requestAnimationFrame(() => {
      const input = runGuiAnswerRef.current;
      if (!input) return;
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    });
  };

  /**
   * "Input args that need correction": the declined summary, what is missing,
   * quick corrections filled with the current values, and the corrections
   * already applied in earlier rounds.
   */
  const renderRunGuiEditArgsContext = (context, view, prompt, disabled) => {
    const confirm =
      view.lastConfirm && view.lastConfirm.item === prompt.item
        ? view.lastConfirm.context
        : null;
    const missing = view.attention
      .filter(
        (notice) => notice.group === "confirm" && notice.item === prompt.item,
      )
      .map((notice) => ({
        notice,
        flag: (String(notice.text).match(/--[a-z][a-z0-9-]*/i) || [])[0] || "",
      }));
    const values = Object.entries(context.values || {});
    const applied = String(context.applied || "").trim();
    return (
      <>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => sendInput(sessionId, "continue")}
            disabled={disabled}
            className="ua-run-gui-choice rounded-lg border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            Continue without changes
          </button>
          <button
            type="button"
            onClick={() => sendInput(sessionId, "skip")}
            disabled={disabled}
            title="Leave this release out; a queue moves on to the next item"
            className="ua-run-gui-choice ua-run-gui-skip rounded-lg border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            Skip this upload
          </button>
          <span className="ua-run-gui-muted text-xs">
            or add corrections below and send them.
          </span>
        </div>
        {confirm && (
          <div className="space-y-3">
            {renderRunGuiConfirmContext(confirm, [])}
          </div>
        )}
        {missing.length > 0 && (
          <div>
            {renderRunGuiSectionLabel("Missing")}
            <ul className="mt-1 space-y-1">
              {missing.map(({ notice, flag }) => (
                <li
                  key={notice.id}
                  className="ua-run-gui-attention-text flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
                >
                  <LucideIcon
                    name="triangle-alert"
                    className="h-3.5 w-3.5 shrink-0"
                  />
                  <span className="min-w-0 flex-1">{notice.text}</span>
                  {flag && (
                    <button
                      type="button"
                      onClick={() =>
                        insertRunGuiArg(flag, context.values?.[flag] || "")
                      }
                      disabled={disabled}
                      className="ua-run-gui-arg-chip rounded-md border px-2 py-0.5 font-mono text-xs disabled:opacity-50"
                    >
                      Add {flag}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {values.length > 0 && (
          <div>
            {renderRunGuiSectionLabel("Quick corrections")}
            <div className="mt-1 flex flex-wrap gap-1.5">
              {values.map(([flag, value]) => (
                <button
                  key={flag}
                  type="button"
                  onClick={() => insertRunGuiArg(flag, value)}
                  disabled={disabled}
                  title={
                    value
                      ? `Insert ${flag} with the current value, ready to edit`
                      : `Insert ${flag}`
                  }
                  className="ua-run-gui-arg-chip inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 text-xs disabled:opacity-50"
                >
                  <span className="font-mono font-semibold">{flag}</span>
                  <span className="ua-run-gui-muted truncate">
                    {value || "…"}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        {applied && (
          <div>
            {renderRunGuiSectionLabel("Applied so far")}
            <p className="ua-run-gui-release-name mt-1 break-all rounded-md px-2.5 py-1.5 font-mono text-xs">
              {applied}
            </p>
          </div>
        )}
      </>
    );
  };

  const renderRunGuiConfirmContext = (context, missing) => {
    const baseName = context.base_name || "";
    const names = Object.entries(context.release_names || {});
    const sameName = names
      .filter(([, name]) => name === baseName)
      .map(([tracker]) => tracker);
    const otherNames = names.filter(([, name]) => name !== baseName);
    return (
      <>
        {baseName && (
          <div>
            {renderRunGuiSectionLabel("Release name")}
            <p className="ua-run-gui-release-name mt-1 break-all rounded-md px-2.5 py-1.5 font-mono text-sm">
              {baseName}
            </p>
            {sameName.length > 0 && (
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <span className="ua-run-gui-muted text-xs">Used on</span>
                {renderRunGuiTrackerChips(sameName)}
              </div>
            )}
          </div>
        )}
        {otherNames.length > 0 && (
          <div>
            {renderRunGuiSectionLabel(
              baseName ? "Different name on" : "Release names",
            )}
            <dl className="mt-1 space-y-1.5">
              {otherNames.map(([tracker, name]) => (
                <div
                  key={tracker}
                  className="grid min-w-0 gap-x-3 gap-y-0.5 sm:grid-cols-[9rem_minmax(0,1fr)]"
                >
                  <dt className="min-w-0 text-sm">
                    {renderRunGuiTracker(tracker)}
                  </dt>
                  <dd className="ua-run-gui-release-name min-w-0 break-all rounded-md px-2 py-1 font-mono text-xs">
                    {name}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}
        {missing.length > 0 && (
          <div>
            {renderRunGuiSectionLabel("Missing")}
            <ul className="mt-1 space-y-1">
              {missing.map((notice) => (
                <li
                  key={notice.id}
                  className="ua-run-gui-attention-text flex gap-1.5 text-sm"
                >
                  <LucideIcon
                    name="triangle-alert"
                    className="mt-0.5 h-3.5 w-3.5 shrink-0"
                  />
                  {notice.text}
                </li>
              ))}
            </ul>
          </div>
        )}
      </>
    );
  };

  // Flags read after the release is confirmed, offered as toggles so a
  // forgotten one can be turned on without restarting. They are sent with
  // "yes" and ignored on "no".
  const renderRunGuiRunOptions = (options, changed, key, disabled) => {
    const update = (option, value) => {
      const next = { ...changed };
      if (value === option.value) delete next[option.key];
      else next[option.key] = value;
      setRunGuiRunOptions({ key, values: next });
    };
    return [
      ["media", "Also generate"],
      ["upload", "Upload options"],
    ].map(([group, label]) => {
      const items = options.filter((option) => option.group === group);
      if (!items.length) return null;
      return (
        <div key={group}>
          {renderRunGuiSectionLabel(label)}
          <div className="mt-1 flex flex-wrap gap-1.5">
            {items.map((option) => {
              const value =
                option.key in changed ? changed[option.key] : option.value;
              if (option.type === "choice") {
                const choices = Array.isArray(option.choices)
                  ? option.choices
                  : [];
                return (
                  <label
                    key={option.key}
                    className="ua-run-gui-choice flex items-center gap-2 rounded-lg border px-2.5 py-1 text-sm"
                  >
                    {option.label}
                    <select
                      value={value}
                      onChange={(event) => update(option, event.target.value)}
                      disabled={disabled}
                      className="ua-run-gui-input rounded border px-1.5 py-0.5 text-sm disabled:opacity-50"
                    >
                      {choices.map((choice) => (
                        <option key={choice} value={choice}>
                          {choice}
                        </option>
                      ))}
                    </select>
                  </label>
                );
              }
              return (
                <label
                  key={option.key}
                  title={option.locked || option.hint || undefined}
                  data-selected={value === true}
                  className="ua-run-gui-choice flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-1 text-sm has-[:disabled]:cursor-default has-[:disabled]:opacity-60"
                >
                  <input
                    type="checkbox"
                    checked={value === true}
                    onChange={() => update(option, value !== true)}
                    disabled={disabled || Boolean(option.locked)}
                    className="h-4 w-4 shrink-0"
                  />
                  {option.label}
                </label>
              );
            })}
          </div>
        </div>
      );
    });
  };

  const renderRunGuiDupeClearContext = (context) => {
    const groups = [
      [
        "No potential dupes found",
        splitTrackers(context.clear_trackers),
        "success",
      ],
      [
        "Possible dupes found",
        splitTrackers(context.dupe_trackers),
        "attention",
      ],
      [
        "Skipped by tracker rules",
        splitTrackers(context.skipped_trackers),
        "muted",
      ],
    ].filter(([, names]) => names.length);
    return groups.map(([label, names, tone]) => (
      <div key={label}>
        {renderRunGuiSectionLabel(label)}
        <div className="mt-1">{renderRunGuiTrackerChips(names, tone)}</div>
      </div>
    ));
  };

  // Other accepted answers of a free-text question, as ``[answer, label]``.
  const getRunGuiActions = (context) =>
    Array.isArray(context.actions)
      ? context.actions.filter(
          (action) => Array.isArray(action) && action.length === 2,
        )
      : [];

  const renderRunGuiActionButtons = (actions, answer, disabled) =>
    actions.length > 0 && (
      <div className="flex flex-wrap gap-2">
        {actions.map(([value, label]) => (
          <button
            key={value || "enter"}
            type="button"
            onClick={() => answer(value)}
            disabled={disabled}
            className="ua-run-gui-choice rounded-lg border px-3 py-1.5 text-sm disabled:opacity-50"
          >
            {label}
          </button>
        ))}
      </div>
    );

  // A question about one of a few known values (e.g. a release's metadata):
  // the values as a table with the one asked for highlighted.
  const renderRunGuiFieldContext = (context, answer, disabled) => {
    const rows =
      context.summary && typeof context.summary === "object"
        ? Object.entries(context.summary)
        : [];
    return (
      <>
        {rows.length > 0 && (
          <div>
            {context.title && renderRunGuiSectionLabel(context.title)}
            <dl className="mt-1 space-y-0.5">
              {rows.map(([label, value]) => (
                <div
                  key={label}
                  className="ua-run-gui-field-row grid min-w-0 gap-x-3 gap-y-0.5 rounded-md px-2 py-1 sm:grid-cols-[9rem_minmax(0,1fr)]"
                  data-focus={label === context.focus}
                >
                  <dt className="ua-run-gui-muted min-w-0 break-words text-xs font-semibold sm:pt-0.5">
                    {label}
                  </dt>
                  <dd className="min-w-0 break-words text-sm">
                    {value || (
                      <span className="ua-run-gui-attention-text">Missing</span>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}
        {context.hint && (
          <p className="ua-run-gui-muted text-xs">{context.hint}</p>
        )}
        {renderRunGuiActionButtons(getRunGuiActions(context), answer, disabled)}
      </>
    );
  };

  const renderRunGuiPrompt = (view) => {
    const prompt = view.prompt;
    // Every cli_ui prompt is announced. Without an announcement, rely on the
    // text heuristic only once the 2-second preview poll agrees, so ordinary
    // lines ending in ":" do not flash a prompt card.
    const awaiting = view.awaiting && isAwaitingTerminalInput;
    if (!isExecuting || (!prompt && !awaiting)) return null;
    const type =
      prompt?.type || (view.inputType === "yes_no" ? "yes_no" : "text");
    const question =
      prompt?.question ||
      getLastTerminalLine() ||
      "The upload is waiting for your answer.";
    const context = prompt?.context || {};
    const checkMessages = Array.isArray(context.check_messages)
      ? context.check_messages.filter(
          (message) => typeof message === "string" && message.trim(),
        )
      : [];
    // The demo has no session; its buttons look live but sendInput ignores them.
    const disabled =
      (!sessionId && !screenshotMode) ||
      isSendingInput ||
      Boolean(prompt?.answered);
    const trackerKey = `${prompt?.item}:${context.tracker}`;
    const slot = context.kind === "dupes" ? view.slots[trackerKey] : null;
    const dupe = context.kind === "dupes" ? view.dupes[trackerKey] : null;
    const missing =
      context.kind === "confirm"
        ? view.attention.filter(
            (notice) =>
              notice.group === "confirm" && notice.item === prompt.item,
          )
        : [];
    // A numbered list printed before a free-text question, sent as options.
    const options =
      context.kind === "options" && Array.isArray(context.options)
        ? context.options
        : [];
    const actions = context.kind === "options" ? getRunGuiActions(context) : [];
    const answer = (value) => sendInput(sessionId, value);
    let details = null;
    if (context.kind === "field") {
      details = renderRunGuiFieldContext(context, answer, disabled);
    } else if (context.kind === "confirm") {
      details = renderRunGuiConfirmContext(context, missing);
    } else if (context.kind === "edit_args") {
      details = renderRunGuiEditArgsContext(context, view, prompt, disabled);
    } else if (context.kind === "dupe_clear") {
      details = renderRunGuiDupeClearContext(context);
    } else if (slot || dupe) {
      details = (
        <>
          {slot && renderRunGuiSlot(slot)}
          {dupe && renderRunGuiDupe(dupe)}
        </>
      );
    }
    // Numbered options count from ``start`` (BDMV playlists start at 0).
    const optionStart = Number.parseInt(context.start ?? "1", 10) || 0;
    // Optional thumbnails (e.g. TMDb/IMDb posters), one per option.
    const optionImages = Array.isArray(context.images) ? context.images : [];
    // Optional per-option details: an ID line, a synopsis and a site link.
    const optionDetails = Array.isArray(context.details) ? context.details : [];
    const hasOptionImages = optionImages.some((image) =>
      /^https?:\/\//i.test(String(image || "")),
    );
    const selectionKey = `${sessionId}:${prompt?.item}:${prompt?.id}`;
    const selectedChoices =
      runGuiSelected.key === selectionKey ? runGuiSelected.values : [];
    const optionButtons =
      !details && (options.length || actions.length) ? (
        <div className="grid gap-1.5">
          {context.hint && (
            <p className="ua-run-gui-muted whitespace-pre-line text-xs leading-snug">
              {context.hint}
            </p>
          )}
          {options.map((option, index) => {
            const detail = optionDetails[index] || {};
            const link = /^https?:\/\//i.test(String(detail.link || ""))
              ? detail.link
              : "";
            return (
              // The card is not a single button: the site link must be its own
              // control, and a link inside a button is invalid HTML.
              <div
                key={`${index}-${option}`}
                className="ua-run-gui-choice flex min-w-0 items-stretch rounded-lg border text-sm"
              >
                <button
                  type="button"
                  onClick={() => answer(String(optionStart + index))}
                  disabled={disabled}
                  className={`flex min-w-0 flex-1 gap-3 px-3 py-2 text-left disabled:opacity-50 ${hasOptionImages ? "items-start" : "items-center"}`}
                >
                  <span className="ua-run-gui-count mt-0.5 shrink-0 rounded px-1.5 text-xs font-semibold">
                    {optionStart + index}
                  </span>
                  {hasOptionImages && (
                    <span className="ua-run-gui-option-thumb flex h-[4.5rem] w-12 shrink-0 items-center justify-center overflow-hidden rounded">
                      {/^https?:\/\//i.test(
                        String(optionImages[index] || ""),
                      ) ? (
                        <img
                          src={optionImages[index]}
                          alt=""
                          loading="lazy"
                          referrerPolicy="no-referrer"
                          onError={(event) => {
                            event.currentTarget.style.display = "none";
                          }}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <LucideIcon name="clapperboard" className="h-4 w-4" />
                      )}
                    </span>
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block break-words font-semibold">
                      {option}
                    </span>
                    {(detail.meta || detail.flag) && (
                      <span className="ua-run-gui-muted mt-0.5 flex min-w-0 items-center gap-1.5 break-words text-xs">
                        {/^[a-z]{2}$/.test(String(detail.flag || "")) && (
                          <img
                            src={`/static/img/flags/${detail.flag}.svg`}
                            alt=""
                            loading="lazy"
                            onError={(event) => {
                              event.currentTarget.style.display = "none";
                            }}
                            className="h-3 w-4 shrink-0 rounded-sm object-cover"
                          />
                        )}
                        <span className="min-w-0">{detail.meta}</span>
                      </span>
                    )}
                    {detail.text && (
                      <span
                        className="ua-run-gui-muted mt-1 block break-words text-xs leading-snug line-clamp-2"
                        title={detail.text}
                      >
                        {detail.text}
                      </span>
                    )}
                  </span>
                </button>
                {link && (
                  <a
                    href={link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ua-run-gui-link flex shrink-0 items-start gap-1 px-3 py-2 text-xs font-semibold"
                    title={`Open on ${detail.link_label || "the site"}`}
                  >
                    {detail.link_label || "Open"}
                    <LucideIcon name="external-link" className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            );
          })}
          {renderRunGuiActionButtons(actions, answer, disabled)}
        </div>
      ) : null;
    // A free-text question without its own list shows the output before it:
    // the list it refers to, or the text (e.g. a description) being decided on.
    const recent =
      !details && type === "text" && !options.length && !checkMessages.length
        ? getRecentTerminalLines(question)
        : [];
    const recentOutput = recent.length ? (
      <details open className="ua-run-gui-details">
        <summary className="ua-run-gui-muted cursor-pointer text-xs font-semibold">
          Output before this question
        </summary>
        <pre className="ua-run-gui-recent mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md p-2 font-mono text-xs">
          {recent.join("\n")}
        </pre>
      </details>
    ) : null;
    if (optionButtons || recentOutput) {
      details = (
        <>
          {optionButtons}
          {recentOutput}
        </>
      );
    }
    const runOptions =
      context.kind === "confirm" && Array.isArray(context.run_options)
        ? context.run_options.filter(
            (option) => option && typeof option.key === "string",
          )
        : [];
    const changedRunOptions =
      runGuiRunOptions.key === selectionKey ? runGuiRunOptions.values : {};
    const yesAnswer = Object.keys(changedRunOptions).length
      ? `yes ${JSON.stringify(changedRunOptions)}`
      : "yes";
    if (runOptions.length) {
      details = (
        <>
          {details}
          {renderRunGuiRunOptions(
            runOptions,
            changedRunOptions,
            selectionKey,
            disabled,
          )}
        </>
      );
    }

    return (
      <section
        className="ua-run-gui-prompt rounded-xl border-2 p-3"
        aria-live="polite"
        data-answered={Boolean(prompt?.answered)}
      >
        {/* Keep answers together, below the question on narrow screens. */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <LucideIcon
                name={prompt?.answered ? "loader-circle" : "circle-help"}
                className={`ua-run-gui-tone-icon h-4 w-4 ${prompt?.answered ? "animate-spin" : ""}`}
              />
              <p className="ua-run-gui-eyebrow text-xs font-semibold uppercase tracking-wide">
                {prompt?.answered ? "Answer sent" : "Your input is needed"}
              </p>
              {context.debug === true && (
                <span
                  className="ua-run-gui-chip ml-auto rounded-md px-2 py-0.5 text-xs"
                  data-tone="info"
                  hidden={Boolean(view.currentItem?.runOptions)}
                >
                  {/* Older logs lack the settings used by the persistent header badge. */}
                  Debug: tracker uploads are disabled
                </span>
              )}
              {view.dupeReview && (
                <span
                  className="ua-run-gui-muted ml-auto text-right text-xs"
                  role="status"
                  title={
                    view.dupeReview.checking
                      ? "More trackers are still being checked; the total may increase."
                      : undefined
                  }
                >
                  <span className="block whitespace-nowrap font-semibold">
                    Tracker review {view.dupeReview.index} of{" "}
                    {view.dupeReview.total}
                    {view.dupeReview.checking ? "+" : ""}
                  </span>
                  {view.dupeReview.checking > 0 && (
                    <span className="block">Still checking trackers…</span>
                  )}
                </span>
              )}
            </div>
            <p className="mt-1.5 break-words text-base font-semibold">
              {question}
            </p>
          </div>
          {type === "yes_no" && (
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => answer(yesAnswer)}
                disabled={disabled}
                className="ua-run-gui-answer flex items-center gap-1.5 rounded-lg px-4 py-2 font-medium disabled:opacity-50"
                data-variant="yes"
                data-default={prompt?.default === true}
                title={prompt?.default === true ? "Default answer" : undefined}
              >
                <LucideIcon name="check" className="h-4 w-4" />
                Yes
              </button>
              <button
                type="button"
                onClick={() => answer("no")}
                disabled={disabled}
                className="ua-run-gui-answer flex items-center gap-1.5 rounded-lg px-4 py-2 font-medium disabled:opacity-50"
                data-variant="no"
                data-default={prompt?.default === false}
                title={prompt?.default === false ? "Default answer" : undefined}
              >
                <LucideIcon name="x" className="h-4 w-4" />
                No
              </button>
            </div>
          )}
        </div>

        {checkMessages.length > 0 && (
          <div
            className="ua-run-gui-prompt-context mt-3 rounded-md p-3"
            data-testid="tracker-check-messages"
          >
            {renderRunGuiSectionLabel("Tracker check details")}
            <ul className="mt-1 space-y-1 text-sm">
              {checkMessages.map((message, index) => (
                <li key={index} className="whitespace-pre-wrap break-words">
                  {message}
                </li>
              ))}
            </ul>
          </div>
        )}

        {details && (
          <div className="ua-run-gui-prompt-context mt-3 space-y-3 rounded-md p-3">
            {details}
          </div>
        )}

        {type !== "yes_no" && (
          <div className="mt-3 flex flex-wrap gap-2">
            {type === "choice" && (
              <div className="grid w-full gap-1.5">
                {prompt.choices.map((choice, index) => (
                  <button
                    key={`${index}-${choice}`}
                    type="button"
                    onClick={() => answer(String(index + 1))}
                    disabled={disabled}
                    className="ua-run-gui-choice flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm disabled:opacity-50"
                  >
                    <span className="ua-run-gui-count shrink-0 rounded px-1.5 text-xs font-semibold">
                      {index + 1}
                    </span>
                    <span className="min-w-0 break-words">{choice}</span>
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => answer("")}
                  disabled={disabled}
                  className="ua-run-gui-muted justify-self-start text-xs underline disabled:opacity-50"
                >
                  Skip
                </button>
              </div>
            )}
            {type === "multi_choice" && (
              <div className="grid w-full gap-1.5">
                {prompt.choices.map((choice, index) => {
                  const number = String(index + 1);
                  const selected = selectedChoices.includes(number);
                  return (
                    <label
                      key={`${index}-${choice}`}
                      data-selected={selected}
                      className="ua-run-gui-choice flex min-w-0 cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm has-[:disabled]:cursor-default has-[:disabled]:opacity-50"
                    >
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() =>
                          setRunGuiSelected({
                            key: selectionKey,
                            values: selected
                              ? selectedChoices.filter(
                                  (value) => value !== number,
                                )
                              : [...selectedChoices, number],
                          })
                        }
                        disabled={disabled}
                        className="h-4 w-4 shrink-0"
                      />
                      <span className="min-w-0 break-words">{choice}</span>
                    </label>
                  );
                })}
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      answer(
                        [...selectedChoices]
                          .sort((a, b) => Number(a) - Number(b))
                          .join(","),
                      )
                    }
                    disabled={disabled || !selectedChoices.length}
                    className="ua-run-gui-answer rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50"
                    data-variant="send"
                  >
                    {selectedChoices.length
                      ? `Send ${selectedChoices.length} selected`
                      : "Select one or more"}
                  </button>
                  <button
                    type="button"
                    onClick={() => answer("")}
                    disabled={disabled}
                    className="ua-run-gui-muted text-xs underline disabled:opacity-50"
                  >
                    None of these
                  </button>
                </div>
              </div>
            )}
            {type === "text" && (
              <form
                className="flex w-full min-w-0 gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  answer(userInput);
                }}
              >
                <input
                  ref={runGuiAnswerRef}
                  value={userInput}
                  onChange={(event) => setUserInput(event.target.value)}
                  disabled={disabled}
                  placeholder={
                    context.kind === "field" && context.placeholder
                      ? context.placeholder
                      : context.kind === "edit_args"
                        ? "e.g. --tag NTb --tmdb movie/12345"
                        : prompt?.default && typeof prompt.default === "string"
                          ? `Leave empty for "${prompt.default}"`
                          : options.length || actions.length
                            ? "Or type your answer"
                            : "Type your answer"
                  }
                  aria-label="Answer"
                  className="ua-run-gui-input min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm"
                />
                <button
                  type="submit"
                  disabled={disabled}
                  className="ua-run-gui-answer rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50"
                  data-variant="send"
                >
                  Send
                </button>
              </form>
            )}
          </div>
        )}
      </section>
    );
  };

  const RUN_GUI_STAGE_STATUS_TEXT = {
    start: "running",
    waiting: "waiting for your answer",
    done: "done",
    fail: "stopped",
    skip: "skipped",
  };

  const renderRunGuiStages = (view, waitingForUser) => (
    <ol
      className="ua-run-gui-stages flex flex-wrap items-center gap-1.5"
      aria-label="Upload stages"
    >
      {view.stages.map((stage) => {
        // The running stage is paused while a prompt waits for the user.
        const status =
          stage.status === "start" && waitingForUser ? "waiting" : stage.status;
        const icon =
          {
            start: "loader-circle",
            waiting: "hourglass",
            done: "circle-check",
            fail: "circle-x",
            skip: "circle-minus",
          }[status] || stage.icon;
        return (
          <li
            key={stage.key}
            className="ua-run-gui-stage flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium"
            data-status={status || "idle"}
            title={`${stage.label}: ${RUN_GUI_STAGE_STATUS_TEXT[status] || "not reached"}`}
          >
            <LucideIcon
              name={icon}
              className={`h-3.5 w-3.5 ${status === "start" ? "animate-spin" : ""}`}
            />
            {stage.label}
          </li>
        );
      })}
    </ol>
  );

  const renderRunGuiResultRow = (entry, view) => {
    const status =
      RUN_GUI_TRACKER_STATUS[entry.status] || RUN_GUI_TRACKER_STATUS.pending;
    const card = view.trackerDetails[`${entry.item}:${entry.tracker}`];
    return (
      <li key={`${entry.item}-${entry.tracker}`} className="py-1.5 text-sm">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <span className="min-w-[8rem] flex-1">
            {renderRunGuiTracker(entry.tracker)}
          </span>
          <span
            className="ua-run-gui-status inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold"
            data-tone={status.tone}
          >
            <LucideIcon name={status.icon} className="h-3.5 w-3.5" />
            {status.label}
          </span>
          {entry.duration ? (
            <span className="ua-run-gui-muted text-xs tabular-nums">
              {entry.duration.toFixed(1)}s
            </span>
          ) : null}
          {entry.link &&
            renderRunGuiLink(
              entry.link,
              entry.torrentId ? `#${entry.torrentId}` : "Open",
              "text-xs",
            )}
        </div>
        {entry.message && (
          <p className="ua-run-gui-muted mt-0.5 break-words text-xs">
            {entry.message}
          </p>
        )}
        {card && (
          <details className="ua-run-gui-details mt-1">
            <summary className="ua-run-gui-muted cursor-pointer text-xs font-semibold">
              {runGuiCardSummary(card)}
            </summary>
            <div className="mt-2">
              {renderRunGuiTrackerCard(card, { showTracker: false })}
            </div>
          </details>
        )}
      </li>
    );
  };

  const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

  /** Overall outcome of one queue item, shown on its card header and stripe. */
  const runGuiItemOutcome = (group, view) => {
    const statuses = group.rows.map((entry) => entry.status);
    const has = (status) => statuses.includes(status);
    if (!view.finished && group.index === view.currentItem?.index) {
      return { tone: "info", icon: "loader-circle", label: "In progress" };
    }
    if (has("failed")) {
      return has("success")
        ? {
            tone: "attention",
            icon: "triangle-alert",
            label: "Partly uploaded",
          }
        : { tone: "error", icon: "circle-x", label: "Failed" };
    }
    if (has("success")) {
      return { tone: "success", icon: "circle-check", label: "Uploaded" };
    }
    if (has("pending")) {
      return { tone: "info", icon: "clock", label: "Queued" };
    }
    if (has("dupe"))
      return { tone: "muted", icon: "copy-check", label: "Dupe" };
    if (has("banned")) return { tone: "muted", icon: "ban", label: "Banned" };
    if (statuses.length) {
      return { tone: "muted", icon: "circle-minus", label: "Skipped" };
    }
    return { tone: "muted", icon: "circle-minus", label: "No upload" };
  };

  /** Identify a resolved personal release in the live header or queue results. */
  const renderRunGuiPersonalRelease = () => (
    <span
      className="ua-run-gui-chip inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium"
      data-tone="info"
    >
      <LucideIcon name="flag" className="ua-run-gui-tone-icon h-3 w-3" />
      Personal Release
    </span>
  );

  /** One queue item as a card: the release is the heading, trackers below it. */
  const renderRunGuiItemCard = (group, view) => {
    const outcome = runGuiItemOutcome(group, view);
    return (
      <section
        key={group.index}
        className="ua-run-gui-item rounded-md border"
        data-tone={outcome.tone}
      >
        {renderRunGuiWithCover(
          group,
          "py-2 pl-3",
          <>
            <header className="ua-run-gui-item-header flex min-w-0 flex-wrap items-center gap-2 px-3 py-2">
              <span className="ua-run-gui-item-index shrink-0 rounded px-1.5 text-xs font-semibold tabular-nums">
                {group.index}
              </span>
              <h4
                className="min-w-0 flex-1 truncate text-sm font-semibold"
                title={group.name || undefined}
              >
                {group.name || `Item ${group.index}`}
              </h4>
              {group.personalRelease && renderRunGuiPersonalRelease()}
              {group.runOptions?.debug && (
                <RunGuiDebugBadge options={group.runOptions} />
              )}
              <span className="ua-run-gui-status inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold">
                <LucideIcon
                  name={outcome.icon}
                  className={`h-3.5 w-3.5 ${outcome.icon === "loader-circle" ? "animate-spin" : ""}`}
                />
                {outcome.label}
              </span>
            </header>
            <div className="px-3 pb-2">
              {group.rows.length > 0 && (
                <ul className="ua-run-gui-divide divide-y">
                  {group.rows.map((entry) =>
                    renderRunGuiResultRow(entry, view),
                  )}
                </ul>
              )}
              {renderRunGuiItemNotes(group.notes)}
            </div>
          </>,
        )}
      </section>
    );
  };

  /** Put an item's cover beside its results when the run reported one. */
  const renderRunGuiWithCover = (group, coverClassName, content) =>
    group.artwork ? (
      <div className="flex min-w-0">
        <div className={`shrink-0 ${coverClassName}`}>
          <RunGuiItemCover
            src={group.artwork}
            category={group.category}
            name={group.name}
          />
        </div>
        <div className="min-w-0 flex-1">{content}</div>
      </div>
    ) : (
      content
    );

  /** Notes, errors and warnings kept for an item the queue has moved past. */
  const renderRunGuiItemNotes = (notes) => {
    const problems = notes.problems || [];
    const errors = problems.filter((notice) => notice.level === "error");
    const warnings = problems.filter((notice) => notice.level === "warning");
    const noteCount = notes.cards.length + notes.notices.length;
    if (!noteCount && !problems.length) return null;
    const tone = errors.length ? "error" : warnings.length ? "attention" : "";
    const summary = [
      errors.length && plural(errors.length, "error"),
      warnings.length && plural(warnings.length, "warning"),
      noteCount && plural(noteCount, "note"),
    ]
      .filter(Boolean)
      .join(" · ");
    return (
      <details className="ua-run-gui-details mt-1.5" data-tone={tone}>
        <summary className="ua-run-gui-muted cursor-pointer text-xs font-semibold">
          {tone && (
            <LucideIcon
              name={errors.length ? "circle-x" : "triangle-alert"}
              className="ua-run-gui-tone-icon mr-1 inline-block h-3.5 w-3.5 align-[-2px]"
            />
          )}
          {summary} from this item
        </summary>
        <div className="mt-2 space-y-3">
          {problems.length > 0 && (
            <ul>
              {[...errors, ...warnings].map((notice) => (
                <li
                  key={notice.id}
                  className="flex min-w-0 items-start gap-2 py-1 text-sm"
                  data-tone={notice.level === "error" ? "error" : "attention"}
                >
                  <LucideIcon
                    name={
                      notice.level === "error" ? "circle-x" : "triangle-alert"
                    }
                    className="ua-run-gui-tone-icon mt-0.5 h-3.5 w-3.5 shrink-0"
                  />
                  {notice.tracker ? (
                    <span className="shrink-0">
                      {renderRunGuiTracker(notice.tracker)}
                    </span>
                  ) : null}
                  <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">
                    {notice.text}
                  </span>
                  {notice.count > 1 && (
                    <span className="ua-run-gui-count shrink-0 rounded-full px-1.5 text-xs font-semibold">
                      ×{notice.count}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {notes.cards.map((card) => renderRunGuiTrackerCard(card))}
          {notes.notices.length > 0 && (
            <ul>{notes.notices.map(renderRunGuiNotice)}</ul>
          )}
        </div>
      </details>
    );
  };

  const renderRunGuiPanel = (toggleInStrip = false) => {
    const view = RunGui.selectRunGuiView(runGui);
    const prompt = view.prompt;
    const waitingForUser =
      isExecuting &&
      ((prompt && !prompt.answered) ||
        (view.awaiting && isAwaitingTerminalInput));
    const promptTracker =
      prompt?.context?.kind === "dupes" ? prompt.context.tracker : "";
    // The open prompt already shows its tracker's slot check and dupes.
    const attentionCards = view.attentionCards.filter(
      (card) => !(promptTracker && card.tracker === promptTracker),
    );
    // The confirmation and correction cards list what is missing themselves.
    const attentionNotices = view.attentionNotices.filter(
      (notice) =>
        !(
          ["confirm", "edit_args"].includes(prompt?.context?.kind) &&
          notice.group === "confirm"
        ),
    );
    const attentionCount = attentionCards.length + attentionNotices.length;
    const emptyNotes = { cards: [], notices: [], problems: [] };
    const resultGroups = view.multipleItems
      ? view.items.map((item) => ({
          index: item.index,
          name: item.name,
          personalRelease: item.personalRelease,
          runOptions: item.runOptions,
          category: item.runOptions?.category,
          artwork: item.artwork,
          rows: view.trackers.filter((entry) => entry.item === item.index),
          notes: view.itemNotes[item.index] || emptyNotes,
        }))
      : [
          {
            index: null,
            name: view.items[0]?.name,
            category: view.items[0]?.runOptions?.category,
            artwork: view.items[0]?.artwork,
            rows: view.trackers,
            notes: Object.values(view.itemNotes).reduce(
              (all, notes) => ({
                cards: [...all.cards, ...notes.cards],
                notices: [...all.notices, ...notes.notices],
                problems: [...all.problems, ...notes.problems],
              }),
              emptyNotes,
            ),
          },
        ];
    const visibleGroups = resultGroups.filter(
      (group) =>
        group.personalRelease ||
        group.runOptions?.debug ||
        group.rows.length ||
        group.notes.cards.length ||
        group.notes.notices.length ||
        group.notes.problems.length,
    );
    const hasAnything =
      view.hasStages ||
      view.trackers.length ||
      view.errors.length ||
      view.warnings.length ||
      attentionCount ||
      visibleGroups.length;
    const { counts } = view;
    const summary = [
      counts.success && { text: `${counts.success} uploaded` },
      counts.failed && { text: `${counts.failed} failed`, tone: "error" },
      counts.dupe && { text: plural(counts.dupe, "dupe") },
      counts.banned && { text: `${counts.banned} banned` },
      counts.skipped && { text: `${counts.skipped} skipped` },
      counts.pending && { text: `${counts.pending} queued` },
    ].filter(Boolean);
    // One failure in a mostly successful queue is a partial result, not a red
    // panel; the failed count itself stays red in the summary.
    const resultsTone = counts.failed
      ? counts.success
        ? "attention"
        : "error"
      : counts.success
        ? "success"
        : "info";
    const showItemHeader =
      view.currentItem &&
      (view.multipleItems ||
        view.currentItem.personalRelease ||
        view.currentItem.runOptions?.debug);

    return (
      <div className="ua-run-gui flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
        {/* The Terminal | GUI switch sits at the right of the stages bar. */}
        <div className="ua-run-gui-strip rounded-xl border px-3 py-2 shadow-sm">
          <div
            className={`flex min-w-0 flex-wrap gap-3 ${showItemHeader ? "items-center" : "items-start"}`}
          >
            <div
              className={`min-w-0 flex-1 ${showItemHeader ? "" : "flex min-h-[1.875rem] flex-col justify-center"} ${view.currentItem?.personalRelease && view.currentItem.runOptions?.debug ? "basis-full sm:basis-0" : ""}`}
            >
              {showItemHeader ? (
                <div className="ua-run-gui-muted flex min-w-0 flex-wrap items-center gap-1.5 text-xs">
                  {view.multipleItems && (
                    <>
                      <LucideIcon
                        name="file-stack"
                        className="h-3.5 w-3.5 shrink-0"
                      />
                      <span className="shrink-0 font-semibold">
                        Item {view.currentItem.index} of{" "}
                        {view.currentItem.total}
                      </span>
                    </>
                  )}
                  <span className="min-w-0 flex-1 truncate">
                    {view.currentItem.name}
                  </span>
                </div>
              ) : (
                renderRunGuiStages(view, waitingForUser)
              )}
            </div>
            {showItemHeader &&
              (view.currentItem.personalRelease ||
                view.currentItem.runOptions?.debug) && (
                <div className="flex flex-wrap items-center gap-1.5">
                  {view.currentItem.personalRelease &&
                    renderRunGuiPersonalRelease()}
                  {view.currentItem.runOptions?.debug && (
                    <RunGuiDebugBadge
                      key={`${activeTabId}:${view.currentItem.index}`}
                      options={view.currentItem.runOptions}
                    />
                  )}
                </div>
              )}
            {toggleInStrip && renderOutputModeToggle(true)}
          </div>
          {showItemHeader && (
            <div className="mt-1.5">
              {renderRunGuiStages(view, waitingForUser)}
            </div>
          )}
        </div>

        {renderRunGuiPrompt(view)}

        {!hasAnything && !prompt && (
          <div className="ua-run-gui-empty flex flex-col items-center justify-center gap-2 rounded-xl border p-8 shadow-sm text-center text-sm">
            {isExecuting ? (
              <>
                <SpinnerIcon />
                <p>Waiting for the upload to report its first step…</p>
              </>
            ) : (
              <>
                <LucideIcon name="layout-dashboard" className="h-6 w-6" />
                <p>
                  Start an upload to see its prompts, problems and results here.
                </p>
              </>
            )}
          </div>
        )}

        {attentionCount > 0 &&
          renderRunGuiBlock({
            tone: "attention",
            icon: "triangle-alert",
            title: "Needs attention",
            count: attentionCount,
            aside:
              view.multipleItems && view.currentItem ? (
                <span className="ua-run-gui-muted block truncate text-xs">
                  {view.currentItem.name}
                </span>
              ) : null,
            children: (
              <div className="space-y-3">
                {/* Decided trackers stay compact; the prompt shows the full detail. */}
                {attentionCards.map((card) => (
                  <div key={card.key}>
                    {renderRunGuiTracker(card.tracker)}
                    {card.slot || card.dupe ? (
                      <details className="ua-run-gui-details mt-1">
                        <summary className="ua-run-gui-muted cursor-pointer text-xs font-semibold">
                          {runGuiCardSummary(card)}
                        </summary>
                        <div className="mt-2">
                          {renderRunGuiTrackerCard(card, {
                            showTracker: false,
                          })}
                        </div>
                      </details>
                    ) : (
                      renderRunGuiTrackerCard(card, { showTracker: false })
                    )}
                  </div>
                ))}
                {attentionNotices.length > 0 && (
                  <ul>{attentionNotices.map(renderRunGuiNotice)}</ul>
                )}
              </div>
            ),
          })}

        {(view.errors.length > 0 || view.warnings.length > 0) &&
          renderRunGuiBlock({
            tone: view.errors.length ? "error" : "attention",
            icon: view.errors.length ? "circle-x" : "triangle-alert",
            title: view.errors.length ? "Errors" : "Warnings",
            count: view.errors.length || view.warnings.length,
            aside: (
              <button
                type="button"
                onClick={() => setOutputMode("terminal")}
                className="ua-run-gui-link inline-flex items-center gap-1 text-xs"
                title="Open the terminal for full details and tracebacks"
              >
                <LucideIcon name="square-terminal" className="h-3.5 w-3.5" />
                View in terminal
              </button>
            ),
            children: (
              <>
                {view.errors.length > 0 && (
                  <ul className="ua-run-gui-divide divide-y">
                    {view.errors.map(renderRunGuiNotice)}
                  </ul>
                )}
                {view.warnings.length > 0 &&
                  (view.errors.length > 0 ? (
                    <details className="mt-2">
                      <summary className="ua-run-gui-muted cursor-pointer text-xs font-semibold">
                        Warnings ({view.warnings.length})
                      </summary>
                      <ul className="mt-1">
                        {view.warnings.map(renderRunGuiNotice)}
                      </ul>
                    </details>
                  ) : (
                    <ul>{view.warnings.map(renderRunGuiNotice)}</ul>
                  ))}
              </>
            ),
          })}

        {(visibleGroups.length > 0 || view.requests.length > 0) &&
          renderRunGuiBlock({
            tone: resultsTone,
            icon: "cloud-upload",
            title: "Results",
            collapsed: runGuiResultsCollapsed,
            onToggle: () => setRunGuiResultsCollapsed((value) => !value),
            aside: summary.length ? (
              <span className="ua-run-gui-muted block truncate text-xs">
                {summary.map((part, index) => (
                  <React.Fragment key={part.text}>
                    {index > 0 && " · "}
                    <span
                      className={
                        part.tone ? "ua-run-gui-tone-text font-semibold" : ""
                      }
                      data-tone={part.tone}
                    >
                      {part.text}
                    </span>
                  </React.Fragment>
                ))}
              </span>
            ) : null,
            children: (
              <div className="space-y-3">
                {visibleGroups.map((group) =>
                  group.index === null ? (
                    <div key="all">
                      {renderRunGuiWithCover(
                        group,
                        "pr-3 pt-1.5",
                        <>
                          {group.rows.length > 0 && (
                            <ul className="ua-run-gui-divide divide-y">
                              {group.rows.map((entry) =>
                                renderRunGuiResultRow(entry, view),
                              )}
                            </ul>
                          )}
                          {renderRunGuiItemNotes(group.notes)}
                        </>,
                      )}
                    </div>
                  ) : (
                    renderRunGuiItemCard(group, view)
                  ),
                )}
                {view.requests.length > 0 && (
                  <div>
                    <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold">
                      <LucideIcon name="hand-coins" className="h-3.5 w-3.5" />
                      Requests you can fill
                    </p>
                    <ul className="ua-run-gui-divide divide-y">
                      {view.requests.map((request) => (
                        <li
                          key={request.key}
                          className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 py-1.5 text-sm"
                        >
                          <span className="shrink-0">
                            {renderRunGuiTracker(request.tracker)}
                          </span>
                          {renderRunGuiLink(
                            request.link,
                            request.name,
                            "min-w-0 flex-1",
                          )}
                          {request.reward && (
                            <span
                              className="ua-run-gui-status rounded-md px-2 py-0.5 text-xs font-semibold"
                              data-tone="success"
                            >
                              {request.reward}
                            </span>
                          )}
                          <span className="ua-run-gui-muted text-xs">
                            {[
                              request.exact ? "exact match" : "partial match",
                              request.status,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ),
          })}

        {view.finished && (
          <p
            className="ua-run-gui-muted flex items-center gap-1.5 text-xs"
            role="status"
          >
            <LucideIcon
              name={view.exitCode ? "circle-x" : "circle-check"}
              className="h-3.5 w-3.5"
            />
            {view.exitCode
              ? `Upload process exited with code ${view.exitCode}.`
              : !view.multipleItems && view.currentItem?.runOptions?.debug
                ? "Debug run finished."
                : "Upload process finished."}
          </p>
        )}
      </div>
    );
  };

  /**
   * Desktop file browser: header with search, the select-all bar and the tree.
   * It is shown either in the sidebar or in the larger modal, never both,
   * because the tree's scroll position and keyboard focus use one ref.
   */
  const renderFileBrowserBody = (inModal) => (
    <>
      <div className="ua-upload-panel-header p-4 border-b">
        <div className="flex items-center justify-between gap-2">
          <h2
            className={`text-lg font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex min-w-0 items-center gap-2 whitespace-nowrap`}
          >
            <LucideIcon name="folders" className="w-4 h-4" />
            File Browser
          </h2>
          <div className="flex shrink-0 items-center gap-0.5">
            <button
              type="button"
              onClick={() => setIsFileBrowserExpanded(!inModal)}
              aria-label={
                inModal ? "Return to sidebar" : "Open in a larger view"
              }
              title={inModal ? "Return to sidebar" : "Open in a larger view"}
              className={`rounded p-1 transition-colors ${isDarkMode ? "text-gray-400 hover:bg-gray-700 hover:text-gray-200" : "text-gray-500 hover:bg-gray-200 hover:text-gray-700"}`}
            >
              <LucideIcon
                name={inModal ? "minimize-2" : "maximize-2"}
                className="h-4 w-4"
              />
            </button>
            <button
              type="button"
              onClick={collapseFileBrowser}
              aria-label="Collapse all folders"
              title="Collapse all folders"
              className={`rounded p-1 transition-colors ${isDarkMode ? "text-gray-400 hover:bg-gray-700 hover:text-gray-200" : "text-gray-500 hover:bg-gray-200 hover:text-gray-700"}`}
            >
              <LucideIcon name="list-collapse" className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={refreshFileBrowser}
              disabled={fileBrowserRefreshing}
              aria-label="Refresh file browser"
              title="Refresh file browser"
              className={`rounded p-1 transition-colors disabled:cursor-wait disabled:opacity-60 ${isDarkMode ? "text-gray-400 hover:bg-gray-700 hover:text-gray-200" : "text-gray-500 hover:bg-gray-200 hover:text-gray-700"}`}
            >
              <LucideIcon
                name="refresh-cw"
                className={`h-4 w-4 ${fileBrowserRefreshing ? "animate-spin" : ""}`}
              />
            </button>
            {inModal && (
              <button
                type="button"
                onClick={() => setIsFileBrowserExpanded(false)}
                aria-label="Close"
                title="Close"
                className={`rounded p-1 transition-colors ${isDarkMode ? "text-gray-400 hover:bg-gray-700 hover:text-gray-200" : "text-gray-500 hover:bg-gray-200 hover:text-gray-700"}`}
              >
                <LucideIcon name="x" className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
        <div className="relative mt-2">
          <input
            type="text"
            aria-label="Search files and folders"
            value={fileBrowserSearch}
            onChange={(e) => handleFileBrowserSearch(e.target.value)}
            placeholder="Search files and folders..."
            className={`w-full pl-8 pr-8 py-1.5 text-sm rounded border ${
              isDarkMode
                ? "bg-gray-800 border-gray-600 text-gray-200 placeholder-gray-500"
                : "bg-white border-gray-300 text-gray-700 placeholder-gray-400 focus:border-blue-500"
            } focus:outline-none`}
          />
          <LucideIcon
            name="search"
            className={`absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 ${isDarkMode ? "text-gray-500" : "text-gray-400"}`}
          />
          {fileBrowserSearch && (
            <button
              type="button"
              aria-label="Clear file search"
              onClick={() => handleFileBrowserSearch("")}
              className={`absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
            >
              <LucideIcon name="x" className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
      {renderSelectAllBar()}
      <div
        ref={fileBrowserRef}
        onScroll={(event) => {
          if (fileBrowserRestoring) return;
          fileBrowserScrollTopRef.current = event.currentTarget.scrollTop;
          storage.set(
            FILE_BROWSER_SCROLL_KEY,
            String(fileBrowserScrollTopRef.current),
          );
        }}
        className={`${!inModal && hasDescFile && !descBrowserCollapsed ? "flex-1 max-h-[50%]" : "flex-1"} min-h-0 overflow-y-auto`}
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
                    Results limited to {fileBrowserSearchResults.count} items
                  </div>
                )}
              {renderSearchResults(fileBrowserSearchResults)}
            </>
          )
        ) : (
          renderFileTree(directories)
        )}
      </div>
    </>
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
            ? "ua-accent-tab-active border-t-2"
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
        className={`ua-upload-page flex flex-col h-screen ${isDarkMode ? "bg-gray-900" : "bg-gray-50"}`}
        data-mode={isDarkMode ? "dark" : "light"}
      >
        {screenshotMode && (
          <ScreenshotModeControls
            onPoster={(poster) =>
              setExecutionPreview((media) => ({ ...media, poster_url: poster }))
            }
            onBackdrop={(backdrop) =>
              setExecutionPreview((media) => ({
                ...media,
                backdrop_url: backdrop,
              }))
            }
          />
        )}
        {isHelpResourcesOpen && (
          <UploadHelpResourcesModal
            updateStatus={updateStatus}
            isCheckingForUpdates={isCheckingForUpdates}
            onCheckForUpdates={checkForUpdatesNow}
            onOpenChangelog={openChangelog}
            onClose={() => setIsHelpResourcesOpen(false)}
          />
        )}
        {isChangelogOpen && (
          <window.UAChangelogModal onClose={() => setIsChangelogOpen(false)} />
        )}
        {isUpdateStatusOpen && visibleUpdateStatus && (
          <window.UAUpdateStatusModal
            status={visibleUpdateStatus}
            onClose={() => setIsUpdateStatusOpen(false)}
            onDismiss={dismissCurrentUpdate}
            onOpenChangelog={openChangelog}
          />
        )}

        {/* Mobile Header */}
        <div
          className={`border-b flex-shrink-0 ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}
        >
          <div className="flex items-center justify-between px-4 py-3">
            <UploadWorkspaceBrand
              appBase={APP_BASE}
              isDarkMode={isDarkMode}
              isExecuting={isExecuting}
              compact
            />
            <div className="ml-2 flex shrink-0 items-center gap-1">
              <window.UAApiKeyAlerts
                trackers={trackers}
                appBase={APP_BASE}
                placement="header"
              />
              {renderUpdateButton()}
              {renderHelpButton()}
              {renderThemePalette()}
            </div>
          </div>
          <div className="px-4 pb-3">
            <WorkspaceSwitcher
              activeWorkspace="upload"
              appBase={APP_BASE}
              isDarkMode={isDarkMode}
              stretch
            />
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
                <div className="ua-upload-panel-header p-3 border-b flex-shrink-0">
                  <div className="flex items-center justify-between gap-2">
                    <h2
                      className={`text-base font-bold ${isDarkMode ? "text-white" : "text-gray-800"} flex items-center gap-2`}
                    >
                      <LucideIcon name="folders" className="w-4 h-4" />
                      File Browser
                    </h2>
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        onClick={collapseFileBrowser}
                        aria-label="Collapse all folders"
                        title="Collapse all folders"
                        className={`rounded p-1.5 transition-colors ${isDarkMode ? "text-gray-400 hover:bg-gray-700 hover:text-gray-200" : "text-gray-500 hover:bg-gray-200 hover:text-gray-700"}`}
                      >
                        <LucideIcon name="list-collapse" className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        onClick={refreshFileBrowser}
                        disabled={fileBrowserRefreshing}
                        aria-label="Refresh file browser"
                        title="Refresh file browser"
                        className={`rounded p-1.5 transition-colors disabled:cursor-wait disabled:opacity-60 ${isDarkMode ? "text-gray-400 hover:bg-gray-700 hover:text-gray-200" : "text-gray-500 hover:bg-gray-200 hover:text-gray-700"}`}
                      >
                        <LucideIcon
                          name="refresh-cw"
                          className={`h-4 w-4 ${fileBrowserRefreshing ? "animate-spin" : ""}`}
                        />
                      </button>
                    </div>
                  </div>
                  <div className="relative mt-2">
                    <input
                      type="text"
                      aria-label="Search files and folders"
                      value={fileBrowserSearch}
                      onChange={(e) => handleFileBrowserSearch(e.target.value)}
                      placeholder="Search files and folders..."
                      className={`w-full pl-8 pr-8 py-1.5 text-sm rounded border ${
                        isDarkMode
                          ? "bg-gray-800 border-gray-600 text-gray-200 placeholder-gray-500"
                          : "bg-white border-gray-300 text-gray-700 placeholder-gray-400 focus:border-blue-500"
                      } focus:outline-none`}
                    />
                    <LucideIcon
                      name="search"
                      className={`absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 ${isDarkMode ? "text-gray-500" : "text-gray-400"}`}
                    />
                    {fileBrowserSearch && (
                      <button
                        type="button"
                        aria-label="Clear file search"
                        onClick={() => handleFileBrowserSearch("")}
                        className={`absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded ${isDarkMode ? "hover:bg-gray-700 text-gray-400" : "hover:bg-gray-200 text-gray-500"}`}
                      >
                        <LucideIcon name="x" className="h-3.5 w-3.5" />
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
                      className={`ua-upload-panel-header p-3 border-t flex-shrink-0 ${!descBrowserCollapsed ? "border-b" : ""} ${descBrowserCollapsed ? "cursor-pointer" : ""}`}
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
                                <LucideIcon
                                  name="check"
                                  className="inline h-4 w-4"
                                />
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
                            <LucideIcon name="x" className="h-4 w-4" />
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
            {renderUploadTabs()}
            {/* Top controls */}
            {!isExecuting && !isTerminalView && (
              <div
                className={`ua-upload-workspace-main p-3 space-y-3 border-b flex-1 min-h-0 overflow-y-auto ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}
              >
                {renderSelectedPathOrQueue(true)}

                {/* Args input */}
                <input
                  type="text"
                  aria-label="Additional arguments"
                  value={customArgs}
                  onChange={(e) => setCustomArgs(e.target.value)}
                  placeholder="--tmdb movie/12345 --trackers passthepopcorn,aither"
                  className={`w-full px-3 py-2 text-sm border rounded-lg ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                  disabled={isExecuting}
                />
                {renderArgumentIssues()}
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
                        className={`w-full px-3 py-2 text-sm border rounded-lg ${
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
                    disabled={executeDisabled}
                    title={executeButtonTitle}
                    className="ua-accent-action flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-lg disabled:bg-gray-400 disabled:cursor-not-allowed font-medium"
                  >
                    <PlayIcon />
                    {getExecuteButtonLabel()}
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
              className={`ua-upload-output-panel ${isExecuting || isTerminalView ? "flex-1 p-3" : "flex-none p-2"} flex flex-col min-h-0 overflow-hidden ${isDarkMode ? "bg-gray-900" : "bg-gray-100"}`}
            >
              <div
                className={`flex items-center gap-2 ${isExecuting || isTerminalView ? "mb-2" : ""} flex-shrink-0`}
              >
                <span className={isDarkMode ? "text-white" : "text-gray-800"}>
                  <TerminalIcon />
                </span>
                <h3
                  className={`text-sm font-bold ${isDarkMode ? "text-white" : "text-gray-800"}`}
                >
                  Output
                </h3>
                {(isExecuting || isTerminalView) &&
                  renderOutputModeToggle(true)}
                {isExecuting && (
                  <span className="ml-auto inline-flex items-center gap-1 text-xs text-green-400 animate-pulse">
                    <LucideIcon name="circle" className="h-2.5 w-2.5" />
                    {activeTabScheduled ? "Scheduled" : "Running"}
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
                    {killButtonLabel}
                  </button>
                )}
                {!isExecuting && (
                  <button
                    onClick={() => setIsTerminalView((expanded) => !expanded)}
                    aria-expanded={isTerminalView}
                    title={
                      isTerminalView ? "Back to preparation" : "View output"
                    }
                    className={`ml-auto flex items-center gap-1 rounded px-2 py-1 text-xs ${isDarkMode ? "text-gray-300 hover:bg-gray-700" : "text-gray-600 hover:bg-gray-200"}`}
                  >
                    {isTerminalView ? (
                      <LucideIcon name="arrow-left" className="h-4 w-4" />
                    ) : (
                      <TerminalIcon />
                    )}
                    {isTerminalView ? "Back to preparation" : "View output"}
                  </button>
                )}
              </div>
              <div
                ref={attachRichOutputHost}
                id="rich-output"
                className={`min-h-0 rounded-lg overflow-auto p-2 border text-sm bg-black border-gray-700 text-white ${(isExecuting || isTerminalView) && !isGuiOutput ? "flex-1" : "hidden"}`}
              ></div>
              {(isExecuting || isTerminalView) &&
                isGuiOutput &&
                renderRunGuiPanel()}
              {isExecuting && !isGuiOutput && (
                <div
                  className={`mt-2 flex shrink-0 gap-2 ${isAwaitingTerminalInput ? "animate-pulse" : ""}`}
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
                    className={`min-w-0 flex-1 px-3 py-2 text-sm rounded-lg border transition-shadow ${isDarkMode ? "bg-gray-700 text-white" : "bg-white text-gray-900"} ${isAwaitingTerminalInput ? (isDarkMode ? "border-amber-400 shadow-[0_0_0_2px_rgba(251,191,36,0.18)]" : "border-amber-500 shadow-[0_0_0_2px_rgba(245,158,11,0.18)]") : isDarkMode ? "border-gray-600" : "border-gray-300"}`}
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
                {renderArgumentsPanel()}
              </div>
            ))}

          {/* Screenshot Review Panel */}
          {activePanel === "screenshots" && renderScreenshotsPanel()}
          {activePanel === "description" && renderDescriptionPanel()}
          {activePanel === "mediainfo" && renderMediaInfoPanel()}
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
            showScreenshotsButton &&
            navButton(
              "screenshots",
              <ScreenshotsIcon />,
              `Screens${executionScreenshots.length ? ` (${executionScreenshots.length})` : ""}`,
            )}
          {isExecuting &&
            navButton("description", <DescriptionIcon />, "Description")}
          {isExecuting &&
            showMediaInfoButton &&
            navButton("mediainfo", <MediaInfoIcon />, mediaInfoLabel)}
        </div>
      </div>
    );
  }

  const activeUploadPath =
    executionPreview?.path || selectedPath || selectedPaths[0]?.path || "";
  const desktopUploadStatusTitle = isAwaitingTerminalInput
    ? "Input required"
    : isExecuting
      ? activeTabScheduled
        ? "Upload scheduled"
        : "Upload running"
      : selectedPaths.length > 0 || selectedPath
        ? "Ready to upload"
        : "Ready";
  const desktopUploadStatusDetail = isExecuting
    ? activeUploadPath || "Upload Assistant is processing the current session."
    : selectedPaths.length > 1
      ? `${selectedPaths.length} items selected and ready to queue.`
      : selectedPaths.length === 1 || selectedPath
        ? "1 item selected. Review the options below, then execute the upload."
        : "Select a file or folder to begin.";

  // Desktop Layout
  return (
    <div
      className={`ua-upload-page flex h-screen ${isDarkMode ? "bg-gray-900" : "bg-gray-50"} overflow-hidden`}
      data-mode={isDarkMode ? "dark" : "light"}
    >
      {screenshotMode && (
        <ScreenshotModeControls
          onPoster={(poster) =>
            setExecutionPreview((media) => ({ ...media, poster_url: poster }))
          }
          onBackdrop={(backdrop) =>
            setExecutionPreview((media) => ({
              ...media,
              backdrop_url: backdrop,
            }))
          }
        />
      )}
      {isHelpResourcesOpen && (
        <UploadHelpResourcesModal
          updateStatus={updateStatus}
          isCheckingForUpdates={isCheckingForUpdates}
          onCheckForUpdates={checkForUpdatesNow}
          onOpenChangelog={openChangelog}
          onClose={() => setIsHelpResourcesOpen(false)}
        />
      )}
      {isChangelogOpen && (
        <window.UAChangelogModal onClose={() => setIsChangelogOpen(false)} />
      )}
      {isUpdateStatusOpen && visibleUpdateStatus && (
        <window.UAUpdateStatusModal
          status={visibleUpdateStatus}
          onClose={() => setIsUpdateStatusOpen(false)}
          onDismiss={dismissCurrentUpdate}
          onOpenChangelog={openChangelog}
        />
      )}

      <ApplicationRail
        trackers={trackers}
        activeWorkspace="upload"
        appBase={APP_BASE}
        appearanceControl={renderRailAppearance()}
        updateStatus={visibleUpdateStatus}
        onOpenUpdate={() =>
          visibleUpdateStatus ? setIsUpdateStatusOpen(true) : openChangelog()
        }
        onOpenHelp={() => setIsHelpResourcesOpen(true)}
        onLogout={handleLogout}
      />

      <div className="ua-upload-desktop-shell flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="ua-upload-context-header flex h-20 shrink-0 border-b">
          <div
            className="ua-upload-context-title flex shrink-0 items-center border-r px-5"
            style={{
              width: `${sidebarWidth}px`,
              minWidth: `${DEFAULT_LEFT_SIDEBAR_WIDTH}px`,
              maxWidth: "600px",
            }}
          >
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold uppercase tracking-widest opacity-60">
                Upload Assistant
              </p>
              <h1 className="mt-1 truncate text-lg font-bold">Upload</h1>
            </div>
          </div>
          <div className="ua-upload-context-resize-gutter shrink-0" />
          <div className="ua-upload-context-status flex min-w-0 flex-1 items-center gap-4 px-4 sm:px-6 lg:px-8">
            <div className="min-w-0 flex-1">
              <div className="flex min-w-0 items-center gap-2">
                <h2 className="truncate text-lg font-bold sm:text-xl">
                  {desktopUploadStatusTitle}
                </h2>
                {isExecuting && (
                  <span
                    className="ua-workspace-run-status shrink-0 rounded-full"
                    role="status"
                  >
                    <span
                      className="ua-workspace-run-dot animate-pulse"
                      aria-hidden="true"
                    ></span>
                    {activeTabScheduled ? "Scheduled" : "Running"}
                  </span>
                )}
              </div>
              <p
                className={`ua-upload-context-detail mt-0.5 truncate text-sm ${isExecuting && activeUploadPath ? "font-mono" : ""}`}
                title={
                  isExecuting && activeUploadPath
                    ? activeUploadPath
                    : desktopUploadStatusDetail
                }
              >
                {desktopUploadStatusDetail}
              </p>
            </div>
            {isExecuting && (
              <div className="flex shrink-0 items-center gap-2">
                {showScreenshotsButton && (
                  <button
                    onClick={() =>
                      setReviewPanelOpen("screenshots", !isScreenshotReviewOpen)
                    }
                    aria-pressed={isScreenshotReviewOpen}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${isScreenshotReviewOpen ? "ua-accent-action" : isDarkMode ? "bg-gray-700 hover:bg-gray-600 text-gray-100" : "bg-gray-100 hover:bg-gray-200 text-gray-700"}`}
                    title="Review generated screenshots"
                  >
                    <ScreenshotsIcon />
                    Screenshots
                    {executionScreenshots.length
                      ? ` (${executionScreenshots.length})`
                      : ""}
                  </button>
                )}
                <button
                  onClick={() =>
                    setReviewPanelOpen("description", !isDescriptionReviewOpen)
                  }
                  aria-pressed={isDescriptionReviewOpen}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${isDescriptionReviewOpen ? "ua-accent-action" : isDarkMode ? "bg-gray-700 hover:bg-gray-600 text-gray-100" : "bg-gray-100 hover:bg-gray-200 text-gray-700"}`}
                  title="Review and edit the base description"
                >
                  <DescriptionIcon />
                  Description
                </button>
                {showMediaInfoButton && (
                  <button
                    onClick={() =>
                      setReviewPanelOpen("mediainfo", !isMediaInfoOpen)
                    }
                    aria-pressed={isMediaInfoOpen}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${isMediaInfoOpen ? "ua-accent-action" : isDarkMode ? "bg-gray-700 hover:bg-gray-600 text-gray-100" : "bg-gray-100 hover:bg-gray-200 text-gray-700"}`}
                    title={`View the ${mediaInfoLabel} report`}
                  >
                    <MediaInfoIcon />
                    {mediaInfoLabel}
                  </button>
                )}
                <button
                  onClick={clearTerminal}
                  aria-label={
                    activeTabScheduled
                      ? "Cancel scheduled upload"
                      : "Kill process and clear terminal"
                  }
                  className="flex items-center gap-2 px-4 py-2 rounded-lg transition-colors bg-red-600 hover:bg-red-700 text-white"
                  title={
                    activeTabScheduled
                      ? "Cancel scheduled upload"
                      : "Kill process and clear terminal"
                  }
                >
                  <TrashIcon />
                  {killButtonLabel}
                </button>
              </div>
            )}
          </div>
        </header>

        <div className="ua-upload-desktop-body flex min-h-0 flex-1 overflow-hidden">
          {/* Left Sidebar - Resizable */}
          <div
            className={`ua-upload-panel ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"} border-r flex flex-col`}
            style={{
              width: `${sidebarWidth}px`,
              minWidth: `${DEFAULT_LEFT_SIDEBAR_WIDTH}px`,
              maxWidth: "600px",
            }}
          >
            {isExecuting ? (
              renderProgressWorkspace()
            ) : (
              <>
                {isFileBrowserExpanded ? (
                  <div
                    className={`flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center text-sm ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                  >
                    <LucideIcon name="maximize-2" className="h-5 w-5" />
                    <p>The file browser is open in a larger view.</p>
                    <button
                      type="button"
                      onClick={() => setIsFileBrowserExpanded(false)}
                      className={`rounded-md px-3 py-1.5 text-sm font-medium ${isDarkMode ? "bg-gray-700 text-gray-100 hover:bg-gray-600" : "bg-gray-100 text-gray-800 hover:bg-gray-200"}`}
                    >
                      Return to sidebar
                    </button>
                  </div>
                ) : (
                  renderFileBrowserBody(false)
                )}

                {/* Description File Browser - shown when --descfile is in args */}
                {hasDescFile && (
                  <>
                    <div
                      className={`ua-upload-panel-header p-4 border-t ${!descBrowserCollapsed ? "border-b" : ""} ${descBrowserCollapsed ? "cursor-pointer" : ""}`}
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
                                <LucideIcon
                                  name="check"
                                  className="inline h-4 w-4"
                                />
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
                            <LucideIcon name="x" className="h-4 w-4" />
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
                                <LucideIcon name="x" className="h-4 w-4" />
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
            className="ua-upload-resize-handle w-1 cursor-col-resize transition-colors"
            onMouseDown={startResizing}
            style={{ userSelect: "none" }}
          />

          {/* Main Content */}
          <div className="relative flex-1 flex flex-col min-w-0 overflow-hidden">
            {renderUploadTabs()}
            {/* Top Panel */}
            <div
              className={`ua-upload-workspace-main ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"} border-b p-4 ${isExecuting || isTerminalView ? "hidden" : "flex-1 min-h-0 overflow-y-auto"}`}
            >
              <div className="mx-auto max-w-6xl space-y-4">
                {!isExecuting && (
                  <>
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
                        aria-label="Additional arguments"
                        value={customArgs}
                        onChange={(e) => setCustomArgs(e.target.value)}
                        placeholder="--tmdb movie/12345 --trackers passthepopcorn,aither,ulcx --no-edition --no-tag"
                        className={`w-full px-3 py-2 border rounded-lg ${
                          isDarkMode
                            ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                            : "bg-white border-gray-300 text-gray-900"
                        }`}
                        disabled={isExecuting}
                      />
                      {renderArgumentIssues()}
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
                            <LucideIcon name="link" className="h-4 w-4" />
                            Description Link URL (pastebin, hastebin, etc.):
                          </label>
                          <input
                            type="url"
                            value={descLinkUrl}
                            onChange={(e) => updateDescLink(e.target.value)}
                            onFocus={() => setDescLinkFocused(true)}
                            onBlur={() => setDescLinkFocused(false)}
                            placeholder="https://pastebin.com/abc123"
                            className={`w-full px-3 py-2 border rounded-lg ${
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
                          <LucideIcon
                            name={descFileError ? "circle-x" : "triangle-alert"}
                            className={`h-4 w-4 ${
                              descFileError ? "text-red-500" : "text-yellow-500"
                            }`}
                          />
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
                        disabled={executeDisabled}
                        title={executeButtonTitle}
                        className="ua-accent-action flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-lg disabled:bg-gray-400 disabled:cursor-not-allowed font-medium text-lg"
                      >
                        <PlayIcon />
                        {getExecuteButtonLabel()}
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
              className={`ua-upload-output-panel ${isExecuting || isTerminalView ? "flex-1 p-4" : "flex-none p-2"} ${isDarkMode ? "bg-gray-900" : "bg-gray-100"} flex flex-col min-h-0 overflow-hidden`}
              style={
                isExecuting || isTerminalView
                  ? undefined
                  : { flex: "0 0 auto", minHeight: 0 }
              }
            >
              <div
                className={`max-w-6xl mx-auto w-full ${isExecuting || isTerminalView ? "flex-1" : "flex-none"} flex flex-col min-h-0`}
              >
                {!isExecuting && (
                  <div
                    className={`flex items-center gap-2 ${isTerminalView ? "mb-3" : ""} flex-shrink-0`}
                  >
                    <span
                      className={isDarkMode ? "text-white" : "text-gray-800"}
                    >
                      <TerminalIcon />
                    </span>
                    <h3
                      className={`text-lg font-bold ${isDarkMode ? "text-white" : "text-gray-800"}`}
                    >
                      Execution Output
                    </h3>
                    <button
                      onClick={() => setIsTerminalView((expanded) => !expanded)}
                      aria-expanded={isTerminalView}
                      title={
                        isTerminalView ? "Back to preparation" : "View output"
                      }
                      className={`ml-auto flex items-center gap-1.5 rounded px-3 py-1.5 text-sm ${isDarkMode ? "text-gray-300 hover:bg-gray-800" : "text-gray-600 hover:bg-gray-200"}`}
                    >
                      {isTerminalView ? (
                        <LucideIcon name="arrow-left" className="h-4 w-4" />
                      ) : isGuiOutput ? (
                        <LucideIcon
                          name="layout-dashboard"
                          className="h-4 w-4"
                        />
                      ) : (
                        <TerminalIcon />
                      )}
                      {isTerminalView ? "Back to preparation" : "View output"}
                    </button>
                  </div>
                )}
                <div
                  className={`relative min-h-0 flex-col ${isExecuting || isTerminalView ? "flex flex-1" : "hidden"}`}
                >
                  {/* In Terminal view the switch floats over the output instead of
                      taking a row; the GUI view shows it in its stages bar. */}
                  {!isGuiOutput && (
                    <div className="ua-run-gui-mode-overlay absolute right-2 top-2 z-10">
                      {renderOutputModeToggle(true)}
                    </div>
                  )}
                  {/* Rich HTML output (rendered from Rich export_html fragments) */}
                  <div
                    ref={attachRichOutputHost}
                    id="rich-output"
                    className={`min-h-0 rounded-lg overflow-auto p-3 border bg-black border-gray-700 text-white ${!isGuiOutput ? "flex-1" : "hidden"}`}
                  ></div>
                  {isGuiOutput && renderRunGuiPanel(true)}
                </div>
                {isExecuting && !isGuiOutput && (
                  <div
                    className={`mt-2 flex shrink-0 gap-2 ${isAwaitingTerminalInput ? "animate-pulse" : ""}`}
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
                      className={`min-w-0 flex-1 px-3 py-2 rounded-lg border transition-shadow ${isDarkMode ? "bg-gray-700 text-white" : "bg-white text-gray-900"} ${isAwaitingTerminalInput ? (isDarkMode ? "border-amber-400 shadow-[0_0_0_2px_rgba(251,191,36,0.18)]" : "border-amber-500 shadow-[0_0_0_2px_rgba(245,158,11,0.18)]") : isDarkMode ? "border-gray-600" : "border-gray-300"}`}
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
        </div>
      </div>

      {/* Right Resize Handle */}
      <div
        className="ua-upload-resize-handle w-1 cursor-col-resize transition-colors"
        onMouseDown={startResizingRight}
        style={{ userSelect: "none" }}
      />

      {/* Right Sidebar - Arguments / Execution Preview */}
      <div
        className={`ua-upload-panel ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"} border-l flex flex-col`}
        style={{
          width: `${rightSidebarWidth}px`,
          minWidth: `${DEFAULT_RIGHT_SIDEBAR_WIDTH}px`,
          maxWidth: "800px",
        }}
      >
        {isExecuting ? (
          isScreenshotReviewOpen && expandedReviewPanel !== "screenshots" ? (
            renderScreenshotsPanel()
          ) : isDescriptionReviewOpen &&
            expandedReviewPanel !== "description" ? (
            renderDescriptionPanel()
          ) : isMediaInfoOpen && expandedReviewPanel !== "mediainfo" ? (
            renderMediaInfoPanel()
          ) : (
            renderExecutionPreviewPanel()
          )
        ) : isArgumentsExpanded ? (
          <div
            className={`flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center text-sm ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
          >
            <LucideIcon name="maximize-2" className="h-5 w-5" />
            <p>The arguments are open in a larger view.</p>
            <button
              type="button"
              onClick={() => setIsArgumentsExpanded(false)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium ${isDarkMode ? "bg-gray-700 text-gray-100 hover:bg-gray-600" : "bg-gray-100 text-gray-800 hover:bg-gray-200"}`}
            >
              Return to sidebar
            </button>
          </div>
        ) : (
          renderArgumentsPanel()
        )}
      </div>
      {!isExecuting && !isMobile && isArgumentsExpanded && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4 sm:p-6"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setIsArgumentsExpanded(false);
            }
          }}
        >
          <section
            ref={argumentsModalRef}
            className={`ua-upload-panel flex h-[90vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border shadow-2xl ${isDarkMode ? "border-gray-700 bg-gray-800" : "border-gray-200 bg-white"}`}
            role="dialog"
            aria-modal="true"
            aria-label="Arguments"
            tabIndex="-1"
          >
            {renderArgumentsPanel({ inModal: true })}
            <footer
              className={`flex-none space-y-2 border-t px-4 py-3 ${isDarkMode ? "border-gray-700" : "border-gray-200"}`}
            >
              <label
                className={`block text-sm font-semibold ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}
              >
                Additional Arguments:
                <input
                  type="text"
                  value={customArgs}
                  onChange={(e) => setCustomArgs(e.target.value)}
                  spellCheck={false}
                  className={`mt-1 w-full rounded-lg border px-3 py-2 font-mono text-sm font-normal ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                />
              </label>
              {renderArgumentIssues()}
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => setIsArgumentsExpanded(false)}
                  className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-500"
                >
                  Done
                </button>
              </div>
            </footer>
          </section>
        </div>
      )}
      {!isExecuting && !isMobile && isFileBrowserExpanded && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4 sm:p-6"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setIsFileBrowserExpanded(false);
            }
          }}
        >
          <section
            ref={fileBrowserModalRef}
            className={`ua-upload-panel flex h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border shadow-2xl ${isDarkMode ? "border-gray-700 bg-gray-800" : "border-gray-200 bg-white"}`}
            role="dialog"
            aria-modal="true"
            aria-label="File browser"
            tabIndex="-1"
          >
            {renderFileBrowserBody(true)}
            <footer
              className={`flex flex-none items-center justify-between gap-3 border-t px-4 py-3 text-sm ${isDarkMode ? "border-gray-700 text-gray-300" : "border-gray-200 text-gray-600"}`}
            >
              <span>
                {selectedPaths.length
                  ? `${selectedPaths.length} selected`
                  : "Nothing selected yet"}
              </span>
              <button
                type="button"
                onClick={() => setIsFileBrowserExpanded(false)}
                className="rounded-md bg-blue-600 px-4 py-1.5 font-medium text-white hover:bg-blue-500"
              >
                Done
              </button>
            </footer>
          </section>
        </div>
      )}
      {isExecuting && !isMobile && expandedReviewPanel && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4 sm:p-6"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeReviewModal();
          }}
        >
          <section
            ref={reviewModalRef}
            className={`flex h-[90vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border shadow-2xl ${isDarkMode ? "border-gray-700 bg-gray-800" : "border-gray-200 bg-white"}`}
            role="dialog"
            aria-modal="true"
            aria-label={
              expandedReviewPanel === "screenshots"
                ? "Generated screenshots"
                : expandedReviewPanel === "description"
                  ? "Description review"
                  : mediaInfoLabel
            }
            tabIndex="-1"
          >
            {isAwaitingTerminalInput && (
              <div className="flex flex-none items-center justify-between gap-3 bg-amber-500 px-4 py-2 text-sm font-semibold text-gray-950">
                <span>The upload is waiting for your input.</span>
                <button
                  type="button"
                  onClick={closeReviewModal}
                  className="rounded-md bg-gray-950/15 px-3 py-1 text-xs font-semibold hover:bg-gray-950/25"
                >
                  Go to terminal
                </button>
              </div>
            )}
            <div className="min-h-0 flex-1">
              {expandedReviewPanel === "screenshots"
                ? renderScreenshotsPanel()
                : expandedReviewPanel === "description"
                  ? renderDescriptionPanel()
                  : renderMediaInfoPanel()}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

// Render the app
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<AudionutsUAGUI />);
