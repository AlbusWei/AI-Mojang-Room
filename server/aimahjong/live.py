"""Live game manager: run a Room in a background thread and expose its
incremental god-view frames for real-time streaming (P7).

The viewer polls /api/live/state?game=<id>&since=<n>; each response carries the
frames produced since the cursor plus status/summary. Frames are recomputed by
replay_mjai only when new events arrived (memoized shanten keeps this cheap).
"""
from __future__ import annotations

import queue
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

from .commentary import generate_commentary
from .config import build_agents, load_config, load_env
from .replay import replay_mjai
from .room import Room

NARRATOR_VOICE = "zh-CN-YunxiNeural"
# kinds that get spoken audio live (highlights are subtitle-only to avoid lag)
SPOKEN_KINDS = {"round", "riichi", "kan", "hora", "ryukyoku", "end"}


class LiveGame:
    def __init__(self, game_id: str, agents: list[str], out_dir: Path):
        self.game_id = game_id
        self.agents = agents
        self.out_dir = out_dir
        self.status = "running"  # running | done | error
        self.events: list[dict] = []
        self.decisions: list[dict] = []
        self.summary: Optional[dict] = None
        self.error: Optional[str] = None
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._frames: list = []
        self._frames_n = -1  # event count the cached frames were built from
        # live commentary (P9): incremental lines + async TTS
        self.commentary: list[dict] = []
        self._comm_pos: set = set()
        self._tts_q: queue.Queue = queue.Queue()
        self._audio_dir = out_dir / "commentary"
        self._tts_thread = threading.Thread(target=self._tts_worker,
                                            name=f"tts-{game_id}", daemon=True)
        self._tts_thread.start()

    def _on_event(self, ev: dict) -> None:
        with self._lock:
            self.events.append(ev)

    def _on_decision(self, dec: dict) -> None:
        with self._lock:
            self.decisions.append(dec)

    def _tts_worker(self) -> None:
        import asyncio
        while True:
            item = self._tts_q.get()
            if item is None:
                return
            pos, text = item
            try:
                import edge_tts
                self._audio_dir.mkdir(parents=True, exist_ok=True)
                fname = f"live_{pos:05d}.mp3"
                path = self._audio_dir / fname
                asyncio.run(edge_tts.Communicate(text, NARRATOR_VOICE).save(str(path)))
                with self._lock:
                    for ln in self.commentary:
                        if ln["event_pos"] == pos:
                            ln["audio_url"] = f"/commentary/{self.game_id}/{fname}"
            except Exception:
                pass  # subtitle still shows; audio optional
            finally:
                self._tts_q.task_done()

    def update_commentary(self) -> None:
        """Generate commentary for events seen so far; enqueue new spoken lines."""
        with self._lock:
            events = list(self.events)
            decisions = list(self.decisions)
        if not events:
            return
        lines = generate_commentary(events, decisions, self.agents, max_highlights=4)
        with self._lock:
            for ln in lines:
                if ln.event_pos in self._comm_pos:
                    continue
                self._comm_pos.add(ln.event_pos)
                d = ln.to_dict()
                d["audio_url"] = None
                self.commentary.append(d)
                if ln.kind in SPOKEN_KINDS:
                    self._tts_q.put((ln.event_pos, ln.text))

    def frames_since(self, since: int) -> tuple[list[dict], int, str, Optional[dict], Optional[str]]:
        with self._lock:
            n = len(self.events)
            if n != self._frames_n:
                self._frames = [f.to_dict() for f in replay_mjai(self.events, self.decisions)]
                self._frames_n = n
            since = max(0, min(since, len(self._frames)))
            return (self._frames[since:], len(self._frames), self.status,
                    self.summary, self.error)


class LiveManager:
    def __init__(self, runs_root: Path):
        self.runs_root = Path(runs_root)
        self.games: dict[str, LiveGame] = {}
        self._lock = threading.Lock()

    def start(self, config_path: str | Path, env_path: str | Path,
              seed: int = 42, game_id: Optional[str] = None,
              game_mode: str = "4p-red-half", rule: str = "tenhou",
              seats_spec: Optional[list] = None) -> LiveGame:
        env = load_env(env_path)
        if seats_spec is not None:
            config = {"seats": seats_spec}
        else:
            config = load_config(config_path)
        agents = build_agents(config, env)
        gid = game_id or f"live_{seed}_{int(time.time())}"
        with self._lock:
            if gid in self.games:
                raise ValueError(f"live game {gid!r} already exists")
            game = LiveGame(gid, [a.name for a in agents], self.runs_root / gid)
            self.games[gid] = game

        def run():
            try:
                room = Room(agents, game_mode=game_mode, rule=rule, seed=seed,
                            out_dir=game.out_dir, game_id=gid,
                            event_sink=game._on_event, decision_sink=game._on_decision)
                result = room.run()
                with game._lock:
                    game.summary = {
                        "game_id": result.game_id, "seed": result.seed,
                        "agents": result.agents, "scores": result.scores,
                        "ranks": result.ranks, "num_kyoku": result.num_kyoku,
                        "hora_count": result.hora_count,
                        "ryukyoku_count": result.ryukyoku_count,
                        "fallback_count": result.fallback_count,
                    }
                    game.status = "done"
            except Exception:
                with game._lock:
                    game.error = traceback.format_exc(limit=3)
                    game.status = "error"

        threading.Thread(target=run, name=f"live-{gid}", daemon=True).start()
        return game

    def get(self, gid: str) -> Optional[LiveGame]:
        with self._lock:
            return self.games.get(gid)

    def list(self) -> list[dict]:
        with self._lock:
            games = list(self.games.values())
        return [{"game_id": g.game_id, "status": g.status, "agents": g.agents,
                 "num_events": len(g.events), "num_decisions": len(g.decisions),
                 "started_at": g.started_at} for g in games]
