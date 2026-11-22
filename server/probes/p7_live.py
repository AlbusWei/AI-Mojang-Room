"""P7 probe: real-time live pipeline (in-process LiveManager, mock agents).

Checks:
  1. frames grow monotonically while the game runs (incremental streaming)
  2. decisions stream too and join into frames (reasoning visible live)
  3. final live frames == offline replay of the written log (same source of truth)
  4. status transitions running -> done; summary scores match the log replay
Usage: python server/probes/p7_live.py
"""
import json
import sys
import time
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from aimahjong.live import LiveManager  # noqa: E402
from aimahjong.replay import replay_mjai  # noqa: E402


def main():
    mgr = LiveManager(Path(tempfile.mkdtemp(prefix="p7_live_")))
    game = mgr.start(ROOT / "config" / "agents.mock.json", ROOT / ".env",
                     seed=7, game_id="p7_live_test")
    seen = 0
    growth = []
    t0 = time.time()
    while game.status == "running" and time.time() - t0 < 120:
        frames, n, status, summary, err = game.frames_since(seen)
        if n > seen:
            growth.append(n)
            seen = n
        time.sleep(0.05)
    frames, n, status, summary, err = game.frames_since(0)
    ok = True
    checks = {
        "status done": status == "done",
        "no error": err is None,
        "frames grew incrementally": len(growth) >= 2,
        "decisions streamed": len(game.decisions) > 0,
        "decisions joined in frames": sum(len(f["decisions"]) for f in frames) == len(game.decisions),
        "summary present": summary is not None,
    }
    d = game.out_dir
    events = [json.loads(l) for l in (d / "game.mjai.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    dec = [json.loads(l) for l in (d / "decisions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    offline = replay_mjai(events, dec)
    checks["live frames == offline replay"] = len(frames) == len(offline)
    checks["final scores match"] = [f["seats"][s]["score"] for s in range(4) for f in [frames[-1]]] == summary["scores"]
    for k, v in checks.items():
        ok &= v
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"  growth samples={growth[:6]}... total={n} decisions={len(game.decisions)} elapsed={time.time()-t0:.1f}s")
    print("P7 LIVE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
