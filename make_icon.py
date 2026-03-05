"""Generate the LocalWhisper app icon: lock + waveform design.

Matches the idle state from the animation reference.
Full-bleed 1024x1024 — macOS applies its own squircle mask.
"""
from PIL import Image, ImageDraw, ImageFilter
import math
import os

SIZE = 1024


def _draw_arch(draw, cx, top_y, outer_w, inner_w, leg_bottom, color, steps=32):
    """Draw the lock arch (U-shape) with an arch hole."""
    outer_pts = []
    outer_pts.append((cx - outer_w, leg_bottom))
    outer_pts.append((cx - outer_w, top_y + outer_w))
    for i in range(steps + 1):
        a = math.radians(180 + 180 * i / steps)
        outer_pts.append((cx + outer_w * math.cos(a), top_y + outer_w + outer_w * math.sin(a)))
    outer_pts.append((cx + outer_w, leg_bottom))
    # Inner cutout (reverse direction for hole)
    outer_pts.append((cx + inner_w, leg_bottom))
    outer_pts.append((cx + inner_w, top_y + outer_w))
    for i in range(steps + 1):
        a = math.radians(0 + 180 * i / steps)
        outer_pts.append((cx + inner_w * math.cos(a), top_y + outer_w + inner_w * math.sin(a)))
    outer_pts.append((cx - inner_w, leg_bottom))
    outer_pts.append((cx - outer_w, leg_bottom))
    draw.polygon(outer_pts, fill=color)


def make_icon():
    # ── Geometry (in 120-unit space, scaled to 1024) ──
    S = SIZE / 120.0

    # Background: deep indigo gradient, fills entire canvas (full-bleed)
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bg = Image.new("RGBA", (SIZE, SIZE))
    for y in range(SIZE):
        t = y / SIZE
        r = int(45 * (1 - t) + 21 * t)    # #2D -> #15
        g = int(43 * (1 - t) + 19 * t)     # #2B -> #13
        b = int(85 * (1 - t) + 43 * t)     # #55 -> #2B
        for x in range(SIZE):
            bg.putpixel((x, y), (r, g, b, 255))
    img = Image.alpha_composite(img, bg)

    # ── Lock body (matches new idle SVG) ──
    body_l = int(27.6 * S)
    body_r = int(92.4 * S)
    body_t = int(44.2 * S)
    body_b = int(99.4 * S)
    body_rad = int(9.2 * S)

    # Glass fill for the lock body
    lock_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    lock_draw = ImageDraw.Draw(lock_layer)

    lock_draw.rounded_rectangle(
        [body_l, body_t, body_r, body_b],
        radius=body_rad,
        fill=(255, 255, 255, 38),  # ~0.15 opacity glass
    )

    # ── Lock arch ──
    arch_cx = int(60 * S)
    arch_outer_w = int(19 * S)
    arch_inner_w = int(11 * S)
    # Arch top: center at y=32.3, minus radius -> top at 32.3-19=13.3
    arch_top_y = int(13.3 * S)

    _draw_arch(
        lock_draw,
        cx=arch_cx,
        top_y=arch_top_y,
        outer_w=arch_outer_w,
        inner_w=arch_inner_w,
        leg_bottom=body_t,
        color=(255, 255, 255, 38),
    )

    # Subtle border on the lock shape
    border_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_layer)
    border_draw.rounded_rectangle(
        [body_l, body_t, body_r, body_b],
        radius=body_rad,
        fill=None,
        outline=(255, 255, 255, 38),
        width=max(1, int(0.5 * S)),
    )
    _draw_arch(
        border_draw,
        cx=arch_cx,
        top_y=arch_top_y,
        outer_w=arch_outer_w,
        inner_w=arch_inner_w,
        leg_bottom=body_t,
        color=(255, 255, 255, 28),
    )

    img = Image.alpha_composite(img, lock_layer)
    img = Image.alpha_composite(img, border_layer)

    # ── Arch hole fill (background color to punch out) ──
    hole_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    hole_draw = ImageDraw.Draw(hole_layer)
    hole_pts = []
    hole_pts.append((arch_cx - arch_inner_w, body_t))
    hole_pts.append((arch_cx - arch_inner_w, arch_top_y + arch_outer_w))
    steps = 32
    for i in range(steps + 1):
        a = math.radians(180 + 180 * i / steps)
        hole_pts.append((
            arch_cx + arch_inner_w * math.cos(a),
            arch_top_y + arch_outer_w + arch_inner_w * math.sin(a),
        ))
    hole_pts.append((arch_cx + arch_inner_w, body_t))
    # Color at arch center (~y=23 in 120-unit space)
    hole_draw.polygon(hole_pts, fill=(40, 38, 77, 255))
    img = Image.alpha_composite(img, hole_layer)

    # ── Waveform bars inside lock body (exact positions from idle SVG) ──
    bars_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bars_draw = ImageDraw.Draw(bars_layer)

    bar_data = [
        {"x": 35.2, "y": 67.9, "h": 15.3, "color": (90, 200, 250), "alpha": 153},   # #5AC8FA, 0.6
        {"x": 46.3, "y": 59.1, "h": 25.8, "color": (108, 99, 255), "alpha": 242},    # #6C63FF, 0.95
        {"x": 57.4, "y": 64.0, "h": 20.0, "color": (90, 200, 250), "alpha": 153},    # #5AC8FA, 0.6
        {"x": 68.5, "y": 56.7, "h": 29.3, "color": (108, 99, 255), "alpha": 242},    # #6C63FF, 0.95
        {"x": 79.6, "y": 69.7, "h": 11.7, "color": (90, 200, 250), "alpha": 153},    # #5AC8FA, 0.6
    ]
    bar_w = 6.6

    for bar in bar_data:
        bx = int(bar["x"] * S)
        by = int(bar["y"] * S)
        bw = int(bar_w * S)
        bh = int(bar["h"] * S)
        br = bw // 2
        r, g, b = bar["color"]
        a = bar["alpha"]
        bars_draw.rounded_rectangle(
            [bx, by, bx + bw, by + bh],
            radius=br,
            fill=(r, g, b, a),
        )

    img = Image.alpha_composite(img, bars_layer)

    # ── Specular highlights ──
    spec_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    spec_draw = ImageDraw.Draw(spec_layer)

    # Top specular sheen on arch
    spec_draw.ellipse(
        [int(38 * S), int(2 * S), int(72 * S), int(16 * S)],
        fill=(255, 255, 255, 18),
    )
    # Inner body top-left sheen
    spec_draw.rounded_rectangle(
        [body_l + int(3 * S), body_t + int(2 * S),
         body_l + int(28 * S), body_t + int(10 * S)],
        radius=int(4 * S),
        fill=(255, 255, 255, 10),
    )

    spec_blurred = spec_layer.filter(ImageFilter.GaussianBlur(radius=int(2 * S)))
    img = Image.alpha_composite(img, spec_blurred)

    # ── Save ──
    out_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(out_dir, "icon_1024.png")
    img.save(png_path, "PNG")
    print(f"Saved {png_path}")
    return png_path


