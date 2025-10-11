# -*- coding: utf-8 -*-
import re
import httpx
import json


async def get_book_info(meta):
    openlibrary_api_url = "https://openlibrary.org/api/books"
    isbn = meta.get('isbn')
    if not isbn:
        return {"error": "ISBN not provided in metadata."}

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
                return data[book_key]
            else:
                return {"error": "Book not found or invalid ISBN."}

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            return {"error": f"HTTP error occurred: {status_code}"}
        except httpx.RequestError as e:
            return {"error": f"An error occurred while requesting the Open Library API: {e}"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response from API."}


async def get_google_book_info(meta):
    isbn = meta.get('isbn')
    if not isbn:
        return {"error": "ISBN not provided in metadata."}
    google_books_api_url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": f"isbn:{isbn}",  # Query to search for the specific ISBN
        "country": "US",      # Optional: Restrict search to US market data
        "maxResults": 1       # We only expect one result for a specific ISBN
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(google_books_api_url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('totalItems', 0) > 0 and 'items' in data:
                return data['items'][0].get('volumeInfo', {})
            else:
                return {"error": "Book not found on Google Books."}

        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP error occurred: {e.response.status_code}"}
        except httpx.RequestError as e:
            return {"error": f"An error occurred while requesting the Google Books API: {e}"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response from API."}


async def book_meta(meta):
    ol_data = meta.get('ol_data')
    gl_data = meta.get('gl_data')

    # Author
    authors = []
    if ol_data and 'authors' in ol_data:
        for author_entry in ol_data['authors']:
            if 'name' in author_entry:
                authors.append(author_entry['name'])
    if gl_data and 'authors' in gl_data:
        for author_name in gl_data['authors']:
            authors.append(author_name)
    if authors:
        meta['author'] = ", ".join(list(set(authors)))

    # Year
    publish_date = ol_data.get('publish_date')
    if publish_date:
        year_match = re.search(r'\d{4}', publish_date)
        if year_match:
            meta['year'] = year_match.group(0)

    # Title
    if not meta.get('title') and ol_data and 'title' in ol_data:
        meta['title'] = ol_data['title']
    elif not meta.get('title') and gl_data and 'title' in gl_data:
        meta['title'] = gl_data['title']

    # Overview
    meta['overview'] = gl_data.get('description', '')

    # Genres
    genres = []
    if gl_data and 'categories' in gl_data:
        genres.extend(gl_data['categories'])
    if ol_data and 'subjects' in ol_data:
        genres.extend(ol_data['subjects'])
    if genres:
        meta['genres'] = ", ".join(list(set(genres)))

    # Cover Image
    cover_url = None
    if ol_data and 'cover' in ol_data and 'large' in ol_data['cover']:
        cover_url = ol_data['cover']['large']
    elif gl_data and 'imageLinks' in gl_data and 'thumbnail' in gl_data['imageLinks']:
        cover_url = gl_data['imageLinks']['thumbnail']

    if cover_url:
        meta['cover_url'] = cover_url

    return meta
