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

    def scale_rect(rect):
        return [r * s for r in rect]

    # 1. Background Squircle with vertical gradient
    bg_gradient = Image.new("RGBA", (size, size))
    bg_draw = ImageDraw.Draw(bg_gradient)

    # Interpolate background colors from deep stone-950 to stone-900 (Obsidian Warm Dark)
    # Start: #0c0a09 (12, 10, 9)
    # End: #1c1917 (28, 25, 23)
    for y in range(size):
        ratio = y / (size - 1)
        r = int(12 + (28 - 12) * ratio)
        g = int(10 + (25 - 10) * ratio)
        b = int(9 + (23 - 9) * ratio)
        bg_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Create a mask for rounded rectangle
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    padding = scale_val(16)
    box_size = scale_val(480)
    mask_draw.rounded_rectangle([padding, padding, padding + box_size, padding + box_size], radius=scale_val(112), fill=255)

    # Paste background gradient using mask
    img.paste(bg_gradient, (0, 0), mask=mask)

    # 2. Sleek Border Outline
    border_width = scale_val(6)
    draw.rounded_rectangle(
        [padding, padding, padding + box_size, padding + box_size],
        radius=scale_val(112),
        outline=(41, 37, 36, 255),  # #292524
        width=max(1, int(border_width)),
    )

    # Inner border ring (subtle white opacity)
    inner_padding = padding + scale_val(8)
    inner_box_size = box_size - scale_val(16)
    draw.rounded_rectangle(
        [inner_padding, inner_padding, inner_padding + inner_box_size, inner_padding + inner_box_size],
        radius=scale_val(104),
        outline=(255, 255, 255, 10),  # white with ~4% alpha
        width=1,
    )

    # 3. Connection pipelines (CLI to P2P and Usenet)
    pipeline_width = max(1, int(scale_val(14)))
    # Draw connections with warm copper-gold colors
    # Left-to-Top (P2P): Copper color (180, 83, 9, 255)
    # Left-to-Bottom (Usenet): Gold color (161, 98, 7, 255)
    draw.line([scale_point((160, 256)), scale_point((340, 160))], fill=(180, 83, 9, 255), width=pipeline_width)
    draw.line([scale_point((160, 256)), scale_point((340, 352))], fill=(161, 98, 7, 255), width=pipeline_width)

    # Helper function to draw rounded path (for prompt and lines)
    def draw_rounded_path(points, width, color):
        scaled_pts = [scale_point(pt) for pt in points]
        # Draw joints and end-caps
        for pt in scaled_pts:
            draw.ellipse([pt[0] - width / 2, pt[1] - width / 2, pt[0] + width / 2, pt[1] + width / 2], fill=color)
        # Draw segments
        for i in range(len(scaled_pts) - 1):
            draw.line([scaled_pts[i], scaled_pts[i + 1]], fill=color, width=width)

    # 4. Source Node: CLI
    cli_center = scale_point((160, 256))
    cli_r = scale_val(48)
    draw.ellipse(
        [cli_center[0] - cli_r, cli_center[1] - cli_r, cli_center[0] + cli_r, cli_center[1] + cli_r],
        fill=(41, 37, 36, 255),  # #292524
        outline=(87, 83, 78, 255),  # #57534e
        width=max(1, int(scale_val(4))),
    )

    # CLI Prompt symbol (>_) inside source node
    prompt_width = max(1, int(scale_val(5)))
    draw_rounded_path([(146, 244), (158, 256), (146, 268)], prompt_width, (255, 255, 255, 255))
    draw_rounded_path([(164, 268), (176, 268)], prompt_width, (255, 255, 255, 255))

    # 5. P2P Node (Mesh)
    p2p_center = scale_point((340, 160))
    p2p_r = scale_val(40)
    draw.ellipse(
        [p2p_center[0] - p2p_r, p2p_center[1] - p2p_r, p2p_center[0] + p2p_r, p2p_center[1] + p2p_r],
        fill=(120, 53, 15, 255),  # #78350f
        outline=(180, 83, 9, 255),  # #b45309
        width=max(1, int(scale_val(4))),
    )

    # P2P mesh network lines
    mesh_lines = [
        ((340, 160), (358, 160)),
        ((340, 160), (340, 178)),
        ((340, 160), (322, 160)),
        ((340, 160), (340, 142)),
        ((358, 160), (340, 178)),
        ((340, 178), (322, 160)),
        ((322, 160), (340, 142)),
        ((340, 142), (358, 160)),
    ]
    for pt1, pt2 in mesh_lines:
        draw.line([scale_point(pt1), scale_point(pt2)], fill=(255, 255, 255, 255), width=max(1, int(scale_val(2))))

    # Mesh network nodes
    draw.ellipse([scale_val(334), scale_val(154), scale_val(346), scale_val(166)], fill=(255, 255, 255, 255))
    draw.ellipse([scale_val(354), scale_val(156), scale_val(362), scale_val(164)], fill=(255, 255, 255, 255))
    draw.ellipse([scale_val(336), scale_val(174), scale_val(344), scale_val(182)], fill=(255, 255, 255, 255))
    draw.ellipse([scale_val(318), scale_val(156), scale_val(326), scale_val(164)], fill=(255, 255, 255, 255))
    draw.ellipse([scale_val(336), scale_val(138), scale_val(344), scale_val(146)], fill=(255, 255, 255, 255))

    # 6. Usenet Node (Papers Stack)
    usenet_center = scale_point((340, 352))
    usenet_r = scale_val(40)
    draw.ellipse(
        [usenet_center[0] - usenet_r, usenet_center[1] - usenet_r, usenet_center[0] + usenet_r, usenet_center[1] + usenet_r],
        fill=(113, 63, 18, 255),  # #713f12
        outline=(161, 98, 7, 255),  # #a16207
        width=max(1, int(scale_val(4))),
    )

    # Stack of two papers representing Usenet articles
    paper_stroke = max(1, int(scale_val(3)))
    draw.rounded_rectangle(scale_rect([325, 338, 347, 364]), radius=scale_val(2), fill=(113, 63, 18, 255), outline=(255, 255, 255, 255), width=paper_stroke)
    draw.rounded_rectangle(scale_rect([333, 344, 355, 370]), radius=scale_val(2), fill=(113, 63, 18, 255), outline=(255, 255, 255, 255), width=paper_stroke)
    # Detail lines on the front paper
    line_stroke = max(1, int(scale_val(2.5)))
    draw.line([scale_point((339, 351)), scale_point((349, 351))], fill=(255, 255, 255, 255), width=line_stroke)
    draw.line([scale_point((339, 357)), scale_point((349, 357))], fill=(255, 255, 255, 255), width=line_stroke)

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
    sizes = [16, 32, 48, 64, 128, 256]
    # Save favicon.ico to web_ui/static/
    favicon_path = web_static / "favicon.ico"
    master_logo.save(favicon_path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"Saved multi-resolution favicon.ico to {favicon_path}")

    # Save logo.ico to scripts/ for the Windows Installer
    installer_ico_path = scripts_dir / "logo.ico"
    master_logo.save(installer_ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"Saved installer logo.ico to {installer_ico_path}")

    print("Asset generation complete!")


if __name__ == "__main__":
    main()
