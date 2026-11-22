"""P9 probe: viewer runtime + controls + no JS errors (Playwright, system Chrome).

Opens the redesigned viewer, exercises play/pause/step/scrub/hide-hands/sound/
commentary toggles and the leaderboard page, and asserts no page errors and
that the primary flow (frame advance, hide-hands, leaderboard rows) works.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18765"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def main():
    errors = []
    ok = True
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True,
                              args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(BASE + "/?game=live2026_1&frame=100")
        pg.wait_for_function("window.__VIEWER_READY__ === true", timeout=20000)
        c0 = pg.text_content("#counter")
        pg.click("#nextBtn")
        c1 = pg.text_content("#counter")
        if c1 == c0:
            print("FAIL: next did not advance", c0, c1); ok = False
        pg.select_option("#speed", "300")
        pg.click("#playBtn")
        pg.wait_for_timeout(1600)
        c2 = pg.text_content("#counter")
        pg.click("#playBtn")  # pause
        if c2 == c1:
            print("FAIL: play did not advance", c1, c2); ok = False
        # hide hands -> face-down teal back
        pg.click("#hideHands")
        down = pg.eval_on_selector("#hand0 svg", "el => Array.from(el.querySelectorAll('rect')).some(r => r.getAttribute('fill') === '#0e6b5c')")
        if not down:
            print("FAIL: hide-hands not face-down"); ok = False
        pg.click("#hideHands")
        down2 = pg.eval_on_selector("#hand0 svg", "el => Array.from(el.querySelectorAll('rect')).some(r => r.getAttribute('fill') === '#0e6b5c')")
        if down2:
            print("FAIL: un-hide still face-down"); ok = False
        # P12: per-seat rotation (Majsoul orientation) + corner avatars
        rot = pg.evaluate("""() => {
            const m = id => new DOMMatrix(getComputedStyle(document.getElementById(id)).transform);
            return {h0: m('hand0').a, h1: m('hand1').a, h2: m('hand2').a, h3: m('hand3').a};
        }""")
        if not (abs(rot['h0'] - 1) < 0.01 and abs(rot['h1']) < 0.01
                and abs(rot['h2'] + 1) < 0.01 and abs(rot['h3']) < 0.01):
            print("FAIL: per-seat rotation wrong", rot); ok = False
        av = pg.eval_on_selector_all("#id0 img, #id1 img, #id2 img, #id3 img", "els => els.length")
        if av < 4:
            print("FAIL: corner avatars missing", av); ok = False
        # toggles should not throw
        pg.click("#soundToggle"); pg.click("#commToggle"); pg.click("#commToggle"); pg.click("#soundToggle")
        # scrub
        pg.eval_on_selector("#scrub", "el => { el.value = 300; el.dispatchEvent(new Event('input')); }")
        c3 = pg.text_content("#counter")
        if not c3.startswith("301"):
            print("FAIL: scrub did not jump, counter=", c3); ok = False
        # leaderboard
        pg.goto(BASE + "/leaderboard.html")
        pg.wait_for_timeout(1500)
        lb = pg.eval_on_selector_all("#lbBody tr", "els => els.length")
        gb = pg.eval_on_selector_all("#gamesBody tr", "els => els.length")
        if lb < 1 or gb < 1:
            print("FAIL: leaderboard rows", lb, gb); ok = False
        b.close()
    real_errors = [e for e in errors if "favicon" not in e.lower()]
    if real_errors:
        print("JS errors:", real_errors[:5]); ok = False
    print(f"counter {c0} -> {c1} -> {c2}; scrub={c3}; lb_rows={lb} games_rows={gb}; js_errors={len(real_errors)}")
    print("P9 UI RUNTIME:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
