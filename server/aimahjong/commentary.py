"""Event-driven Chinese commentary generation (facts-first, no hallucination).

Turns a game's MJAI event log + per-seat decisions into a short list of lively
commentary lines for key moments (round start, riichi, kan, hora, ryukyoku,
final ranking). Every fact comes from the engine events or the agent's own
recorded reason — nothing is invented. Lines are keyed by ``event_pos`` so the
viewer / recorder can trigger them (and their TTS audio) at the right frame.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class CommentaryLine:
    event_pos: int
    seat: Optional[int]
    kind: str           # round | riichi | kan | hora | ryukyoku | end | highlight
    text: str
    audio: Optional[str] = None   # filled by the TTS step (relative filename)

    def to_dict(self) -> dict:
        return asdict(self)


WIND = {"E": "東", "S": "南", "W": "西", "N": "北"}


def _name(agents, seat) -> str:
    if agents and 0 <= seat < len(agents):
        return agents[seat]
    return f"seat{seat}"


def generate_commentary(events: list, decisions: list, agents: list,
                        max_highlights: int = 6) -> list:
    """Generate commentary lines for key events. ``decisions`` may be empty."""
    lines: list[CommentaryLine] = []
    scores = [25000, 25000, 25000, 25000]
    # first decision per event_pos (response phases share a pos)
    dec_by_pos: dict = {}
    for d in decisions or []:
        dec_by_pos.setdefault(d.get("event_pos"), d)

    highlight_budget = max_highlights
    last_riichi_seat = None

    for pos, e in enumerate(events):
        t = e.get("type")
        if t == "start_kyoku":
            scores = list(e.get("scores", scores))
            wind = WIND.get(e.get("bakaze", "E"), "東")
            honba = e.get("honba", 0)
            txt = f"{wind}{e.get('kyoku', 1)}局开始"
            txt += f"，{honba}本場。" if honba else "。"
            lines.append(CommentaryLine(pos, None, "round", txt))
        elif t == "reach_accepted":
            seat = e.get("actor")
            last_riichi_seat = seat
            lines.append(CommentaryLine(pos, seat, "riichi",
                         f"{_name(agents, seat)} 宣布立直！"))
        elif t in ("ankan", "daiminkan", "kakan"):
            seat = e.get("actor")
            kind = {"ankan": "暗杠", "daiminkan": "大明杠", "kakan": "加杠"}[t]
            lines.append(CommentaryLine(pos, seat, "kan",
                         f"{_name(agents, seat)} {kind}！"))
        elif t == "hora":
            seat = e.get("actor")
            deltas = e.get("deltas", [0, 0, 0, 0])
            gain = deltas[seat] if seat is not None and seat < len(deltas) else 0
            for i in range(4):
                if i < len(deltas):
                    scores[i] += deltas[i]
            target = e.get("target")
            how = "自摸" if target == seat else "荣和"
            riichi_tag = "立直后" if last_riichi_seat == seat else ""
            lines.append(CommentaryLine(pos, seat, "hora",
                         f"{_name(agents, seat)} {riichi_tag}{how}！拿下 {gain} 点。"))
            last_riichi_seat = None
        elif t == "ryukyoku":
            deltas = e.get("deltas", [0, 0, 0, 0])
            for i in range(4):
                if i < len(deltas):
                    scores[i] += deltas[i]
            reason = e.get("reason", "")
            extra = "，荒牌流局。" if reason == "exhaustive_draw" else "。"
            lines.append(CommentaryLine(pos, None, "ryukyoku", "流局" + extra))
            last_riichi_seat = None
        elif t == "end_game":
            order = sorted(range(4), key=lambda i: -scores[i])
            champ = _name(agents, order[0])
            rank_txt = "、".join(f"第{i+1}名 {_name(agents, s)} {scores[s]}点"
                                 for i, s in enumerate(order))
            lines.append(CommentaryLine(pos, None, "end",
                         f"对局结束！{champ} 夺得一位。最终排名：{rank_txt}。"))
        elif t == "dahai" and highlight_budget > 0:
            # occasional reasoning highlight: a riichi discard or a thoughtful note
            d = dec_by_pos.get(pos)
            if d and d.get("reason") and not d.get("fallback"):
                reason = d["reason"].strip().replace("\n", " ")
                if len(reason) > 12 and ("立直" in reason or "听牌" in reason
                                         or "役" in reason or highlight_budget == max_highlights):
                    seat = d.get("seat")
                    snippet = reason[:60] + ("…" if len(reason) > 60 else "")
                    lines.append(CommentaryLine(pos, seat, "highlight",
                                 f"{_name(agents, seat)} 的思路：{snippet}"))
                    highlight_budget -= 1

    return lines


def to_srt(lines: list, start_s: float = 0.0, per_line_s: float = 4.0) -> str:
    """Rough SRT (evenly spaced) for editing; precise sync is done in the viewer."""
    def ts(sec: float) -> str:
        h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    out = []
    for i, ln in enumerate(lines):
        a = start_s + i * per_line_s
        b = a + per_line_s - 0.3
        out.append(f"{i+1}\n{ts(a)} --> {ts(b)}\n{ln.text}\n")
    return "\n".join(out)