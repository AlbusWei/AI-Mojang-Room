"""P10 regression: aggregate standings include latest official game & exclude
random; profiles expose the 15-brand AI-musume library; replay exposes furiten +
call-window + melds.
Run: .venv\\Scripts\\python.exe server\\probes\\p10_check.py
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
BASE = "http://127.0.0.1:18765"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def main():
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name + (" " + extra if extra else ""))
        ok = ok and cond

    st = get("/api/standings")
    names = [s["name"] for s in st["standings"]]
    check("standings includes 2026 lineup", "Qwen3.8-max" in names and "GLM-5.3" in names, str(names))
    check("standings excludes random/mock", not any(n.startswith(("Random", "Mock")) for n in names))
    check("standings num_games>=1", st["num_games"] >= 1, f"num_games={st['num_games']}")

    pr = get("/api/profiles")["players"]
    brands = {v["brand"] for v in pr.values()}
    expected = {"qwen", "deepseek", "glm", "kimi", "gpt", "claude", "gemini", "grok",
                "seed", "minimax", "llama", "mistral", "perplexity", "wenxin", "jev"}
    check("profiles core 4 brands present", {"qwen", "deepseek", "glm", "kimi"} <= brands, str(brands))
    check("profiles 15-brand library", brands == expected, str(sorted(brands)))
    check("profiles avatars exist", all((ROOT / "web" / v["avatar"]).exists() for v in pr.values()))
    check("profiles commercial fallbacks exist",
          all((ROOT / "web" / v["commercial_fallback"]).exists() for v in pr.values() if v.get("commercial_fallback")))

    games = get("/api/games")["games"]
    ids = [g["id"] for g in games]
    check("live2026_1 listed", "live2026_1" in ids, str(ids))
    check("no archived test games listed", not any(i.startswith(("p3_test", "p9_live_comm", "p7_")) for i in ids))

    fr = get("/api/game/live2026_1/frames")["frames"]
    furiten_frames = [f["index"] for f in fr if any(s.get("furiten") for s in f["seats"])]
    check("furiten surfaced", len(furiten_frames) > 0, f"count={len(furiten_frames)}")
    call_frames = []
    for i, f in enumerate(fr[:-1]):
        if f["event"].get("type") == "dahai" and fr[i + 1]["event"].get("type") in ("chi", "pon", "daiminkan", "ron"):
            call_frames.append(i)
    check("call windows detectable", len(call_frames) > 0, f"count={len(call_frames)} first={call_frames[:3]}")
    meld_frames = [f["index"] for f in fr if any(s["melds"] for s in f["seats"])]
    check("melds present (separate tray)", len(meld_frames) > 0, f"count={len(meld_frames)}")
    waits_frames = [f["index"] for f in fr if any(s.get("waits") for s in f["seats"])]
    check("reliable waits surfaced", len(waits_frames) > 0, f"count={len(waits_frames)}")

    print("P10_CHECK", "PASS" if ok else "FAIL")
    print("screenshot_frames", json.dumps({"call": call_frames[:1], "meld": meld_frames[:1], "furiten": furiten_frames[:1]}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
