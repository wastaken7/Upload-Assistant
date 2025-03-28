import glob
import os
import json
import aiofiles
import asyncio
from src.console import console
from urllib.parse import urlparse
from src.takescreens import disc_screenshots, dvd_screenshots, screenshots
from src.uploadscreens import upload_screens
from data.config import config


def match_host(hostname, approved_hosts):
    for approved_host in approved_hosts:
        if hostname == approved_host or hostname.endswith(f".{approved_host}"):
            return approved_host
    return hostname


async def check_hosts(meta, tracker, url_host_mapping, img_host_index=1, approved_image_hosts=None):
    reuploaded_images_path = os.path.join(meta['base_dir'], "tmp", meta['uuid'], "reuploaded_images.json")
    reuploaded_images = []

    if os.path.exists(reuploaded_images_path):
        try:
            async with aiofiles.open(reuploaded_images_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                reuploaded_images = json.loads(content)
        except Exception as e:
            console.print(f"[red]Failed to load reuploaded images: {e}")

    valid_reuploaded_images = []
    for image in reuploaded_images:
        raw_url = image.get('raw_url')
        if not raw_url:
            continue

        parsed_url = urlparse(raw_url)
        hostname = parsed_url.netloc
        mapped_host = match_host(hostname, url_host_mapping.keys())

        if mapped_host:
            mapped_host = url_host_mapping.get(mapped_host, mapped_host)
            if mapped_host in approved_image_hosts:
                valid_reuploaded_images.append(image)
            elif meta['debug']:
                console.print(f"[red]URL '{raw_url}' from reuploaded_images.json is not recognized as an approved host.")

    if valid_reuploaded_images:
        meta['image_list'] = valid_reuploaded_images
        console.print("[green]Using valid images from reuploaded_images.json.")
        return meta['image_list'], False, False

    for image in meta['image_list']:
        raw_url = image.get('raw_url')
        if not raw_url:
            continue

        parsed_url = urlparse(raw_url)
        hostname = parsed_url.netloc
        mapped_host = match_host(hostname, url_host_mapping.keys())

        if mapped_host:
            mapped_host = url_host_mapping.get(mapped_host, mapped_host)
            if meta['debug']:
                if mapped_host in approved_image_hosts:
                    console.print(f"[green]URL '{raw_url}' is correctly matched to approved host '{mapped_host}'.")
                else:
                    console.print(f"[red]URL '{raw_url}' is not recognized as part of an approved host.")

    all_images_valid = all(
        url_host_mapping.get(
            match_host(urlparse(image.get('raw_url', '')).netloc, url_host_mapping.keys()),
            None
        ) in approved_image_hosts for image in meta['image_list']
    )

    if all_images_valid:
        return meta['image_list'], False, False

    images_reuploaded = False
    max_retries = len(approved_image_hosts)

    while img_host_index <= max_retries:
        image_list, retry_mode, images_reuploaded = await handle_image_upload(
            meta, tracker, url_host_mapping, approved_image_hosts, img_host_index=img_host_index
        )

        if retry_mode:
            console.print(f"[yellow]Switching to the next image host. Current index: {img_host_index}")
            img_host_index += 1
            continue  # Retry with next host

        new_images_key = f'{tracker}_images_key'
        if image_list is not None:
            meta['image_list'] = meta.get(new_images_key, [])
            break

    if meta['image_list'] is None or not meta['image_list']:
        console.print("[red]All image hosts failed. Please check your configuration.")


async def handle_image_upload(meta, tracker, url_host_mapping, approved_image_hosts=None, img_host_index=1, file=None):
    retry_mode = False
    images_reuploaded = False
    new_images_key = f'{tracker}_images_key'
    discs = meta.get('discs', [])  # noqa F841
    filelist = meta.get('video', [])
    filename = meta['title']
    if meta.get('is_disc') == "HDDVD":
        path = meta['discs'][0]['largest_evo']
    else:
        path = meta.get('filelist', [None])
        path = path[0] if path else None

    if isinstance(filelist, str):
        filelist = [filelist]

    multi_screens = int(config['DEFAULT'].get('screens', 6))
    base_dir = meta['base_dir']
    folder_id = meta['uuid']
    meta[new_images_key] = []

    screenshots_dir = os.path.join(base_dir, 'tmp', folder_id)
    all_screenshots = []

    # First check if there are any saved screenshots matching those in the image_list
    if meta.get('image_list') and isinstance(meta['image_list'], list):
        # Get all PNG files in the screenshots directory
        all_png_files = await asyncio.to_thread(glob.glob, os.path.join(screenshots_dir, "*.png"))
        if all_png_files and meta.get('debug'):
            console.print(f"[cyan]Found {len(all_png_files)} PNG files in screenshots directory")

        # Extract filenames from the image_list
        image_filenames = []
        for image in meta['image_list']:
            for url_key in ['raw_url', 'img_url', 'web_url']:
                if url_key in image and image[url_key]:
                    parsed_url = urlparse(image[url_key])
                    filename_from_url = os.path.basename(parsed_url.path)
                    if filename_from_url and filename_from_url.lower().endswith('.png'):
                        image_filenames.append(filename_from_url)
                        break

        if image_filenames and meta.get('debug'):
            console.print(f"[cyan]Extracted {len(image_filenames)} filenames from image_list URLs: {image_filenames}")

        # Check if any of the extracted filenames match the actual files in the directory
        if all_png_files and image_filenames:
            for png_file in all_png_files:
                basename = os.path.basename(png_file)
                if basename in image_filenames:
                    # Found a match for this filename
                    all_screenshots.append(png_file)
                    if meta.get('debug'):
                        console.print(f"[green]Found existing screenshot matching URL: {basename}")

        # Also check for any screenshots that match the title pattern as a fallback
        if filename and len(all_screenshots) < multi_screens:
            title_pattern_files = [f for f in all_png_files if os.path.basename(f).startswith(filename)]
            if title_pattern_files:
                # Only add title pattern files that aren't already in all_screenshots
                for file in title_pattern_files:
                    if file not in all_screenshots:
                        all_screenshots.append(file)

                if meta.get('debug'):
                    console.print(f"[green]Found {len(title_pattern_files)} screenshots matching title pattern")

    # If we haven't found enough screenshots yet, search for files in the normal way
    if len(all_screenshots) < multi_screens:
        for i, file in enumerate(filelist):
            filename_pattern = f"{filename}*.png"

            if meta['is_disc'] == "DVD":
                existing_screens = await asyncio.to_thread(glob.glob, f"{meta['base_dir']}/tmp/{meta['uuid']}/{meta['discs'][0]['name']}-*.png")
            else:
                existing_screens = await asyncio.to_thread(glob.glob, os.path.join(screenshots_dir, filename_pattern))

            # Add any new screenshots to our list
            for screen in existing_screens:
                if screen not in all_screenshots:
                    all_screenshots.append(screen)

    # Ensure we have unique screenshots
    all_screenshots = list(set(all_screenshots))

    # If we still don't have enough screenshots, generate new ones
    if len(all_screenshots) < multi_screens:
        # Calculate how many more screenshots we need
        needed_screenshots = multi_screens - len(all_screenshots)

        if meta.get('debug'):
            console.print(f"[yellow]Found {len(all_screenshots)} screenshots, need {needed_screenshots} more to reach {multi_screens} total.")

        try:
            if meta['is_disc'] == "BDMV":
                await disc_screenshots(meta, filename, meta['bdinfo'], folder_id, base_dir,
                                       meta.get('vapoursynth', False), [], meta.get('ffdebug', False),
                                       needed_screenshots, True)
            elif meta['is_disc'] == "DVD":
                await dvd_screenshots(meta, 0, None, True)
            else:
                await screenshots(path, filename, meta['uuid'], base_dir, meta,
                                  needed_screenshots, True, None)

            if meta['is_disc'] == "DVD":
                new_screens = await asyncio.to_thread(glob.glob, f"{meta['base_dir']}/tmp/{meta['uuid']}/{meta['discs'][0]['name']}-*.png")
            else:
                # Use a more generic pattern to find any PNG files that aren't already in all_screenshots
                new_screens = await asyncio.to_thread(glob.glob, os.path.join(screenshots_dir, "*.png"))

                # Filter out files we already have
                new_screens = [screen for screen in new_screens if screen not in all_screenshots]

            # Add any new screenshots to our list (only those not already in all_screenshots)
            if new_screens and meta.get('debug'):
                console.print(f"[green]Found {len(new_screens)} new screenshots after generation")

            for screen in new_screens:
                if screen not in all_screenshots:
                    all_screenshots.append(screen)
                    if meta.get('debug'):
                        console.print(f"[green]Added new screenshot: {os.path.basename(screen)}")

        except Exception as e:
            console.print(f"[red]Error during screenshot capture: {e}")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")

    if not all_screenshots:
        console.print("[red]No screenshots were generated or found. Please check the screenshot generation process.")
        return [], True, images_reuploaded

    all_screenshots.sort()
    existing_from_image_list = []
    other_screenshots = []

    # First separate the screenshots into two categories
    for screenshot in all_screenshots:
        basename = os.path.basename(screenshot)
        # Check if this is from the image_list we extracted earlier
        if meta.get('image_list') and any(os.path.basename(urlparse(img.get('raw_url', '')).path) == basename
                                          for img in meta['image_list']):
            existing_from_image_list.append(screenshot)
        else:
            other_screenshots.append(screenshot)

    # First take all existing screenshots from image_list
    final_screenshots = existing_from_image_list.copy()

    # Then fill up to multi_screens with other screenshots
    remaining_needed = multi_screens - len(final_screenshots)
    if remaining_needed > 0 and other_screenshots:
        final_screenshots.extend(other_screenshots[:remaining_needed])

    # If we still don't have enough, just use whatever we have
    if len(final_screenshots) < multi_screens and len(all_screenshots) >= multi_screens:
        # Fill with any remaining screenshots not yet included
        remaining = [s for s in all_screenshots if s not in final_screenshots]
        final_screenshots.extend(remaining[:multi_screens - len(final_screenshots)])

    all_screenshots = final_screenshots[:multi_screens]

    if meta.get('debug'):
        console.print(f"[green]Using {len(all_screenshots)} screenshots:")
        for i, screenshot in enumerate(all_screenshots):
            console.print(f"  {i+1}. {os.path.basename(screenshot)}")

    if not meta.get('skip_imghost_upload', False):
        uploaded_images = []

        # Add a max retry limit to prevent infinite loop
        max_retries = len(approved_image_hosts)
        while img_host_index <= max_retries:
            current_img_host_key = f'img_host_{img_host_index}'
            current_img_host = config.get('DEFAULT', {}).get(current_img_host_key)

            if not current_img_host:
                console.print("[red]No more image hosts left to try.")
                return [], True, images_reuploaded

            if current_img_host not in approved_image_hosts:
                console.print(f"[red]Your preferred image host '{current_img_host}' is not supported at {tracker}, trying next host.")
                retry_mode = True
                images_reuploaded = True
                img_host_index += 1
                continue
            else:
                meta['imghost'] = current_img_host
                console.print(f"[green]Uploading to approved host '{current_img_host}'.")
                break

        uploaded_images, _ = await upload_screens(
            meta, multi_screens, img_host_index, 0, multi_screens,
            all_screenshots, {new_images_key: meta[new_images_key]}, retry_mode
        )

        if uploaded_images:
            meta[new_images_key] = uploaded_images

        if meta['debug']:
            for image in uploaded_images:
                console.print(f"[debug] Response in upload_image_task: {image['img_url']}, {image['raw_url']}, {image['web_url']}")

        for image in meta.get(new_images_key, []):
            raw_url = image['raw_url']
            parsed_url = urlparse(raw_url)
            hostname = parsed_url.netloc
            mapped_host = match_host(hostname, url_host_mapping.keys())
            mapped_host = url_host_mapping.get(mapped_host, mapped_host)

            if mapped_host not in approved_image_hosts:
                console.print(f"[red]Unsupported image host detected in URL '{raw_url}'. Please use one of the approved image hosts.")
                return meta[new_images_key], True, images_reuploaded  # Trigger retry_mode if switching hosts

        # Ensure all uploaded images are valid
        if all(
            url_host_mapping.get(
                match_host(urlparse(image['raw_url']).netloc, url_host_mapping.keys()),
                match_host(urlparse(image['raw_url']).netloc, url_host_mapping.keys()),
            ) in approved_image_hosts
            for image in meta[new_images_key]
        ):
            if new_images_key in meta and isinstance(meta[new_images_key], list):
                output_file = os.path.join(screenshots_dir, "reuploaded_images.json")

                try:
                    async with aiofiles.open(output_file, 'r', encoding='utf-8') as f:
                        existing_data = await f.read()
                        existing_data = json.loads(existing_data) if existing_data else []
                        if not isinstance(existing_data, list):
                            console.print(f"[red]Existing data in {output_file} is not a list. Resetting to an empty list.")
                            existing_data = []
                except Exception:
                    existing_data = []

                updated_data = existing_data + meta[new_images_key]
                updated_data = [dict(s) for s in {tuple(d.items()) for d in updated_data}]

                try:
                    async with aiofiles.open(output_file, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(updated_data, indent=4))
                    console.print(f"[green]Successfully updated reuploaded images in {output_file}.")
                except Exception as e:
                    console.print(f"[red]Failed to save reuploaded images: {e}")
            else:
                console.print("[red]new_images_key is not a valid key in meta or is not a list.")

            return meta[new_images_key], False, images_reuploaded
    else:
        return meta[new_images_key], False, images_reuploaded
