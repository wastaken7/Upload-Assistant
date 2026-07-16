# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any
from xml.etree import ElementTree

from src.meta import Meta


def get_newznab_search_category_id(meta: Meta) -> str:
    category = meta.category.upper()
    resolution = meta.resolution.lower()
    uhd_resolutions = {"2160p", "4320p", "8640p"}
    hd_resolutions = {"1080p", "1080i", "720p", "1440p"}

    if category == "MOVIE":
        if resolution in uhd_resolutions:
            return "2045"
        if resolution in hd_resolutions:
            return "2040"
        return "2030"
    if category == "TV":
        if resolution in uhd_resolutions:
            return "5045"
        if resolution in hd_resolutions:
            return "5040"
        return "5030"
    if category == "BOOK":
        if meta.audiobook:
            return "3030"
        return "7020"
    if category == "GAME":
        return "4050"
    if category == "MUSIC":
        return "3000"
    return "2000"


def build_newznab_search_query(meta: Meta) -> str:
    title = str(meta.title or meta.original_title or "").strip()
    year = int(meta.year or meta.search_year or 0)

    if meta.category.upper() == "TV":
        if title and meta.season_int > 0 and meta.episode_int > 0:
            return f"{title} S{meta.season_int:02d}E{meta.episode_int:02d}"
        if title and meta.season_int > 0:
            return f"{title} S{meta.season_int:02d}"
        if title:
            return title
    elif meta.category.upper() == "MOVIE":
        if title and year > 0:
            return f"{title} {year}"
        if title:
            return title

    return str(meta.basename_no_ext or title).strip()


def parse_newznab_dupes(
    response_text: str,
    torrent_url: str | None = None,
    *,
    use_guid_attr_as_id: bool = False,
) -> list[dict[str, Any]]:
    dupes: list[dict[str, Any]] = []
    response_xml = ElementTree.fromstring(response_text)
    channel = response_xml.find("channel")
    if channel is None:
        return dupes

    for item in channel.findall("item"):
        title = str(item.findtext("title") or "")
        guid = str(item.findtext("guid") or "")
        item_link = guid
        size_text = "0"

        enclosure = item.find("enclosure")
        if enclosure is not None:
            size_text = str(enclosure.attrib.get("length") or "0")

        for attr in item.findall("{http://www.newznab.com/DTD/2010/feeds/attributes/}attr"):
            attr_name = str(attr.attrib.get("name") or "").lower()
            attr_value = str(attr.attrib.get("value") or "")
            if attr_name == "size" and attr_value:
                size_text = attr_value
            elif use_guid_attr_as_id and attr_name == "guid" and attr_value and not guid:
                guid = attr_value

        if item_link and not item_link.startswith(("http://", "https://")) and guid and torrent_url:
            item_link = f"{torrent_url}{guid}"

        dupes.append({
            "name": title,
            "files": title,
            "size": int(size_text) if size_text.isdigit() else 0,
            "link": item_link,
        })

    return dupes
