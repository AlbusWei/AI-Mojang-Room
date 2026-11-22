"""P8 audit: scan every recorded game for process/quality problems.

Reconstructs the EXACT legal-action menu at each decision by replaying the
authoritative MJAI log through a fresh RiichiEnv (apply_event) and reading
get_observations() at the decision point (event_pos == len(log) before the
decision's event is appended). This lets us detect, per decision:
  - missed win: menu offered tsumo/ron but the agent chose something else
  - wasted call: menu had exactly 1 legal option (engine-forced) yet we paid an LLM call
  - illegal pick: chosen mjai not in the menu (should be 0; validation guards it)
Plus log-level stats: fallbacks, parse errors, latency distribution, sequential
response-phase waste, riichi/hora counts, score conservation, tokens.

Usage: python server/probes/p8_audit.py [runs_root]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from riichienv import RiichiEnv, GameRule  # noqa: E402


def load(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def audit_game(d: Path):
    ev = load(d / "game.mjai.jsonl")
    dec = load(d / "decisions.jsonl")
    by_pos = defaultdict(list)
    for x in dec:
        by_pos[x["event_pos"]].append(x)
    out = {"game": d.name, "decisions": len(dec), "events": len(ev)}
    lat = [x["latency_ms"] for x in dec if x["latency_ms"]]
    lat.sort()
    out["fallback"] = sum(1 for x in dec if x["fallback"])
    out["errors"] = sum(1 for x in dec if x.get("error"))
    if lat:
        out["lat_mean"] = round(sum(lat) / len(lat))
        out["lat_p95"] = lat[int(len(lat) * 0.95)]
        out["lat_max"] = lat[-1]
    out["tokens"] = sum((x.get("tokens") or {}).get("total_tokens", 0) for x in dec)
    types = [e.get("type") for e in ev]
    out["hora"] = types.count("hora")
    out["reach"] = types.count("reach_accepted")
    out["ryukyoku"] = types.count("ryukyoku")
    # score conservation: hora deltas include the riichi-stick pot (kyotaku*1000
    # enters from the pot, not from players); ryukyoku deltas must sum to 0.
    bad = 0
    kyotaku = 0
    for e in ev:
        t = e.get("type")
        if t == "start_kyoku":
            kyotaku = e.get("kyotaku", 0)
        elif t == "reach_accepted":
            kyotaku += 1
        elif t in ("hora", "ryukyoku") and "deltas" in e:
            expected = kyotaku * 1000 if t == "hora" else 0
            if sum(e["deltas"]) != expected:
                bad += 1
            if t == "hora":
                kyotaku = 0
    out["delta_nonzero"] = bad
    sj = d / "summary.json"
    out["final_sum"] = sum(json.loads(sj.read_text(encoding="utf-8"))["scores"]) if sj.exists() else None

    # reconstruct legal menus
    env = RiichiEnv(game_mode="4p-red-half", rule=GameRule.default_tenhou(), seed=0)
    env.reset()
    missed = []
    single = 0
    illegal = 0
    resp_waste = 0
    recon_ok = True
    for i, e in enumerate(ev):
        ds = by_pos.get(i, [])
        if ds:
            try:
                obs = env.get_observations()
            except Exception:
                recon_ok = False
                obs = {}
            menus = {}
            for pid, o in obs.items():
                la = o.legal_actions()
                if la:
                    menus[pid] = [a.to_mjai() for a in la]
            if len(ds) > 1:
                resp_waste += sum(x["latency_ms"] for x in ds) - max(x["latency_ms"] for x in ds)
            for x in ds:
                menu = menus.get(x["seat"], [])
                mj = [json.loads(m) if isinstance(m, str) else m for m in menu]
                tset = {m.get("type") for m in mj}
                chosen = json.loads(x["mjai"]) if isinstance(x["mjai"], str) else x["mjai"]
                if menu and x["mjai"] not in menu:
                    illegal += 1
                if len(menu) == 1:
                    single += 1
                win_opts = tset & {"tsumo", "ron"}
                if win_opts and chosen.get("type") not in win_opts:
                    missed.append({"pos": i, "seat": x["seat"], "name": x["name"],
                                   "offered": sorted(win_opts), "chose": chosen.get("type"),
                                   "reason": (x.get("reason") or "")[:80]})
        try:
            env.apply_event(e)
        except Exception:
            recon_ok = False
    out["recon_ok"] = recon_ok
    out["missed_wins"] = missed
    out["single_option_calls"] = single
    out["illegal_picks"] = illegal
    out["resp_seq_waste_ms"] = round(resp_waste)
    return out


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "runs"
    dirs = sorted(p.parent for p in root.rglob("game.mjai.jsonl"))
    tot_missed = tot_single = tot_illegal = tot_fb = tot_err = 0
    tot_waste = 0
    for d in dirs:
        try:
            a = audit_game(d)
        except Exception as ex:
            print(f"[SKIP] {d.name}: {ex}")
            continue
        tot_missed += len(a["missed_wins"]); tot_single += a["single_option_calls"]
        tot_illegal += a["illegal_picks"]; tot_fb += a["fallback"]; tot_err += a["errors"]
        tot_waste += a["resp_seq_waste_ms"]
        print(f"\n== {a['game']}  dec={a['decisions']} hora={a['hora']} reach={a['reach']} "
              f"fb={a['fallback']} err={a['errors']} lat(mean/p95/max)="
              f"{a.get('lat_mean')}/{a.get('lat_p95')}/{a.get('lat_max')}ms "
              f"single={a['single_option_calls']} illegal={a['illegal_picks']} "
              f"respWaste={a['resp_seq_waste_ms']}ms recon={a['recon_ok']} "
              f"deltaBad={a['delta_nonzero']} finalSum={a['final_sum']}")
        for m in a["missed_wins"][:6]:
            print(f"   MISSED-WIN pos={m['pos']} seat={m['seat']} {m['name']} "
                  f"offered={m['offered']} chose={m['chose']} :: {m['reason']}")
    print(f"\nTOTAL missed_wins={tot_missed} single_option_calls={tot_single} "
          f"illegal={tot_illegal} fallback={tot_fb} errors={tot_err} "
          f"resp_seq_waste={tot_waste/1000:.1f}s")


if __name__ == "__main__":
    main()
