const { useEffect, useRef, useState } = React;
const APP_BASE = window.location.origin;
const LucideIcon = window.UALucideIcon;
const PAGE_SIZE = 50;

const OUTCOMES = [
  ["", "All"],
  ["success", "Uploaded"],
  ["error", "Failed"],
  ["no_upload", "Not uploaded"],
  ["skipped", "Skipped"],
];
const OUTCOME_STYLE = {
  success: { label: "Uploaded", tone: "success", icon: "circle-check" },
  error: { label: "Failed", tone: "error", icon: "circle-x" },
  no_upload: { label: "Not uploaded", tone: "muted", icon: "circle-minus" },
  skipped: { label: "Skipped", tone: "muted", icon: "circle-minus" },
};
const TRACKER_STATUS = {
  success: { label: "Uploaded", tone: "success", icon: "circle-check" },
  failed: { label: "Failed", tone: "error", icon: "circle-x" },
  dupe: { label: "Dupe", tone: "attention", icon: "copy-check" },
  banned: { label: "Banned", tone: "error", icon: "ban" },
  skipped: { label: "Skipped", tone: "muted", icon: "circle-minus" },
};
const TRACKER_STATUS_FILTERS = [
  ["", "Any result"],
  ["success", "Uploaded"],
  ["failed", "Failed"],
  ["dupe", "Dupe"],
  ["banned", "Banned"],
  ["skipped", "Skipped"],
];
const REASONS = {
  skipped_by_user: "Skipped at a prompt",
  unsupported: "Unsupported release",
  exception: "Stopped by an error",
  site_check: "Site check",
};
const PROVIDER_LABELS = {
  imdb: "IMDb",
  tmdb: "TMDb",
  tvdb: "TVDB",
  tvmaze: "TVmaze",
  mal: "MAL",
  igdb: "IGDB",
  douban: "Douban",
  openlibrary: "Open Library",
  discogs_release: "Discogs release",
  discogs_master: "Discogs master",
  isbn: "ISBN",
  asin: "ASIN",
};

const AssetIcon = ({ name, className = "h-5 w-5" }) => (
  <LucideIcon name={name} className={className} />
);

// The shared helper refreshes the CSRF token and retries once, e.g. after
// signing out and back in from another tab.
const apiFetch = (url, options = {}) =>
  window.uaApiFetch(url, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });

const formatBytes = (value) => {
  const bytes = Number(value) || 0;
  if (!bytes) return "";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const exponent = Math.min(
    units.length - 1,
    Math.floor(Math.log(bytes) / Math.log(1024)),
  );
  const amount = bytes / 1024 ** exponent;
  return `${amount.toFixed(exponent && amount < 100 ? 1 : 0)} ${units[exponent]}`;
};

const formatDateTime = (value) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
};

const formatDuration = (milliseconds) => {
  const seconds = Math.round((Number(milliseconds) || 0) / 1000);
  if (!seconds) return "";
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
};

const localDayStart = (value, addDays = 0) => {
  if (!value) return "";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "";
  date.setDate(date.getDate() + addDays);
  return date.toISOString();
};

