"""Draw the Nook mark: a white focus ring, three-quarters done, on the app's dark tile.
Writes build/focusos.ico (16-256 px) and ui/logo.png (512 px). Run: py build/make_icon.py"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BG, TRACK, FG = (22, 22, 24, 255), (255, 255, 255, 40), (255, 255, 255, 255)


def mark(px):
    k = 8                                   # draw big, shrink once: smooth edges at every size
    n = px * k
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.225), fill=BG)
    w = n * (0.13 if px > 32 else 0.16)     # thicker ring on tiny icons so it still reads
    pad = n * 0.22
    box = [pad, pad, n - pad, n - pad]
    d.ellipse(box, outline=TRACK, width=int(w))
    d.arc(box, -90, 180, fill=FG, width=int(w))
    r = w / 2                               # round caps on the arc
    c, rad = n / 2, (n - 2 * pad) / 2 - w / 2
    for x, y in ((c, c - rad), (c - rad, c)):
        d.ellipse([x - r, y - r, x + r, y + r], fill=FG)
    return img.resize((px, px), Image.LANCZOS)


if __name__ == "__main__":
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    big = mark(256)
    big.save(os.path.join(ROOT, "build", "focusos.ico"), sizes=[(s, s) for s in sizes],
             append_images=[mark(s) for s in sizes[:-1]])
    mark(512).save(os.path.join(ROOT, "ui", "logo.png"))
    print("icon written")
