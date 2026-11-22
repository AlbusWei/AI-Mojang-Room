"""P1 real-API probe: a few real calls per model on real observations.
Verifies auth + request + JSON parse + legal-action resolution for >=2 families.
Run:  .venv\\Scripts\\python.exe server\\probes\\p1_real.py
"""
from __future__ import annotations
import sys, random
from pathlib import Path
SRV = Path(__file__).resolve().parent.parent
ROOT = SRV.parent
sys.path.insert(0, str(SRV))

from riichienv import RiichiEnv, GameRule
from aimahjong.config import load_env, load_config, build_agents
from aimahjong.obs import build_seat_observation


def main():
    env = load_env(ROOT / ".env")
    cfg = load_config(ROOT / "config" / "agents.real.json")
    agents = build_agents(cfg, env)
    llm_agents = [a for a in agents if a.__class__.__name__ == "LLMAgent"]
    print("real LLM seats:", [(a.name, a.model) for a in llm_agents])

    # collect 3 distinct real observations by stepping a random game
    g = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=42)
    g.reset()
    rng = random.Random(0)
    samples = []
    step = 0
    while len(samples) < 3 and step < 60 and not g.done():
        obs = g.get_observations()
        acts = {}
        for pid in sorted(obs.keys()):
            la = obs[pid].legal_actions()
            if not la:
                continue
            if len(samples) < 3:
                samples.append(build_seat_observation(obs[pid]))
            acts[pid] = rng.choice(la)
        if not acts:
            break
        g.step(acts)
        step += 1
    print(f"collected {len(samples)} sample observations\n")

    ok = 0
    total = 0
    for a in llm_agents:
        for i, s in enumerate(samples):
            total += 1
            d = a.act(s)
            status = "FALLBACK" if d.fallback else "ok"
            if not d.fallback:
                ok += 1
            print(f"[{a.name} #{i}] {status} | {d.label} | {d.latency_ms:.0f}ms "
                  f"| tokens={d.tokens}")
            print(f"    reason: {d.reason[:100]}")
            if d.fallback:
                print(f"    error: {d.error}")
    print(f"\n=== real-API success: {ok}/{total} ===")
    print("[PASS]" if ok >= total - 1 and ok >= 4 else "[CHECK]")


if __name__ == "__main__":
    main()