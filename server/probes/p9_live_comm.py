"""P9 probe: live commentary end-to-end (random agents, no LLM cost).

Starts a live game on the running viewer server, polls /api/live/state until
done, then verifies commentary lines carry audio_url and the mp3 route serves
them (200 audio/mpeg). Validates the live narration pipeline (P9).
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:18765"
ROOT = Path(__file__).resolve().parents[2]


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    body = json.dumps({"config": "config/agents.random.json", "env": ".env",
                       "seed": 99, "game_id": f"p9_live_comm_{int(time.time())}"}).encode()
    req = urllib.request.Request(BASE + "/api/live/start", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.loads(r.read().decode())
    gid = j["game_id"]
    print("started", gid)
    since = 0
    status = "running"
    comm = []
    t0 = time.time()
    while time.time() - t0 < 90:
        d = get(f"/api/live/state?game={gid}&since={since}")
        since = d["n_frames"]
        status = d["status"]
        comm = d.get("commentary") or comm
        if status != "running":
            break
        time.sleep(0.5)
    # give the async TTS worker time to finish writing mp3s (network ~1s/line)
    for _ in range(120):
        d = get(f"/api/live/state?game={gid}&since={since}")
        comm = d.get("commentary") or comm
        if comm and all(c.get("audio_url") for c in comm if c.get("kind") != "highlight"):
            break
        time.sleep(0.5)
    spoken = [c for c in comm if c.get("kind") != "highlight"]
    with_audio = [c for c in spoken if c.get("audio_url")]
    print(f"status={status} frames={since} commentary={len(comm)} spoken={len(spoken)} with_audio={len(with_audio)}")
    ok = True
    if not spoken:
        print("FAIL: no spoken commentary lines"); ok = False
    if len(with_audio) < len(spoken):
        print("FAIL: some spoken lines lack audio_url"); ok = False
    # fetch first audio
    if with_audio:
        url = with_audio[0]["audio_url"]
        with urllib.request.urlopen(BASE + url, timeout=30) as r:
            ct = r.headers.get("Content-Type")
            data = r.read()
        print(f"audio {url} -> {ct} {len(data)} bytes")
        if ct != "audio/mpeg" or len(data) < 1000:
            print("FAIL: bad audio response"); ok = False
    # games list should include the live game
    games = get("/api/games")["games"]
    if not any(g["id"] == gid for g in games):
        print("FAIL: live game not in /api/games"); ok = False
    print("P9 LIVE COMMENTARY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
