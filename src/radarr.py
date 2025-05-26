import httpx
from data.config import config
from src.console import console


async def get_radarr_data(tmdb_id=None, filename=None, debug=False):
    if config['DEFAULT'].get('radarr_api_key', ""):
        if tmdb_id:
            url = f"{config['DEFAULT']['radarr_url']}/api/v3/movie?tmdbId={tmdb_id}&excludeLocalCovers=true"
        elif filename:
            url = f"{config['DEFAULT']['radarr_url']}/api/v3/movie/lookup?term={filename}"
        headers = {
            "X-Api-Key": config['DEFAULT']['radarr_api_key'],
            "Content-Type": "application/json"
        }
        if debug:
            console.print(f"[green]TMDB ID {tmdb_id}[/green]")
            console.print(f"[blue]Radarr URL:[/blue] {url}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10.0)

                if response.status_code == 200:
                    data = response.json()
                    if debug:
                        console.print(f"[blue]Radarr Response Status:[/blue] {response.status_code}")
                        console.print(f"[blue]Radarr Response Data:[/blue] {data}")
                    return data
                else:
                    console.print(f"[yellow]Failed to fetch Radarr movie: {response.status_code} - {response.text}[/yellow]")
                    return None
        except httpx.RequestError as e:
            console.print(f"[red]Error fetching Radarr movie: {e}[/red]")
            return None
        except httpx.TimeoutException:
            console.print(f"[red]Timeout when fetching Radarr movie for TMDB ID {tmdb_id}[/red]")
            return None
        except Exception as e:
            console.print(f"[red]Unexpected error fetching Radarr movie: {e}[/red]")
            return None
    else:
        console.print("[red]Radarr API key is not configured.[/red]")
        return None


async def extract_movie_data(radarr_data, filename=None):
    if not radarr_data or not isinstance(radarr_data, list) or len(radarr_data) == 0:
        return {
            "imdb_id": None,
            "tmdb_id": None,
            "year": None,
            "genres": [],
            "release_group": None
        }

    if filename:
        for item in radarr_data:
            if item.get("movieFile") and item["movieFile"].get("originalFilePath") == filename:
                movie = item
                break
        else:
            return None
    else:
        movie = radarr_data[0]

    release_group = None
    if movie.get("movieFile") and movie["movieFile"].get("releaseGroup"):
        release_group = movie["movieFile"]["releaseGroup"]

    return {
        "imdb_id": int(movie.get("imdbId", "tt0").replace("tt", "")) if movie.get("imdbId") else None,
        "tmdb_id": movie.get("tmdbId", None),
        "year": movie.get("year", None),
        "genres": movie.get("genres", []),
        "release_group": release_group if release_group else None
    }
