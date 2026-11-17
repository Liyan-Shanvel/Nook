"""Draw the Deepcus mark, "steps": a light tile where ember blocks stack up toward the corner, one block
per focus session, warmest where they pile highest. (Before 1.4.1 the mark was "the dive", kept below as
dive_mark so it can come back with one line.)
Writes build/focusos.ico (16-256 px) and ui/logo.png (512 px). Run: py build/make_icon.py"""
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILE, GRID = (241, 239, 238, 255), (226, 223, 221, 255)
# (column, row) on a 5x5 grid -> colour; empty cells show the light tile
CELLS = {
    (3, 1): (230, 165, 150), (4, 1): (239, 211, 203),
    (2, 2): (236, 143, 120), (3, 2): (238, 95, 64), (4, 2): (236, 122, 99),
    (1, 3): (233, 165, 150), (2, 3): (245, 163, 92), (3, 3): (246, 146, 63), (4, 3): (239, 90, 55),
    (1, 4): (233, 115, 90), (2, 4): (244, 128, 63), (3, 4): (242, 122, 60), (4, 4): (232, 64, 31),
}
GLOW = (255, 197, 107)                      # amber heart of the stack


def mark(px):
    k = 8 if px <= 64 else 4                # draw big, shrink once: smooth edges at every size
    n = px * k
    c = n / 5                               # one cell
    img = Image.new("RGBA", (n, n), TILE)
    d = ImageDraw.Draw(img)
    if px >= 40:                            # faint grid only where it can be seen
        for i in range(1, 5):
            d.line([(i * c, 0), (i * c, n)], fill=GRID, width=max(1, n // 400))
            d.line([(0, i * c), (n, i * c)], fill=GRID, width=max(1, n // 400))
    for (col, row), rgb in CELLS.items():
        d.rectangle([col * c, row * c, (col + 1) * c, (row + 1) * c], fill=rgb + (255,))
    # warm glow over the stack only, centred low in the pile
    glow = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gx, gy, gr = 2.55 * c, 3.45 * c, 1.35 * c
    gd.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=GLOW + (150,))
    glow = glow.filter(ImageFilter.GaussianBlur(c * 0.6))
    stack = Image.new("L", (n, n), 0)
    sd = ImageDraw.Draw(stack)
    for (col, row) in CELLS:
        sd.rectangle([col * c, row * c, (col + 1) * c, (row + 1) * c], fill=255)
    glow.putalpha(ImageChops.multiply(glow.getchannel("A"), stack))
    img = Image.alpha_composite(img, glow)
    if px >= 64:                            # fine grain, like the reference; noise on tiny icons is mush
        rnd = random.Random(4)
        grain = Image.new("L", (n, n), 0)
        gp = grain.load()
        for _ in range(n * n // 60):
            gp[rnd.randrange(n), rnd.randrange(n)] = rnd.randrange(40, 110)
        white = Image.new("L", (n, n), 255)
        img = Image.alpha_composite(img, Image.merge("RGBA", (white, white, white, ImageChops.multiply(grain, stack))))
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.225), fill=255)
    img.putalpha(mask)
    return img.resize((px, px), Image.LANCZOS)


# --- the previous mark, "the dive" (1.3.0 - 1.4.0) -------------------------------------------------
BG, FG, EMBER = (22, 22, 24, 255), (255, 255, 255, 255), (255, 122, 61, 255)
RINGS = ((11, 19, 6.4), (23, 12.5, 4.4), (33, 6.6, 2.6))
DOT = (42, 3.2)


def dive_mark(px):
    k = 8
    n = px * k
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.225), fill=BG)
    small = px <= 32
    rings = RINGS[:2] if px <= 20 else RINGS
    stroke = 4.6 if px <= 20 else 3.8 if small else 3.0
    dot_y, dot_r = (38, 4.6) if px <= 20 else (DOT[0], 3.8 if small else DOT[1])
    pad = n * (0.13 if small else 0.17)
    u = (n - 2 * pad) / 48
    X = lambda v: pad + v * u               # noqa: E731
    for cy, rx, ry in rings:
        if px <= 20:
            cy, ry = cy + 2, ry + 1.2
        h = stroke / 2
        d.ellipse([X(24 - rx - h), X(cy - ry - h), X(24 + rx + h), X(cy + ry + h)], outline=FG, width=max(1, int(stroke * u)))
    d.ellipse([X(24 - dot_r), X(dot_y - dot_r), X(24 + dot_r), X(dot_y + dot_r)], fill=EMBER)
    return img.resize((px, px), Image.LANCZOS)


if __name__ == "__main__":
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    big = mark(256)
    big.save(os.path.join(ROOT, "build", "focusos.ico"), sizes=[(s, s) for s in sizes],
             append_images=[mark(s) for s in sizes[:-1]])
    mark(512).save(os.path.join(ROOT, "ui", "logo.png"))
    print("icon written")
