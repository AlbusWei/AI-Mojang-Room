"""P3 verification: small random tournament -> leaderboard + rotation + replay.

Gates:
  - 8 games (2 seeds x 4 rotations); each agent plays each seat exactly twice.
  - leaderboard points sum == games * sum(placement points).
  - every game: ranks are a permutation of 1..4; scores sum to 100000.
  - duplicate board: same seed across rotations has identical opening deal.
  - every game replayable; replay final scores == recorded scores.
Run:  .venv\\Scripts\\python.exe server\\probes\\p3_tournament.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aimahjong.tournament import Tournament
from aimahjong.replay import replay_mjai


def first_deal(game_dir: Path):
    for line in (game_dir / "game.mjai.jsonl").open(encoding="utf-8"):
        e = json.loads(line)
        if e.get("type") == "start_kyoku":
            return e["tehais"]
    return None


def main():
    out = Path(tempfile.mkdtemp(prefix="p3_tournament_"))
    config = {
        "name": "p3_test",
        "seats": [{"name": f"R{i}", "type": "random", "seed": i + 1} for i in range(4)],
        "seeds": [42, 7], "rotations": 4, "scoring": "placement",
    }
    t = Tournament(config, out_dir=out, progress=lambda m: print(m, flush=True))
    res = t.run()

    failures = []

    def check(cond, msg):
        print(("  PASS " if cond else "  FAIL ") + msg)
        if not cond:
            failures.append(msg)

    print("\n=== checks ===")
    check(res["num_games"] == 8, f"num_games == 8 (got {res['num_games']})")
    for e in res["leaderboard"]:
        check(e["games"] == 8, f"{e['name']} games == 8 (got {e['games']})")
        check(e["seat_counts"] == [2, 2, 2, 2],
              f"{e['name']} seat_counts == [2,2,2,2] (got {e['seat_counts']})")
    total_pts = sum(e["points"] for e in res["leaderboard"])
    check(abs(total_pts - 8 * 10) < 1e-6, f"points sum == 80 (got {total_pts})")
    for g in res["games"]:
        check(sorted(g["ranks"]) == [1, 2, 3, 4], f"{g['game_id']} ranks perm 1..4")
        check(sum(g["scores"]) == 100000, f"{g['game_id']} scores sum 100000")

    # duplicate board: identical opening deal across rotations of seed 42
    deals = [first_deal(out / "games" / f"p3_test_s42_r{r}") for r in range(4)]
    check(all(d == deals[0] for d in deals),
          "duplicate board: seed 42 opening deal identical across 4 rotations")

    # replayable + final scores match
    replay_ok = True
    for g in res["games"]:
        gd = Path(g["out_dir"])
        evs = [json.loads(l) for l in (gd / "game.mjai.jsonl").open(encoding="utf-8")]
        decs = [json.loads(l) for l in (gd / "decisions.jsonl").open(encoding="utf-8")]
        frames = replay_mjai(evs, decs)
        if len(frames) != len(evs):
            replay_ok = False
        final = [frames[-1].seats[s]["score"] for s in range(4)]
        if final != g["scores"]:
            replay_ok = False
            print(f"    {g['game_id']} replay final {final} != {g['scores']}")
    check(replay_ok, "all games replayable; replay final scores == recorded")

    print("\n=== leaderboard ===")
    for e in res["leaderboard"]:
        print(f"  #{e['rank']} {e['name']} pts={e['points']} wins={e['wins']}/{e['games']} "
              f"avg_rank={e['avg_rank']} dist={e['rank_counts']}")
    print("\nleaderboard.md:", out / "leaderboard.md")

    if failures:
        print(f"\nP3 FAIL: {len(failures)} check(s) failed")
        sys.exit(1)
    print("\nP3 PASS: tournament + rotation + duplicate board + leaderboard + replay all verified")


if __name__ == "__main__":
    main()