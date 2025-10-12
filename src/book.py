# -*- coding: utf-8 -*-
import re
import httpx
import os
import aiofiles
import json
from src.console import console


async def get_book_info(meta):
    openlibrary_api_url = "https://openlibrary.org/api/books"
    isbn = meta.get('isbn')
    if not isbn:
        return {"error": "ISBN not provided in metadata."}

    # Define cache file path
    cache_dir = f"{meta['base_dir']}/tmp/{meta['uuid']}"
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"openlibrary_{isbn}.json")

    # Check if cache file exists
    if os.path.exists(cache_file):
        try:
            async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                return json.loads(await f.read())
        except Exception as e:
            console.print(f"Error reading cache file {cache_file}: {e}")

    params = {
        "bibkeys": f"ISBN:{isbn}",
        "jscmd": "data",
        "format": "json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(openlibrary_api_url, params=params)
            response.raise_for_status()
            data = response.json()
            book_key = f"ISBN:{isbn}"

            if book_key in data:
                book_data = data[book_key]
                # Save to cache
                async with aiofiles.open(cache_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(book_data, indent=4))
                return book_data
            else:
                return {}

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            console.print(f"HTTP error occurred: {status_code} for ISBN: {isbn}")
        except httpx.RequestError as e:
            console.print(f"error: An error occurred while requesting the Open Library API: {e}")
        except json.JSONDecodeError:
            console.print("error: Invalid JSON response from API.")
        return {}


async def get_google_book_info(meta):
    isbn = meta.get('isbn')
    if not isbn:
        return {"error": "ISBN not provided in metadata."}

    # Define cache file path
    cache_dir = f"{meta['base_dir']}/tmp/{meta['uuid']}"
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"googlebooks_{isbn}.json")

    # Check if cache file exists
    if os.path.exists(cache_file):
        try:
            async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                return json.loads(await f.read())
        except Exception as e:
            console.print(f"Error reading cache file {cache_file}: {e}")
    google_books_api_url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": f"isbn:{isbn}",
        "maxResults": 1
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(google_books_api_url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('totalItems', 0) > 0 and 'items' in data:
                volume_info = data['items'][0].get('volumeInfo', {})
                # Save to cache
                async with aiofiles.open(cache_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(volume_info, indent=4))
                return volume_info

        except httpx.HTTPStatusError as e:
            console.print(f"HTTP error occurred: {e.response.status_code} for ISBN: {isbn}")
        except httpx.RequestError as e:
            console.print(f"error: An error occurred while requesting the Google Books API: {e}")
        except json.JSONDecodeError:
            console.print("error: Invalid JSON response from API.")
        return {}


async def download_book_cover(meta):
    cover_url = meta.get('cover_url', '')
    if not cover_url:
        return False

    # Ensure the tmp directory exists
    tmp_dir = f"{meta['base_dir']}/tmp/{meta['uuid']}"
    os.makedirs(tmp_dir, exist_ok=True)

    cover_path = os.path.join(tmp_dir, "cover.jpg")

    async with httpx.AsyncClient() as client:
        print(f"Downloading cover from: {cover_url}")
        try:
            response = await client.get(cover_url, follow_redirects=True)
            response.raise_for_status()

            async with aiofiles.open(cover_path, 'wb') as f:
                await f.write(response.content)
            return True

        except httpx.HTTPStatusError as e:
            console.print(f"HTTP error occurred while downloading cover: {e.response.status_code} from {cover_url}")
        except httpx.RequestError as e:
            console.print(f"error: An error occurred while requesting the cover image: {e}")
        except Exception as e:
            console.print(f"error: An unexpected error occurred while downloading cover: {e}")
        return False


async def get_amazon_cover_url(meta):
    isbn = meta.get('isbn')
    if not isbn:
        return False

    # Define cache file path
    cache_dir = f"{meta['base_dir']}/tmp/{meta['uuid']}"
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"amazon_cover_url_{isbn}.txt")

    # Check if cache file exists
    if os.path.exists(cache_file):
        try:
            async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                return await f.read()
        except Exception as e:
            console.print(f"Error reading cache file {cache_file}: {e}")

    amazon_url = f"https://www.amazon.com/dp/{isbn}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(amazon_url, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text

            # Regex to find the cover image URL
            match = re.search(r'data-a-image-name="landingImage" src="(.*?)"', html_content)
            if match:
                async with aiofiles.open(cache_file, 'w', encoding='utf-8') as f:
                    await f.write(match.group(1))
                return match.group(1)

        except httpx.HTTPStatusError as e:
            console.print(f"HTTP error occurred: {e.response.status_code} for ISBN: {isbn}")
        except httpx.RequestError as e:
            console.print(f"error: An error occurred while requesting the Amazon URL: {e}")
        except Exception as e:
            console.print(f"error: An unexpected error occurred: {e}")
    return False


async def book_meta(meta):
    open_library_data = await get_book_info(meta)
    google_books_data = await get_google_book_info(meta)

    meta['ol_data'] = open_library_data
    meta['gl_data'] = google_books_data

    ol_data = open_library_data
    gl_data = google_books_data

    # Authors
    authors = []
    # Get authors from OpenLibrary data
    if ol_data and 'authors' in ol_data:
        for author_entry in ol_data['authors']:
            if 'name' in author_entry:
                authors.append(author_entry['name'])

    # Get authors from Google Books data
    if gl_data and 'authors' in gl_data:
        for author_name in gl_data['authors']:
            authors.append(author_name)

    # Clean up duplicates and join (sorted for consistency)
    if authors:
        unique_authors = sorted(list(set(authors)))
        meta['author'] = ", ".join(unique_authors)

    # Year
    # Try to get the year from ol_data
    publish_date = ol_data.get('publish_date', '')
    if publish_date:
        year_match = re.search(r'\d{4}', publish_date)
        if year_match:
            meta['year'] = year_match.group(0)

    # Title
    # Use OpenLibrary title if no title exists, otherwise use Google Books title
    if not meta.get('title') and ol_data and 'title' in ol_data:
        meta['title'] = ol_data['title']
    elif not meta.get('title') and gl_data and 'title' in gl_data:
        meta['title'] = gl_data['title']

    # Overview (Using 'description' from Google Books)
    meta['overview'] = gl_data.get('description', '') if gl_data else ''

    # Genres
    genres = []
    # Get categories from Google Books
    if gl_data and 'categories' in gl_data:
        genres.extend(gl_data['categories'])
    # Get subjects from OpenLibrary
    if ol_data and 'subjects' in ol_data:
        # OpenLibrary subjects are a list of dicts, extract 'name'
        ol_subjects = [subject['name'] for subject in ol_data['subjects'] if 'name' in subject]
        genres.extend(ol_subjects)

    # Clean up duplicates and join
    if genres:
        unique_genres = sorted(list(set(genres)))
        meta['genres'] = ", ".join(unique_genres)

    # Cover Image
    cover_url = None
    meta['cover_url'] = ''
    # OpenLibrary (prioritized)
    if ol_data and 'cover' in ol_data and 'large' in ol_data['cover']:
        cover_url = ol_data['cover']['large']
    # Google Books (fallback)
    elif gl_data and 'imageLinks' in gl_data and 'thumbnail' in gl_data['imageLinks']:
        cover_url = gl_data['imageLinks']['thumbnail']

    if cover_url:
        meta['cover_url'] = cover_url
    else:
        cover_url = await get_amazon_cover_url(meta)

    if cover_url:
        await download_book_cover(meta)

    return meta
