"""Start a REAL-TIME live game on the running viewer server (P7).

Usage:
  .venv\\Scripts\\python.exe scripts\\start_live.py --config config/agents.real.json --seed 7
Then open the printed URL (/?live=<id>) in a browser / OBS Browser Source.
The game runs inside the viewer server process; frames stream in as agents act.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/agents.real.json")
    ap.add_argument("--env", default=".env")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--game-id", default=None)
    ap.add_argument("--base", default="http://127.0.0.1:18765")
    args = ap.parse_args()
    body = json.dumps({"config": args.config, "env": args.env, "seed": args.seed,
                       "game_id": args.game_id}).encode("utf-8")
    req = urllib.request.Request(args.base + "/api/live/start", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.loads(r.read().decode("utf-8"))
    if "error" in j:
        print("ERROR:", j["error"])
        return 1
    print("live game:", j["game_id"])
    print("agents:", ", ".join(j["agents"]))
    print("watch:", args.base + j["url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
