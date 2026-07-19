from pathlib import Path

from PIL import Image, ImageDraw


def draw_logo(size=512):
    # Create an image with transparent background
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Scale factor based on canvas size (512 is baseline)
    s = size / 512.0

    # Coordinates scaling helpers
    def scale_point(pt):
        return (pt[0] * s, pt[1] * s)

    def scale_val(val):
        return val * s

    # 1. Background Squircle with vertical gradient
    bg_gradient = Image.new("RGBA", (size, size))
    bg_draw = ImageDraw.Draw(bg_gradient)

    # Interpolate background colors from deep slate-950 to deep purple-indigo
    # Start: #070814 (7, 8, 20)
    # Mid: #0f1123 (15, 17, 35)
    # End: #1a1435 (26, 20, 53)
    for y in range(size):
        ratio = y / (size - 1)
        if ratio < 0.5:
            # Interpolate between Start and Mid
            r = int(7 + (15 - 7) * (ratio * 2))
            g = int(8 + (17 - 8) * (ratio * 2))
            b = int(20 + (35 - 20) * (ratio * 2))
        else:
            # Interpolate between Mid and End
            r = int(15 + (26 - 15) * ((ratio - 0.5) * 2))
            g = int(17 + (20 - 17) * ((ratio - 0.5) * 2))
            b = int(35 + (53 - 35) * ((ratio - 0.5) * 2))
        bg_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Create a mask for rounded rectangle
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    padding = scale_val(16)
    box_size = scale_val(480)
    mask_draw.rounded_rectangle([padding, padding, padding + box_size, padding + box_size], radius=scale_val(112), fill=255)

    # Paste background gradient using mask
    img.paste(bg_gradient, (0, 0), mask=mask)

    # 2. Glowing Border Outline
    border_width = scale_val(8)
    draw.rounded_rectangle(
        [padding, padding, padding + box_size, padding + box_size],
        radius=scale_val(112),
        outline=(99, 102, 241, 230),  # #6366f1 Indigo-500
        width=max(1, int(border_width)),
    )

    # 3. Code Brackets (Left & Right)
    bracket_width = max(1, int(scale_val(24)))
    bracket_color = (6, 182, 212, 255)  # #06b6d4 (Cyan-500)

    def draw_rounded_path(points, width, color):
        scaled_pts = [scale_point(pt) for pt in points]
        # Draw joints and end-caps
        for pt in scaled_pts:
            draw.ellipse([pt[0] - width / 2, pt[1] - width / 2, pt[0] + width / 2, pt[1] + width / 2], fill=color)
        # Draw segments
        for i in range(len(scaled_pts) - 1):
            draw.line([scaled_pts[i], scaled_pts[i + 1]], fill=color, width=width)

    draw_rounded_path([(155, 176), (95, 256), (155, 336)], bracket_width, bracket_color)
    draw_rounded_path([(357, 176), (417, 256), (357, 336)], bracket_width, bracket_color)

    # 4. Rocket Arrow (Center)
    rocket_points = [(256, 101), (322, 196), (276, 186), (276, 256), (236, 256), (236, 186), (190, 196)]
    scaled_rocket_pts = [scale_point(pt) for pt in rocket_points]
    draw.polygon(scaled_rocket_pts, fill=(217, 70, 239, 255))  # #d946ef

    # 5. Rising Data Packets
    packet_color1 = (139, 92, 246, 255)  # Violet-500
    packet_color2 = (59, 130, 246, 180)  # Blue-500 with alpha
    packet_color3 = (59, 130, 246, 100)  # Blue-500 with lower alpha

    p1 = [scale_val(x) for x in [236, 281, 276, 296]]
    draw.rounded_rectangle(p1, radius=scale_val(7.5), fill=packet_color1)

    p2 = [scale_val(x) for x in [236, 321, 276, 336]]
    draw.rounded_rectangle(p2, radius=scale_val(7.5), fill=packet_color2)

    p3 = [scale_val(x) for x in [241, 361, 271, 373]]
    draw.rounded_rectangle(p3, radius=scale_val(6), fill=packet_color3)

    # 6. Terminal Cursor
    cursor_color = (20, 184, 166, 255)  # #14b8a6 (Teal-500)
    c_box = [scale_val(x) for x in [216, 396, 296, 410]]
    draw.rounded_rectangle(c_box, radius=scale_val(7), fill=cursor_color)

    return img


def main():
    print("Generating assets for Upload-Assistant...")

    # Base directory paths
    base_dir = Path(__file__).resolve().parent.parent
    web_static_img = base_dir / "web_ui" / "static" / "img"
    web_static = base_dir / "web_ui" / "static"
    scripts_dir = base_dir / "scripts"

    web_static_img.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # Generate 512x512 master logo
    master_logo = draw_logo(512)

    # Save PNG versions
    master_logo.save(web_static_img / "logo.png", "PNG")
    master_logo.save(base_dir / "logo.png", "PNG")
    print("Saved logo.png (512x512) to web_ui/static/img/ and root.")

    # Generate and save multi-resolution ICO files
    # Windows installers and browser favicons benefit from standard sizes: 16, 32, 48, 64, 128, 256
    sizes = [16, 32, 48, 64, 128, 256]
    ico_images = [draw_logo(s) for s in sizes]

    # Save favicon.ico to web_ui/static/
    favicon_path = web_static / "favicon.ico"
    ico_images[0].save(favicon_path, format="ICO", sizes=[(s, s) for s in sizes], append_images=ico_images[1:])
    print(f"Saved multi-resolution favicon.ico to {favicon_path}")

    # Save logo.ico to scripts/ for the Windows Installer
    installer_ico_path = scripts_dir / "logo.ico"
    ico_images[0].save(installer_ico_path, format="ICO", sizes=[(s, s) for s in sizes], append_images=ico_images[1:])
    print(f"Saved installer logo.ico to {installer_ico_path}")

    print("Asset generation complete!")


if __name__ == "__main__":
    main()