def make_menubar_template():
    """Generate menubar template images (alpha-only for macOS auto-tinting).

    Renders at 4x resolution then downscales with LANCZOS for crisp anti-aliasing.
    """
    RENDER = 480  # 4x of 120-unit space for quality
    S = RENDER / 120.0

    mask = Image.new("L", (RENDER, RENDER), 0)
    draw = ImageDraw.Draw(mask)

    # Lock body — lighter so bars pop inside (template uses alpha for shading)
    body_alpha = 140
    draw.rounded_rectangle(
        [int(27.6 * S), int(44.2 * S), int(92.4 * S), int(99.4 * S)],
        radius=int(9.2 * S),
        fill=body_alpha,
    )

    # Lock arch (outer) — same lighter alpha
    _draw_arch(
        draw,
        cx=int(60 * S),
        top_y=int(13.3 * S),
        outer_w=int(19 * S),
        inner_w=int(11 * S),
        leg_bottom=int(44.2 * S),
        color=body_alpha,
    )

    # Punch out arch hole
    cx, ay, ri = int(60 * S), int(13.3 * S), int(11 * S)
    ow = int(19 * S)
    hole_pts = []
    hole_pts.append((cx - ri, int(44.2 * S)))
    hole_pts.append((cx - ri, ay + ow))
    for i in range(33):
        a = math.radians(180 + 180 * i / 32)
        hole_pts.append((cx + ri * math.cos(a), ay + ow + ri * math.sin(a)))
    hole_pts.append((cx + ri, int(44.2 * S)))
    draw.polygon(hole_pts, fill=0)

    # Waveform bars
    bar_w = 6.6
    for bx, by, bh in [
        (35.2, 67.9, 15.3),
        (46.3, 59.1, 25.8),
        (57.4, 64.0, 20.0),
        (68.5, 56.7, 29.3),
        (79.6, 69.7, 11.7),
    ]:
        draw.rounded_rectangle(
            [int(bx * S), int(by * S), int((bx + bar_w) * S), int((by + bh) * S)],
            radius=int(3.3 * S),
            fill=255,
        )

    # Convert mask to RGBA template (black RGB + alpha from mask)
    black = Image.new("L", (RENDER, RENDER), 0)
    full = Image.merge("RGBA", (black, black, black, mask))

    out_dir = os.path.dirname(os.path.abspath(__file__))
    for target, name in [(22, "menubarTemplate.png"), (44, "menubarTemplate@2x.png")]:
        resized = full.resize((target, target), Image.LANCZOS)
        path = os.path.join(out_dir, name)
        resized.save(path, "PNG")
        print(f"Saved {path}")


if __name__ == "__main__":
    make_icon()
    make_menubar_template()
