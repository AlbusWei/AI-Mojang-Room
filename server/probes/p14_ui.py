"""P14 probe: human "new game" interaction end-to-end on an ISOLATED temp server.

Spawns its own serve_viewer on :18799 (so the production server / runs/ list is
untouched), opens the viewer, uses the 🎮新开一局 modal to start a MOCK live game,
asserts the live view follows it, then cleans up the temp game dir + server.

Self-contained and roster-size agnostic: seeds its own mock-a..d roster players
(only those not already present) so the agents.mock.json preset can fill all 4
seats regardless of how many real players the roster holds. Seeded players are
deleted in finally (net-zero).
"""
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 18799
BASE = f"http://127.0.0.1:{PORT}"
GID = "p14_ui_test"
MOCK_IDS = ["mock-a", "mock-b", "mock-c", "mock-d"]
MOCK_DISPLAY = {"mock-a": "Mock-A", "mock-b": "Mock-B",
                "mock-c": "Mock-C", "mock-d": "Mock-D"}


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.load(resp)


def wait_server(timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(BASE + "/api/configs", timeout=3) as r:
                json.load(r)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    proc = subprocess.Popen([str(PY), str(ROOT / "server" / "serve_viewer.py"),
                             "--host", "127.0.0.1", "--port", str(PORT)],
                            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok = True
    created_mocks = []
    try:
        if not wait_server():
            print("FAIL: temp server did not start"); return 1
        # Self-seed mock roster players so the agents.mock.json preset fills all
        # 4 seats (roster-size agnostic; net-zero cleanup in finally).
        have = {p.get("id") for p in req("GET", "/api/roster")["players"]}
        for mid in MOCK_IDS:
            if mid not in have:
                req("POST", "/api/roster", {"id": mid, "display": MOCK_DISPLAY[mid],
                                            "type": "mock", "enabled": True})
                created_mocks.append(mid)
        errors = []
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True,
                                  args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
            pg = b.new_page(viewport={"width": 1920, "height": 1080})
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(BASE + "/")
            pg.wait_for_function("window.__VIEWER_READY__ === true", timeout=20000)
            # open modal
            pg.click("#newGameBtn")
            pg.wait_for_selector("#newGameModal:not(.hidden)", timeout=5000)
            nopt = pg.eval_on_selector_all("#ngConfig option", "els => els.length")
            if nopt < 1:
                print("FAIL: no configs in picker"); ok = False
            # choose mock lineup + fixed id, start
            pg.select_option("#ngConfig", "config/agents.mock.json")
            pg.wait_for_timeout(300)  # preset fill is async (roster fetch)
            # P15: modal now uses 4 per-seat selects (preset fills them)
            seats = pg.eval_on_selector_all("#ngSeats select", "els => els.length")
            filled = pg.eval_on_selector_all("#ngSeats select", "els => els.filter(e => e.value).length")
            if seats != 4 or filled != 4:
                print("FAIL: per-seat selects", seats, "filled", filled); ok = False
            pg.fill("#ngId", GID)
            pg.click("#ngStart")
            # modal closes and live view follows the new game
            pg.wait_for_selector("#newGameModal", state="hidden", timeout=10000)
            # viewer switches to the new live game
            pg.wait_for_function(f"document.querySelector('#gameSel').value === '{GID}'", timeout=15000)
            pg.wait_for_function("window.__VIEWER_TOTAL__ > 0", timeout=20000)
            badge = pg.text_content("#liveText")
            if "LIVE" not in badge and "结束" not in badge:
                print("FAIL: live badge not shown", badge); ok = False
            pg.wait_for_timeout(1200)  # let the first live poll of the NEW game land
            n0 = pg.evaluate("window.__VIEWER_TOTAL__")
            pg.wait_for_timeout(1500)
            n1 = pg.evaluate("window.__VIEWER_TOTAL__")
            with urllib.request.urlopen(BASE + "/api/live/list", timeout=5) as r:
                live = json.load(r).get("games", [])
            status = next((g.get("status") for g in live if g.get("game_id") == GID), None)
            # mock games finish fast: growth OR completed both prove streaming worked
            if not (n1 > n0 or status == "done"):
                print("FAIL: live frames did not grow and not done", n0, n1, status); ok = False
            b.close()
        real_errors = [e for e in errors if "favicon" not in e.lower()]
        if real_errors:
            print("JS errors:", real_errors[:5]); ok = False
        print(f"configs={nopt} seats={seats} filled={filled} badge={badge!r} frames {n0}->{n1} js_errors={len(real_errors)}")
    finally:
        for mid in created_mocks:
            try:
                req("DELETE", f"/api/roster/{mid}")
            except Exception:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        d = ROOT / "runs" / GID
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    print("P14 UI NEW-GAME:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
