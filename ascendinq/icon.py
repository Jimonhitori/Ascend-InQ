"""App icon drawn in code (no image files needed): a gold upward chevron."""
from PIL import Image, ImageDraw

COLORS = {
    "waiting": "#c8aa6e",     # gold
    "recording": "#c8aa6e",
    "processing": "#4fa3ff",  # blue
    "paused": "#7a828c",      # gray
    "error": "#ff5d5d",
    "stopped": "#7a828c",
    "starting": "#c8aa6e",
}


def make_icon(state: str = "waiting", size: int = 64) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 5, fill="#12161b")
    color = COLORS.get(state, COLORS["waiting"])
    w = max(2, s // 9)
    for dy in (0.18, 0.42):  # double chevron = "ascend"
        y = s * dy
        d.line([(s * 0.2, y + s * 0.32), (s * 0.5, y + s * 0.06), (s * 0.8, y + s * 0.32)],
               fill=color, width=w, joint="curve")
    if state == "recording":
        r = s * 0.13
        d.ellipse([s - 2.6 * r, s * 0.06, s - 0.6 * r, s * 0.06 + 2 * r], fill="#ff3b3b", outline="#12161b")
    return img


def save_ico(path):
    sizes = [16, 24, 32, 48, 64, 128, 256]
    make_icon("waiting", 256).save(path, format="ICO", sizes=[(n, n) for n in sizes])
