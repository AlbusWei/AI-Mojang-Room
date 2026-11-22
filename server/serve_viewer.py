"""Zero-dependency god-view viewer server (stdlib http.server).

Serves web/ and a small JSON API:
  GET /api/games                 -> list of recorded games
  GET /api/game/<id>/frames      -> replay frames + summary + agent names

Run:  .venv\\Scripts\\python.exe server\\serve_viewer.py --port 18765
Then open http://127.0.0.1:18765  (OBS Browser Source: same URL, 1920x1080).
"""
from __future__ import annotations
import argparse, json, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
RUNS = ROOT / "runs"
sys.path.insert(0, str(ROOT / "server"))
from aimahjong.replay import replay_mjai  # noqa: E402
from aimahjong.live import LiveManager  # noqa: E402
from aimahjong import roster as roster_mod  # noqa: E402

MANAGER = LiveManager(RUNS)


def _read_jsonl(p: Path):
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _game_dirs():
    if not RUNS.exists():
        return []
    dirs = [p.parent for p in RUNS.rglob("game.mjai.jsonl")
            if "_archive" not in p.relative_to(RUNS).parts]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs


def _summary(d: Path) -> dict:
    try:
        return json.loads((d / "summary.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def list_games():
    games = []
    seen = set()
    for d in _game_dirs():
        summ = _summary(d)
        rel = d.relative_to(RUNS)
        tourney = None
        if len(rel.parts) > 1 and (RUNS / rel.parts[0] / "tournament.json").exists():
            tourney = rel.parts[0]
        seen.add(d.name)
        games.append({
            "id": d.name,
            "agents": ", ".join(summ.get("agents", [])) or "?",
            "num_kyoku": summ.get("num_kyoku"),
            "scores": summ.get("scores"),
            "tournament": tourney,
            "mtime": d.stat().st_mtime,
            "live": None,
        })
    # surface in-memory live games (running, not yet on disk) so the selector /
    # leaderboard can link back to a game in progress
    for g in MANAGER.list():
        if g["game_id"] in seen:
            continue
        games.append({
            "id": g["game_id"],
            "agents": ", ".join(g["agents"]) or "?",
            "num_kyoku": None,
            "scores": None,
            "tournament": None,
            "mtime": g["started_at"],
            "live": g["status"],
        })
    games.sort(key=lambda x: x["mtime"], reverse=True)
    return games


def _find_game(gid: str):
    direct = RUNS / gid
    if (direct / "game.mjai.jsonl").exists():
        return direct
    for p in RUNS.rglob("game.mjai.jsonl"):
        if p.parent.name == gid:
            return p.parent
    return None


def game_frames(gid: str):
    d = _find_game(gid)
    if d is None:
        return None
    d = d.resolve()
    if RUNS.resolve() not in d.parents:
        return None
    events = _read_jsonl(d / "game.mjai.jsonl")
    decisions = _read_jsonl(d / "decisions.jsonl")
    frames = replay_mjai(events, decisions)
    summ = _summary(d)
    return {"frames": [f.to_dict() for f in frames], "summary": summ, "agents": summ.get("agents", [])}


def game_commentary(gid: str):
    d = _find_game(gid)
    if d is None:
        return None
    d = d.resolve()
    if RUNS.resolve() not in d.parents:
        return None
    cj = d / "commentary" / "commentary.json"
    if not cj.exists():
        return {"lines": [], "available": False}
    lines = json.loads(cj.read_text(encoding="utf-8"))
    for ln in lines:
        if ln.get("audio"):
            ln["audio_url"] = f"/commentary/{gid}/{ln['audio']}"
    return {"lines": lines, "available": True}


def list_tournaments():
    out = []
    if RUNS.exists():
        for d in RUNS.iterdir():
            tj = d / "tournament.json"
            if not (d.is_dir() and tj.exists()):
                continue
            try:
                data = json.loads(tj.read_text(encoding="utf-8"))
            except Exception:
                continue
            out.append({
                "id": d.name, "name": data.get("name"),
                "num_games": data.get("num_games"),
                "agents": data.get("config", {}).get("agents"),
                "leaderboard": data.get("leaderboard"),
                "mtime": tj.stat().st_mtime,
            })
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def tournament_data(tid: str):
    d = (RUNS / tid).resolve()
    if RUNS.resolve() not in d.parents:
        return None
    tj = d / "tournament.json"
    if not tj.exists():
        return None
    return json.loads(tj.read_text(encoding="utf-8"))


PLACEMENT = [4, 3, 2, 1]


def _is_official(summ: dict) -> bool:
    """A game counts toward the model standings only if all four seats are LLMs
    (no random / mock baselines), so baseline noise never pollutes the board."""
    agents = summ.get("agents") or []
    ranks = summ.get("ranks") or []
    if len(agents) != 4 or len(ranks) != 4:
        return False
    return not any(str(a).startswith(("Random", "Mock")) for a in agents)


def aggregate_standings():
    """Cross-game model leaderboard over every official (all-LLM) game.

    This is what makes a freshly finished game (e.g. live2026_1) immediately
    refresh the board instead of leaving a stale per-tournament snapshot.
    """
    per = {}
    games = []
    for d in _game_dirs():
        summ = _summary(d)
        if not _is_official(summ):
            continue
        games.append({"id": d.name, "agents": summ.get("agents"),
                      "scores": summ.get("scores"), "ranks": summ.get("ranks"),
                      "num_kyoku": summ.get("num_kyoku"),
                      "hora_count": summ.get("hora_count"),
                      "mtime": d.stat().st_mtime})
        for i, name in enumerate(summ["agents"]):
            s = per.setdefault(name, {"name": name, "games": 0, "points": 0,
                                      "wins": 0, "rank_counts": [0, 0, 0, 0],
                                      "score_delta": 0, "score_sum": 0,
                                      "hora": 0, "fallback": 0})
            r = summ["ranks"][i]
            s["games"] += 1
            s["points"] += PLACEMENT[r - 1]
            s["wins"] += 1 if r == 1 else 0
            s["rank_counts"][r - 1] += 1
            s["score_delta"] += summ["scores"][i] - 25000
            s["score_sum"] += summ["scores"][i]
    standings = []
    for s in per.values():
        g = s["games"] or 1
        s["avg_rank"] = round(sum((i + 1) * c for i, c in enumerate(s["rank_counts"])) / g, 3)
        s["avg_score"] = round(s["score_sum"] / g)
        s["win_rate"] = round(s["wins"] / g, 3)
        standings.append(s)
    standings.sort(key=lambda x: (-x["points"], -x["score_delta"], -x["wins"], x["avg_rank"]))
    return {"scoring": "placement[4,3,2,1]", "num_games": len(games),
            "games": games, "standings": standings}


def profiles():
    p = ROOT / "config" / "profiles.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"players": {}}


def list_configs():
    """Playable lineups (agents.*) and tournament presets (tournament.*) for the
    human 'new game' picker and the AI CLI. Read-only metadata, no secrets."""
    out = []
    for p in sorted((ROOT / "config").glob("*.json")):
        if p.name in ("profiles.json",):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        seats = data.get("seats") or data.get("agents") or []
        if not isinstance(seats, list) or not seats:
            continue
        kind = "tournament" if p.name.startswith("tournament.") else "live"
        out.append({
            "id": f"config/{p.name}",
            "kind": kind,
            "name": data.get("name") or p.stem,
            "seats": [{"name": s.get("name", "?"), "type": s.get("type", "?"),
                       "model": s.get("model", "")} for s in seats],
        })
    return {"configs": out}


# ---- Roster (product M1): player/character registry CRUD ----
def roster_list():
    return roster_mod.load_roster()


def roster_upsert(body: dict, pid: str | None = None):
    data = roster_mod.load_roster()
    players = data.setdefault("players", [])
    if pid is None:
        pid = body.get("id") or roster_mod.slug(body.get("display") or body.get("model") or "player")
        if roster_mod.get_player(data, pid) is not None:
            raise ValueError(f"player id already exists: {pid}")
        body["id"] = pid
        players.append(body)
    else:
        pl = roster_mod.get_player(data, pid)
        if pl is None:
            raise ValueError(f"player not found: {pid}")
        body["id"] = pid
        pl.update(body)
    roster_mod.save_roster(data)
    return roster_mod.get_player(data, pid)


def roster_delete(pid: str):
    data = roster_mod.load_roster()
    before = len(data.get("players", []))
    data["players"] = [p for p in data.get("players", []) if p.get("id") != pid]
    if len(data["players"]) == before:
        raise ValueError(f"player not found: {pid}")
    roster_mod.save_roster(data)
    return {"deleted": pid}


def _read_body(self):
    n = int(self.headers.get("Content-Length") or 0)
    return json.loads(self.rfile.read(n) or b"{}")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, fmt, *args):  # quieter
        pass

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/roster":
            try:
                return self._send_json(roster_upsert(_read_body(self)), 201)
            except Exception as e:
                return self._send_json({"error": str(e)}, 400)
        if path == "/api/live/start":
            try:
                body = _read_body(self)
                env = (ROOT / body.get("env", ".env")).resolve()
                seats_spec = None
                if body.get("seats"):
                    seats_spec = roster_mod.resolve_seats(roster_mod.load_roster(), body["seats"])
                    cfg = ROOT / "config" / "agents.mock.json"  # unused when seats given
                else:
                    cfg = (ROOT / body.get("config", "config/agents.mock.json")).resolve()
                    if ROOT.resolve() not in cfg.parents or not cfg.exists():
                        return self._send_json({"error": "config must exist under workspace"}, 400)
                game = MANAGER.start(
                    cfg, env, seed=int(body.get("seed", 42)),
                    game_id=body.get("game_id"),
                    game_mode=body.get("game_mode", "4p-red-half"),
                    rule=body.get("rule", "tenhou"),
                    seats_spec=seats_spec)
                return self._send_json({"game_id": game.game_id, "agents": game.agents,
                                        "url": f"/?live={game.game_id}"})
            except Exception as e:
                return self._send_json({"error": str(e)}, 400)
        return self.send_error(404)

    def do_PUT(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith("/api/roster/"):
            pid = path[len("/api/roster/"):]
            try:
                return self._send_json(roster_upsert(_read_body(self), pid))
            except Exception as e:
                return self._send_json({"error": str(e)}, 400)
        return self.send_error(404)

    def do_DELETE(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith("/api/roster/"):
            pid = path[len("/api/roster/"):]
            try:
                return self._send_json(roster_delete(pid))
            except Exception as e:
                return self._send_json({"error": str(e)}, 400)
        return self.send_error(404)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/games":
            return self._send_json({"games": list_games()})
        if path == "/api/live/list":
            return self._send_json({"games": MANAGER.list()})
        if path == "/api/live/state":
            q = urlparse(self.path).query
            from urllib.parse import parse_qs
            qs = parse_qs(q)
            gid = (qs.get("game") or [""])[0]
            since = int((qs.get("since") or ["0"])[0])
            game = MANAGER.get(gid)
            if game is None:
                return self._send_json({"error": "live game not found"}, 404)
            frames, n, status, summary, error = game.frames_since(since)
            game.update_commentary()
            with game._lock:
                comm = list(game.commentary)
            return self._send_json({"game_id": gid, "status": status, "agents": game.agents,
                                    "frames": frames, "n_frames": n,
                                    "summary": summary, "error": error,
                                    "commentary": comm})
        if path == "/api/tournaments":
            return self._send_json({"tournaments": list_tournaments()})
        if path == "/api/standings":
            return self._send_json(aggregate_standings())
        if path == "/api/profiles":
            return self._send_json(profiles())
        if path == "/api/configs":
            return self._send_json(list_configs())
        if path == "/api/roster":
            return self._send_json(roster_list())
        if path.startswith("/api/tournament/"):
            tid = path[len("/api/tournament/"):]
            data = tournament_data(tid)
            if data is None:
                return self._send_json({"error": "tournament not found"}, 404)
            return self._send_json(data)
        if path.startswith("/api/game/") and path.endswith("/frames"):
            gid = path[len("/api/game/"):-len("/frames")]
            data = game_frames(gid)
            if data is None:
                return self._send_json({"error": "game not found"}, 404)
            return self._send_json(data)
        if path.startswith("/api/game/") and path.endswith("/commentary"):
            gid = path[len("/api/game/"):-len("/commentary")]
            data = game_commentary(gid)
            if data is None:
                return self._send_json({"error": "game not found"}, 404)
            return self._send_json(data)
        if path.startswith("/commentary/"):
            parts = path[len("/commentary/"):].split("/", 1)
            if len(parts) == 2:
                gid, fname = parts
                d = _find_game(gid)
                base = (d / "commentary").resolve() if d is not None else None
                if base is None:
                    lg = MANAGER.get(gid)
                    if lg is not None:
                        base = lg._audio_dir.resolve()
                if base is not None:
                    f = (base / fname).resolve()
                    if base in f.parents and f.exists() and f.suffix == ".mp3":
                        body = f.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "audio/mpeg")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
            return self.send_error(404)
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[viewer] http://{args.host}:{args.port}  (web={WEB})")
    print(f"[viewer] games dir: {RUNS}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[viewer] stopped")


if __name__ == "__main__":
    main()