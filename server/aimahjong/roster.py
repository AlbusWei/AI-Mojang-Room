"""Roster (player/character registry) — product module M1.

A Player decouples *character* (display name / avatar / bio / brand) from *model
binding* (provider endpoint + model + params), so the same model can play several
characters and a character can swap models. The roster is the single source of
truth for "who can sit at a seat"; `config/agents.*.json` become preset lineups
that reference roster players by name.

Storage: config/roster.json  {"players": [ {...}, ... ]}.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
ROSTER_PATH = ROOT / "config" / "roster.json"


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return s or "player"


def load_roster(path: Optional[Path] = None) -> dict:
    p = Path(path) if path else ROSTER_PATH
    if not p.exists():
        return {"players": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"players": []}
    data.setdefault("players", [])
    return data


def save_roster(data: dict, path: Optional[Path] = None) -> None:
    p = Path(path) if path else ROSTER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_player(data: dict, pid: str) -> Optional[dict]:
    for pl in data.get("players", []):
        if pl.get("id") == pid:
            return pl
    return None


def player_to_seat(p: dict) -> dict:
    """Project a roster player into an agent seat spec (config.build_agents)."""
    seat = {
        "name": p.get("display") or p.get("id"),
        "type": p.get("type", "llm"),
    }
    for k in ("base_url", "api_key_env", "model", "temperature", "timeout",
              "extra_body", "omit_temperature", "max_retries", "seed"):
        if k in p and p[k] is not None:
            seat[k] = p[k]
    return seat


def resolve_seats(data: dict, seats: list) -> list[dict]:
    """seats = list of 4 roster ids (or inline seat dicts). Returns seat specs."""
    if len(seats) != 4:
        raise ValueError(f"expected exactly 4 seats, got {len(seats)}")
    out = []
    for s in seats:
        if isinstance(s, dict):
            out.append(s)
            continue
        pl = get_player(data, s)
        if pl is None:
            raise ValueError(f"roster player not found: {s!r}")
        if not pl.get("enabled", True):
            raise ValueError(f"roster player disabled: {s!r}")
        out.append(player_to_seat(pl))
    return out