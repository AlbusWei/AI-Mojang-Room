"""Fair per-seat observation builder.

Wraps a RiichiEnv ``Observation`` into a clean, JSON-friendly view that contains
ONLY what a real player may see: own hand + all public information (discards,
melds, dora indicators, scores, riichi status). Opponent hands are never exposed.
Also pre-computes facts (shanten / tenpai / waits) and a deduplicated, numbered
menu of legal actions for robust LLM selection.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from riichienv import convert, calculate_shanten

WIND_NAMES = {0: "东", 1: "南", 2: "西", 3: "北"}

# mjai action type -> Chinese label
_ACTION_LABEL = {
    "dahai": "打出",
    "chi": "吃",
    "pon": "碰",
    "daiminkan": "大明杠",
    "ankan": "暗杠",
    "kakan": "加杠",
    "reach": "立直",
    "hora": "和牌",
    "ryukyoku": "九種九牌(流局)",
    "pass": "过(不响应)",
    "none": "无操作",
}


@dataclass
class LegalOption:
    index: int
    mjai: str                 # canonical mjai JSON string
    label: str                # human-readable Chinese label
    action: Any               # engine Action object (used to step)


@dataclass
class MeldView:
    seat: int
    kind: str                 # chi / pon / daiminkan / ankan / kakan
    tiles: list[str]          # mjai strings
    from_who: Optional[int]
    opened: bool


@dataclass
class SeatObservation:
    seat: int
    round_wind: str
    kyoku_index: int
    honba: int
    oya: int
    scores: list[int]
    riichi_declared: list[bool]
    riichi_sticks: int
    dora_indicators: list[str]
    discards: list[list[str]]          # 4 seats, public 牌河
    melds: list[MeldView]              # all public melds
    hand: list[str]                    # own tiles (mjai, suit-sorted)
    drawn_tile: Optional[str]
    shanten: Optional[int]
    is_tenpai: bool
    waits: list[str]
    furiten: bool = False
    options: list[LegalOption] = field(default_factory=list)
    recent_events: list[str] = field(default_factory=list)

    # ---- convenience for prompt / logging ----
    def public_state_dict(self) -> dict:
        return {
            "seat": self.seat,
            "round_wind": self.round_wind,
            "kyoku_index": self.kyoku_index,
            "honba": self.honba,
            "oya": self.oya,
            "scores": self.scores,
            "riichi_declared": self.riichi_declared,
            "riichi_sticks": self.riichi_sticks,
            "dora_indicators": self.dora_indicators,
            "discards": self.discards,
            "melds": [vars(m) for m in self.melds],
        }


def _label_for(mjai_obj: dict) -> str:
    t = mjai_obj.get("type", "?")
    base = _ACTION_LABEL.get(t, t)
    pai = mjai_obj.get("pai")
    consumed = mjai_obj.get("consumed")
    if t in ("dahai", "hora") and pai:
        return f"{base} {pai}"
    if t in ("chi", "pon") and pai:
        cs = ",".join(consumed) if consumed else ""
        return f"{base} {pai}" + (f"（用手牌 {cs}）" if cs else "")
    if t in ("daiminkan", "ankan", "kakan") and pai:
        return f"{base} {pai}"
    return base


def _waits_to_mjai(waits: Any) -> list[str]:
    """waits may be empty bytes, a list of tile ids, or None — handle defensively."""
    if waits is None:
        return []
    if isinstance(waits, (bytes, bytearray)):
        if len(waits) == 0:
            return []
        try:
            return convert.tid_to_mjai_list(list(waits))
        except Exception:
            return []
    try:
        ids = list(waits)
        if not ids:
            return []
        return convert.tid_to_mjai_list(ids)
    except Exception:
        return []


def _base(code: str) -> str:
    return code[:-1] if code.endswith("r") else code


def reliable_waits(hand_ids_13: list[int]) -> list[str]:
    """Brute-force the winning tiles of a tenpai 13-tile hand.

    RiichiEnv's ``Observation.waits`` proved unreliable (P6), so derive waits
    from the authoritative ``calculate_shanten``: a tile type is a wait iff
    adding it completes the hand (shanten == -1).
    """
    try:
        if len(hand_ids_13) != 13 or int(calculate_shanten(hand_ids_13)) != 0:
            return []
        out = []
        for t in range(34):
            if int(calculate_shanten(hand_ids_13 + [t * 4])) == -1:
                out.append(convert.tid_to_mjai(t * 4))
        return out
    except Exception:
        return []


def build_seat_observation(o: Any) -> SeatObservation:
    """Build a fair SeatObservation from a RiichiEnv Observation (acting seat)."""
    seat = int(o.player_id)

    hand_ids = sorted(int(t) for t in o.hand)
    hand = convert.tid_to_mjai_list(hand_ids)

    drawn = None
    if getattr(o, "drawn_tile", None) is not None:
        try:
            drawn = convert.tid_to_mjai(int(o.drawn_tile))
        except Exception:
            drawn = None

    discards = [convert.tid_to_mjai_list([int(t) for t in d]) for d in o.discards]
    dora = convert.tid_to_mjai_list([int(t) for t in o.dora_indicators])

    melds: list[MeldView] = []
    for p in range(4):
        for m in o.melds[p]:
            kind = str(m.meld_type).split(".")[-1].lower()
            melds.append(MeldView(
                seat=p,
                kind=kind,
                tiles=convert.tid_to_mjai_list([int(t) for t in m.tiles]),
                from_who=(int(m.from_who) if m.from_who is not None else None),
                opened=bool(m.opened),
            ))

    try:
        shanten = int(calculate_shanten(hand_ids))
    except Exception:
        shanten = None

    # dedupe legal actions by canonical mjai (duplicate physical copies collapse)
    options: list[LegalOption] = []
    seen: set[str] = set()
    for a in o.legal_actions():
        mj = a.to_mjai()
        if mj in seen:
            continue
        seen.add(mj)
        try:
            obj = json.loads(mj)
        except Exception:
            obj = {}
        options.append(LegalOption(
            index=len(options),
            mjai=mj,
            label=_label_for(obj),
            action=a,
        ))

    try:
        recent = list(o.new_events())
    except Exception:
        recent = []

    # Reliable waits + furiten (only meaningful on a 13-tile hand, i.e. when
    # responding to a discard). Own-discards furiten: any wait already present
    # in own river forbids ron (engine enforces; we surface it as a fact).
    waits: list[str] = []
    furiten = False
    if len(hand_ids) == 13:
        waits = reliable_waits(hand_ids)
        if waits:
            own_river = {_base(c) for c in discards[seat]}
            furiten = any(_base(w) in own_river for w in waits)
        if bool(o.riichi_declared[seat]):
            # after declaring riichi, passing any win makes furiten permanent
            furiten = furiten or bool(getattr(o, "riichi_furiten", False))

    return SeatObservation(
        seat=seat,
        round_wind=WIND_NAMES.get(int(o.round_wind), str(o.round_wind)),
        kyoku_index=int(o.kyoku_index),
        honba=int(o.honba),
        oya=int(o.oya),
        scores=[int(s) for s in o.scores],
        riichi_declared=[bool(x) for x in o.riichi_declared],
        riichi_sticks=int(o.riichi_sticks),
        dora_indicators=dora,
        discards=discards,
        melds=melds,
        hand=hand,
        drawn_tile=drawn,
        shanten=shanten,
        is_tenpai=bool(o.is_tenpai),
        waits=waits,
        furiten=furiten,
        options=options,
        recent_events=recent,
    )