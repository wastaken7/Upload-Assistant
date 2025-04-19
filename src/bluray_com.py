import httpx
import time
import random
import asyncio
import re
import json
import cli_ui
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()


async def search_bluray(meta):
    imdb_id = f"tt{meta['imdb_id']:07d}"
    url = f"https://www.blu-ray.com/search/?quicksearch=1&quicksearch_country=all&quicksearch_keyword={imdb_id}&section=theatrical"

    console.print(f"[blue]Searching blu-ray.com for IMDB ID: {imdb_id}[/blue]")
    console.print(f"[dim]Search URL: {url}[/dim]")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.blu-ray.com/",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0"
    }

    delay = random.uniform(1, 3)
    console.print(f"[dim]Waiting {delay:.2f} seconds before request...[/dim]")
    time.sleep(delay)

    with httpx.Client(follow_redirects=True) as client:
        try:
            console.print("[yellow]Sending request to blu-ray.com...[/yellow]")
            response = client.get(url, headers=headers, timeout=10.0)
            console.print(f"[green]Response received with status code: {response.status_code}[/green]")

            if response.status_code == 200:
                if "No index" in response.text or response.text.strip() == "<html><head><meta name=\"robots\" content=\"noindex, nofollow, noodp, noydir\"></head><body>No index.</body></html>":
                    console.print("[red]Request blocked by blu-ray.com (Anti-scraping protection)[/red]")
                    console.print(f"[dim]Response preview: {response.text[:150]}...[/dim]")
                    return None

                console.print(f"[green]Successfully retrieved search results for {imdb_id}[/green]")
                try:
                    with open(f"debug_bluray_search_{imdb_id}.html", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    console.print(f"[dim]Saved search response to debug_bluray_search_{imdb_id}.html[/dim]")
                except Exception as e:
                    console.print(f"[dim]Could not save debug file: {str(e)}[/dim]")

                return response.text
            else:
                console.print(f"[red]Failed with status code: {response.status_code}[/red]")
                return None

        except Exception as e:
            console.print(f"[red]Error fetching data: {str(e)}[/red]")
            return None


def extract_bluray_links(html_content):
    if not html_content:
        console.print("[red]No HTML content to extract links from[/red]")
        return None

    results = []

    try:
        console.print("[yellow]Parsing search results with BeautifulSoup...[/yellow]")
        soup = BeautifulSoup(html_content, 'html.parser')
        movie_divs = soup.select('div.figure')
        console.print(f"[blue]Found {len(movie_divs)} movie divs in the search results[/blue]")

        for i, movie_div in enumerate(movie_divs, 1):
            link = movie_div.find('a', class_='alphaborder')
            console.print(f"[dim]Processing movie #{i}...[/dim]")

            if link and 'href' in link.attrs:
                movie_url = link['href']
                releases_url = f"{movie_url}#Releases"
                title_div = movie_div.select_one('div.figurecaptionbottom div[style*="font-weight: bold"]')
                year_div = movie_div.select_one('div.figurecaptionbottom div[style*="margin-top"]')

                title = title_div.text.strip() if title_div else "Unknown Title"
                year = year_div.text.strip() if year_div else "Unknown Year"

                console.print(f"[green]Found movie: {title} ({year})[/green]")
                console.print(f"[dim]URL: {releases_url}[/dim]")

                results.append({
                    'title': title,
                    'year': year,
                    'releases_url': releases_url
                })
            else:
                console.print("[red]Movie div doesn't have a valid link[/red]")

        console.print(f"[blue]Successfully extracted {len(results)} movie links[/blue]")
        return results

    except Exception as e:
        console.print(f"[red]Error parsing HTML: {str(e)}[/red]")
        console.print_exception()
        return None


async def extract_bluray_release_info(html_content, meta):
    if not html_content:
        console.print("[red]No HTML content to extract release info from[/red]")
        return []

    matching_releases = []
    discs = meta.get('discs', [])
    target_disc_count = len(discs)
    console.print(f"[blue]Looking for releases with {target_disc_count} disc(s)[/blue]")

    try:
        with open("debug_bluray_releases.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        console.print("[dim]Saved releases response to debug_bluray_releases.html[/dim]")
    except Exception as e:
        console.print(f"[dim]Could not save debug file: {str(e)}[/dim]")

    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        bluray_sections = soup.find_all('h3', string=lambda s: s and 'Blu-ray Editions' in s)
        console.print(f"[blue]Found {len(bluray_sections)} Blu-ray section(s)[/blue]")

        for section_idx, section in enumerate(bluray_sections, 1):
            console.print(f"[yellow]Processing Blu-ray section #{section_idx}: {section.text}[/yellow]")

            section_count_match = re.search(r'Blu-ray Editions \((\d+)\)', section.text)
            if section_count_match:
                section_count = int(section_count_match.group(1))
                console.print(f"[blue]Found {section_count} editions in this section[/blue]")

            parent_tr = section.find_parent('tr')
            if not parent_tr:
                console.print("[red]Could not find parent tr for Blu-ray section[/red]")
                continue

            release_links = parent_tr.find_all('a', href=lambda h: h and 'blu-ray.com/movies/' in h)
            console.print(f"[blue]Found {len(release_links)} release links in section {section_idx}[/blue]")

            for link_idx, link in enumerate(release_links, 1):
                try:
                    console.print(f"[dim]Processing release #{link_idx} in section #{section_idx}...[/dim]")

                    release_url = link['href']
                    console.print(f"[dim]Release URL: {release_url}[/dim]")

                    title = link.get('title', link.text.strip())
                    console.print(f"[blue]Release title: {title}[/blue]")

                    country_flag = link.find_previous('img', width='18', height='12')
                    country = country_flag.get('title', 'Unknown') if country_flag else 'Unknown'
                    console.print(f"[blue]Country: {country}[/blue]")

                    price_tag = link.find_next('small', style=lambda s: s and 'color: green' in s)
                    price = price_tag.text.strip() if price_tag else "Unknown"
                    console.print(f"[blue]Price: {price}[/blue]")

                    publisher_tag = link.find_next('small', style=lambda s: s and 'color: #999999' in s)
                    publisher = publisher_tag.text.strip() if publisher_tag else "Unknown"
                    console.print(f"[blue]Publisher: {publisher}[/blue]")

                    console.print(f"[yellow]Need to check release page for disc count: {release_url}[/yellow]")

                    release_id_match = re.search(r'blu-ray\.com/movies/.*?/(\d+)/', release_url)
                    if release_id_match:
                        release_id = release_id_match.group(1)
                        console.print(f"[green]Found release ID: {release_id}[/green]")

                        matching_releases.append({
                            'title': title,
                            'url': release_url,
                            'price': price,
                            'publisher': publisher,
                            'country': country,
                            'release_id': release_id
                        })
                    else:
                        console.print(f"[red]Could not extract release ID from URL: {release_url}[/red]")

                except Exception as e:
                    console.print(f"[red]Error processing release: {str(e)}[/red]")
                    console.print_exception()

        console.print(f"[green]Found {len(matching_releases)} potential matching releases[/green]")
        return matching_releases

    except Exception as e:
        console.print(f"[red]Error parsing Blu-ray release HTML: {str(e)}[/red]")
        console.print_exception()
        return []


async def extract_product_id(url):
    console.print(f"[dim]Extracting product ID from URL: {url}[/dim]")
    pattern = r'blu-ray\.com/.*?/(\d+)/'
    match = re.search(pattern, url)

    if match:
        product_id = match.group(1)
        console.print(f"[green]Successfully extracted product ID: {product_id}[/green]")
        return product_id

    console.print(f"[red]Could not extract product ID from URL: {url}[/red]")
    return None


async def get_bluray_releases(meta):
    console.print("[blue]===== Starting blu-ray.com release search =====[/blue]")
    console.print(f"[blue]Movie: {meta.get('filename', 'Unknown')}, IMDB ID: tt{meta.get('imdb_id', '0000000'):07d}[/blue]")
    console.print(f"[blue]Looking for releases with {len(meta.get('discs', []))} disc(s)[/blue]")

    console.print("[yellow]Step 1: Searching for movie by IMDB ID[/yellow]")
    html_content = await search_bluray(meta)

    if not html_content:
        console.print("[red]Failed to get search results from blu-ray.com[/red]")
        return []

    console.print("[yellow]Step 2: Extracting movie links from search results[/yellow]")
    movie_links = extract_bluray_links(html_content)

    if not movie_links:
        console.print(f"[red]No movies found for IMDB ID: tt{meta['imdb_id']:07d}[/red]")
        return []

    console.print(f"[green]Found {len(movie_links)} blu-ray movies[/green]")

    matching_releases = []

    console.print("[yellow]Step 3: Getting release information for each movie[/yellow]")
    for idx, movie in enumerate(movie_links, 1):
        console.print(f"[blue]Processing movie {idx}/{len(movie_links)}: {movie['title']} ({movie['year']})[/blue]")
        releases_url = movie['releases_url']

        console.print("[yellow]Step 3.1: Extracting product ID[/yellow]")
        product_id = await extract_product_id(releases_url)
        if not product_id:
            console.print(f"[red]Could not extract product ID from {releases_url}[/red]")
            continue

        console.print(f"[green]Product ID: {product_id}[/green]")

        ajax_url = f"https://www.blu-ray.com/products/menu_ajax.php?p={product_id}&c=20&action=showreleasesall"
        console.print(f"[dim]AJAX URL: {ajax_url}[/dim]")

        delay = random.uniform(2, 4)
        console.print(f"[dim]Waiting {delay:.2f} seconds before request...[/dim]")
        await asyncio.sleep(delay)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": releases_url,
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            console.print("[yellow]Step 3.2: Sending request for release information[/yellow]")
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(ajax_url, headers=headers)

                console.print(f"[blue]Response status code: {response.status_code}[/blue]")
                if response.status_code == 200:

                    if "No index" in response.text:
                        console.print(f"[red]Blocked by blu-ray.com when accessing {ajax_url}[/red]")
                        continue

                    console.print("[yellow]Step 3.3: Extracting release information[/yellow]")
                    movie_releases = await extract_bluray_release_info(response.text, meta)

                    for release in movie_releases:
                        release['movie_title'] = movie['title']
                        release['movie_year'] = movie['year']

                    console.print(f"[green]Found {len(movie_releases)} matching releases for this movie[/green]")
                    matching_releases.extend(movie_releases)
                else:
                    console.print(f"[red]Failed to get release information from {ajax_url}, status code: {response.status_code}[/red]")

        except Exception as e:
            console.print(f"[red]Error fetching release details from {ajax_url}: {str(e)}[/red]")
            console.print_exception()

    console.print("[blue]===== BluRay.com search results summary =====[/blue]")
    console.print(f"[green]Found {len(matching_releases)} total matching releases[/green]")

    if matching_releases:
        console.print("[yellow]Matching releases:[/yellow]")
        for idx, release in enumerate(matching_releases, 1):
            console.print(f"[green]{idx}. {release['movie_title']} ({release['movie_year']}):[/green]")
            console.print(f"   [blue]Title: {release['title']}[/blue]")
            console.print(f"   [blue]Country: {release['country']}[/blue]")
            console.print(f"   [blue]Publisher: {release['publisher']}[/blue]")
            console.print(f"   [blue]Price: {release['price']}[/blue]")
            console.print(f"   [dim]URL: {release['url']}[/dim]")

        if meta.get('unattended', False):
            cli_ui.info_1("Running in unattended mode, using first release by default")
            selected_release = matching_releases[0]
            meta['region'] = selected_release['country']
            meta['distributor'] = selected_release['publisher']
            return matching_releases

        cli_ui.info_section("Blu-ray Release Selection")
        cli_ui.info("Please select a Blu-ray release to use for region and distributor information:")
        cli_ui.info("Enter release number, 'a' for all releases, or 'n' to skip")
        cli_ui.info("Selecting all releases will search every release for more information...")
        cli_ui.info("More releases will require more time to process")

        while True:
            try:
                selection = input(f"Selection (1-{len(matching_releases)}/a/n): ").strip().lower()
                if selection == 'a':
                    cli_ui.info("All releases selected")
                    detailed_releases = await process_all_releases(matching_releases, meta)
                    return detailed_releases
                elif selection == 'n':
                    cli_ui.info("Skipped - not using Blu-ray.com information")
                    return []
                else:
                    try:
                        selected_idx = int(selection)

                        if 1 <= selected_idx <= len(matching_releases):
                            selected_release = matching_releases[selected_idx - 1]
                            cli_ui.info(f"Selected: {selected_release['title']} - {selected_release['country']} - {selected_release['publisher']}")
                            region_code = map_country_to_region_code(selected_release['country'])
                            meta['region'] = region_code
                            meta['distributor'] = selected_release['publisher'].upper()
                            cli_ui.info(f"Set region code to: {region_code}, distributor to: {selected_release['publisher'].upper()}")

                            return [selected_release]
                        else:
                            cli_ui.warning(f"Invalid selection: {selected_idx}. Must be between 1 and {len(matching_releases)}")
                    except ValueError:
                        cli_ui.warning(f"Invalid input: '{selection}'. Please enter a number, 'a', or 'n'")

            except (KeyboardInterrupt, EOFError):
                try:
                    confirm = input("Press Enter to exit or any other key to continue: ")
                    if confirm.strip() == "":
                        raise SystemExit("Selection cancelled by user")
                    else:
                        cli_ui.info("Continuing selection...")
                except (KeyboardInterrupt, EOFError):
                    raise SystemExit("Selection cancelled by user")

    try:
        with open("debug_bluray_results.json", "w", encoding="utf-8") as f:
            json.dump({
                "movie": {
                    "title": meta.get("title", "Unknown"),
                    "imdb_id": f"tt{meta.get('imdb_id', '0000000'):07d}"
                },
                "matching_releases": matching_releases
            }, f, indent=2)
        console.print("[dim]Saved results to debug_bluray_results.json[/dim]")
    except Exception as e:
        console.print(f"[dim]Could not save debug results: {str(e)}[/dim]")

    return matching_releases


async def fetch_release_details(release):
    release_url = release['url']
    console.print(f"[yellow]Fetching details for: {release['title']} - {release_url}[/yellow]")

    delay = random.uniform(2, 4)
    console.print(f"[dim]Waiting {delay:.2f} seconds before request...[/dim]")
    await asyncio.sleep(delay)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.blu-ray.com/movies/",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(release_url, headers=headers)

            if response.status_code != 200:
                console.print(f"[red]Failed to get release details, status code: {response.status_code}[/red]")
                return release

            if "No index" in response.text:
                console.print(f"[red]Blocked by blu-ray.com when accessing {release_url}[/red]")
                return release

            try:
                release_id = release.get('release_id', '0000000')
                with open(f"debug_release_{release_id}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                console.print(f"[dim]Saved release page to debug_release_{release_id}.html[/dim]")
            except Exception as e:
                console.print(f"[dim]Could not save debug file: {str(e)}[/dim]")

            soup = BeautifulSoup(response.text, 'html.parser')
            specs_td = soup.find('td', width="228px", style=lambda s: s and 'font-size: 12px' in s)

            if not specs_td:
                console.print("[red]Could not find specs section on the release page[/red]")
                return release

            specs = {
                'video': {},
                'audio': [],
                'subtitles': [],
                'discs': {},
                'playback': {},
            }

            video_section = extract_section(specs_td, 'Video')
            if video_section:
                codec_match = re.search(r'Codec: ([^<\n]+)', video_section)
                if codec_match:
                    specs['video']['codec'] = codec_match.group(1).strip()
                    console.print(f"[blue]Video Codec: {specs['video']['codec']}[/blue]")

                resolution_match = re.search(r'Resolution: ([^<\n]+)', video_section)
                if resolution_match:
                    specs['video']['resolution'] = resolution_match.group(1).strip()
                    console.print(f"[blue]Resolution: {specs['video']['resolution']}[/blue]")

                aspect_match = re.search(r'Aspect ratio: ([^<\n]+)', video_section)
                if aspect_match:
                    specs['video']['aspect_ratio'] = aspect_match.group(1).strip()

                original_aspect_match = re.search(r'Original aspect ratio: ([^<\n]+)', video_section)
                if original_aspect_match:
                    specs['video']['original_aspect_ratio'] = original_aspect_match.group(1).strip()

            audio_section = extract_section(specs_td, 'Audio')
            if audio_section:
                audio_div = specs_td.find('div', id='shortaudio') or specs_td.find('div', id='longaudio')
                if audio_div:
                    audio_lines = [line.strip() for line in audio_div.get_text().split('\n') if line.strip() and 'less' not in line]
                    specs['audio'] = audio_lines
                    console.print(f"[blue]Audio Tracks: {len(audio_lines)} found[/blue]")
                    for track in audio_lines:
                        console.print(f"[dim]  - {track}[/dim]")

            subtitle_section = extract_section(specs_td, 'Subtitles')
            if subtitle_section:
                subs_div = specs_td.find('div', id='shortsubs') or specs_td.find('div', id='longsubs')
                if subs_div:
                    subtitle_text = subs_div.get_text().strip()
                    subtitle_text = re.sub(r'\s*\(less\)\s*', '', subtitle_text)
                    subtitles = [s.strip() for s in re.split(r',|\n', subtitle_text) if s.strip()]
                    specs['subtitles'] = subtitles
                    console.print(f"[blue]Subtitles: {', '.join(subtitles)}[/blue]")

            disc_section = extract_section(specs_td, 'Discs')
            if disc_section:
                disc_type_match = re.search(r'(Blu-ray Disc|DVD|Ultra HD Blu-ray|4K Ultra HD)', disc_section)
                if disc_type_match:
                    specs['discs']['type'] = disc_type_match.group(1).strip()
                    console.print(f"[blue]Disc Type: {specs['discs']['type']}[/blue]")

                disc_count_match = re.search(r'Single disc \(1 ([^)]+)\)|(\d+)-disc set', disc_section)
                if disc_count_match:
                    if disc_count_match.group(1):
                        specs['discs']['count'] = 1
                        specs['discs']['format'] = disc_count_match.group(1).strip()
                    else:
                        specs['discs']['count'] = int(disc_count_match.group(2))
                        specs['discs']['format'] = "multiple discs"
                    console.print(f"[blue]Disc Count: {specs['discs']['count']}[/blue]")
                    console.print(f"[blue]Disc Format: {specs['discs']['format']}[/blue]")

            playback_section = extract_section(specs_td, 'Playback')
            if playback_section:
                region_match = re.search(r'(?:2K Blu-ray|4K Blu-ray|DVD): Region ([A-C])(?: \(([^)]+)\))?', playback_section)
                if region_match:
                    specs['playback']['region'] = region_match.group(1).strip()
                    specs['playback']['region_notes'] = region_match.group(2).strip() if region_match.group(2) else ""
                    console.print(f"[blue]Region: {specs['playback']['region']}[/blue]")
                    if specs['playback']['region_notes']:
                        console.print(f"[dim]Region Notes: {specs['playback']['region_notes']}[/dim]")

            release['specs'] = specs
            return release

    except Exception as e:
        console.print(f"[red]Error fetching release details: {str(e)}[/red]")
        console.print_exception()
        return release


def extract_section(specs_td, section_title):
    section_span = specs_td.find('span', class_='subheading', string=section_title)
    if not section_span:
        return None

    section_content = []
    current_element = section_span.next_sibling

    while current_element:
        if current_element.name == 'span' and 'subheading' in current_element.get('class', []):
            break

        if isinstance(current_element, str):
            section_content.append(current_element)
        elif current_element.name:
            section_content.append(current_element.get_text())

        current_element = current_element.next_sibling

    return ''.join(section_content)


async def process_all_releases(releases, meta):
    if not releases:
        return []

    cli_ui.info_section("Processing Release Details")
    cli_ui.info(f"Fetching detailed information for {len(releases)} releases...")

    disc_count = len(meta.get('discs', []))
    cli_ui.info(f"Local disc count from meta: {disc_count}")

    meta_video_specs = {}
    meta_audio_specs = []
    meta_subtitles = []

    if disc_count > 0 and 'discs' in meta and 'bdinfo' in meta['discs'][0]:
        bdinfo = meta['discs'][0]['bdinfo']

        if 'video' in bdinfo and bdinfo['video']:
            meta_video_specs = bdinfo['video'][0]
            codec = meta_video_specs.get('codec', '')
            resolution = meta_video_specs.get('res', '')
            cli_ui.info(f"Local video: {codec} {resolution}")

        if 'audio' in bdinfo and bdinfo['audio']:
            meta_audio_specs = bdinfo['audio']
            for track in meta_audio_specs:
                cli_ui.info(f"Local audio: {track.get('language', '')} {track.get('codec', '')} {track.get('channels', '')}")

        if 'subtitles' in bdinfo and bdinfo['subtitles']:
            meta_subtitles = bdinfo['subtitles']
            cli_ui.info(f"Local subtitles: {', '.join(meta_subtitles)}")

    detailed_releases = []
    for idx, release in enumerate(releases, 1):
        cli_ui.info(f"Processing release {idx}/{len(releases)}: {release['title']} ({release['country']})")
        detailed_release = await fetch_release_details(release)
        detailed_releases.append(detailed_release)

    cli_ui.info_section("Processing Complete")
    cli_ui.info(f"Successfully processed {len(detailed_releases)} releases")

    if detailed_releases:
        scored_releases = []
        for release in detailed_releases:
            score = 0
            if 'specs' in release:
                specs = release['specs']

                score += len(specs.get('video', {})) * 1.5
                score += len(specs.get('audio', [])) * 1.5
                score += len(specs.get('subtitles', [])) * 1.5
                score += len(specs.get('discs', {})) * 2
                score += len(specs.get('playback', {}))

                # Match disc count - this is very important
                if 'discs' in specs and 'count' in specs['discs']:
                    release_disc_count = specs['discs']['count']
                    if release_disc_count == disc_count:
                        score += 20
                        console.print(f"[green]✓[/green] Disc count match: {release_disc_count}")
                    else:
                        # Disc count mismatch is a significant negative
                        score -= 10
                        console.print(f"[red]✗[/red] Disc count mismatch: {release_disc_count} vs {disc_count}")

                if 'video' in specs and meta_video_specs:
                    release_codec = specs['video'].get('codec', '').lower()
                    meta_codec = meta_video_specs.get('codec', '').lower()

                    if 'avc' in release_codec and 'avc' in meta_codec:
                        score += 5
                        console.print("[green]✓[/green] Video codec match: AVC")
                    elif 'hevc' in release_codec and 'hevc' in meta_codec:
                        score += 5
                        console.print("[green]✓[/green] Video codec match: HEVC")

                    release_res = specs['video'].get('resolution', '').lower()
                    meta_res = meta_video_specs.get('res', '').lower()

                    if '1080' in release_res and '1080' in meta_res:
                        score += 5
                        console.print("[green]✓[/green] Resolution match: 1080p")
                    elif '2160' in release_res or '4k' in release_res and ('2160' in meta_res or '4k' in meta_res):
                        score += 5
                        console.print("[green]✓[/green] Resolution match: 4K/2160p")

                if 'audio' in specs and meta_audio_specs:
                    audio_matches = 0
                    for meta_track in meta_audio_specs:
                        meta_lang = meta_track.get('language', '').lower()
                        meta_format = meta_track.get('codec', '').lower()

                        for release_track in specs.get('audio', []):
                            release_track_lower = release_track.lower()
                            if meta_lang and meta_lang in release_track_lower:
                                if 'lpcm' in meta_format and ('pcm' in release_track_lower or 'lpcm' in release_track_lower):
                                    audio_matches += 1
                                    break
                                elif 'dts-hd' in meta_format and 'dts-hd' in release_track_lower:
                                    audio_matches += 1
                                    break
                                elif 'dolby' in meta_format and 'dolby' in release_track_lower:
                                    audio_matches += 1
                                    break

                    if audio_matches > 0:
                        score += audio_matches * 3
                        console.print(f"[green]✓[/green] Audio track matches: {audio_matches}")

                if 'subtitles' in specs and meta_subtitles:
                    subtitle_matches = 0
                    for meta_sub in meta_subtitles:
                        meta_sub_lower = meta_sub.lower()
                        for release_sub in specs.get('subtitles', []):
                            release_sub_lower = release_sub.lower()
                            if meta_sub_lower in release_sub_lower or release_sub_lower in meta_sub_lower:
                                subtitle_matches += 1
                                break

                    if subtitle_matches > 0:
                        score += subtitle_matches * 2
                        console.print(f"[green]✓[/green] Subtitle matches: {subtitle_matches}")

            cli_ui.info(f"Release score: {score:.1f} for {release['title']} ({release['country']})")
            scored_releases.append((score, release))

        scored_releases.sort(reverse=True, key=lambda x: x[0])

        # Get the highest scored release
        if scored_releases:
            best_score, best_release = scored_releases[0]
            cli_ui.info(f"Best match: {best_release['title']} ({best_release['country']}) with score {best_score:.1f}")

            region_code = map_country_to_region_code(best_release['country'])
            meta['region'] = region_code
            meta['distributor'] = best_release['publisher'].upper()
            cli_ui.info(f"Set region code to: {region_code}, distributor to: {best_release['publisher'].upper()}")
            cli_ui.info(f"Updated metadata with information from {best_release['title']}")

    return detailed_releases


def map_country_to_region_code(country_name):
    country_map = {
        "Afghanistan": "AFG",
        "Albania": "ALB",
        "Algeria": "ALG",
        "Andorra": "AND",
        "Angola": "ANG",
        "Argentina": "ARG",
        "Armenia": "ARM",
        "Aruba": "ARU",
        "Australia": "AUS",
        "Austria": "AUT",
        "Azerbaijan": "AZE",
        "Bahamas": "BAH",
        "Bahrain": "BHR",
        "Bangladesh": "BAN",
        "Barbados": "BRB",
        "Belarus": "BLR",
        "Belgium": "BEL",
        "Belize": "BLZ",
        "Benin": "BEN",
        "Bermuda": "BER",
        "Bhutan": "BHU",
        "Bolivia": "BOL",
        "Bosnia and Herzegovina": "BIH",
        "Botswana": "BOT",
        "Brazil": "BRA",
        "British Virgin Islands": "VGB",
        "Brunei": "BRU",
        "Burkina Faso": "BFA",
        "Burundi": "BDI",
        "Cambodia": "CAM",
        "Cameroon": "CMR",
        "Canada": "CAN",
        "Cape Verde": "CPV",
        "Cayman Islands": "CAY",
        "Central African Republic": "CTA",
        "Chad": "CHA",
        "Chile": "CHI",
        "China": "CHN",
        "Colombia": "COL",
        "Comoros": "COM",
        "Congo": "CGO",
        "Cook Islands": "COK",
        "Costa Rica": "CRC",
        "Croatia": "CRO",
        "Cuba": "CUB",
        "Cyprus": "CYP",
        "Dominican Republic": "DOM",
        "Ecuador": "ECU",
        "Egypt": "EGY",
        "El Salvador": "SLV",
        "Equatorial Guinea": "EQG",
        "Eritrea": "ERI",
        "Ethiopia": "ETH",
        "Fiji": "FIJ",
        "France": "FRA",
        "Gabon": "GAB",
        "Gambia": "GAM",
        "Georgia": "GEO",
        "Germany": "GER",
        "Ghana": "GHA",
        "Greece": "GRE",
        "Grenada": "GRN",
        "Guatemala": "GUA",
        "Guinea": "GUI",
        "Guyana": "GUY",
        "Haiti": "HAI",
        "Honduras": "HON",
        "Hong Kong": "HKG",
        "Hungary": "HUN",
        "Iceland": "ISL",
        "India": "IND",
        "Indonesia": "IDN",
        "Iran": "IRN",
        "Iraq": "IRQ",
        "Ireland": "IRL",
        "Israel": "ISR",
        "Italy": "ITA",
        "Jamaica": "JAM",
        "Japan": "JPN",
        "Jordan": "JOR",
        "Kazakhstan": "KAZ",
        "Kenya": "KEN",
        "Kuwait": "KUW",
        "Kyrgyzstan": "KGZ",
        "Laos": "LAO",
        "Lebanon": "LBN",
        "Liberia": "LBR",
        "Libya": "LBY",
        "Liechtenstein": "LIE",
        "Luxembourg": "LUX",
        "Macau": "MAC",
        "Madagascar": "MAD",
        "Malaysia": "MAS",
        "Malta": "MLT",
        "Mexico": "MEX",
        "Monaco": "MON",
        "Mongolia": "MNG",
        "Morocco": "MAR",
        "Mozambique": "MOZ",
        "Namibia": "NAM",
        "Nepal": "NEP",
        "Netherlands": "NLD",
        "New Zealand": "NZL",
        "Nicaragua": "NCA",
        "Niger": "NIG",
        "North Korea": "PRK",
        "North Macedonia": "MKD",
        "Norway": "NOR",
        "Oman": "OMA",
        "Pakistan": "PAK",
        "Panama": "PAN",
        "Papua New Guinea": "PNG",
        "Paraguay": "PAR",
        "Peru": "PER",
        "Philippines": "PHI",
        "Poland": "POL",
        "Portugal": "POR",
        "Puerto Rico": "PUR",
        "Qatar": "QAT",
        "Romania": "ROU",
        "Russia": "RUS",
        "Rwanda": "RWA",
        "Saint Lucia": "LCA",
        "Samoa": "SAM",
        "San Marino": "SMR",
        "Saudi Arabia": "KSA",
        "Senegal": "SEN",
        "Serbia": "SRB",
        "Singapore": "SIN",
        "South Africa": "RSA",
        "South Korea": "KOR",
        "Spain": "ESP",
        "Sri Lanka": "LKA",
        "Sudan": "SDN",
        "Suriname": "SUR",
        "Switzerland": "SUI",
        "Syria": "SYR",
        "Chinese Taipei": "TWN",
        "Tajikistan": "TJK",
        "Tanzania": "TAN",
        "Thailand": "THA",
        "Trinidad and Tobago": "TRI",
        "Tunisia": "TUN",
        "Turkey": "TUR",
        "Uganda": "UGA",
        "Ukraine": "UKR",
        "United Arab Emirates": "UAE",
        "United Kingdom": "GBR",
        "United States": "USA",
        "Uruguay": "URU",
        "Uzbekistan": "UZB",
        "Venezuela": "VEN",
        "Vietnam": "VIE",
        "Zambia": "ZAM",
        "Zimbabwe": "ZIM",
    }

    region_code = country_map.get(country_name)
    if not region_code:
        region_code = None

    return region_code
