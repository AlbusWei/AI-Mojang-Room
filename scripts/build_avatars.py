"""Build web/avatars/*.png from generated / canonical-derived source images.

Canonical-derived avatars are二次创作 based on the community-recognized AI-girl
designs (see config/profiles.json for credits + license). Original brand-inspired
avatars are kept as orig_* for commercial use.
Crops a square around the character emblem and downsizes to 512px for the web.

P13: 11 new brands (gpt/claude/gemini/grok/seed/minimax/llama/mistral/perplexity/
wenxin/jev). Their canon sources are portrait canvases with a perfect circle whose
diameter equals the canvas width, so the square crop must land exactly on the
circle center — detect_circle_cy() finds it from the solid background span.
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "dsh-image-gen"
OUT = ROOT / "web" / "avatars"
OUT.mkdir(parents=True, exist_ok=True)

CANON = {"deepseek": "image-c55d5b74.png", "qwen": "image-34eab907.png",
         "kimi": "image-afef2dd8.png", "glm": "image-69909017.png",
         "gpt": "image-a5809d98.png", "claude": "image-fb6baa6c.png",
         "gemini": "image-081d39b3.png", "grok": "image-05258c25.png",
         "seed": "image-f97c1a41.png", "minimax": "image-afe9e92a.png",
         "llama": "image-1eef195a.png", "mistral": "image-f04a9ca7.png",
         "perplexity": "image-e87f556e.png", "wenxin": "image-0bb74f48.png",
         "jev": "image-9c1b0eab.png"}
ORIG = {"deepseek": "image-a1ab9173.png", "qwen": "image-d19b0023.png",
        "kimi": "image-42fa0053.png", "glm": "image-6eb1b86e.png",
        "gpt": "image-1d5a4921.png", "claude": "image-fa048611.png",
        "grok": "image-564304c5.png", "gemini": "image-a722b4ae.png",
        "seed": "image-22efceb5.png", "minimax": "image-ffb9556b.png",
        "llama": "image-7e8eb32c.png", "mistral": "image-77faf6ab.png",
        "perplexity": "image-d07d4f0b.png", "wenxin": "image-f10d8d10.png",
        "jev": "image-d0e13c57.png"}
# New canon sources need per-image circle-center detection (see module docstring).
AUTO_CY = {"gpt", "claude", "gemini", "grok", "seed", "minimax", "llama",
           "mistral", "perplexity", "wenxin", "jev"}


def crop_square(im: Image.Image, cy_frac: float) -> Image.Image:
    w, h = im.size
    side = min(w, h)
    cy = int(h * cy_frac)
    top = max(0, min(h - side, cy - side // 2))
    left = max(0, min(w - side, (w - side) // 2))
    return im.crop((left, top, left + side, top + side))


def detect_circle_cy(im: Image.Image) -> float:
    """Vertical center of the inscribed ring circle on a portrait canvas.

    Outside the circle the background is a solid color; scan the center columns
    for the non-background span and return its midpoint as a height fraction.
    Falls back to 0.45 (upper-middle) if the span looks wrong.
    """
    w, h = im.size
    px = im.load()
    bg = px[2, 2]

    def differs(c):
        return abs(c[0] - bg[0]) + abs(c[1] - bg[1]) + abs(c[2] - bg[2]) > 40

    top, bottom = h, -1
    for x in (w // 2 - 2, w // 2, w // 2 + 2):
        for y in range(h):
            if differs(px[x, y]):
                top = min(top, y)
                break
        for y in range(h - 1, -1, -1):
            if differs(px[x, y]):
                bottom = max(bottom, y)
                break
    if bottom - top < w * 0.8:
        return 0.45
    return (top + bottom) / 2 / h


def build(mapping, prefix, cy, auto=()):
    for name, fn in mapping.items():
        src = GEN / fn
        if not src.exists():
            print("missing", src)
            continue
        im = Image.open(src).convert("RGB")
        frac = detect_circle_cy(im) if name in auto else cy
        im = crop_square(im, frac).resize((512, 512), Image.LANCZOS)
        dst = OUT / f"{prefix}{name}.png"
        im.save(dst, optimize=True)
        print("wrote", dst.name, dst.stat().st_size, "bytes", f"cy={frac:.3f}")


if __name__ == "__main__":
    build(CANON, "", 0.47, auto=AUTO_CY)
    build(ORIG, "orig_", 0.5)
