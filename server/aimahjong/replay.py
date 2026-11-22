"""God-view MJAI replay: turn an event log into per-event visual frames.

Pure logic (no I/O) so it is unit-testable and reusable for both the offline
viewer and the live stream server. Each Frame is a full snapshot of what a
god-view spectator sees right after that event, plus the acting seat's
reasoning (joined from decisions.jsonl by event_pos).

Tile codes are MJAI strings: 1m..9m / 1p..9p / 1s..9s, red fives 5mr/5pr/5sr,
honors E S W N P(白) F(發) C(中).

At a `hora` event we additionally compute the winning hand's yaku / han / fu
(best-effort, via RiichiEnv HandEvaluator) for display. Points always come from
the engine's authoritative `deltas`; the yaku block is enrichment only and is
omitted if it cannot be computed reliably.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

HONOR_ORDER = {"E": 0, "S": 1, "W": 2, "N": 3, "P": 4, "F": 5, "C": 6}
SUIT_ORDER = {"m": 0, "p": 1, "s": 2}
WIND_NUM = {"E": 0, "S": 1, "W": 2, "N": 3}


def tile_base(code: str) -> str:
    """Strip the red marker: 5mr -> 5m."""
    return code[:-1] if code.endswith("r") else code


def tile_sort_key(code: str):
    base = tile_base(code)
    if base in HONOR_ORDER:
        return (3, HONOR_ORDER[base], 0)
    suit = base[-1]
    num = int(base[:-1])
    return (SUIT_ORDER.get(suit, 9), num, 1 if code.endswith("r") else 0)


def sort_tiles(codes: list[str]) -> list[str]:
    return sorted(codes, key=tile_sort_key)


def _remove_one(hand: list[str], pai: str) -> None:
    for i, c in enumerate(hand):
        if c == pai:
            hand.pop(i)
            return
    # fallback: match by base (red/normal) if exact missing
    for i, c in enumerate(hand):
        if tile_base(c) == tile_base(pai):
            hand.pop(i)
            return


def _new_seat(score: int = 25000) -> dict:
    return {
        "hand": [],
        "drawn": None,
        "discards": [],   # {pai, tsumogiri, called}
        "melds": [],      # {type, tiles, from_who, opened, called_tile}
        "score": score,
        "riichi": False,
        "ippatsu": False,
        "double_riichi": False,
        "shanten": None,  # -1 complete / 0 tenpai / N shanten; None = unknown
        "furiten": False,  # own-river furiten: cannot ron while waiting on own discard
        "waits": [],       # winning tiles when tenpai (engine-recomputed)
    }


ALL_BASE = [f"{n}{s}" for s in ("m", "p", "s") for n in range(1, 10)] + \
           ["E", "S", "W", "N", "P", "F", "C"]


@lru_cache(maxsize=262144)
def _waits_of(hand_key: tuple) -> tuple:
    """Winning tiles of a tenpai concealed hand (13/10/7/4/1 tiles). Brute-force
    the 34 tile types against calculate_shanten (Observation.waits is unreliable)."""
    try:
        from riichienv import calculate_shanten, convert
        if len(hand_key) % 3 != 1:
            return ()
        tids = convert.mjai_to_tid_list(list(hand_key))
        if int(calculate_shanten(tids)) != 0:
            return ()
        out = []
        for b in ALL_BASE:
            full = list(hand_key) + [b]
            if int(calculate_shanten(convert.mjai_to_tid_list(full))) == -1:
                out.append(b)
        return tuple(out)
    except Exception:
        return ()


@lru_cache(maxsize=262144)
def _shanten_of(hand_key: tuple) -> Optional[int]:
    """Shanten of a concealed hand. riichienv infers the meld count from the
    tile count (13/10/7/4/1 = 0..4 melds), so open hands are handled correctly.
    -1 = complete hand, 0 = tenpai. For a drawn hand (n%3==2) report -1 if it
    can win now, else the best shanten over unique discards."""
    try:
        from riichienv import calculate_shanten, convert
        n = len(hand_key)
        if n == 0:
            return None
        tids = convert.mjai_to_tid_list(list(hand_key))
        if n % 3 == 1:
            return int(calculate_shanten(tids))
        if int(calculate_shanten(tids)) == -1:
            return -1
        best, seen = 99, set()
        for idx, c in enumerate(hand_key):
            b = tile_base(c)
            if b in seen:
                continue
            seen.add(b)
            rest = hand_key[:idx] + hand_key[idx + 1:]
            best = min(best, int(calculate_shanten(convert.mjai_to_tid_list(list(rest)))))
        return best
    except Exception:
        return None


def seat_shanten(hand: list[str]) -> Optional[int]:
    if not hand:
        return None
    return _shanten_of(tuple(sorted(hand, key=tile_sort_key)))


def _win_result(hand_mjai, melds, win_pai, dora_mjai, ura_mjai, *, tsumo, riichi,
                double_riichi, ippatsu, rinshan, chankan, player_wind, round_wind,
                honba, riichi_sticks) -> Optional[dict]:
    """Best-effort yaku/han/fu via RiichiEnv HandEvaluator. None on any failure."""
    try:
        from riichienv import HandEvaluator, Conditions, Meld, MeldType, convert
        mt = {"chi": MeldType.Chi, "pon": MeldType.Pon, "daiminkan": MeldType.Daiminkan,
              "ankan": MeldType.Ankan, "kakan": MeldType.Kakan}
        tiles = convert.mjai_to_tid_list(list(hand_mjai))
        meld_objs = []
        for m in melds:
            meld_objs.append(Meld(
                meld_type=mt[m["type"]],
                tiles=convert.mjai_to_tid_list(m["tiles"]),
                called_tile=convert.mjai_to_tid(m.get("called_tile") or m["tiles"][0]),
                from_who=int(m.get("from_who", 0)),
                opened=bool(m.get("opened", True)),
            ))
        wt = convert.mjai_to_tid(win_pai)
        dora = convert.mjai_to_tid_list(list(dora_mjai)) if dora_mjai else None
        ura = convert.mjai_to_tid_list(list(ura_mjai)) if ura_mjai else None
        cond = Conditions(tsumo=tsumo, riichi=riichi, double_riichi=double_riichi,
                          ippatsu=ippatsu, rinshan=rinshan, chankan=chankan,
                          player_wind=player_wind, round_wind=round_wind,
                          honba=honba, riichi_sticks=riichi_sticks)
        r = HandEvaluator(tiles, meld_objs or None).calc(wt, dora, cond, ura)
        if not r.is_win:
            return None
        return {"han": r.han, "fu": r.fu, "yakuman": bool(r.yakuman),
                "yaku": [y.name for y in r.yaku_list()],
                "ron_agari": int(r.ron_agari),
                "tsumo_agari_ko": int(r.tsumo_agari_ko),
                "tsumo_agari_oya": int(r.tsumo_agari_oya)}
    except Exception:
        return None


@dataclass
class Frame:
    index: int
    event: dict
    seats: list[dict]
    dora: list[str]
    bakaze: str
    kyoku: int
    honba: int
    kyotaku: int
    oya: int
    banner: Optional[str] = None
    decisions: list = field(default_factory=list)
    win: Optional[dict] = None
    wall: int = 70  # live-wall tiles remaining (Majsoul 余牌)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "event": self.event,
            "seats": self.seats,
            "dora": self.dora,
            "bakaze": self.bakaze,
            "kyoku": self.kyoku,
            "honba": self.honba,
            "kyotaku": self.kyotaku,
            "oya": self.oya,
            "banner": self.banner,
            "decisions": self.decisions,
            "win": self.win,
            "wall": self.wall,
        }


def replay_mjai(events: list[dict], decisions: Optional[list[dict]] = None,
                wins: Optional[list[dict]] = None) -> list[Frame]:
    """Replay a god-view MJAI log into snapshots. `decisions` joined by event_pos.

    `wins` (optional) is the authoritative engine win-results sidecar (wins.json):
    [{event_pos, results:{seat:{han,fu,yaku,...}}}]. When present it is preferred
    over the offline best-effort reconstruction (which is only shown if its
    computed points reconcile with the engine's authoritative deltas).
    """
    dec_by_pos: dict[int, list] = {}
    for d in (decisions or []):
        dec_by_pos.setdefault(d["event_pos"], []).append(d)
    wins_by_pos: dict[int, dict] = {}
    for w in (wins or []):
        wins_by_pos[w["event_pos"]] = w.get("results", {})
    seats = [_new_seat() for _ in range(4)]
    dora: list[str] = []
    bakaze, kyoku, honba, kyotaku, oya = "E", 1, 0, 0, 0
    frames: list[Frame] = []
    # win-enrichment state
    last_discard_pai: Optional[str] = None
    last_type: Optional[str] = None
    rinshan_pending = False
    kyoku_discards = 0
    kyoku_calls = 0
    draws = 0                 # tsumo count this kyoku -> live wall = 70 - draws
    ippatsu_pending = [False] * 4  # riichi declaration discard not yet thrown
    riichi_decl_pending = [False] * 4  # next dahai by this seat is the riichi tile

    for i, ev in enumerate(events):
        t = ev.get("type")
        banner: Optional[str] = None
        win: Optional[dict] = None

        if t == "start_kyoku":
            bakaze = ev.get("bakaze", "E")
            kyoku = ev.get("kyoku", 1)
            honba = ev.get("honba", 0)
            kyotaku = ev.get("kyotaku", 0)
            oya = ev.get("oya", 0)
            dora = [ev["dora_marker"]] if ev.get("dora_marker") else []
            for s in range(4):
                seats[s] = _new_seat(ev["scores"][s])
                seats[s]["hand"] = sort_tiles(list(ev["tehais"][s]))
            last_discard_pai, last_type, rinshan_pending = None, None, False
            kyoku_discards, kyoku_calls = 0, 0
            draws = 0
            ippatsu_pending = [False] * 4
            riichi_decl_pending = [False] * 4

        elif t == "tsumo":
            a = ev["actor"]
            seats[a]["hand"].append(ev["pai"])
            seats[a]["drawn"] = ev["pai"]
            draws += 1

        elif t == "dahai":
            a = ev["actor"]
            _remove_one(seats[a]["hand"], ev["pai"])
            seats[a]["hand"] = sort_tiles(seats[a]["hand"])
            seats[a]["drawn"] = None
            is_riichi_tile = riichi_decl_pending[a]
            seats[a]["discards"].append(
                {"pai": ev["pai"], "tsumogiri": ev.get("tsumogiri", False), "called": False,
                 "riichi": is_riichi_tile,
                 "double_riichi": bool(is_riichi_tile and seats[a]["double_riichi"])}
            )
            riichi_decl_pending[a] = False
            last_discard_pai = ev["pai"]
            kyoku_discards += 1
            # ippatsu window: the riichi *declaration* discard does NOT close it;
            # the seat's NEXT discard (or any call) does.
            if ippatsu_pending[a]:
                ippatsu_pending[a] = False
            elif seats[a]["riichi"]:
                seats[a]["ippatsu"] = False

        elif t in ("chi", "pon", "daiminkan"):
            a, tgt = ev["actor"], ev["target"]
            for c in ev.get("consumed", []):
                _remove_one(seats[a]["hand"], c)
            seats[a]["hand"] = sort_tiles(seats[a]["hand"])
            tiles = sort_tiles(list(ev.get("consumed", [])) + [ev["pai"]])
            seats[a]["melds"].append(
                {"type": t, "tiles": tiles, "from_who": tgt, "opened": True,
                 "called_tile": ev["pai"]}
            )
            if seats[tgt]["discards"]:
                seats[tgt]["discards"][-1]["called"] = True
            seats[a]["drawn"] = None
            kyoku_calls += 1
            for s in range(4):
                seats[s]["ippatsu"] = False
            if t == "daiminkan":
                rinshan_pending = True

        elif t == "ankan":
            a = ev["actor"]
            for c in ev.get("consumed", []):
                _remove_one(seats[a]["hand"], c)
            seats[a]["hand"] = sort_tiles(seats[a]["hand"])
            cons = list(ev.get("consumed", []))
            seats[a]["melds"].append(
                {"type": "ankan", "tiles": sort_tiles(cons),
                 "from_who": a, "opened": False, "called_tile": cons[0] if cons else None}
            )
            kyoku_calls += 1
            for s in range(4):
                seats[s]["ippatsu"] = False
            rinshan_pending = True

        elif t == "kakan":
            a = ev["actor"]
            _remove_one(seats[a]["hand"], ev["pai"])
            seats[a]["hand"] = sort_tiles(seats[a]["hand"])
            for m in seats[a]["melds"]:
                if m["type"] == "pon" and tile_base(m["tiles"][0]) == tile_base(ev["pai"]):
                    m["type"] = "kakan"
                    m["tiles"] = sort_tiles(m["tiles"] + [ev["pai"]])
                    m["called_tile"] = ev["pai"]
                    break
            kyoku_calls += 1
            for s in range(4):
                seats[s]["ippatsu"] = False
            rinshan_pending = True

        elif t == "dora":
            if ev.get("dora_marker"):
                dora.append(ev["dora_marker"])

        elif t == "reach":
            a = ev["actor"]
            seats[a]["riichi"] = True
            riichi_decl_pending[a] = True
            # double riichi: first go-around, no calls interrupted (approx)
            if kyoku_calls == 0 and kyoku_discards < 4:
                seats[a]["double_riichi"] = True

        elif t == "reach_accepted":
            # riichi stick deposited: actor pays 1000 into the pot (kyotaku)
            a = ev["actor"]
            seats[a]["riichi"] = True
            seats[a]["score"] -= 1000
            seats[a]["ippatsu"] = True
            ippatsu_pending[a] = True
            kyotaku += 1

        elif t == "hora":
            a = ev["actor"]
            deltas = ev.get("deltas", [0, 0, 0, 0])
            banner = f"seat{a} 和了"
            kyotaku_before = kyotaku
            for s in range(4):
                seats[s]["score"] += deltas[s]
            # hora deltas ALREADY include collected riichi sticks (verified
            # against engine scores at every kyoku boundary); just clear the pot.
            kyotaku = 0
            # --- yaku/han/fu enrichment: authoritative engine wins preferred ---
            is_tsumo = ev.get("target", a) == a
            win_pai = seats[a]["drawn"] if is_tsumo else last_discard_pai
            auth = wins_by_pos.get(i, {}).get(a) or wins_by_pos.get(i, {}).get(str(a))
            if auth:
                win = {"seat": a, "tsumo": is_tsumo, "points": deltas[a],
                       "win_tile": win_pai, "han": auth["han"], "fu": auth["fu"],
                       "yakuman": auth["yakuman"], "yaku": auth["yaku"],
                       "ura": list(ev.get("ura_markers", [])), "dora": list(dora),
                       "source": "engine"}
            elif win_pai:
                concealed = list(seats[a]["hand"])
                if is_tsumo:
                    _remove_one(concealed, win_pai)
                wr = _win_result(
                    concealed, seats[a]["melds"], win_pai, dora,
                    ev.get("ura_markers", []),
                    tsumo=is_tsumo, riichi=seats[a]["riichi"],
                    double_riichi=seats[a]["double_riichi"],
                    ippatsu=seats[a]["ippatsu"] and seats[a]["riichi"],
                    rinshan=rinshan_pending and is_tsumo,
                    chankan=(last_type == "kakan" and not is_tsumo),
                    player_wind=(a - oya + 4) % 4,
                    round_wind=WIND_NUM.get(bakaze, 0),
                    honba=honba, riichi_sticks=kyotaku_before,
                )
                # only show reconstructed yaku if its points reconcile with the
                # engine's authoritative delta (otherwise omit to avoid误导).
                # HandEvaluator already folds honba into the agari values via
                # Conditions.honba, and accounts for dealer via player_wind;
                # riichi sticks (kyotaku) are NOT included, so add them here.
                if wr:
                    if not is_tsumo:
                        base = wr["ron_agari"]
                    elif a == oya:
                        # dealer wins: all three payers are ko -> 3 * ko share
                        base = 3 * wr["tsumo_agari_ko"]
                    else:
                        base = 2 * wr["tsumo_agari_ko"] + wr["tsumo_agari_oya"]
                    if base + kyotaku_before * 1000 == deltas[a]:
                        win = {"seat": a, "tsumo": is_tsumo, "points": deltas[a],
                               "win_tile": win_pai, "han": wr["han"], "fu": wr["fu"],
                               "yakuman": wr["yakuman"], "yaku": wr["yaku"],
                               "ura": list(ev.get("ura_markers", [])), "dora": list(dora),
                               "source": "reconstructed"}

        elif t == "ryukyoku":
            banner = "流局 " + str(ev.get("reason", ""))
            for s in range(4):
                seats[s]["score"] += ev.get("deltas", [0, 0, 0, 0])[s]
            # riichi sticks carry over to the next kyoku (kyotaku unchanged)

        elif t == "end_game":
            banner = "终局"
            # leftover riichi sticks go to the highest-scoring player (Tenhou)
            if kyotaku > 0:
                top = max(range(4), key=lambda s: seats[s]["score"])
                seats[top]["score"] += kyotaku * 1000
                kyotaku = 0

        # rinshan flag only applies to the draw immediately after a kan
        if t == "tsumo":
            pass  # keep rinshan_pending until the hora/tsumo consumes it
        elif t not in ("ankan", "kakan", "daiminkan", "dora"):
            rinshan_pending = False

        # per-seat tenpai/shanten badge (engine-authoritative shanten)
        for s in range(4):
            seats[s]["shanten"] = seat_shanten(seats[s]["hand"])
            # furiten / waits only meaningful on a waiting (13/10/7/4/1) hand;
            # carry the previous value across the drawn (14-tile) frame.
            if len(seats[s]["hand"]) % 3 == 1:
                w = _waits_of(tuple(sorted(seats[s]["hand"], key=tile_sort_key)))
                seats[s]["waits"] = list(w)
                own = {tile_base(d["pai"]) for d in seats[s]["discards"]}
                seats[s]["furiten"] = bool(w) and any(tile_base(x) in own for x in w)
        if win:
            seats[win["seat"]]["shanten"] = -1

        frames.append(
            Frame(i, ev, copy.deepcopy(seats), list(dora),
                  bakaze, kyoku, honba, kyotaku, oya, banner, dec_by_pos.get(i, []), win,
                  wall=max(0, 70 - draws))
        )
        last_type = t

    return frames