"""P0 probe: ENGINE determinism under a fixed seed, using a canonical policy.

The earlier random-policy test diverged because rng.choice() consumed the RNG in
dict-iteration order. Here the policy is fully deterministic (no RNG): iterate
seats sorted by pid, pick the lexicographically-smallest legal mjai action.
If same seed still yields identical streams, RiichiEnv is reproducible and we can
build duplicate-board tournaments directly on its seed.
Run:  .venv\\Scripts\\python.exe server\\probes\\p0_determinism.py
"""
from __future__ import annotations
import json
from riichienv import RiichiEnv, GameRule


def _key(a):
    return a.to_mjai() if hasattr(a, "to_mjai") else str(a)


def canonical_action(o):
    legal = o.legal_actions()
    if not legal:
        return None
    a = min(legal, key=_key)
    if isinstance(a, str):
        a = o.select_action_from_mjai(a)
    return a


def stream(seed, max_steps=6000):
    env = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=seed)
    env.reset()
    steps = 0
    while not env.done() and steps < max_steps:
        obs = env.get_observations()
        actions = {}
        for pid in sorted(obs.keys()):
            a = canonical_action(obs[pid])
            if a is not None:
                actions[pid] = a
        if not actions:
            break
        env.step(actions)
        steps += 1
    log = env.mjai_log
    if isinstance(log, str):
        return [json.loads(l) for l in log.splitlines() if l.strip()]
    return [json.loads(e) if isinstance(e, str) else e for e in log]


def first_kyoku(evts):
    for e in evts:
        if e.get("type") == "start_kyoku":
            return e
    return None


def main():
    print("=== P0 determinism (canonical policy) ===")
    a = stream(42)
    b = stream(42)
    same = a == b
    print(f"same seed(42): events={len(a)}/{len(b)} identical={same}")
    print("opening deal identical:", first_kyoku(a) == first_kyoku(b))

    c = stream(43)
    print(f"diff seed(43) vs (42): different={a != c} (events {len(a)} vs {len(c)})")

    if not same:
        # locate first divergence to understand its nature
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                print(f"first divergence at event {i}:")
                print("  A:", json.dumps(x, ensure_ascii=False)[:200])
                print("  B:", json.dumps(y, ensure_ascii=False)[:200])
                break

    ok = same and (a != c)
    print("RESULT:", "PASS (engine reproducible via seed)" if ok else "FAIL/INCONCLUSIVE")
    if not same:
        print("NOTE: deal is reproducible but mid-game diverges -> for duplicate boards,")
        print("      replay the same seed+policy, or use Mortal arena (decision D-P0).")


if __name__ == "__main__":
    main()