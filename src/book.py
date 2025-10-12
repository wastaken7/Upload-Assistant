# -*- coding: utf-8 -*-
from bs4 import BeautifulSoup
from pathlib import Path
from PIL import Image
from src.console import console
from src.tags import get_tag
import aiofiles
import httpx
import io
import json
import os
import re
import shutil


async def book_meta(meta):
    open_library_data = await get_openlibrary_info(meta)
    google_books_data = await get_google_info(meta)
    isbnsearch_data = await get_isbnsearch_info(meta)
    meta['ol_data'] = open_library_data
    meta['gl_data'] = google_books_data
    meta['isbnsearch_data'] = isbnsearch_data

    ol_data = open_library_data
    gl_data = google_books_data

    # Authors
    meta_author(meta, ol_data, gl_data)

    # Year
    meta_year(meta, ol_data)

    # Title
    meta_title(meta, ol_data, gl_data)

    # Genres
    meta_genres(meta, ol_data, gl_data)

    # Cover Image
    await meta_cover(meta, ol_data, gl_data)

    # Type
    meta_type(meta)

    # Tag
    meta['tag'] = await get_tag(meta.get('uuid'), meta)

    return meta


async def get_isbnsearch_info(meta):
    """
    Fetches book information from isbnsearch.org using the ISBN, caches the result,
    and returns the extracted data including title, author, publisher, publication year,
    binding, and cover URL.
    """
    isbn = meta.get('isbn')
    if not isbn:
        return {}

    cache_dir = f"{meta['base_dir']}/tmp/{meta['uuid']}"
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"isbnsearch_{isbn}.json")

    if os.path.exists(cache_file):
        try:
            async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                return json.loads(await f.read())
        except Exception as e:
            console.print(f"Error reading cache file {cache_file}: {e}")

    isbnsearch_url = f"https://isbnsearch.org/isbn/{isbn}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(isbnsearch_url)
            response.raise_for_status()
            html_content = response.text

            soup = BeautifulSoup(html_content, 'html.parser')
            data = {}

            book_info_div = soup.find('div', class_='bookinfo')

            # Title
            title_tag = book_info_div.find('h1') if book_info_div else None
            if title_tag:
                data['title'] = title_tag.text.strip()

            # Author, Binding, Publisher, Published Year
            if book_info_div:
                for p_tag in book_info_div.find_all('p', recursive=False):
                    text = p_tag.text.strip()
                    # Author: 'Author: Naoya Matsumoto'
                    if text.startswith('Author:'):
                        data['author'] = text.replace('Author:', '').strip()
                    # Binding: 'Binding: Paperback'
                    elif text.startswith('Binding:'):
                        data['binding'] = text.replace('Binding:', '').strip()
                    # Publisher: 'Publisher: Crunchyroll Manga'
                    elif text.startswith('Publisher:'):
                        data['publisher'] = text.replace('Publisher:', '').strip()
                    # Published Year: 'Published: 2022'
                    elif text.startswith('Published:'):
                        data['year'] = text.replace('Published:', '').strip()

            image_div = soup.find('div', class_='image')
            cover_img = image_div.find('img') if image_div else None
            if cover_img and 'src' in cover_img.attrs:
                data['cover_url'] = cover_img['src'].strip()

            # Save to cache
            async with aiofiles.open(cache_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=4))

            return data

        except httpx.HTTPError as e:
            console.print(f"HTTP Error fetching {isbnsearch_url}: {e}")
            return {}
        except Exception as e:
            console.print(f"An unexpected error occurred: {e}")
            return {}


async def get_openlibrary_info(meta):
    openlibrary_api_url = "https://openlibrary.org/api/books"
    isbn = meta.get('isbn')
    if not isbn:
        return {}

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


async def get_google_info(meta):
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
    isbn = meta.get('isbn')
    if not isbn:
        return False
    cover_url = meta.get('cover_url', '')
    if not cover_url:
        return False

    tmp_dir = f"{meta['base_dir']}/tmp/{meta['uuid']}"
    os.makedirs(tmp_dir, exist_ok=True)

    cover_path = os.path.join(tmp_dir, f"cover_{isbn}.jpg")

    if os.path.exists(cover_path):
        console.print(f"Cover image already exists at {cover_path}")
        return True

    async with httpx.AsyncClient() as client:
        print(f"Downloading cover from: {cover_url}")
        try:
            response = await client.get(cover_url, follow_redirects=True)
            response.raise_for_status()

            try:
                img = Image.open(io.BytesIO(response.content))
                width, height = img.size
                aspect_ratio = width / height
                if not (0.5 <= aspect_ratio <= 0.8):
                    console.print(f"Warning: Downloaded image aspect ratio ({aspect_ratio:.2f}) is unusual for a book cover. Skipping download.")
                    return False
            except Exception as img_e:
                console.print(f"Warning: Could not verify image aspect ratio: {img_e}")

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


