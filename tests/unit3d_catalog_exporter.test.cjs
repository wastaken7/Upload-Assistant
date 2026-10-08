const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(
    __dirname,
    "../scripts/UNIT3D-Catalog-Exporter/UNIT3D-catalog-exporter.user.js",
  ),
  "utf8",
);

function initializer(options, variable = "myRegions") {
  const encoded = JSON.stringify(options)
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/"/g, "\\u0022");
  return `let ${variable} = [{label: "No region", value: "0"}, ...JSON.parse('${encoded}')];`;
}

test("accepts unquoted numeric object keys in literal data", async () => {
  const result = run(
    [
      "let myDistributors = [{value: 8, label: 'Example Studio', extra: {1: 'Example value'}}];",
    ],
    { includeDistributors: false },
  );
  assert.deepEqual(result.alerts, []);
  assert.deepEqual(JSON.parse(await result.blob.text()).distributors, {
    8: "Example Studio",
  });
});

test("reads array spreads larger than the engine argument limit", async () => {
  const options = Array.from({ length: 150000 }, (_, index) => ({
    value: index + 1,
    label: `Example Studio ${index}`,
  }));
  const result = run([initializer(options, "myDistributors")], {
    includeDistributors: false,
  });
  assert.deepEqual(result.alerts, []);
  assert.equal(
    Object.keys(JSON.parse(await result.blob.text()).distributors).length,
    options.length,
  );
});

test("equivalent lists in different orders do not conflict", async () => {
  const options = [
    { value: 2, label: "Example Studio B" },
    { value: 1, label: "Example Studio A" },
  ];
  const result = run(
    [
      initializer(options, "myDistributors"),
      initializer([...options].reverse(), "myDistributors"),
    ],
    { includeDistributors: false },
  );
  assert.deepEqual(result.alerts, []);
  assert.deepEqual(JSON.parse(await result.blob.text()).distributors, {
    1: "Example Studio A",
    2: "Example Studio B",
  });
});

function run(
  scripts,
  {
    tracker = "DEMO",
    hostname = "demo.test",
    select = null,
    inputs = [],
    xData = [],
    includeDistributors = true,
  } = {},
) {
  if (includeDistributors)
    scripts = [
      ...scripts,
      initializer([{ value: 7, label: "Example Studio" }], "myDistributors"),
    ];
  const buttons = [];
  const downloads = [];
  const alerts = [];
  const prompts = [];
  let blob;
  const document = {
    readyState: "complete",
    documentElement: {},
    getElementById: () => null,
    querySelector: (selector) =>
      selector.startsWith("select#region")
        ? select
        : selector.startsWith("select#")
          ? null
          : {},
    querySelectorAll: (selector) => {
      if (selector === "input") return inputs;
      if (selector === "[x-data]")
        return xData.map((expression) => ({ getAttribute: () => expression }));
      if (selector === "select")
        return select
          ? [
              {
                ...select,
                matches: (selector) => selector.includes("#region"),
                getAttribute: () => null,
              },
            ]
          : [];
      return scripts.map((textContent) => ({ textContent }));
    },
    createElement: (tag) => ({
      style: {},
      addEventListener(event, handler) {
        this.handler = handler;
      },
      click() {
        downloads.push(this.download);
      },
      remove() {},
      tag,
    }),
    body: {
      appendChild(element) {
        if (element.tag === "button") buttons.push(element);
      },
    },
  };
  vm.runInNewContext(source, {
    document,
    window: {
      location: { hostname },
      prompt: (message, defaultName) => {
        prompts.push({ message, defaultName });
        return tracker;
      },
      alert: (message) => alerts.push(message),
    },
    Blob,
    URL: {
      createObjectURL(value) {
        blob = value;
        return "blob:test";
      },
      revokeObjectURL() {},
    },
    setTimeout: (callback) => callback(),
    MutationObserver: class {
      observe() {}
    },
  });
  assert.equal(buttons.length, 1);
  buttons[0].handler();
  return { blob, downloads, alerts, prompts };
}

test("uses canonical tracker filenames for known domains without prompting", () => {
  for (const [hostname, filename] of [
    ["upload.cx", "ulcx.json"],
    ["theldu.to", "lastdigitalunderground.json"],
    ["tlzdigital.com", "theleachzone.json"],
    ["torrent.desi", "desitorrents.json"],
    ["lat-team.com", "latteam.json"],
    ["eiga.moi", "asiancinema.json"],
    ["reelflix.cc", "reelflix.json"],
    ["reelflix.xyz", "reelflix.json"],
    ["WWW.CAPYBARABR.COM.", "capybarabr.json"],
    ["www.torrenthr.org", "torrenthr.json"],
  ]) {
    const result = run([], { hostname, tracker: null });
    assert.deepEqual(result.downloads, [filename]);
    assert.deepEqual(result.prompts, []);
    assert.deepEqual(result.alerts, []);
  }
});

