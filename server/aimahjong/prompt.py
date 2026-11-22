"""THUDM-style prompt construction for riichi LLM agents.

System prompt: rules + tile notation + fairness contract + strict JSON output.
User prompt: pre-computed engine facts (own hand + public state + shanten/tenpai)
followed by a numbered menu of legal actions. The model replies with
``{"action_index": N, "reason": "..."}`` (raw mjai also accepted as fallback).
"""
from __future__ import annotations

from .obs import SeatObservation, WIND_NAMES

SYSTEM_PROMPT = """你是一名日本立直麻将（ riichi mahjong ）职业玩家，正在参加一场四人南半场对局。你的目标是尽可能和牌得分、提升最终顺位。

【牌记号】
- 万子 1m–9m，筒子 1p–9p，索子 1s–9s。
- 字牌：E=东 S=南 W=西 N=北 P=白 F=發 C=中。
- 赤宝牌：5mr / 5pr / 5sr（红色的 5，算宝牌）。

【公平规则】
- 你只能看到自己的手牌，以及场上所有公开信息：四家牌河（弃牌）、副露（吃碰杠）、宝牌指示牌、各家分数与立直状态。
- 你看不到其他三家的手牌，也不要臆测具体某张牌在谁手里；只能基于公开信息做概率判断。

【完整规则操作】
每一步引擎会给出一个【合法动作菜单】，其中动作已由规则引擎校验合法。可能包含：
打出(dahai)、吃(chi)、碰(pon)、大明杠(daiminkan)、暗杠(ankan)、加杠(kakan)、立直(reach)、和牌(hora，含荣和/自摸)、过(pass，放弃响应对手的弃牌)、九種九牌(ryukyoku，开局流局)。
你必须且只能从菜单中选择一项。

【策略要点】
- 关注向听数（离听牌还差几张）、是否听牌及所听牌、宝牌与役种（立直/断幺/役牌/平和/一杯口等）。
- 防守：他家立直或明显听牌时，优先打安全牌（现物/筋牌），避免放铳；注意振听（自己牌河里有自己听的牌则不能荣和）。
- 立直需门清且听牌，权衡打点与速度；副露会破坏门清。

【输出格式（务必严格遵守）】
只输出一个 JSON 对象，不要任何额外文字、不要 markdown 代码块：
{"action_index": <菜单中的编号整数>, "reason": "<一到两句简短中文理由，说明你的判断>"}
"""


def _fmt_seat(i: int) -> str:
    return f"{i}号位({WIND_NAMES.get(i, '?')})"


def build_user_prompt(o: SeatObservation) -> str:
    lines: list[str] = []
    lines.append(f"=== 当前局面（你是 {o.seat} 号位）===")
    lines.append(f"场风: {o.round_wind}  局数(kyoku_index): {o.kyoku_index}  本场: {o.honba}  庄家(oya): {o.oya}号位")
    lines.append(f"立直棒: {o.riichi_sticks}")
    lines.append("各家分数: " + ", ".join(f"{i}号={s}" for i, s in enumerate(o.scores)))
    lines.append("各家立直: " + ", ".join(f"{i}号={'是' if r else '否'}" for i, r in enumerate(o.riichi_declared)))
    lines.append("宝牌指示牌: " + (", ".join(o.dora_indicators) if o.dora_indicators else "无"))

    lines.append("\n--- 你的手牌（含刚摸的牌）---")
    lines.append(" ".join(o.hand))
    if o.drawn_tile:
        lines.append(f"刚摸到: {o.drawn_tile}")
    if o.shanten is not None:
        lines.append(f"当前向听数: {o.shanten}" + ("（已听牌！）" if o.is_tenpai else ""))
    # Waits are now derived by brute-force over the authoritative shanten
    # calculator (obs.reliable_waits), NOT the unreliable Observation.waits.
    if o.waits:
        lines.append("所听牌（引擎核算）: " + " ".join(o.waits))
    if o.furiten:
        lines.append("⚠️ 你处于振听状态：不能荣和任何牌，只能自摸或改听！")

    lines.append("\n--- 公开副露（吃碰杠）---")
    if o.melds:
        for m in o.melds:
            src = f" 来自{m.from_who}号" if m.from_who is not None else ""
            lines.append(f"{m.seat}号位 {m.kind}: {' '.join(m.tiles)}{src}")
    else:
        lines.append("无")

    lines.append("\n--- 四家牌河（弃牌，公开）---")
    for i, d in enumerate(o.discards):
        lines.append(f"{i}号位: " + (" ".join(d) if d else "（空）"))

    # Facts-first defense aid: against a riichi opponent, tiles already in THAT
    # opponent's river are genbutsu (100% safe vs them, they are furiten on it).
    safe = []
    for i, r in enumerate(o.riichi_declared):
        if r and i != o.seat and o.discards[i]:
            uniq = sorted(set(o.discards[i]))
            safe.append(f"{i}号(已立直)现物: {' '.join(uniq)}")
    if safe:
        lines.append("\n--- 防守参考：对立直家的现物（打这些不会放铳给该家）---")
        lines.extend(safe)

    if o.recent_events:
        lines.append("\n--- 最近事件（mjai，已按你的视角屏蔽他家手牌）---")
        for ev in o.recent_events[-12:]:
            lines.append(ev)

    lines.append("\n=== 合法动作菜单（只能选一项，输出其编号）===")
    for opt in o.options:
        lines.append(f"[{opt.index}] {opt.label}")

    lines.append('\n请输出 JSON：{"action_index": <编号>, "reason": "<简短中文理由>"}')
    return "\n".join(lines)


def build_messages(o: SeatObservation) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(o)},
    ]