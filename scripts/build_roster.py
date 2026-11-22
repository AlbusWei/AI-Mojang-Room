"""Seed config/roster.json from existing presets + profiles (product M1).

Merges every seat found in config/agents.*.json / tournament.*.json into a
Player (character + model binding), enriching avatar/bio/brand from
config/profiles.json. Idempotent: re-running refreshes bindings but keeps any
manually-added players (matched by id). Run:
    .venv\\Scripts\\python.exe scripts\\build_roster.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from aimahjong.roster import load_roster, save_roster, slug  # noqa: E402

CFG = ROOT / "config"


def main():
    profiles = json.loads((CFG / "profiles.json").read_text(encoding="utf-8")).get("players", {})
    existing = {p["id"]: p for p in load_roster().get("players", [])}
    players = {}
    for p in sorted(CFG.glob("*.json")):
        if p.name in ("profiles.json", "roster.json"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        seats = data.get("seats") or data.get("agents") or []
        if not isinstance(seats, list):
            continue
        for s in seats:
            if not isinstance(s, dict):
                continue
            name = s.get("name") or slug(s.get("model", "player"))
            pid = slug(name)
            prof = profiles.get(name, {})
            pl = {
                "id": pid,
                "display": name,
                "type": s.get("type", "llm"),
                "avatar": prof.get("avatar"),
                "bio": prof.get("bio", ""),
                "brand": prof.get("brand", ""),
                "color": prof.get("color"),
                "tags": [prof.get("brand")] if prof.get("brand") else [],
                "enabled": True,
            }
            for k in ("base_url", "api_key_env", "model", "temperature", "timeout",
                      "extra_body", "omit_temperature", "max_retries", "seed"):
                if k in s:
                    pl[k] = s[k]
            # keep manual edits (bio/tags/enabled/avatar) if player already exists
            if pid in existing:
                old = existing[pid]
                for k in ("bio", "tags", "enabled", "avatar", "color"):
                    if old.get(k) not in (None, "", []):
                        pl[k] = old[k]
            players[pid] = pl
    # preserve manually-added players not present in any preset
    for pid, pl in existing.items():
        players.setdefault(pid, pl)
    out = {"players": sorted(players.values(), key=lambda x: x["id"])}
    save_roster(out)
    print(f"roster: {len(out['players'])} players -> config/roster.json")
    for pl in out["players"]:
        print(f"  {pl['id']:28s} {pl['type']:6s} {pl.get('model', '-')}")


if __name__ == "__main__":
    main()
