const { useEffect, useMemo, useRef, useState } = React;
const APP_BASE = window.location.origin;
const STATS_PERIOD_KEY = "ua_stats_period";
const STATS_PERIODS = [
  ["today", "Today"],
  ["this_month", "This month"],
  ["last_month", "Last month"],
  ["7d", "7d"],
  ["30d", "30d"],
  ["90d", "90d"],
  ["1y", "1y"],
  ["all", "All"],
];
const TREND_VIEW_KEY = "ua_stats_trend_view";
const STATS_SETTINGS_KEY = "ua_stats_settings_v1";
const DEFAULT_STATS_SETTINGS = Object.freeze({
  timezone: "utc",
  dateFormat: "YYYY-MM-DD",
  chartGradient: false,
  showFavicons: true,
  visibility: {
    throughput: true,
    itemsCompleted: true,
    successfulUploads: true,
    dataUploaded: true,
    uniqueDataUploaded: true,
    efficiency: true,
    duplicatesPrevented: true,
    pioneeringRate: true,
    hashingAvoided: true,
    health: true,
    cacheHitRate: true,
    cacheWrites: true,
    apiOperations: true,
    artifactsSummary: true,
    torrentsCreated: true,
    nzbsCreated: true,
    screenshotsCreated: true,
    dailyActivity: true,
    uploadFlow: true,
    activityHeatmap: true,
    uploadsByDestination: true,
    categories: true,
    contentTime: true,
    artifactActivity: true,
    mediaProfile: true,
    streamingServices: true,
    personalReleases: true,
    cacheByProvider: true,
    externalOperations: true,
    executionSource: true,
  },
});
const SUMMARY_VISIBILITY = [
  {
    key: "throughput",
    label: "Throughput & scale",
    children: [
      ["itemsCompleted", "Items completed"],
      ["successfulUploads", "Successful uploads"],
      ["dataUploaded", "Data uploaded"],
      ["uniqueDataUploaded", "Unique data uploaded"],
    ],
  },
  {
    key: "efficiency",
    label: "Efficiency & intelligence",
    children: [
      ["duplicatesPrevented", "Duplicates prevented"],
      ["pioneeringRate", "Pioneering rate"],
      ["hashingAvoided", "Hashing I/O avoided"],
    ],
  },
  {
    key: "health",
    label: "Health & infrastructure",
    children: [
      ["cacheHitRate", "Cache hit rate"],
      ["cacheWrites", "Cache writes"],
      ["apiOperations", "API operations"],
    ],
  },
  {
    key: "artifactsSummary",
    label: "Generated artifacts",
    children: [
      ["torrentsCreated", "Torrents created"],
      ["nzbsCreated", "NZBs created"],
      ["screenshotsCreated", "Screenshots created"],
    ],
  },
];
const SECTION_VISIBILITY = [
  ["dailyActivity", "Daily activity"],
  ["uploadFlow", "Upload flow"],
  ["activityHeatmap", "Activity heatmap"],
  ["uploadsByDestination", "Uploads by destination"],
  ["categories", "Categories"],
  ["contentTime", "Successful media time"],
  ["artifactActivity", "Artifact activity"],
  ["mediaProfile", "Media profile"],
  ["streamingServices", "Streaming services"],
  ["personalReleases", "Personal releases"],
  ["cacheByProvider", "Cache by provider"],
  ["externalOperations", "External operations"],
  ["executionSource", "Execution source"],
];
const CHART_COLORS = [
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#a855f7",
  "#ef4444",
  "#06b6d4",
  "#f97316",
  "#64748b",
];

const LucideIcon = window.UALucideIcon;
const AssetIcon = ({ name }) => <LucideIcon name={name} className="h-5 w-5" />;

const formatNumber = (value) => new Intl.NumberFormat().format(value || 0);
const formatCompactNumber = (value) =>
  new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value || 0);
