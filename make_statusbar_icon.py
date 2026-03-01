"""Generate macOS status bar template icon for LocalWhisper.

Produces an 18x18pt (36x36px @2x) template image: black on transparent.
macOS automatically handles dark/light mode when the image is named *Template*.
"""
from PIL import Image, ImageDraw
import math
import os


def make_statusbar_icon():
    # @2x for Retina: 36x36 pixels for 18x18pt
    SIZE = 36
    CENTER = SIZE // 2

    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw a simplified version of the app logo:
    # Central orb + circular waveform bars

    # Central filled circle (orb)
    orb_r = 4
    draw.ellipse(
        [CENTER - orb_r, CENTER - orb_r, CENTER + orb_r, CENTER + orb_r],
        fill=(0, 0, 0, 220),
    )

    # Waveform bars in circular arrangement
    num_bars = 16
    base_radius = 8
    max_bar_height = 7

    for i in range(num_bars):
        angle = (i / num_bars) * 360
        angle_rad = math.radians(angle)

        # Organic waveform pattern matching the app icon
        wave = (
            math.sin(angle_rad * 3) * 0.4
            + math.sin(angle_rad * 7 + 1.2) * 0.25
            + math.sin(angle_rad * 11 + 2.5) * 0.15
            + math.sin(angle_rad * 5 + 0.7) * 0.2
        )
        wave = (wave + 1) / 2
        wave = max(0.2, wave)

        bar_h = max(2, int(wave * max_bar_height))

        inner_r = base_radius
        outer_r = base_radius + bar_h

        x1 = CENTER + inner_r * math.cos(angle_rad)
        y1 = CENTER + inner_r * math.sin(angle_rad)
        x2 = CENTER + outer_r * math.cos(angle_rad)
        y2 = CENTER + outer_r * math.sin(angle_rad)

        alpha = int(180 + wave * 75)
        if alpha > 255:
            alpha = 255

        draw.line(
            [(x1, y1), (x2, y2)],
            fill=(0, 0, 0, alpha),
            width=2,
        )

    out_dir = os.path.dirname(os.path.abspath(__file__))
    # Name with "Template" so macOS treats it as a template image
    png_path = os.path.join(out_dir, "statusbar_iconTemplate.png")
    img.save(png_path, "PNG")
    print(f"Saved {png_path}")

    # Also save @2x version explicitly
    png_path_2x = os.path.join(out_dir, "statusbar_iconTemplate@2x.png")
    img.save(png_path_2x, "PNG")
    print(f"Saved {png_path_2x}")

    # Save @1x version (18x18)
    img_1x = img.resize((18, 18), Image.LANCZOS)
    png_path_1x = os.path.join(out_dir, "statusbar_iconTemplate.png")
    img_1x.save(png_path_1x, "PNG")
    print(f"Saved {png_path_1x} (1x)")

    return png_path_2x


if __name__ == "__main__":
    make_statusbar_icon()
