from io import BytesIO
from pathlib import Path
from shutil import copyfile

from PIL import Image
from resvg_py import svg_to_bytes

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_SVG = BASE_DIR / "docs" / "assets" / "logo.svg"
APP_ICON_BACKGROUND = (16, 14, 13, 255)


def draw_logo(size=512, svg_path=SOURCE_SVG):
    """Render the repository logo SVG as a Pillow image.

    Keeping this helper preserves the API used by generate_social_preview.py,
    while ensuring every generated raster asset comes from the same SVG source.
    """
    if not svg_path.is_file():
        raise FileNotFoundError(f"Logo source not found: {svg_path}")

    rendered_svg = svg_to_bytes(svg_path=str(svg_path), width=size, height=size)
    return Image.open(BytesIO(rendered_svg)).convert("RGBA")


def draw_app_icon(logo):
    """Make an opaque app icon so transparent padding cannot render white."""
    background = Image.new("RGBA", logo.size, APP_ICON_BACKGROUND)
    return Image.alpha_composite(background, logo)


def main():
    print("Generating assets for Upload-Assistant...")

    # Base directory paths
    base_dir = BASE_DIR
    web_static_img = base_dir / "web_ui" / "static" / "img"
    web_static = base_dir / "web_ui" / "static"
    scripts_dir = base_dir / "scripts"

    if not SOURCE_SVG.is_file():
        raise FileNotFoundError(f"Logo source not found: {SOURCE_SVG}")

    web_static_img.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # Keep the Web UI SVG beside its rasterized variants.
    web_logo_svg = web_static_img / "logo.svg"
    copyfile(SOURCE_SVG, web_logo_svg)
    print(f"Copied {SOURCE_SVG} to {web_logo_svg}")

    # Render every raster asset from the root SVG source.
    master_logo = draw_logo(512)
    app_icon = draw_app_icon(master_logo)
    pwa_logo_192 = draw_app_icon(draw_logo(192))

    # Save PNG versions
    master_logo.save(web_static_img / "logo.png", "PNG")
    master_logo.save(base_dir / "docs" / "assets" / "logo.png", "PNG")
    print("Saved logo.png (512x512) to web_ui/static/img/ and docs/assets/.")

    app_icon_path = web_static_img / "apple-touch-icon.png"
    app_icon.save(app_icon_path, "PNG")
    print(f"Saved opaque app icon (512x512) to {app_icon_path}")

    pwa_icon_192_path = web_static_img / "icon-192.png"
    pwa_logo_192.save(pwa_icon_192_path, "PNG")
    print(f"Saved opaque app icon (192x192) to {pwa_icon_192_path}")

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
