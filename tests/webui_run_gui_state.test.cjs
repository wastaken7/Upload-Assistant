const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const loadRunGui = () => {
  const context = { window: {} };
  vm.runInNewContext(
    fs.readFileSync(
      path.join(__dirname, "../web_ui/static/js/run_gui_state.js"),
      "utf8",
    ),
    context,
  );
  return context.window.UARunGui;
};

const {
  createRunGuiState,
  reduceRunGuiEvent,
  markRunGuiPromptAnswered,
  selectRunGuiView,
  getDebugRunRows,
  readPayloadPreviews,
  payloadFieldValue,
  updatePayloadEdits,
  payloadEditErrors,
  payloadRoleAdvice,
  payloadEditWarnings,
  buildConfirmAnswer,
} = loadRunGui();

const plain = (value) => JSON.parse(JSON.stringify(value));
const gui = (data) => ({ type: "gui", data });
const run = (...events) =>
  events.reduce(reduceRunGuiEvent, createRunGuiState());

test("queue items tag later events and stages track the current item", () => {
  const state = run(
    gui({ kind: "item", index: 1, total: 2, name: "Fictional.Movie.2020.mkv" }),
    gui({ kind: "stage", key: "prep", status: "start", item: 1 }),
    gui({ kind: "stage", key: "prep", status: "done", item: 1 }),
    gui({
      kind: "item",
      index: 2,
      total: 2,
      name: "Other.Fake.Show.S01E01.mkv",
    }),
    gui({ kind: "stage", key: "prep", status: "start", item: 2 }),
  );
  const view = selectRunGuiView(state);

  assert.equal(view.multipleItems, true);
  assert.equal(view.currentItem.name, "Other.Fake.Show.S01E01.mkv");
  assert.equal(
    view.stages.find((stage) => stage.key === "prep").status,
    "start",
  );
  assert.equal(state.stages[1].prep, "done");
});

test("unknown stage keys and event kinds are ignored", () => {
  const initial = createRunGuiState();
  assert.equal(
    reduceRunGuiEvent(
      initial,
      gui({ kind: "stage", key: "nope", status: "start" }),
    ),
    initial,
  );
  assert.equal(reduceRunGuiEvent(initial, gui({ kind: "bogus" })), initial);
  assert.equal(
    reduceRunGuiEvent(initial, { type: "html", data: "<b>x</b>" }),
    initial,
  );
});

test("personal release flags survive completion and stay with their queue item", () => {
  const state = run(
    gui({ kind: "item", index: 1, total: 2, name: "Personal.mkv" }),
    gui({
      kind: "item",
      index: 1,
      total: 2,
      name: "Personal.mkv",
      personal_release: true,
    }),
    gui({ kind: "item", index: 2, total: 2, name: "Other.mkv" }),
    { type: "exit", code: 0 },
  );
  const view = selectRunGuiView(state);
  assert.equal(view.items.length, 2);
  assert.equal(view.items[0].personalRelease, true);
  assert.equal(view.currentItem.personalRelease, false);
  assert.equal(view.finished, true);
});

test("a corrected release flag replaces the previous badge", () => {
  const view = selectRunGuiView(
    run(
      gui({
        kind: "item",
        index: 1,
        total: 1,
        name: "Example",
        personal_release: true,
      }),
      gui({
        kind: "item",
        index: 1,
        total: 1,
        name: "Example",
        personal_release: false,
      }),
    ),
  );
  assert.equal(view.currentItem.personalRelease, false);
});

test("debug settings arrive before confirmation, survive replay, and stay with their item", () => {
  const events = [
    gui({
      kind: "item",
      index: 1,
      total: 2,
      name: "Debug",
      run_options: { debug: true, no_seed: true, skip_imghost_upload: false },
    }),
    gui({
      kind: "item",
      index: 1,
      total: 2,
      name: "Debug",
      personal_release: true,
      run_options: {
        debug: true,
        no_seed: true,
        skip_imghost_upload: true,
        prep_directory: "/tmp/prepared",
      },
    }),
    gui({
      kind: "item",
      index: 2,
      total: 2,
      name: "Normal",
      run_options: { debug: false },
    }),
    { type: "exit", code: 0 },
  ];
  const early = selectRunGuiView(run(events[0]));
  assert.equal(early.currentItem.runOptions.debug, true);
  assert.equal(early.lastConfirm, null);
  const view = selectRunGuiView(run(...plain(events)));
  assert.equal(view.items[0].runOptions.debug, true);
  assert.equal(view.items[0].runOptions.prepDirectory, "/tmp/prepared");
  assert.equal(view.currentItem.runOptions.debug, false);
});

