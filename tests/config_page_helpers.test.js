const test = require("node:test");
const assert = require("node:assert/strict");

const {
  filterItemsForSubTab,
  getAvailableTrackers,
  getConfiguredTrackerNames,
  getMetadataCacheServiceLabel,
  getMergedDefaultSubsectionHeading,
  getSubTabsForSection,
  getTrackerCatalogForSection,
  getTorrentClientInstanceLabel,
  getTorrentClientTypeLabel,
  groupMetadataCacheServices,
  sortTrackerNames,
  usesConfigSettingsPanels,
} = require("../web_ui/static/js/config_page_helpers.js");

test("tracker catalog is canonical and multiline help remains a complete fallback", () => {
  const item = {
    help: [
      "Available tracker: AITHER, BLUTOPIA,",
      "HDBITS, PASSTHEPOPCORN",
      "Only add the trackers you use regularly",
    ],
  };

  assert.deepEqual(getAvailableTrackers(item), [
    "AITHER",
    "BLUTOPIA",
    "HDBITS",
    "PASSTHEPOPCORN",
  ]);
  assert.deepEqual(
    getAvailableTrackers(item, [
      { name: "AITHER" },
      { name: "HDBITS" },
      { name: "NEWTRACKER" },
    ]),
    ["AITHER", "HDBITS", "NEWTRACKER"],
  );
});

test("TRACKERS falls back to its config subsections when the catalog is unavailable", () => {
  const subsections = [{ key: "AITHER" }, { key: "BLUTOPIA" }];
  const fallbackCatalog = getTrackerCatalogForSection([], subsections);

  assert.deepEqual(fallbackCatalog, ["AITHER", "BLUTOPIA"]);
  assert.deepEqual(getAvailableTrackers({ help: [] }, fallbackCatalog), [
    "AITHER",
    "BLUTOPIA",
  ]);
  assert.deepEqual(
    getAvailableTrackers({ help: ["Available tracker: AITHER, BLUTOPIA"] }, [
      { display_name: "Malformed catalog entry" },
    ]),
    ["AITHER", "BLUTOPIA"],
  );
});

test("tracker names are sorted in the frontend by their displayed labels", () => {
  const fallbackNames = ["ZENITH", "AITHER", "BLUTOPIA"];

  assert.deepEqual(sortTrackerNames(fallbackNames), [
    "AITHER",
    "BLUTOPIA",
    "ZENITH",
  ]);
  assert.deepEqual(
    sortTrackerNames(["FIRST", "SECOND"], (tracker) =>
      tracker === "FIRST" ? "Zulu" : "Alpha",
    ),
    ["SECOND", "FIRST"],
  );
  assert.deepEqual(fallbackNames, ["ZENITH", "AITHER", "BLUTOPIA"]);
});

test("metadata cache services get readable labels and domain groups", () => {
  const services = [
    { key: "discogs" },
    { key: "tmdb" },
    { key: "custom_provider" },
    { key: "google_books" },
    { key: "igdb" },
  ];

  assert.equal(getMetadataCacheServiceLabel("tmdb"), "TMDB");
  assert.equal(getMetadataCacheServiceLabel("google_books"), "Google Books");
  assert.equal(
    getMetadataCacheServiceLabel("custom_provider"),
    "Custom Provider",
  );
  assert.deepEqual(
    groupMetadataCacheServices(services).map((group) => ({
      label: group.label,
      keys: group.items.map((item) => item.key),
    })),
    [
      { label: "Film, TV & Anime", keys: ["tmdb"] },
      { label: "Games", keys: ["igdb"] },
      { label: "Books & Audiobooks", keys: ["google_books"] },
      { label: "Music", keys: ["discogs"] },
      { label: "Other", keys: ["custom_provider"] },
    ],
  );
});

test("DEFAULT gets a General tab without losing Client Setup", () => {
  const section = {
    section: "DEFAULT",
    items: [
      { key: "screens" },
      { key: "injecting_client_list", subsection: "CLIENT SETUP" },
      { key: "searching_client_list", subsection: "CLIENT SETUP" },
    ],
  };
  const tabs = getSubTabsForSection(section);

  assert.deepEqual(tabs, [
    { id: "general", label: "General" },
    { id: "client-setup", label: "Client Setup" },
  ]);
  assert.deepEqual(
    filterItemsForSubTab(section, "general").map((item) => item.key),
    ["screens"],
  );
  assert.deepEqual(
    filterItemsForSubTab(section, "client-setup").map((item) => item.key),
    ["injecting_client_list", "searching_client_list"],
  );
});

