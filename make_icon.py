"""Generate the LocalWhisper app icon: lock + waveform design.

Matches the idle state from localwhisper-animations.html reference.
Full-bleed 1024x1024 — macOS applies its own squircle mask.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import math
import os

SIZE = 1024


def _vgradient(size, top_color, bottom_color):
    """Create a vertical gradient image efficiently."""
    w, h = size
    # Build a 1-pixel-wide column, then stretch
    col = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top_color[0] * (1 - t) + bottom_color[0] * t)
        g = int(top_color[1] * (1 - t) + bottom_color[1] * t)
        b = int(top_color[2] * (1 - t) + bottom_color[2] * t)
        a = int(top_color[3] * (1 - t) + bottom_color[3] * t)
        col.putpixel((0, y), (r, g, b, a))
    return col.resize((w, h), Image.NEAREST)


def _draw_arch(draw, cx, top_y, outer_w, inner_w, leg_bottom, color, steps=64):
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


def _lock_shape_mask(size, S):
    """Create a mask (L mode) of the full lock shape (body + arch - hole)."""
    body_l, body_r = int(27.6 * S), int(92.4 * S)
    body_t, body_b = int(44.2 * S), int(99.4 * S)
    body_rad = int(9.2 * S)
    arch_cx = int(60 * S)
    arch_outer_w, arch_inner_w = int(19 * S), int(11 * S)
    arch_top_y = int(13.3 * S)

    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)

    draw.rounded_rectangle([body_l, body_t, body_r, body_b], radius=body_rad, fill=255)
    _draw_arch(draw, arch_cx, arch_top_y, arch_outer_w, arch_inner_w, body_t, 255)

    # Punch out arch hole
    hole_pts = []
    hole_pts.append((arch_cx - arch_inner_w, body_t))
    hole_pts.append((arch_cx - arch_inner_w, arch_top_y + arch_outer_w))
    for i in range(65):
        a = math.radians(180 + 180 * i / 64)
        hole_pts.append((
            arch_cx + arch_inner_w * math.cos(a),
            arch_top_y + arch_outer_w + arch_inner_w * math.sin(a),
        ))
    hole_pts.append((arch_cx + arch_inner_w, body_t))
    draw.polygon(hole_pts, fill=0)

    return mask


def make_icon():
    S = SIZE / 120.0

    # ── Background: deep indigo gradient (#2D2B55 → #15132B) ──
    img = _vgradient((SIZE, SIZE), (45, 43, 85, 255), (21, 19, 43, 255))

    # ── Drop shadow behind lock (feDropShadow dy=1.5 stdDeviation=2 flood-opacity=.3) ──
    shadow_dy = int(1.5 * S)
    shadow_mask = _lock_shape_mask(SIZE, S)
    # Shift mask down by shadow_dy
    shifted = Image.new("L", (SIZE, SIZE), 0)
    shifted.paste(shadow_mask, (0, shadow_dy))
    shadow_blurred = shifted.filter(ImageFilter.GaussianBlur(radius=int(2 * S)))
    # Scale alpha: flood-opacity 0.3 → max alpha ~76
    shadow_blurred = shadow_blurred.point(lambda p: int(p * 0.3))
    shadow_img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shadow_img.putalpha(shadow_blurred)
    shadow_img_rgb = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    shadow_img_rgb.putalpha(shadow_blurred)
    img = Image.alpha_composite(img, shadow_img_rgb)

    # ── Lock glass fill with vertical gradient (rgba white 0.18 → 0.08) ──
    lock_mask = _lock_shape_mask(SIZE, S)
    # Glass gradient: white with alpha 46 (0.18*255) at top → 20 (0.08*255) at bottom
    glass_grad = _vgradient((SIZE, SIZE), (255, 255, 255, 46), (255, 255, 255, 20))
    # Apply lock shape as mask
    glass_masked = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    glass_masked.paste(glass_grad, mask=lock_mask)
    img = Image.alpha_composite(img, glass_masked)

    # ── Lock stroke (rgba(255,255,255,0.15), ~0.5px scaled) ──
    stroke_w = max(1, int(0.5 * S))
    # Outer shape minus inner shape = stroke
    outer_mask = _lock_shape_mask(SIZE, S)
    # Erode the mask to get inner
    inner_mask = outer_mask.copy()
    # Use a simple approach: draw the shape slightly smaller
    inner = Image.new("L", (SIZE, SIZE), 0)
    inner_draw = ImageDraw.Draw(inner)
    body_l, body_r = int(27.6 * S), int(92.4 * S)
    body_t, body_b = int(44.2 * S), int(99.4 * S)
    body_rad = int(9.2 * S)
    inner_draw.rounded_rectangle(
        [body_l + stroke_w, body_t + stroke_w, body_r - stroke_w, body_b - stroke_w],
        radius=max(0, body_rad - stroke_w),
        fill=255,
    )
    arch_cx = int(60 * S)
    arch_outer_w, arch_inner_w = int(19 * S), int(11 * S)
    arch_top_y = int(13.3 * S)
    _draw_arch(inner_draw, arch_cx, arch_top_y + stroke_w,
               arch_outer_w - stroke_w, arch_inner_w + stroke_w,
               body_t + stroke_w, 255)
    # Punch hole from inner
    hole_pts = []
    hole_pts.append((arch_cx - arch_inner_w - stroke_w, body_t + stroke_w))
    hole_pts.append((arch_cx - arch_inner_w - stroke_w, arch_top_y + stroke_w + arch_outer_w))
    for i in range(65):
        a = math.radians(180 + 180 * i / 64)
        hole_pts.append((
            arch_cx + (arch_inner_w + stroke_w) * math.cos(a),
            arch_top_y + stroke_w + arch_outer_w + (arch_inner_w + stroke_w) * math.sin(a),
        ))
    hole_pts.append((arch_cx + arch_inner_w + stroke_w, body_t + stroke_w))
    inner_draw.polygon(hole_pts, fill=0)

    # Stroke = outer - inner
    stroke_mask = ImageChops.subtract(outer_mask, inner)
    stroke_layer = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 38))  # 0.15 opacity
    stroke_layer.putalpha(stroke_mask.point(lambda p: int(p * 0.15)))
    img = Image.alpha_composite(img, stroke_layer)

    # ── Waveform bars inside lock body (idle state from reference) ──
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

    body_alpha = 140
    draw.rounded_rectangle(
        [int(27.6 * S), int(44.2 * S), int(92.4 * S), int(99.4 * S)],
        radius=int(9.2 * S),
        fill=body_alpha,
    )

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
