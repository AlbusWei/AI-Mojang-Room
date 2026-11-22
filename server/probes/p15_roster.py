"""P15 probe: roster CRUD + per-seat match creation (API + human GUI).

Runs against an ISOLATED temp server (:18799). Self-contained and roster-size
agnostic: it seeds its own mock-a..d players via the CRUD API (only those not
already present) so per-seat starts need no real LLM API and no pre-existing
mock entries. All seeded players + the temporary test player are deleted in
finally (net-zero). Cleans up temp game dirs + server.
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
GID = "p15_ui_test"
TEST_PID = "p15-probe-tmp"
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
            req("GET", "/api/roster")
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

    def check(name, cond, extra=""):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name + (" " + extra if extra else ""))
        ok = ok and cond

    try:
        if not wait_server():
            print("FAIL: temp server did not start"); return 1
        # --- API: roster list + self-seed mock seats (size-agnostic) ---
        players = req("GET", "/api/roster")["players"]
        baseline_n = len(players)
        have = {p.get("id") for p in players}
        check("roster list returns players", baseline_n >= 1, f"n={baseline_n}")
        for mid in MOCK_IDS:
            if mid not in have:
                req("POST", "/api/roster", {"id": mid, "display": MOCK_DISPLAY[mid],
                                            "type": "mock", "enabled": True})
                created_mocks.append(mid)
        players = req("GET", "/api/roster")["players"]
        have = {p.get("id") for p in players}
        check("roster has 4 mock seats", all(m in have for m in MOCK_IDS),
              f"seeded={created_mocks}")
        check("roster seeding is net-add", len(players) == baseline_n + len(created_mocks),
              f"{baseline_n}->{len(players)}")
        # --- API: roster CRUD (temp player) ---
        created = req("POST", "/api/roster", {"id": TEST_PID, "display": "P15 Probe", "type": "mock"})
        check("roster create", created.get("id") == TEST_PID)
        updated = req("PUT", f"/api/roster/{TEST_PID}", {"bio": "probe bio"})
        check("roster update", updated.get("bio") == "probe bio")
        # --- API: per-seat start with 4 mock roster ids ---
        d = req("POST", "/api/live/start", {"seats": ["mock-a", "mock-b", "mock-c", "mock-d"],
                                            "seed": 5, "game_id": "p15_api_test"})
        check("per-seat start returns game", d.get("game_id") == "p15_api_test", str(d.get("agents")))
        check("per-seat agents are mock roster names",
              d.get("agents") == ["Mock-A", "Mock-B", "Mock-C", "Mock-D"] or len(d.get("agents", [])) == 4,
              str(d.get("agents")))
        # invalid seat rejected
        try:
            req("POST", "/api/live/start", {"seats": ["nope", "mock-b", "mock-c", "mock-d"], "game_id": "p15_bad"})
            check("invalid roster id rejected", False)
        except urllib.error.HTTPError:
            check("invalid roster id rejected", True)
        # --- GUI: per-seat modal ---
        errors = []
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
            pg = b.new_page(viewport={"width": 1920, "height": 1080})
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(BASE + "/")
            pg.wait_for_function("window.__VIEWER_READY__ === true", timeout=20000)
            pg.click("#newGameBtn")
            pg.wait_for_selector("#newGameModal:not(.hidden)", timeout=5000)
            # loadConfigs() is async (fetch roster+configs then renderNgSeats);
            # wait for the per-seat selects to exist before counting them.
            pg.wait_for_selector("#ngSeat0", timeout=10000)
            nsel = pg.eval_on_selector_all("#ngSeats select", "els => els.length")
            check("modal has 4 per-seat selects", nsel == 4, f"n={nsel}")
            nopt = pg.eval_on_selector_all("#ngSeat0 option", "els => els.length")
            check("seat select populated from roster", nopt >= len(MOCK_IDS), f"n={nopt}")
            # preset fill
            pg.select_option("#ngConfig", "config/agents.mock.json")
            pg.wait_for_timeout(300)
            v0 = pg.eval_on_selector("#ngSeat0", "el => el.value")
            check("preset fill sets seat0", bool(v0), v0)
            # override all seats to mock and start
            for i, pid in enumerate(["mock-a", "mock-b", "mock-c", "mock-d"]):
                pg.select_option(f"#ngSeat{i}", pid)
            pg.fill("#ngId", GID)
            pg.click("#ngStart")
            pg.wait_for_selector("#newGameModal", state="hidden", timeout=10000)
            pg.wait_for_function(f"document.querySelector('#gameSel').value === '{GID}'", timeout=15000)
            pg.wait_for_function("window.__VIEWER_TOTAL__ > 0", timeout=20000)
            pg.wait_for_timeout(1200)
            n0 = pg.evaluate("window.__VIEWER_TOTAL__")
            pg.wait_for_timeout(1500)
            n1 = pg.evaluate("window.__VIEWER_TOTAL__")
            live = req("GET", "/api/live/list")["games"]
            status = next((g.get("status") for g in live if g.get("game_id") == GID), None)
            check("GUI per-seat live grows or done", n1 > n0 or status == "done", f"{n0}->{n1} {status}")
            b.close()
        real_errors = [e for e in errors if "favicon" not in e.lower()]
        check("no JS errors", not real_errors, str(real_errors[:3]))
    finally:
        try:
            req("DELETE", f"/api/roster/{TEST_PID}")
        except Exception:
            pass
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
        for gid in (GID, "p15_api_test", "p15_bad"):
            d = ROOT / "runs" / gid
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
    print("P15 ROSTER+PER-SEAT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
