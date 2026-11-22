"""Inspect local credential configs with secrets REDACTED (never prints full keys).
Reports which providers/keys exist so we can wire a real model into .env.
"""
import json, re, os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

def redact(s):
    if not isinstance(s, str):
        return s
    # mask anything key-like
    s = re.sub(r"(sk-[A-Za-z0-9_\-]{6})[A-Za-z0-9_\-]+([A-Za-z0-9]{4})", r"\1…\2", s)
    s = re.sub(r"([A-Za-z0-9_\-]{24,})", lambda m: m.group(1)[:6] + "…[redacted]", s)
    return s

print("=== ~/.bailian/config.json ===")
p = HOME / ".bailian" / "config.json"
if p.exists():
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
        def walk(o, pre=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    if isinstance(v, (dict, list)):
                        print(f"{pre}{k}:")
                        walk(v, pre + "  ")
                    else:
                        print(f"{pre}{k} = {redact(v)}")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    print(f"{pre}[{i}]")
                    walk(v, pre + "  ")
        walk(c)
    except Exception as e:
        print("parse err:", e)
else:
    print("(missing)")

print("\n=== ~/.dsh/.credentials.yaml (redacted lines) ===")
p = HOME / ".dsh" / ".credentials.yaml"
if p.exists():
    for line in p.read_text(encoding="utf-8").splitlines():
        if re.search(r"key|token|secret|provider|base_?url|dashscope|openai|model|name|channel", line, re.I):
            print(redact(line))
else:
    print("(missing)")