test("asks for unknown domains and does not match lookalike domains or arbitrary subdomains", () => {
  for (const hostname of [
    "demo.test",
    "upload.cx.example.test",
    "other.upload.cx",
  ]) {
    const result = run([], { hostname, tracker: "CUSTOM" });
    assert.deepEqual(result.downloads, ["custom.json"]);
    assert.equal(result.prompts.length, 1);
    assert.equal(result.prompts[0].defaultName, hostname.split(".")[0]);
  }
});

test("exports the complete embedded list, preserving IDs and localized codes", async () => {
  const options = [
    { value: 29, label: "BRA (Fictionalândia)" },
    { value: 83, label: "GBR (Example's Isles)" },
  ];
  const result = run([initializer(options)]);
  assert.deepEqual(result.alerts, []);
  assert.deepEqual(result.downloads, ["demo.json"]);
  assert.deepEqual(JSON.parse(await result.blob.text()), {
    regions: { 29: "BRA", 83: "GBR" },
    distributors: { 7: "Example Studio" },
    regions_complete: true,
    distributors_complete: true,
    categories: {},
    types: {},
    resolutions: {},
  });
});

test("reads all entries instead of a virtualized DOM window", async () => {
  const options = Array.from({ length: 243 }, (_, index) => ({
    value: index + 1,
    label: `${String.fromCharCode(65 + Math.floor(index / 26))}${String.fromCharCode(65 + (index % 26))}A (Example)`,
  }));
  const result = run([initializer(options)]);
  assert.equal(
    Object.keys(JSON.parse(await result.blob.text()).regions).length,
    243,
  );
});

test("supports native selects and omits blank and zero placeholders", async () => {
  const result = run([], {
    select: {
      options: [
        { value: "", textContent: "Select" },
        { value: "0", textContent: "No region" },
        { value: "29", textContent: "BRA" },
      ],
    },
  });
  assert.deepEqual(JSON.parse(await result.blob.text()), {
    regions: { 29: "BRA" },
    distributors: { 7: "Example Studio" },
    regions_complete: true,
    distributors_complete: true,
    categories: {},
    types: {},
    resolutions: {},
  });
});

test("rejects conflicting IDs and duplicate region codes", () => {
  for (const options of [
    [
      { value: 1, label: "BRA" },
      { value: 1, label: "GBR" },
    ],
    [
      { value: 1, label: "BRA" },
      { value: 2, label: "BRA" },
    ],
  ]) {
    const result = run([initializer(options)]);
    assert.equal(result.downloads.length, 0);
    assert.equal(result.alerts.length, 1);
  }
});

test("refuses conflicting lists and executable expressions without executing page code", () => {
  for (const scripts of [
    [
      initializer([{ value: 1, label: "BRA" }]),
      initializer([{ value: 2, label: "BRA" }]),
    ],
    ["let myRegions = [...JSON.parse(doSomething())];"],
  ]) {
    const result = run(scripts);
    assert.equal(result.downloads.length, 0);
    assert.equal(result.alerts.length, 1);
  }
});

test("supports literal arrays, mixed spreads, trailing commas and empty spreads", async () => {
  const scripts = [
    "let myRegions = [{label: 'BRA (Example)', value: '33'}, ...[],];",
    "let myDistributors = [{value: 8, label: 'Example Studio'}, ...[],];",
  ];
  const result = run(scripts, { includeDistributors: false });
  const catalog = JSON.parse(await result.blob.text());
  assert.deepEqual(catalog.regions, { 33: "BRA" });
  assert.deepEqual(catalog.distributors, { 8: "Example Studio" });
});

test("supports literal initializers without a semicolon before VirtualSelect.init", async () => {
  const result = run([
    "let myRegions = [{label: 'BRA', value: 33},]\nVirtualSelect.init({});",
  ]);
  assert.deepEqual(JSON.parse(await result.blob.text()).regions, { 33: "BRA" });
});