const trackerFaviconUrl = (tracker) => {
  const slug = String(tracker || "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
  return slug ? `${APP_BASE}/static/img/trackers/${slug}.png` : "";
};

const TrackerFavicon = ({ tracker, className = "h-4 w-4" }) => {
  const src = trackerFaviconUrl(tracker);
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

// Links come from stored tracker data; only web pages are opened.
const isWebLink = (href) => typeof href === "string" && /^https?:\/\//i.test(href);

const ExternalLink = ({ href, children, className = "" }) =>
  isWebLink(href) ? (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`ua-history-link inline-flex items-center gap-1 underline-offset-2 hover:underline ${className}`}
    >
      {children}
      <AssetIcon name="external-link" className="h-3 w-3 opacity-70" />
    </a>
  ) : (
    <span className={className}>{children}</span>
  );

const StatusChip = ({ status, styles }) => {
  const style = styles[status] || {
    label: status,
    tone: "muted",
    icon: "circle",
  };
  return (
    <span
      className="ua-history-status inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold"
      data-tone={style.tone}
    >
      <AssetIcon name={style.icon} className="h-3.5 w-3.5" />
      {style.label}
    </span>
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
    ["history", "History", "/history"],
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
              data-active={id === "history" ? "true" : "false"}
              aria-current={id === "history" ? "page" : undefined}
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
                <window.UAAppearanceControls
                  colorTheme={colorTheme}
                  onColorThemeChange={onColorThemeChange}
                  interfaceStyle={interfaceStyle}
                  onInterfaceStyleChange={onInterfaceStyleChange}
                  isDarkMode={isDarkMode}
                  onToggleMode={onToggleMode}
                  labelClassName="ua-app-rail-popover-label"
                />
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
              data-active={id === "history" ? "true" : "false"}
              aria-current={id === "history" ? "page" : undefined}
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
        aria-labelledby="history-help-title"
        tabIndex="-1"
      >
        <header className="ua-config-section-heading flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 id="history-help-title" className="text-lg font-semibold">
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
            <AssetIcon name="x" className="h-4 w-4" />
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
                      <AssetIcon name="external-link" className="h-3.5 w-3.5" />
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

const trackerLabel = (names, tracker) => names?.[tracker] || tracker;

// Return false when the browser blocks session storage, so the caller can say so.
const uploadAgain = (path) => {
  if (!window.UAUploadHandoff.offer(path)) return false;
  window.location = `${APP_BASE}/`;
  return true;
};

const releaseDetails = (item) =>
  [
    item.category,
    item.year,
    item.season || item.episode
      ? `${item.season || ""}${item.episode || ""}`
      : "",
    item.resolution,
    item.release_type,
    formatBytes(item.size),
  ]
    .filter(Boolean)
    .join(" · ");

function HistoryRow({ item, trackerNames, onOpen }) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(item.id)}
        className="ua-history-row flex w-full min-w-0 items-start gap-3 rounded-xl p-3 text-left sm:p-4"
      >
        {item.artwork_url ? (
          <img
            src={item.artwork_url}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            className="hidden h-16 w-11 flex-none rounded-md object-cover sm:block"
            onError={(event) => event.currentTarget.classList.add("sm:hidden")}
          />
        ) : (
          <span className="ua-history-cover-placeholder hidden h-16 w-11 flex-none items-center justify-center rounded-md sm:flex">
            <AssetIcon name="archive" className="h-5 w-5 opacity-40" />
          </span>
        )}
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="min-w-0 break-words font-semibold">
              {item.name}
            </span>
            <StatusChip status={item.outcome} styles={OUTCOME_STYLE} />
            {item.site_check && (
              <span className="rounded-md border px-1.5 py-0.5 text-[0.7rem] opacity-70">
                Site check
              </span>
            )}
          </span>
          <span className="mt-1 block text-xs opacity-60">
            {[formatDateTime(item.finished_at), releaseDetails(item)]
              .filter(Boolean)
              .join(" · ")}
            {item.reason && REASONS[item.reason]
              ? ` · ${REASONS[item.reason]}`
              : ""}
          </span>
          {(item.trackers.length > 0 || item.request_count > 0) && (
            <span className="mt-2 flex flex-wrap items-center gap-1.5">
              {item.trackers.map((tracker) => (
                <span
                  key={tracker.tracker}
                  className="ua-history-status inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs"
                  data-tone={TRACKER_STATUS[tracker.status]?.tone || "muted"}
                  title={`${trackerLabel(trackerNames, tracker.tracker)}: ${TRACKER_STATUS[tracker.status]?.label || tracker.status}`}
                >
                  <TrackerFavicon
                    tracker={tracker.tracker}
                    className="h-3.5 w-3.5"
                  />
                  {tracker.tracker}
                </span>
              ))}
              {item.request_count > 0 && (
                <span
                  className="ua-history-status inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs"
                  data-tone="info"
                >
                  <AssetIcon name="hand-coins" className="h-3.5 w-3.5" />
                  {item.request_count} request
                  {item.request_count === 1 ? "" : "s"}
                </span>
              )}
            </span>
          )}
        </span>
        <AssetIcon
          name="chevron-right"
          className="mt-1 h-4 w-4 flex-none opacity-50"
        />
      </button>
    </li>
  );
}

const DetailSection = ({ title, children }) => (
  <section className="border-t pt-4">
    <h3 className="mb-2 text-sm font-semibold">{title}</h3>
    {children}
  </section>
);

