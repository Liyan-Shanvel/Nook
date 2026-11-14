"""Draw the Deepcus mark, "the dive": the timer rings seen from the side as they sink, each one smaller,
down to one ember point. White on the app's dark tile.
Writes build/focusos.ico (16-256 px) and ui/logo.png (512 px). Run: py build/make_icon.py"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BG, FG, EMBER = (22, 22, 24, 255), (255, 255, 255, 255), (255, 122, 61, 255)
# the mark on a 48-unit grid: (centre y, half width, half height) per ring, then the point
RINGS = ((11, 19, 6.4), (23, 12.5, 4.4), (33, 6.6, 2.6))
DOT = (42, 3.2)


def mark(px):
    k = 8                                   # draw big, shrink once: smooth edges at every size
    n = px * k
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.225), fill=BG)
    small = px <= 32
    rings = RINGS[:2] if px <= 20 else RINGS            # two rings on the tiniest icons so they still read
    stroke = 4.6 if px <= 20 else 3.8 if small else 3.0
    dot_y, dot_r = (38, 4.6) if px <= 20 else (DOT[0], 3.8 if small else DOT[1])
    pad = n * (0.13 if small else 0.17)
    u = (n - 2 * pad) / 48                  # one grid unit, in pixels
    X = lambda v: pad + v * u               # noqa: E731
    for cy, rx, ry in rings:
        if px <= 20:
            cy, ry = cy + 2, ry + 1.2
        h = stroke / 2                      # Pillow strokes inward; grow the box so the line sits on the ring
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
