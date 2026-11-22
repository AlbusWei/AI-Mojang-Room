"""Mux timed commentary audio into a recorded game video (full ffmpeg via imageio-ffmpeg).

The Playwright recorder produces video-only WebM. This adds the edge-tts narration
as a synced audio track, aligned to the autoplay pacing (pace + banner pauses),
and outputs a universal H.264 MP4.

Usage:
  .venv\\Scripts\\python.exe scripts\\mux_commentary.py \
      --game p1_real_full --video docs/samples/sample_highlight.webm \
      --start-frame 395 --pace 1800 --out docs/samples/sample_highlight_audio.mp4

Requires: pip install imageio-ffmpeg  (bundles a full ffmpeg; the Playwright one
is WebM-only and cannot mux).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from aimahjong.gameio import resolve_game_dir  # noqa: E402
from aimahjong.replay import replay_mjai  # noqa: E402

BANNER = {"hora", "ryukyoku", "end_game"}


def ff() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_duration(path: Path) -> float:
    r = subprocess.run([ff(), "-i", str(path)], capture_output=True, text=True)
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not m:
        return 0.0
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--start-frame", type=int, default=0)
    ap.add_argument("--pace", type=int, default=2500, help="ms per frame used when recording")
    ap.add_argument("--bannerpause", type=int, default=3000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    gdir = resolve_game_dir(args.game)
    video = Path(args.video)
    if not video.is_absolute():
        video = (ROOT / video).resolve()
    out = Path(args.out)
    if not out.is_absolute():
        out = (ROOT / out).resolve()

    ev = [json.loads(l) for l in (gdir / "game.mjai.jsonl").read_text("utf-8").splitlines() if l.strip()]
    frames = replay_mjai(ev)
    # display time (seconds) at which each frame first appears in the recording
    disp = {}
    t = 0.0
    for i in range(args.start_frame, len(frames)):
        disp[i] = t
        etype = frames[i].event.get("type")
        t += (args.pace + (args.bannerpause if etype in BANNER else 0)) / 1000.0
    video_dur = probe_duration(video) or t

    cpath = gdir / "commentary" / "commentary.json"
    lines = json.loads(cpath.read_text("utf-8")) if cpath.exists() else []
    cues = []
    for ln in lines:
        ep = ln.get("event_pos")
        audio = ln.get("audio")
        if ep is None or not audio or ep < args.start_frame or ep not in disp:
            continue
        af = gdir / "commentary" / audio
        if af.exists() and disp[ep] < video_dur:
            cues.append((disp[ep], af))
    cues.sort()
    print(f"[mux] video={video.name} dur~{video_dur:.1f}s start_frame={args.start_frame} cues={len(cues)}")
    for d, af in cues:
        print(f"  @{d:6.1f}s  {af.name}")

    cmd = [ff(), "-y", "-i", str(video)]
    for _, af in cues:
        cmd += ["-i", str(af)]
    if cues:
        # delay each narration to its cue time, then mix
        parts = []
        for idx, (d, _) in enumerate(cues, start=1):
            ms = int(d * 1000)
            parts.append(f"[{idx}:a]adelay={ms}|{ms}[a{idx}]")
        mix = "".join(f"[a{i}]" for i in range(1, len(cues) + 1))
        parts.append(f"{mix}amix=inputs={len(cues)}:normalize=0[aout]")
        cmd += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[aout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", "-shortest"]
    else:
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart"]
    cmd += [str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:]); sys.exit(1)
    print(f"[mux] saved {out} ({out.stat().st_size/1048576:.2f} MB)")


if __name__ == "__main__":
    main()
