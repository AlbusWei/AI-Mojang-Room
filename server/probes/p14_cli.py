"""P14 probe: unified AI CLI (scripts/room.py) machine-readable paths.

Read-only against the running viewer server (configs/list/standings/state/watch)
plus an OFFLINE mock game written to a temp dir (proves `new --offline`).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
ROOM = ROOT / "scripts" / "room.py"


def room(*args):
    p = subprocess.run([str(PY), str(ROOM), "--json", *args], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def main():
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name + (" " + extra if extra else ""))
        ok = ok and cond

    rc, out, err = room("configs")
    cfg = json.loads(out) if rc == 0 else {}
    check("configs --json parses", rc == 0 and len(cfg.get("configs", [])) >= 4, f"n={len(cfg.get('configs', []))}")
    check("configs has live2026", any(c["id"] == "config/agents.live2026.json" for c in cfg.get("configs", [])))

    rc, out, err = room("standings")
    st = json.loads(out) if rc == 0 else {}
    check("standings --json parses", rc == 0 and "standings" in st, f"num_games={st.get('num_games')}")

    rc, out, err = room("list")
    ls = json.loads(out) if rc == 0 else {}
    check("list --json parses", rc == 0 and "games" in ls and "live" in ls)

    rc, out, err = room("watch", "--game", "live2026_1")
    w = json.loads(out) if rc == 0 else {}
    check("watch returns url", rc == 0 and "?live=live2026_1" in w.get("url", ""), w.get("url", ""))

    # offline mock game -> temp dir (does not touch runs/)
    tmp = tempfile.mkdtemp(prefix="p14_cli_")
    rc, out, err = room("new", "--config", "config/agents.mock.json", "--seed", "5",
                        "--offline", "--out", tmp)
    produced = (Path(tmp) / "game.mjai.jsonl").exists()
    check("new --offline writes log to temp", rc == 0 and produced, f"rc={rc}")

    print("P14 CLI:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
