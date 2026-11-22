"""P5 probe: verify all 4 show models via the full agent path (prompt->JSON->legal action).
Run:  .venv\\Scripts\\python.exe server\\probes\\p5_models.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from aimahjong.config import load_env, load_config, build_agents
from aimahjong.obs import build_seat_observation
from riichienv import RiichiEnv, GameRule

env = load_env(ROOT / ".env")
cfg = load_config(ROOT / "config" / "tournament.real.json")
agents = build_agents(cfg, env)

e = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=42)
e.reset()
so = build_seat_observation(e.get_observations()[0])

ok = 0
for ag in agents:
    d = ag.act(so)
    status = "OK " if not d.fallback else "FALLBACK"
    if not d.fallback:
        ok += 1
    print(f"[{status}] {ag.name:20s} model={getattr(ag,'model','?'):18s} "
          f"lat={round(d.latency_ms or 0)}ms label={d.label} err={d.error}")
    if d.reason:
        print(f"        reason: {d.reason[:90]}")
print(f"\n{ok}/{len(agents)} models returned a legal action without fallback")