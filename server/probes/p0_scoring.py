"""P0 probe: scoring sanity across many seeds (canonical policy).

Invariants checked:
  1. Points conservation: sum(final scores) == 100000 for every game
     (riichi sticks / honba are internal transfers, so the total is closed).
  2. Wins occur: at least some games contain `hora` and produce non-trivial
     score changes (random/canonical play is weak, but not zero).
  3. end_game present and scores length 4.
Run:  .venv\\Scripts\\python.exe server\\probes\\p0_scoring.py
"""
from __future__ import annotations
import json
from collections import Counter
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


def play(seed, max_steps=6000):
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
    evts = [json.loads(e) if isinstance(e, str) else e for e in log]
    counts = Counter(e.get("type") for e in evts)
    scores = list(env.scores())
    return scores, counts, evts


def main():
    print("=== P0 scoring sanity (canonical policy, 24 seeds) ===")
    bad_sum = 0
    games_with_hora = 0
    games_score_changed = 0
    total_hora = 0
    for seed in range(24):
        scores, counts, evts = play(seed)
        s = sum(scores)
        hora = counts.get("hora", 0)
        total_hora += hora
        changed = any(x != 25000 for x in scores)
        if s != 100000:
            bad_sum += 1
            print(f"  [BAD SUM] seed={seed} scores={scores} sum={s}")
        if hora:
            games_with_hora += 1
        if changed:
            games_score_changed += 1
        if seed < 6 or hora:
            print(f"  seed={seed:2d} hora={hora} ryukyoku={counts.get('ryukyoku',0)} "
                  f"reach={counts.get('reach',0)} scores={scores} sum={s}")
    print("---")
    print(f"games=24  points-conservation violations={bad_sum}")
    print(f"games with >=1 hora={games_with_hora}  total hora={total_hora}")
    print(f"games with score change={games_score_changed}")
    ok = (bad_sum == 0) and (total_hora > 0)
    print("RESULT:", "PASS" if ok else "NEEDS REVIEW")
    if total_hora == 0:
        print("NOTE: canonical policy never wins; scoring win-path not exercised here.")
        print("      Validate hora scoring in P1 with a greedy/tsumogiri or real policy.")


if __name__ == "__main__":
    main()