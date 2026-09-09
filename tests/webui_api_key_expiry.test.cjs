const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/api_key_status.js"),
  "utf8",
);
class Clock extends Date {
  static now() {
    return Date.parse("2026-09-08T12:00:00Z");
  }
}
const sandbox = vm.createContext({ Date: Clock, window: {} });
vm.runInContext(source, sandbox);
const context = {
  apiKeyExpiryState: sandbox.window.UAApiKeyExpiry.state,
  apiKeyExpiryLabel: sandbox.window.UAApiKeyExpiry.label,
};

test("unknown and confirmed non-expiring keys remain distinct", () => {
  assert.equal(context.apiKeyExpiryState(null), "unknown");
  assert.equal(context.apiKeyExpiryLabel(null), "Expiry not reported");
  assert.equal(context.apiKeyExpiryState({ state: "no_expiry" }), "no_expiry");
  assert.equal(
    context.apiKeyExpiryLabel({ state: "no_expiry" }),
    "No expiry (reported by tracker)",
  );
});

test("badges age from the timestamp even if the cached state was valid", () => {
  assert.equal(
    context.apiKeyExpiryState({
      state: "valid",
      expires_at: "2026-09-08T11:59:59Z",
    }),
    "expired",
  );
  assert.equal(
    context.apiKeyExpiryState({
      state: "valid",
      expires_at: "2026-09-22T12:00:00Z",
    }),
    "expiring",
  );
  assert.equal(
    context.apiKeyExpiryState({
      state: "valid",
      expires_at: "2026-09-22T12:00:01Z",
    }),
    "valid",
  );
});

test("timezone offsets are respected and same-day expiry is explicit", () => {
  const value = { state: "expiring", expires_at: "2026-09-08T15:00:00+02:00" };
  assert.equal(context.apiKeyExpiryState(value), "expiring");
  assert.match(context.apiKeyExpiryLabel(value), /less than a day/);
  assert.match(
    context.apiKeyExpiryLabel({
      state: "valid",
      expires_at: "2026-09-08T12:00:00Z",
    }),
    /^Expired /,
  );
});

test("invalid dates never claim a healthy or non-expiring key", () => {
  const value = { state: "valid", expires_at: "not-a-date" };
  assert.equal(context.apiKeyExpiryState(value), "unknown");
  assert.equal(context.apiKeyExpiryLabel(value), "Expiry not reported");
});

test("compact labels retain the distinction between unknown and unlimited keys", () => {
  const label = context.apiKeyExpiryLabel;
  assert.equal(label(null, true), "Expiry not reported");
  assert.equal(label({ state: "no_expiry" }, true), "Does not expire");
  assert.equal(
    label({ expires_at: "2026-09-13T12:00:00Z" }, true),
    "Expires in 5 days",
  );
  assert.equal(
    label({ expires_at: "2026-09-08T13:00:00Z" }, true),
    "Expires in less than a day",
  );
  assert.match(
    label({ expires_at: "2026-09-08T11:00:00Z" }, true),
    /^Expired /,
  );
});

test("rail alerts cover configured local and Prowlarr keys, ordered by urgency", () => {
  const tracker = (name, expires_at, extra = {}) => ({
    name,
    configured: true,
    api_key_expiry_supported: true,
    api_key_expiry: { state: "valid", expires_at },
    ...extra,
  });
  const trackers = [
    tracker("SOON", "2026-09-22T12:00:00Z", { credential_source: "prowlarr" }),
    tracker("HEALTHY", "2026-09-22T12:00:01Z"),
    tracker("UNCONFIGURED", "2026-09-08T11:00:00Z", { configured: false }),
    tracker("EXPIRED", "2026-09-08T11:00:00Z", { credential_source: "local" }),
    tracker("UNSUPPORTED", "2026-09-08T11:00:00Z", {
      api_key_expiry_supported: false,
    }),
    tracker("UNKNOWN", null),
    tracker("INVALID", "invalid"),
    tracker("UNLIMITED", null, { api_key_expiry: { state: "no_expiry" } }),
  ];
  const result = sandbox.window.UAApiKeyExpiry.alerts(trackers);
  assert.deepEqual(
    Array.from(result, (entry) => entry.name),
    ["EXPIRED", "SOON"],
  );
  assert.equal(trackers[0].name, "SOON", "sorting does not mutate the catalog");
  assert.equal(sandbox.window.UAApiKeyExpiry.alerts([]).length, 0);
});

test("a stale expiry state without a timestamp cannot create a warning", () => {
  assert.equal(context.apiKeyExpiryState({ state: "expired" }), "unknown");
  assert.equal(
    context.apiKeyExpiryLabel({ state: "expired" }),
    "Expiry not reported",
  );
});
