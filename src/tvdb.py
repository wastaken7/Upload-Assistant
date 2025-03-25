import httpx
import re
from src.console import console
from data.config import config

config = config


async def get_tvdb_episode_data(base_dir, token, tvdb_id, season, episode, api_key=None, retry_attempted=False):
    console.print(f"[cyan]Fetching TVDb episode data for S{season}E{episode}...[/cyan]")

    url = f"https://api4.thetvdb.com/v4/series/{tvdb_id}/episodes/default"
    params = {
        "page": 1,
        "season": season,
        "episodeNumber": episode
    }
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers, timeout=30.0)

            # Handle unauthorized responses
            if response.status_code == 401:
                # Only attempt a retry once to prevent infinite loops
                if api_key and not retry_attempted:
                    console.print("[yellow]Unauthorized access. Refreshing TVDb token...[/yellow]")
                    new_token = await get_tvdb_token(api_key)
                    if new_token:
                        # Retry the request with the new token
                        return await get_tvdb_episode_data(
                            new_token, tvdb_id, season, episode, api_key, True
                        )
                    else:
                        console.print("[red]Failed to refresh TVDb token[/red]")
                        return None
                else:
                    console.print("[red]Unauthorized access to TVDb API[/red]")
                    return None

            response.raise_for_status()
            data = response.json()

            # Check for "Unauthorized" message in response body
            if data.get("message") == "Unauthorized":
                if api_key and not retry_attempted:
                    console.print("[yellow]Token invalid or expired. Refreshing TVDb token...[/yellow]")
                    new_token = await get_tvdb_token(api_key, base_dir)
                    if new_token:
                        return await get_tvdb_episode_data(
                            new_token, tvdb_id, season, episode, api_key, True
                        )
                    else:
                        console.print("[red]Failed to refresh TVDb token[/red]")
                        return None
                else:
                    console.print("[red]Unauthorized response from TVDb API[/red]")
                    return None

            if data.get("status") == "success" and data.get("data") and data["data"].get("episodes"):
                episode_data = data["data"]["episodes"][0]
                series_data = data["data"].get("series", {})

                result = {
                    "episode_name": episode_data.get("name", ""),
                    "overview": episode_data.get("overview", ""),
                    "season_number": episode_data.get("seasonNumber", season),
                    "episode_number": episode_data.get("number", episode),
                    "air_date": episode_data.get("aired", ""),
                    "season_name": episode_data.get("seasonName", ""),
                    "series_name": series_data.get("name", ""),
                    "series_overview": series_data.get("overview", ""),
                    "image": episode_data.get("image", None),
                    "series_image": series_data.get("image", None)
                }

                console.print(f"[green]Found episode: {result['season_name']} - S{result['season_number']}E{result['episode_number']} - {result['episode_name']}[/green] - {result['air_date']}")
                console.print(f"[yellow]Overview: {result['overview']}")
                return result
            else:
                console.print(f"[yellow]No episode data found for S{season}E{episode}[/yellow]")
                return None

    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP error occurred: {e.response.status_code} - {e.response.text}[/red]")
        return None
    except httpx.RequestError as e:
        console.print(f"[red]Request error occurred: {e}[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Error fetching TVDb episode data: {e}[/red]")
        return None


async def get_tvdb_token(api_key, base_dir):
    console.print("[cyan]Authenticating with TVDb API...[/cyan]")

    url = "https://api4.thetvdb.com/v4/login"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "apikey": api_key,
        "pin": "string"  # Default value as specified in the example
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "success" and data.get("data") and data["data"].get("token"):
                token = data["data"]["token"]
                console.print("[green]Successfully authenticated with TVDb[/green]")
                console.print(f"[bold yellow]New TVDb token: {token}[/bold yellow]")

                # Update the token in the in-memory configuration
                config['DEFAULT']['tvdb_token'] = f'"{token}"'

                # Save the updated config to disk
                try:
                    # Get the config file path
                    config_path = f"{base_dir}/data/config.py"

                    # Read the current config file
                    with open(config_path, 'r', encoding='utf-8') as file:
                        config_data = file.read()

                    # Update the tvdb_token value in the config file
                    # This regex looks for "tvdb_token": "old_value" and replaces it with the new token
                    new_config_data = re.sub(
                        r'("tvdb_token":\s*")[^"]*("))',  # Match the token value between double quotes
                        rf'\1{token}\2',  # Replace with new token while preserving the structure
                        config_data
                    )

                    # Write the updated config back to the file
                    with open(config_path, 'w', encoding='utf-8') as file:
                        file.write(new_config_data)

                    console.print(f"[bold green]TVDb token successfully saved to {config_path}[/bold green]")
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not update TVDb token in configuration file: {e}[/yellow]")
                    console.print("[yellow]The token will be used for this session only.[/yellow]")

                return token
            else:
                console.print("[red]Failed to get TVDb token: Invalid response format[/red]")
                return None

    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP error occurred during TVDb authentication: {e.response.status_code} - {e.response.text}[/red]")
        return None
    except httpx.RequestError as e:
        console.print(f"[red]Request error occurred during TVDb authentication: {e}[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Error authenticating with TVDb: {e}[/red]")
        return None