test("reads full Alpine triSelect options rather than its rendered window", async () => {
  const xData = [
    ["regionIds", [{ value: 33, label: "BRA" }]],
    ["distributorIds", [{ value: 8, label: "Example Studio" }]],
    ["categoryIds", [{ value: 1, label: "Example Movies" }]],
    ["typeIds", [{ value: 2, label: "Example Encode" }]],
    ["resolutionIds", [{ value: 3, label: "1080p" }]],
  ].map(
    ([includeModel, options]) =>
      `triSelect(JSON.parse(${JSON.stringify(JSON.stringify({ includeModel, options }))}))`,
  );
  const result = run([], { xData, includeDistributors: false });
  const catalog = JSON.parse(await result.blob.text());
  assert.deepEqual(catalog.regions, { 33: "BRA" });
  assert.deepEqual(catalog.distributors, { 8: "Example Studio" });
  assert.deepEqual(catalog.categories, { 1: "Example Movies" });
  assert.deepEqual(catalog.types, { 2: "Example Encode" });
  assert.deepEqual(catalog.resolutions, { 3: "1080p" });
});

test("supports older model names and repeated display labels with different IDs", async () => {
  const inputs = [1, 2].map((value) => ({
    value,
    labels: [{ textContent: "Other" }],
    getAttribute: (attr) => (attr === "wire:model" ? "types" : null),
  }));
  const result = run([], { inputs });
  assert.deepEqual(JSON.parse(await result.blob.text()).types, {
    1: "Other",
    2: "Other",
  });
});

test("missing fields are empty complete catalogs rather than inherited defaults", async () => {
  const result = run([], { includeDistributors: false });
  assert.deepEqual(JSON.parse(await result.blob.text()), {
    regions: {},
    distributors: {},
    categories: {},
    types: {},
    resolutions: {},
    regions_complete: true,
    distributors_complete: true,
  });
});

test("preserves localized IDs and raw non-country region choices without guessing", async () => {
  const options = [
    { value: 249, label: "Brazylia (regions.Brazylia)" },
    { value: 65, label: "UK (regions.UK)" },
    { value: 272, label: "Example non-country option" },
  ];
  const result = run([initializer(options)]);
  const catalog = JSON.parse(await result.blob.text());
  assert.deepEqual(catalog.regions, { 249: "BRA", 65: "GBR" });
  assert.equal(catalog.region_labels[272], "Example non-country option");
  assert.equal(catalog.regions[272], undefined);
  assert.equal(catalog.regions_complete, true);
});

test("canceling or entering an unsafe filename does not download", () => {
  for (const tracker of [null, "../demo", ""]) {
    const result = run([initializer([{ value: 1, label: "BRA" }])], {
      tracker,
    });
    assert.equal(result.downloads.length, 0);
  }
});

test("exports categories, types and resolutions from all available checkboxes", async () => {
  const inputs = [
    ["categoryIds", "1", "Example Movies"],
    ["typeIds", "3", "Example Encode"],
    ["resolutionIds", "5", "1080p"],
  ].map(([model, value, label]) => ({
    value,
    labels: [{ textContent: `\n ${label} \n` }],
    getAttribute: (attribute) =>
      attribute === "wire:model.live" ? model : null,
  }));
  const result = run([initializer([{ value: 33, label: "BRA" }])], { inputs });
  const catalog = JSON.parse(await result.blob.text());
  assert.deepEqual(catalog.categories, { 1: "Example Movies" });
  assert.deepEqual(catalog.types, { 3: "Example Encode" });
  assert.deepEqual(catalog.resolutions, { 5: "1080p" });
});

test("preserves distributor accents, punctuation and apostrophes", async () => {
  const scripts = [
    initializer([{ value: 33, label: "BRA" }]),
    initializer(
      [{ value: 9, label: "Example's Vídeo & Co." }],
      "myDistributors",
    ),
  ];
  const result = run(scripts, { includeDistributors: false });
  assert.deepEqual(JSON.parse(await result.blob.text()).distributors, {
    9: "Example's Vídeo & Co.",
  });
});

test("an absent distributor field exports a complete empty catalog", async () => {
  const result = run([initializer([{ value: 33, label: "BRA" }])], {
    includeDistributors: false,
  });
  assert.deepEqual(JSON.parse(await result.blob.text()).distributors, {});
  assert.equal(
    JSON.parse(await result.blob.text()).distributors_complete,
    true,
  );
});

test("an explicitly empty distributor list is exported as complete", async () => {
  const result = run(
    [
      initializer([{ value: 33, label: "BRA" }]),
      initializer([], "myDistributors"),
    ],
    { includeDistributors: false },
  );
  const catalog = JSON.parse(await result.blob.text());
  assert.deepEqual(catalog.distributors, {});
  assert.equal(catalog.distributors_complete, true);
});

module.exports = { run };
