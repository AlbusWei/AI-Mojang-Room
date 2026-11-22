"""P0 probe: 4 random/legal agents self-play a full hanchan on RiichiEnv.

Verifies: engine runs to completion, scores/ranks sane, MJAI log exportable.
Run:  .venv\\Scripts\\python.exe server\\probes\\p0_selfplay.py
"""
from __future__ import annotations
import json, random, sys, pathlib, tempfile

from riichienv import RiichiEnv, GameRule

# Test artifacts go to a temp dir so runs/ stays clean (only real games).
OUT = pathlib.Path(tempfile.mkdtemp(prefix="p0_selfplay_"))


def pick(o, rng):
    """Choose a legal action; tolerate Action objects or mjai strings."""
    legal = o.legal_actions()
    if not legal:
        return None
    a = rng.choice(legal)
    if isinstance(a, str):
        a = o.select_action_from_mjai(a)
    return a


def run(seed=42, policy_seed=0, max_steps=4000, verbose=True):
    rng = random.Random(policy_seed)
    env = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=seed)
    env.reset()
    steps = 0
    while not env.done() and steps < max_steps:
        obs = env.get_observations()
        actions = {}
        for pid, o in obs.items():
            a = pick(o, rng)
            if a is None:
                continue  # seat not acting this phase (normal); only acting seats get actions
            actions[pid] = a
        if not actions:
            if verbose:
                print(f"[stall] no seat has a legal action at step={steps}; stopping")
            break
        env.step(actions)
        steps += 1
    return env, steps


def main():
    env, steps = run()
    print("=== P0 selfplay ===")
    print("done:", env.done(), "steps:", steps)
    try:
        print("scores:", env.scores())
        print("ranks:", env.ranks())
    except Exception as e:
        print("scores/ranks error:", e)

    log = env.mjai_log
    print("mjai_log type:", type(log).__name__)
    # Normalize to list of event dicts
    events = []
    if isinstance(log, str):
        for line in log.splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
    else:
        for e in log:
            if isinstance(e, str):
                events.append(json.loads(e))
            elif isinstance(e, dict):
                events.append(e)
            else:
                # maybe objects with to_dict / to_mjai
                if hasattr(e, "to_dict"):
                    events.append(e.to_dict())
                else:
                    events.append(json.loads(str(e)))
    print("num events:", len(events))
    if events:
        print("first event:", json.dumps(events[0], ensure_ascii=False)[:300])
        print("last event:", json.dumps(events[-1], ensure_ascii=False)[:300])
        tags = {}
        for e in events:
            t = e.get("type", "?")
            tags[t] = tags.get(t, 0) + 1
        print("event type counts:", tags)

    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "selfplay_seed42.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print("wrote:", p)


if __name__ == "__main__":
    main()