test("DEFAULT comment-heading groups become ordered tabs without a redundant General tab", () => {
  const section = {
    section: "DEFAULT",
    items: [
      { key: "MAIN SETTINGS", children: [], subsection: true },
      { key: "METADATA CACHE", children: [], subsection: true },
      { key: "TRACKER METADATA CACHE", children: [], subsection: true },
      { key: "IMAGE HOSTING SETTINGS", children: [], subsection: true },
      { key: "GETTING METADATA", children: [], subsection: true },
      { key: "SCREENSHOT HANDLING", children: [], subsection: true },
      { key: "DESCRIPTION SETTINGS", children: [], subsection: true },
      {
        key: "CLIENT SETUP",
        children: [{ key: "default_torrent_client" }],
        subsection: true,
      },
      { key: "injecting_client_list", subsection: "CLIENT SETUP" },
      { key: "ARR* INTEGRATION SETTINGS", children: [], subsection: true },
      { key: "TORRENT CREATION", children: [], subsection: true },
      { key: "POST UPLOAD", children: [], subsection: true },
    ],
  };

  assert.deepEqual(getSubTabsForSection(section), [
    { id: "main", label: "Main" },
    { id: "metadata", label: "Metadata" },
    { id: "image-hosting", label: "Image Hosting" },
    { id: "screenshot-handling", label: "Screenshot Handling" },
    { id: "description", label: "Description" },
    { id: "client-setup", label: "Client Setup" },
    { id: "arr*-integration", label: "ARR* Integration" },
    { id: "torrent-creation", label: "Torrent Creation" },
    { id: "post-upload", label: "Post Upload" },
  ]);
  assert.deepEqual(
    filterItemsForSubTab(section, "metadata").map((item) => item.key),
    ["METADATA CACHE", "TRACKER METADATA CACHE", "GETTING METADATA"],
  );
  assert.deepEqual(
    filterItemsForSubTab(section, "client-setup").map((item) => item.key),
    ["CLIENT SETUP", "injecting_client_list"],
  );
});

test("merged Metadata tab preserves its two cache section headings", () => {
  assert.equal(
    getMergedDefaultSubsectionHeading(
      { key: "METADATA CACHE", subsection: true },
      ["DEFAULT"],
    ),
    "Metadata Cache",
  );
  assert.equal(
    getMergedDefaultSubsectionHeading(
      { key: "TRACKER METADATA CACHE", subsection: true },
      ["DEFAULT"],
    ),
    "Tracker Metadata Cache",
  );
  assert.equal(
    getMergedDefaultSubsectionHeading(
      { key: "GETTING METADATA", subsection: true },
      ["DEFAULT"],
    ),
    null,
  );
  assert.equal(
    getMergedDefaultSubsectionHeading(
      { key: "METADATA CACHE", subsection: true },
      ["TRACKERS"],
    ),
    null,
  );
});

test("settings panels are limited to the intended top-level config sections", () => {
  assert.equal(usesConfigSettingsPanels(["DEFAULT"]), true);
  assert.equal(usesConfigSettingsPanels(["IMAGES"]), true);
  assert.equal(usesConfigSettingsPanels(["USENET"]), true);
  assert.equal(usesConfigSettingsPanels(["TRACKERS"]), false);
  assert.equal(usesConfigSettingsPanels(["TORRENT_CLIENTS"]), false);
  assert.equal(usesConfigSettingsPanels(["DEFAULT", "nested"]), false);
});

test("torrent client types remain their own tabs", () => {
  assert.deepEqual(
    getSubTabsForSection({ client_types: ["qbit", "rtorrent"], items: [] }),
    [
      { id: "qbit", label: "qBitTorrent" },
      { id: "rtorrent", label: "rTorrent" },
    ],
  );
});

test("torrent client instances get readable accordion labels", () => {
  assert.equal(getTorrentClientTypeLabel("qbit"), "qBitTorrent");
  assert.equal(getTorrentClientTypeLabel("watch"), "Watch folder");
  assert.equal(
    getTorrentClientInstanceLabel("qbittorrent_searching"),
    "qBitTorrent Searching",
  );
  assert.equal(getTorrentClientInstanceLabel("WhatBox"), "WhatBox");
});

test("copied example fields are not treated as configured tracker overrides", () => {
  const subsections = [
    {
      key: "AITHER",
      children: [{ key: "api_key", source: "config", overridden: false }],
    },
    {
      key: "BLUTOPIA",
      children: [{ key: "api_key", source: "config", overridden: true }],
    },
  ];

  assert.deepEqual(
    getConfiguredTrackerNames(subsections, new Set(["AITHER"])).sort(),
    ["AITHER", "BLUTOPIA"],
  );
  assert.deepEqual(getConfiguredTrackerNames(subsections, new Set()), [
    "BLUTOPIA",
  ]);
});
