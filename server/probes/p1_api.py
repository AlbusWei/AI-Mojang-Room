"""P1 probe: introspect the RiichiEnv API surface needed for obs/prompt/agents.
Discovers: tile-id->mjai-string conversion, legal_actions()/to_mjai() exact format,
Action/ActionType members, shanten/evaluator helpers. Run:
  .venv\\Scripts\\python.exe server\\probes\\p1_api.py
"""
from __future__ import annotations
import json
import riichienv
from riichienv import RiichiEnv, GameRule


def main():
    print("=== riichienv top-level ===")
    print([n for n in dir(riichienv) if not n.startswith("_")])

    print("\n=== riichienv.convert ===")
    try:
        from riichienv import convert
        print([n for n in dir(convert) if not n.startswith("_")])
    except Exception as e:
        print("convert import err:", e)

    env = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=7)
    env.reset()
    obs = env.get_observations()
    # find an acting seat
    acting = None
    for pid in sorted(obs.keys()):
        if obs[pid].legal_actions():
            acting = pid
            break
    o = obs[acting]
    print(f"\n=== acting seat {acting} ===")
    print("Observation methods:", [n for n in dir(o) if not n.startswith("_")])
    print("hand (136 ids):", list(o.hand))

    print("\n=== legal_actions() sample ===")
    legal = o.legal_actions()
    print("count:", len(legal), "elem type:", type(legal[0]).__name__)
    for a in legal[:6]:
        mj = a.to_mjai() if hasattr(a, "to_mjai") else None
        print("  action repr:", repr(a)[:120])
        print("    to_mjai type:", type(mj).__name__, "value:", (mj if isinstance(mj, str) else json.dumps(mj, ensure_ascii=False))[:160])

    print("\n=== ActionType members ===")
    try:
        from riichienv import ActionType
        print([n for n in dir(ActionType) if not n.startswith("_")])
    except Exception as e:
        print("ActionType err:", e)

    print("\n=== tile id -> string attempts ===")
    hand = list(o.hand)
    # try convert helpers
    for fn in ("tile_to_str", "id_to_tile", "to_mjai", "tile_id_to_str", "convert_tile"):
        try:
            from riichienv import convert
            f = getattr(convert, fn, None)
            if f:
                print(f"convert.{fn}(hand[0]={hand[0]}) ->", f(hand[0]))
        except Exception as e:
            print(f"convert.{fn} err:", e)

    print("\n=== shanten / evaluator ===")
    for name in ("calculate_shanten", "HandEvaluator"):
        print(name, "present:", hasattr(riichienv, name))
    try:
        from riichienv import calculate_shanten
        import inspect
        print("calculate_shanten sig:", inspect.signature(calculate_shanten))
    except Exception as e:
        print("shanten sig err:", e)

    print("\n=== to_dict (full) ===")
    d = o.to_dict()
    print(json.dumps({k: (v if not isinstance(v, list) or len(v) < 20 else v[:20]) for k, v in d.items()}, ensure_ascii=False, default=str)[:1200])


if __name__ == "__main__":
    main()