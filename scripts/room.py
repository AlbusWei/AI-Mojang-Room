"""AI 麻将室 · 统一控制 CLI（给 AI Agent / 主持人 / 解说员用）。

一个入口掌控整个麻将室：发起对局、查看局面、出节目。所有子命令支持 --json
输出机器可读结果，便于 Agent 解析；人类也可直接读默认文本输出。

典型 Agent 工作流（主持/解说）：
    room.py configs                      # 看可用阵容
    room.py new --config config/agents.live2026.json --seed 7   # 开一局直播
    room.py state --game <id>            # 读当前局面/事件/解说（上帝视角 JSON）
    room.py watch --game <id>            # 拿观看 URL（人类/OBS）
    room.py standings                    # 读选手总榜
    room.py show --tournament <dir> --record   # 一键出解说+配音样片+复盘+积分榜

离线（不直播、跑完落盘）：
    room.py new --config ... --offline --out runs/mygame

依赖：viewer server 运行中（live/state/list/standings 走 HTTP :18765）。
离线 new / tournament / show / recap / commentary / record 直接调本地脚本。
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
BASE = "http://127.0.0.1:18765"


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.load(r)


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _run(script, *args):
    path = ROOT / "scripts" / script
    if not path.exists():
        path = ROOT / "server" / script
    p = subprocess.run([str(PY), str(path), *args], cwd=str(ROOT))
    return p.returncode


def emit(obj, as_json, text=None):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False))
    elif text is not None:
        print(text)
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    global BASE
    ap = argparse.ArgumentParser(description="AI 麻将室统一控制 CLI")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--base", default=BASE)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("configs", help="列出可用阵容/锦标赛配置")
    sub.add_parser("roster", help="选手库（角色+模型绑定）列表")
    p = sub.add_parser("roster-del", help="删除选手")
    p.add_argument("--id", required=True)
    p = sub.add_parser("new", help="发起新对局（默认实时直播）")
    p.add_argument("--config", default="config/agents.live2026.json")
    p.add_argument("--seats", default=None, help="逗号分隔 4 个 roster id，逐席选人（覆盖 --config）")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--id", default=None)
    p.add_argument("--offline", action="store_true", help="不直播，跑完落盘")
    p.add_argument("--out", default=None)
    sub.add_parser("list", help="直播列表 + 已落盘对局")
    p = sub.add_parser("state", help="读某局当前局面/事件/解说（上帝视角）")
    p.add_argument("--game", required=True)
    p.add_argument("--since", type=int, default=0)
    p = sub.add_parser("watch", help="打印某局观看 URL")
    p.add_argument("--game", required=True)
    sub.add_parser("standings", help="选手总榜")
    sub.add_parser("games", help="已落盘对局列表")
    p = sub.add_parser("tournament", help="跑锦标赛（离线）")
    p.add_argument("--config", default="config/tournament.show2026.json")
    p.add_argument("--out", default=None)
    p.add_argument("--rounds", type=int, default=None)
    p.add_argument("--rotations", type=int, default=None)
    p.add_argument("--seed-start", type=int, default=None)
    p = sub.add_parser("show", help="一键节目：解说+复盘+积分榜(+配音样片)")
    p.add_argument("--tournament", default=None)
    p.add_argument("--game", default=None)
    p.add_argument("--record", action="store_true")
    p.add_argument("--no-tts", action="store_true")
    p = sub.add_parser("recap", help="生成某局复盘 markdown")
    p.add_argument("--game", required=True)
    p.add_argument("--out", default=None)
    p = sub.add_parser("commentary", help="生成某局解说(+TTS)")
    p.add_argument("--game", required=True)
    p.add_argument("--tts", action="store_true")
    p = sub.add_parser("record", help="录制某局回放为 WebM")
    p.add_argument("--game", required=True)
    p.add_argument("--frame", type=int, default=None)
    p.add_argument("--pace", type=int, default=1800)
    p.add_argument("--max-seconds", type=int, default=80)

    a = ap.parse_args()
    BASE = a.base

    if a.cmd == "configs":
        d = _get("/api/configs")
        emit(d, a.json, "\n".join(f"{c['id']}  [{c['kind']}]  " + " / ".join(s["name"] for s in c["seats"]) for c in d["configs"]))
    elif a.cmd == "roster":
        d = _get("/api/roster")
        emit(d, a.json, "\n".join(f"{p['id']:28s} {p.get('type','?'):6s} {p.get('model','-'):32s} {p.get('display','')}" for p in d["players"]))
    elif a.cmd == "roster-del":
        req = urllib.request.Request(BASE + f"/api/roster/{a.id}", method="DELETE")
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        emit(d, a.json, f"deleted {a.id}")
    elif a.cmd == "new":
        seats = [s.strip() for s in a.seats.split(",")] if a.seats else None
        if a.offline:
            cfg_path = a.config
            if seats:
                sys.path.insert(0, str(ROOT / "server"))
                from aimahjong import roster as rmod
                import tempfile
                specs = rmod.resolve_seats(rmod.load_roster(), seats)
                tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
                json.dump({"seats": specs}, tf, ensure_ascii=False)
                tf.close()
                cfg_path = tf.name
            args = ["--config", cfg_path, "--seed", str(a.seed)]
            if a.out:
                args += ["--out", a.out]
            rc = _run("run_game.py", *args)
            emit({"offline": True, "config": cfg_path, "seats": seats, "seed": a.seed, "returncode": rc}, a.json)
            return rc
        body = {"seed": a.seed}
        if seats:
            body["seats"] = seats
        else:
            body["config"] = a.config
        if a.id:
            body["game_id"] = a.id
        d = _post("/api/live/start", body)
        if "error" in d:
            emit(d, a.json, "ERROR: " + d["error"])
            return 1
        d["watch"] = BASE + d["url"]
        emit(d, a.json, f"live: {d['game_id']}\nagents: {', '.join(d['agents'])}\nwatch: {d['watch']}")
    elif a.cmd == "list":
        live = _get("/api/live/list")["games"]
        games = _get("/api/games")["games"]
        emit({"live": live, "games": games}, a.json,
             "LIVE:\n" + "\n".join(f"  {g['game_id']} [{g['status']}]" for g in live) +
             "\nGAMES:\n" + "\n".join(f"  {g['id']}" for g in games))
    elif a.cmd == "state":
        d = _get(f"/api/live/state?game={a.game}&since={a.since}")
        emit(d, a.json, f"{a.game} [{d.get('status')}] frames={d.get('n_frames')} commentary={len(d.get('commentary', []))}")
    elif a.cmd == "watch":
        emit({"game": a.game, "url": f"{BASE}/?live={a.game}"}, a.json, f"{BASE}/?live={a.game}")
    elif a.cmd == "standings":
        d = _get("/api/standings")
        emit(d, a.json, "\n".join(f"#{i+1} {s['name']}  pts={s['points']} games={s['games']} avg_rank={s['avg_rank']}" for i, s in enumerate(d["standings"])))
    elif a.cmd == "games":
        d = _get("/api/games")
        emit(d, a.json, "\n".join(g["id"] for g in d["games"]))
    elif a.cmd == "tournament":
        args = ["--config", a.config]
        if a.out:
            args += ["--out", a.out]
        if a.rounds is not None:
            args += ["--rounds", str(a.rounds)]
        if a.rotations is not None:
            args += ["--rotations", str(a.rotations)]
        if a.seed_start is not None:
            args += ["--seed-start", str(a.seed_start)]
        return _run("run_tournament.py", *args)
    elif a.cmd == "show":
        args = []
        if a.tournament:
            args += ["--tournament", a.tournament]
        if a.game:
            args += ["--game", a.game]
        if a.record:
            args += ["--record"]
        if a.no_tts:
            args += ["--no-tts"]
        return _run("make_show.py", *args)
    elif a.cmd == "recap":
        args = ["--game", a.game]
        if a.out:
            args += ["--out", a.out]
        return _run("make_recap.py", *args)
    elif a.cmd == "commentary":
        args = ["--game", a.game]
        if a.tts:
            args += ["--tts"]
        return _run("make_commentary.py", *args)
    elif a.cmd == "record":
        args = ["--game", a.game, "--pace", str(a.pace), "--max-seconds", str(a.max_seconds)]
        if a.frame is not None:
            args += ["--frame", str(a.frame)]
        return _run("record_game.py", *args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
