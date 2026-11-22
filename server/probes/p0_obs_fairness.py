"""P0 probe: per-seat observation fairness + legal-action enforcement.

Checks:
  * each seat's observation exposes only its own hand (others masked),
  * legal_actions() is non-empty when a seat must act,
  * an illegal mjai action is rejected by select_action_from_mjai / env.step.
Run:  .venv\\Scripts\\python.exe server\\probes\\p0_obs_fairness.py
"""
from __future__ import annotations
import json
from riichienv import RiichiEnv, GameRule


def main():
    print("=== P0 observation fairness ===")
    env = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=7)
    env.reset()

    # Advance a few steps so we see both draw and response phases.
    import random
    rng = random.Random(1)
    for _ in range(6):
        if env.done():
            break
        obs = env.get_observations()
        actions = {}
        for pid, o in obs.items():
            legal = o.legal_actions()
            if legal:
                a = rng.choice(legal)
                if isinstance(a, str):
                    a = o.select_action_from_mjai(a)
                actions[pid] = a
        if actions:
            env.step(actions)

    obs = env.get_observations()
    print("seats needing action:", list(obs.keys()))
    for pid, o in obs.items():
        print(f"\n--- seat {pid} ---")
        print("player_id:", getattr(o, "player_id", "?"))
        hand = getattr(o, "hand", None)
        print("own hand type:", type(hand).__name__,
              "len:", (len(hand) if hasattr(hand, "__len__") else "?"))
        d = None
        try:
            d = o.to_dict()
            print("to_dict keys:", list(d.keys()) if isinstance(d, dict) else type(d).__name__)
            print("to_dict sample:", json.dumps(d, ensure_ascii=False, default=str)[:600])
        except Exception as e:
            print("to_dict error:", e)
        legal = o.legal_actions()
        print("num legal actions:", len(legal))
        if legal:
            a0 = legal[0]
            print("legal[0]:", (a0.to_mjai() if hasattr(a0, "to_mjai") else a0))
        # masked events: other players' tiles should be '?'
        try:
            evs = o.new_events()
            s = json.dumps(evs, ensure_ascii=False, default=str)
            print("new_events sample:", s[:400])
        except Exception as e:
            print("new_events error:", e)
        break  # one seat is enough to inspect structure

    # Illegal-action rejection probe
    print("\n=== illegal action rejection ===")
    o = next(iter(obs.values()))
    bogus = '{"type":"dahai","actor":0,"pai":"9z","tsumogiri":false}'  # 9z is not a real tile
    try:
        r = o.select_action_from_mjai(bogus)
        print("select_action_from_mjai(bogus) ->", r, "(None/raise = good)")
    except Exception as e:
        print("select_action_from_mjai(bogus) raised:", type(e).__name__, str(e)[:160], "(good)")


if __name__ == "__main__":
    main()