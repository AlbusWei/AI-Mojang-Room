"""P6 probe: per-seat tenpai/shanten badges in god-view replay.

Checks (engine-authoritative shanten via riichienv.calculate_shanten):
  1. every reach_accepted frame: declaring seat shanten == 0 (riichi => tenpai)
  2. every hora frame with a win block: winner shanten == -1
  3. shanten values sane (-1..8); None only before the first deal
  4. tenpai badges actually occur in real games; replay stays fast
Usage: python server/probes/p6_badge.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from aimahjong.gameio import resolve_game_dir  # noqa: E402
from aimahjong.replay import replay_mjai  # noqa: E402
import json  # noqa: E402


def load(gid):
    d = Path(gid) if Path(gid).exists() else resolve_game_dir(gid)
    events = [json.loads(l) for l in (d / "game.mjai.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    dec = []
    p = d / "decisions.jsonl"
    if p.exists():
        dec = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return replay_mjai(events, dec)


def main():
    ok = True
    for gid in (str(ROOT / "server" / "probes" / "fixtures" / "p1_real_full"), "live2026_1"):
        t0 = time.time()
        frames = load(gid)
        dt = time.time() - t0
        reach_bad, hora_bad, range_bad = [], [], []
        tenpai_frames, win_frames = 0, 0
        for fr in frames:
            t = fr.event.get("type")
            for s in range(4):
                sh = fr.seats[s]["shanten"]
                if sh is None:
                    if t not in ("start_game",):
                        range_bad.append((fr.index, s, "None"))
                elif not (-1 <= sh <= 8):
                    range_bad.append((fr.index, s, sh))
            if t == "reach_accepted":
                a = fr.event["actor"]
                if fr.seats[a]["shanten"] != 0:
                    reach_bad.append((fr.index, a, fr.seats[a]["shanten"]))
            if t == "hora" and fr.win:
                w = fr.win["seat"]
                if fr.seats[w]["shanten"] != -1:
                    hora_bad.append((fr.index, w, fr.seats[w]["shanten"]))
            if any(fr.seats[s]["shanten"] == 0 for s in range(4)):
                tenpai_frames += 1
            if any(fr.seats[s]["shanten"] == -1 for s in range(4)):
                win_frames += 1
        good = not (reach_bad or hora_bad or range_bad) and tenpai_frames > 0
        ok &= good
        print(f"[{gid}] frames={len(frames)} replay={dt:.2f}s tenpai_frames={tenpai_frames} win_frames={win_frames}")
        print(f"  reach_accepted tenpai violations={reach_bad[:5]} hora winner violations={hora_bad[:5]} range violations={range_bad[:5]}")
        print(f"  => {'PASS' if good else 'FAIL'}")
        if gid.endswith("r3"):
            # pick a showcase frame: >=1 tenpai (non-riichi) or riichi + others shanten
            cands = [fr.index for fr in frames
                     if 300 <= fr.index <= 364
                     and sum(1 for s in range(4) if fr.seats[s]["shanten"] == 0) >= 1]
            print("  showcase candidate frames (300-364 with tenpai):", cands[:12])
            for idx in (cands[-1:] or [360]):
                fr = frames[idx]
                print(f"  frame {idx} badges:", [(s, fr.seats[s]["shanten"], fr.seats[s]["riichi"]) for s in range(4)])
    print("P6 BADGE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
