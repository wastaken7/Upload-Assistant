const test = require("node:test");
const assert = require("node:assert/strict");

global.window = {};
require("../web_ui/static/js/shared_utils.js");

const filterTrackerChoices = global.window.filterUATrackerChoices;

test("tracker selector defaults to configured trackers and preserves selections", () => {
  const trackers = [
    { name: "AITHER" },
    { name: "BLUTOPIA" },
    { name: "UNCONFIGURED" },
  ];

  assert.deepEqual(
    filterTrackerChoices(
      trackers,
      new Set(["AITHER"]),
      new Set(["BLUTOPIA"]),
      false,
    ).map((tracker) => tracker.name),
    ["AITHER", "BLUTOPIA"],
  );
  assert.deepEqual(filterTrackerChoices(trackers, [], [], true), trackers);
});
