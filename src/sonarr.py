import httpx
from data.config import config
from src.console import console


async def get_sonarr_data(tvdb_id=None, filename=None, title=None, debug=False):
    if config['DEFAULT'].get('sonarr_api_key', ""):
        if tvdb_id:
            url = f"{config['DEFAULT']['sonarr_url']}/api/v3/series?tvdbId={tvdb_id}&includeSeasonImages=false"
        elif filename:
            url = f"{config['DEFAULT']['sonarr_url']}/api/v3/parse?title={title}&path={filename}"
        headers = {
            "X-Api-Key": config['DEFAULT']['sonarr_api_key'],
            "Content-Type": "application/json"
        }
        if debug:
            console.print(f"[green]TVDB ID {tvdb_id}[/green]")
            console.print(f"[blue]Sonarr URL:[/blue] {url}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10.0)

                if response.status_code == 200:
                    data = response.json()
                    if debug:
                        console.print(f"[blue]Sonarr Response Status:[/blue] {response.status_code}")
                        console.print(f"[blue]Sonarr Response Data:[/blue] {data}")
                    return data
                else:
                    console.print(f"[yellow]Failed to fetch Sonarr series: {response.status_code} - {response.text}[/yellow]")
                    return None
        except httpx.RequestError as e:
            console.print(f"[red]Error fetching Sonarr series: {e}[/red]")
            return None
        except httpx.TimeoutException:
            console.print(f"[red]Timeout when fetching Sonarr series for TVDB ID {tvdb_id}[/red]")
            return None
        except Exception as e:
            console.print(f"[red]Unexpected error fetching Sonarr series: {e}[/red]")
            return None
    else:
        console.print("[red]Sonarr API key is not configured.[/red]")
        return None


async def extract_show_data(sonarr_data):
    if not sonarr_data:
        return {
            "tvdb_id": None,
            "imdb_id": None,
            "tvmaze_id": None,
            "tmdb_id": None,
            "genres": [],
            "title": "",
            "year": None,
            "release_group": None
        }

    # Handle response from /api/v3/parse endpoint
    if isinstance(sonarr_data, dict) and 'series' in sonarr_data:
        series = sonarr_data['series']
        release_group = sonarr_data.get('parsedEpisodeInfo', {}).get('releaseGroup')

        return {
            "tvdb_id": series.get("tvdbId", None),
            "imdb_id": int(series.get("imdbId", "tt0").replace("tt", "")) if series.get("imdbId") else None,
            "tvmaze_id": series.get("tvMazeId", None),
            "tmdb_id": series.get("tmdbId", None),
            "genres": series.get("genres", []),
            "release_group": release_group if release_group else None,
            "year": series.get("year", None)
        }

    # Handle response from /api/v3/series endpoint (list format)
    elif isinstance(sonarr_data, list) and len(sonarr_data) > 0:
        series = sonarr_data[0]

        return {
            "tvdb_id": series.get("tvdbId", None),
            "imdb_id": int(series.get("imdbId", "tt0").replace("tt", "")) if series.get("imdbId") else None,
            "tvmaze_id": series.get("tvMazeId", None),
            "tmdb_id": series.get("tmdbId", None),
            "genres": series.get("genres", []),
            "title": series.get("title", ""),
            "year": series.get("year", None),
            "release_group": series.get("releaseGroup") if series.get("releaseGroup") else None
        }

    # Return empty data if the format doesn't match any expected structure
    return {
        "tvdb_id": None,
        "imdb_id": None,
        "tvmaze_id": None,
        "tmdb_id": None,
        "genres": [],
        "title": "",
        "year": None,
        "release_group": None
    }
