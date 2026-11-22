"""Agent interface + decision record + safe fallback policy."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..obs import SeatObservation, LegalOption


@dataclass
class AgentDecision:
    action: Any                       # engine Action object to step
    mjai: str                         # canonical mjai of chosen action
    label: str
    action_index: Optional[int] = None
    reason: str = ""
    fallback: bool = False
    raw: str = ""                     # raw model output (audit)
    latency_ms: float = 0.0
    tokens: Optional[dict] = None
    error: Optional[str] = None


class Agent(ABC):
    """A seat in the room. Implementations must return a legal engine Action."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def act(self, obs: SeatObservation) -> AgentDecision:
        ...


def forced_decision(opt: LegalOption) -> AgentDecision:
    """Engine-forced single-option decision: no model call needed (no choice exists).

    Used when the legal menu has exactly one entry (e.g. forced tsumogiri after
    riichi, or a lone pass). Saves an LLM round-trip and cannot be illegal.
    """
    return AgentDecision(
        action=opt.action, mjai=opt.mjai, label=opt.label, action_index=opt.index,
        reason="引擎强制：唯一合法动作", fallback=False, raw="", latency_ms=0.0,
        tokens=None, error=None,
    )


def choose_fallback(obs: SeatObservation) -> LegalOption:
    """Deterministic, legal, sensible default when an agent fails to decide.

    Priority: take a win (hora) > pass on a response > tsumogiri (discard the
    drawn tile) > first discard option. Never returns an illegal action.
    """
    opts = obs.options
    if not opts:
        raise ValueError("no legal options to fall back to")

    def by_type(t: str) -> Optional[LegalOption]:
        for op in opts:
            try:
                if json.loads(op.mjai).get("type") == t:
                    return op
            except Exception:
                continue
        return None

    hora = by_type("hora")
    if hora:
        return hora
    pas = by_type("pass")
    if pas:
        return pas
    # discard phase: prefer discarding the just-drawn tile (tsumogiri)
    if obs.drawn_tile:
        for op in opts:
            try:
                obj = json.loads(op.mjai)
                if obj.get("type") == "dahai" and obj.get("pai") == obs.drawn_tile:
                    return op
            except Exception:
                continue
    dahai = by_type("dahai")
    if dahai:
        return dahai
    return opts[0]