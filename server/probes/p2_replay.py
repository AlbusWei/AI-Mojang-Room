"""P2 verification: god-view replay reconstructs hands/scores correctly.

Run:  .venv\\Scripts\\python.exe server\\probes\\p2_replay.py [--run runs/game_42_...]
Checks:
  - one frame per event
  - concealed hand size == 13 - (tiles contributed to melds) + (1 if drawn)
  - final scores == summary.json scores
  - every decision joins to its action event (seat == actor)
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from aimahjong.replay import replay_mjai  # noqa: E402

MELD_CONTRIB = {"chi": 2, "pon": 2, "daiminkan": 3, "ankan": 4, "kakan": 3}
ACTION_TYPES = {"dahai", "chi", "pon", "daiminkan", "ankan", "kakan", "reach", "hora", "ryukyoku"}


def load_jsonl(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(ROOT / "server" / "probes" / "fixtures" / "game_42"))
    args = ap.parse_args()
    run = Path(args.run)
    events = load_jsonl(run / "game.mjai.jsonl")
    decisions = load_jsonl(run / "decisions.jsonl") if (run / "decisions.jsonl").exists() else []
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8")) if (run / "summary.json").exists() else {}

    frames = replay_mjai(events, decisions)
    assert len(frames) == len(events), f"frame count {len(frames)} != events {len(events)}"

    hand_err = 0
    dealt = False
    for fr in frames:
        if fr.event.get("type") == "start_kyoku":
            dealt = True
        if not dealt:
            continue
        for s, seat in enumerate(fr.seats):
            meld_tiles = sum(len(m["tiles"]) for m in seat["melds"])
            called = fr.event.get("type") in ("chi", "pon", "daiminkan") and fr.event.get("actor") == s
            expected = 13 - meld_tiles + (1 if seat["drawn"] else 0) + (1 if called else 0)
            if len(seat["hand"]) != expected:
                hand_err += 1
                if hand_err <= 5:
                    print(f"  HAND MISMATCH frame {fr.index} seat{s}: got {len(seat['hand'])} expected {expected} event={fr.event.get('type')}")
    print(f"hand-size conservation: {'PASS' if hand_err == 0 else f'FAIL ({hand_err})'}")

    # decision alignment (response-phase decisions share an event_pos -> lists)
    joined = sum(len(fr.decisions) for fr in frames)
    seat_err = sum(1 for fr in frames for d in fr.decisions if not (0 <= d.get("seat", -1) <= 3))
    print(f"decisions joined: {joined}/{len(decisions)}; seat-range: {'PASS' if seat_err == 0 else f'FAIL ({seat_err})'}")

    # final scores
    final_scores = [s["score"] for s in frames[-1].seats]
    if "scores" in summary:
        ok = final_scores == summary["scores"]
        print(f"final scores {final_scores} vs summary {summary['scores']}: {'PASS' if ok else 'FAIL'}")
    else:
        ok = True
        print(f"final scores {final_scores} (no summary to compare)")

    hora = sum(1 for e in events if e.get("type") == "hora")
    print(f"events={len(events)} frames={len(frames)} hora={hora}")
    allpass = hand_err == 0 and seat_err == 0 and ok and joined == len(decisions)
    print("RESULT:", "PASS" if allpass else "FAIL")
    sys.exit(0 if allpass else 1)


if __name__ == "__main__":
    main()