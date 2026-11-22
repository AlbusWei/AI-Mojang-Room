"""Populate project .env from the user's local DSH credentials (secrets never printed).
Extracts DASHSCOPE_API_KEY + DEEPSEEK_API_KEY + BAILIAN_INVITE_API_KEY
from ~/.dsh/.credentials.yaml. BAILIAN_INVITE_API_KEY (sk-ws-…) is for the
qweneval invite-test platform (Qwen4 Max qwen-latest-series-invite-1102).
"""
import os, re
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
ROOT = Path(__file__).resolve().parent.parent
src = HOME / ".dsh" / ".credentials.yaml"
text = src.read_text(encoding="utf-8")

def grab(name):
    m = re.search(rf"^\s*{name}:\s*(\S+)", text, re.M)
    return m.group(1).strip().strip('"').strip("'") if m else None

keys = {}
for name in ("DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY", "BAILIAN_INVITE_API_KEY"):
    v = grab(name)
    if v:
        keys[name] = v

env_path = ROOT / ".env"
lines = ["# Auto-generated from local DSH credentials. Gitignored — do not commit."]
for name, v in keys.items():
    lines.append(f"{name}={v}")
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("wrote", env_path)
for name, v in keys.items():
    print(f"  {name} = {v[:7]}…{v[-4:]} (len {len(v)})")
if not keys:
    print("WARNING: no keys found")