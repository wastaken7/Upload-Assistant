const { useEffect, useMemo, useRef, useState } = React;

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
const THEME_KEY = "ua_config_theme";
const storage = window.UAStorage;
const getStoredTheme = window.getUAStoredTheme;
const colorThemes = window.UAThemes || [];
const getStoredColorTheme = window.getUAStoredColorTheme;
const setColorTheme = window.setUAColorTheme;

const DEFAULT_WORKFLOW_GROUPS = [
  {
    id: "general",
    label: "General",
    headings: ["MAIN SETTINGS", "LOGGING"],
  },
  {
    id: "setup",
    label: "Connections & Tools",
    headings: [
      "ARR INTEGRATION",
      "EXTERNAL TOOL PATHS",
      "CLIENT SELECTION",
    ],
  },
  {
    id: "metadata",
    label: "Metadata",
    headings: [
      "METADATA API CREDENTIALS",
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
    label: "Screenshots",
    headings: [
      "SCREENSHOT CAPTURE AND PROCESSING",
      "SCREENSHOT ENHANCEMENTS",
      "DISC MENU SCREENSHOTS",
      "XXX CONTACT SHEETS",
    ],
  },
  {
    id: "descriptions",
    label: "Descriptions",
    headings: [
      "GENERAL DESCRIPTION SETTINGS",
      "PACK DESCRIPTIONS",
      "DESCRIPTION HEADERS AND OVERRIDES",
      "BLU-RAY SETTINGS",
      "AUDIO SPECTROGRAMS AND HDR PLOTS",
    ],
  },
  {
    id: "release-preparation",
    label: "Release Preparation",
    headings: ["TORRENT CREATION"],
  },
  {
    id: "upload",
    label: "Upload",
    headings: ["TRACKER CHECKS AND UPLOAD", "POST-UPLOAD"],
  },
];

const CONFIG_SECTION_LABELS = {
  IMAGES: "Database Link Images",
  TRACKERS: "Trackers",
  TORRENT_CLIENTS: "Torrent Clients",
  USENET: "Usenet",
};

const CONFIG_BLOCK_LABELS = {
  qbittorrent: "qBittorrent",
  qbittorrent_searching: "qBittorrent (searching)",
  rtorrent: "rTorrent",
};

const METADATA_CACHE_SERVICE_LABELS = {
  tmdb: "TMDB",
  imdb: "IMDb",
  tvdb: "TVDB",
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
    services: [
      "tmdb",
      "imdb",
      "tvdb",
      "tvmaze",
      "anilist",
      "douban",
      "thexem",
    ],
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
  "DESCRIPTION HEADERS AND OVERRIDES":
    "Description Headers and Overrides",
  "BLU-RAY SETTINGS": "Blu-ray Settings",
  "AUDIO SPECTROGRAMS AND HDR PLOTS":
    "Audio Spectrograms and HDR Plots",
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

const normalizeConfigHeading = (value) => String(value || "").trim().toUpperCase();

const formatConfigHeading = (value) => {
  const normalized = normalizeConfigHeading(value);
  return CONFIG_HEADING_LABELS[normalized] || formatDisplayLabel(value);
};

const getDefaultItemGroupId = (item) => {
  const heading = normalizeConfigHeading(
    item?.subsection === true ? item.key : item?.subsection,
  );
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
  formatDisplayLabel(blockName);

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
const formatDisplayLabel = (key) => {
  if (!key) return key;
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
};

const formatConfigFieldLabel = (key, pathParts = []) => {
  if (pathParts.includes("metadata_cache_services")) {
    const serviceFieldLabels = {
      enabled: "Caching enabled",
      ttl_hours: "Cache lifetime (hours)",
      localized_ttl_hours: "Localized data lifetime (hours)",
    };
    if (serviceFieldLabels[key]) return serviceFieldLabels[key];
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

function ConfigLeaf({
  item,
  pathParts,
  isDarkMode,
  fullWidth,
  allImageHosts,
  usedImageHosts,
  torrentClients,
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
  }, [item.value, item.key, pathParts]);

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

  if (isLinkingField(item.key, pathParts)) {
    const linkingOptions = [
      { value: "", label: "None (Original Path)" },
      { value: "symlink", label: "Symbolic Link" },
      { value: "hardlink", label: "Hard Link" },
    ];

    const originalValue = String(item.value || "");

    return (
      <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-start px-4 py-3">
        <div
          className={
            fullWidth ? "col-span-1 md:col-span-12" : "col-span-1 md:col-span-4"
          }
        >
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
        <div
          className={
            fullWidth ? "col-span-1 md:col-span-12" : "col-span-1 md:col-span-7"
          }
        >
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
              {host}
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
        <div className="relative" ref={dropdownRef}>
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
              className={`absolute z-10 w-full mt-1 border rounded-md shadow-lg max-h-60 overflow-auto ${
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
                          pathParts={[
                            ...pathParts,
                            item.key,
                            releaseGroup.key,
                          ]}
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

  // If we're in the top-level TRACKERS section, extract the default_trackers item
  // This must happen before we partition/group regularItems so the default_trackers
  // field is not rendered twice (once in the tracker tabs and once in the grid).
  const isTrackerConfig = pathParts.includes("TRACKERS") && depth === 0;
  let defaultTrackersItem = null;
  if (isTrackerConfig) {
    const idx = regularItems.findIndex((it) => it.key === "default_trackers");
    if (idx >= 0) {
      defaultTrackersItem = regularItems.splice(idx, 1)[0];
    }
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
    "Bluray & DVD": [
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

  // Track user choices to add available-only trackers into default_trackers
  const [pendingDefaultAdds, setPendingDefaultAdds] = useState(() => new Set());
  const [trackerTab, setTrackerTab] = useState(() => {
    try {
      return sessionStorage.getItem("ua_tracker_tab") || "default";
    } catch (e) {
      return "default";
    }
  });

  const normalizeTrackers = (value) =>
    String(value || "")
      .split(",")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);

  let availableFromExample = [];
  let selectedFromDefault = new Set();
  let configuredFromSubsections = new Set();
  let configuredSet = new Set();
  let availableRemaining = [];
  let configuredArray = [];
  let availableArray = [];
  if (isTrackerConfig && defaultTrackersItem) {
    availableFromExample = getAvailableTrackers(defaultTrackersItem).map((t) =>
      String(t).toUpperCase(),
    );
    selectedFromDefault = new Set(normalizeTrackers(defaultTrackersItem.value));
    configuredFromSubsections = new Set(
      (subsections || [])
        .filter(
          (s) =>
            Array.isArray(s.children) &&
            s.children.some((c) => c.source === "config"),
        )
        .map((s) => String(s.key).toUpperCase()),
    );
    configuredSet = new Set([
      ...selectedFromDefault,
      ...configuredFromSubsections,
    ]);
    availableRemaining = availableFromExample.filter(
      (t) => !configuredSet.has(t),
    );
    // Present configured and available lists in alphabetical order by display name
    configuredArray = Array.from(configuredSet).sort((a, b) =>
      getTrackerDisplayName(a).localeCompare(getTrackerDisplayName(b)),
    );
    availableArray = (availableRemaining || [])
      .slice()
      .sort((a, b) =>
        getTrackerDisplayName(a).localeCompare(getTrackerDisplayName(b)),
      );
  }
  // Ensure arrays are defined in outer scope for rendering even when not tracker config
  if (!configuredArray) configuredArray = [];
  if (!availableArray) availableArray = [];

  return (
    <div className="space-y-6">
      {/* TRACKERS tabbed subsections: Default / Configured / Available */}
      {isTrackerConfig && defaultTrackersItem && (
        <div>
          <div className="ua-config-tabs ua-config-tracker-tabs mb-3 flex space-x-1 overflow-x-auto rounded-lg p-1">
            <button
              type="button"
              onClick={() => setTrackerTab("default")}
              className="ua-config-tracker-tab whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors md:flex-1"
              data-active={trackerTab === "default" ? "true" : "false"}
            >
              Default trackers
            </button>
            <button
              type="button"
              onClick={() => setTrackerTab("configured")}
              className="ua-config-tracker-tab whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors md:flex-1"
              data-active={trackerTab === "configured" ? "true" : "false"}
            >
              Configured trackers
            </button>
            <button
              type="button"
              onClick={() => setTrackerTab("available")}
              className="ua-config-tracker-tab whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors md:flex-1"
              data-active={trackerTab === "available" ? "true" : "false"}
            >
              Available trackers
            </button>
          </div>

          <div>
            <div className={trackerTab === "default" ? "" : "hidden"}>
              <ConfigLeaf
                key={[...pathParts, defaultTrackersItem.key].join("/")}
                item={defaultTrackersItem}
                pathParts={pathParts}
                depth={depth}
                isDarkMode={isDarkMode}
                fullWidth={true}
                allImageHosts={allImageHosts}
                usedImageHosts={usedImageHosts}
                torrentClients={torrentClients}
                onValueChange={onValueChange}
              />
            </div>

            <div
              className={trackerTab === "configured" ? "space-y-4" : "hidden"}
            >
              {/* configured tab content */}
              <div className="space-y-4">
                <div
                  className={
                    isDarkMode
                      ? "text-sm font-medium text-gray-200 mb-2"
                      : "text-sm font-medium text-gray-700 mb-2"
                  }
                >
                  Configured trackers
                </div>
                <div
                  className={`rounded-lg border p-3 ${isDarkMode ? "border-gray-700 bg-gray-900/30" : "border-gray-200 bg-gray-50"}`}
                >
                  <div className="space-y-2">
                    {configuredArray.length === 0 && (
                      <div
                        className={
                          isDarkMode ? "text-gray-400" : "text-gray-500"
                        }
                      >
                        No configured trackers
                      </div>
                    )}
                    {configuredArray.map((tr) => {
                      const subsection = subsections.find(
                        (s) => String(s.key).toUpperCase() === tr,
                      );
                      if (subsection) {
                        const groupKey = [...pathParts, subsection.key].join(
                          "/",
                        );
                        const isOpen = expandedGroups.has(groupKey);
                        return (
                          <div key={tr} className="mb-2">
                            <div className="flex items-center justify-between">
                              <button
                                type="button"
                                onClick={() => toggleGroup(groupKey)}
                                aria-expanded={isOpen}
                                className={`flex items-center justify-between w-full px-3 py-2 text-sm font-medium rounded ${isDarkMode ? "text-gray-200" : "text-gray-800"}`}
                              >
                                <span
                                  className={
                                    isDarkMode
                                      ? "text-xs font-mono text-purple-300"
                                      : "text-xs font-mono text-purple-700"
                                  }
                                >
                                  {getTrackerDisplayName(tr)}
                                </span>
                                <span
                                  className="transition-transform"
                                  style={{
                                    transform: isOpen
                                      ? "rotate(90deg)"
                                      : "rotate(0deg)",
                                  }}
                                >
                                  &gt;
                                </span>
                              </button>
                            </div>
                            {isOpen && (
                              <div
                                className={`rounded-lg border p-3 mt-2 ${isDarkMode ? "border-gray-700 bg-gray-900/20" : "border-gray-200 bg-white"}`}
                              >
                                <ItemList
                                  items={subsection.children}
                                  pathParts={[...pathParts, subsection.key]}
                                  depth={depth + 1}
                                  isDarkMode={isDarkMode}
                                  allImageHosts={allImageHosts}
                                  usedImageHosts={usedImageHosts}
                                  fullWidth={true}
                                  expandedGroups={expandedGroups}
                                  toggleGroup={toggleGroup}
                                  torrentClients={torrentClients}
                                  onValueChange={onValueChange}
                                />
                                <div className="mt-2 flex items-center justify-end">
                                  <button
                                    type="button"
                                    onClick={async () => {
                                      const ok = await showConfirmModal(
                                        `Remove configured tracker ${tr}? This will remove the user's overrides for this tracker.`,
                                      );
                                      if (!ok) return;
                                      try {
                                        const resp = await apiFetch(
                                          `${API_BASE}/config_remove_subsection`,
                                          {
                                            method: "POST",
                                            headers: {
                                              "Content-Type":
                                                "application/json",
                                            },
                                            body: JSON.stringify({
                                              path: [
                                                ...pathParts,
                                                subsection.key,
                                              ],
                                            }),
                                          },
                                        );
                                        const data = await resp.json();
                                        if (!data.success)
                                          throw new Error(
                                            data.error || "Failed",
                                          );

                                        // If this tracker is also in default_trackers, remove it there as well
                                        try {
                                          if (
                                            selectedFromDefault &&
                                            selectedFromDefault.has(tr)
                                          ) {
                                            const nextDefault = Array.from(
                                              selectedFromDefault,
                                            )
                                              .filter((x) => x !== tr)
                                              .join(", ");
                                            const resp2 = await apiFetch(
                                              `${API_BASE}/config_update`,
                                              {
                                                method: "POST",
                                                headers: {
                                                  "Content-Type":
                                                    "application/json",
                                                },
                                                body: JSON.stringify({
                                                  path: [
                                                    ...pathParts,
                                                    "default_trackers",
                                                  ],
                                                  value: nextDefault,
                                                }),
                                              },
                                            );
                                            const data2 = await resp2.json();
                                            if (!data2.success)
                                              throw new Error(
                                                data2.error ||
                                                  "Failed to update default_trackers",
                                              );
                                          }
                                        } catch (err) {
                                          console.warn(
                                            "Failed to update default_trackers after removing subsection",
                                            err,
                                          );
                                        }

                                        try {
                                          sessionStorage.setItem(
                                            "ua_active_tab",
                                            String(
                                              pathParts[0] || "",
                                            ).toLowerCase(),
                                          );
                                          sessionStorage.setItem(
                                            "ua_tracker_tab",
                                            trackerTab || "configured",
                                          );
                                        } catch (e) {
                                          /* ignore */
                                        }
                                        window.location.reload();
                                      } catch (err) {
                                        alert(
                                          err.message ||
                                            "Failed to remove subsection",
                                        );
                                      }
                                    }}
                                    className="ml-2 px-2 py-1 text-xs rounded bg-red-600 text-white"
                                  >
                                    Remove
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      }
                      // Tracker selected in default but not configured in file - allow removing from default
                      return (
                        <div
                          key={tr}
                          className="inline-flex items-center mr-2 mb-2 px-2 py-1 rounded text-xs"
                        >
                          <div
                            className={
                              isDarkMode
                                ? "bg-purple-700 text-white px-2 py-1 rounded"
                                : "bg-purple-100 text-purple-800 px-2 py-1 rounded"
                            }
                          >
                            {getTrackerDisplayName(tr)}
                          </div>
                          <button
                            type="button"
                            onClick={async () => {
                              const ok = await showConfirmModal({
                                message: `Remove ${tr} from default trackers?`,
                                confirmLabel: "Remove",
                              });
                              if (!ok) return;
                              try {
                                const next = Array.from(selectedFromDefault)
                                  .filter((x) => x !== tr)
                                  .join(", ");
                                const resp = await apiFetch(
                                  `${API_BASE}/config_update`,
                                  {
                                    method: "POST",
                                    headers: {
                                      "Content-Type": "application/json",
                                    },
                                    body: JSON.stringify({
                                      path: [...pathParts, "default_trackers"],
                                      value: next,
                                    }),
                                  },
                                );
                                const data = await resp.json();
                                if (!data.success)
                                  throw new Error(data.error || "Failed");
                                try {
                                  sessionStorage.setItem(
                                    "ua_active_tab",
                                    String(pathParts[0] || "").toLowerCase(),
                                  );
                                  sessionStorage.setItem(
                                    "ua_tracker_tab",
                                    trackerTab || "default",
                                  );
                                } catch (e) {
                                  /* ignore */
                                }
                                window.location.reload();
                              } catch (err) {
                                alert(
                                  err.message ||
                                    "Failed to update default trackers",
                                );
                              }
                            }}
                            className="ml-2 px-2 py-1 text-xs rounded bg-red-600 text-white"
                          >
                            Remove
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            <div className={trackerTab === "available" ? "" : "hidden"}>
              <div>
                <div
                  className={
                    isDarkMode
                      ? "text-sm font-medium text-gray-200 mb-2"
                      : "text-sm font-medium text-gray-700 mb-2"
                  }
                >
                  Available trackers
                </div>
                <div
                  className={`rounded-lg border p-3 ${isDarkMode ? "border-gray-700 bg-gray-900/30" : "border-gray-200 bg-gray-50"}`}
                >
                  {availableArray.length === 0 && (
                    <div
                      className={isDarkMode ? "text-gray-400" : "text-gray-500"}
                    >
                      No additional available trackers
                    </div>
                  )}
                  <div className="space-y-2">
                    {availableArray.map((t) => {
                      const subsection = subsections.find(
                        (s) => String(s.key).toUpperCase() === t,
                      );
                      const isInDefault =
                        selectedFromDefault && selectedFromDefault.has(t);
                      const isPending = pendingDefaultAdds.has(t);
                      if (subsection) {
                        const groupKey = [...pathParts, subsection.key].join(
                          "/",
                        );
                        const isOpen = expandedGroups.has(groupKey);
                        return (
                          <div key={t} className="mb-2">
                            <button
                              type="button"
                              onClick={() => toggleGroup(groupKey)}
                              aria-expanded={isOpen}
                              className={`flex items-center justify-between w-full px-3 py-2 text-sm font-medium rounded ${isDarkMode ? "text-gray-200" : "text-gray-800"}`}
                            >
                              <span
                                className={
                                  isDarkMode
                                    ? "text-xs font-mono text-gray-200"
                                    : "text-xs font-mono text-gray-700"
                                }
                              >
                                {getTrackerDisplayName(t)}
                              </span>
                              <span
                                className="transition-transform"
                                style={{
                                  transform: isOpen
                                    ? "rotate(90deg)"
                                    : "rotate(0deg)",
                                }}
                              >
                                &gt;
                              </span>
                            </button>
                            {isOpen && (
                              <div
                                className={`rounded-lg border p-3 mt-2 ${isDarkMode ? "border-gray-700 bg-gray-900/20" : "border-gray-200 bg-white"}`}
                              >
                                <ItemList
                                  items={subsection.children}
                                  pathParts={[...pathParts, subsection.key]}
                                  depth={depth + 1}
                                  isDarkMode={isDarkMode}
                                  allImageHosts={allImageHosts}
                                  usedImageHosts={usedImageHosts}
                                  fullWidth={true}
                                  expandedGroups={expandedGroups}
                                  toggleGroup={toggleGroup}
                                  torrentClients={torrentClients}
                                  onValueChange={onValueChange}
                                />
                                <div className="mt-2">
                                  <label className="inline-flex items-center text-xs mr-2">
                                    <input
                                      type="checkbox"
                                      checked={isInDefault || isPending}
                                      onChange={async (e) => {
                                        const checked = e.target.checked;
                                        const nextPending = new Set(
                                          pendingDefaultAdds,
                                        );
                                        if (checked) {
                                          nextPending.add(t);
                                        } else {
                                          nextPending.delete(t);
                                        }
                                        setPendingDefaultAdds(nextPending);
                                        // Compute next default trackers value and queue change
                                        const nextDefaultSet = new Set(
                                          selectedFromDefault || [],
                                        );
                                        for (const x of nextPending)
                                          nextDefaultSet.add(x);
                                        // If user unchecked an already-selected default, remove it
                                        if (
                                          !checked &&
                                          selectedFromDefault &&
                                          selectedFromDefault.has(t)
                                        ) {
                                          nextDefaultSet.delete(t);
                                        }
                                        const nextDefault =
                                          Array.from(nextDefaultSet).join(", ");
                                        const originalDefault =
                                          normalizeTrackers(
                                            defaultTrackersItem.value,
                                          ).join(", ");
                                        onValueChange(
                                          [...pathParts, "default_trackers"],
                                          nextDefault,
                                          {
                                            originalValue: originalDefault,
                                            isSensitive: false,
                                            isRedacted: false,
                                            readOnly: false,
                                          },
                                        );
                                      }}
                                      className="h-4 w-4 mr-2"
                                    />
                                    <span
                                      className={
                                        isDarkMode
                                          ? "text-gray-300"
                                          : "text-gray-700"
                                      }
                                    >
                                      Add to default trackers
                                    </span>
                                  </label>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      }
                      return (
                        <div
                          key={t}
                          className={
                            isDarkMode
                              ? "inline-block px-2 py-1 bg-gray-800 text-gray-200 rounded text-xs"
                              : "inline-block px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs"
                          }
                        >
                          <div className="flex items-center gap-2">
                            <div>{getTrackerDisplayName(t)}</div>
                            <label className="inline-flex items-center text-xs">
                              <input
                                type="checkbox"
                                checked={
                                  (selectedFromDefault &&
                                    selectedFromDefault.has(t)) ||
                                  pendingDefaultAdds.has(t)
                                }
                                onChange={(e) => {
                                  const checked = e.target.checked;
                                  const nextPending = new Set(
                                    pendingDefaultAdds,
                                  );
                                  if (checked) nextPending.add(t);
                                  else nextPending.delete(t);
                                  setPendingDefaultAdds(nextPending);
                                  const nextDefaultSet = new Set(
                                    selectedFromDefault || [],
                                  );
                                  for (const x of nextPending)
                                    nextDefaultSet.add(x);
                                  if (
                                    !checked &&
                                    selectedFromDefault &&
                                    selectedFromDefault.has(t)
                                  ) {
                                    nextDefaultSet.delete(t);
                                  }
                                  const nextDefault =
                                    Array.from(nextDefaultSet).join(", ");
                                  const originalDefault = normalizeTrackers(
                                    defaultTrackersItem.value,
                                  ).join(", ");
                                  onValueChange(
                                    [...pathParts, "default_trackers"],
                                    nextDefault,
                                    {
                                      originalValue: originalDefault,
                                      isSensitive: false,
                                      isRedacted: false,
                                      readOnly: false,
                                    },
                                  );
                                }}
                                className="h-4 w-4"
                              />
                              <span className="ml-1">Add to defaults</span>
                            </label>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
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
              const subgroupKey = [
                ...pathParts,
                subgroupParentKey,
                gname,
              ].join("/");
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
        // When rendering the top-level TRACKERS section we handle tracker subsections
        // inside the tabbed UI above, so skip the generic subsections rendering
        // to avoid duplicate lists.
        if (pathParts.includes("TRACKERS") && depth === 0) {
          return null;
        }
        const isTorrentClientConfig =
          pathParts.includes("TORRENT_CLIENTS") && depth === 0;
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
          normalizeConfigHeading(item.key) ===
            "GENERAL DESCRIPTION SETTINGS";
        const isDescriptionHeadersOverridesSubsection =
          pathParts[0] === "DEFAULT" &&
          depth === 0 &&
          item.subsection === true &&
          normalizeConfigHeading(item.key) ===
            "DESCRIPTION HEADERS AND OVERRIDES";
        const isStaticSubsection =
          item.subsection === true && !isMetadataCachingSubsection;
        const isCollapsible =
          isTrackerConfig || isTorrentClientConfig;
        const nextPath = item.subsection ? pathParts : [...pathParts, item.key];
        const nextDepth = item.subsection ? depth : depth + 1;
        const groupKey = [...pathParts, item.key].join("/");
        const isOpen = expandedGroups.has(groupKey);

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
          const logoKeys = new Set([
            "add_logo",
            "logo_size",
            "logo_language",
          ]);
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

        const nested = (
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
                  {item.subsection === true
                    ? formatConfigHeading(item.key)
                    : isTorrentClientConfig
                      ? getConfigBlockLabel(item.key)
                      : getTrackerDisplayName(item.key)}
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
                  {nested}
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
  isDarkMode,
  onToggleMode,
  onLogout,
}) {
  const defaultSection = sections.find(
    (section) => section.section === "DEFAULT",
  );
  const defaultGroups = getDefaultNavigationGroups(defaultSection);
  const configurationSections = sections.filter(
    (section) => section.section !== "DEFAULT",
  );

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
      <div className="ua-config-sidebar-brand flex h-20 shrink-0 items-center justify-between gap-3 border-b px-5 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <img
            src={window.UA_LOGO_URL || "/static/img/logo.svg"}
            alt="Upload-Assistant logo"
            className="h-8 w-8 shrink-0"
          />
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold uppercase tracking-widest opacity-60">
              Upload Assistant
            </div>
            <div className="mt-1 truncate text-lg font-bold">
              Configuration
            </div>
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

      <nav
        className="ua-config-sidebar-nav min-h-0 flex-1 overflow-y-auto px-3 py-4"
        aria-label="Configuration sections"
      >
        {defaultGroups.length > 0 && (
          <div className="mb-5">
            <div className="ua-config-nav-heading px-3 pb-2 text-xs font-semibold uppercase tracking-wider">
              General Settings
            </div>
            <div className="space-y-1">
              {defaultGroups.map((group) =>
                navButton({
                  id: `default-${group.id}`,
                  label: group.label,
                  tab: "default",
                  subTab: group.id,
                  nested: true,
                }),
              )}
            </div>
          </div>
        )}

        {configurationSections.length > 0 && (
          <div className="mb-5">
            <div className="ua-config-nav-heading px-3 pb-2 text-xs font-semibold uppercase tracking-wider">
              Configuration
            </div>
            <div className="space-y-1">
              {configurationSections.map((section) =>
                navButton({
                  id: section.section,
                  label: getConfigSectionLabel(section.section),
                  tab: section.section.toLowerCase(),
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

      <div className="ua-config-sidebar-footer border-t p-4">
        <div className="ua-config-nav-heading mb-2 text-xs font-semibold uppercase tracking-wider">
          Appearance
        </div>
        <select
          value={colorTheme}
          onChange={onColorThemeChange}
          aria-label="Color theme"
          className="ua-theme-picker w-full rounded-lg px-3 py-2 text-sm"
        >
          {colorThemes.map((theme) => (
            <option key={theme.id} value={theme.id}>
              {theme.label}
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

        <div className="mt-4 grid gap-2">
          <a
            href="/"
            className="ua-config-sidebar-action rounded-lg px-3 py-2 text-center text-sm font-semibold"
          >
            ← Back to Upload
          </a>
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
  const [expandedGroups, setExpandedGroups] = useState(new Set());
  const [pendingChanges, setPendingChanges] = useState(new Map());
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
      return sessionStorage.getItem("ua_active_subtab") || "general";
    } catch (e) {
      return "general";
    }
  });
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [torrentClients, setTorrentClients] = useState([]);

  useEffect(() => {
    const handleColorThemeChange = (event) => {
      setColorThemeState(event.detail?.theme || getStoredColorTheme());
    };
    window.addEventListener("ua-theme-change", handleColorThemeChange);
    return () =>
      window.removeEventListener("ua-theme-change", handleColorThemeChange);
  }, []);

  const handleColorThemeChange = (event) => {
    setColorThemeState(setColorTheme(event.target.value));
  };
  const getSubTabsForSection = (section) => {
    if (section?.section === "DEFAULT") {
      return getDefaultNavigationGroups(section);
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
          // keep ua_tracker_tab; ItemList reads it directly on mount
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
    } catch (error) {
      setStatus({
        text: error.message || "Failed to load config options",
        type: "error",
      });
    }
  };

  const onValueChange = (path, value, meta) => {
    const pathKey = path.join("/");
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

  const saveAllChanges = async () => {
    if (pendingChanges.size === 0) {
      setStatusWithClear("No changes to save.", "warn", 1500);
      return;
    }
    setIsSaving(true);
    setStatusWithClear(
      `Saving ${pendingChanges.size} change${pendingChanges.size === 1 ? "" : "s"}...`,
      "info",
    );
    try {
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
  const activeDefaultGroup =
    activeSection?.section === "DEFAULT"
      ? getDefaultNavigationGroups(activeSection).find(
          (group) => group.id === activeSubTab,
        )
      : null;
  const activeTitle =
    activeTab === "security"
      ? "Security"
      : activeTab === "access-log"
        ? "Access Log"
        : activeDefaultGroup?.label ||
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
  const saveDisabled = isSaving || pendingChanges.size === 0;
  const saveButtonClass =
    "ua-config-save-button rounded-lg px-4 py-2 text-sm font-semibold" +
    (saveDisabled ? " cursor-not-allowed opacity-50" : "");
  const statusTypeClass = statusClassFor(status.type, isDarkMode);

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
      {isMobileNavOpen && (
        <button
          type="button"
          className="ua-config-drawer-overlay fixed inset-0 z-40 md:hidden"
          aria-label="Close configuration navigation"
          onClick={() => setIsMobileNavOpen(false)}
        ></button>
      )}

      <div className="min-h-screen md:flex">
        <aside
          id="config-sidebar"
          className={
            "ua-config-sidebar fixed inset-y-0 left-0 z-50 w-72 transform transition-transform duration-200 " +
            "md:sticky md:top-0 md:z-20 md:h-screen md:translate-x-0 " +
            (isMobileNavOpen ? "translate-x-0" : "-translate-x-full")
          }
        >
          <ConfigSidebar
            sections={sections}
            activeTab={activeTab}
            activeSubTab={activeSubTab}
            onNavigate={navigateTo}
            onClose={() => setIsMobileNavOpen(false)}
            colorTheme={colorTheme}
            onColorThemeChange={handleColorThemeChange}
            isDarkMode={isDarkMode}
            onToggleMode={() => setIsDarkMode((prev) => !prev)}
            onLogout={handleLogout}
          />
        </aside>

        <div className="min-w-0 flex-1">
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
                    className={statusClass + " " + statusTypeClass + " hidden lg:inline"}
                    role="status"
                  >
                    {status.text}
                  </span>
                )}
                {pendingChanges.size > 0 && !status.text && (
                  <span className="ua-config-pending-count hidden text-sm lg:inline">
                    {pendingChanges.size} unsaved{" "}
                    {pendingChanges.size === 1 ? "change" : "changes"}
                  </span>
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
                        onValueChange={onValueChange}
                      />
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
