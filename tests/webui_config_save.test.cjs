const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const context = { window: {} };
vm.runInNewContext(
  fs.readFileSync(
    path.join(__dirname, "../web_ui/static/js/config_save.js"),
    "utf8",
  ),
  context,
);
const { saveUpdates, readResponse } = context.window.UAConfigSave;

test("66 pending field edits are sent together, including inheritance and falsy values", async () => {
  const updates = Array.from({ length: 66 }, (_, index) => ({
    path: [
      "TRACKERS",
      `TRACKER${Math.floor(index / 22)}`,
      `field${index % 22}`,
    ],
    value: [null, false, 0, ""][index % 4],
    remove: false,
  }));
  const calls = [];
  await saveUpdates(
    async (url, options) => {
      calls.push({ url, options });
      return new Response(JSON.stringify({ success: true }), { status: 200 });
    },
    "/api",
    updates,
  );
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/config_update");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), { updates });
});

for (const body of [
  "Too many requests",
  JSON.stringify({ success: false, error: "Too many requests" }),
]) {
  test(`rate limit retains edits for retry with a readable error: ${body}`, async () => {
    const updates = [{ path: ["TRACKERS", "AITHER", "add_logo"], value: null }];
    const original = JSON.stringify(updates);
    let calls = 0;
    const fetch = async () => {
      calls++;
      return new Response(body, { status: 429 });
    };
    await assert.rejects(
      saveUpdates(fetch, "/api", updates),
      /Too many requests.*Pending changes kept/,
    );
    assert.equal(calls, 1);
    assert.equal(JSON.stringify(updates), original);
    await saveUpdates(
      async () => new Response('{"success":true}'),
      "/api",
      updates,
    );
  });
}

test("an HTML server error is not exposed as a JSON parser exception", async () => {
  await assert.rejects(
    readResponse(new Response("<html>Server error</html>", { status: 502 })),
    /HTTP 502.*pending changes/,
  );
});

test("validation errors are shown and no automatic retry occurs", async () => {
  let calls = 0;
  await assert.rejects(
    saveUpdates(
      async () => {
        calls++;
        return new Response('{"success":false,"error":"Invalid field"}', {
          status: 400,
        });
      },
      "/api",
      [{ path: ["DEFAULT", "unknown"], value: true }],
    ),
    /Invalid field/,
  );
  assert.equal(calls, 1);
});

test("a save with no field changes sends no update request", async () => {
  await saveUpdates(async () => assert.fail("Unexpected request"), "/api", []);
});
