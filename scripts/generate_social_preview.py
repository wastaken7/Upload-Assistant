import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Add current scripts directory to path to ensure generate_icons is importable
sys.path.append(str(Path(__file__).resolve().parent))
from generate_icons import draw_logo


def draw_social_preview():
    # 1. Canvas: 1280x640, transparent/RGBA
    img = Image.new("RGBA", (1280, 640), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # 2. Background: vertical gradient
    # Start: #0c0a09 (12, 10, 9)
    # End: #1c1917 (28, 25, 23)
    for y in range(640):
        ratio = y / 639.0
        r = int(12 + (28 - 12) * ratio)
        g = int(10 + (25 - 10) * ratio)
        b = int(9 + (23 - 9) * ratio)
        draw.line([(0, y), (1280, y)], fill=(r, g, b, 255))

    # 3. Load Fonts
    try:
        title_font = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 72)
        sub_font = ImageFont.truetype("C:\\Windows\\Fonts\\segoeui.ttf", 24)
        badge_font = ImageFont.truetype("C:\\Windows\\Fonts\\seguisb.ttf", 14)
    except OSError:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
        badge_font = ImageFont.load_default()

    # 4. Calculate Layout Dimensions
    title_text = "Upload-Assistant"
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]

    sub_text = "Streamline media preparation and uploads\nacross private trackers & usenet indexers."
    sub_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    sub_w = sub_bbox[2] - sub_bbox[0]
    sub_h = sub_bbox[3] - sub_bbox[1]

    # Visual spaces in Left Column
    gap_title_sub = 20
    gap_sub_div = 30
    gap_div_badges = 30
    divider_h = 2
    badges_h = 38

    # Left Column dimensions
    left_column_w = max(title_w, sub_w)
    left_column_h = title_h + gap_title_sub + sub_h + gap_sub_div + divider_h + gap_div_badges + badges_h

    # Horizontal centering
    gap_left_logo = 100
    logo_size = 400
    total_w = left_column_w + gap_left_logo + logo_size
    margin_x = (1280 - total_w) / 2
    x_start = margin_x

    # Vertical centering (middle at y=320)
    visual_top = 320 - left_column_h / 2

    # Draw coordinates for Left Column elements
    title_y = visual_top - title_bbox[1]

    sub_visual_top = visual_top + title_h + gap_title_sub
    sub_y = sub_visual_top - sub_bbox[1]

    divider_y = sub_visual_top + sub_h + gap_sub_div

    badges_y = divider_y + divider_h + gap_div_badges

    # Logo and Glow coordinates
    logo_x = x_start + left_column_w + gap_left_logo
    logo_y = (640 - logo_size) / 2
    glow_center_x = int(logo_x + logo_size / 2)
    glow_center_y = int(logo_y + logo_size / 2)

    # 5. Ambient Glow behind the logo using concentric circles (blended alpha)
    glow_layer = Image.new("RGBA", (1280, 640), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    for r in range(500, 0, -10):
        alpha = int(20 * (1.0 - r / 500.0))  # Max alpha ~8%
        glow_draw.ellipse([glow_center_x - r, glow_center_y - r, glow_center_x + r, glow_center_y + r], fill=(180, 83, 9, alpha))
    img = Image.alpha_composite(img, glow_layer)
    draw = ImageDraw.Draw(img)

    # 6. Typography (Left Column)
    title_x = x_start - title_bbox[0]
    draw.text((title_x, title_y), title_text, fill=(255, 255, 255, 255), font=title_font)

    sub_x = x_start - sub_bbox[0]
    draw.text((sub_x, sub_y), sub_text, fill=(168, 162, 158, 255), font=sub_font)

    # Divider
    draw.line([(x_start, divider_y), (x_start + left_column_w, divider_y)], fill=(41, 37, 36, 255), width=divider_h)

    # 7. Badges (Left Column)
    def draw_badge(x, y, w, h, bg_color, border_color, text, text_color):
        badge_layer = Image.new("RGBA", (1280, 640), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(badge_layer)
        # Background
        b_draw.rounded_rectangle([x, y, x + w, y + h], radius=h / 2, fill=bg_color)
        # Border
        b_draw.rounded_rectangle([x, y, x + w, y + h], radius=h / 2, fill=None, outline=border_color, width=2)
        # Text centering based on actual bounding box
        bbox = b_draw.textbbox((0, 0), text, font=badge_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        tx = x + (w - text_w) / 2 - bbox[0]
        ty = y + (h - text_h) / 2 - bbox[1]
        b_draw.text((tx, ty), text, fill=text_color, font=badge_font)

        nonlocal img, draw
        img = Image.alpha_composite(img, badge_layer)
        draw = ImageDraw.Draw(img)

    badge_w = 165
    badge_gap = 20
    # Badge 1: P2P
    draw_badge(x_start, badges_y, badge_w, badges_h, (120, 53, 15, 38), (180, 83, 9, 255), "P2P / Torrents", (245, 158, 11, 255))
    # Badge 2: Usenet
    draw_badge(x_start + badge_w + badge_gap, badges_y, badge_w, badges_h, (113, 63, 18, 38), (161, 98, 7, 255), "Usenet / NZB", (250, 204, 21, 255))
    # Badge 3: CLI
    draw_badge(x_start + (badge_w + badge_gap) * 2, badges_y, badge_w, badges_h, (41, 37, 36, 102), (87, 83, 78, 255), "CLI & Automation", (231, 229, 228, 255))

    # 8. Render and Paste Logo
    logo_img = draw_logo(logo_size)
    img.paste(logo_img, (int(logo_x), int(logo_y)), mask=logo_img)

    return img


def main():
    print("Generating GitHub Social Preview PNG...")
    base_dir = Path(__file__).resolve().parent.parent

    preview_img = draw_social_preview()
    preview_img.save(base_dir / "social_preview.png", "PNG")

    print("Saved social_preview.png (1280x640) to project root.")


if __name__ == "__main__":
    main()
