const { useEffect, useMemo, useRef, useState } = React;

const CONFIG_FIELD_RESET_EVENT = "ua-config-field-reset";

// Error boundary to catch render errors and prevent blank screen (e.g. on first run in Docker)
class ConfigErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return React.createElement(
        "div",
        {
          className:
            "min-h-screen flex flex-col items-center justify-center bg-gray-900 text-gray-100 p-8",
        },
        React.createElement(
          "h2",
          { className: "text-xl font-bold mb-4" },
          "Config loading failed",
        ),
        React.createElement(
          "p",
          { className: "text-gray-400 mb-4 max-w-md" },
          this.state.error?.message || "An unexpected error occurred",
        ),
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => window.location.reload(),
            className:
              "px-4 py-2 rounded-lg bg-purple-600 text-white hover:bg-purple-700",
          },
          "Reload page",
        ),
      );
    }
    return this.props.children;
  }
}

// Helper to lazily load a QR code library (UMD build) and return the module
function loadQRCodeLib() {
  return new Promise((resolve, reject) => {
    // If already present, resolve immediately
    if (window.qrcode || window.QRCode || window.qrcodeModule) {
      return resolve(window.qrcode || window.QRCode || window.qrcodeModule);
    }
    const script = document.createElement("script");
    script.src =
      "https://cdn.jsdelivr.net/npm/qrcode@1.5.1/build/qrcode.min.js";
    script.integrity =
      "sha384-HGmnkDZJy7mRkoARekrrj0VjEFSh9a0Z8qxGri/kTTAJkgR8hqD1lHsYSh3JdzRi";
    script.crossOrigin = "anonymous";
    script.async = true;
    script.onload = () =>
      resolve(window.qrcode || window.QRCode || window.qrcodeModule);
    script.onerror = () => reject(new Error("Failed to load qrcode library"));
    document.head.appendChild(script);
  });
}

// Info icon component (similar to lucide-react Info icon)
const InfoIcon = ({ className = "" }) => {
  return React.createElement(
    "svg",
    {
      xmlns: "http://www.w3.org/2000/svg",
      width: "16",
      height: "16",
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: "2",
      strokeLinecap: "round",
      strokeLinejoin: "round",
      className: className,
    },
    React.createElement("circle", { cx: "12", cy: "12", r: "10" }),
    React.createElement("path", { d: "M12 16v-4" }),
    React.createElement("path", { d: "M12 8h.01" }),
  );
};

// Tooltip component
const Tooltip = ({ children, content, className = "" }) => {
  const [isVisible, setIsVisible] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const triggerRef = useRef(null);
  const tooltipRef = useRef(null);

  const showTooltip = () => setIsVisible(true);
  const hideTooltip = () => setIsVisible(false);
  const toggleTooltip = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsVisible((v) => !v);
  };

  useEffect(() => {
    if (isVisible && triggerRef.current && tooltipRef.current) {
      const triggerRect = triggerRef.current.getBoundingClientRect();
      const tooltipRect = tooltipRef.current.getBoundingClientRect();
      const viewportWidth = window.innerWidth;

      let top = triggerRect.top - tooltipRect.height - 8;
      let left =
        triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;

      // Adjust if tooltip goes off screen
      if (top < 8) {
        top = triggerRect.bottom + 8;
      }

      if (left < 8) {
        left = 8;
      } else if (left + tooltipRect.width > viewportWidth - 8) {
        left = viewportWidth - tooltipRect.width - 8;
      }

      setPosition({ top, left });
    }
  }, [isVisible]);

  // Dismiss tooltip on outside tap for touch devices
  useEffect(() => {
    if (!isVisible) return;
    const handleOutsideClick = (e) => {
      if (triggerRef.current && !triggerRef.current.contains(e.target)) {
        setIsVisible(false);
      }
    };
    document.addEventListener("pointerdown", handleOutsideClick);
    return () =>
      document.removeEventListener("pointerdown", handleOutsideClick);
  }, [isVisible]);

  return React.createElement(
    "div",
    { className: "relative inline-block" },
    React.createElement(
      "div",
      {
        ref: triggerRef,
        onMouseEnter: showTooltip,
        onMouseLeave: hideTooltip,
        onClick: toggleTooltip,
        className: `cursor-help ${className}`,
      },
      children,
    ),
    isVisible &&
      React.createElement(
        "div",
        {
          ref: tooltipRef,
          className:
            "fixed z-50 px-3 py-2 text-sm text-white bg-gray-900 rounded-md shadow-lg pointer-events-none max-w-xs break-words",
          style: {
            top: `${position.top}px`,
            left: `${position.left}px`,
            whiteSpace: "pre-wrap",
          },
        },
        content,
        React.createElement("div", {
          className: "absolute w-2 h-2 bg-gray-900 transform rotate-45",
          style: {
            top:
              position.top >
              (triggerRef.current?.getBoundingClientRect().top || 0)
                ? "-4px"
                : "100%",
            left: "50%",
            marginLeft: "-4px",
          },
        }),
      ),
  );
};

const API_BASE = window.location.origin + "/api";
const APP_BASE = API_BASE.replace(/\/api$/, "");
const THEME_KEY = "ua_config_theme";
const storage = window.UAStorage;
const getStoredTheme = window.getUAStoredTheme;
const colorThemes = window.UAThemes || [];
const getStoredColorTheme = window.getUAStoredColorTheme;
const setColorTheme = window.setUAColorTheme;
const interfaceStyles = window.UAInterfaceStyles || [];
const getStoredInterfaceStyle = window.getUAStoredInterfaceStyle;
const setInterfaceStyle = window.setUAInterfaceStyle;

const WorkspaceSwitcher = ({ activeWorkspace, isDarkMode, stretch }) => {
  const workspaces = [
    { id: "upload", label: "Upload", href: `${APP_BASE}/` },
    { id: "config", label: "Configuration", href: `${APP_BASE}/config` },
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

const RailUploadIcon = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M12 16V4m0 0L7 9m5-5 5 5M5 20h14"
    />
  </svg>
);

const RailConfigIcon = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M12 15.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM19.4 15a1.7 1.7 0 00.34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0015 19.4a1.7 1.7 0 00-1 .6l-.04.08h-4l-.04-.08a1.7 1.7 0 00-1-.6 1.7 1.7 0 00-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 004.6 15a1.7 1.7 0 00-.6-1l-.08-.04v-4L4 9.92a1.7 1.7 0 00.6-1 1.7 1.7 0 00-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 009 4.6a1.7 1.7 0 001-.6l.04-.08h4l.04.08a1.7 1.7 0 001 .6 1.7 1.7 0 001.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0019.4 9c.08.38.3.73.6 1l.08.04v4L20 14.08a1.7 1.7 0 00-.6.92z"
    />
  </svg>
);

const RailHelpIcon = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M12 6.75c-2.5-1.5-5.5-1.5-8-.5v11c2.5-1 5.5-1 8 .5m0-11c2.5-1.5 5.5-1.5 8-.5v11c-2.5-1-5.5-1-8 .5m0-11v11"
    />
  </svg>
);

const RailUpdateIcon = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14"
    />
  </svg>
);

const RailPaletteIcon = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M12 3a9 9 0 100 18h1.4a1.6 1.6 0 001.1-2.73 1.6 1.6 0 011.1-2.73H18A3 3 0 0021 12a9 9 0 00-9-9zM7.5 10h.01M10 6.5h.01M15 7h.01M17 11h.01"
    />
  </svg>
);

const RailLogoutIcon = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M10 17l5-5-5-5m5 5H3m10-8h5a2 2 0 012 2v12a2 2 0 01-2 2h-5"
    />
  </svg>
);

