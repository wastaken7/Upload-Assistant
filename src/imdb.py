import requests
from difflib import SequenceMatcher
from imdb import Cinemagoer
from src.console import console
from datetime import datetime
import json


async def get_imdb_aka_api(imdb_id, meta):
    if imdb_id == "0":
        return "", None
    if not imdb_id.startswith("tt"):
        imdb_id = f"tt{imdb_id}"
    url = "https://api.graphql.imdb.com/"
    query = {
        "query": f"""
            query {{
                title(id: "{imdb_id}") {{
                    id
                    titleText {{
                        text
                        isOriginalTitle
                    }}
                    originalTitleText {{
                        text
                    }}
                    countriesOfOrigin {{
                        countries {{
                            id
                        }}
                    }}
                }}
            }}
        """
    }

    headers = {
        "Content-Type": "application/json",
    }

    response = requests.post(url, headers=headers, json=query)
    data = response.json()

    # Check if `data` and `title` exist
    title_data = data.get("data", {}).get("title")
    if title_data is None:
        console.print("Title data is missing from response")
        return "", None

    # Extract relevant fields from the response
    aka = title_data.get("originalTitleText", {}).get("text", "")
    is_original = title_data.get("titleText", {}).get("isOriginalTitle", False)
    title_text = title_data.get("titleText", {}).get("text", "")
    if meta.get('manual_language'):
        original_language = meta.get('manual_language')
    else:
        original_language = None

    if title_text != aka:
        aka = f" AKA {aka}"
    elif is_original and aka:
        aka = f" AKA {aka}"

    return aka, original_language


async def safe_get(data, path, default=None):
    for key in path:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data


