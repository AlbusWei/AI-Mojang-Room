---
name: ai-mahjong-room
description: 操控本地「AI 麻将室」（日本立直麻将）：发起/观看多模型 AI 对局、读上帝视角局面与推理、跑锦标赛、出解说/配音样片/复盘/积分榜。当用户要开一局 AI 麻将、看 AI 打麻将直播、做麻将节目、比较模型麻将胜率、或作为主持人/解说员 Agent 掌控牌局时使用。
---

# AI 麻将室 · Agent 操作技能

本地工作区：项目根目录（下称 ROOT，即包含 `server/`、`web/`、`config/` 的目录）。
引擎 = RiichiEnv（Apache-2.0，规则裁判）；协议 = MJAI 事件流；每席一个 LLM Agent，
**只能看到自己手牌 + 场上明牌**，只能从引擎给出的合法动作里选（公平由引擎强制）。
上帝视角回放/直播 = 零依赖 Web viewer；解说 = facts-first + edge-tts。

## 0. 前置（每次会话先确认）
- Python venv：`ROOT\.venv\Scripts\python.exe`（已装 riichienv/playwright/edge-tts/imageio-ffmpeg/pillow）。
- 密钥：`ROOT\.env`（gitignored；含 DASHSCOPE/DEEPSEEK/BAILIAN_INVITE）。缺失时跑 `scripts\setup_env.py`。
- viewer server（live/state/standings 依赖）：默认 `http://127.0.0.1:18765`。
  未启动则：`.\.venv\Scripts\python.exe server\serve_viewer.py --port 18765`（后台）。
  **改过后端代码必须重启 server**（进程内存持旧模块）；若端口被旧进程占用，先清理残留 serve_viewer 进程。

## 1. 统一 CLI（首选，给 Agent 用）
所有子命令加 `--json` 得机器可读输出。入口 `scripts\room.py`：

```
room.py configs                          # 可用阵容(live)/锦标赛(tournament)配置
room.py new --config config/agents.live2026.json --seed 7 [--id mygame]   # 开实时直播局
room.py new --config ... --offline --out runs/x   # 离线跑完落盘(不直播)
room.py list                             # 直播列表 + 已落盘对局
room.py state --game <id> [--since N]    # 上帝视角: frames/seats/事件/解说/commentary
room.py watch --game <id>                # 观看 URL (?live=<id>)
room.py standings                        # 选手总榜(跨正式局聚合)
room.py games                            # 已落盘对局
room.py tournament --config config/tournament.show2026.json [--rounds N --rotations R]
room.py show --tournament runs/show --record     # 一键: 解说+复盘+积分榜+配音样片
room.py recap --game <id>                # 复盘 markdown
room.py commentary --game <id> --tts     # 解说 json/srt + mp3
room.py record --game <id> [--frame N --pace 1800 --max-seconds 80]   # WebM
```

## 2. HTTP API（viewer server，读局面/控直播）
- `GET /api/configs` 阵容元数据（无密钥）。
- `POST /api/live/start` body `{config, seed, game_id?, game_mode?, rule?}` → `{game_id, agents, url}`。config 必须在 ROOT 下。
- `GET /api/live/list`、`GET /api/live/state?game=&since=` → `{frames, n_frames, status, summary, commentary[]}`（增量）。
- `GET /api/games`、`GET /api/game/<id>/frames`、`GET /api/game/<id>/commentary`。
- `GET /api/standings`、`GET /api/profiles`、`GET /api/tournaments`、`GET /api/tournament/<id>`。
- `GET /commentary/<id>/<file>.mp3` 解说音频。

## 3. 作为主持人/解说员 Agent 的工作流
1. `configs` 选阵容 → `new` 开局 → 把 `watch` URL 给人类/OBS。
2. 轮询 `state --game <id>`（或 HTTP since 增量）读事件与各家推理；**解说只基于引擎事件 + Agent reason（facts-first），不要编造牌局事实**。
3. 局终：`standings` 读榜；`show --tournament <dir> --record` 出成片；`recap` 出图文复盘。
4. 人类界面：viewer 顶栏「🎮 新开一局」可选阵容/种子直接开局；「🏆 积分榜」看总榜与直播列表。

## 4. 规则与公平（不要绕过）
- 合法动作由引擎 `legal_actions()` 枚举；Agent 输出编号菜单索引，非法/超时→合法兜底并记录。
- 振听不能荣和；鸣牌窗口只摆合法选项；他家可见「有人可鸣」但不知具体。
- 复式锦标赛 = 同 seed 换座位（RiichiEnv seed 可复现）；积分 placement[4,3,2,1]。
- 和了役种/番符用 gated HandEvaluator 重建（点数对账不上则省略，绝不显示错役种）。

## 5. 合规 / 安全
- 牌面自绘 CC0；**不接雀魂/天鳳官方服务器**（ToS+版权）；严禁赌博用途。
- 头像为社区公认 AI 娘二创：DeepSeek 系 **CC BY-NC-SA（非商业）**；商业/收益直播改用 `web/avatars/orig_*` 或取得授权（见 config/profiles.json）。
- 密钥只放 `.env`，不入库、不打印。

## 6. 排障
- 模型卡住/超时：GLM 需 `extra_body.reasoning_effort:"low"`；kimi 需 `omit_temperature:true`；思考型模型直播设短 timeout+兜底。
- 端口 18765 被占：清理残留 serve_viewer 进程再重启。
- 测试：`scripts\run_tests.py`（16 项回归；产生 artifact 的探针写 temp，runs/ 只留真实局）。
