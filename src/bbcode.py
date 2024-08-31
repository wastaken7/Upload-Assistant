import re
import html
import urllib.parse
from src.console import console

# Bold - KEEP
# Italic - KEEP
# Underline - KEEP
# Strikethrough - KEEP
# Color - KEEP
# URL - KEEP
# PARSING - Probably not exist in uploads
# Spoiler - KEEP

# QUOTE - CONVERT to CODE
# PRE - CONVERT to CODE
# Hide - CONVERT to SPOILER
# COMPARISON - CONVERT

# LIST - REMOVE TAGS/REPLACE with * or something

# Size - REMOVE TAGS

# Align - REMOVE (ALL LEFT ALIGNED)
# VIDEO - REMOVE
# HR - REMOVE
# MEDIAINFO - REMOVE
# MOVIE - REMOVE
# PERSON - REMOVE
# USER - REMOVE
# IMG - REMOVE?
# INDENT - Probably not an issue, but maybe just remove tags


class BBCODE:
    def __init__(self):
        pass

    def clean_ptp_description(self, desc, is_disc):
        # console.print(f"[yellow]Cleaning PTP description...")
        
        # Convert Bullet Points to -
        desc = desc.replace("&bull;", "-")

        # Unescape html
        desc = html.unescape(desc)
        desc = desc.replace('\r\n', '\n')

        # Remove url tags with PTP/HDB links
        url_tags = re.findall(r"(\[url[\=\]]https?:\/\/passthepopcorn\.m[^\]]+)([^\[]+)(\[\/url\])?", desc, flags=re.IGNORECASE)
        url_tags += re.findall(r"(\[url[\=\]]https?:\/\/hdbits\.o[^\]]+)([^\[]+)(\[\/url\])?", desc, flags=re.IGNORECASE)
        if url_tags:
            for url_tag in url_tags:
                url_tag = ''.join(url_tag)
                url_tag_removed = re.sub(r"(\[url[\=\]]https?:\/\/passthepopcorn\.m[^\]]+])", "", url_tag, flags=re.IGNORECASE)
                url_tag_removed = re.sub(r"(\[url[\=\]]https?:\/\/hdbits\.o[^\]]+])", "", url_tag_removed, flags=re.IGNORECASE)
                url_tag_removed = url_tag_removed.replace("[/url]", "")
                desc = desc.replace(url_tag, url_tag_removed)

        # Remove links to PTP/HDB
        desc = desc.replace('http://passthepopcorn.me', 'PTP').replace('https://passthepopcorn.me', 'PTP')
        desc = desc.replace('http://hdbits.org', 'HDB').replace('https://hdbits.org', 'HDB')

        # Remove Mediainfo Tags / Attempt to regex out mediainfo
        mediainfo_tags = re.findall(r"\[mediainfo\][\s\S]*?\[\/mediainfo\]", desc)
        if mediainfo_tags:
            desc = re.sub(r"\[mediainfo\][\s\S]*?\[\/mediainfo\]", "", desc)
        elif is_disc != "BDMV":
            desc = re.sub(r"(^general\nunique)(.*?)^$", "", desc, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
            desc = re.sub(r"(^general\ncomplete)(.*?)^$", "", desc, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
            desc = re.sub(r"(^(Format[\s]{2,}:))(.*?)^$", "", desc, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
            desc = re.sub(r"(^(video|audio|text)( #\d+)?\nid)(.*?)^$", "", desc, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
            desc = re.sub(r"(^(menu)( #\d+)?\n)(.*?)^$", "", f"{desc}\n\n", flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
        elif any(x in is_disc for x in ["BDMV", "DVD"]):
            return "", []

        # Convert Quote tags:
        desc = re.sub(r"\[quote.*?\]", "[code]", desc)
        desc = desc.replace("[/quote]", "[/code]")

        # Remove Alignments:
        desc = re.sub(r"\[align=.*?\]", "", desc)
        desc = desc.replace("[/align]", "")

        # Remove size tags
        desc = re.sub(r"\[size=.*?\]", "", desc)
        desc = desc.replace("[/size]", "")

        # Remove Videos
        desc = re.sub(r"\[video\][\s\S]*?\[\/video\]", "", desc)

        # Remove Staff tags
        desc = re.sub(r"\[staff[\s\S]*?\[\/staff\]", "", desc)

        # Remove Movie/Person/User/hr/Indent
        remove_list = [
            '[movie]', '[/movie]',
            '[artist]', '[/artist]',
            '[user]', '[/user]',
            '[indent]', '[/indent]',
            '[size]', '[/size]',
            '[hr]'
        ]
        for each in remove_list:
            desc = desc.replace(each, '')

        # Catch Stray Images and Prepare Image List
        imagelist = []
        comps = re.findall(r"\[comparison=[\s\S]*?\[\/comparison\]", desc)
        hides = re.findall(r"\[hide[\s\S]*?\[\/hide\]", desc)
        comps.extend(hides)
        nocomp = desc
        comp_placeholders = []

        # Replace comparison/hide tags with placeholder because sometimes uploaders use comp images as loose images
        for i, comp in enumerate(comps):
            nocomp = nocomp.replace(comp, '')
            desc = desc.replace(comp, f"COMPARISON_PLACEHOLDER-{i} ")
            comp_placeholders.append(comp)

        # Remove Images in IMG tags:
        desc = re.sub(r"\[img\][\s\S]*?\[\/img\]", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[img=[\s\S]*?\]", "", desc, flags=re.IGNORECASE)

        # Extract loose images and add to imagelist as dictionaries
        loose_images = re.findall(r"(https?:\/\/.*\.(?:png|jpg))", nocomp, flags=re.IGNORECASE)
        if loose_images:
            for img_url in loose_images:
                image_dict = {
                    'img_url': img_url,
                    'raw_url': img_url,
                    'web_url': img_url  # Since there is no distinction here, use the same URL for all
                }
                imagelist.append(image_dict)
                desc = desc.replace(img_url, '')

        # Re-place comparisons
        for i, comp in enumerate(comp_placeholders):
            comp = re.sub(r"\[\/?img[\s\S]*?\]", "", comp, flags=re.IGNORECASE)
            desc = desc.replace(f"COMPARISON_PLACEHOLDER-{i} ", comp)

        # Convert hides with multiple images to comparison
        desc = self.convert_collapse_to_comparison(desc, "hide", hides)

        # Strip blank lines:
        desc = desc.strip('\n')
        desc = re.sub("\n\n+", "\n\n", desc)
        while desc.startswith('\n'):
            desc = desc.replace('\n', '', 1)
        desc = desc.strip('\n')

        if desc.replace('\n', '').strip() == '':
            console.print(f"[yellow]Description is empty after cleaning.")
            return "", imagelist

        return desc, imagelist

    def clean_unit3d_description(self, desc, site):
        # Unescape html
        desc = html.unescape(desc)
        # End my suffering
        desc = desc.replace('\r\n', '\n')

        # Remove links to site
        site_netloc = urllib.parse.urlparse(site).netloc
        site_regex = rf"(\[url[\=\]]https?:\/\/{site_netloc}/[^\]]+])([^\[]+)(\[\/url\])?"
        site_url_tags = re.findall(site_regex, desc)
        if site_url_tags != []:
            for site_url_tag in site_url_tags:
                site_url_tag = ''.join(site_url_tag)
                url_tag_regex = rf"(\[url[\=\]]https?:\/\/{site_netloc}[^\]]+])"
                url_tag_removed = re.sub(url_tag_regex, "", site_url_tag)
                url_tag_removed = url_tag_removed.replace("[/url]", "")
                desc = desc.replace(site_url_tag, url_tag_removed)

        desc = desc.replace(site_netloc, site_netloc.split('.')[0])

        # Temporarily hide spoiler tags
        spoilers = re.findall(r"\[spoiler[\s\S]*?\[\/spoiler\]", desc)
        nospoil = desc
        spoiler_placeholders = []
        for i in range(len(spoilers)):
            nospoil = nospoil.replace(spoilers[i], '')
            desc = desc.replace(spoilers[i], f"SPOILER_PLACEHOLDER-{i} ")
            spoiler_placeholders.append(spoilers[i])

        # Get Images from outside spoilers
        imagelist = []
        url_tags = re.findall(r"\[url=[\s\S]*?\[\/url\]", desc)
        if url_tags != []:
            for tag in url_tags:
                image = re.findall(r"\[img[\s\S]*?\[\/img\]", tag)
                if len(image) == 1:
                    image_dict = {}
                    img_url = image[0].lower().replace('[img]', '').replace('[/img]', '')
                    image_dict['img_url'] = image_dict['raw_url'] = re.sub(r"\[img[\s\S]*\]", "", img_url)
                    url_tag = tag.replace(image[0], '')
                    image_dict['web_url'] = re.match(r"\[url=[\s\S]*?\]", url_tag, flags=re.IGNORECASE)[0].lower().replace('[url=', '')[:-1]
                    imagelist.append(image_dict)
                    desc = desc.replace(tag, '')

        # Remove bot signatures
        bot_signature_regex = r"\[center\]\s*\[img=\d+\]https:\/\/blutopia\.xyz\/favicon\.ico\[\/img\]\s*\[b\]Uploaded Using \[url=https:\/\/github\.com\/HDInnovations\/UNIT3D\]UNIT3D\[\/url\] Auto Uploader\[\/b\]\s*\[img=\d+\]https:\/\/blutopia\.xyz\/favicon\.ico\[\/img\]\s*\[\/center\]"
        desc = re.sub(bot_signature_regex, "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[center\].*Created by L4G's Upload Assistant.*\[\/center\]", "", desc, flags=re.IGNORECASE)

        # Replace spoiler tags
        if spoiler_placeholders != []:
            for i, spoiler in enumerate(spoiler_placeholders):
                desc = desc.replace(f"SPOILER_PLACEHOLDER-{i} ", spoiler)

        # Check for empty [center] tags
        centers = re.findall(r"\[center[\s\S]*?\[\/center\]", desc)
        if centers != []:
            for center in centers:
                full_center = center
                replace = ['[center]', ' ', '\n', '[/center]']
                for each in replace:
                    center = center.replace(each, '')
                if center == "":
                    desc = desc.replace(full_center, '')

        # Convert Comparison spoilers to [comparison=]
        desc = self.convert_collapse_to_comparison(desc, "spoiler", spoilers)

        # Strip blank lines:
        desc = desc.strip('\n')
        desc = re.sub("\n\n+", "\n\n", desc)
        while desc.startswith('\n'):
            desc = desc.replace('\n', '', 1)
        desc = desc.strip('\n')

        if desc.replace('\n', '') == '':
            return "", imagelist
        return desc, imagelist

    def convert_pre_to_code(self, desc):
        desc = desc.replace('[pre]', '[code]')
        desc = desc.replace('[/pre]', '[/code]')
        return desc

    def convert_hide_to_spoiler(self, desc):
        desc = desc.replace('[hide', '[spoiler')
        desc = desc.replace('[/hide]', '[/spoiler]')
        return desc

    def convert_spoiler_to_hide(self, desc):
        desc = desc.replace('[spoiler', '[hide')
        desc = desc.replace('[/spoiler]', '[/hide]')
        return desc

    def remove_spoiler(self, desc):
        desc = re.sub(r"\[\/?spoiler[\s\S]*?\]", "", desc, flags=re.IGNORECASE)
        return desc

    def convert_spoiler_to_code(self, desc):
        desc = desc.replace('[spoiler', '[code')
        desc = desc.replace('[/spoiler]', '[/code]')
        return desc

    def convert_code_to_quote(self, desc):
        desc = desc.replace('[code', '[quote')
        desc = desc.replace('[/code]', '[/quote]')
        return desc

    def convert_comparison_to_collapse(self, desc, max_width):
        comparisons = re.findall(r"\[comparison=[\s\S]*?\[\/comparison\]", desc)
        for comp in comparisons:
            line = []
            output = []
            comp_sources = comp.split(']', 1)[0].replace('[comparison=', '').replace(' ', '').split(',')
            comp_images = comp.split(']', 1)[1].replace('[/comparison]', '').replace(',', '\n').replace(' ', '\n')
            comp_images = re.findall(r"(https?:\/\/.*\.(?:png|jpg))", comp_images, flags=re.IGNORECASE)
            screens_per_line = len(comp_sources)
            img_size = int(max_width / screens_per_line)
            if img_size > 350:
                img_size = 350
            for img in comp_images:
                img = img.strip()
                if img != "":
                    bb = f"[url={img}][img={img_size}]{img}[/img][/url]"
                    line.append(bb)
                    if len(line) == screens_per_line:
                        output.append(''.join(line))
                        line = []
            output = '\n'.join(output)
            new_bbcode = f"[spoiler={' vs '.join(comp_sources)}][center]{' | '.join(comp_sources)}[/center]\n{output}[/spoiler]"
            desc = desc.replace(comp, new_bbcode)
        return desc

    def convert_comparison_to_centered(self, desc, max_width):
        comparisons = re.findall(r"\[comparison=[\s\S]*?\[\/comparison\]", desc)
        for comp in comparisons:
            line = []
            output = []
            comp_sources = comp.split(']', 1)[0].replace('[comparison=', '').replace(' ', '').split(',')
            comp_images = comp.split(']', 1)[1].replace('[/comparison]', '').replace(',', '\n').replace(' ', '\n')
            comp_images = re.findall(r"(https?:\/\/.*\.(?:png|jpg))", comp_images, flags=re.IGNORECASE)
            screens_per_line = len(comp_sources)
            img_size = int(max_width / screens_per_line)
            if img_size > 350:
                img_size = 350
            for img in comp_images:
                img = img.strip()
                if img != "":
                    bb = f"[url={img}][img={img_size}]{img}[/img][/url]"
                    line.append(bb)
                    if len(line) == screens_per_line:
                        output.append(''.join(line))
                        line = []
            output = '\n'.join(output)
            new_bbcode = f"[center]{' | '.join(comp_sources)}\n{output}[/center]"
            desc = desc.replace(comp, new_bbcode)
        return desc

    def convert_collapse_to_comparison(self, desc, spoiler_hide, collapses):
        # Convert Comparison spoilers to [comparison=]
        if collapses != []:
            for i in range(len(collapses)):
                tag = collapses[i]
                images = re.findall(r"\[img[\s\S]*?\[\/img\]", tag, flags=re.IGNORECASE)
                if len(images) >= 6:
                    comp_images = []
                    final_sources = []
                    for image in images:
                        image_url = re.sub(r"\[img[\s\S]*\]", "", image.replace('[/img]', ''), flags=re.IGNORECASE)
                        comp_images.append(image_url)
                    if spoiler_hide == "spoiler":
                        sources = re.match(r"\[spoiler[\s\S]*?\]", tag)[0].replace('[spoiler=', '')[:-1]
                    elif spoiler_hide == "hide":
                        sources = re.match(r"\[hide[\s\S]*?\]", tag)[0].replace('[hide=', '')[:-1]
                    sources = re.sub("comparison", "", sources, flags=re.IGNORECASE)
                    for each in ['vs', ',', '|']:
                        sources = sources.split(each)
                        sources = "$".join(sources)
                    sources = sources.split("$")
                    for source in sources:
                        final_sources.append(source.strip())
                    comp_images = '\n'.join(comp_images)
                    final_sources = ', '.join(final_sources)
                    spoil2comp = f"[comparison={final_sources}]{comp_images}[/comparison]"
                    desc = desc.replace(tag, spoil2comp)
        return desc
