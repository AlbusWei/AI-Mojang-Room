"""Shared game-directory resolution for the show-production scripts.

Accepts either a directory path (``runs/p1_real_full``) or a bare game id
(``p3_test_s7_r1``). Bare ids are resolved by searching ``runs/`` recursively
for ``<id>/game.mjai.jsonl`` so tournament-nested games work the same way the
web viewer resolves them.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def resolve_game_dir(game_arg: str, runs_root: Path | None = None) -> Path:
    runs_root = runs_root or (ROOT / "runs")
    p = Path(game_arg)
    # 1) explicit path that already contains a log
    if (p / "game.mjai.jsonl").exists():
        return p
    # 2) path relative to runs/
    cand = runs_root / game_arg
    if (cand / "game.mjai.jsonl").exists():
        return cand
    # 3) bare id: search runs/ for a matching directory name
    if runs_root.exists():
        for log in runs_root.rglob("game.mjai.jsonl"):
            if log.parent.name == game_arg:
                return log.parent
    raise FileNotFoundError(
        f"game '{game_arg}' not found (tried path, runs/<arg>, and runs/**/<arg>/game.mjai.jsonl)"
    )
