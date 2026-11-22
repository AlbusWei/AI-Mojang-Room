"""Generate commentary assets (text + SRT + optional edge-tts MP3) for a game.

Usage:
  .venv\\Scripts\\python.exe scripts\\make_commentary.py --game runs/p1_real_full --tts

Outputs into <game>/commentary/:
  commentary.json   lines keyed by event_pos (with audio filenames when --tts)
  commentary.srt    rough subtitles for editing
  line_000.mp3 ...  per-line narration (when --tts)

Facts-first: text is built only from engine events + the agents' recorded reasons.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from aimahjong.commentary import generate_commentary, to_srt  # noqa: E402
from aimahjong.gameio import resolve_game_dir  # noqa: E402

NARRATOR = "zh-CN-YunxiNeural"
SEAT_VOICES = ["zh-CN-XiaoxiaoNeural", "zh-CN-YunyangNeural",
               "zh-CN-XiaoyiNeural", "zh-CN-YunjianNeural"]


def load_game(game_dir: Path):
    events = [json.loads(l) for l in (game_dir / "game.mjai.jsonl").read_text("utf-8").splitlines() if l.strip()]
    decisions = []
    dp = game_dir / "decisions.jsonl"
    if dp.exists():
        decisions = [json.loads(l) for l in dp.read_text("utf-8").splitlines() if l.strip()]
    agents = None
    sp = game_dir / "summary.json"
    if sp.exists():
        agents = json.loads(sp.read_text("utf-8")).get("agents")
    return events, decisions, agents


async def synth(lines, out_dir: Path, concurrency: int = 4):
    import edge_tts
    sem = asyncio.Semaphore(concurrency)

    async def one(i, ln):
        voice = NARRATOR if ln.seat is None else SEAT_VOICES[ln.seat % len(SEAT_VOICES)]
        fname = f"line_{i:03d}.mp3"
        async with sem:
            try:
                await edge_tts.Communicate(ln.text, voice).save(str(out_dir / fname))
                ln.audio = fname
                return True
            except Exception as e:  # network/voice failure -> keep text, skip audio
                print(f"  [tts skip {i}] {e}")
                return False

    results = await asyncio.gather(*(one(i, ln) for i, ln in enumerate(lines)))
    return sum(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="runs/p1_real_full", help="game dir (contains game.mjai.jsonl)")
    ap.add_argument("--tts", action="store_true", help="synthesize MP3 via edge-tts")
    ap.add_argument("--max-highlights", type=int, default=6)
    args = ap.parse_args()

    try:
        game_dir = resolve_game_dir(args.game)
    except FileNotFoundError as e:
        print(f"ERROR: {e}"); sys.exit(1)

    events, decisions, agents = load_game(game_dir)
    lines = generate_commentary(events, decisions, agents, max_highlights=args.max_highlights)
    out_dir = game_dir / "commentary"
    out_dir.mkdir(exist_ok=True)

    n_audio = 0
    if args.tts:
        n_audio = asyncio.run(synth(lines, out_dir))

    (out_dir / "commentary.json").write_text(
        json.dumps([ln.to_dict() for ln in lines], ensure_ascii=False, indent=2), "utf-8")
    (out_dir / "commentary.srt").write_text(to_srt(lines), "utf-8")

    kinds = {}
    for ln in lines:
        kinds[ln.kind] = kinds.get(ln.kind, 0) + 1
    print(f"game: {game_dir.name}")
    print(f"commentary lines: {len(lines)}  {kinds}")
    print(f"audio mp3: {n_audio}/{len(lines)}" + ("" if args.tts else "  (use --tts to synthesize)"))
    print(f"out: {out_dir}")
    for ln in lines[:6]:
        print(f"  [{ln.kind}@{ln.event_pos}] {ln.text}")


if __name__ == "__main__":
    main()