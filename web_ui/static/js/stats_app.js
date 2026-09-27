const { useEffect, useMemo, useRef, useState } = React;
const APP_BASE = window.location.origin;
const BREAKDOWN_VIEW_KEY = "ua_stats_breakdown_view";
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

const Icon = ({ children }) => (
  <svg
    className="h-5 w-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    {children}
  </svg>
);

const AssetIcon = ({ name }) => (
  <span
    aria-hidden="true"
    className="inline-block h-5 w-5 flex-none"
    style={{
      backgroundColor: "currentColor",
      mask: `url(/static/img/webui-icons/${name}.svg) center / contain no-repeat`,
      WebkitMask: `url(/static/img/webui-icons/${name}.svg) center / contain no-repeat`,
    }}
  />
);

const NavIcon = ({ type }) => {
  if (type === "upload")
    return (
      <Icon>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          d="M12 16V4m0 0L7 9m5-5 5 5M5 20h14"
        />
      </Icon>
    );
  if (type === "changelog")
    return (
      <Icon>
        <circle cx="12" cy="12" r="9" strokeWidth="2" />
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          d="M12 7v5l3 2"
        />
      </Icon>
    );
  if (type === "help")
    return (
      <Icon>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          d="M12 6.75c-2.5-1.5-5.5-1.5-8-.5v11c2.5-1 5.5-1 8 .5m0-11c2.5-1.5 5.5-1.5 8-.5v11c-2.5-1-5.5-1-8 .5m0-11v11"
        />
      </Icon>
    );
  if (type === "logout")
    return (
      <Icon>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          d="M10 17l5-5-5-5m5 5H3m10-8h5a2 2 0 012 2v12a2 2 0 01-2 2h-5"
        />
      </Icon>
    );
  return (
    <Icon>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
        d="M4 19V9m6 10V5m6 14v-7m4 7H2"
      />
    </Icon>
  );
};

