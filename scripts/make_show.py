"""One-command show production for a finished tournament.

Picks the most exciting game (most wins, then highest top score), generates its
commentary (edge-tts) + recap, optionally records a highlight clip around the
first win, and prints the leaderboard + viewer links.

Usage:
  .venv\\Scripts\\python.exe scripts\\make_show.py --tournament runs/show
  .venv\\Scripts\\python.exe scripts\\make_show.py --tournament runs/show --record
  .venv\\Scripts\\python.exe scripts\\make_show.py --tournament runs/show --game <id>   # force a game

Requires the viewer server running for --record (serve_viewer.py, port 18765).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
sys.path.insert(0, str(ROOT / "server"))


def run(script: str, *args: str) -> int:
    cmd = [PY, str(ROOT / "scripts" / script), *args]
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(ROOT))


def first_hora_frame(game_dir: Path) -> int:
    from aimahjong.replay import replay_mjai
    ev = [json.loads(l) for l in (game_dir / "game.mjai.jsonl").read_text("utf-8").splitlines() if l.strip()]
    for i, e in enumerate(ev):
        if e.get("type") == "hora":
            return max(0, i - 25)  # lead-up to the win
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tournament", required=True, help="tournament dir (contains tournament.json)")
    ap.add_argument("--game", default=None, help="force a specific game id (else auto-pick highlight)")
    ap.add_argument("--record", action="store_true", help="also record a highlight clip (needs viewer server)")
    ap.add_argument("--no-tts", action="store_true")
    ap.add_argument("--base", default="http://127.0.0.1:18765")
    args = ap.parse_args()

    tdir = Path(args.tournament)
    if not tdir.is_absolute():
        tdir = (ROOT / tdir).resolve()
    t = json.loads((tdir / "tournament.json").read_text("utf-8"))
    games = t["games"]

    if args.game:
        g = next((x for x in games if x["game_id"] == args.game), None)
        if not g:
            print(f"game {args.game} not in tournament"); sys.exit(1)
    else:
        g = sorted(games, key=lambda x: (x.get("hora_count", 0), max(x["scores"])), reverse=True)[0]

    gid = g["game_id"]
    gdir = Path(g["out_dir"])
    print(f"=== tournament: {t['name']} ({t['num_games']} games) ===")
    print(f"highlight game: {gid}  hora={g.get('hora_count')}  scores={g['scores']}  seats={g['seats']}")

    # commentary + recap for the highlight game
    tts = [] if args.no_tts else ["--tts"]
    run("make_commentary.py", "--game", gid, *tts)
    run("make_recap.py", "--game", gid)

    if args.record:
        frame = first_hora_frame(gdir)
        run("record_game.py", "--game", gid, "--frame", str(frame),
            "--pace", "1800", "--max-seconds", "80", "--base", args.base)
        # mux synced narration into the freshly recorded clip (full ffmpeg)
        rec_dir = ROOT / "runs" / "recordings"
        clips = sorted(rec_dir.glob(f"{gid}_*.webm"), key=lambda p: p.stat().st_mtime)
        if clips:
            clip = clips[-1]
            run("mux_commentary.py", "--game", gid, "--video", str(clip),
                "--start-frame", str(frame), "--pace", "1800",
                "--out", str(clip.with_name(clip.stem + "_audio.mp4")))

    # leaderboard
    print("\n=== 积分榜 ===")
    print(f"{'#':<3}{'选手':<16}{'积分':<8}{'一位':<6}{'胜率':<8}{'均顺位':<8}{'累计点差':<10}")
    for s in t.get("leaderboard", []):
        wr = f"{s['win_rate']*100:.0f}%"
        print(f"{s['rank']:<3}{s['name']:<16}{s['points']:<8.0f}{s['wins']:<6}"
              f"{wr:<8}{s['avg_rank']:<8.2f}{s['score_delta']:<+10d}")

    print("\n=== 链接 ===")
    print(f"积分榜页: {args.base}/leaderboard.html")
    print(f"高光回放: {args.base}/?game={gid}&autoplay=1&pace=2500")
    print(f"复盘文件: {gdir / 'recap.md'}")
    print(f"解说目录: {gdir / 'commentary'}")


if __name__ == "__main__":
    main()
