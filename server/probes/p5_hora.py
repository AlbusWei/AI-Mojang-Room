"""P5 probe: introspect HandEvaluator + WinResult, test yaku/han/fu calc on a real hora.
Run:  .venv\\Scripts\\python.exe server\\probes\\p5_hora.py
"""
import sys, json, inspect
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from riichienv import HandEvaluator, WinResult, convert, parse_hand

print("HandEvaluator members:", [m for m in dir(HandEvaluator) if not m.startswith("_")])
print("WinResult members:", [m for m in dir(WinResult) if not m.startswith("_")])
for name in ("calc", "calculate", "is_tenpai", "get_waits", "yaku_list"):
    fn = getattr(HandEvaluator, name, None)
    if fn is not None:
        try:
            print(f"  {name}{inspect.signature(fn)}")
        except (ValueError, TypeError):
            print(f"  {name}: (signature unavailable)")

# Try a known winning hand: 123m 456m 789m 123p 55p (tsumo 5p), riichi, tsumo
# mpsz: 123456789m12355p  -> 14 tiles
try:
    tiles = convert.mpsz_to_tid_list("123456789m12355p")
    print("\ntest hand tids:", tiles, "len", len(tiles))
    he = HandEvaluator()
    for meth in ("calc", "calculate"):
        fn = getattr(he, meth, None)
        if fn is None:
            continue
        print(f"trying he.{meth} ...")
        try:
            res = fn(tiles)
            print("  result:", res)
            print("  attrs:", {a: getattr(res, a) for a in dir(res) if not a.startswith("_")})
        except Exception as e:
            print(f"  {meth}(tiles) failed: {type(e).__name__}: {e}")
except Exception as e:
    print("setup failed:", type(e).__name__, e)