test("skip flags use enabled ticks for skipping and disabled crosses for allowed actions", () => {
  for (const noSeed of [false, true])
    for (const skipImagehostUpload of [false, true]) {
      const rows = getDebugRunRows({
        debug: true,
        noSeed,
        skipImagehostUpload,
      });
      assert.equal(rows[0].enabled, true);
      assert.equal(rows[1].enabled, noSeed);
      assert.equal(rows[2].enabled, skipImagehostUpload);
      assert.equal(
        rows[1].detail,
        noSeed
          ? "Prepared torrents will not be added to a client."
          : "Prepared torrents may be added to configured clients.",
      );
      assert.equal(
        rows[2].detail,
        skipImagehostUpload
          ? "Screenshots will not be uploaded to an image host."
          : "Screenshots may still be uploaded to an image host.",
      );
    }
});

test("debug details explain nohash, disabled clients and music artwork without promising uploads", () => {
  const rows = getDebugRunRows({
    debug: true,
    noSeed: false,
    skipImagehostUpload: false,
    noHash: true,
    ffDebug: true,
    category: "MUSIC",
  });
  assert.match(rows[1].detail, /disabled by --nohash/);
  assert.match(rows[2].detail, /MUSIC artwork hosting is skipped/);
  assert.deepEqual(plain(rows.slice(3).map((row) => row.flag)), [
    "--nohash",
    "--ffdebug",
  ]);
  assert.match(
    getDebugRunRows({ debug: true, clientDisabled: true })[1].detail,
    /--client none/,
  );
  assert.deepEqual(plain(getDebugRunRows({ debug: false })), []);
});

test("repeated notices are counted once, and keyed notices keep the latest text", () => {
  const state = run(
    gui({
      kind: "notice",
      level: "error",
      text: "Upload failed: timeout",
      item: 1,
    }),
    gui({
      kind: "notice",
      level: "error",
      text: "Upload failed: timeout",
      item: 1,
    }),
    gui({
      kind: "notice",
      level: "attention",
      text: "Region 'XX' is not recognized.",
      key: "region:FAKE",
      tracker: "FAKE",
      item: 1,
    }),
    gui({
      kind: "notice",
      level: "attention",
      text: "Region 'YY' is not recognized.",
      key: "region:FAKE",
      tracker: "FAKE",
      item: 1,
    }),
    gui({ kind: "notice", level: "debug", text: "ignored", item: 1 }),
  );
  const view = selectRunGuiView(state);

  assert.equal(view.errors.length, 1);
  assert.equal(view.errors[0].count, 2);
  assert.equal(view.attention.length, 1);
  assert.equal(view.attention[0].text, "Region 'YY' is not recognized.");
  assert.equal(view.attention[0].count, 2);
});

test("a notice group replaces its earlier notices for the same item", () => {
  const state = run(
    gui({
      kind: "notice_group",
      group: "confirm",
      item: 1,
      notices: [
        { level: "attention", text: "Region is missing." },
        { level: "attention", text: "Distributor is missing." },
      ],
    }),
    gui({
      kind: "notice_group",
      group: "confirm",
      item: 1,
      notices: [{ level: "attention", text: "Distributor is missing." }],
    }),
  );

  assert.deepEqual(
    plain(selectRunGuiView(state).attention.map((notice) => notice.text)),
    ["Distributor is missing."],
  );
});

test("the reducer never mutates the previous state", () => {
  const before = run(gui({ kind: "notice", level: "error", text: "first" }));
  const snapshot = JSON.stringify(before);
  reduceRunGuiEvent(
    before,
    gui({ kind: "notice", level: "error", text: "second" }),
  );
  assert.equal(JSON.stringify(before), snapshot);
});

