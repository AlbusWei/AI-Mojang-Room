"""CLI: run one AI mahjong game.

Usage (from anywhere):
  python server/run_game.py --config config/agents.mock.json --seed 42
  python server/run_game.py --config config/agents.example.json --seed 7 --env .env
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # workspace root
sys.path.insert(0, str(Path(__file__).resolve().parent))  # server/ for `import aimahjong`

from aimahjong.config import load_env, load_config, build_agents
from aimahjong.room import Room


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "agents.mock.json"))
    ap.add_argument("--env", default=str(ROOT / ".env"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=None)
    ap.add_argument("--game-mode", default=None)
    ap.add_argument("--rule", default=None)
    ap.add_argument("--max-steps", type=int, default=6000)
    args = ap.parse_args()

    env = load_env(args.env)
    cfg = load_config(args.config)
    agents = build_agents(cfg, env)

    room = Room(
        agents,
        game_mode=args.game_mode or cfg.get("game_mode", "4p-red-half"),
        rule=args.rule or cfg.get("rule", "tenhou"),
        seed=args.seed,
        out_dir=args.out,
        max_steps=args.max_steps,
    )
    print(f"[room] game_id={room.game_id} seed={args.seed} "
          f"agents={[a.name for a in agents]}", flush=True)
    result = room.run()

    print("\n=== RESULT ===")
    print("scores:", result.scores)
    print("ranks :", result.ranks)
    print(f"steps={result.num_steps} events={result.num_events} "
          f"kyoku={result.num_kyoku} hora={result.hora_count} "
          f"ryukyoku={result.ryukyoku_count} fallbacks={result.fallback_count}")
    print(f"total agent latency: {result.total_latency_ms/1000:.1f}s")
    print("out_dir:", room.out_dir)
    # show a few sample reasons
    print("\n=== sample decisions ===")
    for d in result.decisions[:6]:
        print(f"  [{d['seat']} {d['name']}] {d['label']} :: {d['reason'][:80]}")


if __name__ == "__main__":
    main()