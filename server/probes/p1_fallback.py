"""P1 robustness probe: malformed / out-of-range LLM output must fall back to a
LEGAL action and the game must still complete. Run:
  .venv\\Scripts\\python.exe server\\probes\\p1_fallback.py
"""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aimahjong.agents.llm import LLMAgent
from aimahjong.agents.random_agent import RandomAgent
from aimahjong.room import Room


class GarbageClient:
    def __call__(self, messages, model, temperature):
        return {"content": "Sorry, I cannot decide what to do.", "reasoning": "", "usage": {}}


class BadIndexClient:
    def __call__(self, messages, model, temperature):
        return {"content": '{"action_index": 999, "reason": "oops"}', "reasoning": "", "usage": {}}


def main():
    agents = [
        LLMAgent("Garbage", GarbageClient(), "x", max_retries=1),
        LLMAgent("BadIndex", BadIndexClient(), "x", max_retries=1),
        RandomAgent("Rand-C", seed=3),
        RandomAgent("Rand-D", seed=4),
    ]
    room = Room(agents, seed=3, out_dir=tempfile.mkdtemp(prefix="p1_fallback_"))
    r = room.run()
    assert r.fallback_count > 0, "expected fallbacks from malformed clients"
    assert sum(r.scores) == 100000, f"points not conserved: {r.scores}"
    assert r.num_kyoku >= 1
    print(f"[PASS] fallback robustness: fallbacks={r.fallback_count} "
          f"steps={r.num_steps} kyoku={r.num_kyoku} scores={r.scores}")
    # show a couple fallback reasons
    fb = [d for d in r.decisions if d["fallback"]][:3]
    for d in fb:
        print(f"  fallback [{d['name']}] {d['label']} :: {d['reason'][:90]}")


if __name__ == "__main__":
    main()