test("prompts open, can be marked answered, and close only by their own id", () => {
  let state = run(
    gui({
      kind: "prompt",
      action: "open",
      id: 3,
      type: "yes_no",
      question: "Upload to FAKE anyway?",
      default: false,
      context: { kind: "dupes", tracker: "FAKE" },
      item: 1,
    }),
  );
  assert.equal(state.prompt.question, "Upload to FAKE anyway?");
  assert.equal(state.prompt.default, false);

  state = markRunGuiPromptAnswered(state);
  assert.equal(state.prompt.answered, true);

  state = reduceRunGuiEvent(
    state,
    gui({ kind: "prompt", action: "close", id: 2 }),
  );
  assert.ok(state.prompt);
  state = reduceRunGuiEvent(
    state,
    gui({ kind: "prompt", action: "close", id: 3 }),
  );
  assert.equal(state.prompt, null);
});

test("prompt_state and exit events update the waiting and finished flags", () => {
  let state = run({
    type: "prompt_state",
    awaiting: true,
    input_type: "yes_no",
  });
  assert.equal(state.awaiting, true);
  assert.equal(state.inputType, "yes_no");

  state = reduceRunGuiEvent(
    state,
    gui({ kind: "stage", key: "upload", status: "start" }),
  );
  state = reduceRunGuiEvent(state, { type: "exit", code: 1 });
  const view = selectRunGuiView(state);
  assert.equal(view.finished, true);
  assert.equal(view.exitCode, 1);
  assert.equal(view.awaiting, false);
  // A stage left running when the process ended is shown as stopped.
  assert.equal(
    view.stages.find((stage) => stage.key === "upload").status,
    "fail",
  );
});

test("tracker results merge the live result with the final snapshot", () => {
  const state = run(
    gui({ kind: "tracker", tracker: "FAKE", status: "pending", item: 1 }),
    gui({
      kind: "tracker",
      tracker: "OTHER",
      status: "dupe",
      message: "Possible dupe",
      item: 1,
    }),
    gui({
      kind: "tracker",
      tracker: "FAKE",
      status: "success",
      link: "https://tracker.invalid/torrents/7",
      torrent_id: "7",
      duration: 2.5,
      item: 1,
    }),
    gui({ kind: "tracker", tracker: "FAKE", status: "success", item: 1 }),
  );
  const view = selectRunGuiView(state);
  const fake = view.trackers.find((entry) => entry.tracker === "FAKE");

  assert.equal(fake.link, "https://tracker.invalid/torrents/7");
  assert.equal(fake.torrentId, "7");
  assert.equal(fake.duration, 2.5);
  assert.deepEqual(plain(view.counts), {
    success: 1,
    failed: 0,
    dupe: 1,
    banned: 0,
    skipped: 0,
    pending: 0,
  });
  assert.equal(view.trackers[0].tracker, "FAKE");
});

test("dupes, slot decisions and requests are kept per item and tracker", () => {
  const state = run(
    gui({ kind: "item", index: 1, total: 1, name: "Fictional.Movie.mkv" }),
    gui({
      kind: "dupes",
      tracker: "FAKE",
      item: 1,
      entries: [
        {
          name: "Fictional.Movie.2020.1080p-NOGRP",
          link: "https://tracker.invalid/t/1",
          size: 1000,
          diff_pct: -5,
        },
        { name: "" },
      ],
    }),
    gui({
      kind: "dupes",
      tracker: "FAKE",
      item: 1,
      trumpable: true,
      entries: [],
    }),
    gui({
      kind: "slot",
      tracker: "FAKE",
      item: 1,
      verdict: "review",
      title: "Check before uploading",
      reason: "Same slot",
    }),
    gui({
      kind: "slot",
      tracker: "OTHER",
      item: 1,
      verdict: "allow",
      title: "Upload looks fine",
      reason: "",
    }),
    gui({
      kind: "request",
      tracker: "FAKE",
      item: 1,
      name: "Fictional Movie",
      link: "https://tracker.invalid/requests/9",
      reward: "500",
      exact: true,
    }),
    gui({
      kind: "request",
      tracker: "FAKE",
      item: 1,
      name: "Fictional Movie",
      link: "https://tracker.invalid/requests/9",
      reward: "500",
      exact: true,
    }),
  );
  const view = selectRunGuiView(state);

  const dupe = view.dupes["1:FAKE"];
  assert.equal(dupe.entries.length, 1);
  assert.equal(dupe.entries[0].diffPct, -5);
  assert.equal(dupe.trumpable, true);
  // The run is still on item 1 and no tracker has a result yet.
  assert.deepEqual(plain(view.attentionCards.map((card) => card.tracker)), [
    "FAKE",
  ]);
  assert.equal(view.requests.length, 1);
  assert.equal(view.requests[0].reward, "500");
});

