const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const context = vm.createContext({ window: {} });
for (const name of ["language_flags_data.js", "language_flags.js"]) {
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "../web_ui/static/js", name), "utf8"),
    context,
  );
}
const flag = context.window.getUAPreviewLanguageFlag;

test("preview flags recognize MediaInfo names and ISO language aliases", () => {
  for (const language of ["English", " eng ", "en", "EN"]) {
    assert.equal(flag(language), "/static/img/flags/gb.svg");
  }
  for (const language of ["Portuguese", "por", "pt", "Português"]) {
    assert.equal(flag(language), "/static/img/flags/pt.svg");
  }
  assert.equal(flag("Japanese"), "/static/img/flags/jp.svg");
  assert.equal(flag("jpn"), "/static/img/flags/jp.svg");
  assert.equal(flag("fre"), "/static/img/flags/fr.svg");
});

test("explicit regional variants use their corresponding country", () => {
  for (const language of [
    "pt-BR",
    "pt_BR",
    "Portuguese (Brazil)",
    "Brazilian Portuguese",
  ]) {
    assert.equal(flag(language), "/static/img/flags/br.svg");
  }
  assert.equal(flag("pt-PT"), "/static/img/flags/pt.svg");
  assert.equal(flag("en-US"), "/static/img/flags/us.svg");
  assert.equal(flag("es-MX"), "/static/img/flags/mx.svg");
  assert.equal(flag("French (Canada)"), "/static/img/flags/ca.svg");
});

test("unknown and multilingual labels never fabricate a flag or asset path", () => {
  for (const language of [
    null,
    undefined,
    "",
    "und",
    "Unknown language",
    "mul",
    "Multiple languages",
    "English, Portuguese",
    "en-XX",
    "../../other",
    "<img src=x>",
  ]) {
    assert.equal(flag(language), "");
  }
});

test("every mapped flag is bundled locally with its license", () => {
  const aliases = context.window.UAPreviewLanguageFlagData.languages;
  for (const [, , ...languages] of aliases) {
    for (const language of languages) {
      const asset = path.join(__dirname, "../web_ui", flag(language));
      assert.ok(fs.existsSync(asset), `Missing asset for ${language}`);
      assert.match(fs.readFileSync(asset, "utf8"), /<svg\b/);
    }
  }
  const license = fs.readFileSync(
    path.join(__dirname, "../web_ui/static/img/flags/LICENSE"),
    "utf8",
  );
  assert.match(license, /Copyright \(c\) 2013 Panayiotis Lipiridis/);
  assert.match(license, /The MIT License/);
});

test("less common languages, native names and regional languages are recognized", () => {
  const examples = {
    Catalan: "es-ct",
    cat: "es-ct",
    Basque: "es-pv",
    baq: "es-pv",
    Galician: "es-ga",
    Welsh: "gb-wls",
    wel: "gb-wls",
    "Scottish Gaelic": "gb-sct",
    gla: "gb-sct",
    Irish: "ie",
    Khmer: "kh",
    khm: "kh",
    Kazakh: "kz",
    kaz: "kz",
    Amharic: "et",
    Swahili: "tz",
    Zulu: "za",
    Burmese: "mm",
    guj: "in",
    Punjabi: "in",
    Hawaiian: "us",
    Twi: "gh",
    Montenegrin: "me",
    cnr: "me",
    Dari: "af",
    prs: "af",
    Persian: "ir",
    Farsi: "ir",
    swc: "cd",
    Gã: "gh",
    Deutsch: "de",
    Français: "fr",
    日本語: "jp",
    한국어: "kr",
    Русский: "ru",
    Español: "es",
    "Norwegian Bokmål": "no",
  };
  for (const [language, country] of Object.entries(examples)) {
    assert.equal(flag(language), `/static/img/flags/${country}.svg`, language);
  }
});

test("region and script tags preserve variants beyond the initial manual list", () => {
  const examples = {
    "en-AU": "au",
    "eng-NZ": "nz",
    "fr-BE": "be",
    "fr-CH": "ch",
    "es-AR": "ar",
    "de-AT": "at",
    "ar-EG": "eg",
    "zh-Hant": "tw",
    "zh-Hans": "cn",
    "zh-Hant-HK": "hk",
    "sr-Latn-RS": "rs",
    "Portuguese (Brasil)": "br",
    "Português (Portugal)": "pt",
    "English (Australia)": "au",
    "French (Belgium)": "be",
    "English (Scotland)": "gb-sct",
    "French (Quebec)": "ca-qc",
    "fr-CA-QC": "ca-qc",
    "Quebec French": "ca-qc",
    "en-GB-SCT": "gb-sct",
    "Traditional Chinese": "tw",
    Cantonese: "hk",
  };
  for (const [language, country] of Object.entries(examples)) {
    assert.equal(flag(language), `/static/img/flags/${country}.svg`, language);
  }
  assert.equal(flag("Portuguese", "pt-BR"), "/static/img/flags/br.svg");
  assert.equal(flag("English", "en-AU"), "/static/img/flags/au.svg");
  assert.equal(flag("Portuguese (Brazil)", "por"), "/static/img/flags/br.svg");
});

test("ambiguous regions and special languages do not inherit an arbitrary country", () => {
  for (const language of [
    "en-419",
    "English (Latin America)",
    "English (Unknown)",
    "und-US",
    "mul-GB",
    "zxx",
    "No linguistic content",
    "mis",
    "Esperanto",
    "eo",
    "Klingon",
    "tlh",
    "qaa",
    "en-XX",
    "English / French",
    "English + Portuguese",
    "en-US/pt-BR",
    "English commentary",
    "<script>alert(1)</script>",
  ]) {
    assert.equal(flag(language), "", language);
  }
});

test("Latin American Spanish uses Mexico as its representative flag", () => {
  for (const language of [
    "es-419",
    "spa-419",
    "es_419",
    "es-Latn-419",
    "Spanish (Latin America)",
    "Español (América Latina)",
    "Latin American Spanish",
    "Español latinoamericano",
  ]) {
    assert.equal(flag(language), "/static/img/flags/mx.svg", language);
  }
  assert.equal(flag("Spanish", "es-419"), "/static/img/flags/mx.svg");
  assert.equal(
    flag("Spanish (Latin America)", "spa"),
    "/static/img/flags/mx.svg",
  );
  assert.equal(flag("es-ES"), "/static/img/flags/es.svg");
  assert.equal(flag("es-AR"), "/static/img/flags/ar.svg");
});

test("all region and script mappings resolve to bundled assets", () => {
  const data = context.window.UAPreviewLanguageFlagData;
  for (const [country] of data.regions) {
    assert.ok(
      fs.existsSync(
        path.join(__dirname, `../web_ui/static/img/flags/${country}.svg`),
      ),
    );
    assert.equal(flag(`en-${country}`), `/static/img/flags/${country}.svg`);
  }
  for (const [tag, country] of data.scripts) {
    assert.equal(flag(tag), `/static/img/flags/${country}.svg`, tag);
  }
  assert.ok(data.languages.length >= 600);
  assert.ok(
    fs.existsSync(
      path.join(__dirname, "../web_ui/static/img/flags/UNICODE-LICENSE"),
    ),
  );
});
