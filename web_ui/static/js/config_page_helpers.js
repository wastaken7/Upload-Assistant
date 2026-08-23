(function exposeConfigPageHelpers(root, factory) {
  const helpers = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = helpers;
  }
  if (root) {
    root.UAConfigPageHelpers = helpers;
  }
})(
  typeof globalThis !== "undefined" ? globalThis : this,
  function buildHelpers() {
    const formatDisplayLabel = (key) => {
      if (!key) return key;
      return String(key)
        .split(/[_\s]+/)
        .map((word) =>
          word.includes("*")
            ? word.toUpperCase()
            : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase(),
        )
        .join(" ");
    };

    const getAvailableTrackers = (item, trackerCatalog = []) => {
      if (Array.isArray(trackerCatalog) && trackerCatalog.length > 0) {
        const catalogTrackers = trackerCatalog
          .map((tracker) =>
            typeof tracker === "string" ? tracker : tracker && tracker.name,
          )
          .filter(Boolean);
        if (catalogTrackers.length > 0) return catalogTrackers;
      }
      if (!item || !Array.isArray(item.help) || item.help.length === 0) {
        return [];
      }
      const helpText = item.help.join(" ");
      const match = helpText.match(
        /available trackers?:\s*(.*?)(?:only add the trackers|$)/i,
      );
      if (!match) return [];
      return match[1]
        .split(",")
        .map((tracker) => tracker.trim())
        .filter(Boolean);
    };

    const getTrackerCatalogForSection = (trackerCatalog, subsections) => {
      const catalogTrackers = (
        Array.isArray(trackerCatalog) ? trackerCatalog : []
      ).filter(
        (tracker) =>
          (typeof tracker === "string" && tracker.trim()) ||
          (tracker && typeof tracker.name === "string" && tracker.name.trim()),
      );
      if (catalogTrackers.length > 0) return catalogTrackers;
      return (Array.isArray(subsections) ? subsections : [])
        .map((subsection) =>
          typeof subsection === "string"
            ? subsection
            : subsection && subsection.key,
        )
        .filter(Boolean);
    };

    const torrentClientTypeLabels = {
      qbit: "qBitTorrent",
      rtorrent: "rTorrent",
      deluge: "Deluge",
      transmission: "Transmission",
      watch: "Watch folder",
    };

    const getTorrentClientTypeLabel = (type) =>
      torrentClientTypeLabels[String(type || "").toLowerCase()] ||
      formatDisplayLabel(type);

    const getTorrentClientInstanceLabel = (key) => {
      const original = String(key || "");
      if (!original.includes("_") && /[A-Z]/.test(original.slice(1))) {
        return original;
      }
      return original
        .split("_")
        .map(
          (part) =>
            torrentClientTypeLabels[part.toLowerCase()] ||
            (part.toLowerCase() === "qbittorrent"
              ? "qBitTorrent"
              : formatDisplayLabel(part)),
        )
        .join(" ");
    };

    const sortTrackerNames = (
      trackers,
      getDisplayName = (tracker) => tracker,
    ) =>
      (Array.isArray(trackers) ? trackers : []).slice().sort((left, right) => {
        const leftLabel = getDisplayName(left) || left;
        const rightLabel = getDisplayName(right) || right;
        return String(leftLabel).localeCompare(String(rightLabel), undefined, {
          sensitivity: "base",
          numeric: true,
        });
      });

    const metadataCacheServiceLabels = {
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

    const metadataCacheServiceCategories = [
      {
        label: "Film, TV & Anime",
        keys: ["tmdb", "imdb", "tvdb", "tvmaze", "anilist", "douban", "thexem"],
      },
      { label: "Games", keys: ["igdb", "steam"] },
      {
        label: "Books & Audiobooks",
        keys: ["google_books", "openlibrary", "myanonamouse"],
      },
      { label: "Music", keys: ["musicbrainz", "discogs"] },
    ];

    const getMetadataCacheServiceLabel = (key) =>
      metadataCacheServiceLabels[String(key || "").toLowerCase()] ||
      formatDisplayLabel(key);

    const groupMetadataCacheServices = (services) => {
      const serviceItems = Array.isArray(services) ? services : [];
      const byKey = new Map(
        serviceItems.map((service) => [
          String(service.key).toLowerCase(),
          service,
        ]),
      );
      const knownKeys = new Set(
        metadataCacheServiceCategories.flatMap((category) => category.keys),
      );
      const groups = metadataCacheServiceCategories
        .map((category) => ({
          label: category.label,
          items: category.keys.map((key) => byKey.get(key)).filter(Boolean),
        }))
        .filter((category) => category.items.length > 0);
      const otherItems = serviceItems.filter(
        (service) => !knownKeys.has(String(service.key).toLowerCase()),
      );
      if (otherItems.length > 0) {
        groups.push({ label: "Other", items: otherItems });
      }
      return groups;
    };

    const defaultSubsectionLabels = new Map([
      ["MAIN SETTINGS", "Main"],
      ["METADATA CACHE", "Metadata"],
      ["TRACKER METADATA CACHE", "Metadata"],
      ["GETTING METADATA", "Metadata"],
      ["IMAGE HOSTING SETTINGS", "Image Hosting"],
      ["SCREENSHOT HANDLING", "Screenshot Handling"],
      ["DESCRIPTION SETTINGS", "Description"],
      ["CLIENT SETUP", "Client Setup"],
      ["ARR* INTEGRATION SETTINGS", "ARR* Integration"],
      ["TORRENT CREATION", "Torrent Creation"],
      ["POST UPLOAD", "Post Upload"],
    ]);

    const getSubsectionTabLabel = (item, sectionName) => {
      let subsectionName = null;
      if (item && item.subsection && typeof item.subsection === "string") {
        subsectionName = item.subsection;
      } else if (item && item.subsection === true) {
        subsectionName = item.key;
      }
      if (!subsectionName) return null;
      const normalizedName = String(subsectionName).toUpperCase();
      if (
        String(sectionName).toUpperCase() === "DEFAULT" &&
        defaultSubsectionLabels.has(normalizedName)
      ) {
        return defaultSubsectionLabels.get(normalizedName);
      }
      return formatDisplayLabel(subsectionName);
    };

    const getSubTabId = (label) =>
      String(label).toLowerCase().replace(/\s+/g, "-");

    const getSubTabsForSection = (section) => {
      if (Array.isArray(section.client_types)) {
        return section.client_types.map((type) => {
          return { id: type, label: getTorrentClientTypeLabel(type) };
        });
      }

      const subTabs = [];
      const seenSubsections = new Set();
      for (const item of section.items || []) {
        const subsectionName = getSubsectionTabLabel(item, section.section);
        if (subsectionName && !seenSubsections.has(subsectionName)) {
          seenSubsections.add(subsectionName);
          subTabs.push({
            id: getSubTabId(subsectionName),
            label: subsectionName,
          });
        }
      }

      if (
        subTabs.length > 0 &&
        (section.items || []).some((item) => !item.subsection)
      ) {
        subTabs.unshift({ id: "general", label: "General" });
      }
      return subTabs;
    };

    const getMergedDefaultSubsectionHeading = (item, pathParts) => {
      if (
        !item ||
        item.subsection !== true ||
        !Array.isArray(pathParts) ||
        pathParts.length !== 1 ||
        pathParts[0] !== "DEFAULT" ||
        !["METADATA CACHE", "TRACKER METADATA CACHE"].includes(item.key)
      ) {
        return null;
      }
      return formatDisplayLabel(item.key);
    };

    const usesConfigSettingsPanels = (pathParts) =>
      Array.isArray(pathParts) &&
      pathParts.length === 1 &&
      ["DEFAULT", "IMAGES", "USENET"].includes(pathParts[0]);

    const hasMeaningfulOverride = (item) =>
      item.overridden === true ||
      (Array.isArray(item.children) &&
        item.children.some((child) => hasMeaningfulOverride(child)));

    const filterItemsForSubTab = (section, activeSubTab) =>
      (section.items || []).filter((item) => {
        if (section.section === "TORRENT_CLIENTS") {
          const clientTypeItem =
            Array.isArray(item.children) &&
            item.children.find((child) => child.key === "torrent_client");
          return clientTypeItem && clientTypeItem.value === activeSubTab;
        }
        if (activeSubTab === "general") {
          return !item.subsection;
        }
        const subsectionName = getSubsectionTabLabel(item, section.section);
        return (
          subsectionName !== null &&
          getSubTabId(subsectionName) === activeSubTab
        );
      });

    const getConfiguredTrackerNames = (subsections, selectedDefaults) => {
      const configured = new Set(selectedDefaults || []);
      for (const subsection of subsections || []) {
        if (
          Array.isArray(subsection.children) &&
          subsection.children.some((child) => hasMeaningfulOverride(child))
        ) {
          configured.add(String(subsection.key).toUpperCase());
        }
      }
      return Array.from(configured);
    };

    return {
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
      hasMeaningfulOverride,
      sortTrackerNames,
      usesConfigSettingsPanels,
    };
  },
);