test("slot checks keep their full detail and only hex size colours", () => {
  const state = run(
    gui({
      kind: "slot",
      tracker: "FAKE",
      item: 1,
      verdict: "review",
      title: "Check before uploading",
      reason: "Same slot",
      slot: "1080p WEB",
      why: "One release per group",
      conflicts: [
        {
          name: "Fictional.Movie-OTHERGRP",
          size: 10,
          diff_pct: 1,
          color: "#f44f3d",
        },
        {
          name: "Fictional.Movie-FAKEGRP",
          size: 20,
          diff_pct: 90,
          color: "red;background:url(x)",
        },
      ],
      notes: ["Check the source", 7],
      rules: "Rules as of 2026-10-01 (20 days ago).",
    }),
  );
  const slot = state.slots["1:FAKE"];

  assert.equal(slot.slot, "1080p WEB");
  assert.equal(slot.why, "One release per group");
  assert.deepEqual(plain(slot.conflicts.map((entry) => entry.color)), [
    "#f44f3d",
    "",
  ]);
  assert.deepEqual(plain(slot.notes), ["Check the source"]);
  assert.equal(slot.rules, "Rules as of 2026-10-01 (20 days ago).");
});

test("handled items and trackers move from Needs attention to Results", () => {
  const dupes = (item) =>
    gui({
      kind: "dupes",
      tracker: "FAKE",
      item,
      entries: [{ name: "Fictional.Movie.2020-OTHERGRP" }],
    });
  let state = run(
    gui({ kind: "item", index: 1, total: 2, name: "First.Fake.mkv" }),
    dupes(1),
    gui({
      kind: "notice",
      level: "attention",
      text: "Distributor is missing.",
      item: 1,
    }),
  );
  let view = selectRunGuiView(state);
  assert.equal(view.attentionCards.length, 1);
  assert.equal(view.attentionNotices.length, 1);

  // A result row for the tracker takes its dupes along.
  state = reduceRunGuiEvent(
    state,
    gui({ kind: "tracker", tracker: "FAKE", status: "skipped", item: 1 }),
  );
  view = selectRunGuiView(state);
  assert.equal(view.attentionCards.length, 0);
  assert.equal(view.trackerDetails["1:FAKE"].dupe.entries.length, 1);
  assert.equal(view.attentionNotices.length, 1);

  // Starting the next item archives what is left of the first one.
  state = reduceRunGuiEvent(
    state,
    gui({ kind: "item", index: 2, total: 2, name: "Second.Fake.mkv" }),
  );
  view = selectRunGuiView(state);
  assert.equal(view.attentionNotices.length, 0);
  assert.equal(view.itemNotes[1].notices[0].text, "Distributor is missing.");

  // When the run ends nothing is left in Needs attention.
  state = reduceRunGuiEvent(state, dupes(2));
  state = reduceRunGuiEvent(state, { type: "exit", code: 0 });
  view = selectRunGuiView(state);
  assert.equal(view.attentionCards.length, 0);
  assert.equal(view.itemNotes[2].cards[0].tracker, "FAKE");
});

test("notices are capped so a noisy run cannot grow without bound", () => {
  let state = createRunGuiState();
  for (let index = 0; index < 250; index += 1) {
    state = reduceRunGuiEvent(
      state,
      gui({ kind: "notice", level: "warning", text: `warning ${index}` }),
    );
  }
  assert.equal(state.notices.length, 200);
  assert.equal(state.notices.at(-1).text, "warning 249");
});

test("errors and warnings of earlier queue items move under their results", () => {
  const state = run(
    gui({ kind: "notice", level: "warning", text: "Config note for the run" }),
    gui({ kind: "item", index: 1, total: 2, name: "Fictional.Album.2020" }),
    gui({
      kind: "notice",
      level: "warning",
      text: "FAKE: read-only duplicate search failed: ReadTimeout",
      item: 1,
    }),
    gui({ kind: "notice", level: "error", text: "Earlier error", item: 1 }),
    gui({ kind: "item", index: 2, total: 2, name: "Other.Fake.Album.2021" }),
    gui({ kind: "notice", level: "warning", text: "Current warning", item: 2 }),
  );
  const view = selectRunGuiView(state);

  assert.deepEqual(plain(view.warnings.map((notice) => notice.text)), [
    "Config note for the run",
    "Current warning",
  ]);
  assert.equal(view.errors.length, 0);
  assert.deepEqual(
    plain(view.itemNotes[1].problems.map((notice) => notice.level)),
    ["warning", "error"],
  );

  // The last item's problems stay listed once the run has finished.
  const finished = selectRunGuiView(
    reduceRunGuiEvent(state, { type: "exit", code: 0 }),
  );
  assert.equal(finished.warnings.length, 2);
});

