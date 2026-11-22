"""Contact-sheet QC: montage all canon + orig avatars into labeled grids."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
AV = ROOT / "web" / "avatars"
BRANDS = ["deepseek", "qwen", "kimi", "glm", "gpt", "claude", "gemini", "grok",
          "seed", "minimax", "llama", "mistral", "perplexity", "wenxin", "jev"]
CELL = 256
LABEL = 28
COLS = 5
ROWS = 3


def sheet(prefix: str, out: str) -> None:
    W = COLS * CELL
    H = ROWS * (CELL + LABEL)
    canvas = Image.new("RGB", (W, H), (24, 24, 28))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    for i, b in enumerate(BRANDS):
        p = AV / f"{prefix}{b}.png"
        im = Image.open(p).convert("RGB").resize((CELL, CELL), Image.LANCZOS)
        r, c = divmod(i, COLS)
        x, y = c * CELL, r * (CELL + LABEL)
        canvas.paste(im, (x, y))
        draw.text((x + 6, y + CELL + 4), f"{prefix}{b}", fill=(230, 230, 230), font=font)
    canvas.save(ROOT / out)
    print(f"wrote {out} {W}x{H}")


if __name__ == "__main__":
    sheet("", "docs/screenshots/qc_canon.png")
    sheet("orig_", "docs/screenshots/qc_orig.png")
