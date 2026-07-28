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
