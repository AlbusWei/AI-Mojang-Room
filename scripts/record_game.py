"""Unattended game recorder (Playwright + system Chrome, video-only WebM).

Opens the god-view viewer in autoplay mode and records the page to a WebM file.
Audio note: Playwright records VIDEO ONLY. For narration in the final show, either
(a) stream/record through OBS Browser Source (captures the viewer's commentary
audio live), or (b) mux the generated commentary MP3/SRT in post (see
docs/节目制作手册.md). This script is the zero-OBS unattended video path.

Usage:
  .venv\\Scripts\\python.exe scripts\\record_game.py --game p1_real_full --pace 2500
  # quick test clip:
  .venv\\Scripts\\python.exe scripts\\record_game.py --game p1_real_full --pace 200 --max-seconds 12

Requires: pip install playwright ; python -m playwright install ffmpeg
Uses the installed Google Chrome (no extra browser download).
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True, help="game id (as listed by /api/games)")
    ap.add_argument("--base", default="http://127.0.0.1:18765")
    ap.add_argument("--out", default="runs/recordings")
    ap.add_argument("--pace", type=int, default=2500, help="ms per frame (broadcast pace)")
    ap.add_argument("--frame", type=int, default=0, help="start frame (for highlight clips)")
    ap.add_argument("--max-seconds", type=float, default=0, help="cap recording length (0=play to end)")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--chrome", default=CHROME)
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--hide", action="store_true", help="hide opponent hands (player-view)")
    ap.add_argument("--no-commentary", action="store_true")
    ap.add_argument("--loop", action="store_true")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    out_dir = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    params = f"game={args.game}&autoplay=1&pace={args.pace}&frame={args.frame}"
    if args.hide:
        params += "&hide=1"
    if args.no_commentary:
        params += "&commentary=0"
    if args.loop:
        params += "&loop=1"
    url = f"{args.base}/?{params}"

    print(f"[record] {url}")
    print(f"[record] chrome={args.chrome} headless={not args.headed} pace={args.pace}ms")
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=args.chrome,
            headless=not args.headed,
            args=["--autoplay-policy=no-user-gesture-required",
                  "--force-device-scale-factor=1", "--no-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            record_video_dir=str(out_dir),
            record_video_size={"width": args.width, "height": args.height},
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_function("window.__VIEWER_READY__ === true", timeout=30000)
        total = page.evaluate("window.__VIEWER_TOTAL__") or 0
        print(f"[record] viewer ready, {total} frames")

        if args.max_seconds > 0:
            page.wait_for_timeout(int(args.max_seconds * 1000))
        else:
            # estimate full-play duration: frames*pace + banner pauses, generous cap
            est_ms = total * args.pace + total * 200 + 120000
            try:
                page.wait_for_function("window.__VIEWER_DONE__ === true", timeout=est_ms)
            except Exception as e:
                print(f"[record] done-wait ended early: {e}")
        final_frame = page.evaluate("window.__VIEWER_FRAME__")
        video_path = page.video.path() if page.video else None
        page.close()
        context.close()
        browser.close()

    if video_path and Path(video_path).exists():
        dest = out_dir / f"{args.game}_{int(time.time())}.webm"
        shutil.move(video_path, dest)
        kb = dest.stat().st_size / 1024
        print(f"[record] saved {dest}  ({kb:.0f} KB, {time.time()-t0:.1f}s wall, frame {final_frame}/{total})")
    else:
        print("[record] ERROR: no video file produced")
        sys.exit(1)


if __name__ == "__main__":
    main()