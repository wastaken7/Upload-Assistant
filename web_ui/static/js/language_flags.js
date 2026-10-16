// Flags are representative language hints, not claims about a track's origin.
(() => {
  const data = window.UAPreviewLanguageFlagData;
  const normalize = (value) =>
    String(value || "")
      .trim()
      .toLowerCase()
      .normalize("NFC")
      .replace(/_/g, "-")
      .replace(/\s+/g, " ");
  const languages = new Map();
  const regions = new Map();
  const scripts = new Map(data.scripts);
  for (const [code, country, ...aliases] of data.languages) {
    for (const alias of aliases) {
      languages.set(normalize(alias), { code, country });
    }
  }
  for (const [country, ...aliases] of data.regions) {
    for (const alias of aliases) regions.set(normalize(alias), country);
  }
  for (const [country, ...aliases] of [
    ["gb-eng", "England"],
    ["gb-wls", "Wales"],
    ["gb-sct", "Scotland"],
    ["gb-nir", "Northern Ireland"],
    ["es-ct", "Catalonia", "Catalunha", "Cataluña"],
    ["es-ga", "Galicia", "Galiza"],
    ["es-pv", "Basque Country", "País Basco", "País Vasco"],
    ["ca-qc", "Quebec", "Québec"],
    ["gb", "UK", "Great Britain"],
    ["us", "USA"],
  ]) {
    for (const alias of [country, ...aliases]) {
      regions.set(normalize(alias), country);
    }
  }
  const namedVariants = new Map([
    ["latin american spanish", "es-419"],
    ["español latinoamericano", "es-419"],
    ["espanol latinoamericano", "es-419"],
    ["brazilian portuguese", "pt-BR"],
    ["portugues brasileiro", "pt-BR"],
    ["português brasileiro", "pt-BR"],
    ["portugues do brasil", "pt-BR"],
    ["português do brasil", "pt-BR"],
    ["european portuguese", "pt-PT"],
    ["portugues europeu", "pt-PT"],
    ["português europeu", "pt-PT"],
    ["american english", "en-US"],
    ["british english", "en-GB"],
    ["canadian french", "fr-CA"],
    ["quebec french", "fr-CA-QC"],
    ["quebecois", "fr-CA-QC"],
    ["french canadian", "fr-CA"],
    ["castilian", "es-ES"],
    ["farsi", "fa"],
    ["mandarin", "cmn"],
    ["cantonese", "yue"],
    ["simplified chinese", "zh-Hans"],
    ["traditional chinese", "zh-Hant"],
    ["chinese (simplified)", "zh-Hans"],
    ["chinese (traditional)", "zh-Hant"],
    ["brazilian", "pt-BR"],
  ]);

  const getRegionalFlag = (language, region) => {
    const key = normalize(region);
    // Mexico represents Latin American Spanish visually; 419 is a region,
    // not a statement that the track originates in Mexico.
    if (
      language.code === "es" &&
      [
        "419",
        "latin america",
        "américa latina",
        "america latina",
        "latinoamérica",
        "latinoamerica",
      ].includes(key)
    )
      return "mx";
    return regions.get(key) || "";
  };

  const resolve = (value) => {
    const key = normalize(value);
    if (!key || key.length > 200) return null;
    if (namedVariants.has(key)) return resolve(namedVariants.get(key));
    const language = languages.get(key);
    if (language) return { country: language.country, specificity: 1 };

    // Match a whole label, never a word inside a multilingual or unknown label.
    const label = key.match(/^(.+?)\s*\(([^()]+)\)$/);
    if (label) {
      const base = languages.get(label[1].trim());
      if (!base) return null;
      return { country: getRegionalFlag(base, label[2]), specificity: 3 };
    }
    const subdivision = key.match(/^([a-z]{2,3})-((?:gb|es|ca)-[a-z]{2,3})$/);
    if (subdivision && languages.has(subdivision[1])) {
      return { country: regions.get(subdivision[2]) || "", specificity: 3 };
    }
    try {
      const locale = new Intl.Locale(key);
      const base = languages.get(locale.language);
      if (!base) return null;
      if (locale.region) {
        return {
          country: getRegionalFlag(base, locale.region),
          specificity: 3,
        };
      }
      if (locale.script) {
        return {
          country:
            scripts.get(`${base.code}-${locale.script.toLowerCase()}`) ||
            base.country,
          specificity: 2,
        };
      }
      return { country: base.country, specificity: 1 };
    } catch (_error) {
      return null;
    }
  };

  window.getUAPreviewLanguageFlag = (language, languageCode) => {
    const label = resolve(language);
    const code = resolve(languageCode);
    // MediaInfo's raw code can preserve a region lost in its display name.
    const selected =
      code && (!label || code.specificity >= label.specificity) ? code : label;
    return selected?.country ? `/static/img/flags/${selected.country}.svg` : "";
  };
})();
