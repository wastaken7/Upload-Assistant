const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const shared = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/shared_utils.js"),
  "utf8",
);

function fixture(blockStorage = false) {
  const stored = new Map();
  const blocked = () => {
    throw new Error("Storage unavailable");
  };
  const context = vm.createContext({
    window: {},
    document: { documentElement: { dataset: {} } },
    localStorage: { getItem: () => null, setItem: () => {} },
    sessionStorage: {
      getItem: blockStorage ? blocked : (key) => stored.get(key) ?? null,
      setItem: blockStorage
        ? blocked
        : (key, value) => {
            stored.set(key, value);
          },
      removeItem: blockStorage ? blocked : (key) => stored.delete(key),
    },
  });
  vm.runInContext(shared, context);
  return { handoff: context.window.UAUploadHandoff, stored };
}

test("a handed-over path reaches the next Upload page load once", () => {
  const { handoff, stored } = fixture();

  assert.equal(handoff.offer("/media/Fictional Movie (2020)", 1000), true);
  assert.equal(handoff.take(2000), "/media/Fictional Movie (2020)");
  assert.equal(stored.size, 0);
  assert.equal(handoff.take(2000), "");
});

test("a handoff from an earlier, failed navigation expires", () => {
  const { handoff, stored } = fixture();

  handoff.offer("/media/Fictional Show", 0);

  assert.equal(handoff.take(61 * 1000), "");
  assert.equal(stored.size, 0);
});

test("blocked session storage is reported to the History page", () => {
  const { handoff } = fixture(true);

  assert.equal(handoff.offer("/media/Fictional Album"), false);
  assert.equal(handoff.take(), "");
});

test("an unreadable handoff is ignored", () => {
  const { handoff, stored } = fixture();

  stored.set("ua_history_upload_path", "not json");

  assert.equal(handoff.take(), "");
});
