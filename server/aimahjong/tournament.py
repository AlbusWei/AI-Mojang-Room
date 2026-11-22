"""Tournament: seat-rotated duplicate boards + placement-point leaderboard.

Show-friendly (a few to a few dozen hanchan, NOT thousands for statistical
significance). For each seed the SAME deal is replayed across cyclic seat
rotations so every agent occupies every seat once per seed — duplicate mahjong
cancels deal luck (D-P0: RiichiEnv seed is reproducible). Results aggregate into
a leaderboard (placement points / wins / avg rank / score delta) written as JSON
+ readable Markdown. Every game is event-sourced and replayable in the viewer.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

from .config import build_agents
from .room import Room

# rank(1..4) -> points presets
PLACEMENT_PRESETS = {
    "placement": [4, 3, 2, 1],     # simple show-friendly (sum 10 / game)
    "botzone": [3, 2, 1, 0],       # THUDM / Botzone style
    "tenhou": [90, 45, 0, -135],   # Mortal-arena style rank points
}
START_SCORE = 25000


def resolve_points(scoring) -> tuple[str, Optional[list]]:
    """Return (type, points_list_or_None). scoring = preset str or dict."""
    if scoring is None:
        scoring = "placement"
    if isinstance(scoring, str):
        if scoring == "score_delta":
            return "score_delta", None
        if scoring in PLACEMENT_PRESETS:
            return "placement", PLACEMENT_PRESETS[scoring]
        raise ValueError(f"unknown scoring preset {scoring!r}")
    typ = scoring.get("type", "placement")
    if typ == "score_delta":
        return "score_delta", None
    pts = scoring.get("points") or PLACEMENT_PRESETS.get(typ, PLACEMENT_PRESETS["placement"])
    return "placement", list(pts)


@dataclass
class GameRecord:
    game_id: str
    seed: int
    rotation: int
    seats: list[str]          # seat index -> agent name
    scores: list[int]
    ranks: list[int]
    points: list[float]       # tournament points awarded per seat
    fallback_count: int
    num_kyoku: int
    hora_count: int
    out_dir: str


@dataclass
class Standing:
    name: str
    games: int = 0
    points: float = 0.0
    rank_counts: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    total_score: int = 0
    score_delta: int = 0
    wins: int = 0
    fallbacks: int = 0
    seat_counts: list[int] = field(default_factory=lambda: [0, 0, 0, 0])

    @property
    def avg_rank(self) -> float:
        return round(sum((i + 1) * c for i, c in enumerate(self.rank_counts)) / self.games, 3) if self.games else 0.0

    @property
    def win_rate(self) -> float:
        return round(self.wins / self.games, 3) if self.games else 0.0

    @property
    def avg_score(self) -> float:
        return round(self.total_score / self.games, 1) if self.games else 0.0


class Tournament:
    def __init__(self, config: dict, env: Optional[dict] = None,
                 out_dir: Optional[str | Path] = None,
                 progress: Optional[Callable[[str], None]] = None):
        self.config = config
        self.env = env or {}
        self.name = config.get("name") or f"tourney_{int(time.time())}"
        self.base_specs = config["seats"]
        if len(self.base_specs) != 4:
            raise ValueError("tournament needs exactly 4 seat specs")
        self.names = [s.get("name", f"seat{i}") for i, s in enumerate(self.base_specs)]
        if len(set(self.names)) != 4:
            raise ValueError("tournament agent names must be unique")
        # seeds
        if "seeds" in config:
            self.seeds = [int(s) for s in config["seeds"]]
        else:
            n = int(config.get("num_rounds", 2))
            start = int(config.get("seed_start", 42))
            self.seeds = [start + i for i in range(n)]
        self.rotations = int(config.get("rotations", 4))
        self.game_mode = config.get("game_mode", "4p-red-half")
        self.rule = config.get("rule", "tenhou")
        self.max_steps = int(config.get("max_steps", 6000))
        self.verbose = bool(config.get("verbose", False))
        self.score_type, self.points = resolve_points(config.get("scoring"))
        self.out_dir = Path(out_dir) if out_dir else Path("runs") / self.name
        self.progress = progress or (lambda msg: None)
        self.games: list[GameRecord] = []
        self.standings: dict[str, Standing] = {n: Standing(n) for n in self.names}

    def _award(self, scores: list[int], ranks: list[int]) -> list[float]:
        if self.score_type == "score_delta":
            return [float(s - START_SCORE) for s in scores]
        return [float(self.points[r - 1]) for r in ranks]

    def run(self) -> dict:
        total = len(self.seeds) * self.rotations
        idx = 0
        self.progress(f"[tournament] {self.name}: {len(self.seeds)} seeds x "
                      f"{self.rotations} rotations = {total} games; "
                      f"agents={self.names}; scoring={self.score_type}")
        for seed in self.seeds:
            for r in range(self.rotations):
                idx += 1
                # seat s <- base agent (s + r) % 4  (cyclic; each agent visits each seat)
                rotated = [self.base_specs[(s + r) % 4] for s in range(4)]
                agents = build_agents({"seats": rotated}, self.env)
                game_id = f"{self.name}_s{seed}_r{r}"
                game_dir = self.out_dir / "games" / game_id
                room = Room(agents, game_mode=self.game_mode, rule=self.rule,
                            seed=seed, out_dir=game_dir, game_id=game_id,
                            max_steps=self.max_steps, verbose=self.verbose)
                self.progress(f"[{idx}/{total}] {game_id} seats={[a.name for a in agents]} ...")
                res = room.run()
                pts = self._award(res.scores, res.ranks)
                rec = GameRecord(
                    game_id=game_id, seed=seed, rotation=r,
                    seats=[a.name for a in agents],
                    scores=res.scores, ranks=res.ranks, points=pts,
                    fallback_count=res.fallback_count, num_kyoku=res.num_kyoku,
                    hora_count=res.hora_count, out_dir=str(game_dir),
                )
                self.games.append(rec)
                for s in range(4):
                    st = self.standings[agents[s].name]
                    st.games += 1
                    st.points += pts[s]
                    st.rank_counts[res.ranks[s] - 1] += 1
                    st.total_score += res.scores[s]
                    st.score_delta += res.scores[s] - START_SCORE
                    st.wins += 1 if res.ranks[s] == 1 else 0
                    st.fallbacks += res.fallback_count
                    st.seat_counts[s] += 1
                self.progress(f"[{idx}/{total}] {game_id} done ranks={res.ranks} "
                              f"scores={res.scores} hora={res.hora_count} "
                              f"fallbacks={res.fallback_count}")
        result = self._build_result()
        self._write(result)
        return result

    def _leaderboard(self) -> list[Standing]:
        return sorted(self.standings.values(),
                      key=lambda s: (-s.points, -s.score_delta, -s.wins, s.avg_rank))

    def _build_result(self) -> dict:
        lb = self._leaderboard()
        return {
            "name": self.name,
            "config": {
                "seeds": self.seeds, "rotations": self.rotations,
                "scoring": {"type": self.score_type, "points": self.points},
                "game_mode": self.game_mode, "rule": self.rule,
                "agents": self.names,
            },
            "num_games": len(self.games),
            "games": [asdict(g) for g in self.games],
            "leaderboard": [
                {"rank": i + 1, "name": s.name, "games": s.games,
                 "points": round(s.points, 1), "wins": s.wins,
                 "win_rate": s.win_rate, "avg_rank": s.avg_rank,
                 "rank_counts": s.rank_counts, "avg_score": s.avg_score,
                 "score_delta": s.score_delta, "fallbacks": s.fallbacks,
                 "seat_counts": s.seat_counts}
                for i, s in enumerate(lb)
            ],
        }

    def _write(self, result: dict) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "tournament.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.out_dir / "leaderboard.md").write_text(
            self._markdown(result), encoding="utf-8")

    def _markdown(self, result: dict) -> str:
        cfg = result["config"]
        lines = [f"# 锦标赛积分榜 · {result['name']}", ""]
        lines.append(f"- 对局数：**{result['num_games']}**（{len(cfg['seeds'])} 副牌 × "
                     f"{cfg['rotations']} 座位轮换，复式）")
        lines.append(f"- 计分：{cfg['scoring']['type']}"
                     + (f" {cfg['scoring']['points']}" if cfg['scoring']['points'] else "（终分-25000）"))
        lines.append(f"- 规则：{cfg['rule']} / {cfg['game_mode']}")
        lines.append(f"- 选手：{', '.join(cfg['agents'])}")
        lines.append("")
        lines.append("| 名次 | 选手 | 积分 | 局数 | 一位 | 胜率 | 平均顺位 | 顺位分布(1/2/3/4) | 平均终分 | 累计点差 | 兜底 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for e in result["leaderboard"]:
            rc = "/".join(str(c) for c in e["rank_counts"])
            lines.append(f"| {e['rank']} | {e['name']} | {e['points']} | {e['games']} | "
                         f"{e['wins']} | {e['win_rate']:.0%} | {e['avg_rank']} | {rc} | "
                         f"{e['avg_score']} | {e['score_delta']:+d} | {e['fallbacks']} |")
        lines.append("")
        lines.append("## 每局明细")
        lines.append("| 局 | 牌种 | 轮换 | 座位(0→3) | 终分 | 顺位 | 积分 | 和了 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for g in result["games"]:
            seats = " / ".join(g["seats"])
            scores = " / ".join(str(s) for s in g["scores"])
            ranks = " / ".join(str(r) for r in g["ranks"])
            pts = " / ".join(str(p) for p in g["points"])
            lines.append(f"| {g['game_id']} | {g['seed']} | {g['rotation']} | {seats} | "
                         f"{scores} | {ranks} | {pts} | {g['hora_count']} |")
        lines.append("")
        return "\n".join(lines)