test("a regular dupe list after a declined trump is no longer trumpable", () => {
  const state = run(
    gui({
      kind: "dupes",
      tracker: "FAKE",
      item: 1,
      trumpable: true,
      entries: [{ name: "Fictional.Movie.2020.1080p-OLD" }],
    }),
    gui({
      kind: "dupes",
      tracker: "FAKE",
      item: 1,
      entries: [{ name: "Fictional.Movie.2020.1080p-OTHER" }],
    }),
  );

  assert.equal(selectRunGuiView(state).dupes["1:FAKE"].trumpable, false);
});

test("a failed answer reopens only the prompt it was sent for", () => {
  const opened = run(
    gui({
      kind: "prompt",
      action: "open",
      id: 4,
      type: "yes_no",
      question: "Upload anyway?",
    }),
  );
  const answered = markRunGuiPromptAnswered(opened);

  assert.equal(
    markRunGuiPromptAnswered(answered, false, 4).prompt.answered,
    false,
  );
  assert.equal(
    markRunGuiPromptAnswered(answered, false, 5).prompt.answered,
    true,
  );
});

test("the declined confirmation summary stays available for corrections", () => {
  const state = run(
    gui({
      kind: "prompt",
      action: "open",
      id: 1,
      type: "yes_no",
      question: "Is this correct?",
      item: 1,
      context: { kind: "confirm", base_name: "Fictional.Movie.2020-NOGRP" },
    }),
    gui({ kind: "prompt", action: "close", id: 1, item: 1 }),
    gui({
      kind: "prompt",
      action: "open",
      id: 2,
      type: "text",
      question: "Input args that need correction",
      item: 1,
      context: { kind: "edit_args", values: { "--tag": "NOGRP" } },
    }),
  );
  const view = selectRunGuiView(state);

  assert.equal(view.prompt.context.kind, "edit_args");
  assert.equal(view.lastConfirm.item, 1);
  assert.equal(
    view.lastConfirm.context.base_name,
    "Fictional.Movie.2020-NOGRP",
  );
});

test("review progress grows during discovery and counts a tracker only once", () => {
  let state = run(
    gui({ kind: "item", index: 1, total: 2, name: "First" }),
    gui({
      kind: "dupe_review",
      item: 1,
      trackers: ["FIRST"],
      started: ["FIRST"],
      checking: 2,
    }),
    gui({
      kind: "prompt",
      action: "open",
      id: 1,
      type: "yes_no",
      context: { kind: "dupes", tracker: "FIRST" },
    }),
  );
  assert.deepEqual(plain(selectRunGuiView(state).dupeReview), {
    index: 1,
    total: 1,
    checking: 2,
  });
  state = reduceRunGuiEvent(
    state,
    gui({
      kind: "dupe_review",
      item: 1,
      trackers: ["FIRST", "SECOND"],
      started: ["FIRST"],
      checking: 0,
    }),
  );
  assert.deepEqual(plain(selectRunGuiView(state).dupeReview), {
    index: 1,
    total: 2,
    checking: 0,
  });
  state = reduceRunGuiEvent(
    state,
    gui({
      kind: "prompt",
      action: "open",
      id: 2,
      type: "yes_no",
      context: { kind: "dupes", tracker: "FIRST" },
    }),
  );
  assert.equal(selectRunGuiView(state).dupeReview.index, 1);
  state = reduceRunGuiEvent(
    state,
    gui({
      kind: "dupe_review",
      item: 1,
      trackers: ["FIRST", "SECOND"],
      started: ["FIRST", "SECOND"],
      checking: 0,
    }),
  );
  state = reduceRunGuiEvent(
    state,
    gui({
      kind: "prompt",
      action: "open",
      id: 3,
      type: "yes_no",
      context: { kind: "dupes", tracker: "SECOND" },
    }),
  );
  assert.deepEqual(plain(selectRunGuiView(state).dupeReview), {
    index: 2,
    total: 2,
    checking: 0,
  });
  state = reduceRunGuiEvent(
    state,
    gui({ kind: "item", index: 2, total: 2, name: "Second" }),
  );
  state = reduceRunGuiEvent(
    state,
    gui({
      kind: "prompt",
      action: "open",
      id: 4,
      type: "yes_no",
      context: { kind: "dupes", tracker: "FIRST" },
    }),
  );
  assert.equal(selectRunGuiView(state).dupeReview, null);
});

