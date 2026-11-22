"""Room: drives a full RiichiEnv game with one Agent per seat.

Event-sourced: the authoritative god-view MJAI log + a per-decision sidecar
(reason / raw thinking / fallback / latency / tokens) are written to disk. This
single source of truth serves fairness audit, replay, god-view UI and streaming.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

from riichienv import RiichiEnv, GameRule

from .obs import build_seat_observation
from .agents.base import Agent, forced_decision
from .agents.llm import LLMAgent

EventSink = Callable[[dict], None]


@dataclass
class GameResult:
    game_id: str
    seed: int
    agents: list[str]
    scores: list[int]
    ranks: list[int]
    num_steps: int
    num_events: int
    num_kyoku: int
    hora_count: int
    ryukyoku_count: int
    fallback_count: int
    total_latency_ms: float
    mjai_log: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    wins: list = field(default_factory=list)


def _rule(name: str):
    if name in ("tenhou", "default_tenhou"):
        return GameRule.default_tenhou()
    if name in ("mjsoul", "default_mjsoul"):
        return GameRule.default_mjsoul()
    raise ValueError(f"unknown rule preset {name!r}")


class Room:
    def __init__(self, agents: list[Agent], game_mode: str = "4p-red-half",
                 rule: str = "tenhou", seed: int = 42,
                 out_dir: Optional[str | Path] = None,
                 game_id: Optional[str] = None,
                 event_sink: Optional[EventSink] = None,
                 decision_sink: Optional[EventSink] = None,
                 max_steps: int = 6000, verbose: bool = False):
        if len(agents) != 4:
            raise ValueError("room needs exactly 4 agents")
        self.agents = agents
        self.game_mode = game_mode
        self.rule = rule
        self.seed = seed
        self.game_id = game_id or f"game_{seed}_{int(time.time())}"
        self.out_dir = Path(out_dir) if out_dir else Path("runs") / self.game_id
        self.event_sink = event_sink
        self.decision_sink = decision_sink
        self.max_steps = max_steps
        self.verbose = verbose

    def run(self) -> GameResult:
        env = RiichiEnv(game_mode=self.game_mode, rule=_rule(self.rule), seed=self.seed)
        env.reset()

        decisions: list[dict] = []
        prev_len = 0
        step = 0
        while not env.done() and step < self.max_steps:
            obs = env.get_observations()
            acts = {}
            event_pos = len(env.mjai_log)
            pids = [pid for pid in sorted(obs.keys()) if obs[pid].legal_actions()]
            seat_obs = {pid: build_seat_observation(obs[pid]) for pid in pids}
            decs = {}
            pending = []
            for pid in pids:
                # Engine-forced single option (e.g. riichi tsumogiri, lone pass):
                # no real choice exists -> skip the LLM round-trip entirely.
                if len(seat_obs[pid].options) == 1:
                    decs[pid] = forced_decision(seat_obs[pid].options[0])
                else:
                    pending.append(pid)
            # Parallelize only genuine LLM decisions (response phase can have 2-3
            # seats deciding at once). Random/mock stay sequential+deterministic.
            llm_pending = [p for p in pending if isinstance(self.agents[p], LLMAgent)]
            for pid in pending:
                if pid not in llm_pending:
                    decs[pid] = self.agents[pid].act(seat_obs[pid])
            if len(llm_pending) == 1:
                decs[llm_pending[0]] = self.agents[llm_pending[0]].act(seat_obs[llm_pending[0]])
            elif len(llm_pending) > 1:
                with ThreadPoolExecutor(max_workers=len(llm_pending)) as ex:
                    futs = {p: ex.submit(self.agents[p].act, seat_obs[p]) for p in llm_pending}
                    for p in llm_pending:
                        decs[p] = futs[p].result()
            for pid in pids:
                dec = decs[pid]
                acts[pid] = dec.action
                decisions.append({
                    "step": step,
                    "event_pos": event_pos,
                    "seat": pid,
                    "name": self.agents[pid].name,
                    "action_index": dec.action_index,
                    "mjai": dec.mjai,
                    "label": dec.label,
                    "reason": dec.reason,
                    "fallback": dec.fallback,
                    "latency_ms": round(dec.latency_ms, 1),
                    "tokens": dec.tokens,
                    "error": dec.error,
                    "raw": dec.raw,
                })
                if self.decision_sink is not None:
                    self.decision_sink(decisions[-1])
            if not acts:
                break
            env.step(acts)
            step += 1

            # incremental god-view events (for live streaming hook)
            log = env.mjai_log
            new_events = log[prev_len:]
            for j, ev in enumerate(new_events):
                e = ev if isinstance(ev, dict) else json.loads(ev)
                # NOTE: yaku/han/fu are NOT captured here — env.win_results is
                # transient (cleared within the same step at the next start_kyoku).
                # They are computed at replay time by replay.py's gated HandEvaluator
                # reconstruction, which only displays yaku when its points reconcile
                # exactly with the engine's authoritative hora deltas.
                if self.event_sink is not None:
                    self.event_sink(e)
                if self.verbose and e.get("type") == "start_kyoku":
                    print(f"  [{self.game_id}] kyoku={e.get('kyoku')} "
                          f"honba={e.get('honba')} scores={e.get('scores')}",
                          flush=True)
            prev_len = len(log)

        mjai_log = [ev if isinstance(ev, dict) else json.loads(ev) for ev in env.mjai_log]
        scores = [int(s) for s in env.scores()]
        ranks = [int(r) for r in env.ranks()]

        types = [e.get("type") for e in mjai_log]
        result = GameResult(
            game_id=self.game_id, seed=self.seed,
            agents=[a.name for a in self.agents],
            scores=scores, ranks=ranks,
            num_steps=step, num_events=len(mjai_log),
            num_kyoku=types.count("start_kyoku"),
            hora_count=types.count("hora"),
            ryukyoku_count=types.count("ryukyoku"),
            fallback_count=sum(1 for d in decisions if d["fallback"]),
            total_latency_ms=round(sum(d["latency_ms"] for d in decisions), 1),
            mjai_log=mjai_log, decisions=decisions,
        )
        self._write(result)
        return result

    def _write(self, r: GameResult) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        with (self.out_dir / "game.mjai.jsonl").open("w", encoding="utf-8") as f:
            for ev in r.mjai_log:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        with (self.out_dir / "decisions.jsonl").open("w", encoding="utf-8") as f:
            for d in r.decisions:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        summary = {k: v for k, v in asdict(r).items()
                   if k not in ("mjai_log", "decisions", "wins")}
        summary["out_dir"] = str(self.out_dir)
        (self.out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")