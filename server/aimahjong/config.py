"""Config + .env loading + agent factory (dependency-free)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .agents import Agent, RandomAgent, LLMAgent, MockLLMClient, make_chat_client


def load_env(path: str | Path) -> dict:
    """Parse a .env file (KEY=VALUE) and merge into os.environ. Returns dict."""
    out: dict = {}
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        out[k] = v
        os.environ.setdefault(k, v)
    return out


def load_config(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_agents(config: dict, env: Optional[dict] = None) -> list[Agent]:
    env = env or {}
    agents: list[Agent] = []
    seats = config.get("seats", [])
    if len(seats) != 4:
        raise ValueError(f"expected exactly 4 seats, got {len(seats)}")
    for i, s in enumerate(seats):
        name = s.get("name", f"seat{i}")
        typ = s.get("type", "random")
        if typ == "random":
            agents.append(RandomAgent(name, seed=int(s.get("seed", i))))
        elif typ == "mock":
            agents.append(LLMAgent(name, MockLLMClient(), model="mock",
                                   temperature=0.0))
        elif typ == "llm":
            key_env = s.get("api_key_env", "")
            api_key = env.get(key_env) or os.environ.get(key_env) or s.get("api_key", "")
            if not api_key:
                raise ValueError(
                    f"seat {name}: missing API key (set {key_env} in .env)")
            base_url = s["base_url"]
            client = make_chat_client(base_url, api_key,
                                      timeout=float(s.get("timeout", 60)),
                                      extra_body=s.get("extra_body"),
                                      omit_temperature=bool(s.get("omit_temperature", False)))
            agents.append(LLMAgent(
                name, client, model=s["model"],
                temperature=float(s.get("temperature", 0.7)),
                max_retries=int(s.get("max_retries", 1)),
            ))
        else:
            raise ValueError(f"seat {name}: unknown agent type {typ!r}")
    return agents