def meta_type(meta):
    meta['type'] = ''
    file = meta.get('uuid', '').upper()
    meta['type'] = file.split('.')[-1]


def meta_author(meta, ol_data, gl_data):
    authors = []
    if ol_data and 'authors' in ol_data:
        for author_entry in ol_data['authors']:
            if 'name' in author_entry:
                authors.append(author_entry['name'])

    if gl_data and 'authors' in gl_data:
        for author_name in gl_data['authors']:
            authors.append(author_name)

    if authors:
        unique_authors = sorted(list(set(authors)))
        meta['author'] = ", ".join(unique_authors)


def meta_year(meta, ol_data):
    meta['year'] = ''
    publish_date = ol_data.get('publish_date', '')
    if publish_date:
        year_match = re.search(r'\d{4}', publish_date)
        if year_match:
            meta['year'] = year_match.group(0)


def meta_title(meta, ol_data, gl_data):
    meta['title'] = ''
    if not meta.get('title') and ol_data and 'title' in ol_data:
        meta['title'] = ol_data['title']
    elif not meta.get('title') and gl_data and 'title' in gl_data:
        meta['title'] = gl_data['title']

    meta['overview'] = gl_data.get('description', '') if gl_data else ''


def meta_genres(meta, ol_data, gl_data):
    meta['genres'] = ''
    genres = []
    if gl_data and 'categories' in gl_data:
        genres.extend(gl_data['categories'])
    if ol_data and 'subjects' in ol_data:
        ol_subjects = [subject['name'] for subject in ol_data['subjects'] if 'name' in subject]
        genres.extend(ol_subjects)

    if genres:
        unique_genres = sorted(list(set(genres)))
        meta['genres'] = ", ".join(unique_genres)


async def meta_cover(meta, ol_data, gl_data):
    # Check if a cover file already exists in the tmp directory
    tmp_dir = Path(meta['base_dir']) / "tmp" / meta['uuid']
    if tmp_dir.exists():
        for f in tmp_dir.glob(f'cover_{meta.get("isbn")}*'):
            if f.is_file():
                console.print(f"[green]Local cover image already exists: {f}[/green]")
                meta['cover_url'] = f.as_uri()  # Store local file URI
                return True

    potential_urls = []

    # OpenLibrary (prioritized)
    if ol_data and 'cover' in ol_data and 'large' in ol_data['cover']:
        potential_urls.append(ol_data['cover']['large'])

    # Google Books
    if gl_data and 'imageLinks' in gl_data and 'thumbnail' in gl_data['imageLinks']:
        potential_urls.append(gl_data['imageLinks']['thumbnail'])

    # ISBNsearch
    if meta.get('isbnsearch_data') and 'cover_url' in meta['isbnsearch_data']:
        potential_urls.append(meta['isbnsearch_data']['cover_url'])

    successful_url = None

    for url in potential_urls:
        meta['cover_url'] = url

        if await download_book_cover(meta):
            successful_url = url
            print("Successfully downloaded cover. Stopping further attempts.")
            return successful_url

    if not successful_url:
        meta['cover_url'] = ''
        print("All download attempts failed.")
        print('Searching for images in the file directory...')
    if search_local_cover(meta):
        console.print("[green]Successfully found and copied local cover image.")
        return True

    meta['cover_url'] = ''
    console.print("No local cover image found.")

    return successful_url


def search_local_cover(meta):
    book_file_path_str = meta.get('path')
    if book_file_path_str:
        book_file_path = Path(book_file_path_str)
        book_dir = book_file_path.parent

        img_extensions = ['.jpg', '.jpeg', '.png', '.webp']

        for ext in img_extensions:
            glob_pattern = f"*{ext}"

            for potential_cover_path in book_dir.glob(glob_pattern):
                if potential_cover_path.is_file():
                    console.print(f"Found local cover image: {potential_cover_path}")

                    use_local_cover = input("Use this local cover image? (y/N): ").lower()

                    if use_local_cover != 'y':
                        continue

                    try:
                        tmp_dir = Path(meta['base_dir']) / "tmp" / meta['uuid']
                        tmp_dir.mkdir(parents=True, exist_ok=True)
                        cover_path = tmp_dir / f"cover_{meta.get('isbn')}{ext}"

                        shutil.copy(potential_cover_path, cover_path)

                        return True

                    except Exception as e:
                        console.print(f"Error copying local cover: {e}")
                        continue

    return False
