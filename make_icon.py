"""Generates assets/icon.png and assets/icon.ico (run once; output is committed)."""
import math
import os
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((32, 32, S - 32, S - 32), radius=230, fill="#1e1e2e")
d.rounded_rectangle((32, 32, S - 32, S - 32), radius=230, outline="#4a4a68", width=14)

# five-petal sakura
cx, cy, R = S // 2, S // 2 - 30, 250
for k in range(5):
    a = math.radians(-90 + k * 72)
    px, py = cx + R * 0.62 * math.cos(a), cy + R * 0.62 * math.sin(a)
    r = R * 0.5
    d.ellipse((px - r, py - r, px + r, py + r), fill="#f5c2e7")
d.ellipse((cx - 70, cy - 70, cx + 70, cy + 70), fill="#cba6f7")

# terminal prompt  >_
y = S - 250
d.line([(300, y - 60), (390, y), (300, y + 60)], fill="#a6e3a1", width=34, joint="curve")
d.rounded_rectangle((430, y + 40, 640, y + 72), radius=14, fill="#a6e3a1")

os.makedirs("assets", exist_ok=True)
img.resize((256, 256), Image.LANCZOS).save("assets/icon.png")
img.save("assets/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icons written")
