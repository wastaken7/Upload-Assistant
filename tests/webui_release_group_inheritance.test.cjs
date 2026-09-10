const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const context = { window: {} };
vm.runInNewContext(
  fs.readFileSync(
    path.join(
      __dirname,
      "../web_ui/static/js/config_release_group_inheritance.js",
    ),
    "utf8",
  ),
  context,
);
const { normalizeName, resolve } = context.window.UAReleaseGroupInheritance;
const trackerScope = {
  name: "-MyGroup",
  key: "custom_signature",
  pathParts: ["TRACKERS", "AITHER"],
  defaults: { custom_signature: "Default signature" },
  trackerItems: [
    { key: "custom_signature", source: "config", value: "Tracker signature" },
  ],
};

test("matching global group text takes precedence over ordinary tracker text", () => {
  const inherited = resolve({
    ...trackerScope,
    globalGroups: { MYGROUP: { custom_signature: "Group signature" } },
  });
  assert.equal(inherited.value, "Group signature");
  assert.equal(inherited.preview, "Group signature");
  assert.equal(
    inherited.inheritedLabel,
    "Inherits global release-group override",
  );
  assert.equal(
    inherited.overrideLabel,
    "Overrides global release-group override",
  );
});

test("missing or null group fields fall through individually; empty text overrides", () => {
  for (const fields of [
    {},
    { custom_signature: null },
    { screenshot_header: "Screens" },
  ]) {
    const inherited = resolve({
      ...trackerScope,
      globalGroups: { MyGroup: fields },
    });
    assert.equal(inherited.value, "Tracker signature");
    assert.equal(inherited.inheritedLabel, "Inherits tracker-specific DEFAULT");
  }
  const blank = resolve({
    ...trackerScope,
    globalGroups: { MyGroup: { custom_signature: "" } },
  });
  assert.equal(blank.value, "");
  assert.equal(blank.inheritedLabel, "Inherits global release-group override");
});

test("pending tracker additions, edits and removals update the inherited source", () => {
  const key = "TRACKERS/AITHER/custom_signature";
  for (const value of ["Draft tracker signature", ""]) {
    const inherited = resolve({
      ...trackerScope,
      trackerItems: [],
      pendingChanges: new Map([[key, { value }]]),
    });
    assert.equal(inherited.value, value);
    assert.equal(inherited.inheritedLabel, "Inherits tracker-specific DEFAULT");
  }
  const removed = resolve({
    ...trackerScope,
    pendingChanges: new Map([
      [key, { value: "Tracker signature", removeKey: true }],
    ]),
  });
  assert.equal(removed.value, "Default signature");
  assert.equal(removed.inheritedLabel, "Inherits DEFAULT");
});

test("example-only and null tracker values do not become active overrides", () => {
  for (const trackerItems of [
    [],
    [{ key: "custom_signature", source: "example", value: "Example text" }],
    [{ key: "custom_signature", source: "config", value: null }],
  ]) {
    const inherited = resolve({ ...trackerScope, trackerItems });
    assert.equal(inherited.value, "Default signature");
    assert.equal(inherited.inheritedLabel, "Inherits DEFAULT");
  }
  assert.equal(
    resolve({
      ...trackerScope,
      trackerItems: [],
      defaults: { custom_signature: "" },
    }).value,
    "",
  );
});

test("group matching ignores case and leading hyphens, including expanded case variants", () => {
  for (const [left, right] of [
    [" --MyGroup ", "myGROUP"],
    ["Straße", "STRASSE"],
    ["ẞ", "ss"],
    ["Σ", "ς"],
  ]) {
    assert.equal(normalizeName(left), normalizeName(right));
    assert.equal(
      resolve({
        ...trackerScope,
        name: left,
        globalGroups: { [right]: { custom_signature: "Matched" } },
      }).value,
      "Matched",
    );
  }
  assert.notEqual(normalizeName("ı"), normalizeName("i"));
  assert.equal(
    resolve({
      ...trackerScope,
      name: "Renamed",
      globalGroups: { MyGroup: { custom_signature: "Old group" } },
    }).value,
    "Tracker signature",
  );
});

test("global editor does not claim one inherited value applies to every tracker", () => {
  const inherited = resolve({ ...trackerScope, pathParts: ["DEFAULT"] });
  assert.equal(inherited.preview, "");
  assert.equal(inherited.placeholder, "Varies by tracker");
  assert.equal(inherited.inheritedLabel, "Uses tracker/DEFAULT settings");
  assert.equal(inherited.overrideLabel, "Overrides tracker/DEFAULT settings");
  assert.equal(inherited.value, "Default signature");
});

test("invalid global group configuration does not display a misleading source", () => {
  const inherited = resolve({ ...trackerScope, globalGroups: null });
  assert.equal(inherited.inheritedLabel, "Inherited source unavailable");
  assert.equal(inherited.preview, "");
});