test("unrelated prompts and another session do not inherit a review counter", () => {
  const state = run(
    gui({
      kind: "dupe_review",
      trackers: ["FIRST"],
      started: ["FIRST"],
      checking: 0,
    }),
    gui({
      kind: "prompt",
      action: "open",
      id: 1,
      context: { kind: "tracker_checks", tracker: "FIRST" },
    }),
  );
  assert.equal(selectRunGuiView(state).dupeReview, null);
  assert.equal(selectRunGuiView(createRunGuiState()).dupeReview, null);
});

test("queue item covers stay with their item and reject unsafe sources", () => {
  const view = selectRunGuiView(
    run(
      gui({ kind: "item", index: 1, total: 3, name: "First.mkv" }),
      gui({
        kind: "item",
        index: 1,
        total: 3,
        name: "First.mkv",
        artwork: "https://images.invalid/first.jpg",
      }),
      gui({
        kind: "item",
        index: 2,
        total: 3,
        name: "Second",
        artwork: "/api/execution_item_cover?session_id=s&item=2&v=1",
      }),
      gui({
        kind: "item",
        index: 3,
        total: 3,
        name: "Third",
        artwork: "javascript:alert(1)",
      }),
      { type: "exit", code: 0 },
    ),
  );
  assert.deepEqual(plain(view.items.map((item) => item.artwork)), [
    "https://images.invalid/first.jpg",
    "/api/execution_item_cover?session_id=s&item=2&v=1",
    "",
  ]);
});

const payloadContext = {
  kind: "confirm",
  payloads: [
    {
      tracker: "FAKE",
      name: "Fictional Film 2001",
      fields: [
        {
          key: "name",
          label: "Name",
          kind: "text",
          value: "Fictional Film 2001",
          max: 30,
        },
        {
          key: "tmdb",
          label: "TMDB ID",
          kind: "text",
          value: "4321",
          max: 20,
          numeric: true,
        },
        {
          key: "type_id",
          label: "Type",
          kind: "choice",
          value: "4",
          display: "WEBDL (4)",
          choices: "c0",
        },
        {
          key: "region_id",
          label: "Region",
          kind: "choice",
          value: "7",
          display: "GBR (7)",
        },
        { key: "anonymous", label: "Anonymous", kind: "flag", value: false },
        {
          key: "description",
          label: "Description",
          kind: "deferred",
          note: "Built later",
        },
        { key: "bogus", label: "Bogus", kind: "script", value: "x" },
      ],
    },
    { name: "missing tracker" },
  ],
  payload_choices: [
    {
      id: "c0",
      choices: [
        ["2", "REMUX"],
        ["4", "WEBDL"],
      ],
    },
  ],
};

test("upload data previews resolve shared drop-down lists", () => {
  const [preview, ...rest] = readPayloadPreviews(payloadContext);
  assert.equal(rest.length, 0);
  const byKey = Object.fromEntries(
    preview.fields.map((field) => [field.key, field]),
  );
  assert.deepEqual(Object.keys(byKey), [
    "name",
    "tmdb",
    "type_id",
    "region_id",
    "anonymous",
    "description",
  ]);
  assert.deepEqual(plain(byKey.type_id.choices), [
    ["2", "REMUX"],
    ["4", "WEBDL"],
  ]);
  assert.equal(byKey.type_id.editable, true);
  // A drop-down sent without its list is shown but not editable.
  assert.equal(byKey.region_id.editable, false);
  assert.equal(byKey.description.editable, false);
  assert.equal(byKey.anonymous.value, false);
});

