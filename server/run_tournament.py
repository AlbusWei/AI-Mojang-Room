"""CLI: run a small seat-rotated tournament and emit a leaderboard.

Usage:
  python server/run_tournament.py --config config/tournament.random.json
  python server/run_tournament.py --config config/tournament.real.json --rounds 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aimahjong.config import load_env, load_config
from aimahjong.tournament import Tournament


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "tournament.random.json"))
    ap.add_argument("--env", default=str(ROOT / ".env"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--rounds", type=int, default=None, help="override num_rounds (seeds)")
    ap.add_argument("--rotations", type=int, default=None)
    ap.add_argument("--seed-start", type=int, default=None)
    ap.add_argument("--verbose", action="store_true", help="per-kyoku game logging")
    args = ap.parse_args()

    env = load_env(args.env)
    cfg = load_config(args.config)
    if args.name:
        cfg["name"] = args.name
    if args.rounds is not None:
        cfg["num_rounds"] = args.rounds
        cfg.pop("seeds", None)
    if args.seed_start is not None:
        cfg["seed_start"] = args.seed_start
    if args.rotations is not None:
        cfg["rotations"] = args.rotations
    if args.verbose:
        cfg["verbose"] = True

    tourney = Tournament(cfg, env, out_dir=args.out,
                         progress=lambda m: print(m, flush=True))
    result = tourney.run()

    print("\n=== LEADERBOARD ===")
    for e in result["leaderboard"]:
        rc = "/".join(str(c) for c in e["rank_counts"])
        print(f"  #{e['rank']} {e['name']:<16} pts={e['points']:<6} "
              f"wins={e['wins']}/{e['games']} ({e['win_rate']:.0%}) "
              f"avg_rank={e['avg_rank']} dist={rc} avg_score={e['avg_score']}")
    print("\nleaderboard.md:", tourney.out_dir / "leaderboard.md")
    print("tournament.json:", tourney.out_dir / "tournament.json")


if __name__ == "__main__":
    main()