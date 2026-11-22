"""Discover available model IDs on each configured endpoint (Nov 2026 lineup).

Reads keys from .env (DASHSCOPE/DEEPSEEK) and ~/.dsh/.credentials.yaml (BAILIAN*).
GETs /v1/models on each endpoint and prints matching model ids. Never prints keys.
Usage: python scripts/list_models.py [filter_regex]
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from aimahjong.config import load_env  # noqa: E402

env = load_env(ROOT / ".env")
cred = Path.home() / ".dsh" / ".credentials.yaml"
ctext = cred.read_text(encoding="utf-8") if cred.exists() else ""


def ckey(name):
    m = re.search(rf"^\s*{name}:\s*(\S+)", ctext, re.M)
    return m.group(1).strip().strip("'\"") if m else None


ENDPOINTS = [
    ("dashscope", "https://dashscope.aliyuncs.com/compatible-mode/v1", env.get("DASHSCOPE_API_KEY")),
    ("deepseek", "https://api.deepseek.com/v1", env.get("DEEPSEEK_API_KEY")),
    ("token-plan", "https://token-plan.cn-beijing.maas.aliyuncs.com/v1", ckey("BAILIAN_API_KEY")),
    ("token-plan-invite", "https://token-plan.cn-beijing.maas.aliyuncs.com/v1", ckey("BAILIAN_INVITE_API_KEY")),
]

filt = re.compile(sys.argv[1], re.I) if len(sys.argv) > 1 else re.compile(
    r"qwen|deepseek|glm|kimi|moonshot|minimax|max|flash|latest|v4|v3|5\.|4\.", re.I)

for name, base, key in ENDPOINTS:
    if not key:
        print(f"\n### {name}: NO KEY")
        continue
    try:
        req = urllib.request.Request(base + "/models", headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read().decode("utf-8"))
        ids = [m.get("id") for m in j.get("data", [])]
        hit = sorted(i for i in ids if i and filt.search(i))
        print(f"\n### {name}: total={len(ids)} matched={len(hit)}")
        for i in hit:
            print("   ", i)
    except Exception as ex:
        print(f"\n### {name}: ERROR {ex}")