test("upload data edits keep only changed values and report invalid ones", () => {
  const [preview] = readPayloadPreviews(payloadContext);
  const byKey = Object.fromEntries(
    preview.fields.map((field) => [field.key, field]),
  );
  let edits = updatePayloadEdits({}, "FAKE", byKey.type_id, "2");
  edits = updatePayloadEdits(edits, "FAKE", byKey.anonymous, true);
  edits = updatePayloadEdits(edits, "FAKE", byKey.tmdb, "12a");
  assert.equal(payloadFieldValue(byKey.type_id, edits, "FAKE"), "2");
  assert.deepEqual(plain(payloadEditErrors([preview], edits)), {
    FAKE: { tmdb: "Numbers only" },
  });

  edits = updatePayloadEdits(edits, "FAKE", byKey.tmdb, "4321");
  edits = updatePayloadEdits(edits, "FAKE", byKey.name, "  ");
  assert.deepEqual(plain(payloadEditErrors([preview], edits)), {
    FAKE: { name: "Cannot be empty" },
  });
  edits = updatePayloadEdits(edits, "FAKE", byKey.name, "x".repeat(31));
  assert.deepEqual(plain(payloadEditErrors([preview], edits)), {
    FAKE: { name: "At most 30 characters" },
  });
  edits = updatePayloadEdits(edits, "FAKE", byKey.name, "Fictional Film 2001");
  assert.deepEqual(plain(edits), { FAKE: { type_id: "2", anonymous: true } });

  edits = updatePayloadEdits(edits, "FAKE", byKey.type_id, "4");
  edits = updatePayloadEdits(edits, "FAKE", byKey.anonymous, false);
  assert.deepEqual(plain(edits), {});
});

test("the confirm answer carries run options and upload data edits", () => {
  assert.equal(buildConfirmAnswer({}, {}), "yes");
  assert.equal(buildConfirmAnswer({ anon: true }, {}), 'yes {"anon":true}');
  assert.equal(
    buildConfirmAnswer({ anon: true }, { FAKE: { type_id: "2" } }),
    'yes {"anon":true,"payload_edits":{"FAKE":{"type_id":"2"}}}',
  );
});

const warningPreview = () =>
  readPayloadPreviews({
    kind: "confirm",
    payloads: [
      {
        tracker: "FAKE",
        fields: [
          {
            key: "name",
            label: "Name",
            kind: "text",
            value: "Fictional Film 2001 1080p WEB-DL-NOGRP",
            max: 255,
            role: "name",
          },
          {
            key: "tmdb",
            label: "TMDB ID",
            kind: "text",
            value: "4321",
            max: 20,
            numeric: true,
            role: "external_id",
          },
          {
            key: "resolution_id",
            label: "Resolution",
            kind: "choice",
            value: "3",
            display: "1080p / 1440p (3)",
            choices: "r",
            role: "resolution",
          },
          { key: "anonymous", label: "Anonymous", kind: "flag", value: false },
          {
            key: "featured",
            label: "Featured",
            kind: "flag",
            value: false,
            role: "staff_flag",
          },
        ],
      },
    ],
    payload_choices: [
      {
        id: "r",
        choices: [
          ["2", "2160p"],
          ["3", "1080p / 1440p"],
        ],
      },
    ],
  })[0];

test("changing metadata-made fields warns with the correction to use instead", () => {
  const preview = warningPreview();
  const edits = {
    FAKE: { tmdb: "9999", resolution_id: "2", anonymous: true, featured: true },
  };
  const warnings = plain(payloadEditWarnings(preview, edits));
  assert.deepEqual(Object.keys(warnings).sort(), [
    "featured",
    "resolution_id",
    "tmdb",
  ]);
  assert.match(warnings.tmdb, /--tmdb/);
  assert.match(warnings.tmdb, /The name was not changed/);
  assert.match(warnings.resolution_id, /--resolution/);
  assert.match(warnings.resolution_id, /The name still says "1080p"/);
  assert.match(warnings.featured, /staff/);
  assert.equal(payloadRoleAdvice("name").includes("--imdb"), true);
  assert.equal(payloadRoleAdvice(""), "");
});

test("a changed name or a cleared staff option drops the cross-field warnings", () => {
  const preview = warningPreview();
  const warnings = plain(
    payloadEditWarnings(preview, {
      FAKE: {
        name: "Fictional Film 2001 2160p WEB-DL-NOGRP",
        resolution_id: "2",
        featured: false,
      },
    }),
  );
  assert.deepEqual(Object.keys(warnings).sort(), ["name", "resolution_id"]);
  assert.doesNotMatch(warnings.resolution_id, /The name/);
  assert.match(warnings.name, /answer No/);
});
