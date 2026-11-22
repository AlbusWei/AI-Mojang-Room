"""P9 acceptance + rule audit for a finished game (default runs/live2026_1).

Checks: fallback reasons, score conservation, ryukyoku tenpai/noten payments,
riichi-stick (kyotaku) conservation, kan->dora indicator count, ura-dora presence
on riichi wins, and whether displayed win han/fu reconciles with engine deltas.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from aimahjong.replay import replay_mjai  # noqa: E402


def load(gdir):
    events = [json.loads(l) for l in (gdir / "game.mjai.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    decs = [json.loads(l) for l in (gdir / "decisions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    summary = json.loads((gdir / "summary.json").read_text(encoding="utf-8"))
    return events, decs, summary


def main():
    gdir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "runs" / "live2026_1"
    events, decs, summary = load(gdir)
    print("game:", summary["game_id"], "kyoku:", summary["num_kyoku"],
          "hora:", summary["hora_count"], "ryukyoku:", summary["ryukyoku_count"],
          "fallback:", summary["fallback_count"])
    print("scores:", summary["scores"], "sum:", sum(summary["scores"]))

    print("\n--- fallbacks ---")
    fb = [d for d in decs if d.get("fallback")]
    by_seat = Counter(d["name"] for d in fb)
    by_err = Counter((d.get("error") or "?")[:60] for d in fb)
    print("by seat:", dict(by_seat))
    for e, c in by_err.items():
        print(f"  [{c}] {e}")
    for d in fb[:12]:
        print(f"  step{d['step']} seat{d['seat']} {d['name']} lat={d.get('latency_ms')} label={d.get('label')} err={(d.get('error') or '')[:80]}")

    print("\n--- ryukyoku payments ---")
    for i, e in enumerate(events):
        if e.get("type") == "ryukyoku":
            d = e.get("deltas", [0, 0, 0, 0])
            print(f"  pos{i} reason={e.get('reason')} deltas={d} sum={sum(d)}")

    print("\n--- riichi / kyotaku ---")
    kyotaku = 0
    reach = 0
    for i, e in enumerate(events):
        t = e.get("type")
        if t == "start_kyoku":
            kyotaku = e.get("kyotaku", 0)
        elif t == "reach_accepted":
            reach += 1
            kyotaku += 1
        elif t == "hora":
            print(f"  pos{i} hora actor={e['actor']} deltas={e.get('deltas')} kyotaku_before={kyotaku} ura={e.get('ura_markers')}")
            kyotaku = 0
        elif t == "end_game":
            print(f"  end_game leftover kyotaku={kyotaku}")
    print("reach_accepted count:", reach)

    print("\n--- kan / dora ---")
    kans = Counter(e["type"] for e in events if e.get("type") in ("ankan", "kakan", "daiminkan"))
    doras = [i for i, e in enumerate(events) if e.get("type") == "dora"]
    print("kans:", dict(kans), "dora events:", len(doras))

    print("\n--- displayed win reconciliation ---")
    frames = replay_mjai(events, decs)
    for f in frames:
        if f.event.get("type") == "hora" and f.win:
            w = f.win
            print(f"  pos{f.index} seat{w.get('seat')} han={w.get('han')} fu={w.get('fu')} yaku={w.get('yaku')} source={w.get('source')}")
    missing = [f.index for f in frames if f.event.get("type") == "hora" and not f.win]
    print("hora frames WITHOUT displayed win (gated out):", missing)


if __name__ == "__main__":
    main()
