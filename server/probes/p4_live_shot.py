"""P4 probe: capture the autoplay (live) viewer with a commentary subtitle showing.
Proves live mode auto-advances AND the commentary subtitle overlay renders.
Run:  .venv\\Scripts\\python.exe server\\probes\\p4_live_shot.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUT = ROOT / "docs" / "screenshots" / "viewer_autoplay_subtitle.png"
URL = "http://127.0.0.1:18765/?game=live2026_1&autoplay=1&pace=300"

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True,
                          args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1920, "height": 1080})
    pg = ctx.new_page()
    pg.goto(URL, wait_until="domcontentloaded")
    pg.wait_for_function("window.__VIEWER_READY__ === true", timeout=30000)
    # wait until a commentary subtitle is visible (autoplay triggers it)
    pg.wait_for_selector(".subtitle.show", timeout=20000)
    pg.wait_for_timeout(400)
    frame = pg.evaluate("window.__VIEWER_FRAME__")
    sub = pg.evaluate("document.getElementById('subtitle').textContent")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(OUT))
    print(f"autoplay frame={frame}  subtitle='{sub}'")
    print(f"saved {OUT}")
    ctx.close(); b.close()