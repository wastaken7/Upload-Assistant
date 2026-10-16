# ruff: noqa: S101
import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from src.meta import Meta
from src.trackers.hdtorrents import HDTorrents

PAGE = """
<html><body>
<input type="hidden" name="csrfToken" value="token123">
<table class="hdblock"><tr><td>
  <div class="switchcontent" id="view_torrents"><table>
    <tr><td class="mainblockcontent"><a href="details.php?id=900">Other Film 1990 2160p UHD BluRay x265-NOGRPZ</a></td></tr>
  </table></div>
</td></tr></table>
<table>
  <tr><td class="mainblockcontent">Filename</td></tr>
  <tr>
    <td class="mainblockcontent"><a href="details.php?id=1">Fictional Film 2021 1080p BluRay DD 5.1 x264-NOGRPA</a></td>
    <td class="mainblockcontent">8.2 GiB</td>
  </tr>
</table>
</body></html>
"""


def test_latest_torrents_widget_is_not_a_search_result(tmp_path: Any) -> None:
    tracker = HDTorrents({"DEFAULT": {}, "TRACKERS": {"HDTORRENTS": {}}})
    tracker.cookie_validator.load_session_cookies = AsyncMock(return_value=None)
    response = MagicMock(text=PAGE, url="https://example.invalid/torrents.php")
    response.raise_for_status = lambda: None
    tracker.session.get = AsyncMock(return_value=response)

    results = asyncio.run(tracker.search_existing(Meta(category="MOVIE", imdb_id=1234567, imdb_tt="tt1234567", base_dir=str(tmp_path))))

    assert [result["name"] for result in results] == ["Fictional Film 2021 1080p BluRay DD 5.1 x264-NOGRPA"]
    assert results[0]["size"] == "8.2 GiB"
