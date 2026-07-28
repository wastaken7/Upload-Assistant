import asyncio
from types import SimpleNamespace

from src.trackers.makingoff import MakingOff


def test_index_parser_keeps_only_the_exact_imdb_match():
    html = """
    <div class="filme-card">
      <h4 class="card-title"><a href="/topicos/73517/">Até o Último Homem</a></h4>
      <a href="?ano=1951">1951</a>
      <a href="https://www.imdb.com/title/tt0042539">Página Oficial</a>
    </div>
    <div class="filme-card">
      <h4 class="card-title"><a href="/topicos/99999/">Outro Filme</a></h4>
      <a href="?ano=1951">1951</a>
      <a href="https://www.imdb.com/title/tt9999999">Página Oficial</a>
    </div>
    """

    assert MakingOff._parse_index_results(html, "tt0042539") == {  # noqa: S101
        "Até o Último Homem (1951)": "https://www.makingoff.org/topicos/73517/"
    }


def test_exact_imdb_result_uses_post_resolution_and_skips_year_filter():
    tracker = MakingOff({"TRACKERS": {"MAKINGOFF": {}}})
    topic_url = "https://www.makingoff.org/topicos/12345/"
    meta = SimpleNamespace(
        resolution="1080p",
        video_width=1920,
        video_height=1080,
        year=2020,
        title="Known",
        original_title="Known",
        origin_country=["US"],
        production_countries=[],
        original_language="en",
        imdb_tt="tt1234567",
        debug=False,
        skipping=None,
    )

    async def valid_credentials(_meta):
        return True

    async def display_title(_meta):
        return "Known"

    async def forum_id(_meta):
        return 26

    async def index_search(_imdb_tt):
        return {"Known": topic_url}

    async def title_search(*_args, **_kwargs):
        return {"[Hidef] Known (2020)": topic_url}

    async def post_resolution(_url):
        return 1080

    tracker.validate_credentials = valid_credentials
    tracker._resolve_display_title = display_title
    tracker.get_forum_id = forum_id
    tracker.search_index_by_imdb = index_search
    tracker.search_candidate = title_search
    tracker.get_post_resolution = post_resolution

    duplicates = asyncio.run(tracker.search_existing(meta))

    assert duplicates == [{"name": f"[url={topic_url}]Known[/url]", "size": "1080", "link": topic_url}]  # noqa: S101
