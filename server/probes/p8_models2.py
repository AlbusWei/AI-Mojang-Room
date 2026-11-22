"""P8 model probe v2: real-mahjong-prompt latency with correct per-model params.
Run:  .venv\\Scripts\\python.exe server\\probes\\p8_models2.py
"""
from __future__ import annotations
import sys, random
from pathlib import Path
SRV = Path(__file__).resolve().parent.parent
ROOT = SRV.parent
sys.path.insert(0, str(SRV))
from riichienv import RiichiEnv, GameRule
from aimahjong.config import load_env
from aimahjong.obs import build_seat_observation
from aimahjong.agents.llm import LLMAgent, make_chat_client

BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
CAND = [
    ("Qwen3.8-max", "qwen3.8-max", {"enable_thinking": False}, False),
    ("DSv4.1-flash", "deepseek-v4.1-flash", {"enable_thinking": False}, False),
    ("GLM-5.3", "glm-5.3", None, False),
    ("Kimi-k3.1-pro", "kimi-k3.1-pro", None, True),
    ("cmaas-glm-5.3", "cmaas-glm-5.3", None, False),
    ("DSv4-pro", "deepseek-v4-pro", {"enable_thinking": False}, False),
]


def main():
    env = load_env(ROOT / ".env")
    key = env["DASHSCOPE_API_KEY"]
    g = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=42)
    g.reset()
    rng = random.Random(0)
    sample = None
    step = 0
    while sample is None and step < 60 and not g.done():
        obs = g.get_observations()
        acts = {}
        for pid in sorted(obs.keys()):
            la = obs[pid].legal_actions()
            if not la:
                continue
            if sample is None:
                sample = build_seat_observation(obs[pid])
            acts[pid] = rng.choice(la)
        if not acts:
            break
        g.step(acts)
        step += 1
    for name, model, extra, omit in CAND:
        client = make_chat_client(BASE, key, timeout=60, extra_body=extra, omit_temperature=omit)
        a = LLMAgent(name, client, model, temperature=0.7, max_retries=0)
        d = a.act(sample)
        reason = d.reason[:60] if not d.fallback else f"ERR {d.error}"
        print(f"{name:15s} {model:22s} ok={0 if d.fallback else 1} "
              f"lat={d.latency_ms/1000:.1f}s :: {reason}", flush=True)


if __name__ == "__main__":
    main()
