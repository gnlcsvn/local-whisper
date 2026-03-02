"""Generate the LocalWhisper app icon: lock + waveform design.

Full-bleed 1024x1024 — macOS applies its own squircle mask.
"""
from PIL import Image, ImageDraw, ImageFilter
import math
import os

SIZE = 1024


def _rounded_rect_points(x, y, w, h, r, steps=8):
    """Generate points for a rounded rectangle path."""
    pts = []
    corners = [
        (x + w - r, y + r, -90, 0),       # top-right
        (x + w - r, y + h - r, 0, 90),     # bottom-right
        (x + r, y + h - r, 90, 180),        # bottom-left
        (x + r, y + r, 180, 270),            # top-left
    ]
    # Top edge
    pts.append((x + r, y))
    pts.append((x + w - r, y))
    # top-right corner
    for i in range(steps + 1):
        a = math.radians(-90 + 90 * i / steps)
        pts.append((x + w - r + r * math.cos(a), y + r + r * math.sin(a)))
    # Right edge
    pts.append((x + w, y + h - r))
    # bottom-right corner
    for i in range(steps + 1):
        a = math.radians(0 + 90 * i / steps)
        pts.append((x + w - r + r * math.cos(a), y + h - r + r * math.sin(a)))
    # Bottom edge
    pts.append((x + r, y + h))
    # bottom-left corner
    for i in range(steps + 1):
        a = math.radians(90 + 90 * i / steps)
        pts.append((x + r + r * math.cos(a), y + h - r + r * math.sin(a)))
    # Left edge
    pts.append((x, y + r))
    # top-left corner
    for i in range(steps + 1):
        a = math.radians(180 + 90 * i / steps)
        pts.append((x + r + r * math.cos(a), y + r + r * math.sin(a)))
    return pts


def _draw_arch(draw, cx, top_y, outer_w, inner_w, leg_bottom, color, steps=32):
    """Draw the lock arch (U-shape) with an arch hole."""
    # Outer arch path
    outer_pts = []
    # Left leg bottom
    outer_pts.append((cx - outer_w, leg_bottom))
    # Left leg up to arch start
    outer_pts.append((cx - outer_w, top_y + outer_w))
    # Arch curve (semicircle, top)
    for i in range(steps + 1):
        a = math.radians(180 + 180 * i / steps)
        outer_pts.append((cx + outer_w * math.cos(a), top_y + outer_w + outer_w * math.sin(a)))
    # Right leg down
    outer_pts.append((cx + outer_w, leg_bottom))
    # Now inner cutout (reverse direction for hole)
    outer_pts.append((cx + inner_w, leg_bottom))
    outer_pts.append((cx + inner_w, top_y + outer_w))
    for i in range(steps + 1):
        a = math.radians(0 + 180 * i / steps)  # reverse
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

    # ── Lock body ──
    body_l = int(26 * S)
    body_r = int(94 * S)
    body_t = int(48 * S)
    body_b = int(106 * S)
    body_rad = int(12 * S)
    body_w = body_r - body_l
    body_h = body_b - body_t

    # Glass fill for the lock body (semi-transparent white)
    lock_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    lock_draw = ImageDraw.Draw(lock_layer)

    # Body rounded rectangle
    lock_draw.rounded_rectangle(
        [body_l, body_t, body_r, body_b],
        radius=body_rad,
        fill=(255, 255, 255, 38),  # ~0.15 opacity glass
    )

    # ── Lock arch ──
    arch_cx = int(60 * S)
    arch_outer_w = int(19 * S)
    arch_inner_w = int(11 * S)
    arch_top_y = int(20 * S)

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
    # Body border
    border_draw.rounded_rectangle(
        [body_l, body_t, body_r, body_b],
        radius=body_rad,
        fill=None,
        outline=(255, 255, 255, 40),
        width=max(1, int(0.7 * S)),
    )
    # Arch border
    _draw_arch(
        border_draw,
        cx=arch_cx,
        top_y=arch_top_y,
        outer_w=arch_outer_w,
        inner_w=arch_inner_w,
        leg_bottom=body_t,
        color=(255, 255, 255, 30),
    )

    img = Image.alpha_composite(img, lock_layer)
    img = Image.alpha_composite(img, border_layer)

    # ── Arch hole fill (background color to punch out) ──
    hole_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    hole_draw = ImageDraw.Draw(hole_layer)
    # Fill the inner arch area with the dark background color
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
    hole_draw.polygon(hole_pts, fill=(21, 19, 43, 255))
    img = Image.alpha_composite(img, hole_layer)

    # ── Waveform bars inside lock body ──
    bars_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bars_draw = ImageDraw.Draw(bars_layer)

    bar_cy = int(79 * S)  # center of bars (body center + slight offset)
    bar_data = [
        {"x": 35.2, "h": 15.3, "color": (90, 200, 250), "alpha": 153},   # #5AC8FA, 0.6
        {"x": 46.3, "h": 25.8, "color": (108, 99, 255), "alpha": 242},    # #6C63FF, 0.95
        {"x": 57.4, "h": 20.0, "color": (90, 200, 250), "alpha": 153},    # #5AC8FA, 0.6
        {"x": 68.5, "h": 29.3, "color": (108, 99, 255), "alpha": 242},    # #6C63FF, 0.95
        {"x": 79.6, "h": 11.7, "color": (90, 200, 250), "alpha": 153},    # #5AC8FA, 0.6
    ]
    bar_w = 6.6

    for bar in bar_data:
        bx = int(bar["x"] * S)
        bw = int(bar_w * S)
        bh = int(bar["h"] * S)
        by = bar_cy - bh // 2
        br = bw // 2  # rounded end radius
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
        [int(38 * S), int(6 * S), int(72 * S), int(22 * S)],
        fill=(255, 255, 255, 20),
    )
    # Inner body top-left sheen
    spec_draw.rounded_rectangle(
        [body_l + int(3 * S), body_t + int(2 * S),
         body_l + int(31 * S), body_t + int(12 * S)],
        radius=int(5 * S),
        fill=(255, 255, 255, 12),
    )

    spec_blurred = spec_layer.filter(ImageFilter.GaussianBlur(radius=int(2 * S)))
    img = Image.alpha_composite(img, spec_blurred)

    # ── Save ──
    out_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(out_dir, "icon_1024.png")
    img.save(png_path, "PNG")
    print(f"Saved {png_path}")
    return png_path


if __name__ == "__main__":
    make_icon()
