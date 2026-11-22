"""Verify gated yaku reconstruction match rate (ron + tsumo) across games."""
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, "server")
from aimahjong.replay import replay_mjai
from aimahjong.room import Room
from aimahjong.agents import RandomAgent

def check(events, decisions, label):
    fr = replay_mjai(events, decisions)
    hora = [f for f in fr if f.event.get("type") == "hora"]
    shown = [f for f in hora if f.win]
    print(f"{label}: {len(shown)}/{len(hora)} hora show yaku")
    for f in shown:
        w = f.win
        print(f"   pos{f.index} seat{w['seat']} {'tsumo' if w['tsumo'] else 'ron'} "
              f"{w['han']}han{w['fu']}fu pts{w['points']} {w['yaku']}")
    return len(shown), len(hora)

# real game (2 ron)
g = Path("server/probes/fixtures/p1_real_full")
ev = [json.loads(l) for l in (g / "game.mjai.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
dec = [json.loads(l) for l in (g / "decisions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
ts, th = check(ev, dec, "p1_real_full")

# random games for tsumo coverage
tot_s = tot_h = 0
out = Path(tempfile.mkdtemp(prefix="p5_yaku_"))
for seed in range(1, 51):
    agents = [RandomAgent(f"R{i}", seed=seed * 10 + i) for i in range(4)]
    r = Room(agents, seed=seed, out_dir=out, game_id="yv").run()
    if r.hora_count:
        e2 = [json.loads(l) for l in (out / "game.mjai.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        d2 = [json.loads(l) for l in (out / "decisions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        s, h = check(e2, d2, f"random seed{seed}")
        tot_s += s; tot_h += h
print(f"\nTOTAL random: {tot_s}/{tot_h} hora show yaku; real {ts}/{th}")