function DupesList({ dupes }) {
  if (!dupes?.entries?.length) return null;
  return (
    <details className="mt-1.5">
      <summary className="cursor-pointer text-xs opacity-70">
        {dupes.trumpable ? "Trumpable releases" : "Possible dupes"} (
        {dupes.entries.length})
      </summary>
      <ul className="mt-1 space-y-0.5 pl-4 text-xs">
        {dupes.entries.map((entry, index) => (
          <li
            key={`${entry.link || entry.name}-${index}`}
            className="break-words"
          >
            <ExternalLink href={entry.link}>{entry.name}</ExternalLink>
            {entry.size ? (
              <span className="opacity-60"> · {formatBytes(entry.size)}</span>
            ) : null}
          </li>
        ))}
      </ul>
      {dupes.note && (
        <p className="mt-1 pl-4 text-xs opacity-60">{dupes.note}</p>
      )}
    </details>
  );
}

function SlotDetails({ slot }) {
  if (!slot?.title) return null;
  const conflicts = Array.isArray(slot.conflicts) ? slot.conflicts : [];
  const notes = Array.isArray(slot.notes) ? slot.notes : [];
  return (
    <div className="mt-0.5 text-xs opacity-70">
      <p>
        Slot: {slot.title}
        {slot.slot ? ` (${slot.slot})` : ""}
        {slot.reason ? ` — ${slot.reason}` : ""}
      </p>
      {slot.why && <p className="mt-0.5">{slot.why}</p>}
      {conflicts.length > 0 && (
        <ul className="mt-0.5 space-y-0.5 pl-4">
          {conflicts.map((entry, index) => (
            <li
              key={`${entry.link || entry.name}-${index}`}
              className="break-words"
            >
              <ExternalLink href={entry.link}>{entry.name}</ExternalLink>
              {entry.size ? (
                <span className="opacity-60"> · {formatBytes(entry.size)}</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {notes.map((note, index) => (
        <p key={index} className="mt-0.5">
          {note}
        </p>
      ))}
      {(slot.rules || slot.rules_url) && (
        <p className="mt-0.5">
          {slot.rules_url ? (
            <ExternalLink href={slot.rules_url}>
              {slot.rules || "Tracker rules"}
            </ExternalLink>
          ) : (
            slot.rules
          )}
        </p>
      )}
    </div>
  );
}

function HistoryDetail({ itemId, onClose, onDeleted }) {
  const dialogRef = window.useUAModalFocus(onClose);
  const [item, setItem] = useState(null);
  const [trackerNames, setTrackerNames] = useState({});
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const response = await apiFetch(`${APP_BASE}/api/history/${itemId}`, {
          signal: controller.signal,
        });
        const body = await response.json();
        if (!response.ok || !body.success)
          throw new Error(body.error || "Unable to load this entry");
        setItem(body.item);
        setTrackerNames(body.item.tracker_names || {});
      } catch (err) {
        if (err?.name !== "AbortError") setError(err.message);
      }
    })();
    return () => controller.abort();
  }, [itemId]);

  const remove = async () => {
    setDeleting(true);
    try {
      const response = await apiFetch(`${APP_BASE}/api/history/${itemId}`, {
        method: "DELETE",
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || "Unable to delete");
      onDeleted(itemId);
    } catch (err) {
      setError(err.message);
      setDeleting(false);
    }
  };

  const copyPath = async () => {
    try {
      await navigator.clipboard.writeText(item.path);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (_error) {
      setCopied(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-2 sm:p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="ua-config-modal flex max-h-[94vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-detail-title"
        tabIndex="-1"
      >
        <header className="ua-config-section-heading flex items-start justify-between gap-3 border-b px-4 py-4 sm:px-5">
          <div className="min-w-0">
            <h2
              id="history-detail-title"
              className="break-words text-lg font-semibold"
            >
              {item?.name || "History entry"}
            </h2>
            {item && (
              <p className="mt-1 text-sm opacity-60">
                {formatDateTime(item.finished_at)}
                {item.duration_ms
                  ? ` · ${formatDuration(item.duration_ms)}`
                  : ""}
                {item.source
                  ? ` · ${item.source === "webui" ? "Web UI" : "CLI"}`
                  : ""}
              </p>
            )}
          </div>
          <button
            type="button"
            className="ua-config-icon-button h-9 w-9 flex-none"
            onClick={onClose}
            aria-label="Close entry"
            data-ua-modal-initial-focus
          >
            <AssetIcon name="x" className="h-4 w-4" />
          </button>
        </header>
        <div className="min-h-0 space-y-4 overflow-y-auto px-4 py-4 sm:px-5">
          {error && (
            <p role="alert" className="text-sm text-red-500">
              {error}
            </p>
          )}
          {!item && !error && <p className="text-sm opacity-60">Loading…</p>}
          {item && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <StatusChip status={item.outcome} styles={OUTCOME_STYLE} />
                {item.reason && REASONS[item.reason] && (
                  <span className="text-sm opacity-70">
                    {REASONS[item.reason]}
                  </span>
                )}
                {item.personal_release && (
                  <span className="rounded-md border px-1.5 py-0.5 text-xs opacity-70">
                    Personal release
                  </span>
                )}
              </div>
              <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                {[
                  ["Title", item.title],
                  ["Year", item.year],
                  ["Category", item.category],
                  ["Type", item.release_type],
                  ["Resolution", item.resolution],
                  ["Group", item.release_group],
                  [
                    "Season / episode",
                    `${item.season || ""}${item.episode || ""}`,
                  ],
                  ["Size", formatBytes(item.size)],
                  ["Infohash", item.infohash],
                ]
                  .filter(([, value]) => value)
                  .map(([label, value]) => (
                    <div key={label} className="min-w-0">
                      <dt className="text-xs uppercase tracking-wide opacity-55">
                        {label}
                      </dt>
                      <dd className="break-words font-medium">{value}</dd>
                    </div>
                  ))}
                <div className="min-w-0 sm:col-span-2">
                  <dt className="text-xs uppercase tracking-wide opacity-55">
                    Path
                  </dt>
                  <dd className="flex min-w-0 items-start gap-2">
                    <code className="min-w-0 flex-1 break-all text-xs">
                      {item.path}
                    </code>
                    <button
                      type="button"
                      onClick={copyPath}
                      className="ua-config-icon-button h-7 w-7 flex-none"
                      aria-label="Copy path"
                      title={copied ? "Copied" : "Copy path"}
                    >
                      <AssetIcon
                        name={copied ? "check" : "copy"}
                        className="h-3.5 w-3.5"
                      />
                    </button>
                  </dd>
                </div>
              </dl>
              {item.ids.length > 0 && (
                <DetailSection title="External IDs">
                  <ul className="flex flex-wrap gap-2 text-sm">
                    {item.ids.map((entry) => (
                      <li
                        key={entry.provider}
                        className="rounded-md border px-2 py-1"
                      >
                        <span className="opacity-60">
                          {PROVIDER_LABELS[entry.provider] ||
                            entry.provider}{" "}
                        </span>
                        <ExternalLink href={entry.link} className="font-medium">
                          {entry.value}
                        </ExternalLink>
                      </li>
                    ))}
                  </ul>
                </DetailSection>
              )}
              <DetailSection title="Trackers">
                {item.trackers.length === 0 ? (
                  <p className="text-sm opacity-60">No tracker was selected.</p>
                ) : (
                  <ul className="divide-y">
                    {item.trackers.map((tracker) => (
                      <li key={tracker.tracker} className="py-2 text-sm">
                        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
                          <span className="flex min-w-[8rem] flex-1 items-center gap-2 font-medium">
                            <TrackerFavicon tracker={tracker.tracker} />
                            {trackerLabel(trackerNames, tracker.tracker)}
                          </span>
                          <StatusChip
                            status={tracker.status}
                            styles={TRACKER_STATUS}
                          />
                          {tracker.duration ? (
                            <span className="text-xs tabular-nums opacity-60">
                              {Number(tracker.duration).toFixed(1)}s
                            </span>
                          ) : null}
                          {tracker.link && (
                            <ExternalLink
                              href={tracker.link}
                              className="text-xs"
                            >
                              {tracker.torrent_id
                                ? `#${tracker.torrent_id}`
                                : "Open"}
                            </ExternalLink>
                          )}
                        </div>
                        {tracker.message && (
                          <p className="mt-0.5 break-words text-xs opacity-70">
                            {tracker.message}
                          </p>
                        )}
                        <SlotDetails slot={tracker.slot} />
                        <DupesList dupes={tracker.dupes} />
                      </li>
                    ))}
                  </ul>
                )}
              </DetailSection>
              {item.requests.length > 0 && (
                <DetailSection title="Request matches">
                  <ul className="divide-y">
                    {item.requests.map((request, index) => (
                      <li
                        key={`${request.tracker}-${request.link || request.name}-${index}`}
                        className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm"
                      >
                        <span className="flex items-center gap-1.5 font-medium">
                          <TrackerFavicon tracker={request.tracker} />
                          {trackerLabel(trackerNames, request.tracker)}
                        </span>
                        <ExternalLink
                          href={request.link}
                          className="min-w-0 flex-1 break-words"
                        >
                          {request.name}
                        </ExternalLink>
                        {request.reward && (
                          <span className="rounded-md border px-1.5 py-0.5 text-xs">
                            {request.reward}
                          </span>
                        )}
                        <span className="text-xs opacity-60">
                          {[
                            request.exact ? "Exact match" : "Partial match",
                            request.status,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </li>
                    ))}
                  </ul>
                </DetailSection>
              )}
            </>
          )}
        </div>
        {item && (
          <footer className="flex flex-wrap items-center justify-end gap-2 border-t px-4 py-3 sm:px-5">
            {confirmDelete ? (
              <>
                <span className="mr-auto text-sm">Delete this entry?</span>
                <button
                  type="button"
                  className="rounded-lg border px-3 py-2 text-sm"
                  onClick={() => setConfirmDelete(false)}
                  disabled={deleting}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="rounded-lg bg-red-600 px-3 py-2 text-sm text-white disabled:opacity-40"
                  onClick={remove}
                  disabled={deleting}
                >
                  {deleting ? "Deleting…" : "Delete"}
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="ua-config-danger-button mr-auto inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm"
                  onClick={() => setConfirmDelete(true)}
                >
                  <AssetIcon name="trash-2" className="h-4 w-4" />
                  Delete entry
                </button>
                <button
                  type="button"
                  className="ua-stats-control inline-flex min-w-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm"
                  onClick={() => {
                    if (!uploadAgain(item.path))
                      setError(
                        "This browser blocks session storage, so the path cannot be passed to the Upload page. Copy the path above and paste it there.",
                      );
                  }}
                  title="Open the Upload page with this path in the queue"
                >
                  <AssetIcon name="upload" className="h-4 w-4" />
                  Upload again
                </button>
              </>
            )}
          </footer>
        )}
      </section>
    </div>
  );
}

function ClearHistoryDialog({ onClose, onCleared }) {
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const close = () => {
    if (!busy) onClose();
  };
  const dialogRef = window.useUAModalFocus(close);
  const clear = async () => {
    setBusy(true);
    setError("");
    try {
      const response = await apiFetch(`${APP_BASE}/api/history`, {
        method: "DELETE",
        body: JSON.stringify({ confirmation }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(body.error || "Unable to clear the history");
      onCleared();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };
  return (
    <div
      className="fixed inset-0 z-[70] grid place-items-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="clear-history-title"
      ref={dialogRef}
      tabIndex="-1"
    >
      <div className="ua-config-modal w-full max-w-md rounded-xl border p-5 shadow-xl">
        <h2 id="clear-history-title" className="text-lg font-semibold">
          Clear the whole history?
        </h2>
        <p className="mt-2 text-sm opacity-70">
          This removes every history entry. Statistics, caches, configuration,
          torrents and NZBs are untouched.
        </p>
        <label className="mt-4 block text-sm">
          Type <strong>CLEAR</strong> to confirm
          <input
            data-ua-modal-initial-focus
            disabled={busy}
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            className="ua-config-input mt-2 w-full rounded-lg border px-3 py-2"
          />
        </label>
        {error && (
          <p role="alert" className="mt-3 text-sm text-red-500">
            {error}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={close}
            disabled={busy}
            className="rounded-lg border px-3 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={confirmation !== "CLEAR" || busy}
            onClick={clear}
            className="rounded-lg bg-red-600 px-3 py-2 text-sm text-white disabled:opacity-40"
          >
            {busy ? "Clearing…" : "Clear history"}
          </button>
        </div>
      </div>
    </div>
  );
}

function HistoryApp() {
  const [isDarkMode, setIsDarkMode] = useState(window.getUAStoredTheme);
  const [colorTheme, setColorTheme] = useState(window.getUAStoredColorTheme);
  const [interfaceStyle, setInterfaceStyle] = useState(
    window.getUAStoredInterfaceStyle,
  );
  const [helpOpen, setHelpOpen] = useState(false);
  const [changelogOpen, setChangelogOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [outcome, setOutcome] = useState("");
  const [category, setCategory] = useState("");
  const [tracker, setTracker] = useState("");
  const [trackerStatus, setTrackerStatus] = useState("");
  const [withRequests, setWithRequests] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [openItem, setOpenItem] = useState(null);
  const [refresh, setRefresh] = useState(0);
  const [exporting, setExporting] = useState("");
  const [exportError, setExportError] = useState("");

  useEffect(() => {
    window.setUAThemeMode(isDarkMode);
  }, [isDarkMode]);
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);
  useEffect(() => {
    setOffset(0);
  }, [
    search,
    outcome,
    category,
    tracker,
    trackerStatus,
    withRequests,
    dateFrom,
    dateTo,
  ]);

  const filterQuery = () => {
    const query = new URLSearchParams();
    if (search) query.set("q", search);
    if (outcome) query.set("outcome", outcome);
    if (category) query.set("category", category);
    if (tracker) query.set("tracker", tracker);
    if (trackerStatus) query.set("tracker_status", trackerStatus);
    if (withRequests) query.set("requests", "1");
    if (dateFrom) query.set("after", localDayStart(dateFrom));
    if (dateTo) query.set("before", localDayStart(dateTo, 1));
    return query;
  };

  const exportHistory = async (format) => {
    setExporting(format);
    setExportError("");
    try {
      const query = filterQuery();
      // Use the text in the search box, even if the list has not caught up with it yet.
      const typed = searchInput.trim();
      if (typed) query.set("q", typed);
      else query.delete("q");
      query.set("format", format);
      const response = await apiFetch(
        `${APP_BASE}/api/history/export?${query.toString()}`,
      );
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.error || "Unable to export the history");
      }
      const disposition = response.headers.get("Content-Disposition") || "";
      const filename =
        disposition.match(/filename="([^"]+)"/)?.[1] ||
        `upload-assistant-history.${format}`;
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err.message);
    } finally {
      setExporting("");
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      setLoading(true);
      setError("");
      try {
        const query = filterQuery();
        query.set("limit", String(PAGE_SIZE));
        query.set("offset", String(offset));
        const response = await apiFetch(
          `${APP_BASE}/api/history?${query.toString()}`,
          { signal: controller.signal },
        );
        const body = await response.json();
        if (!response.ok || !body.success)
          throw new Error(body.error || "Unable to load the history");
        if (!body.items.length && offset > 0 && body.total > 0) {
          // The last entry of this page was deleted: show the last page that has entries.
          setOffset(Math.floor((body.total - 1) / PAGE_SIZE) * PAGE_SIZE);
          return;
        }
        setData(body);
      } catch (err) {
        if (err?.name === "AbortError") return;
        setData(null);
        setError(err.message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [
    search,
    outcome,
    category,
    tracker,
    trackerStatus,
    withRequests,
    dateFrom,
    dateTo,
    offset,
    refresh,
  ]);

  const counts = data?.counts || {};
  const totalAll = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const total = data?.total || 0;
  const filtersActive = Boolean(
    search ||
    category ||
    tracker ||
    trackerStatus ||
    withRequests ||
    dateFrom ||
    dateTo,
  );
  const resetFilters = () => {
    setSearchInput("");
    setSearch("");
    setOutcome("");
    setCategory("");
    setTracker("");
    setTrackerStatus("");
    setWithRequests(false);
    setDateFrom("");
    setDateTo("");
  };

  return (
    <div
      className={`ua-config-page ua-history-page min-h-screen md:pl-20 ${isDarkMode ? "ua-mode-dark" : "ua-mode-light"}`}
    >
      {helpOpen && <HelpResourcesModal onClose={() => setHelpOpen(false)} />}
      {changelogOpen && (
        <window.UAChangelogModal onClose={() => setChangelogOpen(false)} />
      )}
      {clearOpen && (
        <ClearHistoryDialog
          onClose={() => setClearOpen(false)}
          onCleared={() => {
            setClearOpen(false);
            setOffset(0);
            setRefresh((value) => value + 1);
          }}
        />
      )}
      {openItem !== null && (
        <HistoryDetail
          itemId={openItem}
          onClose={() => setOpenItem(null)}
          onDeleted={() => {
            setOpenItem(null);
            setRefresh((value) => value + 1);
          }}
        />
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
      <main className="mx-auto max-w-[1280px] p-4 sm:p-6 lg:p-8">
        <header className="ua-stats-header flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest opacity-60">
              Upload Assistant
            </p>
            <h1 className="mt-1 text-2xl font-bold">History</h1>
            <p className="mt-1 text-sm opacity-60">
              Every release processed on this installation, newest first. Debug
              runs are not recorded.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 self-start sm:self-auto">
            {["csv", "json"].map((format) => (
              <button
                key={format}
                type="button"
                onClick={() => exportHistory(format)}
                disabled={!total || Boolean(exporting)}
                title={`Download the entries matching the filters as ${format.toUpperCase()}`}
                className="ua-stats-control inline-flex min-w-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm disabled:opacity-40"
              >
                <AssetIcon name="download" className="h-4 w-4" />
                {exporting === format ? "Exporting…" : format.toUpperCase()}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setClearOpen(true)}
              disabled={!totalAll && !filtersActive && !outcome}
              className="ua-config-danger-button inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm disabled:opacity-40"
            >
              <AssetIcon name="trash-2" className="h-4 w-4" />
              Clear history
            </button>
          </div>
        </header>
        {exportError && (
          <p role="alert" className="mt-3 text-sm text-red-500">
            {exportError}
          </p>
        )}

        {data && data.enabled === false && (
          <div
            className="ua-config-warning mt-4 rounded-xl border p-3 text-sm"
            role="status"
          >
            Recording is off. Enable
            <code className="mx-1 font-semibold">history_enabled</code>
            in{" "}
            <a href={`${APP_BASE}/config`} className="underline">
              Configuration
            </a>{" "}
            to add new entries. Stored entries are still shown.
          </div>
        )}

        <section
          className="ua-stats-panel mt-5 rounded-xl p-3 sm:p-4"
          aria-label="Filters"
        >
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <label className="relative sm:col-span-2">
              <span className="sr-only">Search</span>
              <AssetIcon
                name="search"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 opacity-50"
              />
              <input
                type="search"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search name, title, group, path or ID"
                aria-describedby="history-search-help"
                className="ua-stats-control w-full rounded-xl pl-9 pr-3 text-sm"
              />
            </label>
            <select
              aria-label="Category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              className="ua-stats-control w-full min-w-0 rounded-xl px-3 text-sm"
            >
              <option value="">All categories</option>
              {(data?.facets?.categories || []).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
            <label className="ua-stats-control flex min-w-0 cursor-pointer items-center gap-2 rounded-xl px-3 text-sm">
              <input
                type="checkbox"
                checked={withRequests}
                onChange={(event) => setWithRequests(event.target.checked)}
                className="h-4 w-4 accent-[var(--ua-copper-bright)]"
              />
              With request matches
            </label>
            <select
              aria-label="Tracker"
              value={tracker}
              onChange={(event) => setTracker(event.target.value)}
              className="ua-stats-control w-full min-w-0 rounded-xl px-3 text-sm"
            >
              <option value="">All trackers</option>
              {(data?.facets?.trackers || []).map((value) => (
                <option key={value} value={value}>
                  {trackerLabel(data?.tracker_names, value)}
                </option>
              ))}
            </select>
            <select
              aria-label="Tracker result"
              value={trackerStatus}
              onChange={(event) => setTrackerStatus(event.target.value)}
              className="ua-stats-control w-full min-w-0 rounded-xl px-3 text-sm"
            >
              {TRACKER_STATUS_FILTERS.map(([value, label]) => (
                <option key={value} value={value}>
                  {tracker && value ? `${label} on this tracker` : label}
                </option>
              ))}
            </select>
            <label className="ua-stats-control flex min-w-0 items-center gap-2 rounded-xl px-3 text-sm">
              <span className="opacity-60">From</span>
              <input
                type="date"
                value={dateFrom}
                max={dateTo || undefined}
                onChange={(event) => setDateFrom(event.target.value)}
                className="min-w-0 flex-1 bg-transparent"
              />
            </label>
            <label className="ua-stats-control flex min-w-0 items-center gap-2 rounded-xl px-3 text-sm">
              <span className="opacity-60">To</span>
              <input
                type="date"
                value={dateTo}
                min={dateFrom || undefined}
                onChange={(event) => setDateTo(event.target.value)}
                className="min-w-0 flex-1 bg-transparent"
              />
            </label>
          </div>
          <p id="history-search-help" className="mt-2 text-xs opacity-60">
            IMDb (tt0123456), TMDb (movie/42), ISBN, ASIN and Open Library IDs
            match as typed. For other IDs, put the provider first: tvdb:12345,
            tmdb:42, tvmaze:, mal:, douban:, igdb:, discogs:.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <div
              className="ua-stats-period-group flex flex-wrap items-center rounded-xl p-1"
              role="group"
              aria-label="Outcome"
            >
              {OUTCOMES.map(([value, label]) => (
                <button
                  key={value || "all"}
                  type="button"
                  onClick={() => setOutcome(value)}
                  aria-pressed={outcome === value}
                  className={`ua-stats-period-button rounded-lg px-3 text-sm ${outcome === value ? "ua-stats-period-button-active font-semibold shadow-sm" : "opacity-75"}`}
                >
                  {label}
                  <span className="ml-1.5 tabular-nums opacity-60">
                    {value ? counts[value] || 0 : totalAll}
                  </span>
                </button>
              ))}
            </div>
            {(filtersActive || outcome) && (
              <button
                type="button"
                onClick={resetFilters}
                className="rounded-lg px-3 py-2 text-sm underline-offset-2 opacity-75 hover:underline"
              >
                Reset filters
              </button>
            )}
          </div>
        </section>

        <section className="mt-5" aria-live="polite" aria-busy={loading}>
          {error && (
            <p
              role="alert"
              className="ua-stats-panel rounded-xl p-4 text-sm text-red-500"
            >
              {error}
            </p>
          )}
          {!error && data && data.items.length === 0 && (
            <div className="ua-stats-panel rounded-xl p-8 text-center">
              <AssetIcon
                name="archive"
                className="mx-auto h-8 w-8 opacity-50"
              />
              <p className="mt-3 font-semibold">
                {filtersActive || outcome
                  ? "No entries match these filters"
                  : "No uploads recorded yet"}
              </p>
              <p className="mt-1 text-sm opacity-60">
                {filtersActive || outcome
                  ? "Change or reset the filters to see more."
                  : "Entries appear here when a release finishes processing."}
              </p>
            </div>
          )}
          {data && data.items.length > 0 && (
            <>
              <ul
                className="ua-stats-panel divide-y rounded-xl"
                style={{ opacity: loading ? 0.6 : 1 }}
              >
                {data.items.map((item) => (
                  <HistoryRow
                    key={item.id}
                    item={item}
                    trackerNames={data.tracker_names}
                    onOpen={setOpenItem}
                  />
                ))}
              </ul>
              <nav
                className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm"
                aria-label="Pages"
              >
                <span className="opacity-70">
                  {offset + 1}–{Math.min(offset + data.items.length, total)} of{" "}
                  {total}
                </span>
                <span className="flex gap-2">
                  <button
                    type="button"
                    disabled={offset === 0 || loading}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    className="ua-stats-control inline-flex min-w-0 items-center gap-1 rounded-xl px-3 disabled:opacity-40"
                  >
                    <AssetIcon name="chevron-left" className="h-4 w-4" />
                    Newer
                  </button>
                  <button
                    type="button"
                    disabled={offset + PAGE_SIZE >= total || loading}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                    className="ua-stats-control inline-flex min-w-0 items-center gap-1 rounded-xl px-3 disabled:opacity-40"
                  >
                    Older
                    <AssetIcon name="chevron-right" className="h-4 w-4" />
                  </button>
                </span>
              </nav>
            </>
          )}
          {!data && !error && loading && (
            <p className="ua-stats-panel rounded-xl p-6 text-center text-sm opacity-60">
              Loading…
            </p>
          )}
        </section>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<HistoryApp />);
