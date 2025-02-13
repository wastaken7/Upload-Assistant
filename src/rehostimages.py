import glob
import os
import json
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
            with open(reuploaded_images_path, 'r') as f:
                reuploaded_images = json.load(f)
        except Exception as e:
            console.print(f"[red]Failed to load reuploaded images: {e}")

    valid_reuploaded_images = []
    for image in reuploaded_images:
        raw_url = image['raw_url']
        parsed_url = urlparse(raw_url)
        hostname = parsed_url.netloc
        mapped_host = match_host(hostname, url_host_mapping.keys())
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
        raw_url = image['raw_url']
        parsed_url = urlparse(raw_url)
        hostname = parsed_url.netloc
        mapped_host = match_host(hostname, url_host_mapping.keys())
        mapped_host = url_host_mapping.get(mapped_host, mapped_host)
        if meta['debug']:
            if mapped_host in approved_image_hosts:
                console.print(f"[green]URL '{raw_url}' is correctly matched to approved host '{mapped_host}'.")
            else:
                console.print(f"[red]URL '{raw_url}' is not recognized as part of an approved host.")

    if not all(
        url_host_mapping.get(
            match_host(urlparse(image['raw_url']).netloc, url_host_mapping.keys()),
            match_host(urlparse(image['raw_url']).netloc, url_host_mapping.keys()),
        ) in approved_image_hosts
        for image in meta['image_list']
    ):
        images_reuploaded = False
        while img_host_index <= len(approved_image_hosts):
            image_list, retry_mode, images_reuploaded = await handle_image_upload(meta, tracker, url_host_mapping, approved_image_hosts, img_host_index=1)

            if retry_mode:
                console.print(f"[yellow]Switching to the next image host. Current index: {img_host_index}")
                img_host_index += 1
                continue

            new_images_key = f'{tracker}_images_key'
            if image_list is not None:
                image_list = meta[new_images_key]
                break

        if image_list is None:
            console.print("[red]All image hosts failed. Please check your configuration.")
            return


async def handle_image_upload(meta, tracker, url_host_mapping, approved_image_hosts=None, img_host_index=1, file=None):
    retry_mode = False
    images_reuploaded = False
    new_images_key = f'{tracker}_images_key'
    discs = meta.get('discs', [])  # noqa F841
    filelist = meta.get('video', [])
    filename = meta['title']
    path = meta['path']
    if isinstance(filelist, str):
        filelist = [filelist]

    multi_screens = int(config['DEFAULT'].get('screens', 6))
    base_dir = meta['base_dir']
    folder_id = meta['uuid']
    meta[new_images_key] = []

    screenshots_dir = os.path.join(base_dir, 'tmp', folder_id)
    all_screenshots = []

    for i, file in enumerate(filelist):
        filename_pattern = f"{filename}*.png"

        if meta['is_disc'] == "DVD":
            existing_screens = glob.glob(f"{meta['base_dir']}/tmp/{meta['uuid']}/{meta['discs'][0]['name']}-*.png")
        else:
            existing_screens = glob.glob(os.path.join(screenshots_dir, filename_pattern))

        if len(existing_screens) < multi_screens:
            if meta.get('debug'):
                console.print("[yellow]The image host of existing images is not supported.")
                console.print(f"[yellow]Insufficient screenshots found: generating {multi_screens} screenshots.")
            if meta['is_disc'] == "BDMV":
                try:
                    await disc_screenshots(meta, filename, meta['bdinfo'], folder_id, base_dir, meta.get('vapoursynth', False), [], meta.get('ffdebug', False), multi_screens, True)
                except Exception as e:
                    print(f"Error during BDMV screenshot capture: {e}")
            elif meta['is_disc'] == "DVD":
                try:
                    await dvd_screenshots(
                        meta, 0, None, True
                    )
                except Exception as e:
                    print(f"Error during DVD screenshot capture: {e}")
            else:
                try:
                    await screenshots(
                        path, filename, meta['uuid'], base_dir, meta, multi_screens, True, None)
                except Exception as e:
                    print(f"Error during generic screenshot capture: {e}")

            if meta['is_disc'] == "DVD":
                existing_screens = glob.glob(f"{meta['base_dir']}/tmp/{meta['uuid']}/{meta['discs'][0]['name']}-*.png")
            else:
                existing_screens = glob.glob(os.path.join(screenshots_dir, filename_pattern))

        all_screenshots.extend(existing_screens)

    if not all_screenshots:
        console.print("[red]No screenshots were generated or found. Please check the screenshot generation process.")
        return [], True, images_reuploaded

    if not meta.get('skip_imghost_upload', False):
        uploaded_images = []
        while True:
            current_img_host_key = f'img_host_{img_host_index}'
            current_img_host = config.get('DEFAULT', {}).get(current_img_host_key)

            if not current_img_host:
                console.print("[red]No more image hosts left to try.")
                return

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

        if all(
            url_host_mapping.get(
                match_host(urlparse(image['raw_url']).netloc, url_host_mapping.keys()),
                match_host(urlparse(image['raw_url']).netloc, url_host_mapping.keys()),
            ) in approved_image_hosts
            for image in meta[new_images_key]
        ):

            if new_images_key in meta and isinstance(meta[new_images_key], list):
                output_file = os.path.join(screenshots_dir, "reuploaded_images.json")
                existing_data = []
                if os.path.exists(output_file):
                    try:
                        with open(output_file, 'r') as f:
                            existing_data = json.load(f)
                            if not isinstance(existing_data, list):
                                console.print(f"[red]Existing data in {output_file} is not a list. Resetting to an empty list.")
                                existing_data = []
                    except Exception as e:
                        console.print(f"[red]Failed to load existing data from {output_file}: {e}")

                updated_data = existing_data + meta[new_images_key]
                updated_data = [dict(s) for s in {tuple(d.items()) for d in updated_data}]

                try:
                    with open(output_file, 'w') as f:
                        json.dump(updated_data, f, indent=4)
                    console.print(f"[green]Successfully updated reuploaded images in {output_file}.")
                except Exception as e:
                    console.print(f"[red]Failed to save reuploaded images: {e}")
            else:
                console.print("[red]new_images_key is not a valid key in meta or is not a list.")

            return meta[new_images_key], False, images_reuploaded
    else:
        return meta[new_images_key], False, images_reuploaded
