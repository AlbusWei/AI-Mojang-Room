"""P1 probe #2: Meld serialization, shanten input, action round-trip, facts.
Run:  .venv\\Scripts\\python.exe server\\probes\\p1_api2.py
"""
from __future__ import annotations
import json, random, inspect
import riichienv
from riichienv import RiichiEnv, GameRule, convert, Meld, calculate_shanten


def main():
    env = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=7)
    env.reset()
    o = env.get_observations()[0]

    print("=== convert hand ===")
    print("tid_to_mjai_list(hand):", convert.tid_to_mjai_list(list(o.hand)))
    print("drawn_tile:", o.drawn_tile, type(o.drawn_tile).__name__)
    if o.drawn_tile is not None:
        try:
            print("drawn mjai:", convert.tid_to_mjai(o.drawn_tile))
        except Exception as e:
            print("drawn conv err:", e)
    print("is_tenpai:", o.is_tenpai, "waits:", o.waits)

    print("\n=== calculate_shanten input formats ===")
    hand = list(o.hand)
    for label, arg in [("hand14", hand), ("hand13", hand[:13])]:
        try:
            print(f"  {label}: shanten =", calculate_shanten(arg))
        except Exception as e:
            print(f"  {label} err:", repr(e)[:120])

    print("\n=== action round-trip (dedup) ===")
    legal = o.legal_actions()
    seen, uniq = set(), []
    for a in legal:
        mj = a.to_mjai()
        if mj not in seen:
            seen.add(mj); uniq.append((mj, a))
    print("legal count:", len(legal), "unique mjai:", len(uniq))
    mj0, a0 = uniq[0]
    rt = o.select_action_from_mjai(mj0)
    print("select_action_from_mjai(uniq[0]) ->", repr(rt)[:100])
    print("round-trip ok:", rt is not None)

    print("\n=== check_riichi_candidates ===")
    try:
        print("sig:", inspect.signature(riichienv.check_riichi_candidates))
    except Exception as e:
        print("sig err:", e)

    print("\n=== Meld class ===")
    print("Meld attrs:", [n for n in dir(Meld) if not n.startswith("_")])

    # play random until a meld appears, then inspect
    rng = random.Random(1)
    meld_obs = None
    for _ in range(400):
        if env.done():
            break
        obs = env.get_observations()
        acts = {}
        for pid in sorted(obs.keys()):
            la = obs[pid].legal_actions()
            if la:
                acts[pid] = rng.choice(la)
        if not acts:
            break
        env.step(acts)
        for pid, oo in obs.items():
            if any(oo.melds[p] for p in range(4)):
                meld_obs = oo
        if meld_obs is not None:
            break
    if meld_obs is not None:
        print("\n=== sample melds (from random play) ===")
        for p in range(4):
            for m in meld_obs.melds[p]:
                print(f"  seat{p} meld:", repr(m)[:160])
                print("    attrs:", {n: getattr(m, n) for n in dir(m) if not n.startswith('_') and not callable(getattr(m, n))})
                break
            if any(meld_obs.melds[p]):
                break
    else:
        print("\n(no meld encountered in 400 random steps)")


if __name__ == "__main__":
    main()