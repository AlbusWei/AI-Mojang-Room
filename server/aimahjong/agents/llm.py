"""LLM agent over any OpenAI-compatible chat endpoint (dependency-free urllib).

Flow: build THUDM-style messages -> call model -> parse strict JSON ->
resolve action_index (or raw mjai) to a legal engine Action -> on failure retry
once with a corrective note -> still failing => safe legal fallback (logged).
Captures reasoning_content (for later god-view CoT display), latency and tokens.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
import urllib.error
from typing import Callable, Optional

from ..obs import SeatObservation, LegalOption
from ..prompt import build_messages
from .base import Agent, AgentDecision, choose_fallback

# client(messages, model, temperature) -> {"content": str, "reasoning": str, "usage": dict}
ChatClient = Callable[[list, str, float], dict]


def make_chat_client(base_url: str, api_key: str, timeout: float = 60.0,
                     extra_body: Optional[dict] = None,
                     omit_temperature: bool = False) -> ChatClient:
    base_url = base_url.rstrip("/")
    url = base_url + "/chat/completions"

    def client(messages: list, model: str, temperature: float) -> dict:
        payload = {"model": model, "messages": messages}
        # some models (kimi-k3*) reject temperature; some (qwen3.8/deepseek-v4)
        # accept enable_thinking=False to skip slow chain-of-thought for pace.
        if not omit_temperature:
            payload["temperature"] = temperature
        if extra_body:
            payload.update(extra_body)
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = (data.get("choices") or [{}])[0].get("message", {}) or {}
        return {
            "content": msg.get("content") or "",
            "reasoning": msg.get("reasoning_content") or "",
            "usage": data.get("usage") or {},
        }

    return client


class MockLLMClient:
    """Deterministic stand-in for tests: always picks legal option 0."""

    def __call__(self, messages: list, model: str, temperature: float) -> dict:
        return {
            "content": '{"action_index": 0, "reason": "mock：选择第一个合法动作以验证解析链路"}',
            "reasoning": "",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    # strip markdown fences
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # grab outermost braces
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return None


def _resolve(obj: dict, options: list[LegalOption]) -> Optional[LegalOption]:
    # 1) action_index
    idx = obj.get("action_index", obj.get("index", obj.get("choice")))
    if idx is not None:
        try:
            idx = int(idx)
            if 0 <= idx < len(options):
                return options[idx]
        except Exception:
            pass
    # 2) raw mjai action string
    act = obj.get("action")
    if isinstance(act, str):
        for op in options:
            if op.mjai == act:
                return op
        try:
            want = json.loads(act)
            for op in options:
                have = json.loads(op.mjai)
                if (have.get("type") == want.get("type")
                        and have.get("pai") == want.get("pai")
                        and have.get("consumed") == want.get("consumed")):
                    return op
        except Exception:
            pass
    elif isinstance(act, dict):
        for op in options:
            have = json.loads(op.mjai)
            if (have.get("type") == act.get("type")
                    and have.get("pai") == act.get("pai")
                    and have.get("consumed") == act.get("consumed")):
                return op
    return None


class LLMAgent(Agent):
    def __init__(self, name: str, client: ChatClient, model: str,
                 temperature: float = 0.7, max_retries: int = 1):
        super().__init__(name)
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries

    def act(self, obs: SeatObservation) -> AgentDecision:
        t0 = time.perf_counter()
        messages = build_messages(obs)
        raw_all, reasoning_all, usage = [], [], {}
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = self.client(messages, self.model, self.temperature)
            except Exception as e:  # network / timeout / HTTP
                last_error = f"{type(e).__name__}: {e}"
                raw_all.append(f"[call error] {last_error}")
                continue

            content = resp.get("content", "")
            raw_all.append(content)
            if resp.get("reasoning"):
                reasoning_all.append(resp["reasoning"])
            usage = resp.get("usage") or usage

            obj = _extract_json(content)
            if obj is None:
                last_error = "no JSON object in response"
            else:
                opt = _resolve(obj, obs.options)
                if opt is not None:
                    return AgentDecision(
                        action=opt.action, mjai=opt.mjai, label=opt.label,
                        action_index=opt.index,
                        reason=str(obj.get("reason", "")),
                        raw="\n---\n".join(raw_all),
                        latency_ms=(time.perf_counter() - t0) * 1000,
                        tokens=usage or None,
                    )
                last_error = f"action not resolvable to a legal option: {obj}"

            # corrective retry
            messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content":
                    f"你的输出无法解析为合法动作（{last_error}）。"
                    f"请只输出 JSON：{{\"action_index\": <0..{len(obs.options)-1} 的整数>, "
                    f"\"reason\": \"<简短中文理由>\"}}，编号必须来自上面的合法动作菜单。"},
            ]

        # exhausted => safe fallback
        opt = choose_fallback(obs)
        return AgentDecision(
            action=opt.action, mjai=opt.mjai, label=opt.label,
            action_index=opt.index,
            reason=f"[fallback] {last_error}",
            fallback=True,
            raw="\n---\n".join(raw_all),
            latency_ms=(time.perf_counter() - t0) * 1000,
            tokens=usage or None,
            error=last_error,
        )