const formatNumber = (value) => new Intl.NumberFormat().format(value || 0);
const formatDuration = (value) =>
  value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value || 0}ms`;
const formatBytes = (value) => {
  if (!value || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const power = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    units.length - 1,
  );
  return `${(value / 1024 ** power).toFixed(power ? 1 : 0)} ${units[power]}`;
};
const formatDimensionValue = (value) =>
  String(value || "Unknown").replaceAll("_", " ");
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
              {id === "config" ? (
                <AssetIcon name="settings" />
              ) : (
                <NavIcon type={id} />
              )}
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
            <NavIcon type="changelog" />
            <span>Changelog</span>
          </button>
          <button
            type="button"
            className="ua-app-rail-button rounded-lg"
            onClick={onOpenHelp}
            aria-haspopup="dialog"
          >
            <NavIcon type="help" />
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
            <NavIcon type="logout" />
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
            ×
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
                    <span className="block text-sm font-semibold">
                      {link.label} ↗
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
  <span
    className={`inline-block flex-none ${className}`}
    aria-hidden="true"
    style={{
      backgroundColor: "currentColor",
      mask: `url(/static/img/stats-icons/${name}.svg) center / contain no-repeat`,
      WebkitMask: `url(/static/img/stats-icons/${name}.svg) center / contain no-repeat`,
    }}
  />
);

const MetricIcon = ({ type }) => (
  <span className="flex h-8 w-8 flex-none items-center justify-center opacity-60">
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

function ExportMenu({ disabled, onCsv, onJson }) {
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
    <div ref={menuRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        className="ua-theme-picker rounded-lg px-3 py-2 text-sm disabled:opacity-40"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        Export <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div
          className="ua-stats-export-menu absolute right-0 z-20 mt-2 min-w-36 overflow-hidden rounded-lg py-1 shadow-xl"
          role="menu"
          aria-label="Export statistics"
        >
          <button
            type="button"
            className="block w-full px-3 py-2 text-left text-sm"
            role="menuitem"
            onClick={() => choose(onCsv)}
          >
            CSV timeline
          </button>
          <button
            type="button"
            className="block w-full px-3 py-2 text-left text-sm"
            role="menuitem"
            onClick={() => choose(onJson)}
          >
            JSON details
          </button>
        </div>
      )}
    </div>
  );
}

function TrendChart({ rows }) {
  const [visible, setVisible] = useState({
    items: true,
    uploads: true,
    upload_errors: true,
    api: false,
  });
  const [hovered, setHovered] = useState(null);
  const width = 760,
    height = 190,
    padding = 28;
  const series = [
    { key: "items", label: "Items", color: "#8b5cf6" },
    { key: "uploads", label: "Uploads", color: "#22c55e" },
    { key: "upload_errors", label: "Upload errors", color: "#ef4444" },
    { key: "api", label: "API operations", color: "#f59e0b" },
  ];
  const activeSeries = series.filter((entry) => visible[entry.key]);
  const maximum = Math.max(
    1,
    ...rows.flatMap((row) => activeSeries.map((entry) => row[entry.key] || 0)),
  );
  const xFor = (index) =>
    rows.length <= 1
      ? width / 2
      : padding + (index * (width - padding * 2)) / (rows.length - 1);
  const yFor = (key, row) =>
    height - padding - ((row[key] || 0) * (height - padding * 2)) / maximum;
  const points = (key) =>
    rows
      .map((row, index) => {
        return `${xFor(index)},${yFor(key, row)}`;
      })
      .join(" ");
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
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
            <line
              key={ratio}
              x1={padding}
              x2={width - padding}
              y1={padding + ratio * (height - padding * 2)}
              y2={padding + ratio * (height - padding * 2)}
              stroke="currentColor"
              opacity="0.12"
            />
          ))}
          {activeSeries.map((entry) => (
            <polyline
              key={entry.key}
              points={points(entry.key)}
              fill="none"
              stroke={entry.color}
              strokeWidth="3"
            />
          ))}
          {hovered !== null && (
            <line
              x1={xFor(hovered)}
              x2={xFor(hovered)}
              y1={padding}
              y2={height - padding}
              stroke="currentColor"
              opacity="0.35"
            />
          )}
          {rows.map((row, index) => {
            const segmentWidth =
              (width - padding * 2) / Math.max(1, rows.length - 1);
            return (
              <rect
                key={row.date}
                x={Math.max(0, xFor(index) - segmentWidth / 2)}
                y="0"
                width={segmentWidth}
                height={height}
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
              {new Date(`${rows[hovered].date}T00:00:00`).toLocaleDateString()}
            </p>
            <p className="mt-1">{formatNumber(rows[hovered].items)} items</p>
            <p>{formatNumber(rows[hovered].uploads)} uploads</p>
            <p>{formatNumber(rows[hovered].upload_errors)} upload errors</p>
            <p>{formatBytes(rows[hovered].uploaded_bytes)} uploaded</p>
            <p>{formatNumber(rows[hovered].api)} API operations</p>
          </div>
        )}
      </div>
      <div className="flex flex-wrap justify-center gap-2 text-xs">
        {series.map((entry) => (
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

function ActivityHeatmap({ rows }) {
  const byDate = new Map((rows || []).map((row) => [row.date, row.count]));
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  const start = new Date(today);
  start.setUTCDate(today.getUTCDate() - 364);
  const cells = Array.from({ length: start.getUTCDay() }, () => null);
  for (let offset = 0; offset < 365; offset += 1) {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + offset);
    const key = date.toISOString().slice(0, 10);
    cells.push({ date: key, count: byDate.get(key) || 0 });
  }
  const maximum = Math.max(
    1,
    ...cells.filter(Boolean).map((cell) => cell.count),
  );
  const monthMarkers = [];
  let previousMonth = "";
  cells.forEach((cell, index) => {
    if (!cell) return;
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
  const columnStyle = {
    gridTemplateColumns: "repeat(53, minmax(0, 1fr))",
  };
  return (
    <div className="w-full pb-1">
      <div className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-2 gap-y-1">
        <span aria-hidden="true" />
        <div
          className="grid min-h-4 gap-[2px] text-[0.65rem] opacity-60 sm:gap-1 sm:text-xs"
          style={columnStyle}
          aria-hidden="true"
        >
          {monthMarkers.map((marker, index) => (
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
          <span className="self-center" style={{ gridRowStart: 2 }}>
            Mon
          </span>
          <span className="self-center" style={{ gridRowStart: 4 }}>
            Wed
          </span>
          <span className="self-center" style={{ gridRowStart: 6 }}>
            Fri
          </span>
        </div>
        <div
          className="grid w-full grid-flow-col grid-rows-7 gap-[2px] sm:gap-1"
          role="img"
          aria-label="Activity during the last 365 days"
        >
          {cells.map((cell, index) =>
            cell ? (
              <span
                key={cell.date}
                className="aspect-square rounded-[3px]"
                style={{
                  background: cell.count
                    ? `color-mix(in srgb, var(--ua-copper-bright) ${25 + Math.round((cell.count / maximum) * 70)}%, var(--ua-config-surface))`
                    : "var(--ua-config-surface)",
                }}
                title={`${cell.date}: ${formatNumber(cell.count)} completed`}
              />
            ) : (
              <span key={`empty-${index}`} />
            ),
          )}
        </div>
        <span aria-hidden="true" />
        <div className="mt-1 flex items-center justify-end gap-1 text-xs opacity-60">
          <span>Less</span>
          {[0, 25, 45, 65, 85].map((intensity) => (
            <span
              key={intensity}
              className="h-3 w-3 rounded-[3px]"
              style={{
                background: intensity
                  ? `color-mix(in srgb, var(--ua-copper-bright) ${intensity}%, var(--ua-config-surface))`
                  : "var(--ua-config-surface)",
              }}
              aria-hidden="true"
            />
          ))}
          <span>More</span>
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

function MediaProfile({ media, category, onCategoryChange, view }) {
  const rows = (media?.dimensions || []).filter(
    (row) => row.category === category,
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
      {view === "chart" ? (
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
      ) : (
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
      )}
    </div>
  );
}

function DonutChart({ rows, ariaLabel }) {
  const normalizedRows = rows
    .map((row) => ({
      label: String(row.label || "Unknown"),
      value: Math.max(0, Number(row.value) || 0),
      favicon: row.favicon || "",
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
            />
          ))}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold">{formatNumber(total)}</span>
          <span className="text-xs opacity-60">Total</span>
        </div>
      </div>
      <ul className="grid gap-2 text-sm">
        {segments.map((segment) => (
          <li
            key={segment.label}
            className="flex min-w-0 items-center justify-between gap-3"
          >
            <span className="flex min-w-0 items-center gap-2">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: segment.color }}
                aria-hidden="true"
              />
              {segment.favicon && (
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
              {formatNumber(segment.value)} · {segment.percentage.toFixed(1)}%
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

function Table({ headers, rows, empty = "No data in this period." }) {
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
            <tr key={row.key || index}>
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
  const [period, setPeriod] = useState("30d");
  const [mode, setMode] = useState("real");
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
  const [breakdownView, setBreakdownView] = useState(() =>
    window.UAStorage.get(BREAKDOWN_VIEW_KEY) === "chart" ? "chart" : "table",
  );
  const [mediaCategory, setMediaCategory] = useState("");

  useEffect(() => {
    window.UAStorage.set("ua_config_theme", isDarkMode ? "dark" : "light");
    document.documentElement.dataset.uaMode = isDarkMode ? "dark" : "light";
  }, [isDarkMode]);
  useEffect(() => {
    window.UAStorage.set(BREAKDOWN_VIEW_KEY, breakdownView);
  }, [breakdownView]);

  const load = async (signal) => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${APP_BASE}/api/stats?range=${period}&mode=${mode}`,
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
  }, [period, mode]);
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
  const statsEnabled = data?.enabled !== false;
  const artifactMap = useMemo(
    () =>
      (data?.artifacts || []).reduce((totals, row) => {
        const key = `${row.type}:${row.operation}`;
        totals[key] = (totals[key] || 0) + row.count;
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
      `upload-assistant-stats-${period}-${mode}.json`,
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
      `upload-assistant-stats-${period}-${mode}.csv`,
      lines.join("\n"),
      "text/csv;charset=utf-8",
    );
  };
  return (
    <div
      className={`ua-config-page min-h-screen md:pl-20 ${isDarkMode ? "ua-mode-dark" : "ua-mode-light"}`}
    >
      {helpOpen && <HelpResourcesModal onClose={() => setHelpOpen(false)} />}
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
      <main className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">
        <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest opacity-60">
              Upload Assistant
            </p>
            <h1 className="mt-1 text-2xl font-bold">Statistics</h1>
            <p className="mt-1 text-sm opacity-60">Local daily aggregates.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <div
              className="ua-theme-picker flex rounded-lg p-1"
              role="group"
              aria-label="Breakdown visualization"
            >
              {["table", "chart"].map((view) => (
                <button
                  key={view}
                  type="button"
                  onClick={() => setBreakdownView(view)}
                  aria-pressed={breakdownView === view}
                  className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                    breakdownView === view
                      ? "bg-[var(--ua-copper)] text-white"
                      : "opacity-60 hover:opacity-100"
                  }`}
                >
                  {view === "table" ? "Tables" : "Charts"}
                </button>
              ))}
            </div>
            <select
              value={period}
              onChange={(event) => setPeriod(event.target.value)}
              className="ua-theme-picker rounded-lg px-3 py-2 text-sm"
              aria-label="Statistics period"
            >
              <option value="7d">7 days</option>
              <option value="30d">30 days</option>
              <option value="90d">90 days</option>
              <option value="all">All time</option>
            </select>
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value)}
              className="ua-theme-picker rounded-lg px-3 py-2 text-sm"
              aria-label="Statistics mode"
            >
              <option value="real">Real activity</option>
              <option value="debug">Debug simulations</option>
            </select>
            <ExportMenu
              disabled={!statsEnabled || !hasData}
              onCsv={exportCsv}
              onJson={exportJson}
            />
            <button
              type="button"
              onClick={() => setResetOpen(true)}
              className="rounded-lg border border-red-500 px-3 py-2 text-sm text-red-500"
            >
              Reset
            </button>
          </div>
        </header>
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
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Card
                  icon="items-completed"
                  label="Items completed"
                  value={formatNumber(overview.items_completed)}
                  detail={`${formatNumber(data.items.success)} with upload · ${formatNumber(data.items.no_upload)} without upload · ${formatNumber(data.items.error)} errors`}
                  trend={formatTrend(data.comparison?.items_completed_pct)}
                />
                <Card
                  icon="successful-uploads"
                  label="Successful uploads"
                  value={formatNumber(overview.uploads)}
                  detail={`${overview.upload_success_rate || 0}% of ${formatNumber(overview.upload_attempts)} attempts`}
                  trend={formatTrend(data.comparison?.uploads_pct)}
                />
                <Card
                  icon="torrents-created"
                  label="Torrents created"
                  value={formatNumber(overview.torrents_created)}
                  detail={`${formatNumber(artifactMap["torrent:reused"])} reused`}
                />
                <Card
                  icon="nzbs-created"
                  label="NZBs created"
                  value={formatNumber(overview.nzbs_created)}
                  detail={`${formatNumber(artifactMap["nzb:reused"])} reused`}
                />
                <Card
                  icon="api-operations"
                  label="API operations"
                  value={formatNumber(overview.api_operations)}
                  detail={`${formatNumber(data.api.errors)} errors`}
                />
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
                <Card
                  icon="cache-writes"
                  label="Cache writes"
                  value={formatNumber(data.cache.writes)}
                  detail={`${formatBytes(data.cache.bytes_written)} written since collection began`}
                />
                <Card
                  icon="mode"
                  label="Mode"
                  value={mode === "real" ? "Real" : "Debug"}
                  detail="Debug never affects real totals"
                />
                <Card
                  icon="data-uploaded"
                  label="Data uploaded"
                  value={formatBytes(overview.uploaded_bytes)}
                  detail="Successful destination uploads"
                />
                <Card
                  icon="average-item-size"
                  label="Average item size"
                  value={formatBytes(overview.average_item_bytes)}
                  detail={`${formatBytes(overview.processed_bytes)} processed`}
                />
                <Card
                  icon="duplicates-prevented"
                  label="Duplicates prevented"
                  value={formatNumber(overview.duplicate_preventions)}
                  detail={`${overview.pioneering_rate || 0}% pioneering rate`}
                />
                <Card
                  icon="hashing-io-avoided"
                  label="Hashing I/O avoided"
                  value={formatBytes(overview.hashing_bytes_avoided)}
                  detail="Media volume covered by reused base torrents"
                />
              </div>
              <Section
                icon="daily-activity"
                title="Daily activity"
                subtitle="The three lines are separate measures and are not intended to be added together."
              >
                <TrendChart rows={data.timeline} />
              </Section>
              <Section
                icon="activity-heatmap"
                title="Activity heatmap"
                subtitle="Completed items over the last 365 days. Darker cells indicate busier days."
              >
                <ActivityHeatmap rows={data.heatmap} />
              </Section>
              <Section
                icon="uploads-by-destination"
                title="Uploads by destination"
                subtitle="One release uploaded to several sites counts once for each destination."
              >
                {breakdownView === "chart" ? (
                  <DonutChart
                    ariaLabel="Upload activity by destination"
                    rows={data.uploads.by_destination.map((row) => ({
                      label: row.destination,
                      value: row.successes + row.errors + row.skipped,
                      favicon: row.destination,
                    }))}
                  />
                ) : (
                  <Table
                    rows={data.uploads.by_destination.map((row) => ({
                      ...row,
                      key: `${row.destination}:${row.type}`,
                    }))}
                    headers={[
                      {
                        label: "Destination",
                        sortValue: (r) => r.destination,
                        render: (r) => (
                          <span className="flex items-center gap-2">
                            <TrackerFavicon destination={r.destination} />
                            <span>{r.destination}</span>
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
                        render: (r) => formatDuration(r.average_duration_ms),
                      },
                      {
                        label: "Volume",
                        sortValue: (r) => r.bytes,
                        render: (r) => formatBytes(r.bytes),
                      },
                    ]}
                  />
                )}
              </Section>
              <div className="grid gap-5 lg:grid-cols-2">
                <Section icon="categories" title="Categories">
                  {breakdownView === "chart" ? (
                    <DonutChart
                      ariaLabel="Upload activity by category"
                      rows={data.uploads.by_category.map((row) => ({
                        label: row.category,
                        value: row.successes + row.errors + row.skipped,
                      }))}
                    />
                  ) : (
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
                  )}
                </Section>
                <Section icon="artifact-activity" title="Artifact activity">
                  {breakdownView === "chart" ? (
                    <DonutChart
                      ariaLabel="Artifact activity"
                      rows={data.artifacts.map((row) => ({
                        label: `${row.type} · ${row.operation} · ${row.variant}`,
                        value: row.count,
                      }))}
                    />
                  ) : (
                    <Table
                      rows={data.artifacts}
                      headers={[
                        { label: "Type", key: "type" },
                        { label: "Operation", key: "operation" },
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
                  )}
                </Section>
              </div>
              <Section
                icon="media-profile"
                title="Media profile"
                subtitle="Low-cardinality technical characteristics appropriate to each category."
              >
                <MediaProfile
                  media={data.media}
                  category={mediaCategory}
                  onCategoryChange={setMediaCategory}
                  view={breakdownView}
                />
              </Section>
              <Section icon="cache-by-provider" title="Cache by provider">
                {breakdownView === "chart" ? (
                  <DonutChart
                    ariaLabel="Cache activity by provider"
                    rows={data.cache.by_provider.map((row) => ({
                      label: row.provider,
                      value: row.hits + row.misses + row.writes + row.bypasses,
                    }))}
                  />
                ) : (
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
                )}
              </Section>
              <Section
                icon="external-operations"
                title="External operations"
                subtitle="Logical adapter operations; internal redirects and retries are not counted separately. Bytes sent are available for NNTP and successful image uploads."
              >
                {breakdownView === "chart" ? (
                  <DonutChart
                    ariaLabel="External operations by service"
                    rows={data.api.by_service.map((row) => ({
                      label: `${row.service} · ${row.operation}`,
                      value: row.requests,
                    }))}
                  />
                ) : (
                  <Table
                    rows={data.api.by_service.map((row) => ({
                      ...row,
                      key: `${row.service}:${row.operation}`,
                    }))}
                    headers={[
                      { label: "Service", key: "service" },
                      { label: "Operation", key: "operation" },
                      { label: "Requests", key: "requests" },
                      { label: "Success", key: "successes" },
                      { label: "Errors", key: "errors" },
                      {
                        label: "Avg time",
                        sortValue: (r) => r.average_duration_ms,
                        render: (r) => formatDuration(r.average_duration_ms),
                      },
                      {
                        label: "Bytes sent",
                        sortValue: (r) => r.bytes,
                        render: (r) =>
                          r.bytes > 0 ? formatBytes(r.bytes) : "—",
                      },
                    ]}
                  />
                )}
              </Section>
              <Section icon="execution-source" title="Execution source">
                {breakdownView === "chart" ? (
                  <DonutChart
                    ariaLabel="Completed items by execution source"
                    rows={data.sources.map((row) => ({
                      label: row.source,
                      value: row.count,
                    }))}
                  />
                ) : (
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
                )}
              </Section>
            </div>
            {!statsEnabled && (
              <div className="absolute inset-x-0 top-12 z-10 flex justify-center px-4">
                <section
                  className="ua-stats-disabled-notice w-full max-w-lg rounded-xl p-6 text-center shadow-2xl sm:p-8"
                  role="status"
                >
                  <svg
                    className="mx-auto h-9 w-9 opacity-60"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="1.8"
                      d="M12 9v4m0 4h.01M10.3 4.4 2.6 18a2 2 0 001.74 3h15.32a2 2 0 001.74-3L13.7 4.4a2 2 0 00-3.4 0z"
                    />
                  </svg>
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
