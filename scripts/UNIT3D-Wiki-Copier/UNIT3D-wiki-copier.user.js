// ==UserScript==
// @name         UNIT3D Wiki Copier
// @namespace    upload-assistant
// @version      1.0.0
// @description  Copy UNIT3D wiki and rules pages as BBCode or Markdown.
// @match        *://*/wikis*
// @match        *://*/wiki*
// @match        *://*/pages*
// @match        *://*/articles*
// @match        *://*/rules*
// @grant        none
// ==/UserScript==

(function () {
  "use strict";

  // Helper to normalize and clean whitespace and consecutive newlines
  function cleanOutput(text) {
    return text
      .replace(/\r\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  // Copy to clipboard helper with visual feedback
  async function copyToClipboard(text, button, originalText) {
    try {
      await navigator.clipboard.writeText(text);
      const icon = button.querySelector("i");
      const iconClass = icon ? icon.className : "";
      if (icon) icon.className = "fa fa-check";
      button.childNodes[button.childNodes.length - 1].nodeValue = " Copied!";
      button.classList.add("form__button--filled");
      button.classList.remove("form__button--outlined");

      setTimeout(() => {
        if (icon) icon.className = iconClass;
        button.childNodes[button.childNodes.length - 1].nodeValue =
          originalText;
        button.classList.remove("form__button--filled");
        button.classList.add("form__button--outlined");
      }, 2000);
    } catch (err) {
      console.error("Failed to copy text: ", err);
      alert("Failed to copy to clipboard. Please check browser permissions.");
    }
  }

  // HTML to BBCode recursive converter
  function convertNodeToBBCode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.textContent;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return "";
    }

    let innerContent = "";
    for (let child of node.childNodes) {
      innerContent += convertNodeToBBCode(child);
    }

    const tag = node.tagName;
    switch (tag) {
      case "H1":
        return `[h1]${innerContent}[/h1]`;
      case "H2":
        return `[h2]${innerContent}[/h2]`;
      case "H3":
        return `[h3]${innerContent}[/h3]`;
      case "H4":
        return `[h4]${innerContent}[/h4]`;
      case "H5":
        return `[h5]${innerContent}[/h5]`;
      case "H6":
        return `[h6]${innerContent}[/h6]`;
      case "B":
      case "STRONG":
        return `[b]${innerContent}[/b]`;
      case "I":
      case "EM":
      case "DFN":
        return `[i]${innerContent}[/i]`;
      case "U":
        return `[u]${innerContent}[/u]`;
      case "S":
      case "DEL":
      case "STRIKE":
        return `[s]${innerContent}[/s]`;
      case "SUB":
        return `[sub]${innerContent}[/sub]`;
      case "SUP":
        return `[sup]${innerContent}[/sup]`;
      case "SMALL":
        return `[small]${innerContent}[/small]`;
      case "SPAN": {
        const style = node.getAttribute("style") || "";
        let open = "";
        let close = "";

        const sizeMatch =
          style.match(/font-size:\s*clamp\(\d+px,\s*(\d+)px,\s*\d+px\)/i) ||
          style.match(/font-size:\s*(\d+)(?:px|pt)?/i);
        if (sizeMatch) {
          open += `[size=${sizeMatch[1]}]`;
          close = `[/size]` + close;
        }

        const fontMatch = style.match(/font-family:\s*([^;]+)/i);
        if (fontMatch) {
          const font = fontMatch[1].replace(/['"]/g, "").trim();
          open += `[font=${font}]`;
          close = `[/font]` + close;
        }

        const colorMatch = style.match(/color:\s*([^;]+)/i);
        if (colorMatch) {
          const color = colorMatch[1].trim();
          open += `[color=${color}]`;
          close = `[/color]` + close;
        }

        return `${open}${innerContent}${close}`;
      }
      case "DIV":
      case "P": {
        let open = "";
        let close = "";

        if (
          node.classList.contains("bbcode-rendered__center") ||
          node.style.textAlign === "center"
        ) {
          open = "[center]";
          close = "[/center]";
        } else if (
          node.classList.contains("bbcode-rendered__left") ||
          node.style.textAlign === "left"
        ) {
          open = "[left]";
          close = "[/left]";
        } else if (
          node.classList.contains("bbcode-rendered__right") ||
          node.style.textAlign === "right"
        ) {
          open = "[right]";
          close = "[/right]";
        } else if (node.classList.contains("bbcode-rendered__alert")) {
          open = "[alert]";
          close = "[/alert]";
        } else if (node.classList.contains("bbcode-rendered__note")) {
          open = "[note]";
          close = "[/note]";
        } else if (node.classList.contains("bbcode-rendered__clipboard")) {
          const codeEl = node.querySelector("code");
          if (codeEl) {
            return `[code]${codeEl.textContent}[/code]\n`;
          }
        }

        return `${open}${innerContent}${close}\n`;
      }
      case "BLOCKQUOTE": {
        const citeEl = node.querySelector("cite");
        if (citeEl) {
          const nameMatch = citeEl.textContent.match(/Quoting\s+(.*?):/i);
          if (nameMatch) {
            const pEl = node.querySelector("p");
            const quoteBody = pEl ? convertNodeToBBCode(pEl) : innerContent;
            return `[quote=${nameMatch[1].trim()}]${quoteBody}[/quote]\n`;
          }
        }
        return `[quote]${innerContent}[/quote]\n`;
      }
      case "UL":
        return `[list]\n${innerContent}[/list]\n`;
      case "OL": {
        const type = node.getAttribute("type");
        if (type === "a") return `[list=a]\n${innerContent}[/list]\n`;
        return `[list=1]\n${innerContent}[/list]\n`;
      }
      case "LI": {
        return `[*]${innerContent}\n`;
      }
      case "A": {
        const href = node.getAttribute("href");
        if (!href) return innerContent;
        if (
          href === innerContent ||
          href === decodeURIComponent(innerContent)
        ) {
          return `[url]${href}[/url]`;
        }
        return `[url=${href}]${innerContent}[/url]`;
      }
      case "IMG": {
        if (
          node.classList.contains("joypixels") ||
          node.src.includes("joypixels")
        ) {
          return node.title || node.alt || "";
        }
        const src = node.getAttribute("src");
        if (!src) return "";
        const width = node.getAttribute("width");
        if (width) {
          const w = parseInt(width);
          return `[img width=${w}]${src}[/img]`;
        }
        return `[img]${src}[/img]`;
      }
      case "HR":
        return "[hr]\n";
      case "BR":
        return "\n";
      case "TABLE":
        return `[table]\n${innerContent}[/table]\n`;
      case "TR":
        return `[tr]\n${innerContent}[/tr]\n`;
      case "TH":
        return `[th]${innerContent}[/th]`;
      case "TD":
        return `[td]${innerContent}[/td]`;
      case "DETAILS": {
        const summaryEl = node.querySelector("summary");
        const summaryText = summaryEl ? summaryEl.textContent : "";
        const bodyEl = node.querySelector("div");
        const bodyContent = bodyEl ? convertNodeToBBCode(bodyEl) : innerContent;
        if (summaryText && summaryText !== "Spoiler") {
          return `[spoiler=${summaryText}]${bodyContent}[/spoiler]`;
        }
        return `[spoiler]${bodyContent}[/spoiler]`;
      }
      case "IFRAME": {
        const src = node.getAttribute("src") || "";
        const ytMatch =
          src.match(/youtube-nocookie\.com\/embed\/([a-zA-Z0-9_-]{11})/i) ||
          src.match(/youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/i);
        if (ytMatch) {
          return `[youtube]${ytMatch[1]}[/youtube]`;
        }
        return "";
      }
      case "PRE": {
        const codeEl = node.querySelector("code");
        if (codeEl) {
          return `[code]${codeEl.textContent}[/code]\n`;
        }
        return `[pre]${innerContent}[/pre]\n`;
      }
      case "CODE": {
        return `[pre]${innerContent}[/pre]`;
      }
      default:
        return innerContent;
    }
  }

  // HTML to Markdown recursive converter
  function convertNodeToMarkdown(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.textContent;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return "";
    }

    let innerContent = "";
    for (let child of node.childNodes) {
      innerContent += convertNodeToMarkdown(child);
    }

    const tag = node.tagName;
    switch (tag) {
      case "H1":
        return `\n# ${innerContent.trim()}\n`;
      case "H2":
        return `\n## ${innerContent.trim()}\n`;
      case "H3":
        return `\n### ${innerContent.trim()}\n`;
      case "H4":
        return `\n#### ${innerContent.trim()}\n`;
      case "H5":
        return `\n##### ${innerContent.trim()}\n`;
      case "H6":
        return `\n###### ${innerContent.trim()}\n`;
      case "B":
      case "STRONG":
        return `**${innerContent}**`;
      case "I":
      case "EM":
      case "DFN":
        return `*${innerContent}*`;
      case "U":
        return `<u>${innerContent}</u>`;
      case "S":
      case "DEL":
      case "STRIKE":
        return `~~${innerContent}~~`;
      case "SUB":
        return `<sub>${innerContent}</sub>`;
      case "SUP":
        return `<sup>${innerContent}</sup>`;
      case "SMALL":
        return `<small>${innerContent}</small>`;
      case "SPAN": {
        const style = node.getAttribute("style") || "";
        if (style) {
          return `<span style="${style}">${innerContent}</span>`;
        }
        return innerContent;
      }
      case "DIV":
      case "P": {
        let open = "";
        let close = "";

        if (
          node.classList.contains("bbcode-rendered__center") ||
          node.style.textAlign === "center"
        ) {
          open = '<div align="center">\n\n';
          close = "\n\n</div>";
        } else if (
          node.classList.contains("bbcode-rendered__left") ||
          node.style.textAlign === "left"
        ) {
          open = '<div align="left">\n\n';
          close = "\n\n</div>";
        } else if (
          node.classList.contains("bbcode-rendered__right") ||
          node.style.textAlign === "right"
        ) {
          open = '<div align="right">\n\n';
          close = "\n\n</div>";
        } else if (node.classList.contains("bbcode-rendered__alert")) {
          open = "> **[ALERT]**\n> ";
          return `\n${open}${innerContent.trim().replace(/\n/g, "\n> ")}\n`;
        } else if (node.classList.contains("bbcode-rendered__note")) {
          open = "> **[NOTE]**\n> ";
          return `\n${open}${innerContent.trim().replace(/\n/g, "\n> ")}\n`;
        } else if (node.classList.contains("bbcode-rendered__clipboard")) {
          const codeEl = node.querySelector("code");
          if (codeEl) {
            return `\n\`\`\`\n${codeEl.textContent}\n\`\`\`\n`;
          }
        }

        return `\n${open}${innerContent}${close}\n`;
      }
      case "BLOCKQUOTE": {
        const citeEl = node.querySelector("cite");
        let quoteHeader = "";
        let quoteBody = innerContent;
        if (citeEl) {
          const nameMatch = citeEl.textContent.match(/Quoting\s+(.*?):/i);
          if (nameMatch) {
            quoteHeader = `**${nameMatch[1].trim()} wrote:**\n`;
            const pEl = node.querySelector("p");
            quoteBody = pEl ? convertNodeToMarkdown(pEl) : innerContent;
          }
        }
        const lines = quoteBody.trim().split("\n");
        const prefixed = lines.map((line) => `> ${line}`).join("\n");
        return `\n${quoteHeader}${prefixed}\n`;
      }
      case "UL":
        return `\n${innerContent}\n`;
      case "OL":
        return `\n${innerContent}\n`;
      case "LI": {
        const parent = node.parentNode;
        if (parent && parent.tagName === "OL") {
          const lis = Array.from(parent.children).filter(
            (c) => c.tagName === "LI",
          );
          const idx = lis.indexOf(node) + 1;
          return `${idx}. ${innerContent}\n`;
        }
        return `- ${innerContent}\n`;
      }
      case "A": {
        const href = node.getAttribute("href");
        if (!href) return innerContent;
        if (
          href === innerContent ||
          href === decodeURIComponent(innerContent)
        ) {
          return `<${href}>`;
        }
        return `[${innerContent}](${href})`;
      }
      case "IMG": {
        if (
          node.classList.contains("joypixels") ||
          node.src.includes("joypixels")
        ) {
          return node.title || node.alt || "";
        }
        const src = node.getAttribute("src");
        if (!src) return "";
        const alt = node.getAttribute("alt") || "image";
        const width = node.getAttribute("width");
        if (width) {
          return `<img src="${src}" width="${width}" alt="${alt}" />`;
        }
        return `![${alt}](${src})`;
      }
      case "HR":
        return "\n---\n";
      case "BR":
        return "\n";
      case "TABLE": {
        const rows = Array.from(node.querySelectorAll("tr"));
        if (rows.length === 0) return "";

        let mdTable = "\n";
        let headerParsed = false;

        for (let row of rows) {
          const cells = Array.from(row.childNodes).filter(
            (c) => c.tagName === "TD" || c.tagName === "TH",
          );
          if (cells.length === 0) continue;

          const cellTexts = cells.map((cell) =>
            convertNodeToMarkdown(cell).replace(/\n/g, " ").trim(),
          );
          mdTable += `| ${cellTexts.join(" | ")} |\n`;

          if (!headerParsed) {
            const separators = cells.map(() => "---");
            mdTable += `| ${separators.join(" | ")} |\n`;
            headerParsed = true;
          }
        }
        return mdTable + "\n";
      }
      case "TH":
      case "TD":
        return innerContent;
      case "DETAILS": {
        const summaryEl = node.querySelector("summary");
        const summaryText = summaryEl ? summaryEl.textContent : "Spoiler";
        const bodyEl = node.querySelector("div");
        const bodyContent = bodyEl
          ? convertNodeToMarkdown(bodyEl)
          : innerContent;
        return `\n<details>\n<summary>${summaryText}</summary>\n\n${bodyContent.trim()}\n\n</details>\n`;
      }
      case "IFRAME": {
        const src = node.getAttribute("src") || "";
        const ytMatch =
          src.match(/youtube-nocookie\.com\/embed\/([a-zA-Z0-9_-]{11})/i) ||
          src.match(/youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/i);
        if (ytMatch) {
          const link = `https://www.youtube.com/watch?v=${ytMatch[1]}`;
          return `[YouTube Video](${link})`;
        }
        return "";
      }
      case "PRE": {
        const codeEl = node.querySelector("code");
        if (codeEl) {
          return `\n\`\`\`\n${codeEl.textContent}\n\`\`\`\n`;
        }
        return `\n\`\`\`\n${innerContent}\n\`\`\`\n`;
      }
      case "CODE": {
        return `\`${innerContent}\``;
      }
      default:
        return innerContent;
    }
  }

  // Initialize and inject elements
  function init() {
    // Confirm we are on a UNIT3D site
    if (
      !document.querySelector('meta[name="_base_url"]') &&
      !document.querySelector('meta[name="csrf-token"]')
    ) {
      return;
    }

    // Confirm this is a wiki, pages, rules, or articles page (where editing is generally restricted)
    const isTargetPage = window.location.pathname.match(
      /\/(wikis|wiki|pages|articles|rules)(\/|$)/i,
    );
    if (!isTargetPage) {
      return;
    }

    const renderedBlocks = document.querySelectorAll(
      ".bbcode-rendered:not([data-copier-processed])",
    );
    renderedBlocks.forEach((block) => {
      block.setAttribute("data-copier-processed", "true");

      // Create toolbar container
      const toolbar = document.createElement("div");
      toolbar.className = "userscript-copier-toolbar";
      toolbar.style.display = "flex";
      toolbar.style.gap = "8px";
      toolbar.style.justifyContent = "flex-end";
      toolbar.style.marginBottom = "12px";

      // Copy BBCode button
      const bbBtn = document.createElement("button");
      bbBtn.className =
        "form__button form__button--outlined form__button--centered";
      bbBtn.style.fontSize = "12px";
      bbBtn.style.padding = "4px 8px";
      bbBtn.style.minHeight = "unset";
      bbBtn.style.lineHeight = "1.2";
      bbBtn.style.cursor = "pointer";
      bbBtn.innerHTML =
        '<i class="fa fa-code" style="margin-right: 4px;"></i> Copy BBCode';
      bbBtn.addEventListener("click", () => {
        const rawBBCode = cleanOutput(convertNodeToBBCode(block));
        copyToClipboard(rawBBCode, bbBtn, " Copy BBCode");
      });

      // Copy Markdown button
      const mdBtn = document.createElement("button");
      mdBtn.className =
        "form__button form__button--outlined form__button--centered";
      mdBtn.style.fontSize = "12px";
      mdBtn.style.padding = "4px 8px";
      mdBtn.style.minHeight = "unset";
      mdBtn.style.lineHeight = "1.2";
      mdBtn.style.cursor = "pointer";
      mdBtn.innerHTML =
        '<i class="fa fa-copy" style="margin-right: 4px;"></i> Copy Markdown';
      mdBtn.addEventListener("click", () => {
        const markdown = cleanOutput(convertNodeToMarkdown(block));
        copyToClipboard(markdown, mdBtn, " Copy Markdown");
      });

      toolbar.appendChild(bbBtn);
      toolbar.appendChild(mdBtn);

      // Insert toolbar before the bbcode-rendered block
      block.parentNode.insertBefore(toolbar, block);
    });
  }

  // Run on startup
  init();

  // Observe changes to support dynamically loaded components / Livewire pages
  const observer = new MutationObserver(() => {
    init();
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
