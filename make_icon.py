"""Generate an abstract, modern app icon for LocalWhisper."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os

SIZE = 1024
CENTER = SIZE // 2


def make_icon():
    # Start with transparent
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # Rounded rect mask
    radius = int(SIZE * 0.22)
    mask = Image.new("L", (SIZE, SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=radius, fill=255)

    # Gradient background: deep indigo to near-black
    bg = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    for y in range(SIZE):
        t = y / SIZE
        # Deep indigo gradient
        r = int(18 * (1 - t) + 8 * t)
        g = int(10 * (1 - t) + 5 * t)
        b = int(40 * (1 - t) + 20 * t)
        for x in range(SIZE):
            bg.putpixel((x, y), (r, g, b, 255))

    # Apply rounded mask
    result = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    result.paste(bg, mask=mask)

    # --- Draw abstract sound waveform ring ---
    wave_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    wave_draw = ImageDraw.Draw(wave_layer)

    # Central orb - soft glowing circle
    orb_r = 140
    orb_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    orb_draw = ImageDraw.Draw(orb_layer)

    # Multi-layer glow
    for i in range(80, 0, -1):
        alpha = int(2.5 * (80 - i))
        if alpha > 255:
            alpha = 255
        r = orb_r + i * 2
        orb_draw.ellipse(
            [CENTER - r, CENTER - 40 - r, CENTER + r, CENTER - 40 + r],
            fill=(100, 80, 255, min(alpha // 3, 60)),
        )

    # Core orb
    orb_draw.ellipse(
        [CENTER - orb_r, CENTER - 40 - orb_r, CENTER + orb_r, CENTER - 40 + orb_r],
        fill=(130, 110, 255, 200),
    )
    # Bright inner
    inner_r = orb_r - 30
    orb_draw.ellipse(
        [CENTER - inner_r, CENTER - 40 - inner_r, CENTER + inner_r, CENTER - 40 + inner_r],
        fill=(180, 170, 255, 220),
    )
    # White hot center
    core_r = 50
    orb_draw.ellipse(
        [CENTER - core_r, CENTER - 40 - core_r, CENTER + core_r, CENTER - 40 + core_r],
        fill=(230, 225, 255, 240),
    )

    result = Image.alpha_composite(result, orb_layer)

    # --- Waveform bars in a circular arrangement ---
    bars_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bars_draw = ImageDraw.Draw(bars_layer)

    num_bars = 48
    base_radius = 200
    max_bar_height = 160
    bar_width_angle = 2.5  # degrees

    for i in range(num_bars):
        angle = (i / num_bars) * 360
        angle_rad = math.radians(angle)

        # Create organic waveform pattern (multiple sine waves combined)
        wave = (
            math.sin(angle_rad * 3) * 0.4
            + math.sin(angle_rad * 7 + 1.2) * 0.25
            + math.sin(angle_rad * 11 + 2.5) * 0.15
            + math.sin(angle_rad * 5 + 0.7) * 0.2
        )
        wave = (wave + 1) / 2  # normalize to 0-1
        wave = max(0.15, wave)  # minimum bar height

        bar_h = int(wave * max_bar_height)

        # Bar start and end points (radial)
        inner_r = base_radius
        outer_r = base_radius + bar_h

        # Colors: gradient from purple to cyan based on position
        t = i / num_bars
        if t < 0.5:
            # Purple to blue
            cr = int(160 * (1 - t * 2) + 60 * (t * 2))
            cg = int(100 * (1 - t * 2) + 180 * (t * 2))
            cb = 255
        else:
            # Blue to cyan
            t2 = (t - 0.5) * 2
            cr = int(60 * (1 - t2) + 160 * t2)
            cg = int(180 * (1 - t2) + 100 * t2)
            cb = 255

        alpha = int(180 + wave * 75)
        if alpha > 255:
            alpha = 255

        # Draw bar as a thick line
        x1 = CENTER + inner_r * math.cos(angle_rad)
        y1 = CENTER - 40 + inner_r * math.sin(angle_rad)
        x2 = CENTER + outer_r * math.cos(angle_rad)
        y2 = CENTER - 40 + outer_r * math.sin(angle_rad)

        bars_draw.line(
            [(x1, y1), (x2, y2)],
            fill=(cr, cg, cb, alpha),
            width=8,
        )

        # Add rounded caps
        cap_r = 4
        bars_draw.ellipse(
            [x2 - cap_r, y2 - cap_r, x2 + cap_r, y2 + cap_r],
            fill=(cr, cg, cb, alpha),
        )

    # Blur the bars slightly for a soft glow effect
    bars_blurred = bars_layer.filter(ImageFilter.GaussianBlur(radius=2))
    result = Image.alpha_composite(result, bars_blurred)
    result = Image.alpha_composite(result, bars_layer)

    # --- Add subtle particle dots ---
    dots_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    dots_draw = ImageDraw.Draw(dots_layer)

    import random
    random.seed(42)  # deterministic
    for _ in range(60):
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(180, 420)
        x = CENTER + dist * math.cos(angle)
        y = CENTER - 40 + dist * math.sin(angle)
        r = random.uniform(1.5, 4)
        alpha = random.randint(40, 120)
        dots_draw.ellipse(
            [x - r, y - r, x + r, y + r],
            fill=(180, 200, 255, alpha),
        )

    result = Image.alpha_composite(result, dots_layer)

    # --- App name at bottom ---
    draw = ImageDraw.Draw(result)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/SFCompact.ttf", 68)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 68)
        except (OSError, IOError):
            font = ImageFont.load_default()

    text = "LocalWhisper"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = (SIZE - tw) // 2
    ty = 830

    # Subtle shadow
    draw.text((tx + 2, ty + 2), text, fill=(0, 0, 0, 80), font=font)
    # Main text - light with slight purple tint
    draw.text((tx, ty), text, fill=(210, 205, 235, 220), font=font)

    # Re-apply rounded mask to clean up edges
    final = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    final.paste(result, mask=mask)

    out_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(out_dir, "icon_1024.png")
    final.save(png_path, "PNG")
    print(f"Saved {png_path}")
    return png_path


if __name__ == "__main__":
    make_icon()
