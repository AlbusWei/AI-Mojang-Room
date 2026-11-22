"""Random legal agent — for self-play tests and as a cheap baseline seat."""
from __future__ import annotations

import random
import time

from ..obs import SeatObservation
from .base import Agent, AgentDecision


class RandomAgent(Agent):
    def __init__(self, name: str, seed: int = 0):
        super().__init__(name)
        self._rng = random.Random(seed)

    def act(self, obs: SeatObservation) -> AgentDecision:
        t0 = time.perf_counter()
        opt = self._rng.choice(obs.options)
        return AgentDecision(
            action=opt.action,
            mjai=opt.mjai,
            label=opt.label,
            action_index=opt.index,
            reason="(random baseline)",
            latency_ms=(time.perf_counter() - t0) * 1000,
        )