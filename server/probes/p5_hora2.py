"""P5 probe 2: HandEvaluator constructor + text helpers; compute a real hora's yaku/han/fu."""
import sys, json, inspect
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from riichienv import HandEvaluator, Conditions, convert

print("__init__:", inspect.signature(HandEvaluator.__init__))
for n in ("hand_from_text", "calc_from_text", "to_text"):
    fn = getattr(HandEvaluator, n)
    print(f"{n}:", inspect.signature(fn))
    print("   doc:", (inspect.getdoc(fn) or "")[:300])
print("Conditions members:", [m for m in dir(Conditions) if not m.startswith("_")])
try:
    print("Conditions.__init__:", inspect.signature(Conditions.__init__))
except Exception as e:
    print("Conditions sig err:", e)

# Try calc_from_text on a simple winning hand text (guess format from doc)
for txt in ["123456789m12355p", "1m2m3m4m5m6m7m8m9m1p2p3p5p5p"]:
    try:
        he = HandEvaluator.hand_from_text(txt)
        print(f"\nhand_from_text({txt!r}) ->", he, "to_text:", he.to_text())
    except Exception as e:
        print(f"hand_from_text({txt!r}) failed: {type(e).__name__}: {e}")