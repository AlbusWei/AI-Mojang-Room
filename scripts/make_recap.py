"""Generate a markdown show recap from a finished game (god-view log + decisions).

Usage: python scripts/make_recap.py --game runs/show/<game_id> [--out recap.md]
Produces a节目复盘: final ranking, score story, hora highlights with yaku,
riichi moments, and per-agent behaviour stats (fallbacks / latency).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from aimahjong.replay import replay_mjai  # noqa: E402
from aimahjong.gameio import resolve_game_dir  # noqa: E402


def load_game(g: Path):
    ev = [json.loads(l) for l in (g / "game.mjai.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    dec = [json.loads(l) for l in (g / "decisions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    summary = json.loads((g / "summary.json").read_text(encoding="utf-8"))
    return ev, dec, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    g = resolve_game_dir(args.game)
    ev, dec, summary = load_game(g)
    frames = replay_mjai(ev, dec)
    agents = summary.get("agents", [f"seat{i}" for i in range(4)])
    scores = summary.get("scores", [0, 0, 0, 0])
    ranks = summary.get("ranks", [0, 0, 0, 0])

    # per-agent stats
    stats = {i: {"decisions": 0, "fallbacks": 0, "lat": [], "wins": 0} for i in range(4)}
    for d in dec:
        s = d["seat"]
        stats[s]["decisions"] += 1
        if d.get("fallback"):
            stats[s]["fallbacks"] += 1
        if d.get("latency_ms"):
            stats[s]["lat"].append(d["latency_ms"])
    horas = [f for f in frames if f.event.get("type") == "hora"]
    for f in horas:
        if f.win:
            stats[f.win["seat"]]["wins"] += 1
    riichi = [f for f in frames if f.event.get("type") == "reach_accepted"]

    order = sorted(range(4), key=lambda i: ranks[i])
    lines = []
    lines.append(f"# 🀄 AI 麻将室 · 节目复盘")
    lines.append("")
    lines.append(f"**对局**：`{summary.get('game_id', g.name)}` · 种子 {summary.get('seed')} · "
                 f"{summary.get('num_kyoku', '?')} 局 · {summary.get('num_events', '?')} 事件")
    lines.append("")
    lines.append("## 🏆 终局排名")
    lines.append("")
    lines.append("| 名次 | 选手 | 终分 | 和了 | 兜底 | 平均决策延迟 |")
    lines.append("|---|---|---|---|---|---|")
    medal = {1: "🥇", 2: "🥈", 3: "🥉", 4: "4"}
    for i in order:
        st = stats[i]
        avg = f"{sum(st['lat'])/len(st['lat']):.0f}ms" if st["lat"] else "—"
        lines.append(f"| {medal.get(ranks[i], ranks[i])} | {agents[i]} | {scores[i]} | "
                     f"{st['wins']} | {st['fallbacks']} | {avg} |")
    lines.append("")
    lines.append("## ✨ 和了高光")
    lines.append("")
    if horas:
        for f in horas:
            w = f.win
            ky = f"東{f.kyoku}局" if f.bakaze == "E" else f"南{f.kyoku}局"
            if w:
                how = "自摸" if w["tsumo"] else "荣和"
                sc = "役满" if w["yakuman"] else f"{w['han']}番{w['fu']}符"
                yaku = " / ".join(w["yaku"])
                lines.append(f"- **{ky} {f.honba}本場** · {agents[w['seat']]} {how} "
                             f"**{sc} · {w['points']}点** — {yaku}")
            else:
                a = f.event["actor"]
                lines.append(f"- **{ky} {f.honba}本場** · {agents[a]} 和了 "
                             f"{f.event.get('deltas', [0]*4)[a]}点")
    else:
        lines.append("- 本局无人和了（全部流局）。")
    lines.append("")
    lines.append(f"## 📊 对局概况")
    lines.append("")
    lines.append(f"- 立直次数：{len(riichi)}")
    lines.append(f"- 和了：{summary.get('hora_count', len(horas))} · 流局：{summary.get('ryukyoku_count', '?')}")
    lines.append(f"- 总决策：{len(dec)} · 总兜底：{summary.get('fallback_count', 0)}")
    tot_lat = summary.get("total_latency_ms", 0)
    lines.append(f"- 累计模型耗时：{tot_lat/1000:.1f}s")
    lines.append("")
    lines.append("## 🎬 回放")
    lines.append("")
    lines.append(f"上帝视角回放：`http://127.0.0.1:18765/?game={g.name}&autoplay=1&pace=2500`")
    lines.append("")
    lines.append("> 复盘由引擎权威事件 + 各 Agent 真实推理自动生成（facts-first，无幻觉）。")
    lines.append("")

    out = Path(args.out) if args.out else (g / "recap.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"recap written: {out}")
    print("\n".join(lines[:24]))


if __name__ == "__main__":
    main()