const formatDuration = (value) =>
  value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value || 0}ms`;
const formatMediaHours = (seconds) => {
  const hours = Math.max(0, Number(seconds) || 0) / 3600;
  return `${new Intl.NumberFormat(undefined, {
    maximumFractionDigits: hours >= 100 ? 0 : 1,
  }).format(hours)} h`;
};
const formatMediaTime = (seconds) => {
  const totalMinutes = Math.round(Math.max(0, Number(seconds) || 0) / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours ? `${formatNumber(hours)}h ${minutes}m` : `${minutes}m`;
};
const formatBytes = (value) => {
  if (!value || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const power = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    units.length - 1,
  );
  return `${(value / 1024 ** power).toFixed(power ? 1 : 0)} ${units[power]}`;
};
const isoTodayUtc = () => new Date().toISOString().slice(0, 10);
const isoTodayLocal = () => {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};
const browserTimeZone = () =>
  Intl.DateTimeFormat().resolvedOptions().timeZone || "this browser";
const loadStatsSettings = () => {
  try {
    const stored = JSON.parse(window.UAStorage.get(STATS_SETTINGS_KEY) || "{}");
    return {
      ...DEFAULT_STATS_SETTINGS,
      ...stored,
      timezone: stored.timezone === "browser" ? "browser" : "utc",
      visibility: {
        ...DEFAULT_STATS_SETTINGS.visibility,
        ...(stored.visibility || {}),
      },
    };
  } catch (_error) {
    return {
      ...DEFAULT_STATS_SETTINGS,
      visibility: { ...DEFAULT_STATS_SETTINGS.visibility },
    };
  }
};
const formatStatsDate = (value, pattern = "YYYY-MM-DD", short = false) => {
  const [year, month, day] = String(value || "").split("-");
  if (!year || !month || !day) return value || "";
  const separator = pattern.includes("/") ? "/" : "-";
  const parts = pattern.split(/[-/]/);
  const values = { YYYY: year, MM: month, DD: day };
  if (short) {
    const shortParts = parts.filter((part) => part !== "YYYY");
    return shortParts.map((part) => values[part]).join(separator);
  }
  return parts.map((part) => values[part]).join(separator);
};
const formatDimensionValue = (value) =>
  String(value || "Unknown").replaceAll("_", " ");
const OPERATION_LABELS = {
  credential_sync: "Sync credentials",
  image_upload: "Upload images",
  nntp_post: "Post to Usenet",
  search: "Search existing releases",
  torrent_client_add: "Add to torrent client",
  torrent_client_search: "Search torrent client",
  upload: "Upload release",
};
const formatOperation = (value) => {
  const key = String(value || "")
    .trim()
    .toLowerCase();
  if (!key) return "Unknown";
  return (
    OPERATION_LABELS[key] ||
    key
      .replaceAll("_", " ")
      .replace(/\b\w/g, (character) => character.toUpperCase())
  );
};
const formatTrend = (value, suffix = "%") => {
  if (value == null) return "";
  if (value === 0) return `• 0${suffix}`;
  return `${value > 0 ? "▲" : "▼"} ${value > 0 ? "+" : ""}${value}${suffix}`;
};

const downloadText = (filename, content, type) => {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
};

const csvCell = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;

const trackerFaviconUrl = (destination) => {
  const slug = String(destination || "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
  return slug ? `/static/img/trackers/${slug}.png` : "";
};

const TrackerFavicon = ({ destination, className = "h-5 w-5" }) => {
  const src = trackerFaviconUrl(destination);
  if (!src) return null;
  return (
    <img
      src={src}
      alt=""
      aria-hidden="true"
      className={`${className} flex-none rounded-sm object-contain`}
      onError={(event) => event.currentTarget.classList.add("hidden")}
    />
  );
};

function WorkspaceNav({
  colorTheme,
  interfaceStyle,
  isDarkMode,
  onColorThemeChange,
  onInterfaceStyleChange,
  onOpenChangelog,
  onOpenHelp,
  onToggleMode,
  onLogout,
}) {
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const appearanceRef = useRef(null);
  const links = [
    ["upload", "Upload", "/"],
    ["config", "Config", "/config"],
    ["stats", "Stats", "/stats"],
  ];
  useEffect(() => {
    if (!appearanceOpen) return undefined;
    const closeWhenOutside = (event) => {
      if (!appearanceRef.current?.contains(event.target)) {
        setAppearanceOpen(false);
      }
    };
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setAppearanceOpen(false);
    };
    document.addEventListener("pointerdown", closeWhenOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeWhenOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [appearanceOpen]);

  return (
    <>
      <aside
        className="ua-app-rail fixed inset-y-0 left-0 z-30 hidden w-20 flex-col border-r md:flex"
        aria-label="Application navigation"
      >
        <div className="ua-app-rail-brand flex h-20 shrink-0 flex-col items-center justify-center gap-1 border-b px-2">
          <img
            src={window.UA_LOGO_URL}
            alt="Upload Assistant"
            className="h-8 w-8"
          />
          <span className="text-[0.65rem] font-semibold opacity-60">
            {window.UA_APP_VERSION}
          </span>
        </div>
        <nav className="grid gap-1 p-2" aria-label="Workspaces">
          {links.map(([id, label, href]) => (
            <a
              key={id}
              href={`${APP_BASE}${href}`}
              className="ua-app-rail-button rounded-lg"
              data-active={id === "stats" ? "true" : "false"}
              aria-current={id === "stats" ? "page" : undefined}
            >
              <AssetIcon name={id} />
              <span>{label}</span>
            </a>
          ))}
        </nav>
        <div className="min-h-4 flex-1"></div>
        <div className="ua-app-rail-footer grid shrink-0 gap-1 border-t p-2">
          <button
            type="button"
            className="ua-app-rail-button rounded-lg"
            onClick={onOpenChangelog}
            aria-haspopup="dialog"
          >
            <AssetIcon name="changelog" />
            <span>Changelog</span>
          </button>
          <button
            type="button"
            className="ua-app-rail-button rounded-lg"
            onClick={onOpenHelp}
            aria-haspopup="dialog"
          >
            <AssetIcon name="help" />
            <span>Help</span>
          </button>
          <div ref={appearanceRef} className="relative min-w-0 w-full">
            <button
              type="button"
              className="ua-app-rail-button rounded-lg"
              onClick={() => setAppearanceOpen((open) => !open)}
              aria-expanded={appearanceOpen}
            >
              <AssetIcon name="palette" />
              <span>Appearance</span>
            </button>
            {appearanceOpen && (
              <div className="ua-app-rail-popover absolute bottom-0 left-full z-[60] ml-2 w-64 rounded-xl border p-4 shadow-2xl">
                <h2 className="text-sm font-semibold">Appearance</h2>
                <label className="ua-app-rail-popover-label mt-3 block text-xs font-semibold">
                  Color theme
                </label>
                <select
                  aria-label="Color theme"
                  value={colorTheme}
                  onChange={(event) => {
                    onColorThemeChange(event.target.value);
                    setAppearanceOpen(false);
                  }}
                  className="ua-theme-picker mt-1 w-full rounded-lg px-3 py-2 text-sm"
                >
                  {(window.UAThemes || []).map((theme) => (
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
                    onInterfaceStyleChange(event.target.value);
                    setAppearanceOpen(false);
                  }}
                  className="ua-theme-picker mt-1 w-full rounded-lg px-3 py-2 text-sm"
                >
                  {(window.UAInterfaceStyles || []).map((style) => (
                    <option key={style.id} value={style.id}>
                      {style.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="ua-config-mode-button mt-3 flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm"
                  onClick={onToggleMode}
                  aria-pressed={isDarkMode}
                >
                  <span>{isDarkMode ? "Dark mode" : "Light mode"}</span>
                  <LucideIcon
                    name={isDarkMode ? "moon" : "sun"}
                    className="h-4 w-4"
                  />
                </button>
              </div>
            )}
          </div>
          <button
            type="button"
            className="ua-app-rail-button rounded-lg text-red-500"
            onClick={onLogout}
          >
            <AssetIcon name="logout" />
            <span>Log out</span>
          </button>
        </div>
      </aside>
      <div className="mx-4 mt-4 md:hidden">
        <nav
          className="ua-workspace-switcher rounded-lg"
          data-stretch="true"
          aria-label="Workspace"
        >
          {links.map(([id, label, href]) => (
            <a
              key={id}
              href={`${APP_BASE}${href}`}
              className="ua-workspace-link rounded-md"
              data-active={id === "stats" ? "true" : "false"}
              aria-current={id === "stats" ? "page" : undefined}
            >
              {label}
            </a>
          ))}
        </nav>
      </div>
    </>
  );
}

function HelpResourcesModal({ onClose }) {
  const dialogRef = window.useUAModalFocus(onClose);
  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="ua-config-modal flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="stats-help-title"
        tabIndex="-1"
      >
        <header className="ua-config-section-heading flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 id="stats-help-title" className="text-lg font-semibold">
              Help &amp; Resources
            </h2>
            <p className="mt-1 text-sm opacity-60">
              Official Upload Assistant documentation and setup guides.
            </p>
          </div>
          <button
            type="button"
            className="ua-config-icon-button h-9 w-9"
            onClick={onClose}
            aria-label="Close help and resources"
            data-ua-modal-initial-focus
          >
            <LucideIcon name="x" className="h-4 w-4" />
          </button>
        </header>
        <div className="grid min-h-0 gap-4 overflow-y-auto p-5 md:grid-cols-2">
          {(window.UAHelpResourceGroups || []).map((group) => (
            <section key={group.title} className="rounded-xl border p-4">
              <h3 className="mb-3 text-sm font-semibold">{group.title}</h3>
              <div className="space-y-2">
                {group.links.map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block rounded-lg border px-3 py-2.5"
                  >
                    <span className="flex items-center gap-1 text-sm font-semibold">
                      {link.label}
                      <LucideIcon
                        name="external-link"
                        className="h-3.5 w-3.5"
                      />
                    </span>
                    <span className="mt-1 block text-xs opacity-60">
                      {link.description}
                    </span>
                  </a>
                ))}
              </div>
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}

const StatsIcon = ({ name, className = "h-5 w-5" }) => (
  <LucideIcon name={name} className={className} />
);

const SettingsToggle = ({ checked, label, onChange, nested = false }) => (
  <label
    className={`ua-stats-settings-option flex cursor-pointer items-center justify-between gap-4 rounded-lg border px-3 py-2 text-sm ${nested ? "ml-5" : ""}`}
  >
    <span className={nested ? "opacity-75" : "font-medium"}>{label}</span>
    <input
      type="checkbox"
      checked={checked}
      onChange={(event) => onChange(event.target.checked)}
      className="h-4 w-4 accent-[var(--ua-copper-bright)]"
    />
  </label>
);

function StatsSettingsModal({
  mode,
  onModeChange,
  settings,
  onChange,
  onClose,
  localTimeLabel,
}) {
  const dialogRef = window.useUAModalFocus(onClose);
  const updateSetting = (key, value) => onChange({ ...settings, [key]: value });
  const updateVisibility = (key, value) =>
    onChange({
      ...settings,
      visibility: { ...settings.visibility, [key]: value },
    });
  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="ua-config-modal ua-stats-settings-modal flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="stats-settings-title"
        tabIndex="-1"
      >
        <header className="ua-config-section-heading flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 id="stats-settings-title" className="text-lg font-semibold">
              Stats display
            </h2>
            <p className="mt-1 text-sm opacity-60">
              These preferences are saved in this browser.
            </p>
          </div>
          <button
            type="button"
            className="ua-config-icon-button h-9 w-9"
            onClick={onClose}
            aria-label="Close stats display"
            data-ua-modal-initial-focus
          >
            <LucideIcon name="x" className="h-4 w-4" />
          </button>
        </header>
        <div className="min-h-0 space-y-5 overflow-y-auto p-5">
          <section className="ua-stats-settings-group grid gap-3 rounded-xl border p-4 sm:grid-cols-2 md:grid-cols-3">
            <label className="grid min-w-0 gap-1 text-sm">
              <span className="font-medium">Activity source</span>
              <select
                value={mode}
                onChange={(event) => onModeChange(event.target.value)}
                className="ua-stats-control w-full min-w-0 rounded-xl px-4 text-sm"
                aria-label="Statistics mode"
              >
                <option value="real">Real activity</option>
                <option value="debug">Debug simulations</option>
              </select>
            </label>
            <label className="grid min-w-0 gap-1 text-sm">
              <span className="font-medium">Date &amp; time</span>
              <select
                value={settings.timezone}
                onChange={(event) =>
                  updateSetting("timezone", event.target.value)
                }
                className="ua-theme-picker w-full min-w-0 rounded-lg px-3 py-2 text-sm"
              >
                <option value="utc">UTC</option>
                <option value="browser">{localTimeLabel}</option>
              </select>
            </label>
            <label className="grid min-w-0 gap-1 text-sm">
              <span className="font-medium">Date format</span>
              <select
                value={settings.dateFormat}
                onChange={(event) =>
                  updateSetting("dateFormat", event.target.value)
                }
                className="ua-theme-picker w-full min-w-0 rounded-lg px-3 py-2 text-sm"
              >
                <option value="YYYY-MM-DD">YYYY-MM-DD</option>
                <option value="DD-MM-YYYY">DD-MM-YYYY</option>
                <option value="MM-DD-YYYY">MM-DD-YYYY</option>
                <option value="YYYY/MM/DD">YYYY/MM/DD</option>
                <option value="DD/MM/YYYY">DD/MM/YYYY</option>
                <option value="MM/DD/YYYY">MM/DD/YYYY</option>
              </select>
            </label>
            {settings.timezone === "browser" && (
              <p className="ua-stats-settings-note rounded-lg border px-3 py-2 text-xs opacity-70 sm:col-span-2 md:col-span-3">
                Historical statistics are stored in UTC calendar-day buckets.
                Activity near midnight remains assigned to its original UTC day.
              </p>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold">Chart &amp; icons</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              <SettingsToggle
                checked={settings.chartGradient}
                label="Daily activity color gradient"
                onChange={(value) => updateSetting("chartGradient", value)}
              />
              <SettingsToggle
                checked={settings.showFavicons}
                label="Tracker and indexer favicons"
                onChange={(value) => updateSetting("showFavicons", value)}
              />
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold">Summary blocks</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              {SUMMARY_VISIBILITY.map((group) => (
                <div key={group.key} className="space-y-2">
                  <SettingsToggle
                    checked={settings.visibility[group.key]}
                    label={group.label}
                    onChange={(value) => updateVisibility(group.key, value)}
                  />
                  {group.children.map(([key, label]) => (
                    <SettingsToggle
                      key={key}
                      checked={settings.visibility[key]}
                      label={label}
                      nested
                      onChange={(value) => updateVisibility(key, value)}
                    />
                  ))}
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold">Detail blocks</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {SECTION_VISIBILITY.map(([key, label]) => (
                <SettingsToggle
                  key={key}
                  checked={settings.visibility[key]}
                  label={label}
                  onChange={(value) => updateVisibility(key, value)}
                />
              ))}
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}

const MetricIcon = ({ type }) => (
  <span className="ua-stats-metric-icon flex h-8 w-8 flex-none items-center justify-center">
    <StatsIcon name={type} className="h-5 w-5" />
  </span>
);

const Card = ({ icon, label, value, detail, trend }) => (
  <article className="ua-stats-summary-card relative rounded-xl p-4 shadow-sm">
    <p className="pr-10 text-xs font-semibold uppercase tracking-wider opacity-60">
      {label}
    </p>
    <span className="absolute right-4 top-4">
      <MetricIcon type={icon} />
    </span>
    <p className="mt-2 text-2xl font-bold">{value}</p>
    {detail && <p className="mt-1 text-xs opacity-60">{detail}</p>}
    {trend && (
      <p
        className={`mt-1 text-xs ${trend.startsWith("▲") ? "text-green-500" : trend.startsWith("▼") ? "text-red-500" : "opacity-60"}`}
      >
        {trend} vs previous period
      </p>
    )}
  </article>
);

const MetricGroup = ({ title, global = false, children }) => (
  <section className="ua-stats-panel rounded-xl p-3 shadow-sm">
    <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider opacity-65">
      {title}
      {global && (
        <span className="rounded-full border px-2 py-0.5 normal-case tracking-normal">
          Global
        </span>
      )}
    </h2>
    <div className="grid gap-3 sm:grid-cols-2">{children}</div>
  </section>
);

function StatsActionsMenu({ exportsDisabled, onCsv, onJson, onReset }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const closeWhenOutside = (event) => {
      if (!menuRef.current?.contains(event.target)) setOpen(false);
    };
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", closeWhenOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeWhenOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const choose = (callback) => {
    setOpen(false);
    callback();
  };
  return (
    <div ref={menuRef} className="ua-stats-actions relative flex">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="ua-stats-actions-trigger flex h-11 w-11 items-center justify-center rounded-xl text-xl font-medium"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Statistics actions"
        title="Statistics actions"
      >
        <LucideIcon name="ellipsis" className="h-5 w-5" />
      </button>
      {open && (
        <div
          className="ua-stats-actions-menu absolute right-0 z-20 mt-2 min-w-48 overflow-hidden rounded-lg py-1 shadow-xl"
          role="menu"
          aria-label="Statistics actions"
        >
          <button
            type="button"
            disabled={exportsDisabled}
            className="block w-full px-3 py-2 text-left text-sm disabled:cursor-not-allowed disabled:opacity-40"
            role="menuitem"
            onClick={() => choose(onCsv)}
          >
            CSV timeline
          </button>
          <button
            type="button"
            disabled={exportsDisabled}
            className="block w-full px-3 py-2 text-left text-sm disabled:cursor-not-allowed disabled:opacity-40"
            role="menuitem"
            onClick={() => choose(onJson)}
          >
            JSON details
          </button>
          <button
            type="button"
            className="ua-stats-actions-danger mt-1 block w-full border-t px-3 py-2 text-left text-sm"
            role="menuitem"
            onClick={() => choose(onReset)}
          >
            Reset statistics
          </button>
        </div>
      )}
    </div>
  );
}

function TrendChart({
  rows,
  trackerActive = false,
  dateFormat = "YYYY-MM-DD",
  gradient = false,
}) {
  const [view, setView] = useState(() => {
    const stored = window.UAStorage.get(TREND_VIEW_KEY);
    return ["count", "volume", "both"].includes(stored) ? stored : "count";
  });
  const [visible, setVisible] = useState({
    items: true,
    uploads: true,
    upload_errors: true,
    api: false,
    processed_bytes: true,
    uploaded_bytes: true,
  });
  const [hovered, setHovered] = useState(null);
  const width = 760,
    height = 220;
  const plot = { top: 12, right: 56, bottom: 44, left: 56 };
  const plotWidth = width - plot.left - plot.right;
  const plotHeight = height - plot.top - plot.bottom;
  const series = [
    { key: "items", label: "Items", color: "#8b5cf6", kind: "count" },
    { key: "uploads", label: "Uploads", color: "#22c55e", kind: "count" },
    {
      key: "upload_errors",
      label: "Upload errors",
      color: "#ef4444",
      kind: "count",
    },
    {
      key: "api",
      label: trackerActive ? "API operations (global)" : "API operations",
      color: "#f59e0b",
      kind: "count",
    },
    {
      key: "processed_bytes",
      label: "Processed volume",
      color: "#06b6d4",
      kind: "volume",
    },
    {
      key: "uploaded_bytes",
      label: "Uploaded volume",
      color: "#14b8a6",
      kind: "volume",
    },
  ];
  const viewSeries = series.filter(
    (entry) => view === "both" || entry.kind === view,
  );
  const activeSeries = viewSeries.filter((entry) => visible[entry.key]);
  const countMaximum = Math.max(
    1,
    ...rows.flatMap((row) =>
      activeSeries
        .filter((entry) => entry.kind === "count")
        .map((entry) => row[entry.key] || 0),
    ),
  );
  const byteMaximum = Math.max(
    1,
    ...rows.flatMap((row) =>
      activeSeries
        .filter((entry) => entry.kind === "volume")
        .map((entry) => row[entry.key] || 0),
    ),
  );
  const xFor = (index) =>
    rows.length <= 1
      ? width / 2
      : plot.left + (index * plotWidth) / (rows.length - 1);
  const scaleMaximum = view === "volume" ? byteMaximum : countMaximum;
  const yForValue = (value, kind = "count") =>
    plot.top +
    (1 - value / (kind === "volume" ? byteMaximum : countMaximum)) * plotHeight;
  const yFor = (entry, row) => yForValue(row[entry.key] || 0, entry.kind);
  const yStepCount = Math.min(4, scaleMaximum);
  const yTicks = Array.from(
    new Set(
      Array.from({ length: yStepCount + 1 }, (_, index) =>
        Math.round((scaleMaximum * index) / yStepCount),
      ),
    ),
  );
  const byteTicks = Array.from({ length: 5 }, (_, index) =>
    Math.round((byteMaximum * index) / 4),
  );
  const xTickCount = Math.min(7, rows.length);
  const xTickIndices = Array.from(
    new Set(
      Array.from({ length: xTickCount }, (_, index) =>
        xTickCount === 1
          ? 0
          : Math.round((index * (rows.length - 1)) / (xTickCount - 1)),
      ),
    ),
  );
  const formatAxisDate = (date) =>
    formatStatsDate(date, dateFormat, !(rows.length > 365));
  const curvePath = (entry) => {
    const coordinates = rows.map((row, index) => ({
      x: xFor(index),
      y: yFor(entry, row),
    }));
    if (!coordinates.length) return "";
    return coordinates.slice(1).reduce((path, current, index) => {
      const previous = coordinates[index];
      const controlX = (previous.x + current.x) / 2;
      return `${path} C ${controlX},${previous.y} ${controlX},${current.y} ${current.x},${current.y}`;
    }, `M ${coordinates[0].x},${coordinates[0].y}`);
  };
  const areaPath = (entry) => {
    const line = curvePath(entry);
    if (!line) return "";
    const baseline = height - plot.bottom;
    return `${line} L ${xFor(rows.length - 1)},${baseline} L ${xFor(0)},${baseline} Z`;
  };
  if (!rows.length)
    return (
      <p className="py-12 text-center text-sm opacity-60">
        No activity in this period.
      </p>
    );
  return (
    <div>
      <div className="relative overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="min-w-[620px]"
          role="img"
          aria-label="Daily activity trend"
          onMouseLeave={() => setHovered(null)}
        >
          {gradient && (
            <defs>
              {activeSeries.map((entry) => (
                <linearGradient
                  key={entry.key}
                  id={`daily-activity-gradient-${entry.key}`}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor={entry.color}
                    stopOpacity="0.34"
                  />
                  <stop
                    offset="100%"
                    stopColor={entry.color}
                    stopOpacity="0.03"
                  />
                </linearGradient>
              ))}
            </defs>
          )}
          {gradient &&
            activeSeries.map((entry) => (
              <path
                key={`${entry.key}-gradient`}
                d={areaPath(entry)}
                fill={`url(#daily-activity-gradient-${entry.key})`}
                stroke="none"
              />
            ))}
          {yTicks.map((value) => (
            <React.Fragment key={value}>
              <line
                x1={plot.left}
                x2={width - plot.right}
                y1={yForValue(value, view === "volume" ? "volume" : "count")}
                y2={yForValue(value, view === "volume" ? "volume" : "count")}
                stroke="currentColor"
                opacity="0.12"
              />
              <text
                x={plot.left - 8}
                y={yForValue(value, view === "volume" ? "volume" : "count")}
                fill="currentColor"
                fontSize="10"
                textAnchor="end"
                dominantBaseline="middle"
                opacity="0.65"
              >
                {view === "volume"
                  ? formatBytes(value)
                  : formatCompactNumber(value)}
              </text>
            </React.Fragment>
          ))}
          {view === "both" &&
            byteTicks.map((value) => (
              <text
                key={`bytes-${value}`}
                x={width - plot.right + 8}
                y={yForValue(value, "volume")}
                fill="currentColor"
                fontSize="10"
                textAnchor="start"
                dominantBaseline="middle"
                opacity="0.65"
              >
                {formatBytes(value)}
              </text>
            ))}
          <line
            x1={plot.left}
            x2={plot.left}
            y1={plot.top}
            y2={height - plot.bottom}
            stroke="currentColor"
            opacity="0.28"
          />
          <line
            x1={plot.left}
            x2={width - plot.right}
            y1={height - plot.bottom}
            y2={height - plot.bottom}
            stroke="currentColor"
            opacity="0.28"
          />
          {xTickIndices.map((index) => (
            <text
              key={rows[index].date}
              x={xFor(index)}
              y={height - 24}
              fill="currentColor"
              fontSize="10"
              textAnchor={
                index === 0
                  ? "start"
                  : index === rows.length - 1
                    ? "end"
                    : "middle"
              }
              opacity="0.65"
            >
              {formatAxisDate(rows[index].date)}
            </text>
          ))}
          {activeSeries.map((entry) => (
            <path
              key={entry.key}
              d={curvePath(entry)}
              fill="none"
              stroke={entry.color}
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {hovered !== null && (
            <line
              x1={xFor(hovered)}
              x2={xFor(hovered)}
              y1={plot.top}
              y2={height - plot.bottom}
              stroke="currentColor"
              opacity="0.35"
            />
          )}
          {rows.map((row, index) => {
            const segmentWidth = plotWidth / Math.max(1, rows.length - 1);
            return (
              <rect
                key={row.date}
                x={Math.max(plot.left, xFor(index) - segmentWidth / 2)}
                y={plot.top}
                width={segmentWidth}
                height={plotHeight}
                fill="transparent"
                onMouseEnter={() => setHovered(index)}
              />
            );
          })}
        </svg>
        {hovered !== null && rows[hovered] && (
          <div
            className="ua-stats-chart-tooltip pointer-events-none absolute top-2 z-10 min-w-44 -translate-x-1/2 rounded-lg p-3 text-xs shadow-xl"
            style={{
              left: `${Math.min(86, Math.max(14, (xFor(hovered) / width) * 100))}%`,
            }}
          >
            <p className="font-semibold">
              {formatStatsDate(rows[hovered].date, dateFormat)}
            </p>
            <p className="mt-1">{formatNumber(rows[hovered].items)} items</p>
            <p>{formatNumber(rows[hovered].uploads)} uploads</p>
            <p>{formatNumber(rows[hovered].upload_errors)} upload errors</p>
            <p>{formatBytes(rows[hovered].uploaded_bytes)} uploaded</p>
            <p>{formatBytes(rows[hovered].processed_bytes)} processed</p>
            <p>{formatNumber(rows[hovered].api)} API operations</p>
          </div>
        )}
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-2 text-xs">
        {["count", "volume", "both"].map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={view === value}
            className={`rounded-lg px-3 py-1.5 ${view === value ? "ua-stats-series-active" : "opacity-55"}`}
            onClick={() => {
              setView(value);
              window.UAStorage.set(TREND_VIEW_KEY, value);
            }}
          >
            {value === "count"
              ? "Count"
              : value === "volume"
                ? "Volume"
                : "Both"}
          </button>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-2 text-xs">
        {viewSeries.map((entry) => (
          <button
            key={entry.key}
            type="button"
            aria-pressed={visible[entry.key]}
            className={`rounded-full px-3 py-1.5 transition ${visible[entry.key] ? "ua-stats-series-active" : "opacity-45"}`}
            onClick={() =>
              setVisible((current) => ({
                ...current,
                [entry.key]: !current[entry.key],
              }))
            }
          >
            <span style={{ color: entry.color }}>●</span> {entry.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ActivityHeatmap({
  rows,
  today: todayValue,
  dateFormat = "YYYY-MM-DD",
}) {
  const byDate = new Map((rows || []).map((row) => [row.date, row.count]));
  const today = new Date(`${todayValue || isoTodayUtc()}T00:00:00Z`);
  today.setUTCHours(0, 0, 0, 0);
  const start = new Date(today);
  start.setUTCDate(today.getUTCDate() - 363);
  const cells = [];
  for (let offset = 0; offset < 364; offset += 1) {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + offset);
    const key = date.toISOString().slice(0, 10);
    cells.push({ date: key, count: byDate.get(key) || 0 });
  }
  const maximum = Math.max(1, ...cells.map((cell) => cell.count));
  let currentStreak = 0;
  let longestStreak = 0;
  cells.forEach((cell) => {
    currentStreak = cell.count > 0 ? currentStreak + 1 : 0;
    longestStreak = Math.max(longestStreak, currentStreak);
  });
  const monthMarkers = [];
  let previousMonth = "";
  cells.forEach((cell, index) => {
    const date = new Date(`${cell.date}T00:00:00Z`);
    const month = cell.date.slice(0, 7);
    if (month !== previousMonth) {
      monthMarkers.push({
        key: month,
        label: date.toLocaleString("en-US", {
          month: "short",
          timeZone: "UTC",
        }),
        column: Math.floor(index / 7) + 1,
      });
      previousMonth = month;
    }
  });
  const visibleMonthMarkers =
    monthMarkers.length > 1 &&
    monthMarkers[1].column - monthMarkers[0].column <= 1
      ? monthMarkers.slice(1)
      : monthMarkers;
  const weekdayLabels = [
    { label: "Sun", weekday: 0 },
    { label: "Mon", weekday: 1 },
    { label: "Tue", weekday: 2 },
    { label: "Wed", weekday: 3 },
    { label: "Thu", weekday: 4 },
    { label: "Fri", weekday: 5 },
    { label: "Sat", weekday: 6 },
  ].map((entry) => ({
    ...entry,
    row: ((entry.weekday - start.getUTCDay() + 7) % 7) + 1,
  }));
  const columnStyle = {
    gridTemplateColumns: "repeat(52, minmax(0, 1fr))",
  };
  return (
    <div className="ua-stats-heatmap w-full pb-1">
      <div className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-2 gap-y-1">
        <span aria-hidden="true" />
        <div
          className="grid min-h-4 gap-[2px] text-[0.65rem] opacity-60 sm:gap-1 sm:text-xs"
          style={columnStyle}
          aria-hidden="true"
        >
          {visibleMonthMarkers.map((marker, index) => (
            <span
              key={marker.key}
              className={`whitespace-nowrap ${index % 2 ? "hidden sm:block" : ""}`}
              style={{ gridColumnStart: marker.column, gridRowStart: 1 }}
            >
              {marker.label}
            </span>
          ))}
        </div>
        <div
          className="grid grid-rows-7 gap-[2px] text-xs opacity-60 sm:gap-1"
          aria-hidden="true"
        >
          {weekdayLabels.map((entry) => (
            <span
              key={entry.label}
              className="self-center"
              style={{ gridRowStart: entry.row }}
            >
              {entry.label}
            </span>
          ))}
        </div>
        <div
          className="grid w-full grid-flow-col grid-rows-7 gap-[2px] sm:gap-1"
          style={columnStyle}
          role="img"
          aria-label="Activity during the last 52 weeks"
        >
          {cells.map((cell) => (
            <span
              key={cell.date}
              className="aspect-square rounded-[3px]"
              style={{
                background: cell.count
                  ? `color-mix(in srgb, var(--ua-copper-bright) ${25 + Math.round((cell.count / maximum) * 70)}%, var(--ua-stats-heatmap-empty))`
                  : "var(--ua-stats-heatmap-empty)",
              }}
              title={`${formatStatsDate(cell.date, dateFormat)}: ${formatNumber(cell.count)} completed`}
            />
          ))}
        </div>
        <span aria-hidden="true" />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
          <span>
            Longest streak: {formatNumber(longestStreak)}{" "}
            {longestStreak === 1 ? "day" : "days"}
          </span>
          <div className="flex items-center gap-1 opacity-60">
            <span>Less</span>
            {[0, 25, 45, 65, 85].map((intensity) => (
              <span
                key={intensity}
                className="h-3 w-3 rounded-[3px]"
                style={{
                  background: intensity
                    ? `color-mix(in srgb, var(--ua-copper-bright) ${intensity}%, var(--ua-stats-heatmap-empty))`
                    : "var(--ua-stats-heatmap-empty)",
                }}
                aria-hidden="true"
              />
            ))}
            <span>More</span>
          </div>
        </div>
      </div>
    </div>
  );
}

const ReliabilityBadge = ({ rate, attempts }) => {
  if (!attempts) return <span className="opacity-60">No attempts</span>;
  const [label, className] =
    rate >= 98
      ? ["Healthy", "ua-stats-health-good"]
      : rate >= 90
        ? ["Watch", "ua-stats-health-watch"]
        : ["Unreliable", "ua-stats-health-poor"];
  return (
    <span
      className={`ua-stats-health rounded-full px-2 py-1 text-xs ${className}`}
    >
      {label}
    </span>
  );
};

function SankeyDiagram({ sankey }) {
  const nodes = sankey?.nodes || [];
  const links = sankey?.links || [];
  const root = nodes.find((node) => node.kind === "root");
  const trackers = nodes.filter((node) => node.kind === "tracker");
  const outcomes = nodes.filter((node) => node.kind === "outcome");
  if (!root || !links.length)
    return (
      <p className="py-8 text-center text-sm opacity-60">
        No upload routes in this period.
      </p>
    );
  const height = Math.max(240, trackers.length * 52 + 40);
  const trackerY = new Map(
    trackers.map((node, index) => [
      node.id,
      ((index + 1) * height) / (trackers.length + 1),
    ]),
  );
  const outcomeY = new Map(
    outcomes.map((node, index) => [
      node.id,
      ((index + 1) * height) / (outcomes.length + 1),
    ]),
  );
  const maximum = Math.max(1, ...links.map((link) => link.value));
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const pointFor = (id) => {
    if (id === "routes") return { x: 92, y: height / 2 };
    if (id.startsWith("tracker:")) return { x: 380, y: trackerY.get(id) };
    return { x: 680, y: outcomeY.get(id) };
  };
  return (
    <div>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 760 ${height}`}
          className="min-w-[700px]"
          role="img"
          aria-label="Upload route Sankey diagram"
        >
          {links.map((link, index) => {
            const source = pointFor(link.source);
            const target = pointFor(link.target);
            const bend = (source.x + target.x) / 2;
            return (
              <path
                key={`${link.source}:${link.target}:${index}`}
                d={`M ${source.x},${source.y} C ${bend},${source.y} ${bend},${target.y} ${target.x},${target.y}`}
                fill="none"
                stroke={link.source === "routes" ? "#8b5cf6" : "#22c55e"}
                strokeOpacity="0.35"
                strokeWidth={Math.max(2, (link.value / maximum) * 28)}
              >
                <title>{`${nodeById.get(link.source)?.label} → ${nodeById.get(link.target)?.label}: ${formatNumber(link.value)}`}</title>
              </path>
            );
          })}
          {nodes.map((node) => {
            const point = pointFor(node.id);
            return (
              <g key={node.id} transform={`translate(${point.x}, ${point.y})`}>
                <rect
                  x="-72"
                  y="-16"
                  width="144"
                  height="32"
                  rx="8"
                  fill="var(--ua-config-surface-raised)"
                  stroke="currentColor"
                  strokeOpacity="0.2"
                />
                <text
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="currentColor"
                  fontSize="11"
                >
                  {node.label} · {formatNumber(node.total)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <details className="ua-stats-table-details mt-4">
        <summary className="cursor-pointer text-sm font-medium">
          Accessible route table
        </summary>
        <Table
          rows={links.map((link, index) => ({
            key: `${link.source}:${link.target}:${index}`,
            source: nodeById.get(link.source)?.label,
            target: nodeById.get(link.target)?.label,
            value: link.value,
          }))}
          headers={[
            { label: "From", key: "source" },
            { label: "To", key: "target" },
            { label: "Routes", key: "value" },
          ]}
        />
      </details>
    </div>
  );
}

function MediaProfile({ media, category, onCategoryChange }) {
  const rows = (media?.dimensions || []).filter(
    (row) => row.category === category && row.dimension !== "streaming_service",
  );
  const groups = rows.reduce((result, row) => {
    (result[row.dimension] ||= []).push(row);
    return result;
  }, {});
  if (!media?.categories?.length)
    return (
      <p className="py-5 text-center text-sm opacity-60">
        No media profile data in this period.
      </p>
    );
  return (
    <div>
      <label className="mb-4 flex items-center gap-2 text-sm">
        <span className="opacity-60">Category</span>
        <select
          value={category}
          onChange={(event) => onCategoryChange(event.target.value)}
          className="ua-theme-picker rounded-lg px-3 py-2 text-sm"
        >
          {media.categories.map((name) => (
            <option key={name} value={name}>
              {formatDimensionValue(name)}
            </option>
          ))}
        </select>
      </label>
      <ChartWithTable
        chart={
          <div className="grid gap-4 xl:grid-cols-2">
            {Object.entries(groups).map(([dimension, values]) => (
              <div className="ua-stats-inset rounded-xl p-4" key={dimension}>
                <h3 className="mb-3 text-sm font-semibold capitalize">
                  {formatDimensionValue(dimension)}
                </h3>
                <DonutChart
                  ariaLabel={`${formatDimensionValue(dimension)} distribution`}
                  rows={values.map((row) => ({
                    label: formatDimensionValue(row.value),
                    value: row.count,
                  }))}
                />
              </div>
            ))}
          </div>
        }
        table={
          <Table
            rows={rows.map((row) => ({
              ...row,
              key: `${row.dimension}:${row.value}`,
            }))}
            headers={[
              {
                label: "Dimension",
                sortValue: (row) => row.dimension,
                render: (row) => formatDimensionValue(row.dimension),
              },
              {
                label: "Value",
                sortValue: (row) => row.value,
                render: (row) => formatDimensionValue(row.value),
              },
              { label: "Items", key: "count" },
              {
                label: "Volume",
                sortValue: (row) => row.bytes,
                render: (row) => formatBytes(row.bytes),
              },
            ]}
          />
        }
      />
      <MediaMatrix rows={media.matrix || []} category={category} />
    </div>
  );
}

function MediaMatrix({ rows, category }) {
  const filtered = rows.filter((row) => row.category === category);
  if (!filtered.length) return null;
  const resolutions = [...new Set(filtered.map((row) => row.resolution))];
  const profiles = [...new Set(filtered.map((row) => row.profile))];
  const maximum = Math.max(...filtered.map((row) => row.count), 1);
  const byCell = new Map(
    filtered.map((row) => [`${row.resolution}\u0000${row.profile}`, row]),
  );
  return (
    <div className="mt-5">
      <h3 className="mb-2 text-sm font-semibold">
        Resolution × video/HDR profile
      </h3>
      <div className="ua-stats-table-scroll overflow-x-auto">
        <table className="ua-stats-table w-full text-left text-xs">
          <thead>
            <tr>
              <th className="px-2 py-2">Resolution</th>
              {profiles.map((profile) => (
                <th className="min-w-32 px-2 py-2" key={profile}>
                  {formatDimensionValue(profile)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {resolutions.map((resolution) => (
              <tr key={resolution}>
                <th className="px-2 py-2">{resolution}</th>
                {profiles.map((profile) => {
                  const cell = byCell.get(`${resolution}\u0000${profile}`);
                  const opacity = cell
                    ? 0.15 + (cell.count / maximum) * 0.75
                    : 0;
                  return (
                    <td
                      key={profile}
                      className="px-2 py-3 text-center tabular-nums"
                      style={{
                        backgroundColor: `rgba(59, 130, 246, ${opacity})`,
                      }}
                      title={
                        cell
                          ? `${formatNumber(cell.count)} items · ${formatBytes(cell.bytes)}`
                          : "No items"
                      }
                    >
                      {cell ? formatNumber(cell.count) : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StreamingServices({ services }) {
  const rows = services || [];
  return (
    <ChartWithTable
      chart={
        <DonutChart
          ariaLabel="Processed items by streaming service"
          rows={rows.map((row) => ({
            label: formatDimensionValue(row.service),
            value: row.items,
          }))}
        />
      }
      table={
        <Table
          rows={rows}
          headers={[
            {
              label: "Service",
              sortValue: (row) => row.service,
              render: (row) => formatDimensionValue(row.service),
            },
            { label: "Items", key: "items" },
            {
              label: "Unique volume",
              sortValue: (row) => row.bytes,
              render: (row) => formatBytes(row.bytes),
            },
            {
              label: "Average size",
              sortValue: (row) => row.average_item_bytes,
              render: (row) => formatBytes(row.average_item_bytes),
            },
          ]}
        />
      }
    />
  );
}

function ReleaseProfiles({ releaseProfiles }) {
  const profiles = releaseProfiles?.profiles || [];
  const personal = profiles.find((row) => row.profile === "personal");
  const personalCategories = (releaseProfiles?.by_category || []).filter(
    (row) => row.profile === "personal",
  );
  const tableRows = personal
    ? [
        { ...personal, category: "All categories", key: "personal:all" },
        ...personalCategories.map((row) => ({
          ...row,
          key: `personal:${row.category}`,
        })),
      ]
    : [];
  return (
    <ChartWithTable
      chart={
        <DonutChart
          ariaLabel="Personal and standard releases"
          rows={profiles.map((row) => ({
            label: row.profile === "personal" ? "Personal" : "Standard",
            value: row.items,
          }))}
        />
      }
      table={
        <Table
          rows={tableRows}
          empty="No personal releases in this period."
          headers={[
            { label: "Category", key: "category" },
            { label: "Items", key: "items" },
            { label: "With upload", key: "successes" },
            { label: "Without upload", key: "without_upload" },
            { label: "Errors", key: "errors" },
            {
              label: "Success rate",
              sortValue: (row) => row.success_rate,
              render: (row) => `${row.success_rate}%`,
            },
            {
              label: "Unique volume",
              sortValue: (row) => row.bytes,
              render: (row) => formatBytes(row.bytes),
            },
          ]}
        />
      }
    />
  );
}

function DonutChart({
  rows,
  ariaLabel,
  onSelect,
  activeLabel = "",
  showFavicons = true,
  valueFormatter = formatNumber,
  centerLabel = "Total",
}) {
  const normalizedRows = rows
    .map((row) => ({
      label: String(row.label || "Unknown"),
      value: Math.max(0, Number(row.value) || 0),
      favicon: row.favicon || "",
      id: row.id || "",
    }))
    .filter((row) => row.value > 0)
    .sort((left, right) => right.value - left.value);
  const visibleRows = normalizedRows.slice(0, 7);
  const otherValue = normalizedRows
    .slice(7)
    .reduce((total, row) => total + row.value, 0);
  if (otherValue) visibleRows.push({ label: "Other", value: otherValue });
  const total = visibleRows.reduce((sum, row) => sum + row.value, 0);
  if (!total)
    return (
      <p className="py-8 text-center text-sm opacity-60">
        No data in this period.
      </p>
    );

  let offset = 0;
  const segments = visibleRows.map((row, index) => {
    const percentage = (row.value / total) * 100;
    const segment = { ...row, color: CHART_COLORS[index], offset, percentage };
    offset += percentage;
    return segment;
  });

  return (
    <div className="grid items-center gap-5 sm:grid-cols-[minmax(180px,240px)_1fr]">
      <div className="relative mx-auto aspect-square w-full max-w-[240px]">
        <svg viewBox="0 0 42 42" role="img" aria-label={ariaLabel}>
          <title>{ariaLabel}</title>
          <circle
            cx="21"
            cy="21"
            r="15.9155"
            fill="none"
            stroke="currentColor"
            strokeWidth="6"
            opacity="0.1"
          />
          {segments.map((segment) => (
            <circle
              key={segment.label}
              cx="21"
              cy="21"
              r="15.9155"
              fill="none"
              stroke={segment.color}
              strokeWidth="6"
              strokeDasharray={`${segment.percentage} ${100 - segment.percentage}`}
              strokeDashoffset={-segment.offset}
              strokeLinecap="butt"
              transform="rotate(-90 21 21)"
              className={onSelect && segment.id ? "cursor-pointer" : ""}
              opacity={activeLabel && activeLabel !== segment.id ? "0.3" : "1"}
              onClick={() => segment.id && onSelect?.(segment.id)}
            />
          ))}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold">{valueFormatter(total)}</span>
          <span className="text-xs opacity-60">{centerLabel}</span>
        </div>
      </div>
      <ul className="grid gap-2 text-sm">
        {segments.map((segment) => (
          <li
            key={segment.label}
            className={`flex min-w-0 items-center justify-between gap-3 px-1 ${onSelect && segment.id ? "cursor-pointer" : ""} ${activeLabel && activeLabel === segment.id ? "font-semibold" : ""}`}
            role={onSelect && segment.id ? "button" : undefined}
            tabIndex={onSelect && segment.id ? 0 : undefined}
            onClick={() => segment.id && onSelect?.(segment.id)}
            onKeyDown={(event) => {
              if (onSelect && (event.key === "Enter" || event.key === " ")) {
                event.preventDefault();
                onSelect(segment.id);
              }
            }}
          >
            <span className="flex min-w-0 items-center gap-2">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: segment.color }}
                aria-hidden="true"
              />
              {showFavicons && segment.favicon && (
                <TrackerFavicon
                  destination={segment.favicon}
                  className="h-5 w-5"
                />
              )}
              <span className="truncate" title={segment.label}>
                {segment.label}
              </span>
            </span>
            <span className="shrink-0 tabular-nums">
              {valueFormatter(segment.value)} · {segment.percentage.toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const Section = ({ icon, title, subtitle, children }) => (
  <section className="ua-stats-panel rounded-xl p-4 shadow-sm sm:p-5">
    <div className="flex items-center gap-2.5">
      <StatsIcon name={icon} className="h-5 w-5 opacity-60" />
      <h2 className="text-base font-semibold">{title}</h2>
    </div>
    {subtitle && <p className="mt-1 text-sm opacity-60">{subtitle}</p>}
    <div className="mt-4">{children}</div>
  </section>
);

const ChartWithTable = ({ chart, table }) => (
  <>
    {chart}
    <details className="ua-stats-table-details mt-5">
      <summary
        className="ml-auto flex h-9 w-9 cursor-pointer list-none items-center justify-center rounded-lg"
        aria-label="Show or hide data table"
        title="Show or hide data table"
      >
        <span
          className="ua-stats-table-details-arrow transition-transform"
          aria-hidden="true"
        >
          ▾
        </span>
      </summary>
      <div className="mt-3">{table}</div>
    </details>
  </>
);

function Table({
  headers,
  rows,
  empty = "No data in this period.",
  onRowClick,
  activeKey = "",
}) {
  const [sort, setSort] = useState({ label: "", direction: "ascending" });
  const sortedRows = useMemo(() => {
    if (!sort.label) return rows;
    const header = headers.find((candidate) => candidate.label === sort.label);
    if (!header) return rows;
    const valueFor = (row) =>
      header.sortValue ? header.sortValue(row) : row[header.key];
    const direction = sort.direction === "ascending" ? 1 : -1;
    return [...rows].sort((leftRow, rightRow) => {
      const left = valueFor(leftRow);
      const right = valueFor(rightRow);
      if (left == null) return right == null ? 0 : 1;
      if (right == null) return -1;
      if (typeof left === "number" && typeof right === "number")
        return (left - right) * direction;
      return (
        String(left).localeCompare(String(right), undefined, {
          numeric: true,
          sensitivity: "base",
        }) * direction
      );
    });
  }, [headers, rows, sort]);

  if (!rows.length)
    return <p className="py-5 text-center text-sm opacity-60">{empty}</p>;
  return (
    <div className="ua-stats-table-scroll overflow-x-auto">
      <table className="ua-stats-table w-full text-left text-sm">
        <thead className="text-xs uppercase">
          <tr>
            {headers.map((header) => {
              const sortable = Boolean(header.key || header.sortValue);
              const active = sort.label === header.label;
              return (
                <th
                  className="px-2 py-2"
                  key={header.label}
                  aria-sort={active ? sort.direction : undefined}
                >
                  {sortable ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1.5 whitespace-nowrap text-left hover:opacity-100"
                      onClick={() =>
                        setSort({
                          label: header.label,
                          direction:
                            active && sort.direction === "ascending"
                              ? "descending"
                              : "ascending",
                        })
                      }
                    >
                      <span>{header.label}</span>
                      <span aria-hidden="true" className="text-[0.65rem]">
                        {active
                          ? sort.direction === "ascending"
                            ? "▲"
                            : "▼"
                          : "↕"}
                      </span>
                    </button>
                  ) : (
                    header.label
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, index) => (
            <tr
              key={row.key || index}
              className={`${onRowClick ? "cursor-pointer" : ""} ${activeKey && activeKey === row.key ? "ua-stats-series-active" : ""}`}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={() => onRowClick?.(row)}
              onKeyDown={(event) => {
                if (
                  onRowClick &&
                  (event.key === "Enter" || event.key === " ")
                ) {
                  event.preventDefault();
                  onRowClick(row);
                }
              }}
            >
              {headers.map((header) => (
                <td className="px-2 py-2.5" key={header.label}>
                  {header.render ? header.render(row) : row[header.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatsApp() {
  const [period, setPeriod] = useState(() => {
    const stored = window.UAStorage.get(STATS_PERIOD_KEY);
    return STATS_PERIODS.some(([value]) => value === stored) ? stored : "30d";
  });
  const [mode, setMode] = useState("real");
  const [settings, setSettings] = useState(loadStatsSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const initialToday = () =>
    settings.timezone === "browser" ? isoTodayLocal() : isoTodayUtc();
  const [customFrom, setCustomFrom] = useState(initialToday);
  const [customTo, setCustomTo] = useState(initialToday);
  const [customRange, setCustomRange] = useState(() => ({
    from: initialToday(),
    to: initialToday(),
  }));
  const [activeTracker, setActiveTracker] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [resetOpen, setResetOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [isDarkMode, setIsDarkMode] = useState(window.getUAStoredTheme);
  const [colorTheme, setColorTheme] = useState(window.getUAStoredColorTheme);
  const [interfaceStyle, setInterfaceStyle] = useState(
    window.getUAStoredInterfaceStyle,
  );
  const [helpOpen, setHelpOpen] = useState(false);
  const [changelogOpen, setChangelogOpen] = useState(false);
  const [mediaCategory, setMediaCategory] = useState("");

  useEffect(() => {
    window.UAStorage.set("ua_config_theme", isDarkMode ? "dark" : "light");
    document.documentElement.dataset.uaMode = isDarkMode ? "dark" : "light";
  }, [isDarkMode]);
  useEffect(() => {
    window.UAStorage.set(STATS_PERIOD_KEY, period);
  }, [period]);
  useEffect(() => {
    window.UAStorage.set(STATS_SETTINGS_KEY, JSON.stringify(settings));
  }, [settings]);

  const load = async (signal) => {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({
        range: period,
        mode,
        timezone: settings.timezone,
      });
      if (settings.timezone === "browser") query.set("today", isoTodayLocal());
      if (period === "custom") {
        query.set("from", customRange.from);
        query.set("to", customRange.to);
      }
      if (activeTracker) query.set("tracker", activeTracker);
      const response = await fetch(
        `${APP_BASE}/api/stats?${query.toString()}`,
        {
          headers: { "X-CSRF-Token": window.UA_CSRF_TOKEN },
          signal,
        },
      );
      const body = await response.json();
      if (!response.ok)
        throw new Error(body.error || "Unable to load statistics");
      setData(body);
    } catch (err) {
      if (err?.name === "AbortError") return;
      setError(err.message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [period, mode, customRange, activeTracker, settings.timezone]);
  useEffect(() => {
    const categories = data?.media?.categories || [];
    if (!categories.includes(mediaCategory))
      setMediaCategory(categories[0] || "");
  }, [data, mediaCategory]);

  const reset = async () => {
    try {
      const response = await fetch(`${APP_BASE}/api/stats`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": window.UA_CSRF_TOKEN,
        },
        body: JSON.stringify({ confirmation }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(body.error || "Unable to reset statistics");
        return;
      }
    } catch (_error) {
      setError("Unable to reset statistics");
      return;
    }
    setResetOpen(false);
    setConfirmation("");
    await load();
  };

  const overview = data?.overview || {};
  const activeTrackerRow = (data?.filters?.destinations || []).find(
    (row) => row.destination === activeTracker,
  );
  const toggleTracker = (destination) =>
    setActiveTracker((current) =>
      current === destination ? "" : destination || "",
    );
  const statsEnabled = data?.enabled !== false;
  const visible = settings.visibility;
  const localTimeLabel = `Local time · ${browserTimeZone()}`;
  const artifactMap = useMemo(
    () =>
      (data?.artifacts || []).reduce((totals, row) => {
        const key = `${row.type}:${row.operation}`;
        totals[key] = (totals[key] || 0) + row.count;
        return totals;
      }, {}),
    [data],
  );
  const screenshotArtifactMap = useMemo(
    () =>
      (data?.artifacts || []).reduce((totals, row) => {
        if (row.type === "screenshot" && row.operation === "created")
          totals[row.variant] = (totals[row.variant] || 0) + row.count;
        return totals;
      }, {}),
    [data],
  );
  const hasData =
    data &&
    (overview.items_completed ||
      overview.upload_attempts ||
      overview.api_operations ||
      data.cache.hits ||
      data.cache.misses ||
      data.artifacts.length);
  const exportJson = () =>
    downloadText(
      `upload-assistant-stats-${period}-${mode}${activeTracker ? `-${activeTracker}` : ""}.json`,
      JSON.stringify(data, null, 2),
      "application/json",
    );
  const exportCsv = () => {
    const columns = [
      "date",
      "items",
      "uploads",
      "upload_errors",
      "uploaded_bytes",
      "processed_bytes",
      "api",
      "cache_hit",
      "cache_miss",
    ];
    const lines = [
      columns.join(","),
      ...(data?.timeline || []).map((row) =>
        columns.map((column) => csvCell(row[column])).join(","),
      ),
    ];
    downloadText(
      `upload-assistant-stats-${period}-${mode}${activeTracker ? `-${activeTracker}` : ""}.csv`,
      lines.join("\n"),
      "text/csv;charset=utf-8",
    );
  };
  return (
    <div
      className={`ua-config-page min-h-screen md:pl-20 ${isDarkMode ? "ua-mode-dark" : "ua-mode-light"}`}
    >
      {helpOpen && <HelpResourcesModal onClose={() => setHelpOpen(false)} />}
      {settingsOpen && (
        <StatsSettingsModal
          mode={mode}
          onModeChange={setMode}
          settings={settings}
          onChange={setSettings}
          onClose={() => setSettingsOpen(false)}
          localTimeLabel={localTimeLabel}
        />
      )}
      {changelogOpen && (
        <window.UAChangelogModal onClose={() => setChangelogOpen(false)} />
      )}
      <WorkspaceNav
        colorTheme={colorTheme}
        interfaceStyle={interfaceStyle}
        isDarkMode={isDarkMode}
        onColorThemeChange={(value) =>
          setColorTheme(window.setUAColorTheme(value))
        }
        onInterfaceStyleChange={(value) =>
          setInterfaceStyle(window.setUAInterfaceStyle(value))
        }
        onOpenChangelog={() => setChangelogOpen(true)}
        onOpenHelp={() => setHelpOpen(true)}
        onToggleMode={() => setIsDarkMode((current) => !current)}
        onLogout={async () => {
          try {
            const response = await window.uaApiFetch(`${APP_BASE}/logout`, {
              method: "POST",
            });
            window.location = response.redirected
              ? response.url
              : `${APP_BASE}/login`;
          } catch (_error) {
            window.location = `${APP_BASE}/login`;
          }
        }}
      />
      <main className="mx-auto max-w-[1680px] p-4 sm:p-6 lg:p-8">
        <header className="ua-stats-header flex flex-col gap-5 border-b pb-6 xl:flex-row xl:items-center xl:justify-between">
          <div className="ua-stats-heading shrink-0">
            <p className="text-xs font-semibold uppercase tracking-widest opacity-60">
              Upload Assistant
            </p>
            <h1 className="mt-1 text-2xl font-bold">Statistics</h1>
            <p className="mt-1 text-sm opacity-60">Local daily aggregates.</p>
          </div>
          <div className="ua-stats-toolbar flex flex-wrap items-stretch gap-2">
            <div
              className="ua-stats-period-group flex flex-wrap items-center rounded-xl p-1"
              role="group"
              aria-label="Statistics period"
            >
              {STATS_PERIODS.map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setPeriod(value)}
                  aria-pressed={period === value}
                  className={`ua-stats-period-button rounded-lg px-3 text-sm transition-colors ${
                    period === value
                      ? "ua-stats-period-button-active font-semibold shadow-sm"
                      : "opacity-65 hover:opacity-100"
                  }`}
                >
                  {label}
                </button>
              ))}
              <details className="ua-stats-custom-dates relative">
                <summary
                  className={`ua-stats-custom-summary flex h-full cursor-pointer list-none items-center gap-2 rounded-lg px-3 text-sm ${period === "custom" ? "ua-stats-period-button-active font-semibold shadow-sm" : ""}`}
                >
                  <LucideIcon name="calendar-days" className="h-4 w-4" />
                  Custom dates
                </summary>
                <div className="ua-stats-chart-tooltip absolute right-0 z-20 mt-3 grid min-w-64 gap-3 rounded-lg p-3 shadow-xl">
                  <label className="grid gap-1 text-xs">
                    <span>From ({data?.period?.timezone || "UTC"})</span>
                    <input
                      type="date"
                      value={customFrom}
                      max={customTo}
                      onChange={(event) => setCustomFrom(event.target.value)}
                      className="ua-theme-picker rounded-lg px-3 py-2"
                    />
                  </label>
                  <label className="grid gap-1 text-xs">
                    <span>To ({data?.period?.timezone || "UTC"})</span>
                    <input
                      type="date"
                      value={customTo}
                      min={customFrom}
                      max={data?.time_context?.today || initialToday()}
                      onChange={(event) => setCustomTo(event.target.value)}
                      className="ua-theme-picker rounded-lg px-3 py-2"
                    />
                  </label>
                  <button
                    type="button"
                    className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white"
                    onClick={() => {
                      setCustomRange({ from: customFrom, to: customTo });
                      setPeriod("custom");
                    }}
                  >
                    Apply range
                  </button>
                </div>
              </details>
            </div>
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="ua-stats-settings-trigger flex min-h-11 items-center gap-2 rounded-xl px-4 text-sm font-medium"
              aria-haspopup="dialog"
            >
              <StatsIcon name="settings" className="h-4 w-4" />
              Display
            </button>
            <StatsActionsMenu
              exportsDisabled={!statsEnabled || !hasData}
              onCsv={exportCsv}
              onJson={exportJson}
              onReset={() => setResetOpen(true)}
            />
          </div>
        </header>
        <div className="mt-5 flex flex-wrap items-center gap-2 text-xs">
          <span className="ua-stats-range-chip inline-flex items-center rounded-full px-4 py-2">
            {data?.period?.timezone || "UTC"}:{" "}
            {data?.period?.from
              ? formatStatsDate(data.period.from, settings.dateFormat)
              : "first event"}{" "}
            → {formatStatsDate(data?.period?.to, settings.dateFormat)}
          </span>
          {activeTracker && (
            <button
              type="button"
              className="ua-stats-series-active inline-flex items-center gap-1 rounded-full px-3 py-1"
              onClick={() => setActiveTracker("")}
              aria-label="Clear tracker filter"
            >
              <span>{activeTrackerRow?.display_name || activeTracker}</span>
              <LucideIcon name="x" className="h-3 w-3" />
            </button>
          )}
        </div>
        {error && (
          <div
            role="alert"
            className="mt-5 rounded-lg border border-red-500 p-3 text-sm text-red-500"
          >
            {error}
          </div>
        )}
        {loading && (
          <p className="py-16 text-center opacity-60">Loading statistics…</p>
        )}
        {!loading && data && (
          <div className="relative mt-6">
            <div
              className={`space-y-5 transition duration-200 ${
                statsEnabled
                  ? ""
                  : "pointer-events-none select-none opacity-35 blur-[3px]"
              }`}
              aria-hidden={!statsEnabled}
            >
              {statsEnabled && !hasData && (
                <div className="ua-stats-panel rounded-xl p-8 text-center shadow-sm">
                  <h2 className="font-semibold">No statistics recorded yet</h2>
                  <p className="mt-2 text-sm opacity-60">
                    Counters start after this feature is installed. Existing
                    caches and logs are not backfilled.
                  </p>
                </div>
              )}
              <div className="grid gap-4 xl:grid-cols-2">
                {visible.throughput && (
                  <MetricGroup title="Throughput & scale">
                    {visible.itemsCompleted && (
                      <Card
                        icon="items-completed"
                        label="Items completed"
                        value={formatNumber(overview.items_completed)}
                        detail={`${formatNumber(data.items.success)} with upload · ${formatNumber(data.items.no_upload)} without upload · ${formatNumber(data.items.error)} errors`}
                        trend={formatTrend(
                          data.comparison?.items_completed_pct,
                        )}
                      />
                    )}
                    {visible.successfulUploads && (
                      <Card
                        icon="successful-uploads"
                        label="Successful uploads"
                        value={formatNumber(overview.uploads)}
                        detail={`${overview.upload_success_rate || 0}% of ${formatNumber(overview.upload_attempts)} attempts`}
                        trend={formatTrend(data.comparison?.uploads_pct)}
                      />
                    )}
                    {visible.dataUploaded && (
                      <Card
                        icon="data-uploaded"
                        label="Data uploaded"
                        value={formatBytes(overview.uploaded_bytes)}
                        detail="Successful destination uploads"
                      />
                    )}
                    {visible.uniqueDataUploaded && (
                      <Card
                        icon="unique-data-uploaded"
                        label="Unique data uploaded"
                        value={formatBytes(overview.unique_uploaded_bytes)}
                        detail="Each successful item counted once"
                      />
                    )}
                  </MetricGroup>
                )}
                {visible.efficiency && (
                  <MetricGroup title="Efficiency & intelligence">
                    {visible.duplicatesPrevented && (
                      <Card
                        icon="duplicates-prevented"
                        label="Duplicates prevented"
                        value={formatNumber(overview.duplicate_preventions)}
                        detail="Routes stopped before upload"
                      />
                    )}
                    {visible.pioneeringRate && (
                      <Card
                        icon="pioneering-rate"
                        label="Pioneering rate"
                        value={`${overview.pioneering_rate || 0}%`}
                        detail="Uploads ÷ uploads plus duplicates"
                      />
                    )}
                    {visible.hashingAvoided && (
                      <Card
                        icon="hashing-io-avoided"
                        label="Hashing I/O avoided"
                        value={formatBytes(overview.hashing_bytes_avoided)}
                        detail="Media volume covered by reused base torrents"
                      />
                    )}
                  </MetricGroup>
                )}
                {visible.health && (
                  <MetricGroup
                    title="Health & infrastructure"
                    global={Boolean(activeTracker)}
                  >
                    {visible.cacheHitRate && (
                      <Card
                        icon="cache-hit-rate"
                        label="Cache hit rate"
                        value={`${overview.cache_hit_rate || 0}%`}
                        detail={`${formatNumber(data.cache.hits)} hits · ${formatNumber(data.cache.misses)} misses`}
                        trend={formatTrend(
                          data.comparison?.cache_hit_rate_delta,
                          " pts",
                        )}
                      />
                    )}
                    {visible.cacheWrites && (
                      <Card
                        icon="cache-writes"
                        label="Cache writes"
                        value={formatNumber(data.cache.writes)}
                        detail={`${formatBytes(data.cache.bytes_written)} written since collection began`}
                      />
                    )}
                    {visible.apiOperations && (
                      <Card
                        icon="api-operations"
                        label="API operations"
                        value={formatNumber(overview.api_operations)}
                        detail={`${formatNumber(data.api.errors)} errors`}
                      />
                    )}
                  </MetricGroup>
                )}
                {visible.artifactsSummary && (
                  <MetricGroup title="Generated artifacts">
                    {visible.torrentsCreated && (
                      <Card
                        icon="torrents-created"
                        label="Torrents created"
                        value={formatNumber(overview.torrents_created)}
                        detail={`${formatNumber(artifactMap["torrent:reused"])} reused`}
                      />
                    )}
                    {visible.nzbsCreated && (
                      <Card
                        icon="nzbs-created"
                        label="NZBs created"
                        value={formatNumber(overview.nzbs_created)}
                        detail={`${formatNumber(artifactMap["nzb:reused"])} reused`}
                      />
                    )}
                    {visible.screenshotsCreated && (
                      <Card
                        icon="screenshots-created"
                        label="Screenshots created"
                        value={formatNumber(overview.screenshots_created)}
                        detail={`${formatNumber(screenshotArtifactMap.standard)} standard · ${formatNumber(screenshotArtifactMap.menu)} menus · ${formatNumber(screenshotArtifactMap.spectrogram)} spectrograms · ${formatNumber((screenshotArtifactMap.dovi_plot || 0) + (screenshotArtifactMap.hdr10plus_plot || 0))} HDR plots`}
                      />
                    )}
                  </MetricGroup>
                )}
              </div>
              {visible.dailyActivity && (
                <Section
                  icon="daily-activity"
                  title="Daily activity"
                  subtitle="The three lines are separate measures and are not intended to be added together."
                >
                  <TrendChart
                    rows={data.timeline}
                    trackerActive={Boolean(activeTracker)}
                    dateFormat={settings.dateFormat}
                    gradient={settings.chartGradient}
                  />
                </Section>
              )}
              {visible.uploadFlow && (
                <Section
                  icon="upload-flow"
                  title="Upload flow"
                  subtitle="Each unit is one processed item × target tracker route."
                >
                  <SankeyDiagram sankey={data.sankey} />
                </Section>
              )}
              {visible.activityHeatmap && (
                <Section
                  icon="activity-heatmap"
                  title="Activity heatmap"
                  subtitle="Completed items in the last year."
                >
                  <ActivityHeatmap
                    rows={data.heatmap}
                    today={data.time_context?.today}
                    dateFormat={settings.dateFormat}
                  />
                </Section>
              )}
              {visible.uploadsByDestination && (
                <Section
                  icon="uploads-by-destination"
                  title="Uploads by destination"
                  subtitle="One release uploaded to several sites counts once for each destination."
                >
                  <ChartWithTable
                    chart={
                      <DonutChart
                        ariaLabel="Upload activity by destination"
                        rows={data.uploads.by_destination.map((row) => ({
                          label: row.display_name || row.destination,
                          value: row.successes + row.errors + row.skipped,
                          favicon: row.destination,
                          id: row.destination,
                        }))}
                        activeLabel={activeTracker}
                        onSelect={toggleTracker}
                        showFavicons={settings.showFavicons}
                      />
                    }
                    table={
                      <Table
                        rows={data.uploads.by_destination.map((row) => ({
                          ...row,
                          key: `${row.destination}:${row.type}`,
                        }))}
                        headers={[
                          {
                            label: "Destination",
                            sortValue: (r) => r.display_name || r.destination,
                            render: (r) => (
                              <span className="flex items-center gap-2">
                                {settings.showFavicons && (
                                  <TrackerFavicon destination={r.destination} />
                                )}
                                <span>{r.display_name || r.destination}</span>
                              </span>
                            ),
                          },
                          { label: "Type", key: "type" },
                          {
                            label: "Attempts",
                            sortValue: (r) => r.attempts,
                            render: (r) => formatNumber(r.attempts),
                          },
                          {
                            label: "Success",
                            sortValue: (r) => r.successes,
                            render: (r) => formatNumber(r.successes),
                          },
                          {
                            label: "Errors",
                            sortValue: (r) => r.errors,
                            render: (r) => formatNumber(r.errors),
                          },
                          {
                            label: "Skipped",
                            sortValue: (r) => r.skipped,
                            render: (r) => formatNumber(r.skipped),
                          },
                          {
                            label: "Skip reasons",
                            render: (r) =>
                              Object.entries(r.skip_reasons || {})
                                .map(([reason, count]) => `${reason}: ${count}`)
                                .join(", ") || "—",
                          },
                          {
                            label: "Rate",
                            sortValue: (r) => r.success_rate,
                            render: (r) => `${r.success_rate}%`,
                          },
                          {
                            label: "Pioneering",
                            sortValue: (r) => r.pioneering_rate,
                            render: (r) => `${r.pioneering_rate}%`,
                          },
                          {
                            label: "Health",
                            sortValue: (r) => r.success_rate,
                            render: (r) => (
                              <ReliabilityBadge
                                rate={r.success_rate}
                                attempts={r.attempts}
                              />
                            ),
                          },
                          {
                            label: "Avg time",
                            sortValue: (r) => r.average_duration_ms,
                            render: (r) =>
                              formatDuration(r.average_duration_ms),
                          },
                          {
                            label: "Volume",
                            sortValue: (r) => r.bytes,
                            render: (r) => formatBytes(r.bytes),
                          },
                        ]}
                        activeKey={
                          activeTracker
                            ? `${activeTracker}:${data.uploads.by_destination.find((row) => row.destination === activeTracker)?.type || ""}`
                            : ""
                        }
                        onRowClick={(row) => toggleTracker(row.destination)}
                      />
                    }
                  />
                </Section>
              )}
              {(visible.categories || visible.artifactActivity) && (
                <div className="grid gap-5 lg:grid-cols-2">
                  {visible.categories && (
                    <Section icon="categories" title="Categories">
                      <ChartWithTable
                        chart={
                          <DonutChart
                            ariaLabel="Upload activity by category"
                            rows={data.uploads.by_category.map((row) => ({
                              label: row.category,
                              value: row.successes + row.errors + row.skipped,
                            }))}
                          />
                        }
                        table={
                          <Table
                            rows={data.uploads.by_category}
                            headers={[
                              { label: "Category", key: "category" },
                              { label: "Success", key: "successes" },
                              { label: "Errors", key: "errors" },
                              { label: "Skipped", key: "skipped" },
                              {
                                label: "Volume",
                                sortValue: (r) => r.bytes,
                                render: (r) => formatBytes(r.bytes),
                              },
                            ]}
                          />
                        }
                      />
                    </Section>
                  )}
                  {visible.artifactActivity && (
                    <Section icon="artifact-activity" title="Artifact activity">
                      <ChartWithTable
                        chart={
                          <DonutChart
                            ariaLabel="Artifact activity"
                            rows={data.artifacts.map((row) => ({
                              label: `${formatDimensionValue(row.type)} · ${formatOperation(row.operation)} · ${formatDimensionValue(row.variant)}`,
                              value: row.count,
                            }))}
                          />
                        }
                        table={
                          <Table
                            rows={data.artifacts}
                            headers={[
                              { label: "Type", key: "type" },
                              {
                                label: "Operation",
                                sortValue: (row) =>
                                  formatOperation(row.operation),
                                render: (row) => formatOperation(row.operation),
                              },
                              { label: "Variant", key: "variant" },
                              {
                                label: "Count",
                                sortValue: (r) => r.count,
                                render: (r) => formatNumber(r.count),
                              },
                              {
                                label: "Media volume",
                                sortValue: (r) => r.bytes,
                                render: (r) =>
                                  r.bytes > 0 ? formatBytes(r.bytes) : "—",
                              },
                            ]}
                          />
                        }
                      />
                    </Section>
                  )}
                </div>
              )}
              {visible.contentTime && (
                <Section
                  icon="content-time"
                  title="Successful media time"
                  subtitle="Each successfully processed item is counted once, regardless of destination. Unknown runtimes are excluded."
                >
                  <ChartWithTable
                    chart={
                      <DonutChart
                        ariaLabel="Successfully uploaded media time by category"
                        rows={(data.content_time?.by_category || []).map(
                          (row) => ({
                            label: row.category,
                            value: row.seconds,
                          }),
                        )}
                        valueFormatter={formatMediaHours}
                        centerLabel="uploaded"
                      />
                    }
                    table={
                      <Table
                        rows={data.content_time?.by_category || []}
                        empty="No successful media duration in this period."
                        headers={[
                          { label: "Category", key: "category" },
                          {
                            label: "Items",
                            sortValue: (row) => row.items,
                            render: (row) => formatNumber(row.items),
                          },
                          {
                            label: "Media time",
                            sortValue: (row) => row.seconds,
                            render: (row) => formatMediaTime(row.seconds),
                          },
                          {
                            label: "Hours",
                            sortValue: (row) => row.seconds,
                            render: (row) => formatMediaHours(row.seconds),
                          },
                        ]}
                      />
                    }
                  />
                </Section>
              )}
              {visible.mediaProfile && (
                <Section
                  icon="media-profile"
                  title="Media profile"
                  subtitle="Low-cardinality technical characteristics."
                >
                  <MediaProfile
                    media={data.media}
                    category={mediaCategory}
                    onCategoryChange={setMediaCategory}
                  />
                </Section>
              )}
              {(visible.streamingServices || visible.personalReleases) && (
                <div className="grid gap-5 lg:grid-cols-2">
                  {visible.streamingServices && (
                    <Section
                      icon="streaming-services"
                      title="Streaming services"
                      subtitle="Processed WEB items grouped by their identified source."
                    >
                      <StreamingServices services={data.streaming.services} />
                    </Section>
                  )}
                  {visible.personalReleases && (
                    <Section
                      icon="personal-releases"
                      title="Personal releases"
                      subtitle="Aggregate results only; release groups and tags are never stored."
                    >
                      <ReleaseProfiles
                        releaseProfiles={data.release_profiles}
                      />
                    </Section>
                  )}
                </div>
              )}
              {visible.cacheByProvider && (
                <Section
                  icon="cache-by-provider"
                  title="Cache by provider"
                  subtitle={
                    activeTracker
                      ? "Global · not affected by the tracker filter."
                      : ""
                  }
                >
                  <ChartWithTable
                    chart={
                      <DonutChart
                        ariaLabel="Cache activity by provider"
                        rows={data.cache.by_provider.map((row) => ({
                          label: row.provider,
                          value:
                            row.hits + row.misses + row.writes + row.bypasses,
                        }))}
                      />
                    }
                    table={
                      <Table
                        rows={data.cache.by_provider}
                        headers={[
                          { label: "Provider", key: "provider" },
                          { label: "Hits", key: "hits" },
                          { label: "Misses", key: "misses" },
                          { label: "Writes", key: "writes" },
                          { label: "Bypasses", key: "bypasses" },
                          {
                            label: "Written",
                            sortValue: (r) => r.bytes_written,
                            render: (r) => formatBytes(r.bytes_written),
                          },
                          {
                            label: "Hit rate",
                            sortValue: (r) => r.hit_rate,
                            render: (r) => `${r.hit_rate}%`,
                          },
                        ]}
                      />
                    }
                  />
                </Section>
              )}
              {visible.externalOperations && (
                <Section
                  icon="external-operations"
                  title="External operations"
                  subtitle={`${activeTracker ? "Global · not affected by the tracker filter. " : ""}Logical adapter operations; internal redirects and retries are not counted separately. Bytes sent are available for NNTP and successful image uploads.`}
                >
                  <ChartWithTable
                    chart={
                      <DonutChart
                        ariaLabel="External operations by service"
                        rows={data.api.by_service.map((row) => ({
                          label: `${row.service} · ${formatOperation(row.operation)}`,
                          value: row.requests,
                        }))}
                      />
                    }
                    table={
                      <Table
                        rows={data.api.by_service.map((row) => ({
                          ...row,
                          key: `${row.service}:${row.operation}`,
                        }))}
                        headers={[
                          { label: "Service", key: "service" },
                          {
                            label: "Operation",
                            sortValue: (row) => formatOperation(row.operation),
                            render: (row) => formatOperation(row.operation),
                          },
                          { label: "Requests", key: "requests" },
                          { label: "Success", key: "successes" },
                          { label: "Errors", key: "errors" },
                          {
                            label: "Avg time",
                            sortValue: (r) => r.average_duration_ms,
                            render: (r) =>
                              formatDuration(r.average_duration_ms),
                          },
                          {
                            label: "Bytes sent",
                            sortValue: (r) => r.bytes,
                            render: (r) =>
                              r.bytes > 0 ? formatBytes(r.bytes) : "—",
                          },
                        ]}
                      />
                    }
                  />
                </Section>
              )}
              {visible.executionSource && (
                <Section icon="execution-source" title="Execution source">
                  <ChartWithTable
                    chart={
                      <DonutChart
                        ariaLabel="Completed items by execution source"
                        rows={data.sources.map((row) => ({
                          label: row.source,
                          value: row.count,
                        }))}
                      />
                    }
                    table={
                      <Table
                        rows={data.sources}
                        headers={[
                          { label: "Source", key: "source" },
                          {
                            label: "Completed items",
                            sortValue: (r) => r.count,
                            render: (r) => formatNumber(r.count),
                          },
                        ]}
                      />
                    }
                  />
                </Section>
              )}
            </div>
            {!statsEnabled && (
              <div className="absolute inset-x-0 top-12 z-10 flex justify-center px-4">
                <section
                  className="ua-stats-disabled-notice w-full max-w-lg rounded-xl p-6 text-center shadow-2xl sm:p-8"
                  role="status"
                >
                  <LucideIcon
                    name="triangle-alert"
                    className="mx-auto h-9 w-9 opacity-60"
                  />
                  <h2 className="mt-4 text-lg font-semibold">
                    Statistics collection is disabled
                  </h2>
                  <p className="mt-2 text-sm opacity-70">
                    Enable
                    <code className="mx-1 font-semibold">stats_enabled</code>
                    in Configuration to start viewing activity.
                  </p>
                  <a
                    href={`${APP_BASE}/config`}
                    className="mt-5 inline-flex rounded-lg bg-[var(--ua-copper)] px-4 py-2 text-sm font-semibold text-white transition hover:brightness-110"
                  >
                    Open configuration
                  </a>
                </section>
              </div>
            )}
          </div>
        )}
      </main>
      {resetOpen && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reset-title"
        >
          <div className="w-full max-w-md rounded-xl border bg-[var(--ua-surface,#171615)] p-5 shadow-xl">
            <h2 id="reset-title" className="text-lg font-semibold">
              Reset all statistics?
            </h2>
            <p className="mt-2 text-sm opacity-70">
              This removes real and debug aggregates only. Caches,
              configuration, torrents and NZBs are untouched.
            </p>
            <label className="mt-4 block text-sm">
              Type <strong>RESET</strong> to confirm
              <input
                autoFocus
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                className="mt-2 w-full rounded-lg border bg-transparent px-3 py-2"
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setResetOpen(false);
                  setConfirmation("");
                }}
                className="rounded-lg border px-3 py-2 text-sm"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={confirmation !== "RESET"}
                onClick={reset}
                className="rounded-lg bg-red-600 px-3 py-2 text-sm text-white disabled:opacity-40"
              >
                Reset statistics
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<StatsApp />);
