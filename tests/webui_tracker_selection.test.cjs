const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const babel = require("../web_ui/static/js/node_modules/@babel/core");

const source = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/app.js"),
  "utf8",
);
const ast = babel.parseSync(source, { parserOpts: { plugins: ["jsx"] } });
const functions = new Map();
function walk(node) {
  if (!node || typeof node !== "object") return;
  if (node.type === "VariableDeclarator" && node.id.type === "Identifier")
    functions.set(node.id.name, node.init);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach(walk);
    else if (value && typeof value === "object") walk(value);
  }
}
walk(ast);
const context = vm.createContext({
  Set,
  trackerAliases: { ATH: "AITHER", BLU: "BLUTOPIA", FOX: "AITHER" },
});
for (const name of [
  "extractArgValue",
  "parseTrackersFromArgs",
  "syncTrackersToArgs",
]) {
  const node = functions.get(name);
  vm.runInContext(
    `var ${name} = ${source.slice(node.start, node.end)}`,
    context,
  );
}
const selected = (args, defaults = []) =>
  [...context.parseTrackersFromArgs(args, new Set(defaults))].sort();

test("configured aliases, built-in aliases and canonical names highlight canonical cards", () => {
  for (const args of [
    "-tk ath,BLU",
    '--trackers="ATH,BLUTOPIA"',
    "--trackers 'aither,blu'",
    "-tk=ATH,BLU",
  ]) {
    assert.deepEqual(selected(args), ["AITHER", "BLUTOPIA"]);
  }
  assert.deepEqual(selected("-tk ATH,AITHER,FOX"), ["AITHER"]);
});

test("default lists and similarly named options do not use configured aliases", () => {
  assert.deepEqual(selected("--trackers-remove ATH", ["BLUTOPIA"]), [
    "BLUTOPIA",
  ]);
  assert.deepEqual(selected("--debug", ["ATH"]), ["ATH"]);
  assert.deepEqual(selected("-tk", ["AITHER"]), []);
});

test("explicit aliases supplied by a newly loaded catalog take effect immediately", () => {
  const args = "-tk NEW";
  assert.deepEqual(
    [...context.parseTrackersFromArgs(args, new Set(), { NEW: "AITHER" })],
    ["AITHER"],
  );
  assert.deepEqual(
    [...context.parseTrackersFromArgs("-tk ATH", new Set(), { NEW: "AITHER" })],
    ["ATH"],
  );
  assert.equal(args, "-tk NEW");
});

test("card toggles after alias input write canonical names and preserve other arguments", () => {
  const args = "--debug -tk ATH";
  const next = context.parseTrackersFromArgs(args, new Set());
  next.add("BLUTOPIA");
  const updated = context.syncTrackersToArgs(args, next, new Set());
  assert.equal(updated, '--debug -tk "AITHER,BLUTOPIA"');
  assert.deepEqual(selected(updated), ["AITHER", "BLUTOPIA"]);
  assert.equal(args, "--debug -tk ATH");
});

test("unknown identifiers never resolve through Object.prototype", () => {
  assert.deepEqual(selected("-tk constructor,UNKNOWN"), [
    "CONSTRUCTOR",
    "UNKNOWN",
  ]);
});

/** Run the real bulk-selection handler with isolated selection and argument state. */
function groupSelection(args, selectedNames, defaults = [], running = false) {
  const scope = vm.createContext({
    Set,
    customArgs: args,
    selectedTrackers: new Set(selectedNames),
    defaultTrackers: new Set(defaults),
    isExecuting: running,
    updates: 0,
  });
  scope.setSelectedTrackers = (next) => {
    scope.selectedTrackers = next;
    scope.updates++;
  };
  scope.setCustomArgs = (update) => {
    scope.customArgs = update(scope.customArgs);
  };
  for (const name of ["syncTrackersToArgs", "handleTrackerGroupSelection"]) {
    const node = functions.get(name);
    vm.runInContext(
      `var ${name} = ${source.slice(node.start, node.end)}`,
      scope,
    );
  }
  return scope;
}

test("group selection changes only its supplied trackers and keeps other command options", () => {
  const page = groupSelection('--debug --category movie -tk "ATH,ULCX"', [
    "AITHER",
    "ULCX",
  ]);
  const group = ["AITHER", "BLUTOPIA", "LST"];
  page.handleTrackerGroupSelection(group, true);
  assert.deepEqual([...page.selectedTrackers].sort(), [
    "AITHER",
    "BLUTOPIA",
    "LST",
    "ULCX",
  ]);
  assert.deepEqual(selected(page.customArgs), [
    "AITHER",
    "BLUTOPIA",
    "LST",
    "ULCX",
  ]);
  assert.ok(page.customArgs.includes("--debug --category movie"));
  page.handleTrackerGroupSelection(group, false);
  assert.deepEqual([...page.selectedTrackers], ["ULCX"]);
  assert.deepEqual(selected(page.customArgs), ["ULCX"]);
  assert.ok(page.customArgs.includes("--debug --category movie"));
});

test("bulk selection returns to defaults and explicitly represents selecting no trackers", () => {
  const group = ["AITHER", "BLUTOPIA"];
  const page = groupSelection("--debug -tk ATH", ["AITHER"], group);
  page.handleTrackerGroupSelection(group, true);
  assert.equal(page.customArgs, "--debug");
  assert.deepEqual(selected(page.customArgs, group), group);
  page.handleTrackerGroupSelection(group, false);
  assert.equal(page.customArgs, '--debug -tk ""');
  assert.deepEqual(selected(page.customArgs, group), []);
});

test("group controls cannot alter the upload selection during a run", () => {
  const args = "--debug -tk AITHER";
  const page = groupSelection(args, ["AITHER"], [], true);
  page.handleTrackerGroupSelection(["AITHER", "BLUTOPIA"], true);
  page.handleTrackerGroupSelection(["AITHER"], false);
  assert.equal(page.updates, 0);
  assert.equal(page.customArgs, args);
  assert.deepEqual([...page.selectedTrackers], ["AITHER"]);
});
