"""Raw model probe: show error bodies + test thinking-disable for pace.
Usage: python scripts/probe_model_raw.py
"""
import json, sys, time, urllib.request, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from aimahjong.config import load_env
env = load_env(ROOT / ".env")
KEY = env["DASHSCOPE_API_KEY"]
BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MSG = [{"role": "user", "content": 'Reply only JSON: {"action_index":0,"reason":"test"}'}]


def call(model, extra=None, timeout=40):
    body = {"model": model, "messages": MSG, "temperature": 0.7}
    if extra:
        body.update(extra)
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read().decode())
        dt = time.time() - t0
        content = j["choices"][0]["message"].get("content", "")[:60]
        return f"OK {dt:.1f}s :: {content}"
    except urllib.error.HTTPError as e:
        return f"HTTP{e.code} {time.time()-t0:.1f}s :: {e.read().decode()[:200]}"
    except Exception as e:
        return f"ERR {time.time()-t0:.1f}s :: {e}"


for model in ["glm-5.3", "ZHIPU/GLM-5.3-Flash", "kimi-k3.1-pro", "MiniMax/MiniMax-M3",
              "glm-5.3-flash", "kimi-k3", "qwen3.8-flash"]:
    print(f"{model:24s} default   -> {call(model)}", flush=True)
print("--- thinking disabled ---", flush=True)
for model, extra in [("qwen3.8-max", {"enable_thinking": False}),
                     ("deepseek-v4.1-flash", {"enable_thinking": False}),
                     ("glm-5.3", {"enable_thinking": False}),
                     ("qwen3.8-flash", {"enable_thinking": False})]:
    print(f"{model:24s} nothink   -> {call(model, extra)}", flush=True)
