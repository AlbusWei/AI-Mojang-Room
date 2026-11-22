"""P13 probe: verify Qwen4 Max invite (qwen-latest-series-invite-1102) on real obs.

The invite model lives ONLY on the qweneval evaluation endpoint (not DashScope
compatible-mode). Thinking is ON by default (xhigh); mahjong seats must send
enable_thinking:false (sending a non-none reasoning_effort alongside it is a 400).
This probe makes 3 real decision calls with thinking off and requires all ok.
Run:  .venv\\Scripts\\python.exe server\\probes\\p13_qwen4_invite.py
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

BASE = "https://qweneval.aliyuncs.com/1254597783533862/compatible-mode/v1"
MODEL = "qwen-latest-series-invite-1102"
NAME = "Qwen4-max-invite"


def main():
    env = load_env(ROOT / ".env")
    key = env.get("BAILIAN_INVITE_API_KEY")
    if not key:
        print("FAIL: BAILIAN_INVITE_API_KEY missing from .env (run scripts/setup_env.py)")
        sys.exit(1)
    g = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=42)
    g.reset()
    rng = random.Random(0)
    samples = []
    step = 0
    while len(samples) < 3 and step < 120 and not g.done():
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
    print(f"collected {len(samples)} obs", flush=True)
    client = make_chat_client(BASE, key, timeout=60,
                              extra_body={"enable_thinking": False})
    a = LLMAgent(NAME, client, MODEL, temperature=0.7, max_retries=0)
    ok = 0
    for i, s in enumerate(samples):
        d = a.act(s)
        good = not d.fallback
        ok += int(good)
        reason = d.reason[:70] if good else f"ERR {d.error}"
        print(f"call {i+1}: ok={int(good)}/1 lat={d.latency_ms/1000:.1f}s :: {reason}",
              flush=True)
    print(f"RESULT {ok}/{len(samples)} " + ("PASS" if ok == len(samples) else "FAIL"),
          flush=True)
    sys.exit(0 if ok == len(samples) else 1)


if __name__ == "__main__":
    main()
