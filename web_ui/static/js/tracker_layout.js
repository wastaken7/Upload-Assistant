// Browser-local tracker organisation. Upload selection and CLI order stay separate.
(() => {
  const STORAGE_KEY = "ua_tracker_layout_v1";
  const PINNED = "pinned";
  const UNGROUPED = "ungrouped";
  const names = (value) => [
    ...new Set(
      Array.isArray(value)
        ? value.filter((name) => typeof name === "string" && name)
        : [],
    ),
  ];

  /** Validate saved groups and deduplicate membership without discarding unknown trackers. */
  const normalize = (value) => {
    const source = value && typeof value === "object" ? value : {};
    const groupIds = new Set([PINNED, UNGROUPED]);
    const assigned = new Set();
    const groups = [];
    for (const group of Array.isArray(source.groups) ? source.groups : []) {
      if (
        !group ||
        typeof group.id !== "string" ||
        !group.id ||
        groupIds.has(group.id)
      )
        continue;
      const name =
        typeof group.name === "string" ? group.name.trim().slice(0, 60) : "";
      if (!name) continue;
      groupIds.add(group.id);
      const trackers = names(group.trackers).filter((tracker) => {
        if (assigned.has(tracker)) return false;
        assigned.add(tracker);
        return true;
      });
      groups.push({ id: group.id, name, trackers });
    }
    return {
      pinned: names(source.pinned),
      groups,
      ungrouped: names(source.ungrouped).filter(
        (tracker) => !assigned.has(tracker),
      ),
    };
  };

  /** Restore browser preferences, falling back to an empty layout when storage fails. */
  const load = (storage) => {
    try {
      return normalize(JSON.parse(storage.get(STORAGE_KEY) || "null"));
    } catch (_error) {
      return normalize(null);
    }
  };

  /** Project visible trackers into ordered sections, showing each tracker once. */
  const sections = (layout, trackers) => {
    const catalog = new Map(trackers.map((tracker) => [tracker.name, tracker]));
    const pinned = new Set(layout.pinned);
    const assigned = new Set(layout.groups.flatMap((group) => group.trackers));
    const resolve = (order) =>
      order
        .filter((name) => catalog.has(name))
        .map((name) => catalog.get(name));
    const ungrouped = trackers.filter(
      (tracker) => !pinned.has(tracker.name) && !assigned.has(tracker.name),
    );
    const savedOrder = new Map(
      layout.ungrouped.map((name, index) => [name, index]),
    );
    ungrouped.sort(
      (a, b) =>
        (savedOrder.get(a.name) ?? Infinity) -
        (savedOrder.get(b.name) ?? Infinity),
    );
    return [
      { id: PINNED, name: "Pinned", trackers: resolve(layout.pinned) },
      ...layout.groups.map((group) => ({
        ...group,
        trackers: resolve(group.trackers.filter((name) => !pinned.has(name))),
      })),
      {
        id: UNGROUPED,
        name: layout.groups.length
          ? "Ungrouped"
          : layout.pinned.length
            ? "Other trackers"
            : "All trackers",
        trackers: ungrouped,
      },
    ];
  };

  /** Toggle a pin while retaining the original group and position for unpinning. */
  const togglePin = (layout, name) => ({
    ...layout,
    pinned: layout.pinned.includes(name)
      ? layout.pinned.filter((item) => item !== name)
      : [...layout.pinned, name],
  });

  /** Move or reorder a tracker without mutating the layout or losing hidden preferences. */
  const moveTracker = (layout, name, targetId, before = null, catalog = []) => {
    if (
      before === name ||
      ![PINNED, UNGROUPED, ...layout.groups.map((group) => group.id)].includes(
        targetId,
      )
    )
      return layout;
    const next = normalize(layout);
    const insert = (order) => {
      const result = order.filter((item) => item !== name);
      const index = before ? result.indexOf(before) : -1;
      result.splice(index < 0 ? result.length : index, 0, name);
      return result;
    };
    if (targetId === PINNED) {
      next.pinned = insert(next.pinned);
      return next;
    }
    // Include newly discovered trackers when reordering the default section.
    next.ungrouped = sections({ ...next, pinned: [] }, catalog)
      .find((section) => section.id === UNGROUPED)
      .trackers.map((tracker) => tracker.name)
      .concat(
        next.ungrouped.filter(
          (item) => !catalog.some((tracker) => tracker.name === item),
        ),
      );
    next.pinned = next.pinned.filter((item) => item !== name);
    next.ungrouped = next.ungrouped.filter((item) => item !== name);
    next.groups = next.groups.map((group) => ({
      ...group,
      trackers: group.trackers.filter((item) => item !== name),
    }));
    if (targetId === UNGROUPED) next.ungrouped = insert(next.ungrouped);
    else {
      const group = next.groups.find((item) => item.id === targetId);
      group.trackers = insert(group.trackers);
    }
    return next;
  };

  /** Reorder custom groups, ignoring stale or self-referential destinations. */
  const moveGroup = (layout, id, before = null) => {
    if (id === before || !layout.groups.some((group) => group.id === id))
      return layout;
    const groups = layout.groups.filter((group) => group.id !== id);
    const index = before
      ? groups.findIndex((group) => group.id === before)
      : -1;
    groups.splice(
      index < 0 ? groups.length : index,
      0,
      layout.groups.find((group) => group.id === id),
    );
    return { ...layout, groups };
  };

  /** Return a removed group's trackers to Ungrouped while preserving their pins. */
  const removeGroup = (layout, id) => ({
    ...layout,
    ungrouped: [
      ...layout.ungrouped,
      ...(layout.groups.find((group) => group.id === id)?.trackers || []),
    ],
    groups: layout.groups.filter((group) => group.id !== id),
  });

  const api = {
    STORAGE_KEY,
    PINNED,
    UNGROUPED,
    normalize,
    load,
    sections,
    togglePin,
    moveTracker,
    moveGroup,
    removeGroup,
  };
  if (typeof window !== "undefined") window.UATrackerLayout = api;
})();
