"""Generate the exe icon and the start-up splash image (no external assets needed)."""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ACCENT, INK, MUTED = (0, 113, 227), (29, 29, 31), (110, 110, 115)


def font(size, bold=False):
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def book(d, x, y, s):
    """A simple open book with a row of 'text lines' — the app's mark."""
    d.rounded_rectangle((x, y, x + s, y + s), radius=s // 5, fill=ACCENT)
    m, mid = s // 6, x + s // 2
    d.rounded_rectangle((x + m, y + m, mid - s // 40, y + s - m), radius=s // 25, fill="white")
    d.rounded_rectangle((mid + s // 40, y + m, x + s - m, y + s - m), radius=s // 25, fill="white")
    lw = max(1, s // 28)
    for i in range(4):
        yy = y + m + s // 7 + i * s // 7
        d.line((x + m + s // 14, yy, mid - s // 10, yy), fill=ACCENT, width=lw)
        d.line((mid + s // 10, yy, x + s - m - s // 14, yy), fill=ACCENT, width=lw)


icon = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
book(ImageDraw.Draw(icon), 8, 8, 240)
icon.save(os.path.join(HERE, "app.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

sp = Image.new("RGB", (460, 170), (245, 245, 247))
d = ImageDraw.Draw(sp)
d.rectangle((0, 0, 459, 169), outline=(210, 210, 215))
book(d, 28, 41, 88)
d.text((136, 52), "Exhibition Book Reader", fill=INK, font=font(24, True))
d.text((137, 90), "Catalog photos  →  Excel / Access", fill=MUTED, font=font(14))
sp.save(os.path.join(HERE, "splash.png"))
print("assets written")
