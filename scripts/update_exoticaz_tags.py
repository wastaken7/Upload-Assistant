#!/usr/bin/env python3
"""Refresh data/exoticaz_tags.json from the ExoticaZ tag list, one page at a time."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import platform
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

TAGS_URL = "https://exoticaz.to/tags"
PAGE_DELAY_SECONDS = 2


def parse_page(html: str) -> tuple[list[dict[str, Any]], int]:
    """Return the page's main tags with their synonyms, and the last page number."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    tbody = table.find("tbody") if table else None
    if not tbody:
        raise ValueError("Tag table not found; the cookies may be expired")

    tags: list[dict[str, Any]] = []
    for row in tbody.find_all("tr", recursive=False):
        name_tag = row.find("div", class_="tag")
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        # Main tags are highlighted rows with a search link; their synonyms follow as secondary rows.
        if "table-primary" in (row.get("class") or []):
            link = row.find("a", href=re.compile(r"tags\[\]=\d+"))
            if not link:
                raise ValueError(f"Tag ID not found for {name!r}")
            cells = row.find_all("td", recursive=False)
            usage = cells[2].get_text(strip=True).replace(",", "") if len(cells) > 2 else ""
            tag_id = re.search(r"tags\[\]=(\d+)", str(link["href"]))
            tags.append({"id": int(tag_id.group(1)) if tag_id else 0, "tag": name, "usage": int(usage) if usage.isdigit() else 0, "synonyms": []})
        elif tags:
            tags[-1]["synonyms"].append(name)

    pages = [int(page) for page in re.findall(r"page=(\d+)", html)]
    return tags, max(pages, default=1)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cookies", required=True, type=Path, help="Netscape cookie file exported from a logged-in ExoticaZ session")
    parser.add_argument("--output", type=Path, default=root / "data/exoticaz_tags.json")
    args = parser.parse_args()

    jar = http.cookiejar.MozillaCookieJar(str(args.cookies))
    jar.load(ignore_discard=True, ignore_expires=True)
    headers = {"User-Agent": f"Upload-Assistant/2.3 ({platform.system()} {platform.release()})"}

    tags: list[dict[str, Any]] = []
    try:
        with httpx.Client(headers=headers, cookies=jar, timeout=60.0) as client:
            page, last_page = 1, 1
            while page <= last_page:
                # Sorting by name keeps pages stable; the usage order shuffles ties between requests.
                response = client.get(TAGS_URL, params={"order": "tag", "sort": "asc", "page": page})
                response.raise_for_status()
                page_tags, linked_last_page = parse_page(response.text)
                last_page = max(last_page, linked_last_page)
                tags.extend(page_tags)
                print(f"Page {page}/{last_page}: {len(tags)} tags")
                page += 1
                if page <= last_page:
                    time.sleep(PAGE_DELAY_SECONDS)
        if not tags or len({tag["id"] for tag in tags}) != len(tags):
            raise ValueError("The tag list is empty or contains repeated IDs")
    except (OSError, ValueError, httpx.HTTPError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    catalog = {"source": TAGS_URL, "updated": datetime.now(UTC).date().isoformat(), "tags": tags}
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(f"Saved {len(tags)} tags and {sum(len(tag['synonyms']) for tag in tags)} synonyms to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
