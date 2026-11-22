"""P8 model probe: verify Nov-2026 flagship lineup on real observations.

All candidates routed via DashScope compatible-mode (hosts Qwen + DeepSeek +
ZHIPU/GLM + Kimi + MiniMax). Reports latency / legal-JSON validity / reason so we
can pick a strong-but-watchable 4-seat lineup.
Run:  .venv\\Scripts\\python.exe server\\probes\\p8_models.py
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
CANDIDATES = [
    ("Qwen3.8-max", "qwen3.8-max"),
    ("DSv4.1-flash", "deepseek-v4.1-flash"),
    ("DSv4-pro", "deepseek-v4-pro"),
    ("GLM-5.3", "glm-5.3"),
    ("GLM-5.3-Flash", "ZHIPU/GLM-5.3-Flash"),
    ("Kimi-k3.1-pro", "kimi-k3.1-pro"),
    ("MiniMax-M3", "MiniMax/MiniMax-M3"),
]


def main():
    env = load_env(ROOT / ".env")
    key = env.get("DASHSCOPE_API_KEY")
    g = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=42)
    g.reset()
    rng = random.Random(0)
    samples = []
    step = 0
    while len(samples) < 1 and step < 60 and not g.done():
        obs = g.get_observations()
        acts = {}
        for pid in sorted(obs.keys()):
            la = obs[pid].legal_actions()
            if not la:
                continue
            if len(samples) < 1:
                samples.append(build_seat_observation(obs[pid]))
            acts[pid] = rng.choice(la)
        if not acts:
            break
        g.step(acts)
        step += 1
    print(f"collected {len(samples)} obs", flush=True)
    for name, model in CANDIDATES:
        client = make_chat_client(BASE, key, timeout=45)
        a = LLMAgent(name, client, model, temperature=0.7, max_retries=0)
        d = a.act(samples[0])
        reason = d.reason[:70] if not d.fallback else f"ERR {d.error}"
        print(f"{name:16s} {model:24s} ok={0 if d.fallback else 1}/1 "
              f"lat={d.latency_ms/1000:.1f}s :: {reason}", flush=True)


if __name__ == "__main__":
    main()
