"""Unified regression / test round for AI 麻将室.

Runs the phase probes in order and aggregates PASS/FAIL. Probes that produce
game artifacts write to temp dirs (runs/ stays clean, only real games live there).
Server-dependent probes (p9_ui / p10_check) are SKIPped if the viewer server is
not reachable on :18765 (start it with server/serve_viewer.py).

Usage:
    .venv\\Scripts\\python.exe scripts\\run_tests.py [--fast]
      --fast  skip the slower tournament / yaku / UI probes
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
PROBES = ROOT / "server" / "probes"
BASE = "http://127.0.0.1:18765"

# (probe file, needs_server, slow)
SUITE = [
    ("p0_determinism.py", False, False),
    ("p0_obs_fairness.py", False, False),
    ("p0_scoring.py", False, False),
    ("p0_selfplay.py", False, False),
    ("p1_fallback.py", False, False),
    ("p2_replay.py", False, False),
    ("p3_tournament.py", False, True),
    ("p5_yaku_verify.py", False, True),
    ("p6_badge.py", False, False),
    ("p7_live.py", False, False),
    ("p9_accept.py", False, False),
    ("p9_ui.py", True, True),
    ("p10_check.py", True, False),
    ("p14_cli.py", True, False),
    ("p14_ui.py", False, True),
    ("p15_roster.py", False, True),
]


def server_up() -> bool:
    try:
        with urllib.request.urlopen(BASE + "/api/games", timeout=5) as r:
            r.read()
        return True
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    args = ap.parse_args()
    up = server_up()
    results = []
    for name, needs_server, slow in SUITE:
        if args.fast and slow:
            results.append((name, "SKIP", "fast mode"))
            continue
        if needs_server and not up:
            results.append((name, "SKIP", "server not on :18765"))
            continue
        print(f"\n=== {name} ===", flush=True)
        p = subprocess.run([str(PY), str(PROBES / name)], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=600)
        tail = (p.stdout or p.stderr or "").strip().splitlines()
        last = tail[-1] if tail else ""
        status = "PASS" if p.returncode == 0 else "FAIL"
        results.append((name, status, last))
        # echo a compact tail for visibility
        for line in tail[-4:]:
            print("   " + line, flush=True)
    print("\n================ TEST ROUND SUMMARY ================")
    npass = nfail = nskip = 0
    for name, status, note in results:
        print(f"{status:4}  {name:22} {note[:90]}")
        npass += status == "PASS"
        nfail += status == "FAIL"
        nskip += status == "SKIP"
    print(f"----------------------------------------------------")
    print(f"PASS={npass} FAIL={nfail} SKIP={nskip}")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
