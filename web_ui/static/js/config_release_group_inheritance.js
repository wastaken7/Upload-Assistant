/** Resolve the value a release-group field uses when its own override is off. */
(() => {
  const normalizeName = (name) =>
    [...String(name).trim().replace(/^-+/, "")]
      // Match expanded case variants (e.g. ß/SS), while retaining dotless i
      // as a distinct letter, consistent with Python's casefold comparison.
      .map((char) =>
        char === "\u0131"
          ? char
          : char.toLowerCase().toUpperCase().toLowerCase(),
      )
      .join("");

  const resolve = ({
    name,
    key,
    pathParts,
    defaults = {},
    globalGroups = {},
    trackerItems = [],
    pendingChanges = new Map(),
  }) => {
    const defaultValue = String(defaults[key] ?? "");
    if (pathParts[0] !== "TRACKERS") {
      return {
        value: defaultValue,
        preview: "",
        placeholder: "Varies by tracker",
        inheritedLabel: "Uses tracker/DEFAULT settings",
        overrideLabel: "Overrides tracker/DEFAULT settings",
      };
    }

    const result = (value, source) => ({
      value: String(value),
      preview: String(value),
      placeholder: "",
      inheritedLabel: `Inherits ${source}`,
      overrideLabel: `Overrides ${source}`,
    });

    if (globalGroups === null) {
      return {
        value: "",
        preview: "",
        placeholder: "Check global release-group settings",
        inheritedLabel: "Inherited source unavailable",
        overrideLabel: "Overrides inherited text",
      };
    }
    for (const [groupName, fields] of Object.entries(globalGroups)) {
      if (
        normalizeName(groupName) === normalizeName(name) &&
        Object.hasOwn(fields, key) &&
        fields[key] !== null
      ) {
        return result(fields[key], "global release-group override");
      }
    }

    const pending = pendingChanges.get([...pathParts, key].join("/"));
    const item = trackerItems.find((entry) => entry.key === key);
    const hasTrackerValue = pending
      ? !pending.removeKey && pending.value != null
      : item?.source === "config" && item.value != null;
    if (hasTrackerValue) {
      return result(
        pending ? pending.value : item.value,
        "tracker-specific DEFAULT",
      );
    }
    return result(defaultValue, "DEFAULT");
  };

  window.UAReleaseGroupInheritance = { normalizeName, resolve };
})();