async def get_imdb_info_api(imdbID, meta):
    imdb_info = {}
    if imdbID and imdbID != 0:
        try:
            imdbIDtt = f"tt{imdbID}" if not str(imdbID).startswith("tt") else imdbID
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            return imdb_info
        query = {
            "query": f"""
            query GetTitleInfo {{
                title(id: "{imdbIDtt}") {{
                id
                titleText {{
                    text
                    isOriginalTitle
                    country {{
                        text
                    }}
                }}
                originalTitleText {{
                    text
                }}
                releaseYear {{
                    year
                }}
                titleType {{
                    id
                }}
                plot {{
                    plotText {{
                    plainText
                    }}
                }}
                ratingsSummary {{
                    aggregateRating
                    voteCount
                }}
                primaryImage {{
                    url
                }}
                runtime {{
                    displayableProperty {{
                    value {{
                        plainText
                    }}
                    }}
                    seconds
                }}
                titleGenres {{
                    genres {{
                    genre {{
                        text
                    }}
                    }}
                }}
                principalCredits {{
                    category {{
                    text
                    id
                    }}
                    credits {{
                    name {{
                        id
                        nameText {{
                        text
                        }}
                    }}
                    }}
                }}
                episodes {{
                    episodes(first: 500) {{
                    edges {{
                        node {{
                        id
                        titleText {{
                            text
                        }}
                        releaseYear {{
                            year
                        }}
                        releaseDate {{
                            year
                            month
                            day
                        }}
                        }}
                    }}
                    pageInfo {{
                        hasNextPage
                        hasPreviousPage
                    }}
                    total
                    }}
                }}
                akas(first: 100) {{
                edges {{
                    node {{
                    text
                    country {{
                        text
                    }}
                    language {{
                        text
                    }}
                    }}
                }}
                }}
                }}
            }}
            """
        }

        url = "https://api.graphql.imdb.com/"
        headers = {"Content-Type": "application/json"}

        response = requests.post(url, json=query, headers=headers)
        data = response.json()

        if response.status_code != 200:
            return imdb_info

        title_data = await safe_get(data, ["data", "title"], {})
        if not data or "data" not in data or "title" not in data["data"]:
            return imdb_info
        imdb_info['imdbID'] = imdbID
        imdb_info['title'] = await safe_get(title_data, ['titleText', 'text'])
        imdb_info['country'] = await safe_get(title_data, ['titleText', 'country', 'text'])
        imdb_info['year'] = await safe_get(title_data, ['releaseYear', 'year'])
        original_title = await safe_get(title_data, ['originalTitleText', 'text'], '')
        imdb_info['aka'] = original_title if original_title and original_title != imdb_info['title'] else imdb_info['title']
        imdb_info['type'] = await safe_get(title_data, ['titleType', 'id'], None)
        runtime_seconds = await safe_get(title_data, ['runtime', 'seconds'], 0)
        imdb_info['runtime'] = str(runtime_seconds // 60 if runtime_seconds else 60)
        imdb_info['cover'] = await safe_get(title_data, ['primaryImage', 'url'])
        imdb_info['plot'] = await safe_get(title_data, ['plot', 'plotText', 'plainText'], 'No plot available')
        genres = await safe_get(title_data, ['titleGenres', 'genres'], [])
        genre_list = [await safe_get(g, ['genre', 'text'], '') for g in genres]
        imdb_info['genres'] = ', '.join(filter(None, genre_list))
        imdb_info['rating'] = await safe_get(title_data, ['ratingsSummary', 'aggregateRating'], 'N/A')
        imdb_info['directors'] = []
        principal_credits = await safe_get(title_data, ['principalCredits'], [])
        if isinstance(principal_credits, list):
            for pc in principal_credits:
                category_text = await safe_get(pc, ['category', 'text'], '')
                if 'Direct' in category_text:
                    credits = await safe_get(pc, ['credits'], [])
                    for c in credits:
                        name_id = await safe_get(c, ['name', 'id'], '')
                        if name_id.startswith('nm'):
                            imdb_info['directors'].append(name_id)
                    break
        akas_edges = await safe_get(title_data, ['akas', 'edges'], default=[])
        imdb_info['akas'] = [
            {
                "title": await safe_get(edge, ['node', 'text']),
                "country": await safe_get(edge, ['node', 'country', 'text']),
                "language": await safe_get(edge, ['node', 'language', 'text']),
            }
            for edge in akas_edges
        ]
        if meta.get('manual_language'):
            imdb_info['original_langauge'] = meta.get('manual_language')
        imdb_info['episodes'] = []
        episodes_data = await safe_get(title_data, ['episodes', 'episodes'], None)
        if episodes_data:
            edges = await safe_get(episodes_data, ['edges'], [])
            for edge in edges:
                node = await safe_get(edge, ['node'], {})
                episode_info = {
                    'id': await safe_get(node, ['id'], ''),
                    'title': await safe_get(node, ['titleText', 'text'], 'Unknown Title'),
                    'release_year': await safe_get(node, ['releaseYear', 'year'], 'Unknown Year'),
                    'release_date': {
                        'year': await safe_get(node, ['releaseDate', 'year'], None),
                        'month': await safe_get(node, ['releaseDate', 'month'], None),
                        'day': await safe_get(node, ['releaseDate', 'day'], None),
                    }
                }
                imdb_info['episodes'].append(episode_info)

            episodes = imdb_info.get('episodes', [])
            current_year = datetime.now().year
            release_years = [episode['release_year'] for episode in episodes if 'release_year' in episode and isinstance(episode['release_year'], int)]
            if release_years:
                closest_year = min(release_years, key=lambda year: abs(year - current_year))
                meta['tv_year'] = closest_year
            else:
                meta['tv_year'] = None

        difference = SequenceMatcher(None, meta['title'].lower(), meta['aka'][5:].lower()).ratio()
        if difference >= 0.9 or meta['aka'][5:].strip() == "" or meta['aka'][5:].strip().lower() in meta['title'].lower():
            meta['aka'] = ""
        if f"({meta['year']})" in meta['aka']:
            meta['aka'] = meta['aka'].replace(f"({meta['year']})", "").strip()

    else:
        imdb_info = {
            'title': meta.get('title', ''),
            'year': meta.get('year', ''),
            'aka': '',
            'type': None,
            'runtime': meta.get('runtime', '60'),
            'cover': meta.get('poster', ''),
        }
        if len(meta.get('tmdb_directors', [])) >= 1:
            imdb_info['directors'] = meta['tmdb_directors']

    if meta['debug']:
        console.print(f"[cyan]IMDB Response: {json.dumps(imdb_info, indent=2)[:600]}...")
    return imdb_info


async def search_imdb(filename, search_year):
    imdbID = '0'
    ia = Cinemagoer()
    search = ia.search_movie(filename)
    for movie in search:
        if filename in movie.get('title', ''):
            if movie.get('year') == search_year:
                imdbID = str(movie.movieID).replace('tt', '')
    return imdbID