function ConfigApplicationRail({
  colorTheme,
  onColorThemeChange,
  interfaceStyle,
  onInterfaceStyleChange,
  isDarkMode,
  onToggleMode,
  updateStatus,
  onOpenUpdate,
  onOpenHelp,
  onLogout,
}) {
  const [isAppearanceOpen, setIsAppearanceOpen] = useState(false);
  const appearanceRef = useRef(null);

  useEffect(() => {
    if (!isAppearanceOpen) return undefined;
    const closeWhenOutside = (event) => {
      if (!appearanceRef.current?.contains(event.target)) {
        setIsAppearanceOpen(false);
      }
    };
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setIsAppearanceOpen(false);
    };
    document.addEventListener("pointerdown", closeWhenOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeWhenOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isAppearanceOpen]);

  return (
    <aside
      className="ua-app-rail fixed inset-y-0 left-0 z-30 hidden w-20 flex-col border-r md:flex"
      aria-label="Application navigation"
    >
      <div className="ua-app-rail-brand flex h-20 shrink-0 flex-col items-center justify-center gap-1 border-b px-2">
        <img
          src={window.UA_LOGO_URL || "/static/img/logo.svg"}
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
        <a href={`${APP_BASE}/`} className="ua-app-rail-button rounded-lg">
          <RailUploadIcon />
          <span>Upload</span>
        </a>
        <a
          href={`${APP_BASE}/config`}
          className="ua-app-rail-button rounded-lg"
          data-active="true"
          aria-current="page"
          onClick={(event) => event.preventDefault()}
        >
          <RailConfigIcon />
          <span>Config</span>
        </a>
      </nav>

      <div className="min-h-4 flex-1"></div>

      <div className="ua-app-rail-footer grid shrink-0 gap-1 border-t p-2">
        {updateStatus?.update_available && (
          <button
            type="button"
            className="ua-app-rail-button ua-update-rail-button rounded-lg"
            onClick={onOpenUpdate}
            aria-haspopup="dialog"
            title={`${updateStatus.latest_version} is available`}
          >
            <RailUpdateIcon />
            <span>Update</span>
          </button>
        )}
        <button
          type="button"
          className="ua-app-rail-button rounded-lg"
          onClick={onOpenHelp}
          aria-haspopup="dialog"
        >
          <RailHelpIcon />
          <span>Help</span>
        </button>
        <div ref={appearanceRef} className="relative min-w-0 w-full">
          <button
            type="button"
            className="ua-app-rail-button rounded-lg"
            onClick={() => setIsAppearanceOpen((open) => !open)}
            aria-expanded={isAppearanceOpen}
          >
            <RailPaletteIcon />
            <span>Appearance</span>
          </button>
          {isAppearanceOpen && (
            <div className="ua-app-rail-popover absolute bottom-0 left-full z-[60] ml-2 w-64 rounded-xl border p-4 shadow-2xl">
              <h2 className="text-sm font-semibold">Appearance</h2>
              <label className="ua-app-rail-popover-label mt-3 block text-xs font-semibold">
                Color theme
              </label>
              <select
                aria-label="Color theme"
                value={colorTheme}
                onChange={(event) => {
                  onColorThemeChange(event);
                  setIsAppearanceOpen(false);
                }}
                className="ua-theme-picker mt-1 w-full rounded-lg px-3 py-2 text-sm"
              >
                {colorThemes.map((theme) => (
                  <option key={theme.id} value={theme.id}>
                    {theme.label}
                  </option>
                ))}
              </select>
              <label className="ua-app-rail-popover-label mt-3 block text-xs font-semibold">
                Corner style
              </label>
              <select
                aria-label="Corner style"
                value={interfaceStyle}
                onChange={(event) => {
                  onInterfaceStyleChange(event);
                  setIsAppearanceOpen(false);
                }}
                className="ua-theme-picker mt-1 w-full rounded-lg px-3 py-2 text-sm"
              >
                {interfaceStyles.map((style) => (
                  <option key={style.id} value={style.id}>
                    {style.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="ua-config-mode-button mt-3 flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm"
                onClick={onToggleMode}
              >
                <span>{isDarkMode ? "Dark mode" : "Light mode"}</span>
                <span aria-hidden="true">{isDarkMode ? "●" : "○"}</span>
              </button>
            </div>
          )}
        </div>
        <button
          type="button"
          className="ua-app-rail-button rounded-lg text-red-500"
          onClick={onLogout}
        >
          <RailLogoutIcon />
          <span>Log out</span>
        </button>
      </div>
    </aside>
  );
}

const DEFAULT_WORKFLOW_GROUPS = [
  {
    id: "general",
    label: "General",
    headings: ["MAIN SETTINGS", "LOGGING", "EXTERNAL TOOL PATHS"],
  },
  {
    id: "metadata",
    label: "Metadata Services",
    headings: [
      "METADATA API CREDENTIALS",
      "ARR INTEGRATION",
      "METADATA CACHING",
      "MUSIC METADATA",
      "TRACKER SEARCH AND IMPORT",
    ],
  },
  {
    id: "image-hosting",
    label: "Image Hosting",
    headings: ["IMAGE HOSTING"],
  },
  {
    id: "screenshots",
    label: "Screenshot Handling",
    headings: [
      "SCREENSHOT CAPTURE AND PROCESSING",
      "SCREENSHOT ENHANCEMENTS",
      "DISC MENU SCREENSHOTS",
      "XXX CONTACT SHEETS",
    ],
  },
  {
    id: "descriptions",
    label: "Description Formatting",
    headings: [
      "GENERAL DESCRIPTION SETTINGS",
      "PACK DESCRIPTIONS",
      "DESCRIPTION HEADERS AND OVERRIDES",
      "BLU-RAY SETTINGS",
      "AUDIO SPECTROGRAMS AND HDR PLOTS",
    ],
  },
  {
    id: "upload",
    label: "Upload Workflow",
    headings: ["TORRENT CREATION", "TRACKER CHECKS AND UPLOAD", "POST-UPLOAD"],
  },
];

const TRACKER_NAVIGATION_GROUPS = [
  { id: "default", label: "Default Trackers" },
  { id: "configured", label: "Configured Trackers" },
  { id: "available", label: "Available Trackers" },
];

const CONFIG_SECTION_LABELS = {
  IMAGES: "Tracker Database Icons",
  TRACKERS: "Trackers",
  TORRENT_CLIENTS: "Torrent Clients",
  USENET: "Usenet Uploads",
};

const CONFIG_BLOCK_LABELS = {
  qbittorrent: "qBittorrent",
  qbittorrent_searching: "qBittorrent (searching)",
  rtorrent: "rTorrent",
};

const TORRENT_CLIENT_TEMPLATE_LABELS = {
  qbittorrent: "qBittorrent",
  rtorrent: "rTorrent",
  deluge: "Deluge",
  transmission: "Transmission",
  watch: "Watch Folder",
};

const TORRENT_CLIENT_TYPE_LABELS = {
  qbit: "qBittorrent",
  rtorrent: "rTorrent",
  deluge: "Deluge",
  transmission: "Transmission",
  watch: "Watch Folder",
};

const METADATA_CACHE_SERVICE_LABELS = {
  tmdb: "TMDb",
  imdb: "IMDb",
  tvdb: "TVDb",
  tvmaze: "TVmaze",
  anilist: "AniList",
  douban: "Douban",
  thexem: "TheXEM",
  igdb: "IGDB",
  steam: "Steam",
  google_books: "Google Books",
  openlibrary: "OpenLibrary",
  myanonamouse: "MyAnonamouse",
  musicbrainz: "MusicBrainz",
  discogs: "Discogs",
};

const METADATA_CACHE_SERVICE_GROUPS = [
  {
    label: "Film, TV & Anime",
    services: ["tmdb", "imdb", "tvdb", "tvmaze", "anilist", "douban", "thexem"],
  },
  { label: "Games", services: ["igdb", "steam"] },
  {
    label: "Books, Audiobooks & Comics",
    services: ["google_books", "openlibrary", "myanonamouse"],
  },
  { label: "Music", services: ["musicbrainz", "discogs"] },
];

const CONFIG_HEADING_LABELS = {
  "MAIN SETTINGS": "Main Settings",
  LOGGING: "Logging",
  "METADATA API CREDENTIALS": "Metadata API Credentials",
  "ARR INTEGRATION": "ARR Integration",
  "EXTERNAL TOOL PATHS": "External Tool Paths",
  "CLIENT SELECTION": "Client Selection",
  "METADATA CACHING": "Metadata Caching",
  "MUSIC METADATA": "Music Metadata",
  "TRACKER SEARCH AND IMPORT": "Tracker Search and Import",
  "IMAGE HOSTING": "Image Hosting",
  "SCREENSHOT CAPTURE AND PROCESSING": "Screenshot Capture and Processing",
  "SCREENSHOT ENHANCEMENTS": "Screenshot Enhancements",
  "DISC MENU SCREENSHOTS": "Disc Menu Screenshots",
  "XXX CONTACT SHEETS": "XXX Contact Sheets",
  "GENERAL DESCRIPTION SETTINGS": "General Description Settings",
  "PACK DESCRIPTIONS": "Pack Descriptions",
  "DESCRIPTION HEADERS AND OVERRIDES": "Description Headers and Overrides",
  "BLU-RAY SETTINGS": "Blu-ray Settings",
  "AUDIO SPECTROGRAMS AND HDR PLOTS": "Audio Spectrograms and HDR Plots",
  "TORRENT CREATION": "Torrent Creation",
  "TRACKER CHECKS AND UPLOAD": "Tracker Checks and Upload",
  "POST-UPLOAD": "Post-Upload",
  "GENERAL SETTINGS": "General Settings",
  "SERVER CONNECTION": "Server Connection",
  "ARCHIVING AND PARITY": "Archiving and Parity",
  "UPLOADER AND VERIFICATION": "Uploader and Verification",
  "BINARY PATHS": "Binary Paths",
  "OUTPUT PATHS": "Output Paths",
};

const normalizeConfigHeading = (value) =>
  String(value || "")
    .trim()
    .toUpperCase();

const formatConfigHeading = (value) => {
  const normalized = normalizeConfigHeading(value);
  return CONFIG_HEADING_LABELS[normalized] || formatDisplayLabel(value);
};

const getDefaultItemGroupId = (item) => {
  const heading = normalizeConfigHeading(
    item?.subsection === true ? item.key : item?.subsection,
  );
  if (heading === "CLIENT SELECTION") return "torrent-clients";
  const group = DEFAULT_WORKFLOW_GROUPS.find((candidate) =>
    candidate.headings.includes(heading),
  );
  return group?.id || "other";
};

const getDefaultNavigationGroups = (section) => {
  if (!section || section.section !== "DEFAULT") return [];
  const presentGroupIds = new Set(
    (section.items || []).map(getDefaultItemGroupId),
  );
  const groups = DEFAULT_WORKFLOW_GROUPS.filter((group) =>
    presentGroupIds.has(group.id),
  );
  if (presentGroupIds.has("other")) {
    groups.push({ id: "other", label: "Other", headings: [] });
  }
  return groups;
};

const getConfigSectionLabel = (sectionName) =>
  CONFIG_SECTION_LABELS[String(sectionName || "").toUpperCase()] ||
  formatDisplayLabel(sectionName);

const getConfigBlockLabel = (blockName) =>
  CONFIG_BLOCK_LABELS[String(blockName || "").toLowerCase()] ||
  String(blockName || "");

// Local CSRF cache used by fallback `apiFetch` when `uaApiFetch` isn't present.
let localCsrf = null;
const loadLocalCsrf = async (force = false) => {
  if (localCsrf && !force) return;
  try {
    const r = await fetch(`${API_BASE}/csrf_token`, {
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

// Use shared loader when available; otherwise provide a no-op fallback.
const loadCsrfToken =
  (typeof window !== "undefined" && window.loadCsrfToken) || (async () => {});

const sensitiveKeyPattern =
  /(api|username|password|announce_url|rss_key|passkey|qui_proxy_url)/i;
const isSensitiveKey = (key) => sensitiveKeyPattern.test(key || "");
const isTorrentClientUserPass = (key, pathParts) =>
  pathParts.includes("TORRENT_CLIENTS") && /(user|pass)/i.test(key || "");
const isSensitiveKeyForPath = (key, pathParts) =>
  isSensitiveKey(key) || isTorrentClientUserPass(key, pathParts);
const isReadOnlyKeyForPath = (key, pathParts) =>
  pathParts.includes("TORRENT_CLIENTS") && key === "torrent_client";
const DISPLAY_LABEL_OVERRIDES = {
  multiScreens: "Multiple Screenshots",
  charLimit: "Character Limit",
  fileLimit: "File Limit",
  processLimit: "Process Limit",
  dalexni_api: "Dalexni API Key",
  imgbb_api: "ImgBB API Key",
  lensdump_api: "LensDump API Key",
  lostimg_api: "LostImg API Key",
  midnightscene_api_key: "MidnightScene API Key",
  onlyimage_api: "OnlyImage API Key",
  passtheima_ge_api: "PassTheImage API Key",
  ptscreens_api: "PTScreens API Key",
  seedpool_cdn_api: "Seedpool CDN API Key",
  sharex_api_key: "ShareX API Key",
  utppm_api: "UTPPM API Key",
  zipline_api_key: "Zipline API Key",
  dovi_tool_path: "Dolby Vision Tool Path",
  hdr10plus_tool_path: "HDR10+ Tool Path",
  "7z_path": "7-Zip Path",
  skip_auto_torrent_personalrelease: "Skip Auto Torrent Personal Release",
};
const DISPLAY_WORD_LABELS = {
  api: "API",
  bdinfo: "BDInfo",
  bhd: "BHD",
  bluray: "Blu-ray",
  btn: "BTN",
  cdn: "CDN",
  cbr: "CBR",
  cbz: "CBZ",
  desc: "Description",
  dir: "Directory",
  discogs: "Discogs",
  dvd: "DVD",
  ffmpeg: "FFmpeg",
  ffprobe: "FFprobe",
  hdr: "HDR",
  id: "ID",
  ids: "IDs",
  igdb: "IGDB",
  imdb: "IMDb",
  imgbb: "ImgBB",
  img: "Image",
  libplacebo: "libplacebo",
  mal: "MAL",
  mam: "MAM",
  mediainfo: "MediaInfo",
  mkbrr: "mkbrr",
  musicbrainz: "MusicBrainz",
  myanonamouse: "MyAnonamouse",
  nntp: "NNTP",
  nyuu: "Nyuu",
  nzb: "NZB",
  par: "PAR",
  par2: "PAR2",
  pesto: "pesto",
  predb: "PreDB",
  ptgen: "PTGen",
  qui: "QUI",
  rar: "RAR",
  rpc: "RPC",
  rss: "RSS",
  rtorrent: "rTorrent",
  sdr: "SDR",
  sfx: "SFX",
  sharex: "ShareX",
  ssl: "SSL",
  tmp: "Temporary",
  tmdb: "TMDb",
  ttl: "TTL",
  tvdb: "TVDb",
  tvmaze: "TVmaze",
  unit3d: "UNIT3D",
  unrar: "UnRAR",
  url: "URL",
  urls: "URLs",
  usenet: "Usenet",
  webp: "WebP",
  xxx: "XXX",
};
const formatDisplayLabel = (key) => {
  if (!key) return key;
  if (DISPLAY_LABEL_OVERRIDES[key]) return DISPLAY_LABEL_OVERRIDES[key];
  return String(key)
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .split("_")
    .map((word) => {
      const normalized = word.toLowerCase();
      return (
        DISPLAY_WORD_LABELS[normalized] ||
        word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
      );
    })
    .join(" ");
};

const formatConfigFieldLabel = (key, pathParts = []) => {
  if (pathParts[0] === "IMAGES") {
    const databaseImageLabels = {
      imdb_75: "IMDb Image URL",
      tmdb_75: "TMDb Image URL",
      tvdb_75: "TVDb Image URL",
      tvmaze_75: "TVmaze Image URL",
      mal_75: "MyAnimeList Image URL",
    };
    if (databaseImageLabels[key]) return databaseImageLabels[key];
  }
  if (pathParts.includes("metadata_cache_services")) {
    const serviceFieldLabels = {
      enabled: "Caching enabled",
      ttl_hours: "Cache lifetime (hours)",
      localized_ttl_hours: "Localized data lifetime (hours)",
    };
    if (serviceFieldLabels[key]) return serviceFieldLabels[key];
  }
  if (pathParts.includes("TORRENT_CLIENTS")) {
    const torrentClientFieldLabels = {
      qui_proxy_url: "QUI Proxy URL",
      qbit_url: "qBittorrent URL",
      qbit_port: "qBittorrent Port",
      qbit_user: "qBittorrent Username",
      qbit_pass: "qBittorrent Password",
      qbit_api_key: "qBittorrent API Key",
      qbit_tag: "qBittorrent Tag",
      qbit_cat: "qBittorrent Category",
      qbit_cross_tag: "Cross-Seed Tag",
      qbit_cross_cat: "Cross-Seed Category",
      rtorrent_url: "rTorrent URL",
      rtorrent_label: "rTorrent Label",
      deluge_url: "Deluge URL",
      deluge_port: "Deluge Port",
      deluge_user: "Deluge Username",
      deluge_pass: "Deluge Password",
      transmission_protocol: "Transmission Protocol",
      transmission_username: "Transmission Username",
      transmission_password: "Transmission Password",
      transmission_host: "Transmission Host",
      transmission_port: "Transmission Port",
      transmission_path: "Transmission RPC Path",
      transmission_label: "Transmission Label",
      torrent_storage_dir: "Torrent Storage Directory",
      super_seed_trackers: "Super-Seed Trackers",
      use_tracker_as_tag: "Use Tracker as Tag",
      linked_folder: "Linked Folders",
      local_path: "Local Paths",
      remote_path: "Remote Paths",
      watch_folder: "Watch Folder",
    };
    if (torrentClientFieldLabels[key]) return torrentClientFieldLabels[key];
  }
  if (pathParts.includes("TRACKERS")) {
    const trackerFieldLabels = {
      ApiUser: "API User",
      api_key: "API Key",
      api_url: "API URL",
      api_upload: "API Upload",
      announce_url: "Announce URL",
      my_announce_url: "Personal Announce URL",
      bhd_rss_key: "BHD RSS Key",
      bioma_api_key: "Bioma API Key",
      ptgen_api: "PTGen API Key",
      use_for_search: "Use for Search",
      link_dir_name: "Link Directory Name",
      doubleup: "Double Upload",
      modq: "Moderator Queue",
      allow_ext_subtitles: "Allow External Subtitles",
      full_mediainfo: "Full MediaInfo",
      use_metadata_name: "Use Metadata Name",
      use_spanish_title: "Use Spanish Title",
      use_german_title: "Use German Title",
      use_italian_title: "Use Italian Title",
      add_web_source_to_desc: "Add Web Source to Description",
      multiScreens: "Multiple Screenshots",
      charLimit: "Character Limit",
      fileLimit: "File Limit",
      processLimit: "Process Limit",
      add_bluray_link: "Add Blu-ray Link",
      use_bluray_images: "Use Blu-ray Images",
      bluray_image_size: "Blu-ray Image Size",
      add_audio_spectrogram: "Add Audio Spectrogram",
      audio_spectrogram_header: "Audio Spectrogram Header",
      dynamic_hdr_plot_header: "Dynamic HDR Plot Header",
      add_dynamic_hdr_plot: "Add Dynamic HDR Plot",
      inject_delay: "Injection Delay",
      daily_api_hit_limit: "Daily API Request Limit",
      image_count: "Image Count",
      user_id: "User ID",
    };
    if (trackerFieldLabels[key]) return trackerFieldLabels[key];
  }
  return formatDisplayLabel(key);
};

const imageHostApiKeys = {
  imgbb: ["imgbb_api"],
  lensdump: ["lensdump_api"],
  lostimg: ["lostimg_api"],
  ptscreens: ["ptscreens_api"],
  onlyimage: ["onlyimage_api"],
  dalexni: ["dalexni_api"],
  passtheimage: ["passtheima_ge_api"],
  zipline: ["zipline_url", "zipline_api_key"],
  midnightscene: ["midnightscene_api_key"],
  seedpool_cdn: ["seedpool_cdn_api"],
  sharex: ["sharex_url", "sharex_api_key"],
  utppm: ["utppm_api"],
};

const IMAGE_HOST_LABELS = {
  dalexni: "Dalexni",
  imgbb: "ImgBB",
  imgbox: "Imgbox",
  lensdump: "LensDump",
  lostimg: "LostImg",
  midnightscene: "MidnightScene",
  onlyimage: "OnlyImage",
  passtheimage: "PassTheImage",
  pixhost: "Pixhost",
  ptscreens: "PTScreens",
  seedpool_cdn: "Seedpool CDN",
  sharex: "ShareX",
  utppm: "UTPPM",
  zipline: "Zipline",
};

const trackerDefaultOverrideKeys = new Set([
  "add_audio_spectrogram",
  "add_bluray_link",
  "add_dynamic_hdr_plot",
  "add_logo",
  "audio_spectrogram_header",
  "bluray_image_size",
  "charLimit",
  "custom_description_header",
  "custom_footer",
  "custom_header",
  "custom_signature",
  "disc_menu_header",
  "dynamic_hdr_plot_header",
  "episode_overview",
  "fileLimit",
  "inject_delay",
  "logo_size",
  "mediainfo_header",
  "multiScreens",
  "pack_thumb_size",
  "processLimit",
  "screens_per_row",
  "screenshot_header",
  "thumbnail_size",
  "tonemapped_header",
  "use_bluray_images",
  "user_description",
]);

// Mapping from tracker acronyms to full names
const trackerNameMap = {
  AITHER: "Aither",
  ALPHARATIO: "Alpharatio",
  AMIGOSSHARE: "Amigos-Share",
  ANTHELION: "Anthelion",
  ASIANCINEMA: "AsianCinema",
  AVISTAZ: "AvistaZ",
  BEYONDHD: "Beyond-HD",
  BITHDTV: "BitHDTV",
  BITPORN: "BitPorn",
  BLUTOPIA: "Blutopia",
  BJSHARE: "BrasilJapão-Share",
  BRASILTRACKER: "BrasilTracker",
  CAPYBARABR: "CapybaraBR",
  CINEMAZ: "CinemaZ",
  CINEMATIK: "Cinematik",
  CURUPIRA: "Curupira",
  DARKPEERS: "DarkPeers",
  DESITORRENTS: "DesiTorrents",
  DIGITALCORE: "DigitalCore",
  DREADVAULT: "DreadVault",
  DRUNKENSLUG: "DrunkenSlug",
  EMUWAREZ: "Emuwarez",
  FILELIST: "FileList",
  FLOOD: "Flood",
  FUNFILE: "FunFile",
  GREATPOSTERWALL: "GreatPosterWall",
  HAWKEUNO: "hawke-uno",
  HDBITS: "HDBits",
  HDSPACE: "HD-Space",
  HDTORRENTS: "HD-Torrents",
  HOMIEHELPDESK: "HomieHelpDesk",
  IMMORTALSEED: "ImmortalSeed",
  INFINITYHD: "InfinityHD",
  ITATORRENTS: "ItaTorrents",
  IPTORRENTS: "IPTorrents",
  LASTDIGITALUNDERGROUND: "LastDigitalUnderground",
  LAJIDUI: "Lajidui",
  LEMONHD: "LemonHD",
  LATTEAM: "Lat-Team",
  LOCADORA: "Locadora",
  LONGPT: "LongPT",
  LST: "LST",
  LUMINARR: "Luminarr",
  MAKINGOFF: "MakingOff",
  MIDNIGHTSCENE: "MidnightScene",
  MTEAM: "MTeam",
  NEBULANCE: "Nebulance",
  NORDICQUALITY: "NordicQuality",
  NZBGEEK: "NZBGeek",
  OLDTOONSWORLD: "OldToonsWorld",
  ONLYENCODES: "OnlyEncodes+",
  PASSTHEPOPCORN: "PassThePopcorn",
  PEERGARDEN: "PeerGarden",
  POLISHTORRENT: "PolishTorrent",
  PORTUGAS: "Portugas",
  PRIVATEHD: "PrivateHD",
  PTCAFE: "PTCafe",
  PTERCLUB: "PTerClub",
  PTFANS: "PTFans",
  PTGTK: "PTGTK",
  PTSKIT: "PTSKIT",
  PTZONE: "PTZone",
  RACING4EVERYONE: "Racing4Everyone",
  RAILGUNPT: "RailgunPT",
  RASTASTUGAN: "Rastastugan",
  REELFLIX: "ReelFLiX",
  RETROFLIX: "RetroFlix",
  RETROMOVIESCLUB: "RetroMoviesClub",
  ROCKETHD: "RocketHD",
  SAMARITANO: "Samaritano",
  SEEDPOOL: "Seedpool",
  SHAREISLAND: "ShareIsland",
  SKIPTHECOMMERCIALS: "SkipTheCommercials",
  SPEEDAPP: "SpeedApp",
  SWARMAZON: "Swarmazon",
  THELEACHZONE: "TheLeachZone",
  THEOLDSCHOOL: "TheOldSchool",
  TOTHEGLORY: "ToTheGlory",
  TORRENTHR: "TorrentHR",
  TORRENTEROS: "Torrenteros",
  TORRENTLEECH: "TorrentLeech",
  TVCHAOSUK: "TVChaosUK",
  ULCX: "ULCX",
  SUIO: "Suio",
  UTOPIA: "Utopia",
  XINGYUNGEPT: "XingyungePT",
  YUSCENE: "YUSCENE",
  ZENITH: "Zenith",
  "1PTBA": "1PTBA",
};

const getTrackerDisplayName = (acronym) => {
  return trackerNameMap[acronym.toUpperCase()] || acronym;
};

const getImageHostForApiKey = (key) => {
  if (!key) {
    return null;
  }
  const normalizedKey = String(key);
  for (const [host, keys] of Object.entries(imageHostApiKeys)) {
    if (keys.includes(normalizedKey)) {
      return host;
    }
  }
  return null;
};

const getImageHostOptions = (item, allHosts, usedHosts) => {
  if (!item || !item.key || !item.key.startsWith("img_host_")) {
    return [];
  }
  if (!allHosts.length) {
    return [];
  }
  const currentValue = String(item.value || "")
    .trim()
    .toLowerCase();
  return allHosts.filter((host) => {
    const normalizedHost = String(host).trim().toLowerCase();
    return !usedHosts.has(normalizedHost) || currentValue === normalizedHost;
  });
};

const getAvailableTrackers = (item) => {
  if (!item || !item.help || !item.help.length) {
    return [];
  }
  const helpLine = item.help.find((line) =>
    line.toLowerCase().includes("available tracker"),
  );
  if (!helpLine) {
    return [];
  }
  const parts = helpLine.split(":");
  if (parts.length < 2) {
    return [];
  }
  return parts[1]
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
};

const statusClassFor = (type, isDarkMode) => {
  if (type === "success") {
    return isDarkMode ? "text-green-400" : "text-green-600";
  }
  if (type === "error") {
    return isDarkMode ? "text-red-400" : "text-red-500";
  }
  if (type === "warn") {
    return isDarkMode ? "text-yellow-400" : "text-yellow-600";
  }
  return isDarkMode ? "text-gray-400" : "text-gray-500";
};

// NumberInput component - styled number input using browser's built-in controls
const NumberInput = ({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  className = "",
  isDarkMode = false,
}) => {
  const currentValue =
    value === null || value === undefined || value === "" ? min : Number(value);

  const handleInputChange = (e) => {
    const inputValue = e.target.value;
    if (inputValue === "") {
      onChange(min);
    } else {
      const numValue = Number(inputValue);
      if (!isNaN(numValue)) {
        onChange(Math.max(min, Math.min(max, numValue)));
      }
    }
  };

  const inputClass = isDarkMode
    ? "px-3 py-2 border border-gray-700 bg-gray-900 text-gray-100 rounded-md focus:ring-2 focus:ring-purple-500 focus:border-transparent"
    : "px-3 py-2 border border-gray-300 bg-white text-gray-800 rounded-md focus:ring-2 focus:ring-purple-500 focus:border-transparent";

  return (
    <input
      type="number"
      value={currentValue}
      onChange={handleInputChange}
      min={min}
      max={max}
      step={step}
      className={`${inputClass} ${className}`}
      style={{ width: "100px" }}
    />
  );
};

// SelectDropdown component - styled select dropdown for categorical options
const SelectDropdown = ({
  id,
  value,
  onChange,
  options = [],
  className = "",
  isDarkMode = false,
}) => {
  const currentValue =
    value === null || value === undefined ? "" : String(value);

  const handleSelectChange = (e) => {
    onChange(e.target.value);
  };

  const selectClass = isDarkMode
    ? "w-full px-3 py-2 border border-gray-700 bg-gray-900 text-gray-100 rounded-md focus:ring-2 focus:ring-purple-500 focus:border-transparent"
    : "w-full px-3 py-2 border border-gray-300 bg-white text-gray-800 rounded-md focus:ring-2 focus:ring-purple-500 focus:border-transparent";

  return (
    <select
      id={id}
      value={currentValue}
      onChange={handleSelectChange}
      className={`${selectClass} ${className}`}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
};

function StringListEditor({
  value,
  placeholder,
  addLabel,
  onBrowse,
  onChange,
}) {
  const normalizeValues = (rawValue) =>
    (Array.isArray(rawValue) ? rawValue : [])
      .map((entry) => String(entry ?? ""))
      .filter((entry, index, entries) => entry !== "" || entries.length === 1);
  const [values, setValues] = useState(() => normalizeValues(value));

  useEffect(() => {
    setValues(normalizeValues(value));
  }, [value]);

  const updateValues = (nextValues) => {
    setValues(nextValues);
    onChange(nextValues);
  };

  return (
    <div className="space-y-2">
      {values.map((entry, index) => (
        <div
          key={index}
          className="flex flex-col gap-2 sm:flex-row sm:items-center"
        >
          <input
            type="text"
            value={entry}
            placeholder={placeholder}
            className="ua-config-input w-full rounded-lg border px-3 py-2"
            onChange={(event) => {
              const nextValues = [...values];
              nextValues[index] = event.target.value;
              updateValues(nextValues);
            }}
          />
          {onBrowse && (
            <button
              type="button"
              className="ua-config-service-action shrink-0 rounded-lg border px-3 py-2 text-sm font-semibold"
              onClick={async () => {
                const selectedPath = await onBrowse();
                if (!selectedPath) return;
                const nextValues = [...values];
                nextValues[index] = selectedPath;
                updateValues(nextValues);
              }}
            >
              Browse
            </button>
          )}
          <button
            type="button"
            className="shrink-0 rounded-lg border border-red-500/40 px-3 py-2 text-sm font-semibold text-red-500 hover:bg-red-500/10"
            onClick={() =>
              updateValues(
                values.filter((_value, valueIndex) => valueIndex !== index),
              )
            }
            aria-label={`Remove item ${index + 1}`}
          >
            Remove
          </button>
        </div>
      ))}
      <button
        type="button"
        className="ua-config-service-action rounded-lg border px-3 py-2 text-sm font-semibold"
        onClick={() => updateValues([...values, ""])}
      >
        + {addLabel}
      </button>
    </div>
  );
}

function PathMappingEditor({
  localItem,
  remoteItem,
  pathParts,
  onBrowseFolder,
  onValueChange,
}) {
  const createRows = (localValue, remoteValue) => {
    const localPaths = Array.isArray(localValue) ? localValue : [];
    const remotePaths = Array.isArray(remoteValue) ? remoteValue : [];
    const rowCount = Math.max(localPaths.length, remotePaths.length, 1);
    return Array.from({ length: rowCount }, (_value, index) => ({
      local: String(localPaths[index] ?? ""),
      remote: String(remotePaths[index] ?? ""),
    }));
  };
  const [rows, setRows] = useState(() =>
    createRows(localItem.value, remoteItem.value),
  );

  useEffect(() => {
    setRows(createRows(localItem.value, remoteItem.value));
  }, [localItem.value, remoteItem.value]);

  const localPathKey = [...pathParts, localItem.key].join("/");
  const remotePathKey = [...pathParts, remoteItem.key].join("/");
  useEffect(() => {
    const resetPath = (event) => {
      const resetPathKey = String(event.detail?.pathKey || "");
      if (resetPathKey === localPathKey) {
        setRows((currentRows) =>
          createRows(
            localItem.value,
            currentRows.map((row) => row.remote),
          ),
        );
      } else if (resetPathKey === remotePathKey) {
        setRows((currentRows) =>
          createRows(
            currentRows.map((row) => row.local),
            remoteItem.value,
          ),
        );
      }
    };
    window.addEventListener(CONFIG_FIELD_RESET_EVENT, resetPath);
    return () =>
      window.removeEventListener(CONFIG_FIELD_RESET_EVENT, resetPath);
  }, [localItem.value, localPathKey, remoteItem.value, remotePathKey]);

  const commitRows = (nextRows) => {
    setRows(nextRows);
    onValueChange(
      [...pathParts, localItem.key],
      JSON.stringify(nextRows.map((row) => row.local)),
      {
        originalValue: JSON.stringify(localItem.value),
        isSensitive: false,
        isRedacted: false,
        readOnly: false,
      },
    );
    onValueChange(
      [...pathParts, remoteItem.key],
      JSON.stringify(nextRows.map((row) => row.remote)),
      {
        originalValue: JSON.stringify(remoteItem.value),
        isSensitive: false,
        isRedacted: false,
        readOnly: false,
      },
    );
  };

  return (
    <div className="space-y-3">
      <div className="hidden grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-3 text-sm font-medium md:grid">
        <span>Local Path</span>
        <span>Remote Path</span>
        <span className="w-20"></span>
      </div>
      {rows.map((row, index) => (
        <div
          key={index}
          className="grid grid-cols-1 items-end gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
        >
          <div className="space-y-1 md:space-y-0">
            <span className="text-xs font-medium md:hidden">Local Path</span>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                type="text"
                value={row.local}
                placeholder="Local path"
                className="ua-config-input w-full rounded-lg border px-3 py-2"
                onChange={(event) => {
                  const nextRows = rows.map((currentRow, rowIndex) =>
                    rowIndex === index
                      ? { ...currentRow, local: event.target.value }
                      : currentRow,
                  );
                  commitRows(nextRows);
                }}
              />
              {onBrowseFolder && (
                <button
                  type="button"
                  className="ua-config-service-action shrink-0 rounded-lg border px-3 py-2 text-sm font-semibold"
                  onClick={async () => {
                    const selectedPath = await onBrowseFolder("Local Path");
                    if (!selectedPath) return;
                    const nextRows = rows.map((currentRow, rowIndex) =>
                      rowIndex === index
                        ? { ...currentRow, local: selectedPath }
                        : currentRow,
                    );
                    commitRows(nextRows);
                  }}
                >
                  Browse
                </button>
              )}
            </div>
          </div>
          <label className="space-y-1 md:space-y-0">
            <span className="text-xs font-medium md:hidden">Remote Path</span>
            <input
              type="text"
              value={row.remote}
              placeholder="Remote or container path"
              className="ua-config-input w-full rounded-lg border px-3 py-2"
              onChange={(event) => {
                const nextRows = rows.map((currentRow, rowIndex) =>
                  rowIndex === index
                    ? { ...currentRow, remote: event.target.value }
                    : currentRow,
                );
                commitRows(nextRows);
              }}
            />
          </label>
          <button
            type="button"
            className="rounded-lg border border-red-500/40 px-3 py-2 text-sm font-semibold text-red-500 hover:bg-red-500/10"
            onClick={() =>
              commitRows(
                rows.length === 1
                  ? [{ local: "", remote: "" }]
                  : rows.filter((_row, rowIndex) => rowIndex !== index),
              )
            }
          >
            Remove
          </button>
        </div>
      ))}
      <button
        type="button"
        className="ua-config-service-action rounded-lg border px-3 py-2 text-sm font-semibold"
        onClick={() => commitRows([...rows, { local: "", remote: "" }])}
      >
        + Add Path Mapping
      </button>
    </div>
  );
}

function ConfigLeaf(props) {
  const [resetVersion, setResetVersion] = useState(0);
  const pathKey = [...props.pathParts, props.item.key].join("/");

  useEffect(() => {
    const resetField = (event) => {
      if (String(event.detail?.pathKey) === pathKey) {
        setResetVersion((version) => version + 1);
      }
    };
    window.addEventListener(CONFIG_FIELD_RESET_EVENT, resetField);
    return () =>
      window.removeEventListener(CONFIG_FIELD_RESET_EVENT, resetField);
  }, [pathKey]);

  return <ConfigLeafEditor key={resetVersion} {...props} />;
}

function ConfigLeafEditor({
  item,
  pathParts,
  isDarkMode,
  fullWidth,
  allImageHosts,
  usedImageHosts,
  torrentClients,
  onBrowseFolder,
  onValueChange,
}) {
  const path = [...pathParts, item.key];
  const fieldId = path.join("--");
  const displayLabel = formatConfigFieldLabel(item.key, pathParts);

  const helpText = item.help && item.help.length ? item.help.join("\n") : "";
  const labelClass = isDarkMode
    ? "text-sm font-medium text-gray-200"
    : "text-sm font-medium text-gray-700";

  const inputClass = isDarkMode
    ? "w-full px-3 py-2 border border-gray-700 bg-gray-900 text-gray-100 rounded-md focus:ring-2 focus:ring-purple-500 focus:border-transparent"
    : "w-full px-3 py-2 border border-gray-300 bg-white text-gray-800 rounded-md focus:ring-2 focus:ring-purple-500 focus:border-transparent";

  // Check if this is a numeric field that should use NumberInput
  const isNumericField = (key) => {
    // Define which fields should be treated as numeric
    const numericFields = [
      "tracker_pass_checks",
      "mkbrr_threads",
      "ffmpeg_compression",
      "screens",
      "cutoff_screens",
      "max_menu_screens",
      "thumbnail_size",
      "process_limit",
      "threads",
      "multiScreens",
      "pack_thumb_size",
      "charLimit",
      "fileLimit",
      "processLimit",
      "desat",
      "min_successful_image_uploads",
      "overlay_text_size",
      "logo_size",
      "bluray_image_size",
      "bluray_score",
      "bluray_single_score",
      "rehash_cooldown",
      "custom_layout",
      "screens_per_row",
    ];
    return numericFields.includes(key);
  };

  // Check if this is a linking field that should use SelectDropdown
  const isLinkingField = (key, pathParts) => {
    return key === "linking" && pathParts.includes("TORRENT_CLIENTS");
  };
  const torrentClientListFields = new Set([
    "super_seed_trackers",
    "linked_folder",
    "local_path",
    "remote_path",
  ]);
  const isTorrentClientListField =
    pathParts.includes("TORRENT_CLIENTS") &&
    torrentClientListFields.has(item.key) &&
    Array.isArray(item.value);

  // Hooks for boolean values
  const [checked, setChecked] = useState(Boolean(item.value));

  useEffect(() => {
    if (typeof item.value === "boolean") setChecked(Boolean(item.value));
  }, [item.value]);

  // Hooks for numeric values
  const getDefaultValue = (key) => {
    switch (key) {
      case "mkbrr_threads":
      case "rehash_cooldown":
        return 0;
      case "multiScreens":
        return 2;
      case "tracker_pass_checks":
      case "screens":
      case "cutoff_screens":
      case "process_limit":
      case "threads":
      case "min_successful_image_uploads":
      case "overlay_text_size":
      case "logo_size":
      case "thumbnail_size":
      case "pack_thumb_size":
      case "charLimit":
      case "fileLimit":
      case "processLimit":
      case "bluray_image_size":
      case "bluray_score":
      case "bluray_single_score":
      case "desat":
        return 10;
      case "screens_per_row":
        return 2;
      case "custom_layout":
        return 1;
      case "ffmpeg_compression":
        return 6;
      default:
        return 1;
    }
  };

  const [numericValue, setNumericValue] = useState(() => {
    if (isNumericField(item.key)) {
      const val = item.value;
      if (val === null || val === undefined || val === "")
        return getDefaultValue(item.key);
      const num = Number(val);
      return isNaN(num) ? getDefaultValue(item.key) : num;
    }
    return 1;
  });

  useEffect(() => {
    if (!isNumericField(item.key)) return;
    const val = item.value;
    if (val === null || val === undefined || val === "") {
      setNumericValue(getDefaultValue(item.key));
    } else {
      const num = Number(val);
      setNumericValue(isNaN(num) ? getDefaultValue(item.key) : num);
    }
  }, [item.value, item.key]);

  // Hooks for select values (always declared to follow Rules of Hooks)
  const [selectedValue, setSelectedValue] = useState(() =>
    item == null || item.value == null ? "" : String(item.value),
  );

  useEffect(() => {
    setSelectedValue(
      item == null || item.value == null ? "" : String(item.value),
    );
  }, [item.value]);

  // Helpers and hooks for `default_trackers` (must run unconditionally to obey Rules of Hooks)
  const normalizeTrackers = (value) =>
    String(value || "")
      .split(",")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);

  const [selected, setSelected] = useState(
    () => new Set(normalizeTrackers(item.value)),
  );
  const prevDefaultRef = useRef(normalizeTrackers(item.value).join(", "));

  useEffect(() => {
    setSelected(new Set(normalizeTrackers(item.value)));
  }, [item.value]);

  // Observer: whenever the selected set changes, persist the default_trackers value
  useEffect(() => {
    // Only run this persistence effect for the actual `default_trackers` field.
    if (item.key !== "default_trackers") return;
    const nextValue = Array.from(selected)
      .map((t) => String(t).toUpperCase())
      .join(", ");
    const originalValue = normalizeTrackers(item.value).join(", ");
    if (prevDefaultRef.current === nextValue) return;
    prevDefaultRef.current = nextValue;
    onValueChange(path, nextValue, {
      originalValue,
      isSensitive: false,
      isRedacted: false,
      readOnly: false,
    });
  }, [selected, onValueChange, path, item.value]);

  const toggleTracker = (tracker, checked) => {
    const selections = new Set(selected);
    if (checked) {
      selections.add(tracker.toUpperCase());
    } else {
      selections.delete(tracker.toUpperCase());
    }
    setSelected(selections);
  };

  if (isTorrentClientListField) {
    const originalValue = JSON.stringify(item.value);
    const placeholders = {
      super_seed_trackers: "Tracker acronym, e.g. AITHER",
      linked_folder: "Path to linked content",
      local_path: "Local path",
      remote_path: "Remote or container path",
    };
    const addLabels = {
      super_seed_trackers: "Add Tracker",
      linked_folder: "Add Linked Folder",
      local_path: "Add Local Path",
      remote_path: "Add Remote Path",
    };
    return (
      <div className={fullWidth ? "space-y-2" : "px-4 py-3"}>
        <div className="mb-2 flex items-center gap-2">
          <div className={labelClass}>{displayLabel}</div>
          {helpText && (
            <Tooltip content={helpText}>
              <InfoIcon
                className={`h-4 w-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
              />
            </Tooltip>
          )}
        </div>
        <StringListEditor
          value={item.value}
          placeholder={placeholders[item.key] || "Value"}
          addLabel={addLabels[item.key] || "Add Entry"}
          onBrowse={
            ["linked_folder", "local_path"].includes(item.key) && onBrowseFolder
              ? () => onBrowseFolder(displayLabel)
              : null
          }
          onChange={(nextValues) =>
            onValueChange(path, JSON.stringify(nextValues), {
              originalValue,
              isSensitive: false,
              isRedacted: false,
              readOnly: false,
            })
          }
        />
      </div>
    );
  }

  if (typeof item.value === "boolean") {
    const originalValue = Boolean(item.value);

    return (
      <div
        className={
          fullWidth
            ? "space-y-2"
            : "grid grid-cols-1 items-start gap-3 px-4 py-3 md:grid-cols-12"
        }
      >
        <div className={fullWidth ? "" : "col-span-1 md:col-span-4"}>
          <div className="flex items-center gap-2">
            <div className={labelClass}>{displayLabel}</div>
            {helpText && (
              <Tooltip content={helpText}>
                <InfoIcon
                  className={`w-4 h-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
                />
              </Tooltip>
            )}
          </div>
        </div>
        <div className={fullWidth ? "" : "col-span-1 md:col-span-7"}>
          <div
            className={`flex items-center gap-3${fullWidth ? " ua-config-boolean-control-row" : ""}`}
          >
            <button
              onClick={() => {
                const nextValue = !checked;
                setChecked(nextValue);
                onValueChange(path, nextValue, {
                  originalValue,
                  isSensitive: false,
                  isRedacted: false,
                  readOnly: false,
                });
              }}
              aria-pressed={checked}
              aria-label={`${displayLabel}: ${checked ? "True" : "False"}`}
              className="ua-config-boolean-toggle relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
              data-enabled={checked ? "true" : "false"}
            >
              <span
                className={`ua-config-boolean-knob inline-block h-4 w-4 transform rounded-full transition-transform ${checked ? "translate-x-6" : "translate-x-1"}`}
              />
            </button>
            <span className={isDarkMode ? "text-gray-200" : "text-gray-700"}>
              {checked ? "True" : "False"}
            </span>
          </div>
        </div>
        {!fullWidth && <div className="col-span-1 text-right"></div>}
      </div>
    );
  }

  if (isNumericField(item.key)) {
    const originalValue = String(item.value);

    // Define min/max for different fields
    const getFieldLimits = (key) => {
      switch (key) {
        case "tracker_pass_checks":
          return { min: 1, max: 20, step: 1 };
        case "mkbrr_threads":
          return { min: 0, max: 32, step: 1 };
        case "ffmpeg_compression":
          return { min: 0, max: 9, step: 1 };
        case "screens":
          return { min: 1, max: 50, step: 1 };
        case "cutoff_screens":
          return { min: 1, max: 50, step: 1 };
        case "thumbnail_size":
          return { min: 100, max: 1000, step: 50 };
        case "process_limit":
          return { min: 1, max: 100, step: 1 };
        case "threads":
          return { min: 1, max: 32, step: 1 };
        case "multiScreens":
          return { min: 0, max: 20, step: 1 };
        case "pack_thumb_size":
          return { min: 100, max: 1000, step: 50 };
        case "charLimit":
          return { min: 100, max: 50000, step: 100 };
        case "fileLimit":
          return { min: 1, max: 1000, step: 1 };
        case "processLimit":
          return { min: 1, max: 100, step: 1 };
        case "desat":
          return { min: 0, max: 20, step: 0.1 };
        case "min_successful_image_uploads":
          return { min: 1, max: 10, step: 1 };
        case "overlay_text_size":
          return { min: 10, max: 50, step: 1 };
        case "logo_size":
          return { min: 100, max: 1000, step: 50 };
        case "bluray_image_size":
          return { min: 100, max: 1000, step: 50 };
        case "bluray_score":
          return { min: 0, max: 100, step: 0.1 };
        case "bluray_single_score":
          return { min: 0, max: 100, step: 0.1 };
        case "rehash_cooldown":
          return { min: 0, max: 300, step: 5 };
        case "screens_per_row":
          return { min: 1, max: 10, step: 1 };
        case "custom_layout":
          return { min: 1, max: 10, step: 1 };
        default:
          return { min: 0, max: 100, step: 1 };
      }
    };

    const limits = getFieldLimits(item.key);

    return (
      <div
        className={
          fullWidth
            ? "space-y-2"
            : "grid grid-cols-1 items-start gap-3 px-4 py-3 md:grid-cols-12"
        }
      >
        <div className={fullWidth ? "" : "col-span-1 md:col-span-4"}>
          <div className="flex items-center gap-2">
            <div className={labelClass}>{displayLabel}</div>
            {helpText && (
              <Tooltip content={helpText}>
                <InfoIcon
                  className={`w-4 h-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
                />
              </Tooltip>
            )}
          </div>
        </div>
        <div className={fullWidth ? "" : "col-span-1 md:col-span-7"}>
          <NumberInput
            value={numericValue}
            onChange={(newValue) => {
              setNumericValue(newValue);
              onValueChange(path, String(newValue), {
                originalValue,
                isSensitive: false,
                isRedacted: false,
                readOnly: false,
              });
            }}
            min={limits.min}
            max={limits.max}
            step={limits.step}
            isDarkMode={isDarkMode}
          />
        </div>
        {!fullWidth && <div className="col-span-1 text-right"></div>}
      </div>
    );
  }

  if (item.key === "default_torrent_client") {
    const originalValue =
      item.value === null || item.value === undefined ? "" : String(item.value);
    const currentClient = String(selectedValue || "");
    const currentClientKey = currentClient.toLowerCase();
    const configuredClients = Array.from(
      new Map(
        (torrentClients || [])
          .filter(Boolean)
          .map((client) => [String(client).toLowerCase(), String(client)]),
      ).values(),
    ).sort((left, right) => left.localeCompare(right));
    const configuredCurrentClient = configuredClients.find(
      (client) => client.toLowerCase() === currentClientKey,
    );
    const clientOptions = [
      {
        value: "",
        label:
          configuredClients.length > 0
            ? "Select a configured client..."
            : "No configured clients available",
      },
      ...(currentClient
        ? [
            {
              value: currentClient,
              label:
                configuredCurrentClient || `${currentClient} (Not configured)`,
            },
          ]
        : []),
      ...configuredClients
        .filter((client) => client.toLowerCase() !== currentClientKey)
        .map((client) => ({ value: client, label: client })),
    ];

    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <label htmlFor={fieldId} className={labelClass}>
            {displayLabel}
          </label>
          {helpText && (
            <Tooltip content={helpText}>
              <InfoIcon
                className={`h-4 w-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
              />
            </Tooltip>
          )}
        </div>
        <SelectDropdown
          id={fieldId}
          value={selectedValue}
          onChange={(newValue) => {
            setSelectedValue(newValue);
            onValueChange(path, newValue, {
              originalValue,
              isSensitive: false,
              isRedacted: false,
              readOnly: false,
            });
          }}
          options={clientOptions}
          isDarkMode={isDarkMode}
        />
      </div>
    );
  }

  if (item.key === "tracker_description_mode") {
    const originalValue =
      item.value === null || item.value === undefined ? "" : String(item.value);
    const modeOptions = [
      { value: "", label: "Select an import mode..." },
      { value: "ids", label: "IDs and metadata only" },
      { value: "images", label: "IDs, metadata and screenshots" },
      { value: "text", label: "IDs, metadata and description text" },
      {
        value: "text_and_images",
        label: "IDs, metadata, description text and screenshots",
      },
    ];
    if (
      selectedValue &&
      !modeOptions.some((option) => option.value === selectedValue)
    ) {
      modeOptions.splice(1, 0, {
        value: selectedValue,
        label: `${selectedValue} (Unsupported)`,
      });
    }

    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <label htmlFor={fieldId} className={labelClass}>
            {displayLabel}
          </label>
          {helpText && (
            <Tooltip content={helpText}>
              <InfoIcon
                className={`h-4 w-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
              />
            </Tooltip>
          )}
        </div>
        <SelectDropdown
          id={fieldId}
          value={selectedValue}
          onChange={(newValue) => {
            setSelectedValue(newValue);
            onValueChange(path, newValue, {
              originalValue,
              isSensitive: false,
              isRedacted: false,
              readOnly: false,
            });
          }}
          options={modeOptions}
          isDarkMode={isDarkMode}
        />
      </div>
    );
  }

  if (item.key === "upload_order") {
    const originalValue =
      item.value === null || item.value === undefined ? "" : String(item.value);
    const uploadOrderOptions = [
      {
        value: "concurrent",
        label: "Concurrent — Upload to Usenet and torrent trackers together",
      },
      {
        value: "usenet",
        label: "Usenet first — Finish Usenet before torrent trackers",
      },
      {
        value: "tracker",
        label: "Torrent trackers first — Finish trackers before Usenet",
      },
    ];
    if (
      selectedValue &&
      !uploadOrderOptions.some((option) => option.value === selectedValue)
    ) {
      uploadOrderOptions.unshift({
        value: selectedValue,
        label: `${selectedValue} (Unsupported)`,
      });
    }

    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <label htmlFor={fieldId} className={labelClass}>
            {displayLabel}
          </label>
          {helpText && (
            <Tooltip content={helpText}>
              <InfoIcon
                className={`h-4 w-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
              />
            </Tooltip>
          )}
        </div>
        <SelectDropdown
          id={fieldId}
          value={selectedValue}
          onChange={(newValue) => {
            setSelectedValue(newValue);
            onValueChange(path, newValue, {
              originalValue,
              isSensitive: false,
              isRedacted: false,
              readOnly: false,
            });
          }}
          options={uploadOrderOptions}
          isDarkMode={isDarkMode}
        />
      </div>
    );
  }

  if (isLinkingField(item.key, pathParts)) {
    const linkingOptions = [
      { value: "", label: "None (Original Path)" },
      { value: "symlink", label: "Symbolic Link" },
      { value: "hardlink", label: "Hard Link" },
    ];

    const originalValue = String(item.value || "");

    return (
      <div
        className={
          fullWidth
            ? "space-y-2"
            : "grid grid-cols-1 items-start gap-3 px-4 py-3 md:grid-cols-12"
        }
      >
        <div className={fullWidth ? "" : "col-span-1 md:col-span-4"}>
          <div className="flex items-center gap-2">
            <div className={labelClass}>{displayLabel}</div>
            {helpText && (
              <Tooltip content={helpText}>
                <InfoIcon
                  className={`w-4 h-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
                />
              </Tooltip>
            )}
          </div>
        </div>
        <div className={fullWidth ? "" : "col-span-1 md:col-span-7"}>
          <SelectDropdown
            value={selectedValue}
            onChange={(newValue) => {
              setSelectedValue(newValue);
              onValueChange(path, newValue, {
                originalValue,
                isSensitive: false,
                isRedacted: false,
                readOnly: false,
              });
            }}
            options={linkingOptions}
            isDarkMode={isDarkMode}
          />
        </div>
        {!fullWidth && <div className="col-span-1 text-right"></div>}
      </div>
    );
  }

  if (item.key === "default_trackers") {
    const availableTrackers = getAvailableTrackers(item);

    return (
      <div className="col-span-full px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <div className={labelClass}>{displayLabel}</div>
          {helpText && (
            <Tooltip content={helpText}>
              <InfoIcon
                className={`w-4 h-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
              />
            </Tooltip>
          )}
        </div>
        <div
          className={`rounded-lg border p-3 ${isDarkMode ? "border-gray-700 bg-gray-900/30" : "border-gray-200 bg-gray-50"}`}
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2">
            {availableTrackers.map((tracker) => (
              <label
                key={tracker}
                className={`flex items-center gap-2 text-xs ${isDarkMode ? "text-gray-200" : "text-gray-700"}`}
              >
                <input
                  type="checkbox"
                  checked={selected.has(tracker.toUpperCase())}
                  onChange={(e) => toggleTracker(tracker, e.target.checked)}
                  className={
                    isDarkMode
                      ? "h-4 w-4 accent-purple-500"
                      : "h-4 w-4 accent-purple-600"
                  }
                />
                <span>{getTrackerDisplayName(tracker)}</span>
              </label>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (item.key && item.key.startsWith("img_host_")) {
    const options = getImageHostOptions(item, allImageHosts, usedImageHosts);
    const [value, setValue] = useState(
      item.value === null || item.value === undefined
        ? ""
        : String(item.value).trim().toLowerCase(),
    );

    useEffect(() => {
      setValue(
        item.value === null || item.value === undefined
          ? ""
          : String(item.value).trim().toLowerCase(),
      );
    }, [item.value]);

    const originalValue =
      item.value === null || item.value === undefined
        ? ""
        : String(item.value).trim().toLowerCase();

    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <label htmlFor={fieldId} className={labelClass}>
            {displayLabel}
          </label>
          {helpText && (
            <Tooltip content={helpText}>
              <InfoIcon
                className={`w-4 h-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
              />
            </Tooltip>
          )}
        </div>
        <select
          id={fieldId}
          value={value}
          onChange={(e) => {
            const nextValue = e.target.value;
            setValue(nextValue);
            onValueChange(path, nextValue, {
              originalValue,
              isSensitive: false,
              isRedacted: false,
              readOnly: false,
            });
          }}
          className={inputClass}
        >
          <option value=""></option>
          {options.map((host) => (
            <option key={host} value={host}>
              {IMAGE_HOST_LABELS[host] || host}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (
    item.key === "injecting_client_list" ||
    item.key === "searching_client_list"
  ) {
    const normalizeClients = (value) => {
      if (Array.isArray(value)) {
        return value
          .filter((client) => client && typeof client === "string")
          .map((client) => client.trim());
      }
      if (typeof value === "string" && value.trim()) {
        try {
          const parsed = JSON.parse(value);
          if (Array.isArray(parsed)) {
            return parsed
              .filter((client) => client && typeof client === "string")
              .map((client) => client.trim());
          }
        } catch (e) {
          // If not valid JSON, treat as comma-separated string
          return value
            .split(",")
            .map((client) => client.trim())
            .filter((client) => client);
        }
      }
      return [];
    };

    const [selected, setSelected] = useState(() =>
      normalizeClients(item.value),
    );
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef(null);

    useEffect(() => {
      setSelected(normalizeClients(item.value));
    }, [item.value]);

    useEffect(() => {
      const handleClickOutside = (event) => {
        if (
          dropdownRef.current &&
          !dropdownRef.current.contains(event.target)
        ) {
          setIsOpen(false);
        }
      };

      document.addEventListener("mousedown", handleClickOutside);
      return () =>
        document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const originalValue = normalizeClients(item.value);

    const toggleClient = (client) => {
      const newSelected = selected.includes(client)
        ? selected.filter((c) => c !== client)
        : [...selected, client];
      setSelected(newSelected);
      onValueChange(path, newSelected, {
        originalValue,
        isSensitive: false,
        isRedacted: false,
        readOnly: false,
      });
    };

    const removeClient = (clientToRemove, e) => {
      e.stopPropagation();
      const newSelected = selected.filter((c) => c !== clientToRemove);
      setSelected(newSelected);
      onValueChange(path, newSelected, {
        originalValue,
        isSensitive: false,
        isRedacted: false,
        readOnly: false,
      });
    };

    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <label className={labelClass}>{displayLabel}</label>
          {helpText && (
            <Tooltip content={helpText}>
              <InfoIcon
                className={`w-4 h-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
              />
            </Tooltip>
          )}
        </div>
        <div className={`relative ${isOpen ? "z-30" : ""}`} ref={dropdownRef}>
          <div
            className={`${inputClass} cursor-pointer flex items-center justify-between`}
            onClick={() => setIsOpen(!isOpen)}
          >
            <div className="flex flex-wrap gap-1 flex-1">
              {selected.length === 0 ? (
                <span
                  className={isDarkMode ? "text-gray-500" : "text-gray-400"}
                >
                  Select clients...
                </span>
              ) : (
                selected.map((client) => (
                  <span
                    key={client}
                    className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs ${
                      isDarkMode
                        ? "bg-purple-600 text-white"
                        : "bg-purple-100 text-purple-800"
                    }`}
                  >
                    {client}
                    <button
                      type="button"
                      onClick={(e) => removeClient(client, e)}
                      className={`hover:${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
                    >
                      ×
                    </button>
                  </span>
                ))
              )}
            </div>
            <span
              className={`transition-transform ${isOpen ? "rotate-180" : "rotate-0"}`}
            >
              ▼
            </span>
          </div>
          {isOpen && (
            <div
              className={`absolute z-40 w-full mt-1 border rounded-md shadow-lg max-h-60 overflow-auto ${
                isDarkMode
                  ? "bg-gray-900 border-gray-700"
                  : "bg-white border-gray-300"
              }`}
            >
              {torrentClients.length === 0 ? (
                <div
                  className={`px-3 py-2 text-sm ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
                >
                  No torrent clients configured
                </div>
              ) : (
                torrentClients.map((client) => (
                  <div
                    key={client}
                    className={`px-3 py-2 cursor-pointer hover:${
                      isDarkMode ? "bg-gray-800" : "bg-gray-100"
                    } ${selected.includes(client) ? (isDarkMode ? "bg-purple-900" : "bg-purple-50") : ""}`}
                    onClick={() => toggleClient(client)}
                  >
                    <label
                      className={`flex items-center gap-2 text-sm cursor-pointer ${
                        isDarkMode ? "text-gray-200" : "text-gray-700"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selected.includes(client)}
                        onChange={() => {}} // Handled by parent div
                        className={
                          isDarkMode
                            ? "h-4 w-4 accent-purple-500"
                            : "h-4 w-4 accent-purple-600"
                        }
                      />
                      {client}
                    </label>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Special-case: render a dropdown for tonemapping algorithm selection
  if (item.key === "algorithm") {
    const algoOptions = [
      { value: "", label: "" },
      {
        value: "none",
        label:
          "none — Do not apply any tone map, only desaturate overbright pixels.",
      },
      {
        value: "clip",
        label:
          "clip — Hard-clip out-of-range values; accurate in-range colors.",
      },
      {
        value: "linear",
        label:
          "linear — Stretch reference gamut to a linear multiple of the display.",
      },
      {
        value: "gamma",
        label: "gamma — Fit a logarithmic transfer between the tone curves.",
      },
      {
        value: "reinhard",
        label:
          "reinhard — Preserve brightness with a simple curve; may flatten details.",
      },
      {
        value: "hable",
        label: "hable — Preserve dark/bright details better than reinhard.",
      },
      {
        value: "mobius",
        label:
          "mobius — Smoothly map out-of-range values while retaining colors.",
      },
    ];

    const originalValue =
      item.value === null || item.value === undefined ? "" : String(item.value);

    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <label className={labelClass}>{displayLabel}</label>
          {helpText && (
            <Tooltip content={helpText}>
              <InfoIcon
                className={`w-4 h-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
              />
            </Tooltip>
          )}
        </div>
        <SelectDropdown
          value={selectedValue}
          onChange={(newValue) => {
            setSelectedValue(newValue);
            onValueChange(path, newValue, {
              originalValue,
              isSensitive: false,
              isRedacted: false,
              readOnly: false,
            });
          }}
          options={algoOptions}
          isDarkMode={isDarkMode}
        />
      </div>
    );
  }

  const rawValue =
    item.value === null || item.value === undefined
      ? ""
      : typeof item.value === "string"
        ? item.value
        : JSON.stringify(item.value);
  const sensitive = isSensitiveKeyForPath(item.key, pathParts);
  const readOnly = isReadOnlyKeyForPath(item.key, pathParts);
  const canBrowseTorrentFolder =
    pathParts.includes("TORRENT_CLIENTS") &&
    ["torrent_storage_dir", "watch_folder"].includes(item.key) &&
    Boolean(onBrowseFolder);
  const originalValue =
    sensitive && String(rawValue).trim() !== "" ? "<REDACTED>" : rawValue;

  const [textValue, setTextValue] = useState(rawValue);
  const [redacted, setRedacted] = useState(
    sensitive && String(rawValue).trim() !== "",
  );

  useEffect(() => {
    const nextRaw =
      item.value === null || item.value === undefined
        ? ""
        : typeof item.value === "string"
          ? item.value
          : JSON.stringify(item.value);
    const isRedacted = sensitive && String(nextRaw).trim() !== "";
    setTextValue(isRedacted ? "<REDACTED>" : nextRaw);
    setRedacted(isRedacted);
  }, [item.value, sensitive]);

  const onFocus = () => {
    if (redacted) {
      setTextValue("");
      setRedacted(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <label htmlFor={fieldId} className={labelClass}>
          {displayLabel}
        </label>
        {helpText && (
          <Tooltip content={helpText}>
            <InfoIcon
              className={`w-4 h-4 ${isDarkMode ? "text-gray-400 hover:text-gray-300" : "text-gray-500 hover:text-gray-600"}`}
            />
          </Tooltip>
        )}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id={fieldId}
          type="text"
          value={textValue}
          onChange={(e) => {
            const nextValue = e.target.value;
            setTextValue(nextValue);
            onValueChange(path, nextValue, {
              originalValue,
              isSensitive: sensitive,
              isRedacted: redacted,
              readOnly,
            });
          }}
          onFocus={onFocus}
          disabled={readOnly}
          className={`${inputClass}${readOnly ? " opacity-70 cursor-not-allowed" : ""}`}
        />
        {canBrowseTorrentFolder && (
          <button
            type="button"
            className="ua-config-service-action shrink-0 rounded-lg border px-3 py-2 text-sm font-semibold"
            onClick={async () => {
              const selectedPath = await onBrowseFolder(displayLabel);
              if (!selectedPath) return;
              setTextValue(selectedPath);
              setRedacted(false);
              onValueChange(path, selectedPath, {
                originalValue,
                isSensitive: false,
                isRedacted: false,
                readOnly,
              });
            }}
          >
            Browse
          </button>
        )}
      </div>
    </div>
  );
}

function MetadataCacheServices({
  item,
  pathParts,
  depth,
  isDarkMode,
  allImageHosts,
  usedImageHosts,
  expandedGroups,
  toggleGroup,
  torrentClients,
  onValueChange,
}) {
  const groupKey = [...pathParts, item.key].join("/");
  const isOpen = expandedGroups.has(groupKey);
  const services = item.children || [];
  const serviceByKey = new Map(
    services.map((service) => [String(service.key).toLowerCase(), service]),
  );
  const groupedServiceKeys = new Set(
    METADATA_CACHE_SERVICE_GROUPS.flatMap((group) => group.services),
  );
  const serviceGroups = METADATA_CACHE_SERVICE_GROUPS.map((group) => ({
    label: group.label,
    services: group.services
      .map((serviceKey) => serviceByKey.get(serviceKey))
      .filter(Boolean),
  })).filter((group) => group.services.length > 0);
  const otherServices = services.filter(
    (service) => !groupedServiceKeys.has(String(service.key).toLowerCase()),
  );
  if (otherServices.length > 0) {
    serviceGroups.push({ label: "Other", services: otherServices });
  }
  const helpText = (item.help || []).join(" ");

  return (
    <section
      className="ua-config-accordion overflow-hidden rounded-xl border"
      data-open={isOpen ? "true" : "false"}
    >
      <button
        type="button"
        onClick={() => toggleGroup(groupKey)}
        className="ua-config-accordion-trigger flex w-full items-center justify-between gap-4 px-4 py-3 text-left"
        aria-expanded={isOpen}
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold">
            Service Cache Overrides
          </span>
          {helpText && (
            <span className="ua-config-service-description mt-1 block text-xs font-normal">
              {helpText}
            </span>
          )}
        </span>
        <span className="flex shrink-0 items-center gap-3">
          <span className="ua-config-service-action hidden text-xs font-medium sm:inline">
            {isOpen ? "Hide services" : `Show ${services.length} services`}
          </span>
          <span
            className="ua-config-accordion-chevron transition-transform"
            style={{
              transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
            }}
            aria-hidden="true"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m9 18 6-6-6-6"></path>
            </svg>
          </span>
        </span>
      </button>

      {isOpen && (
        <div className="ua-config-accordion-panel border-t">
          {serviceGroups.map((serviceGroup) => (
            <section key={serviceGroup.label}>
              <h3 className="ua-config-service-group-title border-b px-4 py-3 text-xs font-semibold uppercase tracking-wider">
                {serviceGroup.label}
              </h3>
              <div>
                {serviceGroup.services.map((service) => {
                  const serviceKey = String(service.key).toLowerCase();
                  const serviceHelp = (service.help || []).join(" ");
                  return (
                    <div
                      key={service.key}
                      className="ua-config-service-row px-4 py-4"
                    >
                      <div className="min-w-0">
                        <h4 className="text-sm font-semibold">
                          {METADATA_CACHE_SERVICE_LABELS[serviceKey] ||
                            formatDisplayLabel(service.key)}
                        </h4>
                        {serviceHelp && (
                          <p className="ua-config-service-description mt-1 text-xs leading-relaxed">
                            {serviceHelp}
                          </p>
                        )}
                      </div>
                      {(service.children || []).map((field) => (
                        <ConfigLeaf
                          key={`${groupKey}/${service.key}/${field.key}`}
                          item={field}
                          pathParts={[...pathParts, item.key, service.key]}
                          depth={depth + 2}
                          isDarkMode={isDarkMode}
                          fullWidth={true}
                          allImageHosts={allImageHosts}
                          usedImageHosts={usedImageHosts}
                          torrentClients={torrentClients}
                          onValueChange={onValueChange}
                        />
                      ))}
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}

function ReleaseGroupOverrides({
  item,
  pathParts,
  depth,
  isDarkMode,
  allImageHosts,
  usedImageHosts,
  expandedGroups,
  toggleGroup,
  torrentClients,
  onValueChange,
}) {
  const groupKey = [...pathParts, item.key].join("/");
  const isOpen = expandedGroups.has(groupKey);
  const releaseGroups = item.children || [];
  const helpText = (item.help || []).join(" ");
  const groupLabel = releaseGroups.length === 1 ? "group" : "groups";

  return (
    <section
      className="ua-config-accordion overflow-hidden rounded-xl border"
      data-open={isOpen ? "true" : "false"}
    >
      <button
        type="button"
        onClick={() => toggleGroup(groupKey)}
        className="ua-config-accordion-trigger flex w-full items-center justify-between gap-4 px-4 py-3 text-left"
        aria-expanded={isOpen}
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold">
            Release Group Overrides
          </span>
          {helpText && (
            <span className="ua-config-service-description mt-1 block text-xs font-normal">
              {helpText}
            </span>
          )}
        </span>
        <span className="flex shrink-0 items-center gap-3">
          <span className="ua-config-service-action hidden text-xs font-medium sm:inline">
            {isOpen
              ? `Hide ${groupLabel}`
              : `Show ${releaseGroups.length} ${groupLabel}`}
          </span>
          <span
            className="ua-config-accordion-chevron transition-transform"
            style={{
              transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
            }}
            aria-hidden="true"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m9 18 6-6-6-6"></path>
            </svg>
          </span>
        </span>
      </button>

      {isOpen && (
        <div className="ua-config-accordion-panel space-y-3 border-t p-4">
          {releaseGroups.map((releaseGroup) => {
            const releaseGroupKey = [
              ...pathParts,
              item.key,
              releaseGroup.key,
            ].join("/");
            const isReleaseGroupOpen = expandedGroups.has(releaseGroupKey);
            const fields = releaseGroup.children || [];
            return (
              <div
                key={releaseGroupKey}
                className="ua-config-accordion overflow-hidden rounded-lg border"
                data-open={isReleaseGroupOpen ? "true" : "false"}
              >
                <button
                  type="button"
                  onClick={() => toggleGroup(releaseGroupKey)}
                  className="ua-config-accordion-trigger flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
                  aria-expanded={isReleaseGroupOpen}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold">
                      {releaseGroup.key}
                    </span>
                    <span className="ua-config-service-description mt-1 block text-xs font-normal">
                      {fields.length} description overrides
                    </span>
                  </span>
                  <span
                    className="ua-config-accordion-chevron shrink-0 transition-transform"
                    style={{
                      transform: isReleaseGroupOpen
                        ? "rotate(90deg)"
                        : "rotate(0deg)",
                    }}
                    aria-hidden="true"
                  >
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="m9 18 6-6-6-6"></path>
                    </svg>
                  </span>
                </button>
                {isReleaseGroupOpen && (
                  <div className="ua-config-accordion-panel border-t p-4">
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                      {fields.map((field) => (
                        <ConfigLeaf
                          key={`${releaseGroupKey}/${field.key}`}
                          item={field}
                          pathParts={[...pathParts, item.key, releaseGroup.key]}
                          depth={depth + 2}
                          isDarkMode={isDarkMode}
                          fullWidth={true}
                          allImageHosts={allImageHosts}
                          usedImageHosts={usedImageHosts}
                          torrentClients={torrentClients}
                          onValueChange={onValueChange}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function FolderPickerModal({ fieldLabel, onCancel, onSelect }) {
  const [pathHistory, setPathHistory] = useState([]);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const currentPath = pathHistory[pathHistory.length - 1] || "";

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [onCancel]);

  useEffect(() => {
    let active = true;
    const loadFolders = async () => {
      setLoading(true);
      setError("");
      try {
        const endpoint = currentPath
          ? `${API_BASE}/browse?path=${encodeURIComponent(currentPath)}`
          : `${API_BASE}/browse_roots`;
        const response = await apiFetch(endpoint);
        const data = await response.json();
        if (!response.ok || !data.success) {
          throw new Error(data.error || "Unable to browse folders");
        }
        if (active) {
          setItems((data.items || []).filter((item) => item.type === "folder"));
        }
      } catch (loadError) {
        if (active) {
          setItems([]);
          setError(loadError.message || "Unable to browse folders");
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    loadFolders();
    return () => {
      active = false;
    };
  }, [currentPath]);

  const openFolder = (path) => {
    setPathHistory((history) => [...history, path]);
  };

  const goBack = () => {
    setPathHistory((history) => history.slice(0, -1));
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <section
        className="ua-config-modal flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="folder-picker-title"
      >
        <div className="ua-config-section-heading border-b px-4 py-3">
          <h2 id="folder-picker-title" className="text-base font-semibold">
            Choose {fieldLabel || "Folder"}
          </h2>
          <p className="ua-config-service-description mt-1 text-xs">
            Folders visible to Upload Assistant are shown here.
          </p>
        </div>

        <div className="flex items-center gap-3 border-b px-4 py-3">
          <button
            type="button"
            className="ua-config-service-action rounded-lg border px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            disabled={pathHistory.length === 0}
            onClick={goBack}
          >
            Back
          </button>
          <span className="min-w-0 truncate text-sm" title={currentPath}>
            {currentPath || "Browse roots"}
          </span>
        </div>

        <div className="min-h-48 flex-1 overflow-y-auto p-3">
          {loading && (
            <div className="ua-config-service-description p-3 text-sm">
              Loading folders...
            </div>
          )}
          {!loading && error && (
            <div className="rounded-lg border border-red-500/40 p-3 text-sm text-red-500">
              {error}
            </div>
          )}
          {!loading && !error && items.length === 0 && (
            <div className="ua-config-service-description p-3 text-sm">
              No folders are available here.
            </div>
          )}
          {!loading && !error && items.length > 0 && (
            <div className="space-y-2">
              {items.map((item) => (
                <button
                  key={item.path}
                  type="button"
                  className="ua-config-folder-row flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left"
                  onClick={() => openFolder(item.path)}
                >
                  <span aria-hidden="true">📁</span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {item.name}
                    </span>
                    {item.subtitle && (
                      <span className="ua-config-service-description block truncate text-xs">
                        {item.subtitle}
                      </span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-wrap justify-end gap-2 border-t px-4 py-3">
          <button
            type="button"
            className="ua-config-service-action rounded-lg border px-4 py-2 text-sm font-semibold"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="ua-config-save-button rounded-lg px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!currentPath}
            onClick={() => onSelect(currentPath)}
          >
            Select This Folder
          </button>
        </div>
      </section>
    </div>
  );
}

function TorrentClientCreator({ templateItems, configuredNames, onAddClient }) {
  const templateChoices = Object.entries(TORRENT_CLIENT_TEMPLATE_LABELS)
    .filter(([templateName]) =>
      templateItems.some((item) => item.key === templateName),
    )
    .map(([templateName, label]) => ({ templateName, label }));
  const [isOpen, setIsOpen] = useState(false);
  const [templateName, setTemplateName] = useState(
    templateChoices[0]?.templateName || "",
  );
  const [clientName, setClientName] = useState("");
  const [message, setMessage] = useState("");
  const normalizedName = clientName.trim();
  const validName = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(normalizedName);
  const nameTaken = configuredNames.has(normalizedName.toLowerCase());

  const addClient = (event) => {
    event.preventDefault();
    if (!validName || nameTaken || !templateName) return;
    setMessage("");
    try {
      onAddClient(normalizedName, templateName);
      setClientName("");
      setIsOpen(false);
    } catch (error) {
      setMessage(error.message || "Failed to add torrent client");
    }
  };

  return (
    <section
      className="ua-config-accordion overflow-hidden rounded-xl border"
      data-open={isOpen ? "true" : "false"}
    >
      <button
        type="button"
        className="ua-config-accordion-trigger flex w-full items-center justify-between gap-4 px-4 py-3 text-left"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold">
            Add Torrent Client
          </span>
          <span className="ua-config-service-description mt-1 block text-xs font-normal">
            Create a named client from one of the supported connection
            templates.
          </span>
        </span>
        <span
          className="ua-config-accordion-chevron shrink-0 transition-transform"
          style={{ transform: isOpen ? "rotate(90deg)" : "rotate(0deg)" }}
          aria-hidden="true"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m9 18 6-6-6-6"></path>
          </svg>
        </span>
      </button>

      {isOpen && (
        <form
          className="ua-config-accordion-panel border-t p-4"
          onSubmit={addClient}
        >
          <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
            <div className="space-y-2">
              <label
                htmlFor="new-torrent-client-name"
                className="text-sm font-semibold"
              >
                Client Name
              </label>
              <input
                id="new-torrent-client-name"
                type="text"
                value={clientName}
                onChange={(event) => setClientName(event.target.value)}
                placeholder="seedbox_qbit"
                className="ua-config-input w-full rounded-lg border px-3 py-2"
                autoComplete="off"
              />
              <p className="ua-config-service-description text-xs">
                This name is used by Client Selection and may contain letters,
                numbers, hyphens and underscores.
              </p>
            </div>
            <div className="space-y-2">
              <label
                htmlFor="new-torrent-client-template"
                className="text-sm font-semibold"
              >
                Client Type
              </label>
              <select
                id="new-torrent-client-template"
                value={templateName}
                onChange={(event) => setTemplateName(event.target.value)}
                className="ua-config-select w-full rounded-lg border px-3 py-2"
              >
                {templateChoices.map((choice) => (
                  <option key={choice.templateName} value={choice.templateName}>
                    {choice.label}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="submit"
              className="ua-config-save-button rounded-lg px-4 py-2 text-sm font-semibold md:mt-7"
              disabled={!validName || nameTaken || !templateName}
            >
              Add Client
            </button>
          </div>
          {normalizedName && !validName && (
            <p className="mt-3 text-sm text-red-500">
              Enter a valid client name using letters, numbers, hyphens or
              underscores.
            </p>
          )}
          {nameTaken && (
            <p className="mt-3 text-sm text-red-500">
              A client with that name already exists.
            </p>
          )}
          {message && <p className="mt-3 text-sm text-red-500">{message}</p>}
        </form>
      )}
    </section>
  );
}

function RenameTorrentClientModal({
  sourceName,
  existingNames,
  onCancel,
  onRename,
}) {
  const [clientName, setClientName] = useState(sourceName);
  const normalizedName = clientName.trim();
  const validName = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(normalizedName);
  const unchanged =
    normalizedName.toLowerCase() === String(sourceName).toLowerCase();
  const nameTaken = (existingNames || []).some(
    (name) =>
      String(name).toLowerCase() === normalizedName.toLowerCase() &&
      String(name).toLowerCase() !== String(sourceName).toLowerCase(),
  );

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <form
        className="ua-config-modal w-full max-w-md overflow-hidden rounded-xl border shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rename-client-title"
        onSubmit={(event) => {
          event.preventDefault();
          if (validName && !unchanged && !nameTaken) onRename(normalizedName);
        }}
      >
        <div className="ua-config-section-heading border-b px-4 py-3">
          <h2 id="rename-client-title" className="text-base font-semibold">
            Rename {sourceName}
          </h2>
          <p className="ua-config-service-description mt-1 text-xs">
            Client Selection references will be updated automatically.
          </p>
        </div>
        <div className="space-y-2 p-4">
          <label htmlFor="rename-client-name" className="text-sm font-semibold">
            Client Name
          </label>
          <input
            id="rename-client-name"
            type="text"
            value={clientName}
            className="ua-config-input w-full rounded-lg border px-3 py-2"
            autoComplete="off"
            autoFocus
            onFocus={(event) => event.target.select()}
            onChange={(event) => setClientName(event.target.value)}
          />
          {normalizedName && !validName && (
            <p className="text-sm text-red-500">
              Use letters, numbers, hyphens or underscores, up to 64 characters.
            </p>
          )}
          {nameTaken && (
            <p className="text-sm text-red-500">
              A client with that name already exists.
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t px-4 py-3">
          <button
            type="button"
            className="ua-config-service-action rounded-lg border px-4 py-2 text-sm font-semibold"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="ua-config-save-button rounded-lg px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!validName || unchanged || nameTaken}
          >
            Rename Client
          </button>
        </div>
      </form>
    </div>
  );
}

function HelpResourcesModal({
  updateStatus,
  isCheckingForUpdates,
  onCheckForUpdates,
  onClose,
}) {
  const resourceGroups = window.UAHelpResourceGroups || [];
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

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-3 sm:p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="ua-config-modal flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-resources-title"
      >
        <div className="ua-config-section-heading flex items-start justify-between gap-4 border-b px-4 py-3 sm:px-5 sm:py-4">
          <div>
            <h2 id="help-resources-title" className="text-lg font-semibold">
              Help &amp; Resources
            </h2>
            <p className="ua-config-service-description mt-1 text-sm">
              Official Upload Assistant documentation and setup guides.
            </p>
          </div>
          <button
            type="button"
            className="ua-config-icon-button shrink-0"
            aria-label="Close help and resources"
            autoFocus
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
          <div className="ua-config-state-panel mb-4 rounded-lg border p-3 text-sm">
            These links open GitHub in a new tab, keeping guidance aligned with
            the upstream development documentation.
          </div>
          <section className="ua-config-state-panel mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
            <div className="min-w-0">
              <h3 className="text-sm font-semibold">Updates</h3>
              <p className="ua-config-service-description mt-1 text-xs">
                {updateMessage}
              </p>
            </div>
            <button
              type="button"
              className="ua-config-service-action shrink-0 rounded-lg border px-3 py-2 text-sm font-semibold disabled:cursor-wait disabled:opacity-60"
              disabled={isCheckingForUpdates}
              onClick={onCheckForUpdates}
            >
              {isCheckingForUpdates ? "Checking…" : "Check now"}
            </button>
          </section>
          <div className="grid gap-4 md:grid-cols-2">
            {resourceGroups.map((group) => (
              <section
                key={group.title}
                className="ua-config-state-panel rounded-xl border p-3 sm:p-4"
              >
                <h3 className="mb-3 text-sm font-semibold">{group.title}</h3>
                <div className="space-y-2">
                  {group.links.map((link) => (
                    <a
                      key={link.href}
                      href={link.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ua-config-folder-row flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5"
                    >
                      <span className="min-w-0">
                        <span className="block text-sm font-semibold">
                          {link.label}
                        </span>
                        <span className="ua-config-service-description mt-0.5 block text-xs">
                          {link.description}
                        </span>
                      </span>
                      <span
                        className="ua-config-service-action shrink-0 text-sm"
                        aria-hidden="true"
                      >
                        ↗
                      </span>
                    </a>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>

        <div className="flex justify-end border-t px-4 py-3 sm:px-5">
          <a
            href="https://github.com/wastaken7/Upload-Assistant/tree/development/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="ua-config-service-action rounded-lg border px-4 py-2 text-sm font-semibold"
          >
            Browse all documentation ↗
          </a>
        </div>
      </section>
    </div>
  );
}

function TorrentClientSettings({
  items,
  pathParts,
  isDarkMode,
  allImageHosts,
  usedImageHosts,
  torrentClients,
  onBrowseFolder,
  onValueChange,
}) {
  const editableItems = (items || []).filter(
    (item) => item.key !== "torrent_client",
  );
  const itemByKey = new Map(editableItems.map((item) => [item.key, item]));
  const linkingItem = itemByKey.get("linking");
  const [linkingValue, setLinkingValue] = useState(
    String(linkingItem?.value || ""),
  );

  useEffect(() => {
    setLinkingValue(String(linkingItem?.value || ""));
  }, [linkingItem?.value]);

  const handleValueChange = (path, value, meta) => {
    if (path[path.length - 1] === "linking") {
      setLinkingValue(String(value || ""));
    }
    onValueChange(path, value, meta);
  };

  const groupDefinitions = [
    {
      id: "connection",
      title: "Connection & Authentication",
      keys: [
        "qui_proxy_url",
        "qbit_url",
        "qbit_port",
        "qbit_user",
        "qbit_pass",
        "qbit_api_key",
        "rtorrent_url",
        "deluge_url",
        "deluge_port",
        "deluge_user",
        "deluge_pass",
        "transmission_protocol",
        "transmission_host",
        "transmission_port",
        "transmission_path",
        "transmission_username",
        "transmission_password",
      ],
    },
    {
      id: "storage",
      title: itemByKey.has("enable_search") ? "Search & Storage" : "Storage",
      keys: ["enable_search", "torrent_storage_dir"],
    },
    {
      id: "organization",
      title: "Tags & Categories",
      keys: [
        "super_seed_trackers",
        "use_tracker_as_tag",
        "qbit_tag",
        "qbit_cat",
        "qbit_cross_tag",
        "qbit_cross_cat",
        "content_layout",
        "rtorrent_label",
        "transmission_label",
      ],
    },
    {
      id: "linking",
      title: "Linking",
      keys: linkingValue
        ? ["linking", "allow_fallback", "linked_folder"]
        : ["linking"],
    },
    {
      id: "watch",
      title: "Watch Folder",
      keys: ["watch_folder"],
    },
  ];

  const groupedKeys = new Set(groupDefinitions.flatMap((group) => group.keys));
  groupedKeys.add("local_path");
  groupedKeys.add("remote_path");
  const groups = groupDefinitions
    .map((group) => ({
      ...group,
      items: group.keys.map((key) => itemByKey.get(key)).filter(Boolean),
    }))
    .filter((group) => group.items.length > 0);
  const additionalItems = editableItems.filter(
    (item) => !groupedKeys.has(item.key),
  );
  if (additionalItems.length > 0) {
    groups.push({
      id: "additional",
      title: "Additional Settings",
      items: additionalItems,
    });
  }

  const localPathItem = itemByKey.get("local_path");
  const remotePathItem = itemByKey.get("remote_path");

  const renderField = (item) => {
    const isWideList = ["super_seed_trackers", "linked_folder"].includes(
      item.key,
    );
    return (
      <div
        key={item.key}
        className={isWideList ? "md:col-span-2 xl:col-span-3" : ""}
      >
        <ConfigLeaf
          item={item}
          pathParts={pathParts}
          isDarkMode={isDarkMode}
          fullWidth={true}
          allImageHosts={allImageHosts}
          usedImageHosts={usedImageHosts}
          torrentClients={torrentClients}
          onBrowseFolder={onBrowseFolder}
          onValueChange={handleValueChange}
        />
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <section
          key={group.id}
          className="ua-config-client-settings-group overflow-hidden rounded-lg border"
        >
          <div className="ua-config-section-heading border-b px-4 py-2.5">
            <h3 className="text-sm font-semibold">{group.title}</h3>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {group.items.map(renderField)}
            </div>
            {group.id === "linking" && !linkingValue && (
              <p className="ua-config-service-description mt-3 text-xs">
                Choose Symbolic Link or Hard Link to configure linked folders
                and fallback behaviour.
              </p>
            )}
          </div>
        </section>
      ))}

      {localPathItem && remotePathItem && (
        <section className="ua-config-client-settings-group overflow-hidden rounded-lg border">
          <div className="ua-config-section-heading border-b px-4 py-2.5">
            <h3 className="text-sm font-semibold">Path Mapping</h3>
          </div>
          <div className="p-4">
            <PathMappingEditor
              localItem={localPathItem}
              remoteItem={remotePathItem}
              pathParts={pathParts}
              onBrowseFolder={onBrowseFolder}
              onValueChange={handleValueChange}
            />
          </div>
        </section>
      )}
    </div>
  );
}

function TrackerSettings({
  items,
  pathParts,
  isDarkMode,
  allImageHosts,
  usedImageHosts,
  torrentClients,
  overridesEnabled = false,
  onToggleOverrides = () => {},
  onValueChange,
}) {
  const editableItems = items || [];
  const itemByKey = new Map(editableItems.map((item) => [item.key, item]));
  const overrideItems = editableItems.filter((item) =>
    trackerDefaultOverrideKeys.has(item.key),
  );
  const groupDefinitions = [
    {
      id: "authentication",
      title: "Authentication & Connection",
      keys: [
        "api_key",
        "announce_url",
        "my_announce_url",
        "username",
        "password",
        "passkey",
        "cookie_file",
        "cookies",
        "ApiUser",
        "bhd_rss_key",
        "bioma_api_key",
        "ptgen_api",
        "base_url",
        "api_url",
        "url",
        "user_id",
        "login_question",
        "login_answer",
      ],
    },
    {
      id: "upload",
      title: "Upload Preferences",
      keys: [
        "anon",
        "featured",
        "doubleup",
        "sticky",
        "modq",
        "exclusive",
        "refundable",
        "draft",
        "draft_default",
        "uploader_status",
        "uploader_name",
        "show_group_if_anon",
        "double_upload_until",
        "freeleech_until",
        "api_upload",
      ],
    },
    {
      id: "validation",
      title: "Search & Validation",
      keys: [
        "use_for_search",
        "check_for_rules",
        "check_requests",
        "daily_api_hit_limit",
        "max_retries",
        "allow_ext_subtitles",
        "full_mediainfo",
        "force_data",
        "filebrowser",
        "image_count",
      ],
    },
    {
      id: "description",
      title: "Tracker Description Options",
      keys: ["custom_layout", "img_rehost", "add_web_source_to_desc"],
    },
    {
      id: "metadata",
      title: "Naming & Metadata",
      keys: [
        "use_metadata_name",
        "use_spanish_title",
        "use_german_title",
        "use_italian_title",
        "resolve_language",
      ],
    },
    {
      id: "advanced",
      title: "Advanced",
      keys: ["link_dir_name", "channel", "trackers"],
    },
  ];
  const groupedKeys = new Set(groupDefinitions.flatMap((group) => group.keys));
  const groups = groupDefinitions
    .map((group) => ({
      ...group,
      items: group.keys.map((key) => itemByKey.get(key)).filter(Boolean),
    }))
    .filter((group) => group.items.length > 0);
  const additionalItems = editableItems.filter(
    (item) =>
      !groupedKeys.has(item.key) && !trackerDefaultOverrideKeys.has(item.key),
  );
  if (additionalItems.length > 0) {
    groups.push({
      id: "additional",
      title: "Additional Settings",
      items: additionalItems,
    });
  }

  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <section
          key={group.id}
          className="ua-config-client-settings-group overflow-hidden rounded-lg border"
        >
          <div className="ua-config-section-heading border-b px-4 py-2.5">
            <h3 className="text-sm font-semibold">{group.title}</h3>
          </div>
          <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
            {group.items.map((item) => (
              <ConfigLeaf
                key={item.key}
                item={item}
                pathParts={pathParts}
                isDarkMode={isDarkMode}
                fullWidth={true}
                allImageHosts={allImageHosts}
                usedImageHosts={usedImageHosts}
                torrentClients={torrentClients}
                onValueChange={onValueChange}
              />
            ))}
          </div>
        </section>
      ))}
      {overrideItems.length > 0 && (
        <section className="ua-config-client-settings-group overflow-hidden rounded-lg border">
          <div className="ua-config-section-heading flex flex-col gap-3 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-sm font-semibold">
                Tracker-Specific DEFAULT Overrides
              </h3>
              <p className="ua-config-service-description mt-1 text-xs">
                Enable only when this tracker should use different description,
                screenshot, or injection settings from DEFAULT.
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <button
                type="button"
                onClick={() =>
                  onToggleOverrides(!overridesEnabled, overrideItems)
                }
                aria-pressed={overridesEnabled}
                aria-label={`Tracker-specific overrides: ${overridesEnabled ? "Enabled" : "Disabled"}`}
                className="ua-config-boolean-toggle relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
                data-enabled={overridesEnabled ? "true" : "false"}
              >
                <span
                  className={`ua-config-boolean-knob inline-block h-4 w-4 transform rounded-full transition-transform ${overridesEnabled ? "translate-x-6" : "translate-x-1"}`}
                />
              </button>
              <span className="text-sm font-medium">
                {overridesEnabled ? "Enabled" : "Disabled"}
              </span>
            </div>
          </div>
          {overridesEnabled ? (
            <div>
              <div className="ua-config-state-panel m-4 rounded-lg border p-4 text-sm">
                These values will override the matching DEFAULT settings for
                this tracker. Disable this section to remove them and restore
                DEFAULT inheritance.
              </div>
              <div className="grid grid-cols-1 gap-4 border-t p-4 md:grid-cols-2 xl:grid-cols-3">
                {overrideItems.map((item) => (
                  <ConfigLeaf
                    key={item.key}
                    item={item}
                    pathParts={pathParts}
                    isDarkMode={isDarkMode}
                    fullWidth={true}
                    allImageHosts={allImageHosts}
                    usedImageHosts={usedImageHosts}
                    torrentClients={torrentClients}
                    onValueChange={onValueChange}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="ua-config-state-panel m-4 rounded-lg border p-4 text-sm">
              This tracker currently inherits the matching DEFAULT settings.
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function DatabaseLinkImagesSettings({
  items,
  pathParts,
  isDarkMode,
  allImageHosts,
  usedImageHosts,
  torrentClients,
  onValueChange,
}) {
  const itemByKey = new Map((items || []).map((item) => [item.key, item]));
  const groups = [
    {
      id: "film-tv",
      title: "Film & TV Databases",
      keys: ["imdb_75", "tmdb_75", "tvdb_75", "tvmaze_75"],
    },
    {
      id: "anime",
      title: "Anime Databases",
      keys: ["mal_75"],
    },
  ]
    .map((group) => ({
      ...group,
      items: group.keys.map((key) => itemByKey.get(key)).filter(Boolean),
    }))
    .filter((group) => group.items.length > 0);
  const groupedKeys = new Set(groups.flatMap((group) => group.keys));
  const additionalItems = (items || []).filter(
    (item) => !groupedKeys.has(item.key),
  );
  if (additionalItems.length > 0) {
    groups.push({
      id: "additional",
      title: "Additional Database Images",
      items: additionalItems,
    });
  }

  return (
    <div className="space-y-4">
      <div className="ua-config-state-panel rounded-xl border p-4 text-sm">
        These URLs point to database icons used in AlphaRatio and TVChaosUK
        descriptions. They are not image-host API keys and normally do not need
        to be changed.
      </div>
      {groups.map((group) => (
        <section
          key={group.id}
          className="ua-config-section overflow-hidden rounded-xl border"
        >
          <div className="ua-config-section-heading border-b px-4 py-3">
            <h2 className="text-sm font-semibold">{group.title}</h2>
          </div>
          <div className="ua-config-section-panel grid grid-cols-1 gap-4 p-4 md:grid-cols-2">
            {group.items.map((item) => (
              <ConfigLeaf
                key={item.key}
                item={item}
                pathParts={pathParts}
                isDarkMode={isDarkMode}
                fullWidth={true}
                allImageHosts={allImageHosts}
                usedImageHosts={usedImageHosts}
                torrentClients={torrentClients}
                onValueChange={onValueChange}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function DescriptionImagesSection({
  section,
  isDarkMode,
  allImageHosts,
  usedImageHosts,
  torrentClients,
  onValueChange,
}) {
  return (
    <section className="ua-config-section overflow-hidden rounded-xl border">
      <div className="ua-config-section-heading border-b px-4 py-3">
        <h2 className="text-sm font-semibold">
          Tracker Database Icons (AlphaRatio &amp; TVChaosUK)
        </h2>
      </div>
      <div className="ua-config-section-panel p-4">
        <DatabaseLinkImagesSettings
          items={section.items}
          pathParts={[section.section]}
          isDarkMode={isDarkMode}
          allImageHosts={allImageHosts}
          usedImageHosts={usedImageHosts}
          torrentClients={torrentClients}
          onValueChange={onValueChange}
        />
      </div>
    </section>
  );
}

function TrackerManager({
  items,
  defaultTrackersItem,
  trackerView,
  trackerCatalog,
  pendingChanges = new Map(),
  pendingTrackerOverrideModes = new Map(),
  trackerOverrideEditors = new Set(),
  onToggleTrackerOverrides = () => {},
  pathParts,
  isDarkMode,
  allImageHosts,
  usedImageHosts,
  expandedGroups,
  toggleGroup,
  torrentClients,
  onRemoveTracker,
  onUndoRemoveTracker,
  onValueChange,
}) {
  const trackerItems = items || [];
  const trackerItemByName = new Map(
    trackerItems.map((item) => [String(item.key).toUpperCase(), item]),
  );
  const pendingTrackerValues = new Map();
  for (const update of pendingChanges.values()) {
    if (
      Array.isArray(update.path) &&
      update.path.length >= 3 &&
      String(update.path[0]).toUpperCase() === "TRACKERS"
    ) {
      const trackerName = String(update.path[1]).toUpperCase();
      if (!pendingTrackerValues.has(trackerName)) {
        pendingTrackerValues.set(trackerName, new Map());
      }
      pendingTrackerValues
        .get(trackerName)
        .set(String(update.path[2]), update.value);
    }
  }
  const normalizeTrackers = (value) =>
    String(value || "")
      .split(",")
      .map((tracker) => tracker.trim().toUpperCase())
      .filter(Boolean);
  const originalDefaults = normalizeTrackers(defaultTrackersItem.value);
  const originalDefaultSet = new Set(originalDefaults);
  const originalDefaultValue = defaultTrackersItem.value;
  const [selectedDefaults, setSelectedDefaults] = useState(originalDefaults);
  const [trackerQuery, setTrackerQuery] = useState("");

  useEffect(() => {
    setSelectedDefaults(normalizeTrackers(defaultTrackersItem.value));
  }, [defaultTrackersItem.value]);

  const defaultTrackersPathKey = [...pathParts, "default_trackers"].join("/");
  useEffect(() => {
    const resetDefaultTrackers = (event) => {
      if (String(event.detail?.pathKey) === defaultTrackersPathKey) {
        setSelectedDefaults(normalizeTrackers(defaultTrackersItem.value));
      }
    };
    window.addEventListener(CONFIG_FIELD_RESET_EVENT, resetDefaultTrackers);
    return () =>
      window.removeEventListener(
        CONFIG_FIELD_RESET_EVENT,
        resetDefaultTrackers,
      );
  }, [defaultTrackersItem.value, defaultTrackersPathKey]);

  useEffect(() => {
    setTrackerQuery("");
  }, [trackerView]);

  const fallbackNames = getAvailableTrackers(defaultTrackersItem).map((name) =>
    String(name).toUpperCase(),
  );
  const catalogEntries =
    trackerCatalog?.trackers?.length > 0
      ? trackerCatalog.trackers
      : fallbackNames.map((name) => ({
          name,
          display_name: getTrackerDisplayName(name),
          base_url: "",
          favicon: "",
          configured: selectedDefaults.includes(name),
        }));
  const catalogByName = new Map(
    catalogEntries.map((tracker) => [
      String(tracker.name).toUpperCase(),
      tracker,
    ]),
  );
  const displayName = (name) =>
    catalogByName.get(name)?.display_name || getTrackerDisplayName(name);
  const sortedEntries = catalogEntries
    .slice()
    .sort((left, right) =>
      String(left.display_name || left.name).localeCompare(
        String(right.display_name || right.name),
      ),
    );
  const defaultEntries = selectedDefaults.map(
    (name) =>
      catalogByName.get(name) || {
        name,
        display_name: getTrackerDisplayName(name),
        base_url: "",
        favicon: "",
        configured: true,
      },
  );
  const configuredEntries = sortedEntries.filter(
    (tracker) => tracker.configured,
  );
  const availableEntries = sortedEntries.filter(
    (tracker) => !tracker.configured,
  );
  const addableDefaultEntries = sortedEntries.filter((tracker) => {
    const name = String(tracker.name).toUpperCase();
    return (
      (tracker.configured || name === "MANUAL") &&
      !selectedDefaults.includes(name)
    );
  });

  const queueDefaultTrackers = (nextTrackers) => {
    setSelectedDefaults(nextTrackers);
    onValueChange([...pathParts, "default_trackers"], nextTrackers.join(", "), {
      originalValue: originalDefaultValue,
      isSensitive: false,
      isRedacted: false,
      readOnly: false,
    });
  };

  const addDefaultTracker = (trackerName) => {
    const normalized = String(trackerName || "").toUpperCase();
    if (!normalized || selectedDefaults.includes(normalized)) return;
    queueDefaultTrackers([...selectedDefaults, normalized]);
  };

  const removeDefaultTracker = (trackerName) => {
    const normalized = String(trackerName || "").toUpperCase();
    queueDefaultTrackers(
      selectedDefaults.filter((tracker) => tracker !== normalized),
    );
  };

  const trackerStatusBadge = (label, tone = "neutral") => (
    <span
      key={label}
      className="ua-config-tracker-status rounded-full border px-2 py-0.5 text-[0.68rem] font-semibold"
      data-tone={tone}
    >
      {label}
    </span>
  );

  const trackerIdentity = (tracker, statuses = []) => {
    const name = String(tracker.name).toUpperCase();
    return (
      <span className="flex min-w-0 items-center gap-3">
        <span className="ua-config-tracker-icon flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg border">
          {tracker.favicon ? (
            <img
              src={tracker.favicon}
              alt=""
              className="h-full w-full object-contain p-1"
            />
          ) : (
            <span className="text-xs font-bold">{name.slice(0, 2)}</span>
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <span className="min-w-0 truncate text-sm font-semibold">
              {tracker.display_name || getTrackerDisplayName(name)}
            </span>
            {statuses.length > 0 && (
              <span className="flex flex-wrap gap-1.5">
                {statuses.map((status) =>
                  trackerStatusBadge(status.label, status.tone),
                )}
              </span>
            )}
          </span>
          <span className="ua-config-service-description block truncate text-xs">
            {name}
          </span>
        </span>
      </span>
    );
  };

  const trackerSetupState = (tracker, trackerItem) => {
    if (!trackerItem) return { requirements: [], missing: [] };
    const name = String(tracker.name).toUpperCase();
    const fields = new Map(
      (trackerItem.children || []).map((item) => [String(item.key), item]),
    );
    const pendingValues = pendingTrackerValues.get(name) || new Map();
    const placeholderPattern =
      /<[^>]+>|\b(?:your|custom|insert|replace|example)\b|\b(?:api[ _-]?user|username|password|passkey)\b/i;
    const isComplete = (item) => {
      const value = pendingValues.has(item.key)
        ? pendingValues.get(item.key)
        : item.value;
      if (value === null || value === undefined || value === false)
        return false;
      if (typeof value !== "string") return true;
      const normalized = value.trim();
      if (!normalized) return false;
      const exampleValue =
        typeof item.example_value === "string" ? item.example_value.trim() : "";
      if (
        exampleValue &&
        normalized === exampleValue &&
        placeholderPattern.test(exampleValue)
      ) {
        return false;
      }
      return true;
    };
    const requirements = [];
    const addRequirement = (id, label, keys, options = {}) => {
      const requirementFields = keys
        .map((key) => fields.get(key))
        .filter(Boolean);
      if (requirementFields.length === 0 && !options.external) return;
      const complete = options.external
        ? Boolean(options.complete)
        : requirementFields.every(isComplete);
      requirements.push({ id, label, complete, note: options.note || "" });
    };

    addRequirement("api", "API credentials", ["ApiUser", "api_key"]);
    const announceKeys = fields.has("announce_url")
      ? fields.has("my_announce_url")
        ? ["announce_url", "my_announce_url"]
        : ["announce_url"]
      : ["my_announce_url"];
    addRequirement("announce", "Announce URL", announceKeys);
    addRequirement("account", "Account credentials", [
      "username",
      "password",
      "passkey",
    ]);
    if (String(tracker.auth_type || "").toLowerCase() === "cookies") {
      addRequirement("cookie", "Cookie file", [], {
        external: true,
        complete: tracker.cookie_configured,
        note: "Cookie files are managed in data/cookies outside this form.",
      });
    }

    return {
      requirements,
      missing: requirements.filter((requirement) => !requirement.complete),
    };
  };

  if (trackerView === "default") {
    return (
      <div className="space-y-4">
        <div className="ua-config-state-panel rounded-xl border p-4 text-sm">
          These trackers are selected automatically when an upload does not
          provide an explicit tracker list.
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 2xl:grid-cols-3">
          {defaultEntries.map((tracker) => {
            const name = String(tracker.name).toUpperCase();
            return (
              <div
                key={name}
                className="ua-config-tracker-card flex flex-col items-stretch justify-between gap-3 rounded-xl border p-3 sm:flex-row sm:items-center"
              >
                {trackerIdentity(tracker, [
                  { label: "Default", tone: "accent" },
                ])}
                <button
                  type="button"
                  className="w-full shrink-0 rounded-lg border border-red-500/40 px-2.5 py-1.5 text-xs font-semibold text-red-500 hover:bg-red-500/10 sm:w-auto"
                  onClick={() => removeDefaultTracker(name)}
                >
                  Remove
                </button>
              </div>
            );
          })}
        </div>
        {defaultEntries.length === 0 && (
          <div className="ua-config-state-panel rounded-xl border p-4 text-sm">
            No default trackers are selected.
          </div>
        )}
        {addableDefaultEntries.length > 0 ? (
          <div className="space-y-3 border-t pt-4">
            <div className="ua-config-state-panel rounded-xl border p-4 text-sm">
              These trackers are available but are not currently selected as
              defaults.
            </div>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 2xl:grid-cols-3">
              {addableDefaultEntries.map((tracker) => {
                const name = String(tracker.name).toUpperCase();
                return (
                  <div
                    key={name}
                    className="ua-config-tracker-card flex flex-col items-stretch justify-between gap-3 rounded-xl border p-3 sm:flex-row sm:items-center"
                  >
                    {trackerIdentity(
                      tracker,
                      tracker.configured
                        ? [{ label: "Configured", tone: "success" }]
                        : [],
                    )}
                    <button
                      type="button"
                      className="w-full shrink-0 rounded-lg border border-emerald-500/40 px-2.5 py-1.5 text-xs font-semibold text-emerald-500 hover:bg-emerald-500/10 sm:w-auto"
                      onClick={() => addDefaultTracker(name)}
                    >
                      Add
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="ua-config-state-panel rounded-xl border p-4 text-sm">
            {configuredEntries.length > 0
              ? "All configured trackers are already selected."
              : "Configure a tracker before adding it to your defaults."}
          </div>
        )}
      </div>
    );
  }

  const entries =
    trackerView === "configured" ? configuredEntries : availableEntries;
  const normalizedTrackerQuery = trackerQuery.trim().toLowerCase();
  const visibleEntries = normalizedTrackerQuery
    ? entries.filter((tracker) =>
        [tracker.name, tracker.display_name, tracker.base_url].some((value) =>
          String(value || "")
            .toLowerCase()
            .includes(normalizedTrackerQuery),
        ),
      )
    : entries;
  const emptyMessage = normalizedTrackerQuery
    ? "No trackers match that search."
    : trackerView === "configured"
      ? "No configured trackers were detected."
      : "All supported trackers are already configured.";

  return (
    <div className="space-y-4">
      <div className="ua-config-state-panel flex flex-col gap-2 rounded-xl border p-4 text-sm sm:flex-row sm:items-center sm:justify-between sm:gap-4">
        <span>
          {trackerView === "configured"
            ? "Manage tracker credentials, preferences and description overrides."
            : "Open a tracker, enter its required credentials, then save it to make it available for uploads."}
        </span>
        <span className="ua-config-service-description shrink-0 text-sm">
          {normalizedTrackerQuery
            ? `${visibleEntries.length} of ${entries.length}`
            : entries.length}{" "}
          {entries.length === 1 ? "tracker" : "trackers"}
        </span>
      </div>

      {entries.length > 0 && (
        <div className="relative">
          <label htmlFor={`tracker-search-${trackerView}`} className="sr-only">
            Search {trackerView} trackers
          </label>
          <input
            id={`tracker-search-${trackerView}`}
            type="search"
            value={trackerQuery}
            onChange={(event) => setTrackerQuery(event.target.value)}
            placeholder="Search by tracker name or acronym..."
            className="ua-config-input w-full rounded-lg border px-3 py-2"
          />
        </div>
      )}

      {visibleEntries.length === 0 && (
        <div className="ua-config-state-panel rounded-xl border p-5 text-sm">
          {emptyMessage}
        </div>
      )}

      {visibleEntries.map((tracker) => {
        const name = String(tracker.name).toUpperCase();
        const trackerItem = trackerItemByName.get(name);
        const groupKey = [...pathParts, name].join("/");
        const isOpen = expandedGroups.has(groupKey);
        const isDefault = selectedDefaults.includes(name);
        const isDefaultPending = isDefault !== originalDefaultSet.has(name);
        const isRemoving = trackerItem?.source === "removing";
        const isUnsaved =
          pendingTrackerValues.has(name) ||
          pendingTrackerOverrideModes.has(name) ||
          isDefaultPending;
        const statuses = [];
        if (tracker.configured && !isRemoving) {
          statuses.push({ label: "Configured", tone: "success" });
        }
        if (isDefault) statuses.push({ label: "Default", tone: "accent" });
        if (isRemoving) {
          statuses.push({ label: "Removal pending", tone: "danger" });
        } else if (isUnsaved) {
          statuses.push({ label: "Unsaved", tone: "warning" });
        }
        const setupState = trackerSetupState(tracker, trackerItem);
        const hasStoredOverrides = (trackerItem?.children || []).some(
          (item) =>
            trackerDefaultOverrideKeys.has(item.key) &&
            item.source === "config",
        );
        const overridesEnabled =
          hasStoredOverrides || trackerOverrideEditors.has(name);
        return (
          <section
            key={name}
            className="ua-config-accordion overflow-hidden rounded-xl border"
            data-open={isOpen ? "true" : "false"}
            data-removing={isRemoving ? "true" : "false"}
          >
            <div className="flex flex-col gap-2 p-2 sm:flex-row sm:items-center">
              <button
                type="button"
                className="ua-config-accordion-trigger flex min-w-0 flex-1 items-center justify-between gap-4 rounded-lg px-2 py-3 text-left"
                onClick={() => toggleGroup(groupKey)}
                aria-expanded={isOpen}
              >
                {trackerIdentity(tracker, statuses)}
                <span
                  className="ua-config-accordion-chevron shrink-0 transition-transform"
                  style={{
                    transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
                  }}
                  aria-hidden="true"
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="m9 18 6-6-6-6"></path>
                  </svg>
                </span>
              </button>
              {trackerView === "configured" ? (
                <button
                  type="button"
                  className="ua-config-tracker-default-action w-full shrink-0 rounded-lg border px-3 py-2 text-xs font-semibold sm:w-auto"
                  data-selected={isDefault ? "true" : "false"}
                  disabled={isRemoving}
                  onClick={() =>
                    isDefault
                      ? removeDefaultTracker(name)
                      : addDefaultTracker(name)
                  }
                >
                  {isDefault ? "Remove Default" : "Add to Defaults"}
                </button>
              ) : (
                <button
                  type="button"
                  className="ua-config-tracker-default-action w-full shrink-0 rounded-lg border px-3 py-2 text-xs font-semibold sm:w-auto"
                  onClick={() => toggleGroup(groupKey)}
                >
                  {isOpen ? "Close" : "Configure"}
                </button>
              )}
            </div>
            {isOpen && (
              <div className="ua-config-accordion-panel border-t p-4">
                {trackerView === "available" && (
                  <div className="ua-config-state-panel mb-4 rounded-lg border p-4 text-sm">
                    Enter the required authentication details and choose Save
                    Config. Once configured, this tracker will move to
                    Configured Trackers and can be added to your defaults.
                  </div>
                )}
                {setupState.requirements.length > 0 && (
                  <div
                    className="ua-config-tracker-setup mb-4 rounded-lg border p-4"
                    data-complete={
                      setupState.missing.length === 0 ? "true" : "false"
                    }
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <h3 className="text-sm font-semibold">
                          Setup requirements
                        </h3>
                        <p className="ua-config-service-description mt-1 text-xs">
                          Authentication detected from this tracker&apos;s
                          configuration template.
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {setupState.requirements.map((requirement) => (
                          <span
                            key={requirement.id}
                            className="ua-config-tracker-requirement rounded-full border px-2.5 py-1 text-xs font-semibold"
                            data-complete={
                              requirement.complete ? "true" : "false"
                            }
                          >
                            {requirement.complete ? "✓ " : "○ "}
                            {requirement.label}
                          </span>
                        ))}
                      </div>
                    </div>
                    {setupState.missing.length > 0 && (
                      <p className="ua-config-tracker-setup-warning mt-3 text-sm">
                        Setup may be incomplete. Check:{" "}
                        {setupState.missing
                          .map((requirement) => requirement.label)
                          .join(", ")}
                        .
                      </p>
                    )}
                    {setupState.requirements.some(
                      (requirement) => requirement.note,
                    ) && (
                      <p className="ua-config-service-description mt-2 text-xs">
                        {setupState.requirements
                          .filter((requirement) => requirement.note)
                          .map((requirement) => requirement.note)
                          .join(" ")}
                      </p>
                    )}
                  </div>
                )}
                {tracker.base_url && (
                  <a
                    href={tracker.base_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mb-4 inline-block max-w-full break-all text-xs"
                  >
                    {tracker.base_url}
                  </a>
                )}
                {trackerItem ? (
                  <TrackerSettings
                    items={trackerItem.children}
                    pathParts={[...pathParts, trackerItem.key]}
                    isDarkMode={isDarkMode}
                    allImageHosts={allImageHosts}
                    usedImageHosts={usedImageHosts}
                    torrentClients={torrentClients}
                    overridesEnabled={overridesEnabled}
                    onToggleOverrides={(enabled, overrideItems) =>
                      onToggleTrackerOverrides(name, enabled, overrideItems)
                    }
                    onValueChange={onValueChange}
                  />
                ) : (
                  <div className="ua-config-state-panel rounded-lg border p-4 text-sm">
                    No example configuration is available for this tracker.
                  </div>
                )}
                {trackerView === "configured" &&
                  trackerItem?.source === "removing" && (
                    <div className="ua-config-removal-panel mt-5 flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between">
                      <span className="text-sm">
                        This tracker configuration will be removed when you
                        save.
                      </span>
                      <button
                        type="button"
                        className="w-full rounded-lg border px-3 py-2 text-sm font-semibold sm:w-auto"
                        onClick={() => {
                          onUndoRemoveTracker(name);
                          if (trackerItem.wasDefaultBeforeRemoval) {
                            addDefaultTracker(name);
                          }
                        }}
                      >
                        Undo
                      </button>
                    </div>
                  )}
                {trackerView === "configured" &&
                  trackerItem?.source === "config" && (
                    <div className="mt-5 flex justify-end border-t pt-4">
                      <button
                        type="button"
                        className="w-full rounded-lg border border-red-500/50 px-3 py-2 text-sm font-semibold text-red-500 hover:bg-red-500/10 sm:w-auto"
                        onClick={async () => {
                          const confirmed = await showConfirmModal({
                            title: "Remove tracker configuration",
                            message: isDefault
                              ? `Remove the saved configuration for ${displayName(name)} and remove it from your default trackers?${tracker.cookie_configured ? " Its cookie file will not be deleted, so it may remain listed as Configured." : ""}`
                              : `Remove the saved configuration for ${displayName(name)}?${tracker.cookie_configured ? " Its cookie file will not be deleted, so it may remain listed as Configured." : ""}`,
                            confirmLabel: "Remove Configuration",
                          });
                          if (!confirmed) return;
                          onRemoveTracker(name, isDefault);
                          if (isDefault) {
                            removeDefaultTracker(name);
                          }
                        }}
                      >
                        Remove Configuration
                      </button>
                    </div>
                  )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function ItemList({
  items,
  pathParts,
  depth,
  isDarkMode,
  allImageHosts,
  usedImageHosts,
  fullWidth,
  expandedGroups,
  toggleGroup,
  torrentClients,
  clientSelectionItem,
  trackerView,
  trackerCatalog,
  pendingChanges,
  pendingTrackerOverrideModes,
  trackerOverrideEditors,
  onToggleTrackerOverrides,
  onAddTorrentClient,
  onRemovePendingTorrentClient,
  onRenameTorrentClient,
  onTestTorrentClient,
  onRemoveTorrentClient,
  onUndoRemoveTorrentClient,
  onRemoveTracker,
  onUndoRemoveTracker,
  clientTestStates,
  onBrowseFolder,
  onValueChange,
}) {
  // Group items into regular fields and subsections
  const regularItems = [];
  const subsections = [];

  for (const item of items || []) {
    if (item.children && item.children.length) {
      subsections.push(item);
    } else {
      regularItems.push(item);
    }
  }

  // The tracker manager needs the default list separately from tracker blocks.
  const isTrackerConfig = pathParts.includes("TRACKERS") && depth === 0;
  const isTorrentClientsRoot =
    pathParts.includes("TORRENT_CLIENTS") && depth === 0;
  const configuredTorrentClientNames = new Set(
    (torrentClients || []).map((name) => String(name).toLowerCase()),
  );
  const userTorrentClientItems = isTorrentClientsRoot
    ? subsections.filter((item) =>
        ["config", "pending", "renaming", "removing"].includes(item.source),
      )
    : [];
  const configuredTorrentClientItems = isTorrentClientsRoot
    ? userTorrentClientItems.filter((item) =>
        configuredTorrentClientNames.has(String(item.key).toLowerCase()),
      )
    : [];
  let defaultTrackersItem = null;
  if (isTrackerConfig) {
    const idx = regularItems.findIndex((it) => it.key === "default_trackers");
    if (idx >= 0) {
      defaultTrackersItem = regularItems.splice(idx, 1)[0];
    }
  }

  if (isTrackerConfig && defaultTrackersItem) {
    return (
      <TrackerManager
        items={subsections}
        defaultTrackersItem={defaultTrackersItem}
        trackerView={trackerView || "default"}
        trackerCatalog={trackerCatalog}
        pendingChanges={pendingChanges}
        pendingTrackerOverrideModes={pendingTrackerOverrideModes}
        pathParts={pathParts}
        isDarkMode={isDarkMode}
        allImageHosts={allImageHosts}
        usedImageHosts={usedImageHosts}
        expandedGroups={expandedGroups}
        toggleGroup={toggleGroup}
        torrentClients={torrentClients}
        trackerOverrideEditors={trackerOverrideEditors}
        onToggleTrackerOverrides={onToggleTrackerOverrides}
        onRemoveTracker={onRemoveTracker}
        onUndoRemoveTracker={onUndoRemoveTracker}
        onValueChange={onValueChange}
      />
    );
  }

  if (pathParts[0] === "IMAGES" && depth === 0) {
    return (
      <DatabaseLinkImagesSettings
        items={regularItems}
        pathParts={pathParts}
        isDarkMode={isDarkMode}
        allImageHosts={allImageHosts}
        usedImageHosts={usedImageHosts}
        torrentClients={torrentClients}
        onValueChange={onValueChange}
      />
    );
  }

  // Define known subgroupings for better visual breakdown (screenshots-related)
  const subgroupDefinitions = {
    "HDR Tonemapping": [
      "tone_map",
      "algorithm",
      "desat",
      "use_libplacebo",
      "ffmpeg_is_good",
      "ffmpeg_warmup",
    ],
    "Screenshot Overlays": ["frame_overlay", "overlay_text_size"],
    "Blu-ray & DVD": [
      "use_largest_playlist",
      "get_bluray_info",
      "bluray_score",
      "bluray_single_score",
      "ping_unit3d",
    ],
    Headers: [
      "custom_description_header",
      "tonemapped_header",
      "screenshot_header",
    ],
    Signature: ["custom_signature"],
    Sonarr: [
      "use_sonarr",
      "sonarr_url",
      "sonarr_api_key",
      "sonarr_url_1",
      "sonarr_api_key_1",
    ],
    Radarr: [
      "use_radarr",
      "radarr_url",
      "radarr_api_key",
      "radarr_url_1",
      "radarr_api_key_1",
    ],
  };

  const isImageHostingSection =
    pathParts[0] === "DEFAULT" &&
    regularItems.some((item) => item.key === "img_host_1") &&
    regularItems.some((item) => item.key === "smart_image_host_selection");
  const isScreenshotCaptureProcessingSection =
    pathParts[0] === "DEFAULT" &&
    regularItems.some((item) => item.key === "screens") &&
    regularItems.some((item) => item.key === "ffmpeg_compression");
  const isScreenshotEnhancementsSection =
    pathParts[0] === "DEFAULT" &&
    regularItems.some((item) => item.key === "tone_map") &&
    regularItems.some((item) => item.key === "frame_overlay");

  // Partition regularItems into subgroups and an "Other" bucket
  const grouped = {};
  const ungrouped = [];
  if (isImageHostingSection) {
    grouped["Image Hosts"] = [];
    grouped["Image Host API Keys"] = [];
    grouped["Upload Behavior"] = [];
  } else if (isScreenshotCaptureProcessingSection) {
    grouped["Screenshot Capture"] = [];
    grouped["FFmpeg Processing"] = [];
  }
  // Pre-create keys for consistent ordering for other subgroup definitions
  for (const g of Object.keys(subgroupDefinitions)) grouped[g] = [];

  for (const it of regularItems) {
    if (isImageHostingSection) {
      if (it.key && it.key.startsWith && it.key.startsWith("img_host_")) {
        grouped["Image Hosts"].push(it);
      } else if (getImageHostForApiKey(it.key)) {
        grouped["Image Host API Keys"].push(it);
      } else {
        grouped["Upload Behavior"].push(it);
      }
      continue;
    }
    if (isScreenshotCaptureProcessingSection) {
      if (
        ["screens", "cutoff_screens", "scale_screenshots_for_par"].includes(
          it.key,
        )
      ) {
        grouped["Screenshot Capture"].push(it);
      } else {
        grouped["FFmpeg Processing"].push(it);
      }
      continue;
    }

    let placed = false;
    for (const [gname, keys] of Object.entries(subgroupDefinitions)) {
      if (keys.includes(it.key)) {
        grouped[gname].push(it);
        placed = true;
        break;
      }
    }
    if (!placed) ungrouped.push(it);
  }

  if (isScreenshotCaptureProcessingSection) {
    const ffmpegFieldOrder = [
      "ffmpeg_limit",
      "process_limit",
      "ffmpeg_compression",
    ];
    grouped["FFmpeg Processing"].sort((left, right) => {
      const leftIndex = ffmpegFieldOrder.indexOf(left.key);
      const rightIndex = ffmpegFieldOrder.indexOf(right.key);
      return (
        (leftIndex === -1 ? ffmpegFieldOrder.length : leftIndex) -
        (rightIndex === -1 ? ffmpegFieldOrder.length : rightIndex)
      );
    });
  }

  return (
    <div className="space-y-6">
      {isTorrentClientsRoot && (
        <React.Fragment>
          {clientSelectionItem && (
            <section className="ua-config-section relative overflow-visible rounded-xl border">
              <div className="ua-config-section-heading border-b px-4 py-3">
                <h2 className="text-sm font-semibold">Client Selection</h2>
                <p className="ua-config-service-description mt-1 text-xs">
                  Choose the default client and optional clients used for
                  injection and torrent searches.
                </p>
              </div>
              <div className="ua-config-section-panel grid grid-cols-1 gap-4 p-4 lg:grid-cols-3">
                {(clientSelectionItem.children || []).map((item) => (
                  <ConfigLeaf
                    key={`DEFAULT/${item.key}`}
                    item={item}
                    pathParts={["DEFAULT"]}
                    depth={0}
                    isDarkMode={isDarkMode}
                    fullWidth={true}
                    allImageHosts={allImageHosts}
                    usedImageHosts={usedImageHosts}
                    torrentClients={torrentClients}
                    onValueChange={onValueChange}
                  />
                ))}
              </div>
            </section>
          )}
          <TorrentClientCreator
            templateItems={subsections}
            configuredNames={
              new Set(
                userTorrentClientItems.map((item) =>
                  String(item.key).toLowerCase(),
                ),
              )
            }
            onAddClient={onAddTorrentClient}
          />
          <div className="flex items-end justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold">Configured Clients</h2>
              <p className="ua-config-page-subtitle mt-1 text-sm">
                Open a client to edit its connection, paths and injection
                settings.
              </p>
            </div>
            <span className="ua-config-service-description shrink-0 text-sm">
              {configuredTorrentClientItems.length}{" "}
              {configuredTorrentClientItems.length === 1 ? "client" : "clients"}
            </span>
          </div>
          {configuredTorrentClientItems.length === 0 && (
            <div className="ua-config-state-panel rounded-xl border p-5 text-sm">
              No torrent clients are configured yet. Use Add Torrent Client to
              create one.
            </div>
          )}
        </React.Fragment>
      )}
      {/* Regular form fields, optionally grouped into subheaders */}
      {(ungrouped.length > 0 ||
        Object.values(grouped).some((g) => g.length > 0)) && (
        <div className="space-y-4">
          {/* Ungrouped items */}
          {ungrouped.length > 0 && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
              {ungrouped.map((item) => {
                const leafPath = [...pathParts, item.key].join("/");
                return (
                  <ConfigLeaf
                    key={leafPath}
                    item={item}
                    pathParts={pathParts}
                    depth={depth}
                    isDarkMode={isDarkMode}
                    fullWidth={fullWidth}
                    allImageHosts={allImageHosts}
                    usedImageHosts={usedImageHosts}
                    torrentClients={torrentClients}
                    onValueChange={onValueChange}
                  />
                );
              })}
            </div>
          )}

          {/* Grouped subheaders */}
          {Object.keys(grouped).map((gname) => {
            const itemsInGroup = grouped[gname] || [];
            if (!itemsInGroup.length) return null;
            if (
              isImageHostingSection ||
              isScreenshotCaptureProcessingSection ||
              isScreenshotEnhancementsSection
            ) {
              const subgroupParentKey = isImageHostingSection
                ? "IMAGE HOSTING"
                : isScreenshotCaptureProcessingSection
                  ? "SCREENSHOT CAPTURE AND PROCESSING"
                  : "SCREENSHOT ENHANCEMENTS";
              const subgroupKey = [...pathParts, subgroupParentKey, gname].join(
                "/",
              );
              return (
                <section
                  key={subgroupKey}
                  className="ua-config-section overflow-hidden rounded-xl border"
                >
                  <div className="ua-config-section-heading border-b px-4 py-3">
                    <h3 className="text-sm font-semibold">{gname}</h3>
                  </div>
                  <div className="ua-config-section-panel p-4">
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                      {itemsInGroup.map((item) => {
                        const leafPath = [...pathParts, item.key].join("/");
                        return (
                          <ConfigLeaf
                            key={leafPath}
                            item={item}
                            pathParts={pathParts}
                            depth={depth}
                            isDarkMode={isDarkMode}
                            fullWidth={fullWidth}
                            allImageHosts={allImageHosts}
                            usedImageHosts={usedImageHosts}
                            torrentClients={torrentClients}
                            onValueChange={onValueChange}
                          />
                        );
                      })}
                    </div>
                  </div>
                </section>
              );
            }
            const headerClass = isDarkMode
              ? "text-sm font-semibold text-gray-200 border-b pb-1 mb-3"
              : "text-sm font-semibold text-gray-700 border-b pb-1 mb-3";
            return (
              <div key={gname}>
                <div className={headerClass}>{gname}</div>
                <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                  {itemsInGroup.map((item) => {
                    const leafPath = [...pathParts, item.key].join("/");
                    return (
                      <ConfigLeaf
                        key={leafPath}
                        item={item}
                        pathParts={pathParts}
                        depth={depth}
                        isDarkMode={isDarkMode}
                        fullWidth={fullWidth}
                        allImageHosts={allImageHosts}
                        usedImageHosts={usedImageHosts}
                        torrentClients={torrentClients}
                        onValueChange={onValueChange}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Subsections */}
      {subsections.map((item) => {
        const isTorrentClientConfig =
          pathParts.includes("TORRENT_CLIENTS") && depth === 0;
        if (
          isTorrentClientConfig &&
          !configuredTorrentClientNames.has(String(item.key).toLowerCase())
        ) {
          return null;
        }
        const isMetadataCachingSubsection =
          pathParts[0] === "DEFAULT" &&
          depth === 0 &&
          item.subsection === true &&
          normalizeConfigHeading(item.key) === "METADATA CACHING";
        const isImageHostingSubsection =
          pathParts[0] === "DEFAULT" &&
          depth === 0 &&
          item.subsection === true &&
          normalizeConfigHeading(item.key) === "IMAGE HOSTING";
        const isScreenshotCaptureProcessingSubsection =
          pathParts[0] === "DEFAULT" &&
          depth === 0 &&
          item.subsection === true &&
          normalizeConfigHeading(item.key) ===
            "SCREENSHOT CAPTURE AND PROCESSING";
        const isScreenshotEnhancementsSubsection =
          pathParts[0] === "DEFAULT" &&
          depth === 0 &&
          item.subsection === true &&
          normalizeConfigHeading(item.key) === "SCREENSHOT ENHANCEMENTS";
        const isGeneralDescriptionSettingsSubsection =
          pathParts[0] === "DEFAULT" &&
          depth === 0 &&
          item.subsection === true &&
          normalizeConfigHeading(item.key) === "GENERAL DESCRIPTION SETTINGS";
        const isDescriptionHeadersOverridesSubsection =
          pathParts[0] === "DEFAULT" &&
          depth === 0 &&
          item.subsection === true &&
          normalizeConfigHeading(item.key) ===
            "DESCRIPTION HEADERS AND OVERRIDES";
        const isStaticSubsection =
          item.subsection === true && !isMetadataCachingSubsection;
        const isCollapsible = isTorrentClientConfig;
        const nextPath = item.subsection ? pathParts : [...pathParts, item.key];
        const nextDepth = item.subsection ? depth : depth + 1;
        const groupKey = [...pathParts, item.key].join("/");
        const isOpen = expandedGroups.has(groupKey);
        const torrentClientType = isTorrentClientConfig
          ? (item.children || []).find(
              (child) => child.key === "torrent_client",
            )?.value
          : "";
        const clientTestState = isTorrentClientConfig
          ? clientTestStates?.get(String(item.key).toLowerCase())
          : null;

        if (isMetadataCachingSubsection) {
          const serviceOverrides = (item.children || []).find(
            (child) => child.key === "metadata_cache_services",
          );
          const cacheSettings = (item.children || []).filter(
            (child) => child.key !== "metadata_cache_services",
          );
          return (
            <React.Fragment key={groupKey}>
              <section className="ua-config-section overflow-hidden rounded-xl border">
                <div className="ua-config-section-heading border-b px-4 py-3">
                  <h2 className="text-sm font-semibold">Metadata Cache</h2>
                </div>
                <div className="ua-config-section-panel p-4">
                  <ItemList
                    items={cacheSettings}
                    pathParts={pathParts}
                    depth={depth}
                    isDarkMode={isDarkMode}
                    allImageHosts={allImageHosts}
                    usedImageHosts={usedImageHosts}
                    fullWidth={true}
                    expandedGroups={expandedGroups}
                    toggleGroup={toggleGroup}
                    torrentClients={torrentClients}
                    onValueChange={onValueChange}
                  />
                </div>
              </section>
              {serviceOverrides && (
                <MetadataCacheServices
                  item={serviceOverrides}
                  pathParts={pathParts}
                  depth={depth}
                  isDarkMode={isDarkMode}
                  allImageHosts={allImageHosts}
                  usedImageHosts={usedImageHosts}
                  expandedGroups={expandedGroups}
                  toggleGroup={toggleGroup}
                  torrentClients={torrentClients}
                  onValueChange={onValueChange}
                />
              )}
            </React.Fragment>
          );
        }

        if (isGeneralDescriptionSettingsSubsection) {
          const logoKeys = new Set(["add_logo", "logo_size", "logo_language"]);
          const logoSettings = (item.children || []).filter((child) =>
            logoKeys.has(child.key),
          );
          const generalDescriptionSettings = (item.children || []).filter(
            (child) => !logoKeys.has(child.key),
          );

          const renderDescriptionSettings = (heading, settings) => (
            <section className="ua-config-section overflow-hidden rounded-xl border">
              <div className="ua-config-section-heading border-b px-4 py-3">
                <h2 className="text-sm font-semibold">{heading}</h2>
              </div>
              <div className="ua-config-section-panel p-4">
                <ItemList
                  items={settings}
                  pathParts={pathParts}
                  depth={depth}
                  isDarkMode={isDarkMode}
                  allImageHosts={allImageHosts}
                  usedImageHosts={usedImageHosts}
                  fullWidth={true}
                  expandedGroups={expandedGroups}
                  toggleGroup={toggleGroup}
                  torrentClients={torrentClients}
                  onValueChange={onValueChange}
                />
              </div>
            </section>
          );

          return (
            <React.Fragment key={groupKey}>
              {renderDescriptionSettings(
                "General Description Settings",
                generalDescriptionSettings,
              )}
              {renderDescriptionSettings("Logo Settings", logoSettings)}
            </React.Fragment>
          );
        }

        if (isDescriptionHeadersOverridesSubsection) {
          const releaseGroupOverrides = (item.children || []).find(
            (child) => child.key === "tag_overrides",
          );
          const descriptionSettings = (item.children || []).filter(
            (child) => child.key !== "tag_overrides",
          );

          return (
            <React.Fragment key={groupKey}>
              <section className="ua-config-section overflow-hidden rounded-xl border">
                <div className="ua-config-section-heading border-b px-4 py-3">
                  <h2 className="text-sm font-semibold">
                    Description Headers and Signature
                  </h2>
                </div>
                <div className="ua-config-section-panel p-4">
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                    {descriptionSettings.map((field) => (
                      <ConfigLeaf
                        key={`${groupKey}/${field.key}`}
                        item={field}
                        pathParts={pathParts}
                        depth={depth}
                        isDarkMode={isDarkMode}
                        fullWidth={true}
                        allImageHosts={allImageHosts}
                        usedImageHosts={usedImageHosts}
                        torrentClients={torrentClients}
                        onValueChange={onValueChange}
                      />
                    ))}
                  </div>
                </div>
              </section>
              {releaseGroupOverrides && (
                <ReleaseGroupOverrides
                  item={releaseGroupOverrides}
                  pathParts={pathParts}
                  depth={depth}
                  isDarkMode={isDarkMode}
                  allImageHosts={allImageHosts}
                  usedImageHosts={usedImageHosts}
                  expandedGroups={expandedGroups}
                  toggleGroup={toggleGroup}
                  torrentClients={torrentClients}
                  onValueChange={onValueChange}
                />
              )}
            </React.Fragment>
          );
        }

        const nested = isTorrentClientConfig ? (
          <TorrentClientSettings
            items={item.children}
            pathParts={nextPath}
            isDarkMode={isDarkMode}
            allImageHosts={allImageHosts}
            usedImageHosts={usedImageHosts}
            torrentClients={torrentClients}
            onBrowseFolder={onBrowseFolder}
            onValueChange={onValueChange}
          />
        ) : (
          <ItemList
            items={item.children}
            pathParts={nextPath}
            depth={nextDepth}
            isDarkMode={isDarkMode}
            allImageHosts={allImageHosts}
            usedImageHosts={usedImageHosts}
            fullWidth={isStaticSubsection || isCollapsible}
            expandedGroups={expandedGroups}
            toggleGroup={toggleGroup}
            torrentClients={torrentClients}
            onValueChange={onValueChange}
          />
        );

        if (
          isImageHostingSubsection ||
          isScreenshotCaptureProcessingSubsection ||
          isScreenshotEnhancementsSubsection
        ) {
          return <React.Fragment key={groupKey}>{nested}</React.Fragment>;
        }

        if (isStaticSubsection) {
          return (
            <section
              key={groupKey}
              className="ua-config-section overflow-hidden rounded-xl border"
            >
              <div className="ua-config-section-heading border-b px-4 py-3">
                <h2 className="text-sm font-semibold">
                  {formatConfigHeading(item.key)}
                </h2>
              </div>
              <div className="ua-config-section-panel p-4">{nested}</div>
            </section>
          );
        }

        if (isCollapsible) {
          return (
            <div
              key={groupKey}
              className="ua-config-accordion overflow-hidden rounded-xl border"
              data-open={isOpen ? "true" : "false"}
            >
              <button
                type="button"
                onClick={() => toggleGroup(groupKey)}
                className="ua-config-accordion-trigger flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-semibold"
                aria-expanded={isOpen}
              >
                <span>
                  {item.subsection === true ? (
                    formatConfigHeading(item.key)
                  ) : isTorrentClientConfig ? (
                    <span className="flex flex-wrap items-center gap-2">
                      <span>{getConfigBlockLabel(item.key)}</span>
                      {torrentClientType && (
                        <span className="ua-config-client-type rounded-full px-2 py-0.5 text-xs font-medium">
                          {TORRENT_CLIENT_TYPE_LABELS[
                            String(torrentClientType).toLowerCase()
                          ] || formatDisplayLabel(torrentClientType)}
                        </span>
                      )}
                      {item.source === "removing" && (
                        <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-500">
                          Pending removal
                        </span>
                      )}
                      {item.source === "renaming" && (
                        <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-500">
                          Renamed from {item.renamedFrom}
                        </span>
                      )}
                    </span>
                  ) : (
                    getTrackerDisplayName(item.key)
                  )}
                </span>
                <span
                  className="ua-config-accordion-chevron text-lg transition-transform"
                  style={{
                    transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
                  }}
                  aria-hidden="true"
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="m9 18 6-6-6-6"></path>
                  </svg>
                </span>
              </button>
              {isOpen && (
                <div className="ua-config-accordion-panel border-t p-4">
                  {item.source === "removing" ? (
                    <div className="ua-config-state-panel rounded-lg border p-4 text-sm">
                      This client will be removed when you save the
                      configuration.
                    </div>
                  ) : (
                    nested
                  )}
                  {isTorrentClientConfig &&
                    ["config", "pending", "renaming", "removing"].includes(
                      item.source,
                    ) && (
                      <div className="mt-5 space-y-3 border-t pt-4">
                        {clientTestState?.message && (
                          <div
                            className={
                              "rounded-lg border px-3 py-2 text-sm " +
                              (clientTestState.status === "success"
                                ? "border-green-500/40 text-green-500"
                                : clientTestState.status === "error"
                                  ? "border-red-500/40 text-red-500"
                                  : "ua-config-service-description")
                            }
                            role="status"
                          >
                            {clientTestState.message}
                          </div>
                        )}
                        <div className="flex flex-wrap justify-end gap-2">
                          {item.source !== "removing" && (
                            <React.Fragment>
                              <button
                                type="button"
                                className="ua-config-service-action rounded-lg border px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                                disabled={clientTestState?.status === "loading"}
                                onClick={() => onTestTorrentClient(item.key)}
                              >
                                {clientTestState?.status === "loading"
                                  ? "Testing..."
                                  : "Test Connection"}
                              </button>
                              <button
                                type="button"
                                className="ua-config-service-action rounded-lg border px-3 py-2 text-sm font-semibold"
                                onClick={() => onRenameTorrentClient(item.key)}
                              >
                                Rename Client
                              </button>
                            </React.Fragment>
                          )}
                          <button
                            type="button"
                            className="rounded-lg border border-red-500/50 px-3 py-2 text-sm font-semibold text-red-500 hover:bg-red-500/10"
                            onClick={async () => {
                              if (item.source === "pending") {
                                onRemovePendingTorrentClient(item.key);
                                return;
                              }
                              if (item.source === "removing") {
                                onUndoRemoveTorrentClient(item.key);
                                return;
                              }
                              await onRemoveTorrentClient(item.key);
                            }}
                          >
                            {item.source === "pending"
                              ? "Discard Client"
                              : item.source === "removing"
                                ? "Undo Removal"
                                : "Remove Client"}
                          </button>
                        </div>
                      </div>
                    )}
                </div>
              )}
            </div>
          );
        }

        return <div key={groupKey}>{nested}</div>;
      })}
    </div>
  );
}

// Promise-based confirmation modal to avoid blocking `confirm()`.
// Returns a Promise that resolves to true (confirmed) or false (cancelled).
function showConfirmModal(opts) {
  // Accept either a string (message) or an options object { title, message, confirmLabel }
  const options = typeof opts === "string" ? { message: opts } : opts || {};
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className =
      "ua-confirm-overlay fixed inset-0 z-50 flex items-center justify-center";
    overlay.style.background = "rgba(0,0,0,0.4)";

    const dlg = document.createElement("div");
    dlg.className =
      "ua-confirm-dialog max-w-md w-full rounded-lg p-4 bg-white text-gray-900";
    dlg.style.boxShadow = "0 10px 30px rgba(0,0,0,0.3)";

    const msg = document.createElement("div");
    msg.className = "mb-4 text-sm";
    msg.textContent = options.message || "";

    if (options.title) {
      const titleEl = document.createElement("div");
      titleEl.className = "mb-2 font-semibold";
      titleEl.textContent = options.title;
      dlg.appendChild(titleEl);
    }

    const btnRow = document.createElement("div");
    btnRow.className = "flex justify-end gap-2";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "px-3 py-1 rounded bg-gray-200";
    cancelBtn.textContent = "Cancel";

    const okBtn = document.createElement("button");
    okBtn.type = "button";
    okBtn.className = "px-3 py-1 rounded bg-red-600 text-white";
    okBtn.textContent = options.confirmLabel || "Remove";

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(okBtn);
    dlg.appendChild(msg);
    dlg.appendChild(btnRow);
    overlay.appendChild(dlg);
    document.body.appendChild(overlay);

    // Focus management
    okBtn.focus();

    function cleanup(result) {
      try {
        document.body.removeChild(overlay);
      } catch (e) {
        /* ignore */
      }
      try {
        window.removeEventListener("keydown", keyHandler);
      } catch (e) {
        /* ignore */
      }
      resolve(result);
    }

    cancelBtn.addEventListener("click", () => cleanup(false));
    okBtn.addEventListener("click", () => cleanup(true));
    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) cleanup(false);
    });
    // Keyboard handling
    function keyHandler(ev) {
      if (ev.key === "Escape") {
        ev.preventDefault();
        cleanup(false);
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        cleanup(true);
      }
    }
    window.addEventListener("keydown", keyHandler, { once: true });
  });
}

function SecurityTab({ isDarkMode }) {
  const [twofaStatus, setTwofaStatus] = useState(null);
  const [setupData, setSetupData] = useState(null);
  const [verificationCode, setVerificationCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  // API tokens
  const [tokens, setTokens] = useState([]);
  const [tokensLoading, setTokensLoading] = useState(false);
  const [tokensReadOnly, setTokensReadOnly] = useState(false);
  const [newTokenLabel, setNewTokenLabel] = useState("");
  const [createdTokenRaw, setCreatedTokenRaw] = useState(null);
  const [tokenMessage, setTokenMessage] = useState("");
  const [createdTokenCopied, setCreatedTokenCopied] = useState(false);

  useEffect(() => {
    loadTwofaStatus();
    loadTokens();
  }, []);

  const loadTwofaStatus = async () => {
    try {
      const response = await apiFetch(`${API_BASE}/2fa/status`);
      if (!response.ok) {
        console.error(`Failed to load 2FA status: HTTP ${response.status}`);
        return;
      }
      const data = await response.json();
      if (data && typeof data.enabled === "boolean") {
        setTwofaStatus(data.enabled);
      } else {
        console.warn(
          "Unexpected 2FA status response shape, defaulting to disabled",
          data,
        );
        setTwofaStatus(false);
      }
    } catch (error) {
      console.error("Failed to load 2FA status:", error);
    }
  };

  const handleSetup2FA = async () => {
    setLoading(true);
    setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/2fa/setup`, {
        method: "POST",
      });
      const data = await response.json();
      if (data.success) {
        setSetupData(data);
        setRecoveryCodes(data.recovery_codes || null);
        setMessage(
          "Scan the QR code with your authenticator app, then enter the 6-digit code below.",
        );
      } else {
        setMessage(data.error || "Failed to setup 2FA");
      }
    } catch (error) {
      setMessage("Failed to setup 2FA");
    }
    setLoading(false);
  };

  const handleVerifyAndEnable = async () => {
    if (!verificationCode || verificationCode.length !== 6) {
      setMessage("Please enter a valid 6-digit code");
      return;
    }

    setLoading(true);
    setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/2fa/enable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: verificationCode }),
      });
      const data = await response.json();
      if (data.success) {
        setTwofaStatus(true);
        setSetupData(null);
        setVerificationCode("");
        setRecoveryCodes(data.recovery_codes || null);
        setMessage("2FA has been enabled successfully!");
      } else {
        setMessage(data.error || "Failed to enable 2FA");
      }
    } catch (error) {
      setMessage("Failed to enable 2FA");
    }
    setLoading(false);
  };

  const handleDisable2FA = async () => {
    const confirmed = await showConfirmModal({
      title: "Disable Two-Factor Authentication",
      message:
        "Are you sure you want to disable 2FA? This will make your account less secure.",
      confirmLabel: "Disable",
    });
    if (!confirmed) return;

    setLoading(true);
    setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/2fa/disable`, {
        method: "POST",
      });
      const data = await response.json();
      if (data.success) {
        setTwofaStatus(false);
        setMessage("2FA has been disabled.");
      } else {
        setMessage(data.error || "Failed to disable 2FA");
      }
    } catch (error) {
      setMessage("Failed to disable 2FA");
    }
    setLoading(false);
  };

  const loadTokens = async () => {
    setTokensLoading(true);
    setTokenMessage("");
    try {
      const resp = await apiFetch(`${API_BASE}/tokens`);
      const data = await resp.json();
      if (data && data.success) {
        setTokens(data.tokens || []);
        setTokensReadOnly(Boolean(data.read_only));
      } else {
        setTokenMessage(data.error || "Failed to load tokens");
      }
    } catch (err) {
      setTokenMessage("Failed to load tokens");
    }
    setTokensLoading(false);
  };

  const handleCreateToken = async () => {
    setTokenMessage("");
    setCreatedTokenRaw(null);
    try {
      const resp = await apiFetch(`${API_BASE}/tokens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "generate",
          label: newTokenLabel || "",
          persist: false,
        }),
      });
      const data = await resp.json();
      if (data && data.success && data.token) {
        setCreatedTokenRaw(data.token);
        if (!data.persisted) {
          setTokenMessage(
            'Generated token (not yet stored). Click "Store" to persist, or copy it now.',
          );
        } else {
          setTokenMessage("Token created and persisted.");
        }
      } else {
        setTokenMessage(data.error || "Failed to create token");
      }
    } catch (err) {
      setTokenMessage("Failed to create token");
    }
  };

  const handleStoreToken = async (token) => {
    if (!token) return;
    setTokenMessage("");
    try {
      const resp = await apiFetch(`${API_BASE}/tokens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "store",
          token,
          label: newTokenLabel || "",
        }),
      });
      const data = await resp.json();
      if (data && data.success) {
        setTokenMessage("Token stored successfully");
        setCreatedTokenRaw(null);
        setNewTokenLabel("");
        await loadTokens();
      } else {
        setTokenMessage(data.error || "Failed to store token");
      }
    } catch (err) {
      setTokenMessage("Failed to store token");
    }
  };

  const handleRevokeToken = async (id) => {
    const ok = await showConfirmModal({
      message: `Revoke token ${id.slice(0, 8)}...?`,
      confirmLabel: "Revoke",
    });
    if (!ok) return;
    setTokenMessage("");
    try {
      const resp = await apiFetch(`${API_BASE}/tokens`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
      const data = await resp.json();
      if (data && data.success) {
        await loadTokens();
      } else {
        setTokenMessage(data.error || "Failed to revoke token");
      }
    } catch (err) {
      setTokenMessage("Failed to revoke token");
    }
  };

  // QR code data URL for setup (generated client-side to avoid leaking the TOTP secret
  // to third-party QR services). We lazily load a small QR library and generate a
  // data URL from the provided `setupData.uri`.
  const [qrDataUrl, setQrDataUrl] = useState(null);
  const [recoveryCodes, setRecoveryCodes] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function gen() {
      if (!setupData || !setupData.uri) {
        setQrDataUrl(null);
        return;
      }
      try {
        const lib = await loadQRCodeLib();
        // The UMD exposes either `qrcode` or `QRCode`; both provide `toDataURL`
        const toDataURL =
          (lib && lib.toDataURL) ||
          (lib && lib.QRCode && lib.QRCode.toDataURL) ||
          (window.qrcode && window.qrcode.toDataURL) ||
          (window.QRCode && window.QRCode.toDataURL);
        if (!toDataURL) {
          setQrDataUrl(null);
          return;
        }
        const dataUrl = await toDataURL(setupData.uri, {
          width: 200,
          margin: 1,
        });
        if (!cancelled) setQrDataUrl(dataUrl);
      } catch (err) {
        // Fail silently; optional fallback could request a backend-provided image
        setQrDataUrl(null);
      }
    }
    gen();
    return () => {
      cancelled = true;
    };
  }, [setupData?.uri]);

  return (
    <div
      className={`rounded-lg border p-6 ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}
    >
      <h2
        className={`text-xl font-semibold mb-4 ${isDarkMode ? "text-white" : "text-gray-900"}`}
      >
        Two-Factor Authentication (2FA)
      </h2>

      <div className="space-y-4">
        <div
          className={`p-4 rounded-lg ${isDarkMode ? "bg-gray-700" : "bg-gray-50"}`}
        >
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h3
                className={`font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}
              >
                2FA Status:{" "}
                {twofaStatus === null
                  ? "Loading..."
                  : twofaStatus
                    ? "Enabled"
                    : "Disabled"}
              </h3>
              <p
                className={`text-sm mt-1 ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
              >
                {twofaStatus
                  ? "Your account is protected with time-based one-time passwords."
                  : "Enable 2FA to add an extra layer of security to your account."}
              </p>
            </div>
            <div className="flex gap-2 flex-shrink-0">
              {!twofaStatus && (
                <button
                  onClick={handleSetup2FA}
                  disabled={loading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {loading ? "Setting up..." : "Enable 2FA"}
                </button>
              )}
              {twofaStatus && (
                <button
                  onClick={handleDisable2FA}
                  disabled={loading}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
                >
                  {loading ? "Disabling..." : "Disable 2FA"}
                </button>
              )}
            </div>
          </div>
        </div>

        {setupData && (
          <div
            className={`p-4 rounded-lg border ${isDarkMode ? "bg-gray-700 border-gray-600" : "bg-yellow-50 border-yellow-200"}`}
          >
            <h4
              className={`font-medium mb-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}
            >
              Setup 2FA
            </h4>
            <p
              className={`text-sm mb-4 ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
            >
              Scan this QR code with your authenticator app (Google
              Authenticator, Authy, etc.):
            </p>
            <div className="mb-4">
              {qrDataUrl
                ? React.createElement("img", {
                    src: qrDataUrl,
                    alt: "2FA QR Code",
                    className: "mx-auto border rounded",
                  })
                : React.createElement(
                    "div",
                    {
                      className:
                        "mx-auto border rounded w-48 h-48 flex items-center justify-center text-sm text-gray-500",
                      role: "status",
                    },
                    "QR unavailable — please copy the secret manually",
                  )}
            </div>
            <p
              className={`text-xs mb-4 text-center ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
            >
              Or manually enter:{" "}
              <code
                className={`px-2 py-1 rounded ${isDarkMode ? "bg-gray-600" : "bg-gray-200"}`}
              >
                {setupData.secret}
              </code>
            </p>
            <p
              className={`text-xs mb-4 ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}
            >
              <strong>To store in environment variable:</strong> Set{" "}
              <code
                className={`px-1 py-0.5 rounded text-xs ${isDarkMode ? "bg-gray-600" : "bg-gray-200"}`}
              >
                UA_WEBUI_TOTP_SECRET={"{"}setupData.secret
              </code>
              <br />
              <strong>To copy to password manager:</strong> Save the secret{" "}
              {"{"}setupData.secret{"}"} in your password manager&#39;s TOTP
              field.
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={verificationCode}
                onChange={(e) =>
                  setVerificationCode(
                    e.target.value.replace(/\D/g, "").slice(0, 6),
                  )
                }
                placeholder="000000"
                className={`flex-1 px-3 py-2 border rounded-lg ${isDarkMode ? "bg-gray-600 border-gray-500 text-white" : "bg-white border-gray-300"}`}
                maxLength="6"
              />
              <button
                onClick={handleVerifyAndEnable}
                disabled={loading || verificationCode.length !== 6}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                Verify & Enable
              </button>
            </div>
            {recoveryCodes && (
              <div
                className={`mt-4 p-3 rounded text-sm ${isDarkMode ? "bg-gray-800 border-gray-700 text-white" : "bg-white border-gray-200 text-gray-900"}`}
              >
                <div className="font-medium mb-2">
                  One-time recovery codes (store these safely)
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {recoveryCodes.map((c, idx) =>
                    React.createElement(
                      "div",
                      {
                        key: idx,
                        className: `${isDarkMode ? "px-2 py-1 bg-gray-700 text-white rounded text-xs" : "px-2 py-1 bg-gray-100 text-gray-800 rounded text-xs"}`,
                      },
                      c,
                    ),
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {message && (
          <div
            className={`p-3 rounded-lg ${message.includes("success") || message.includes("enabled") ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}
          >
            {message}
          </div>
        )}

        {/* API Tokens management */}
        <div className="mt-6">
          <h2
            className={`text-lg font-semibold mb-3 ${isDarkMode ? "text-white" : "text-gray-900"}`}
          >
            API Access Tokens
          </h2>
          <p
            className={`text-sm mb-3 ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
          >
            Create opaque bearer tokens for automation and API clients. Tokens
            are shown once when created — store them securely.
          </p>

          {createdTokenRaw && (
            <div
              className={`p-3 mb-3 rounded ${isDarkMode ? "bg-gray-700 text-white" : "bg-yellow-50 text-gray-900"}`}
            >
              <div className="font-medium mb-2">New token (store this now)</div>
              <div className="flex items-center gap-2">
                <input
                  readOnly
                  value={createdTokenRaw}
                  className={
                    isDarkMode
                      ? "flex-1 px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-100"
                      : "flex-1 px-2 py-1 rounded border border-gray-300 bg-white text-gray-800"
                  }
                />
                <button
                  onClick={async () => {
                    try {
                      if (navigator.clipboard && createdTokenRaw) {
                        await navigator.clipboard.writeText(createdTokenRaw);
                        setCreatedTokenCopied(true);
                        setTokenMessage("Token copied to clipboard");
                        setTimeout(() => setCreatedTokenCopied(false), 2000);
                      } else {
                        setTokenMessage("Clipboard unavailable");
                      }
                    } catch (err) {
                      setTokenMessage("Failed to copy token");
                    }
                  }}
                  className="px-3 py-1 bg-gray-800 text-white rounded"
                >
                  {createdTokenCopied ? "Copied!" : "Copy"}
                </button>
                <button
                  onClick={() => handleStoreToken(createdTokenRaw)}
                  className="px-3 py-1 bg-blue-600 text-white rounded"
                >
                  Store
                </button>
              </div>
            </div>
          )}
          <div
            className={`p-3 mb-3 rounded ${isDarkMode ? "bg-gray-800 text-white" : "bg-white text-gray-900"}`}
          >
            <div className="mb-2 font-medium">Token label</div>
            <input
              value={newTokenLabel}
              onChange={(e) => setNewTokenLabel(e.target.value)}
              placeholder="Optional label"
              className={`w-full px-3 py-2 rounded border ${isDarkMode ? "bg-gray-700 border-gray-600 text-white" : "bg-white border-gray-300"}`}
            />

            <div className="mt-3 flex gap-2">
              <button
                onClick={handleCreateToken}
                className="px-3 py-1 bg-green-600 text-white rounded"
              >
                Generate
              </button>
              <button
                onClick={() => {
                  if (createdTokenRaw) handleStoreToken(createdTokenRaw);
                  else setTokenMessage("No token to store");
                }}
                className="px-3 py-1 bg-blue-600 text-white rounded"
              >
                Store
              </button>
            </div>
          </div>

          <div
            className={`p-3 rounded border ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}
          >
            {tokenMessage && (
              <div className="text-sm text-red-600">{tokenMessage}</div>
            )}
            <div className="mt-4">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium mb-2">Existing tokens</div>
                {tokensReadOnly && (
                  <div className="text-xs text-yellow-400">
                    Read-only token store (env)
                  </div>
                )}
              </div>
              {tokensLoading ? (
                <div className="text-sm">Loading...</div>
              ) : tokens.length === 0 ? (
                <div className="text-sm text-gray-500">No tokens</div>
              ) : (
                <div className="space-y-2">
                  {tokens.map((t) => (
                    <div
                      key={t.id}
                      className={`flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-2 rounded ${isDarkMode ? "bg-gray-700" : "bg-gray-50"}`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="text-xs font-mono flex-shrink-0">
                          {t.id.slice(0, 8)}..
                        </div>
                        <div className="text-sm truncate">
                          {t.label || "(no label)"} — {t.user}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <div className="text-sm text-gray-500">
                          {t.expiry
                            ? new Date(t.expiry * 1000).toLocaleString()
                            : "no expiry"}
                        </div>
                        <button
                          onClick={() => handleRevokeToken(t.id)}
                          className="px-2 py-1 bg-red-600 text-white rounded text-sm"
                        >
                          Revoke
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AccessLogTab({ isDarkMode }) {
  const [level, setLevel] = useState("access_denied");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [logEntries, setLogEntries] = useState([]);
  const [logLoading, setLogLoading] = useState(false);
  const [whitelist, setWhitelist] = useState([]);
  const [blacklist, setBlacklist] = useState([]);
  const [ipLoading, setIpLoading] = useState(false);
  const [ipMessage, setIpMessage] = useState("");

  useEffect(() => {
    loadLevel();
    loadLogEntries();
    loadIpSettings();
  }, []);

  const loadLevel = async () => {
    try {
      const response = await apiFetch(`${API_BASE}/access_log/level`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      if (data && data.success) {
        setLevel(data.level || "access_denied");
      } else {
        setMessage(data.error || "Failed to load level");
      }
    } catch (error) {
      setMessage("Failed to load current level");
    }
  };

  const loadLogEntries = async () => {
    setLogLoading(true);
    try {
      const response = await apiFetch(`${API_BASE}/access_log/entries?n=50`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      if (data && data.success) {
        setLogEntries(data.entries || []);
      } else {
        console.warn("Failed to load log entries:", data.error);
      }
    } catch (error) {
      console.warn("Failed to load log entries:", error);
    }
    setLogLoading(false);
  };

  const handleSave = async () => {
    setLoading(true);
    setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/access_log/level`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level }),
      });
      const data = await response.json();
      if (data && data.success) {
        setMessage("Saved.");
        // Refresh log entries to show the change
        loadLogEntries();
      } else {
        setMessage(data.error || "Save failed");
      }
    } catch (error) {
      setMessage("Save failed");
    }
    setLoading(false);
  };

  const loadIpSettings = async () => {
    try {
      const response = await apiFetch(`${API_BASE}/ip_control`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      if (data && data.success) {
        setWhitelist(data.whitelist || []);
        setBlacklist(data.blacklist || []);
      } else {
        console.warn("Failed to load IP settings:", data.error);
      }
    } catch (error) {
      console.warn("Failed to load IP settings:", error);
    }
  };

  const handleIpSave = async () => {
    setIpLoading(true);
    setIpMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/ip_control`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ whitelist, blacklist }),
      });
      const data = await response.json();
      if (data && data.success) {
        setIpMessage("Saved.");
      } else {
        setIpMessage(data.error || "Save failed");
      }
    } catch (error) {
      setIpMessage("Save failed");
    }
    setIpLoading(false);
  };

  const addToWhitelist = (ip) => {
    if (ip && !whitelist.includes(ip)) {
      setWhitelist([...whitelist, ip]);
    }
  };

  const removeFromWhitelist = (ip) => {
    setWhitelist(whitelist.filter((item) => item !== ip));
  };

  const addToBlacklist = (ip) => {
    if (ip && !blacklist.includes(ip)) {
      setBlacklist([...blacklist, ip]);
    }
  };

  const removeFromBlacklist = (ip) => {
    setBlacklist(blacklist.filter((item) => item !== ip));
  };

  return (
    <div>
      {/* IP Control Panel */}
      <div
        className={`rounded-lg border p-6 mb-6 ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}
      >
        <h2
          className={`text-xl font-semibold mb-4 ${isDarkMode ? "text-white" : "text-gray-900"}`}
        >
          IP Access Control
        </h2>
        <p
          className={`text-sm mb-4 ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
        >
          Control which IP addresses can access the Web UI. If whitelist is set,
          only listed IPs are allowed. Otherwise, listed IPs in blacklist are
          denied.
        </p>

        <div className="mb-4">
          <label
            className={`block text-sm font-medium mb-2 ${isDarkMode ? "text-gray-200" : "text-gray-700"}`}
          >
            Whitelist (allowed IPs)
          </label>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              placeholder="192.168.1.100"
              className={`flex-1 rounded-md border px-3 py-2 text-sm ${isDarkMode ? "bg-gray-700 border-gray-600 text-white" : "bg-white border-gray-300 text-gray-900"}`}
              onKeyPress={(e) => {
                if (e.key === "Enter") {
                  addToWhitelist(e.target.value.trim());
                  e.target.value = "";
                }
              }}
            />
            <button
              onClick={(e) => {
                const input = e.target.previousElementSibling;
                addToWhitelist(input.value.trim());
                input.value = "";
              }}
              className="px-3 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
            >
              Add
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {whitelist.map((ip) => (
              <span
                key={ip}
                className={`inline-flex items-center px-2 py-1 rounded text-xs ${isDarkMode ? "bg-green-800 text-green-200" : "bg-green-100 text-green-800"}`}
              >
                {ip}
                <button
                  onClick={() => removeFromWhitelist(ip)}
                  className="ml-1 text-red-500 hover:text-red-700"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>

        <div className="mb-4">
          <label
            className={`block text-sm font-medium mb-2 ${isDarkMode ? "text-gray-200" : "text-gray-700"}`}
          >
            Blacklist (denied IPs)
          </label>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              placeholder="192.168.1.100"
              className={`flex-1 rounded-md border px-3 py-2 text-sm ${isDarkMode ? "bg-gray-700 border-gray-600 text-white" : "bg-white border-gray-300 text-gray-900"}`}
              onKeyPress={(e) => {
                if (e.key === "Enter") {
                  addToBlacklist(e.target.value.trim());
                  e.target.value = "";
                }
              }}
            />
            <button
              onClick={(e) => {
                const input = e.target.previousElementSibling;
                addToBlacklist(input.value.trim());
                input.value = "";
              }}
              className="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
            >
              Add
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {blacklist.map((ip) => (
              <span
                key={ip}
                className={`inline-flex items-center px-2 py-1 rounded text-xs ${isDarkMode ? "bg-red-800 text-red-200" : "bg-red-100 text-red-800"}`}
              >
                {ip}
                <button
                  onClick={() => removeFromBlacklist(ip)}
                  className="ml-1 text-red-500 hover:text-red-700"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleIpSave}
            disabled={ipLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {ipLoading ? "Saving..." : "Save IP Settings"}
          </button>
        </div>

        {ipMessage && (
          <div
            className={`mt-4 text-sm ${ipMessage === "Saved." ? "text-green-600" : "text-red-600"}`}
          >
            {ipMessage}
          </div>
        )}
      </div>

      {/* Access Log Settings */}

      <h2
        className={`text-xl font-semibold mb-4 ${isDarkMode ? "text-white" : "text-gray-900"}`}
      >
        Access Log Settings
      </h2>
      <p
        className={`text-sm mb-4 ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
      >
        Control what the Web UI logs. Default is{" "}
        <code
          className={`px-1 rounded ${isDarkMode ? "bg-gray-700" : "bg-gray-100"}`}
        >
          access_denied
        </code>{" "}
        (only failed API attempts). Choose{" "}
        <code
          className={`px-1 rounded ${isDarkMode ? "bg-gray-700" : "bg-gray-100"}`}
        >
          disabled
        </code>{" "}
        to turn off all logging.
      </p>

      <div className="mb-4">
        <label
          className={`block text-sm font-medium mb-1 ${isDarkMode ? "text-gray-200" : "text-gray-700"}`}
        >
          Level
        </label>
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          className={`mt-1 block w-full rounded-md border px-3 py-2 text-sm ${isDarkMode ? "bg-gray-700 border-gray-600 text-white" : "bg-white border-gray-300 text-gray-900"}`}
        >
          <option value="access_denied">
            access_denied (failed attempts only)
          </option>
          <option value="access">access (log all API accesses)</option>
          <option value="disabled">disabled (no logging)</option>
        </select>
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Saving..." : "Save"}
        </button>
      </div>

      {message && (
        <div
          className={`mt-4 text-sm ${message === "Saved." ? "text-green-600" : "text-red-600"}`}
        >
          {message}
        </div>
      )}

      {/* Access Log Display */}
      <div className="mt-6">
        <div className="flex justify-between items-center mb-3">
          <h3
            className={`text-lg font-semibold ${isDarkMode ? "text-white" : "text-gray-900"}`}
          >
            Recent Access Log
          </h3>
          <button
            onClick={loadLogEntries}
            disabled={logLoading}
            className="px-3 py-1 bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-50 text-sm"
          >
            {logLoading ? "Loading..." : "Refresh"}
          </button>
        </div>
        <div
          className={`p-3 rounded border ${isDarkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}
        >
          {logLoading ? (
            <div
              className={`text-sm ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
            >
              Loading log entries...
            </div>
          ) : logEntries.length === 0 ? (
            <div
              className={`text-sm ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
            >
              No log entries found.
            </div>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {logEntries.map((entry, index) => (
                <div
                  key={index}
                  className={`p-2 rounded text-xs ${isDarkMode ? "bg-gray-700 text-gray-200" : "bg-gray-50 text-gray-800"}`}
                >
                  <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-1">
                    <div className="flex-1">
                      <span
                        className={`font-medium ${entry.success ? "text-green-600" : "text-red-600"}`}
                      >
                        {entry.method} {entry.endpoint}
                      </span>
                      <span className="ml-2 text-gray-500">
                        {entry.user || "anonymous"} @{" "}
                        {entry.remote_addr || "unknown"}
                      </span>
                    </div>
                    <div className="text-right">
                      <div className="text-gray-500">
                        {new Date(entry.timestamp).toLocaleString()}
                      </div>
                      <div
                        className={`text-xs ${entry.success ? "text-green-600" : "text-red-600"}`}
                      >
                        {entry.status} {entry.success ? "✓" : "✗"}
                      </div>
                    </div>
                  </div>
                  {entry.details && (
                    <div className="mt-1 text-gray-600 text-xs">
                      {entry.details}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ConfigSidebar({
  sections,
  activeTab,
  activeSubTab,
  onNavigate,
  onClose,
  colorTheme,
  onColorThemeChange,
  interfaceStyle,
  onInterfaceStyleChange,
  isDarkMode,
  onToggleMode,
  updateStatus,
  onOpenUpdate,
  onOpenHelp,
  onLogout,
}) {
  const [isAppearanceOpen, setIsAppearanceOpen] = useState(() =>
    window.matchMedia
      ? !window.matchMedia("(max-width: 767px), (max-height: 760px)").matches
      : true,
  );
  const defaultSection = sections.find(
    (section) => section.section === "DEFAULT",
  );
  const defaultGroups = getDefaultNavigationGroups(defaultSection);
  const sectionByName = new Map(
    sections.map((section) => [section.section, section]),
  );
  const torrentClientsSection = sectionByName.get("TORRENT_CLIENTS");
  const usenetSection = sectionByName.get("USENET");
  const trackersSection = sectionByName.get("TRACKERS");
  const reservedSections = new Set([
    "DEFAULT",
    "IMAGES",
    "TRACKERS",
    "TORRENT_CLIENTS",
    "USENET",
  ]);
  const remainingConfigurationSections = sections.filter(
    (section) => !reservedSections.has(section.section),
  );
  const configurationNavigationItems = [];

  for (const group of defaultGroups) {
    configurationNavigationItems.push({
      id: `default-${group.id}`,
      label: group.label,
      tab: "default",
      subTab: group.id,
      nested: true,
    });
    if (group.id === "general" && torrentClientsSection) {
      configurationNavigationItems.push({
        id: torrentClientsSection.section,
        label: getConfigSectionLabel(torrentClientsSection.section),
        tab: torrentClientsSection.section.toLowerCase(),
        nested: true,
      });
    }
    if (group.id === "upload" && usenetSection) {
      configurationNavigationItems.push({
        id: usenetSection.section,
        label: getConfigSectionLabel(usenetSection.section),
        tab: usenetSection.section.toLowerCase(),
        nested: true,
      });
    }
  }

  if (
    torrentClientsSection &&
    !configurationNavigationItems.some(
      (item) => item.id === torrentClientsSection.section,
    )
  ) {
    configurationNavigationItems.push({
      id: torrentClientsSection.section,
      label: getConfigSectionLabel(torrentClientsSection.section),
      tab: torrentClientsSection.section.toLowerCase(),
      nested: true,
    });
  }
  if (
    usenetSection &&
    !configurationNavigationItems.some(
      (item) => item.id === usenetSection.section,
    )
  ) {
    configurationNavigationItems.push({
      id: usenetSection.section,
      label: getConfigSectionLabel(usenetSection.section),
      tab: usenetSection.section.toLowerCase(),
      nested: true,
    });
  }
  for (const section of remainingConfigurationSections) {
    configurationNavigationItems.push({
      id: section.section,
      label: getConfigSectionLabel(section.section),
      tab: section.section.toLowerCase(),
      nested: true,
    });
  }

  const navButton = ({ id, label, tab, subTab = "", nested = false }) => {
    const isActive = activeTab === tab && (!subTab || activeSubTab === subTab);
    return (
      <button
        key={id}
        type="button"
        className={`ua-config-nav-button ${nested ? "ua-config-nav-button-nested" : ""}`}
        data-active={isActive ? "true" : "false"}
        aria-current={isActive ? "page" : undefined}
        onClick={() => onNavigate(tab, subTab)}
      >
        <span className="ua-config-nav-indicator" aria-hidden="true"></span>
        <span>{label}</span>
      </button>
    );
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="ua-config-sidebar-brand flex h-20 shrink-0 items-center justify-between gap-2 border-b px-3 py-3 sm:gap-3 sm:px-5 md:hidden">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <img
            src={window.UA_LOGO_URL || "/static/img/logo.svg"}
            alt="Upload-Assistant logo"
            className="h-7 w-7 shrink-0 sm:h-8 sm:w-8"
          />
          <div className="min-w-0">
            <div className="flex min-w-0 items-baseline gap-1 text-[0.68rem] font-semibold uppercase tracking-[0.12em] opacity-60 sm:text-xs sm:tracking-widest">
              <span className="truncate">Upload Assistant</span>
              {window.UA_APP_VERSION && (
                <span className="shrink-0 normal-case tracking-normal">
                  <span aria-hidden="true">·</span> {window.UA_APP_VERSION}
                </span>
              )}
            </div>
            <div className="mt-1 truncate text-lg font-bold">Configuration</div>
          </div>
        </div>
        <button
          type="button"
          className="ua-config-icon-button md:hidden"
          aria-label="Close configuration navigation"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <div className="ua-config-sidebar-brand hidden h-20 shrink-0 items-center border-b px-5 md:flex">
        <div className="min-w-0">
          <p className="truncate text-xs font-semibold uppercase tracking-widest opacity-60">
            Upload Assistant
          </p>
          <h2 className="mt-1 truncate text-lg font-bold">Configuration</h2>
        </div>
      </div>

      <div className="shrink-0 px-3 pt-4 md:hidden">
        <WorkspaceSwitcher
          activeWorkspace="config"
          isDarkMode={isDarkMode}
          stretch
        />
      </div>

      <nav
        className="ua-config-sidebar-nav min-h-0 flex-1 overflow-y-auto px-3 py-4"
        aria-label="Configuration sections"
      >
        {configurationNavigationItems.length > 0 && (
          <div className="mb-5">
            <div className="ua-config-nav-heading px-3 pb-2 text-xs font-semibold uppercase tracking-wider">
              Settings
            </div>
            <div className="space-y-1">
              {configurationNavigationItems.map(navButton)}
            </div>
          </div>
        )}

        {trackersSection && (
          <div className="mb-5">
            <div className="ua-config-nav-heading px-3 pb-2 text-xs font-semibold uppercase tracking-wider">
              Trackers
            </div>
            <div className="space-y-1">
              {trackersSection &&
                TRACKER_NAVIGATION_GROUPS.map((group) =>
                  navButton({
                    id: `trackers-${group.id}`,
                    label: group.label,
                    tab: "trackers",
                    subTab: group.id,
                    nested: true,
                  }),
                )}
            </div>
          </div>
        )}

        <div>
          <div className="ua-config-nav-heading px-3 pb-2 text-xs font-semibold uppercase tracking-wider">
            Administration
          </div>
          <div className="space-y-1">
            {navButton({
              id: "security",
              label: "Security",
              tab: "security",
            })}
            {navButton({
              id: "access-log",
              label: "Access Log",
              tab: "access-log",
            })}
          </div>
        </div>
      </nav>

      <div className="ua-config-sidebar-footer shrink-0 border-t p-4 md:hidden">
        <button
          type="button"
          className="ua-config-nav-heading flex w-full items-center justify-between text-left text-xs font-semibold uppercase tracking-wider"
          aria-expanded={isAppearanceOpen}
          aria-controls="config-appearance-controls"
          onClick={() => setIsAppearanceOpen((current) => !current)}
        >
          <span>Appearance</span>
          <span className="text-base leading-none" aria-hidden="true">
            {isAppearanceOpen ? "−" : "+"}
          </span>
        </button>

        {isAppearanceOpen && (
          <div id="config-appearance-controls" className="mt-3">
            <label
              htmlFor="config-color-theme"
              className="ua-config-service-description block text-xs font-semibold"
            >
              Color theme
            </label>
            <select
              id="config-color-theme"
              value={colorTheme}
              onChange={onColorThemeChange}
              aria-label="Color theme"
              className="ua-theme-picker mt-1 w-full rounded-lg px-3 py-2 text-sm"
            >
              {colorThemes.map((theme) => (
                <option key={theme.id} value={theme.id}>
                  {theme.label}
                </option>
              ))}
            </select>
            <label
              htmlFor="config-interface-style"
              className="ua-config-service-description mt-3 block text-xs font-semibold"
            >
              Corner style
            </label>
            <select
              id="config-interface-style"
              value={interfaceStyle}
              onChange={onInterfaceStyleChange}
              aria-label="Corner style"
              className="ua-theme-picker mt-1 w-full rounded-lg px-3 py-2 text-sm"
            >
              {interfaceStyles.map((style) => (
                <option key={style.id} value={style.id}>
                  {style.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="ua-config-mode-button mt-2 flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm"
              onClick={onToggleMode}
              aria-label={`Switch to ${isDarkMode ? "light" : "dark"} mode`}
            >
              <span>{isDarkMode ? "Dark mode" : "Light mode"}</span>
              <span
                className="ua-config-mode-switch relative inline-flex h-6 w-11 items-center rounded-full"
                data-enabled={isDarkMode ? "true" : "false"}
                aria-hidden="true"
              >
                <span className="ua-config-mode-knob inline-block h-4 w-4 rounded-full bg-white transition-transform"></span>
              </span>
            </button>
          </div>
        )}

        <div className="mt-3 grid gap-2">
          {updateStatus?.update_available && (
            <button
              type="button"
              className="ua-config-sidebar-action ua-update-sidebar-action rounded-lg px-3 py-2 text-sm font-semibold"
              aria-haspopup="dialog"
              onClick={onOpenUpdate}
            >
              Update available
            </button>
          )}
          <button
            type="button"
            className="ua-config-sidebar-action rounded-lg px-3 py-2 text-center text-sm font-semibold"
            aria-haspopup="dialog"
            onClick={onOpenHelp}
          >
            Help &amp; Resources
          </button>
          <button
            type="button"
            onClick={onLogout}
            className="ua-config-sidebar-action ua-config-sidebar-action-danger rounded-lg px-3 py-2 text-sm font-semibold"
          >
            Log out
          </button>
        </div>
      </div>
    </div>
  );
}

function ConfigApp() {
  useEffect(() => {
    const root = document.documentElement;
    const viewport = window.visualViewport;
    let animationFrame = 0;

    const updateViewportHeight = () => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(() => {
        const visibleHeight = Math.round(
          viewport?.height || window.innerHeight,
        );
        if (visibleHeight > 0) {
          root.style.setProperty(
            "--ua-config-viewport-height",
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
      root.style.removeProperty("--ua-config-viewport-height");
    };
  }, []);

  const [sections, setSections] = useState([]);
  // Keep a ref to the latest sections to avoid stale closures inside async loaders
  const currentSectionsRef = useRef(sections);
  useEffect(() => {
    currentSectionsRef.current = sections;
  }, [sections]);
  const [status, setStatus] = useState({
    text: "Loading config options...",
    type: "info",
  });
  const [isDarkMode, setIsDarkMode] = useState(getStoredTheme);
  const [colorTheme, setColorThemeState] = useState(getStoredColorTheme);
  const [interfaceStyle, setInterfaceStyleState] = useState(
    getStoredInterfaceStyle,
  );
  const [expandedGroups, setExpandedGroups] = useState(new Set());
  const [pendingChanges, setPendingChanges] = useState(new Map());
  const [pendingTorrentClients, setPendingTorrentClients] = useState(new Map());
  const [pendingRemovedTorrentClients, setPendingRemovedTorrentClients] =
    useState(new Set());
  const [pendingRenamedTorrentClients, setPendingRenamedTorrentClients] =
    useState(new Map());
  const [pendingRemovedTrackers, setPendingRemovedTrackers] = useState(
    new Set(),
  );
  const [pendingTrackerOverrideModes, setPendingTrackerOverrideModes] =
    useState(new Map());
  const [trackerOverrideEditors, setTrackerOverrideEditors] = useState(
    new Set(),
  );
  const [isSaving, setIsSaving] = useState(false);
  const [configWarning, setConfigWarning] = useState("");
  const [activeTab, setActiveTab] = useState(() => {
    try {
      return sessionStorage.getItem("ua_active_tab") || "default";
    } catch (e) {
      return "default";
    }
  });
  const [activeSubTab, setActiveSubTab] = useState(() => {
    try {
      const storedSubTab =
        sessionStorage.getItem("ua_active_subtab") || "general";
      return storedSubTab === "release-preparation" ? "upload" : storedSubTab;
    } catch (e) {
      return "general";
    }
  });
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isHelpResourcesOpen, setIsHelpResourcesOpen] = useState(false);
  const [updateStatus, setUpdateStatus] = useState(null);
  const [isUpdateStatusOpen, setIsUpdateStatusOpen] = useState(false);
  const [isCheckingForUpdates, setIsCheckingForUpdates] = useState(false);
  const [dismissedUpdateVersion, setDismissedUpdateVersion] = useState(
    () => window.getUADismissedUpdateVersion?.() || "",
  );
  const [torrentClients, setTorrentClients] = useState([]);
  const [trackerCatalog, setTrackerCatalog] = useState({
    defaultTrackers: [],
    trackers: [],
  });
  const folderPickerResolveRef = useRef(null);
  const [folderPicker, setFolderPicker] = useState(null);
  const [renameClientSource, setRenameClientSource] = useState("");
  const [clientTestStates, setClientTestStates] = useState(new Map());
  const [isPendingSummaryOpen, setIsPendingSummaryOpen] = useState(false);
  const pendingSummaryRef = useRef(null);
  const mobileNavGestureRef = useRef(null);
  const suppressMobileNavClickRef = useRef(false);

  const visibleUpdateStatus =
    updateStatus?.update_available &&
    updateStatus.latest_version !== dismissedUpdateVersion
      ? updateStatus
      : null;

  useEffect(() => {
    if (!window.loadUAUpdateStatus) return undefined;
    let cancelled = false;
    const loadUpdateStatus = () => {
      if (document.visibilityState === "hidden") return;
      window
        .loadUAUpdateStatus()
        .then((nextStatus) => {
          if (!cancelled) setUpdateStatus(nextStatus);
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
      const nextStatus = await window.loadUAUpdateStatus(true);
      setUpdateStatus(nextStatus);
      if (nextStatus?.update_available) {
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

  useEffect(() => {
    const handleColorThemeChange = (event) => {
      setColorThemeState(event.detail?.theme || getStoredColorTheme());
    };
    window.addEventListener("ua-theme-change", handleColorThemeChange);
    return () =>
      window.removeEventListener("ua-theme-change", handleColorThemeChange);
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
    if (!isPendingSummaryOpen) return undefined;
    const closeWhenOutside = (event) => {
      if (!pendingSummaryRef.current?.contains(event.target)) {
        setIsPendingSummaryOpen(false);
      }
    };
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setIsPendingSummaryOpen(false);
    };
    document.addEventListener("pointerdown", closeWhenOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeWhenOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isPendingSummaryOpen]);

  const handleColorThemeChange = (event) => {
    setColorThemeState(setColorTheme(event.target.value));
  };
  const handleInterfaceStyleChange = (event) => {
    setInterfaceStyleState(setInterfaceStyle(event.target.value));
  };
  const getSubTabsForSection = (section) => {
    if (section?.section === "DEFAULT") {
      return getDefaultNavigationGroups(section);
    }
    if (section?.section === "TRACKERS") {
      return TRACKER_NAVIGATION_GROUPS;
    }
    return [];
  };

  const setStatusWithClear = (text, type = "info", clearAfterMs = 0) => {
    setStatus({ text, type });
    if (clearAfterMs > 0) {
      window.setTimeout(() => {
        setStatus({ text: "", type: "info" });
      }, clearAfterMs);
    }
  };

  const toggleGroup = (groupKey) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupKey)) {
        next.delete(groupKey);
      } else {
        next.add(groupKey);
      }
      return next;
    });
  };

  const navigateTo = (tab, subTab = "") => {
    setActiveTab(tab);
    setActiveSubTab(subTab);
    setIsMobileNavOpen(false);
  };

  useEffect(() => {
    if (!isMobileNavOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setIsMobileNavOpen(false);
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isMobileNavOpen]);

  const startMobileNavGesture = (event) => {
    if (
      event.pointerType === "mouse" ||
      !window.matchMedia("(max-width: 767px)").matches
    ) {
      return;
    }
    if (
      event.target.closest("input, select, textarea, [contenteditable='true']")
    ) {
      return;
    }
    mobileNavGestureRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const moveMobileNavGesture = (event) => {
    const gesture = mobileNavGestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const horizontalDistance = event.clientX - gesture.startX;
    const verticalDistance = event.clientY - gesture.startY;
    if (
      Math.abs(horizontalDistance) > 12 &&
      Math.abs(horizontalDistance) > Math.abs(verticalDistance)
    ) {
      event.preventDefault();
    }
  };

  const finishMobileNavGesture = (event) => {
    const gesture = mobileNavGestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    mobileNavGestureRef.current = null;

    const horizontalDistance = event.clientX - gesture.startX;
    const verticalDistance = event.clientY - gesture.startY;
    const isDeliberateHorizontalSwipe =
      Math.abs(horizontalDistance) >= 72 &&
      Math.abs(verticalDistance) <= 56 &&
      Math.abs(horizontalDistance) > Math.abs(verticalDistance) * 1.25;
    if (!isDeliberateHorizontalSwipe) return;

    if (horizontalDistance < 0) {
      suppressMobileNavClickRef.current = true;
      setIsMobileNavOpen(false);
      window.setTimeout(() => {
        suppressMobileNavClickRef.current = false;
      }, 250);
    }
  };

  const cancelMobileNavGesture = () => {
    mobileNavGestureRef.current = null;
  };

  const suppressClickAfterMobileNavSwipe = (event) => {
    if (!suppressMobileNavClickRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    suppressMobileNavClickRef.current = false;
  };

  const loadConfigOptions = async (isRetry = false) => {
    try {
      setStatus({
        text: isRetry ? "Retrying..." : "Loading config options...",
        type: "info",
      });
      const response = await apiFetch(`${API_BASE}/config_options`);
      const data = await response.json();
      if (!data.success) {
        throw new Error(data.error || "Failed to load config options");
      }
      const newSections = data.sections || [];
      const fallbackSection =
        newSections.find((section) => section.section === "DEFAULT") ||
        newSections[0];
      setSections(newSections);
      setPendingChanges(new Map());
      setPendingTorrentClients(new Map());
      setPendingRemovedTorrentClients(new Set());
      setPendingRenamedTorrentClients(new Map());
      setPendingRemovedTrackers(new Set());
      setPendingTrackerOverrideModes(new Map());
      setTrackerOverrideEditors(new Set());
      setClientTestStates(new Map());
      setRenameClientSource("");
      setConfigWarning(data.config_warning || "");
      setStatus({ text: "", type: "info" });

      // Restore tab state after operations (preserve which section/tab the user was on)
      let didRestoreTab = false;
      try {
        const storedActive = sessionStorage.getItem("ua_active_tab");
        const storedSub = sessionStorage.getItem("ua_active_subtab");
        if (storedActive && newSections.length > 0) {
          setActiveTab(storedActive);
          const activeSection = newSections.find(
            (section) => section.section.toLowerCase() === storedActive,
          );
          const subTabs = activeSection
            ? getSubTabsForSection(activeSection)
            : [];
          if (storedSub && subTabs.some((s) => s.id === storedSub)) {
            setActiveSubTab(storedSub);
          } else if (subTabs.length > 0) {
            setActiveSubTab(subTabs[0].id);
          } else {
            setActiveSubTab("");
          }
          sessionStorage.removeItem("ua_active_tab");
          sessionStorage.removeItem("ua_active_subtab");
          didRestoreTab = true;
        }
      } catch (e) {
        // ignore storage errors
      }

      // Load torrent clients
      try {
        const clientsResponse = await apiFetch(`${API_BASE}/torrent_clients`);
        const clientsData = await clientsResponse.json();
        if (clientsData.success) {
          setTorrentClients(clientsData.clients || []);
        }
      } catch (error) {
        console.warn("Failed to load torrent clients:", error);
        setTorrentClients([]);
      }

      try {
        const trackersResponse = await apiFetch(`${API_BASE}/trackers`);
        const trackersData = await trackersResponse.json();
        if (trackersData.success) {
          setTrackerCatalog({
            defaultTrackers: trackersData.default_trackers || [],
            trackers: trackersData.trackers || [],
          });
        }
      } catch (error) {
        console.warn("Failed to load tracker catalogue:", error);
        setTrackerCatalog({ defaultTrackers: [], trackers: [] });
      }

      // Only set default tabs if we don't have any sections loaded yet
      const currentlyHaveSections =
        currentSectionsRef &&
        currentSectionsRef.current &&
        currentSectionsRef.current.length
          ? currentSectionsRef.current.length
          : sections
            ? sections.length
            : 0;
      if (currentlyHaveSections === 0 && newSections.length > 0) {
        // If we restored a tab from sessionStorage above, don't override it.
        if (!didRestoreTab) {
          setActiveTab(fallbackSection.section.toLowerCase());
          // Set first sub-tab if available
          const subTabs = getSubTabsForSection(fallbackSection);
          if (subTabs.length > 0) {
            setActiveSubTab(subTabs[0].id);
          }
        }
      } else if (newSections.length > 0) {
        // Validate that current active tab still exists
        const currentTabExists =
          activeTab === "security" ||
          activeTab === "access-log" ||
          newSections.some(
            (section) => section.section.toLowerCase() === activeTab,
          );
        if (!currentTabExists) {
          // Reset to first tab if current tab no longer exists
          setActiveTab(fallbackSection.section.toLowerCase());
          const subTabs = getSubTabsForSection(fallbackSection);
          if (subTabs.length > 0) {
            setActiveSubTab(subTabs[0].id);
          } else {
            setActiveSubTab("");
          }
        } else {
          // Validate that current sub-tab still exists for the active tab
          const activeSection = newSections.find(
            (section) => section.section.toLowerCase() === activeTab,
          );
          if (activeSection) {
            const subTabs = getSubTabsForSection(activeSection);
            const currentSubTabExists = subTabs.some(
              (subTab) => subTab.id === activeSubTab,
            );
            if (!currentSubTabExists && subTabs.length > 0) {
              setActiveSubTab(subTabs[0].id);
            } else if (!currentSubTabExists) {
              setActiveSubTab("");
            }
          }
        }
      }
      return true;
    } catch (error) {
      setStatus({
        text: error.message || "Failed to load config options",
        type: "error",
      });
      return false;
    }
  };

  const discardAllChanges = async () => {
    const confirmed = await showConfirmModal({
      title: "Discard unsaved changes",
      message:
        "Discard every pending configuration change and restore the last saved values?",
      confirmLabel: "Discard Changes",
    });
    if (!confirmed) return;
    setIsPendingSummaryOpen(false);
    const didReload = await loadConfigOptions();
    if (didReload) {
      setStatusWithClear("Unsaved changes discarded.", "info", 2500);
    }
  };

  const onValueChange = (path, value, meta) => {
    const pathKey = path.join("/");
    if (path[0] === "TORRENT_CLIENTS" && path[1]) {
      setClientTestStates((currentStates) => {
        const stateKey = String(path[1]).toLowerCase();
        if (!currentStates.has(stateKey)) return currentStates;
        const next = new Map(currentStates);
        next.delete(stateKey);
        return next;
      });
    }
    setPendingChanges((prev) => {
      const next = new Map(prev);
      if (meta.readOnly) {
        return prev;
      }
      if (meta.isSensitive && meta.isRedacted) {
        next.delete(pathKey);
        return next;
      }
      if (value === meta.originalValue) {
        next.delete(pathKey);
      } else {
        next.set(pathKey, { path, value });
      }
      return next;
    });
  };

  const addPendingTorrentClient = (clientName, templateName) => {
    const torrentSection = sections.find(
      (section) => section.section === "TORRENT_CLIENTS",
    );
    const templateItem = torrentSection?.items?.find(
      (item) => item.key === templateName,
    );
    if (!templateItem) {
      throw new Error("The selected torrent client template is unavailable.");
    }

    const cloneExampleTemplate = (item) => {
      const clone = JSON.parse(JSON.stringify(item));
      if (Array.isArray(clone.children)) {
        clone.children = clone.children.map(cloneExampleTemplate);
      } else if (Object.prototype.hasOwnProperty.call(clone, "example_value")) {
        clone.value = clone.example_value;
      }
      clone.source = "example";
      return clone;
    };
    const pendingItem = cloneExampleTemplate(templateItem);
    pendingItem.key = clientName;
    pendingItem.source = "pending";
    setSections((currentSections) =>
      currentSections.map((section) =>
        section.section === "TORRENT_CLIENTS"
          ? { ...section, items: [...section.items, pendingItem] }
          : section,
      ),
    );
    setTorrentClients((currentClients) =>
      [...currentClients, clientName].sort((left, right) =>
        String(left).localeCompare(String(right)),
      ),
    );
    setPendingTorrentClients((currentClients) => {
      const next = new Map(currentClients);
      next.set(clientName, templateName);
      return next;
    });
    setExpandedGroups((currentGroups) => {
      const next = new Set(currentGroups);
      next.add(`TORRENT_CLIENTS/${clientName}`);
      return next;
    });
    setStatusWithClear(
      `${clientName} added locally. Save Config to keep it.`,
      "info",
      2500,
    );
  };

  const removePendingTorrentClient = (clientName) => {
    const normalizedName = String(clientName).toLowerCase();
    setSections((currentSections) =>
      currentSections.map((section) =>
        section.section === "TORRENT_CLIENTS"
          ? {
              ...section,
              items: section.items.filter(
                (item) =>
                  !(
                    item.source === "pending" &&
                    String(item.key).toLowerCase() === normalizedName
                  ),
              ),
            }
          : section,
      ),
    );
    setTorrentClients((currentClients) =>
      currentClients.filter(
        (name) => String(name).toLowerCase() !== normalizedName,
      ),
    );
    setPendingTorrentClients((currentClients) => {
      const next = new Map(currentClients);
      for (const name of next.keys()) {
        if (String(name).toLowerCase() === normalizedName) next.delete(name);
      }
      return next;
    });
    setPendingChanges((currentChanges) => {
      const next = new Map(currentChanges);
      const pathPrefix = `TORRENT_CLIENTS/${clientName}/`.toLowerCase();
      for (const pathKey of next.keys()) {
        if (String(pathKey).toLowerCase().startsWith(pathPrefix)) {
          next.delete(pathKey);
        }
      }
      return next;
    });
    setExpandedGroups((currentGroups) => {
      const next = new Set(currentGroups);
      next.delete(`TORRENT_CLIENTS/${clientName}`);
      return next;
    });
  };

  const findConfigItem = (items, targetKey) => {
    for (const item of items || []) {
      if (item.key === targetKey && !item.children) return item;
      const nested = findConfigItem(item.children, targetKey);
      if (nested) return nested;
    }
    return null;
  };

  const getEffectiveDefaultValue = (key) => {
    const pendingPath = `DEFAULT/${key}`;
    if (pendingChanges.has(pendingPath)) {
      return pendingChanges.get(pendingPath).value;
    }
    const defaultSection = sections.find(
      (section) => section.section === "DEFAULT",
    );
    return findConfigItem(defaultSection?.items, key)?.value;
  };

  const editorValueForRuntime = (rawValue, currentValue) => {
    if (Array.isArray(currentValue)) {
      if (Array.isArray(rawValue)) return rawValue;
      try {
        const parsed = JSON.parse(String(rawValue));
        return Array.isArray(parsed) ? parsed : currentValue;
      } catch (_error) {
        return currentValue;
      }
    }
    if (typeof currentValue === "boolean") {
      if (typeof rawValue === "boolean") return rawValue;
      return String(rawValue).trim().toLowerCase() === "true";
    }
    if (typeof currentValue === "number") {
      const parsed = Number(rawValue);
      return Number.isNaN(parsed) ? currentValue : parsed;
    }
    if (
      currentValue &&
      typeof currentValue === "object" &&
      !Array.isArray(currentValue)
    ) {
      if (rawValue && typeof rawValue === "object") return rawValue;
      try {
        const parsed = JSON.parse(String(rawValue));
        return parsed && typeof parsed === "object" ? parsed : currentValue;
      } catch (_error) {
        return currentValue;
      }
    }
    return rawValue === null || rawValue === undefined ? "" : String(rawValue);
  };

  const replaceClientNameInValue = (value, oldName, newName) => {
    const oldNormalized = String(oldName).toLowerCase();
    if (Array.isArray(value)) {
      return value.map((entry) =>
        typeof entry === "string" && entry.toLowerCase() === oldNormalized
          ? newName
          : entry,
      );
    }
    if (typeof value === "string") {
      if (value.toLowerCase() === oldNormalized) return newName;
      try {
        const parsed = JSON.parse(value);
        if (Array.isArray(parsed)) {
          return replaceClientNameInValue(parsed, oldName, newName);
        }
      } catch (_error) {
        // Plain client names are expected here as well as JSON list values.
      }
    }
    return value;
  };

  const effectiveTorrentClientConfig = (clientName) => {
    const torrentSection = sections.find(
      (section) => section.section === "TORRENT_CLIENTS",
    );
    const clientItem = torrentSection?.items?.find(
      (item) =>
        String(item.key).toLowerCase() === String(clientName).toLowerCase(),
    );
    if (!clientItem) return null;

    const buildObject = (items, pathParts) => {
      const result = {};
      for (const item of items || []) {
        if (Array.isArray(item.children)) {
          result[item.key] = buildObject(item.children, [
            ...pathParts,
            item.key,
          ]);
          continue;
        }
        const update = pendingChanges.get([...pathParts, item.key].join("/"));
        result[item.key] = update
          ? editorValueForRuntime(update.value, item.value)
          : item.value;
      }
      return result;
    };

    return buildObject(clientItem.children, ["TORRENT_CLIENTS", clientName]);
  };

  const renameTorrentClient = (currentName, newName) => {
    const torrentSection = sections.find(
      (section) => section.section === "TORRENT_CLIENTS",
    );
    const sourceItem = torrentSection?.items?.find(
      (item) =>
        String(item.key).toLowerCase() === String(currentName).toLowerCase(),
    );
    if (!sourceItem) {
      setStatusWithClear(
        "The selected torrent client is unavailable.",
        "error",
      );
      return;
    }

    const referenceKeys = [
      "default_torrent_client",
      "injecting_client_list",
      "searching_client_list",
    ];
    const referenceUpdates = new Map();
    for (const key of referenceKeys) {
      const currentValue = getEffectiveDefaultValue(key);
      const nextValue = replaceClientNameInValue(
        currentValue,
        currentName,
        newName,
      );
      if (JSON.stringify(nextValue) !== JSON.stringify(currentValue)) {
        referenceUpdates.set(key, nextValue);
      }
    }

    const updateReferenceItems = (items) =>
      (items || []).map((item) => {
        if (Array.isArray(item.children)) {
          return { ...item, children: updateReferenceItems(item.children) };
        }
        return referenceUpdates.has(item.key)
          ? { ...item, value: referenceUpdates.get(item.key) }
          : item;
      });

    const originalName = sourceItem.renamedFrom || currentName;
    setSections((currentSections) =>
      currentSections.map((section) => {
        if (section.section === "TORRENT_CLIENTS") {
          return {
            ...section,
            items: section.items.map((item) =>
              String(item.key).toLowerCase() ===
              String(currentName).toLowerCase()
                ? {
                    ...item,
                    key: newName,
                    source: item.source === "pending" ? "pending" : "renaming",
                    renamedFrom:
                      item.source === "pending" ? undefined : originalName,
                  }
                : item,
            ),
          };
        }
        if (section.section === "DEFAULT") {
          return { ...section, items: updateReferenceItems(section.items) };
        }
        return section;
      }),
    );

    setPendingChanges((currentChanges) => {
      const next = new Map();
      const oldPrefix = `TORRENT_CLIENTS/${currentName}/`.toLowerCase();
      for (const [pathKey, update] of currentChanges) {
        if (String(pathKey).toLowerCase().startsWith(oldPrefix)) {
          const nextPath = [...update.path];
          nextPath[1] = newName;
          next.set(nextPath.join("/"), { ...update, path: nextPath });
        } else {
          next.set(pathKey, update);
        }
      }
      for (const [key, value] of referenceUpdates) {
        const path = ["DEFAULT", key];
        next.set(path.join("/"), { path, value });
      }
      return next;
    });

    if (sourceItem.source === "pending") {
      setPendingTorrentClients((currentClients) => {
        const next = new Map(currentClients);
        const templateName = next.get(currentName);
        next.delete(currentName);
        next.set(newName, templateName);
        return next;
      });
    } else {
      setPendingRenamedTorrentClients((currentRenames) => {
        const next = new Map(currentRenames);
        next.set(originalName, newName);
        return next;
      });
    }

    setTorrentClients((currentClients) =>
      currentClients
        .map((name) =>
          String(name).toLowerCase() === String(currentName).toLowerCase()
            ? newName
            : name,
        )
        .sort((left, right) => String(left).localeCompare(String(right))),
    );
    setExpandedGroups((currentGroups) => {
      const next = new Set(currentGroups);
      next.delete(`TORRENT_CLIENTS/${currentName}`);
      next.add(`TORRENT_CLIENTS/${newName}`);
      return next;
    });
    setClientTestStates((currentStates) => {
      const next = new Map(currentStates);
      next.delete(String(currentName).toLowerCase());
      return next;
    });
    setRenameClientSource("");
    setStatusWithClear(
      `${currentName} will be renamed to ${newName} when you save.`,
      "info",
      3000,
    );
  };

  const undoRenameTorrentClient = (originalName, currentName) => {
    const currentNormalized = String(currentName).toLowerCase();
    const referenceKeys = new Set([
      "default_torrent_client",
      "injecting_client_list",
      "searching_client_list",
    ]);
    const restoreReferenceItems = (items) =>
      (items || []).map((item) => {
        if (Array.isArray(item.children)) {
          return { ...item, children: restoreReferenceItems(item.children) };
        }
        return referenceKeys.has(item.key)
          ? {
              ...item,
              value: replaceClientNameInValue(
                item.value,
                currentName,
                originalName,
              ),
            }
          : item;
      });

    setSections((currentSections) =>
      currentSections.map((section) => {
        if (section.section === "TORRENT_CLIENTS") {
          return {
            ...section,
            items: section.items.map((item) =>
              String(item.key).toLowerCase() === currentNormalized
                ? {
                    ...item,
                    key: originalName,
                    source: "config",
                    renamedFrom: undefined,
                  }
                : item,
            ),
          };
        }
        if (section.section === "DEFAULT") {
          return { ...section, items: restoreReferenceItems(section.items) };
        }
        return section;
      }),
    );
    setPendingChanges((currentChanges) => {
      const next = new Map();
      const currentPrefix = `TORRENT_CLIENTS/${currentName}/`.toLowerCase();
      for (const [pathKey, update] of currentChanges) {
        if (
          Array.isArray(update.path) &&
          update.path[0] === "DEFAULT" &&
          referenceKeys.has(update.path[1])
        ) {
          continue;
        }
        if (String(pathKey).toLowerCase().startsWith(currentPrefix)) {
          const nextPath = [...update.path];
          nextPath[1] = originalName;
          next.set(nextPath.join("/"), { ...update, path: nextPath });
        } else {
          next.set(pathKey, update);
        }
      }
      return next;
    });
    setPendingRenamedTorrentClients((currentRenames) => {
      const next = new Map(currentRenames);
      for (const name of next.keys()) {
        if (String(name).toLowerCase() === String(originalName).toLowerCase()) {
          next.delete(name);
        }
      }
      return next;
    });
    setTorrentClients((currentClients) =>
      currentClients
        .map((name) =>
          String(name).toLowerCase() === currentNormalized
            ? originalName
            : name,
        )
        .sort((left, right) => String(left).localeCompare(String(right))),
    );
    setExpandedGroups((currentGroups) => {
      const next = new Set(currentGroups);
      next.delete(`TORRENT_CLIENTS/${currentName}`);
      next.add(`TORRENT_CLIENTS/${originalName}`);
      return next;
    });
    setClientTestStates((currentStates) => {
      const next = new Map(currentStates);
      next.delete(currentNormalized);
      return next;
    });
    setRenameClientSource("");
  };

  const testTorrentClient = async (clientName) => {
    const clientConfig = effectiveTorrentClientConfig(clientName);
    if (!clientConfig) {
      setStatusWithClear(
        "The selected torrent client is unavailable.",
        "error",
      );
      return;
    }
    const stateKey = String(clientName).toLowerCase();
    setClientTestStates((currentStates) => {
      const next = new Map(currentStates);
      next.set(stateKey, {
        status: "loading",
        message: "Testing connection...",
      });
      return next;
    });
    try {
      const response = await apiFetch(
        `${API_BASE}/config_test_torrent_client`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: clientName, config: clientConfig }),
        },
      );
      const data = await response.json();
      setClientTestStates((currentStates) => {
        const next = new Map(currentStates);
        next.set(stateKey, {
          status: data.success ? "success" : "error",
          message: data.success
            ? data.message || "Connection successful"
            : data.error || "Connection failed",
        });
        return next;
      });
    } catch (error) {
      setClientTestStates((currentStates) => {
        const next = new Map(currentStates);
        next.set(stateKey, {
          status: "error",
          message: error.message || "Connection failed",
        });
        return next;
      });
    }
  };

  const torrentClientReferences = (clientName) => {
    const normalizedName = String(clientName).trim().toLowerCase();
    const references = [];
    const fields = [
      ["default_torrent_client", "Default Torrent Client"],
      ["injecting_client_list", "Injecting Client List"],
      ["searching_client_list", "Searching Client List"],
    ];
    for (const [key, label] of fields) {
      const value = getEffectiveDefaultValue(key);
      const names = Array.isArray(value)
        ? value
        : String(value || "")
            .replace(/^\[|\]$/g, "")
            .split(",")
            .map((name) => name.replace(/^['"]|['"]$/g, "").trim());
      if (
        names.some(
          (name) => String(name).trim().toLowerCase() === normalizedName,
        )
      ) {
        references.push(label);
      }
    }
    return references;
  };

  const removeTorrentClient = async (clientName) => {
    const references = torrentClientReferences(clientName);
    if (references.length > 0) {
      setStatusWithClear(
        `${clientName} is still used by ${references.join(", ")}. Update Client Selection before removing it.`,
        "error",
        5000,
      );
      return;
    }
    const confirmed = await showConfirmModal({
      title: "Remove torrent client",
      message: `Remove ${clientName} when the configuration is next saved?`,
      confirmLabel: "Remove Client",
    });
    if (!confirmed) return;

    const normalizedName = String(clientName).toLowerCase();
    setSections((currentSections) =>
      currentSections.map((section) =>
        section.section === "TORRENT_CLIENTS"
          ? {
              ...section,
              items: section.items.map((item) =>
                String(item.key).toLowerCase() === normalizedName
                  ? {
                      ...item,
                      previousSource: item.source,
                      source: "removing",
                    }
                  : item,
              ),
            }
          : section,
      ),
    );
    setPendingRemovedTorrentClients((currentClients) => {
      const next = new Set(currentClients);
      next.add(clientName);
      return next;
    });
    setPendingChanges((currentChanges) => {
      const next = new Map(currentChanges);
      const pathPrefix = `TORRENT_CLIENTS/${clientName}/`.toLowerCase();
      for (const pathKey of next.keys()) {
        if (String(pathKey).toLowerCase().startsWith(pathPrefix)) {
          next.delete(pathKey);
        }
      }
      return next;
    });
  };

  const undoRemoveTorrentClient = (clientName) => {
    const normalizedName = String(clientName).toLowerCase();
    setSections((currentSections) =>
      currentSections.map((section) =>
        section.section === "TORRENT_CLIENTS"
          ? {
              ...section,
              items: section.items.map((item) =>
                String(item.key).toLowerCase() === normalizedName &&
                item.source === "removing"
                  ? {
                      ...item,
                      source: item.previousSource || "config",
                      previousSource: null,
                    }
                  : item,
              ),
            }
          : section,
      ),
    );
    setPendingRemovedTorrentClients((currentClients) => {
      const next = new Set(currentClients);
      for (const name of next) {
        if (String(name).toLowerCase() === normalizedName) next.delete(name);
      }
      return next;
    });
  };

  const toggleTrackerOverrides = (trackerName, enabled, overrideItems) => {
    const normalizedName = String(trackerName).toUpperCase();
    const originalEnabled = (overrideItems || []).some(
      (item) => item.source === "config" || item.previousSource === "config",
    );

    setTrackerOverrideEditors((currentEditors) => {
      const next = new Set(currentEditors);
      if (enabled) {
        next.add(normalizedName);
      } else {
        next.delete(normalizedName);
      }
      return next;
    });
    setPendingTrackerOverrideModes((currentModes) => {
      const next = new Map(currentModes);
      if (enabled === originalEnabled) {
        next.delete(normalizedName);
      } else {
        next.set(normalizedName, enabled);
      }
      return next;
    });
    setSections((currentSections) =>
      currentSections.map((section) =>
        section.section === "TRACKERS"
          ? {
              ...section,
              items: section.items.map((trackerItem) =>
                String(trackerItem.key).toUpperCase() === normalizedName
                  ? {
                      ...trackerItem,
                      children: (trackerItem.children || []).map((item) => {
                        if (!trackerDefaultOverrideKeys.has(item.key)) {
                          return item;
                        }
                        if (enabled && item.source === "override-removing") {
                          return {
                            ...item,
                            source: item.previousSource || "config",
                            previousSource: null,
                          };
                        }
                        if (!enabled && item.source === "config") {
                          return {
                            ...item,
                            previousSource: item.source,
                            source: "override-removing",
                          };
                        }
                        return item;
                      }),
                    }
                  : trackerItem,
              ),
            }
          : section,
      ),
    );
    if (!enabled) {
      setPendingChanges((currentChanges) => {
        const next = new Map(currentChanges);
        for (const item of overrideItems || []) {
          next.delete(["TRACKERS", trackerName, item.key].join("/"));
        }
        return next;
      });
    }
    setStatusWithClear(
      enabled
        ? `${trackerName} will use tracker-specific overrides after you save.`
        : `${trackerName} will inherit these settings from DEFAULT after you save.`,
      "info",
      3500,
    );
  };

  const removeTracker = (trackerName, wasDefault = false) => {
    const normalizedName = String(trackerName).toUpperCase();
    setSections((currentSections) =>
      currentSections.map((section) =>
        section.section === "TRACKERS"
          ? {
              ...section,
              items: section.items.map((item) =>
                String(item.key).toUpperCase() === normalizedName
                  ? {
                      ...item,
                      previousSource: item.source,
                      source: "removing",
                      wasDefaultBeforeRemoval: wasDefault,
                    }
                  : item,
              ),
            }
          : section,
      ),
    );
    setPendingRemovedTrackers((currentTrackers) => {
      const next = new Set(currentTrackers);
      next.add(normalizedName);
      return next;
    });
    setPendingTrackerOverrideModes((currentModes) => {
      const next = new Map(currentModes);
      next.delete(normalizedName);
      return next;
    });
    setTrackerOverrideEditors((currentEditors) => {
      const next = new Set(currentEditors);
      next.delete(normalizedName);
      return next;
    });
    setPendingChanges((currentChanges) => {
      const next = new Map(currentChanges);
      const pathPrefix = `TRACKERS/${normalizedName}/`.toLowerCase();
      for (const pathKey of next.keys()) {
        if (String(pathKey).toLowerCase().startsWith(pathPrefix)) {
          next.delete(pathKey);
        }
      }
      return next;
    });
    setStatusWithClear(
      `${trackerName} will be removed when you save.`,
      "info",
      3000,
    );
  };

  const undoRemoveTracker = (trackerName) => {
    const normalizedName = String(trackerName).toUpperCase();
    setSections((currentSections) =>
      currentSections.map((section) =>
        section.section === "TRACKERS"
          ? {
              ...section,
              items: section.items.map((item) =>
                String(item.key).toUpperCase() === normalizedName &&
                item.source === "removing"
                  ? {
                      ...item,
                      source: item.previousSource || "config",
                      previousSource: null,
                      wasDefaultBeforeRemoval: false,
                    }
                  : item,
              ),
            }
          : section,
      ),
    );
    setPendingRemovedTrackers((currentTrackers) => {
      const next = new Set(currentTrackers);
      for (const name of next) {
        if (String(name).toUpperCase() === normalizedName) next.delete(name);
      }
      return next;
    });
  };

  const saveAllChanges = async () => {
    const pendingChangeCount =
      pendingChanges.size +
      pendingTorrentClients.size +
      pendingRenamedTorrentClients.size +
      pendingRemovedTorrentClients.size +
      pendingRemovedTrackers.size +
      pendingTrackerOverrideModes.size;
    if (pendingChangeCount === 0) {
      setStatusWithClear("No changes to save.", "warn", 1500);
      return;
    }
    for (const clientName of pendingRemovedTorrentClients) {
      const references = torrentClientReferences(clientName);
      if (references.length > 0) {
        setStatusWithClear(
          `${clientName} is still used by ${references.join(", ")}. Update Client Selection before saving its removal.`,
          "error",
          5000,
        );
        return;
      }
    }
    setIsSaving(true);
    setStatusWithClear(
      `Saving ${pendingChangeCount} change${pendingChangeCount === 1 ? "" : "s"}...`,
      "info",
    );
    try {
      for (const [oldName, newName] of pendingRenamedTorrentClients) {
        const response = await apiFetch(
          `${API_BASE}/config_rename_torrent_client`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ old_name: oldName, new_name: newName }),
          },
        );
        const data = await response.json();
        if (!data.success) {
          throw new Error(data.error || "Failed to rename torrent client");
        }
      }
      for (const [clientName, templateName] of pendingTorrentClients) {
        const response = await apiFetch(
          `${API_BASE}/config_add_torrent_client`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: clientName, template: templateName }),
          },
        );
        const data = await response.json();
        if (!data.success && response.status !== 409) {
          throw new Error(data.error || "Failed to add torrent client");
        }
      }

      // Some updates may target keys inside subsections that only exist in the example-config.
      // Ensure we create an empty subsection object in the user's config first so subsequent
      // nested updates succeed. Collect unique subsection creations needed.
      const pending = Array.from(pendingChanges.values());
      const toCreate = [];
      const createdKeys = new Set();
      for (const update of pending) {
        if (Array.isArray(update.path) && update.path.length >= 2) {
          const sectionName = String(update.path[0]);
          const subsectionName = String(update.path[1]);
          const section = sections.find(
            (s) =>
              s.section &&
              String(s.section).toLowerCase() === sectionName.toLowerCase(),
          );
          if (section && Array.isArray(section.items)) {
            const subsectionItem = section.items.find(
              (it) =>
                it.key &&
                String(it.key).toUpperCase() === subsectionName.toUpperCase(),
            );
            if (
              subsectionItem &&
              subsectionItem.children &&
              subsectionItem.source === "example"
            ) {
              const keyId = `${sectionName}/${subsectionName}`;
              if (!createdKeys.has(keyId)) {
                toCreate.push([sectionName, subsectionName]);
                createdKeys.add(keyId);
              }
            }
          }
        }
      }

      // Create missing subsections in the user's config (as empty dicts)
      for (const createPath of toCreate) {
        const respCreate = await apiFetch(`${API_BASE}/config_update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: createPath, value: "{}" }),
        });
        const dataCreate = await respCreate.json();
        if (!dataCreate.success) {
          throw new Error(dataCreate.error || "Failed to create subsection");
        }
      }

      // Apply group-level tracker overrides after any missing tracker block has
      // been created, then save individual field edits over the copied values.
      for (const [trackerName, enabled] of pendingTrackerOverrideModes) {
        const response = await apiFetch(
          `${API_BASE}/config_set_tracker_overrides`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tracker: trackerName, enabled }),
          },
        );
        const data = await response.json();
        if (!data.success) {
          throw new Error(
            data.error || "Failed to update tracker-specific overrides",
          );
        }
      }

      // Now save the actual pending updates
      for (const update of pending) {
        const response = await apiFetch(`${API_BASE}/config_update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: update.path, value: update.value }),
        });
        const data = await response.json();
        if (!data.success) {
          throw new Error(data.error || "Failed to save");
        }
      }

      for (const clientName of pendingRemovedTorrentClients) {
        const response = await apiFetch(
          `${API_BASE}/config_remove_subsection`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              path: ["TORRENT_CLIENTS", clientName],
            }),
          },
        );
        const data = await response.json();
        if (!data.success) {
          throw new Error(data.error || "Failed to remove torrent client");
        }
      }
      for (const trackerName of pendingRemovedTrackers) {
        const response = await apiFetch(
          `${API_BASE}/config_remove_subsection`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              path: ["TRACKERS", trackerName],
            }),
          },
        );
        const data = await response.json();
        if (!data.success) {
          throw new Error(
            data.error || "Failed to remove tracker configuration",
          );
        }
      }
      setStatusWithClear("Saved", "success", 1500);
      await loadConfigOptions();
    } catch (error) {
      setStatusWithClear(error.message || "Failed to save", "error");
    } finally {
      setIsSaving(false);
    }
  };

  useEffect(() => {
    (async () => {
      await loadCsrfToken();
      await loadConfigOptions();
    })();
  }, []);

  useEffect(() => {
    storage.set(THEME_KEY, isDarkMode ? "dark" : "light");
  }, [isDarkMode]);

  useEffect(() => {
    const handleStorage = (event) => {
      if (event.key === THEME_KEY) {
        setIsDarkMode(event.newValue === "dark");
      }
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const allImageHosts = useMemo(() => {
    const collectFromItems = (items) => {
      for (const item of items || []) {
        if (item.children && item.children.length) {
          const found = collectFromItems(item.children);
          if (found.length) {
            return found;
          }
        }
        if (item.key && item.key.startsWith("img_host_") && item.help) {
          const helpLine = item.help.find((line) =>
            line.toLowerCase().includes("available image hosts"),
          );
          if (helpLine) {
            const parts = helpLine.split(":");
            if (parts.length >= 2) {
              return parts[1]
                .split(",")
                .map((host) => host.trim().toLowerCase())
                .filter(Boolean);
            }
          }
        }
      }
      return [];
    };

    for (const section of sections) {
      const found = collectFromItems(section.items || []);
      if (found.length) {
        return found;
      }
    }
    return [];
  }, [sections]);

  const usedImageHosts = useMemo(() => {
    const used = new Set();
    const collectFromItems = (items) => {
      for (const item of items || []) {
        if (item.children && item.children.length) {
          collectFromItems(item.children);
        }
        if (item.key && item.key.startsWith("img_host_") && item.value) {
          const normalized = String(item.value).trim().toLowerCase();
          if (normalized) {
            used.add(normalized);
          }
        }
      }
    };

    for (const section of sections) {
      collectFromItems(section.items || []);
    }
    return used;
  }, [sections]);

  const activeSection = sections.find(
    (section) => section.section.toLowerCase() === activeTab,
  );
  const descriptionImagesSection = sections.find(
    (section) => section.section === "IMAGES",
  );
  const clientSelectionItem = sections
    .find((section) => section.section === "DEFAULT")
    ?.items?.find(
      (item) =>
        item.subsection === true &&
        normalizeConfigHeading(item.key) === "CLIENT SELECTION",
    );
  const activeDefaultGroup =
    activeSection?.section === "DEFAULT"
      ? getDefaultNavigationGroups(activeSection).find(
          (group) => group.id === activeSubTab,
        )
      : null;
  const activeTrackerGroup =
    activeSection?.section === "TRACKERS"
      ? TRACKER_NAVIGATION_GROUPS.find((group) => group.id === activeSubTab)
      : null;
  const activeTitle =
    activeTab === "security"
      ? "Security"
      : activeTab === "access-log"
        ? "Access Log"
        : activeDefaultGroup?.label ||
          activeTrackerGroup?.label ||
          getConfigSectionLabel(activeSection?.section || "Configuration");
  const activeSubtitle =
    activeSection?.section === "DEFAULT"
      ? "General settings arranged in the order they are used."
      : activeTab === "security"
        ? "Manage WebUI authentication and access controls."
        : activeTab === "access-log"
          ? "Review and configure WebUI access logging."
          : activeSection
            ? "Manage settings for " +
              getConfigSectionLabel(activeSection.section).toLowerCase() +
              "."
            : "Manage Upload Assistant settings.";
  const visibleItems =
    activeSection?.section === "DEFAULT" && activeSubTab
      ? activeSection.items.filter(
          (item) => getDefaultItemGroupId(item) === activeSubTab,
        )
      : activeSection?.items || [];

  const statusClass = "ua-config-status text-sm";
  const pendingChangeCount =
    pendingChanges.size +
    pendingTorrentClients.size +
    pendingRenamedTorrentClients.size +
    pendingRemovedTorrentClients.size +
    pendingRemovedTrackers.size +
    pendingTrackerOverrideModes.size;
  const pendingChangeSummaries = useMemo(() => {
    const summaries = [];
    const describeValue = (update) => {
      const path = Array.isArray(update.path) ? update.path : [];
      const key = String(path[path.length - 1] || "");
      const parentPath = path.slice(0, -1);
      if (
        isSensitiveKeyForPath(key, parentPath) ||
        /(cookie|token|secret|passkey)/i.test(key)
      ) {
        return "Sensitive value changed";
      }
      if (update.value === "" || update.value === null) return "Set to empty";
      if (typeof update.value === "boolean") {
        return `Set to ${update.value ? "True" : "False"}`;
      }
      let displayValue;
      if (typeof update.value === "string") {
        displayValue = update.value;
      } else {
        try {
          displayValue = JSON.stringify(update.value);
        } catch (error) {
          displayValue = "Structured value changed";
        }
      }
      if (displayValue === undefined) return "Value changed";
      const conciseValue = String(displayValue);
      return `Set to ${
        conciseValue.length > 72
          ? conciseValue.slice(0, 69) + "…"
          : conciseValue
      }`;
    };
    const describePath = (update) => {
      const path = Array.isArray(update.path) ? update.path : [];
      return path
        .map((part, index) => {
          const value = String(part);
          if (index === 0) {
            if (value.toUpperCase() === "DEFAULT") return "Main Settings";
            return getConfigSectionLabel(value);
          }
          if (index === 1 && path[0] === "TORRENT_CLIENTS") {
            return value;
          }
          if (index === 1 && path[0] === "TRACKERS") {
            return getTrackerDisplayName(value);
          }
          return formatConfigFieldLabel(value, path.slice(0, index));
        })
        .join(" › ");
    };

    for (const [pathKey, update] of pendingChanges) {
      summaries.push({
        id: `field:${pathKey}`,
        kind: "field",
        pathKey,
        title: describePath(update) || "Configuration value",
        detail: describeValue(update),
      });
    }
    for (const [clientName, templateName] of pendingTorrentClients) {
      const templateLabel =
        TORRENT_CLIENT_TEMPLATE_LABELS[
          String(templateName || "").toLowerCase()
        ] || formatDisplayLabel(templateName);
      summaries.push({
        id: `client-add:${clientName}`,
        kind: "client-add",
        clientName,
        title: "Add torrent client",
        detail: `${clientName} · ${templateLabel}`,
      });
    }
    for (const [oldName, newName] of pendingRenamedTorrentClients) {
      summaries.push({
        id: `client-rename:${oldName}`,
        kind: "client-rename",
        originalName: oldName,
        currentName: newName,
        title: "Rename torrent client",
        detail: `${oldName} → ${newName}`,
      });
    }
    for (const clientName of pendingRemovedTorrentClients) {
      summaries.push({
        id: `client-remove:${clientName}`,
        kind: "client-remove",
        clientName,
        title: "Remove torrent client",
        detail: clientName,
      });
    }
    for (const trackerName of pendingRemovedTrackers) {
      summaries.push({
        id: `tracker-remove:${trackerName}`,
        kind: "tracker-remove",
        trackerName,
        title: "Remove tracker configuration",
        detail: getTrackerDisplayName(String(trackerName)),
      });
    }
    for (const [trackerName, enabled] of pendingTrackerOverrideModes) {
      summaries.push({
        id: `tracker-overrides:${trackerName}`,
        kind: "tracker-overrides",
        trackerName,
        enabled,
        title: "Tracker-specific DEFAULT overrides",
        detail: `${getTrackerDisplayName(String(trackerName))}: ${
          enabled ? "Enable" : "Remove"
        }`,
      });
    }
    return summaries;
  }, [
    pendingChanges,
    pendingRemovedTorrentClients,
    pendingRemovedTrackers,
    pendingRenamedTorrentClients,
    pendingTorrentClients,
    pendingTrackerOverrideModes,
  ]);
  useEffect(() => {
    if (pendingChangeCount === 0) {
      setIsPendingSummaryOpen(false);
    }
  }, [pendingChangeCount]);
  const discardPendingSummary = (summary) => {
    if (summary.kind === "field") {
      setPendingChanges((currentChanges) => {
        const next = new Map(currentChanges);
        next.delete(summary.pathKey);
        return next;
      });
      window.dispatchEvent(
        new CustomEvent(CONFIG_FIELD_RESET_EVENT, {
          detail: { pathKey: summary.pathKey },
        }),
      );
    } else if (summary.kind === "client-add") {
      removePendingTorrentClient(summary.clientName);
    } else if (summary.kind === "client-rename") {
      undoRenameTorrentClient(summary.originalName, summary.currentName);
    } else if (summary.kind === "client-remove") {
      undoRemoveTorrentClient(summary.clientName);
    } else if (summary.kind === "tracker-remove") {
      undoRemoveTracker(summary.trackerName);
    } else if (summary.kind === "tracker-overrides") {
      const trackerSection = sections.find(
        (section) => section.section === "TRACKERS",
      );
      const trackerItem = trackerSection?.items?.find(
        (item) =>
          String(item.key).toUpperCase() ===
          String(summary.trackerName).toUpperCase(),
      );
      const overrideItems = (trackerItem?.children || []).filter((item) =>
        trackerDefaultOverrideKeys.has(item.key),
      );
      toggleTrackerOverrides(
        summary.trackerName,
        !summary.enabled,
        overrideItems,
      );
    }
  };
  const saveDisabled = isSaving || pendingChangeCount === 0;
  const saveButtonClass =
    "ua-config-save-button rounded-lg px-4 py-2 text-sm font-semibold" +
    (saveDisabled ? " cursor-not-allowed opacity-50" : "");
  const statusTypeClass = statusClassFor(status.type, isDarkMode);

  const browseForFolder = (fieldLabel) =>
    new Promise((resolve) => {
      if (folderPickerResolveRef.current) {
        folderPickerResolveRef.current(null);
      }
      folderPickerResolveRef.current = resolve;
      setFolderPicker({ fieldLabel });
    });

  const finishFolderPicker = (selectedPath) => {
    const resolve = folderPickerResolveRef.current;
    folderPickerResolveRef.current = null;
    setFolderPicker(null);
    if (resolve) resolve(selectedPath || null);
  };

  const handleLogout = async () => {
    try {
      const resp = await apiFetch("/logout", { method: "POST" });
      if (resp && resp.redirected) {
        window.location = resp.url;
      } else {
        window.location = "/login";
      }
    } catch (err) {
      // Fallback to hard redirect
      window.location = "/login";
    }
  };

  return (
    <div
      className={
        "ua-config-page min-h-screen " +
        (isDarkMode ? "ua-mode-dark" : "ua-mode-light")
      }
    >
      {folderPicker && (
        <FolderPickerModal
          fieldLabel={folderPicker.fieldLabel}
          onCancel={() => finishFolderPicker(null)}
          onSelect={finishFolderPicker}
        />
      )}
      {isHelpResourcesOpen && (
        <HelpResourcesModal
          updateStatus={updateStatus}
          isCheckingForUpdates={isCheckingForUpdates}
          onCheckForUpdates={checkForUpdatesNow}
          onClose={() => setIsHelpResourcesOpen(false)}
        />
      )}
      {isUpdateStatusOpen && visibleUpdateStatus && (
        <window.UAUpdateStatusModal
          status={visibleUpdateStatus}
          onClose={() => setIsUpdateStatusOpen(false)}
          onDismiss={dismissCurrentUpdate}
        />
      )}
      {renameClientSource && (
        <RenameTorrentClientModal
          sourceName={renameClientSource}
          existingNames={torrentClients}
          onCancel={() => setRenameClientSource("")}
          onRename={(newName) =>
            renameTorrentClient(renameClientSource, newName)
          }
        />
      )}
      {isMobileNavOpen && (
        <button
          type="button"
          className="ua-config-drawer-overlay fixed inset-0 z-40 md:hidden"
          aria-label="Close configuration navigation"
          onClick={() => setIsMobileNavOpen(false)}
        ></button>
      )}

      <div className="min-h-screen">
        <ConfigApplicationRail
          colorTheme={colorTheme}
          onColorThemeChange={handleColorThemeChange}
          interfaceStyle={interfaceStyle}
          onInterfaceStyleChange={handleInterfaceStyleChange}
          isDarkMode={isDarkMode}
          onToggleMode={() => setIsDarkMode((prev) => !prev)}
          updateStatus={visibleUpdateStatus}
          onOpenUpdate={() => setIsUpdateStatusOpen(true)}
          onOpenHelp={() => setIsHelpResourcesOpen(true)}
          onLogout={handleLogout}
        />

        <aside
          id="config-sidebar"
          className={
            "ua-config-sidebar fixed inset-y-0 left-0 z-50 w-72 transform transition-transform duration-200 " +
            "md:left-20 md:z-20 md:w-64 md:translate-x-0 " +
            (isMobileNavOpen ? "translate-x-0" : "-translate-x-full")
          }
          style={{ touchAction: "pan-y" }}
          onClickCapture={suppressClickAfterMobileNavSwipe}
          onPointerDown={startMobileNavGesture}
          onPointerMove={moveMobileNavGesture}
          onPointerUp={finishMobileNavGesture}
          onPointerCancel={cancelMobileNavGesture}
        >
          <ConfigSidebar
            sections={sections}
            activeTab={activeTab}
            activeSubTab={activeSubTab}
            onNavigate={navigateTo}
            onClose={() => setIsMobileNavOpen(false)}
            colorTheme={colorTheme}
            onColorThemeChange={handleColorThemeChange}
            interfaceStyle={interfaceStyle}
            onInterfaceStyleChange={handleInterfaceStyleChange}
            isDarkMode={isDarkMode}
            onToggleMode={() => setIsDarkMode((prev) => !prev)}
            updateStatus={visibleUpdateStatus}
            onOpenUpdate={() => {
              setIsUpdateStatusOpen(true);
              setIsMobileNavOpen(false);
            }}
            onOpenHelp={() => {
              setIsHelpResourcesOpen(true);
              setIsMobileNavOpen(false);
            }}
            onLogout={handleLogout}
          />
        </aside>

        <div className="min-w-0 md:ml-[21rem]">
          <header className="ua-config-header sticky top-0 z-30 h-20 border-b">
            <div className="flex h-full items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
              <div className="flex min-w-0 items-center gap-3">
                <button
                  type="button"
                  className="ua-config-icon-button shrink-0 md:hidden"
                  aria-label="Open configuration navigation"
                  aria-controls="config-sidebar"
                  aria-expanded={isMobileNavOpen}
                  onClick={() => setIsMobileNavOpen(true)}
                >
                  <span aria-hidden="true">☰</span>
                </button>
                <div className="min-w-0">
                  <h1 className="ua-config-page-title truncate text-lg font-bold sm:text-xl">
                    {activeTitle}
                  </h1>
                  <p className="ua-config-page-subtitle mt-0.5 hidden truncate text-sm sm:block">
                    {activeSubtitle}
                  </p>
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-3">
                {status.text && sections.length > 0 && (
                  <span
                    className={
                      statusClass + " " + statusTypeClass + " hidden lg:inline"
                    }
                    role="status"
                  >
                    {status.text}
                  </span>
                )}
                {pendingChangeCount > 0 && (
                  <div className="relative" ref={pendingSummaryRef}>
                    <button
                      type="button"
                      className="ua-config-pending-trigger rounded-lg px-3 py-2 text-sm font-semibold"
                      onClick={() =>
                        setIsPendingSummaryOpen((isOpen) => !isOpen)
                      }
                      aria-expanded={isPendingSummaryOpen}
                      aria-controls="pending-change-summary"
                      title={`${pendingChangeCount} unsaved ${
                        pendingChangeCount === 1 ? "change" : "changes"
                      }`}
                    >
                      <span className="hidden lg:inline">
                        {pendingChangeCount} unsaved{" "}
                        {pendingChangeCount === 1 ? "change" : "changes"}
                      </span>
                      <span className="lg:hidden">{pendingChangeCount}</span>
                    </button>
                    {isPendingSummaryOpen && (
                      <div
                        id="pending-change-summary"
                        className="ua-config-pending-popover absolute right-0 top-full z-50 mt-2 w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-xl border shadow-2xl"
                      >
                        <div className="ua-config-pending-popover-header flex items-start justify-between gap-4 border-b px-4 py-3">
                          <div>
                            <h2 className="text-sm font-bold">
                              Pending changes
                            </h2>
                            <p className="mt-0.5 text-xs">
                              These changes have not been saved.
                            </p>
                          </div>
                          <button
                            type="button"
                            className="ua-config-pending-close rounded-md px-2 py-1 text-sm"
                            onClick={() => setIsPendingSummaryOpen(false)}
                            aria-label="Close pending changes"
                          >
                            ×
                          </button>
                        </div>
                        <div className="max-h-80 space-y-2 overflow-y-auto p-2">
                          {pendingChangeSummaries.map((summary) => (
                            <div
                              className="ua-config-pending-item flex items-center gap-3 rounded-lg border px-3 py-2"
                              key={summary.id}
                            >
                              <div className="min-w-0 flex-1">
                                <div className="break-words text-sm font-semibold">
                                  {summary.title}
                                </div>
                                <div className="ua-config-pending-item-detail mt-0.5 break-words text-xs">
                                  {summary.detail}
                                </div>
                              </div>
                              <button
                                type="button"
                                className="ua-config-pending-item-discard shrink-0 rounded-md border px-2.5 py-1.5 text-xs font-semibold"
                                onClick={() => discardPendingSummary(summary)}
                                aria-label={`Discard change: ${summary.title}`}
                              >
                                Discard
                              </button>
                            </div>
                          ))}
                        </div>
                        <div className="ua-config-pending-popover-footer border-t p-3">
                          <button
                            type="button"
                            className="ua-config-discard-button w-full rounded-lg border px-3 py-2 text-sm font-semibold"
                            onClick={discardAllChanges}
                            disabled={isSaving}
                          >
                            Discard all changes
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
                <button
                  type="button"
                  className={saveButtonClass}
                  onClick={saveAllChanges}
                  disabled={saveDisabled}
                >
                  {isSaving ? "Saving..." : "Save Config"}
                </button>
              </div>
            </div>
          </header>

          <main className="ua-config-main px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
            <div className="w-full">
              {/* Always show loading/error area until content loads - prevents an empty screen on first run. */}
              {sections.length === 0 && (
                <div className="ua-config-state-panel flex min-h-48 flex-col items-start justify-center rounded-xl border p-6">
                  {status.text && (
                    <div
                      className={statusClass + " " + statusTypeClass + " mb-3"}
                      role="status"
                    >
                      {status.text}
                    </div>
                  )}
                  {status.type === "error" && (
                    <button
                      type="button"
                      onClick={() => loadConfigOptions(true)}
                      className="ua-config-save-button rounded-lg px-4 py-2 text-sm font-semibold"
                    >
                      Retry
                    </button>
                  )}
                  {status.type === "info" && status.text && (
                    <div className="ua-config-page-subtitle mt-2 text-sm">
                      If this takes too long, check your connection or try
                      refreshing.
                    </div>
                  )}
                </div>
              )}

              {sections.length > 0 && (
                <div className="space-y-5">
                  {/* Config load warning banner */}
                  {configWarning && (
                    <div
                      className="ua-config-warning rounded-xl border px-4 py-3 text-sm"
                      role="alert"
                    >
                      <span className="font-semibold">Warning: </span>
                      {configWarning}
                    </div>
                  )}
                  {status.text && (
                    <div
                      className={
                        "ua-config-inline-status rounded-lg border px-4 py-3 lg:hidden " +
                        statusClass +
                        " " +
                        statusTypeClass
                      }
                      role="status"
                    >
                      {status.text}
                    </div>
                  )}

                  {/* Tab Content */}
                  <div className="space-y-4">
                    {activeTab === "security" && (
                      <SecurityTab isDarkMode={isDarkMode} />
                    )}
                    {activeTab === "access-log" && (
                      <AccessLogTab isDarkMode={isDarkMode} />
                    )}
                    {activeSection && (
                      <React.Fragment>
                        <ItemList
                          items={visibleItems}
                          pathParts={[activeSection.section]}
                          depth={0}
                          isDarkMode={isDarkMode}
                          allImageHosts={allImageHosts}
                          usedImageHosts={usedImageHosts}
                          fullWidth={true}
                          expandedGroups={expandedGroups}
                          toggleGroup={toggleGroup}
                          torrentClients={torrentClients}
                          clientSelectionItem={clientSelectionItem}
                          trackerView={
                            activeSection.section === "TRACKERS"
                              ? activeSubTab
                              : ""
                          }
                          trackerCatalog={trackerCatalog}
                          pendingChanges={pendingChanges}
                          pendingTrackerOverrideModes={
                            pendingTrackerOverrideModes
                          }
                          trackerOverrideEditors={trackerOverrideEditors}
                          onToggleTrackerOverrides={toggleTrackerOverrides}
                          onAddTorrentClient={addPendingTorrentClient}
                          onRemovePendingTorrentClient={
                            removePendingTorrentClient
                          }
                          onRenameTorrentClient={setRenameClientSource}
                          onTestTorrentClient={testTorrentClient}
                          onRemoveTorrentClient={removeTorrentClient}
                          onUndoRemoveTorrentClient={undoRemoveTorrentClient}
                          onRemoveTracker={removeTracker}
                          onUndoRemoveTracker={undoRemoveTracker}
                          clientTestStates={clientTestStates}
                          onBrowseFolder={browseForFolder}
                          onValueChange={onValueChange}
                        />
                        {activeSection.section === "DEFAULT" &&
                          activeSubTab === "descriptions" &&
                          descriptionImagesSection && (
                            <DescriptionImagesSection
                              section={descriptionImagesSection}
                              isDarkMode={isDarkMode}
                              allImageHosts={allImageHosts}
                              usedImageHosts={usedImageHosts}
                              torrentClients={torrentClients}
                              onValueChange={onValueChange}
                            />
                          )}
                      </React.Fragment>
                    )}
                  </div>
                </div>
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

(function mountConfigApp() {
  const rootEl = document.getElementById("page-root");
  if (!rootEl || !window.React || !window.ReactDOM) {
    return;
  }
  const root = ReactDOM.createRoot(rootEl);
  root.render(
    React.createElement(
      ConfigErrorBoundary,
      null,
      React.createElement(ConfigApp),
    ),
  );
})();
