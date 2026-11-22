/* AI 麻将室 · 上帝视角 viewer (replay + live). Self-contained, no deps.
 * P11: fixed-geometry Majsoul-like board. Regions never reflow; meld trays and
 * rivers are always present; riichi discards render sideways + stick + callout;
 * large avatars sit in the four corners. */
(function () {
  const $ = (id) => document.getElementById(id);
  const els = {
    sel: $("gameSel"), liveBadge: $("liveBadge"), liveText: $("liveText"), status: $("status"),
    board: $("board"), table: $("table"), center: $("center"), overlay: $("overlay"), reasoning: $("reasoning"),
    rivers: [$("river0"), $("river1"), $("river2"), $("river3")],
    hands: [$("hand0"), $("hand1"), $("hand2"), $("hand3")],
    meldTrays: [$("meld0"), $("meld1"), $("meld2"), $("meld3")],
    idents: [$("id0"), $("id1"), $("id2"), $("id3")],
    restart: $("restartBtn"), prev: $("prevBtn"), play: $("playBtn"), next: $("nextBtn"),
    scrub: $("scrub"), speed: $("speed"), counter: $("counter"),
    hideHands: $("hideHands"), sound: $("soundToggle"), comm: $("commToggle"), subtitle: $("subtitle"),
    newGameBtn: $("newGameBtn"), modal: $("newGameModal"), ngClose: $("ngClose"),
    ngConfig: $("ngConfig"), ngSeats: $("ngSeats"), ngSeed: $("ngSeed"), ngId: $("ngId"),
    ngError: $("ngError"), ngStart: $("ngStart"), ngLiveList: $("ngLiveList"),
  };
  const WIND = ["東", "南", "西", "北"];
  const SEAT_COLORS = ["#f0c04a", "#5ab0f0", "#4ad0a0", "#f07ab0"];
  const pdot = (seat) => `<span class="pdot" style="background:${SEAT_COLORS[seat]};color:${SEAT_COLORS[seat]}"></span>`;
  let PROFILES = {};
  let BRAND_ALIASES = {};
  async function loadProfiles() {
    try { const r = await fetch("/api/profiles"); const d = await r.json(); PROFILES = d.players || {}; BRAND_ALIASES = d.brand_aliases || {}; } catch (e) { PROFILES = {}; BRAND_ALIASES = {}; }
  }
  function profileFor(name) {
    const n = String(name || "");
    if (PROFILES[n]) return PROFILES[n];
    const low = n.toLowerCase();
    let brand = null, bestLen = 0;
    for (const [prefix, b] of Object.entries(BRAND_ALIASES)) {
      if (low.startsWith(prefix) && prefix.length > bestLen) { brand = b; bestLen = prefix.length; }
    }
    if (brand) for (const p of Object.values(PROFILES)) if (p && p.brand === brand) return p;
    return null;
  }
  function avatar(seat, size) {
    const name = S.agents[seat] || "";
    const p = profileFor(name);
    if (p && p.avatar) return `<img class="avatar" style="width:${size}px;height:${size}px" src="${esc(p.avatar)}" alt="">`;
    return pdot(seat);
  }
  const S = {
    frames: [], agents: [], latest: [], idx: 0, playing: false, timer: null,
    live: false, liveId: null, liveSince: 0, liveStatus: null, follow: true, pollTimer: null,
    paceMs: 2500, bannerPauseMs: 3000, loop: false, autoplay: false,
    hideHands: false, soundOn: true, commOn: true,
    commByPos: new Map(), playedComm: new Set(), audioPlayed: new Set(), subTimer: null,
    gameId: null,
  };
  const BANNER = new Set(["hora", "ryukyoku", "end_game"]);
  const params = new URLSearchParams(location.search);

  function seatWind(seat, oya) { return WIND[(seat - oya + 4) % 4]; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  /* ---------- fixed-board scaling ---------- */
  function fitBoard() {
    const t = els.table;
    const s = Math.min(t.clientWidth / 1500, t.clientHeight / 940);
    els.board.style.transform = `translate(-50%, -50%) scale(${s})`;
  }
  window.addEventListener("resize", fitBoard);

  /* ---------- rendering ---------- */
  function handHTML(seat, fr) {
    const st = fr.seats[seat];
    // Uniform upright tiles; the seat's CSS rotation (0/-90/180/90) orients them.
    const w = 40, h = 56;
    const concealed = [...st.hand];
    if (st.drawn) { const i = concealed.indexOf(st.drawn); if (i >= 0) concealed.splice(i, 1); }
    let html = "";
    for (let i = 0; i < 13; i++) {
      const t = concealed[i];
      html += t ? `<span class="slot">${Tiles.tileSVG(t, { w, h, down: S.hideHands })}</span>`
                : `<span class="slot empty">${Tiles.tileSVG("1m", { w, h })}</span>`;
    }
    html += st.drawn
      ? `<span class="slot drawn-slot">${Tiles.tileSVG(st.drawn, { w, h, down: S.hideHands, highlight: !S.hideHands })}</span>`
      : `<span class="slot drawn-slot empty">${Tiles.tileSVG("1m", { w, h })}</span>`;
    return html;
  }
  function meldsHTML(seat, fr) {
    const st = fr.seats[seat];
    let html = "";
    for (let i = 0; i < 4; i++) {
      const m = st.melds && st.melds[i];
      if (!m) { html += `<span class="meld empty" style="width:86px;height:28px"></span>`; continue; }
      let g = "";
      const tiles = m.tiles || [];
      tiles.forEach((t, j) => {
        const down = m.type === "ankan" && (j === 0 || j === tiles.length - 1);
        const rot = m.called_tile && t === m.called_tile && m.type !== "ankan";
        g += Tiles.tileSVG(t, { w: 20, h: 28, down, rot });
      });
      html += `<span class="meld">${g}</span>`;
    }
    return html;
  }
  function riverHTML(seat, fr) {
    const st = fr.seats[seat];
    let html = "";
    for (let i = 0; i < 24; i++) {
      const d = st.discards[i];
      if (!d) { html += `<span class="cell"></span>`; continue; }
      html += `<span class="cell">${Tiles.tileSVG(d.pai, { w: 30, h: 42, dim: d.called, rot: !!d.riichi })}</span>`;
    }
    return html;
  }
  function badgesHTML(seat, fr, call) {
    const st = fr.seats[seat];
    let b = "";
    if (fr.win && fr.win.seat === seat) b += `<span class="badge win">和了</span>`;
    if (st.riichi) b += `<span class="badge riichi">${st.double_riichi ? "双立直" : "立直"}</span>`;
    else if (st.shanten === 0) b += `<span class="badge tenpai">听牌</span>`;
    else if (st.shanten > 0 && st.shanten <= 6) b += `<span class="badge shanten">${st.shanten}向听</span>`;
    if (st.furiten) b += `<span class="badge furiten">振听</span>`;
    if (call && call.caller === seat) b += `<span class="badge call">可鸣牌</span>`;
    const ev = fr.event || {};
    if (ev.actor === seat && ["chi", "pon", "daiminkan", "ankan", "kakan"].includes(ev.type)) b += `<span class="badge call">鸣牌</span>`;
    return b;
  }
  function renderIdentity(seat, fr, call) {
    const st = fr.seats[seat];
    const actor = fr.event && fr.event.actor === seat;
    const el = els.idents[seat];
    el.classList.toggle("actor", !!actor);
    const dealer = fr.oya === seat ? `<span class="dealer">庄</span>` : "";
    el.innerHTML =
      avatar(seat, 56) +
      `<div class="meta"><div class="row1"><span class="wind">${seatWind(seat, fr.oya)}</span>${dealer}` +
      `<span class="score">${st.score}</span></div>` +
      `<div class="name">${esc(S.agents[seat] || ("seat" + seat))}</div>` +
      `<div class="badges">${badgesHTML(seat, fr, call)}</div></div>`;
  }
  function renderHand(seat, fr) { els.hands[seat].innerHTML = handHTML(seat, fr); }
  function renderMelds(seat, fr) { els.meldTrays[seat].querySelector(".melds").innerHTML = meldsHTML(seat, fr); }
  function renderRiver(seat, fr) { els.rivers[seat].innerHTML = riverHTML(seat, fr); }

  /* Call (chi/pon/kan/ron) opportunity window derived from the event stream. */
  function callInfo(fr) {
    const ev = fr.event || {};
    if (ev.type !== "dahai") return null;
    const nxt = S.frames[S.idx + 1];
    const ne = nxt && nxt.event;
    if (!ne || !["chi", "pon", "daiminkan", "ron"].includes(ne.type)) return null;
    const caller = ne.actor, discarder = ev.actor, pai = ev.pai;
    const base = (c) => (c.endsWith("r") ? c.slice(0, -1) : c);
    const hand = fr.seats[caller].hand || [];
    const cnt = (b) => hand.filter((c) => base(c) === b).length;
    const opts = [];
    if (ne.type === "ron") opts.push({ type: "ron", label: "荣和" });
    if (cnt(base(pai)) >= 2) opts.push({ type: "pon", label: "碰" });
    if (cnt(base(pai)) >= 3) opts.push({ type: "daiminkan", label: "大明杠" });
    if (caller === (discarder + 1) % 4 && /^[1-9][mps]$/.test(base(pai))) {
      const n = parseInt(base(pai)[0], 10), s = base(pai)[1];
      const has = (x) => x >= 1 && x <= 9 && cnt(x + s) > 0;
      if (has(n - 2) && has(n - 1)) opts.push({ type: "chi", label: "吃" });
      if (has(n - 1) && has(n + 1)) opts.push({ type: "chi", label: "吃" });
      if (has(n + 1) && has(n + 2)) opts.push({ type: "chi", label: "吃" });
    }
    opts.push({ type: "none", label: "过" });
    return { caller, discarder, pai, chosen: ne.type, opts };
  }
  function callWindowHTML(call) {
    if (!call) return "";
    const chips = call.opts.map((o) => `<span class="call-opt${o.type === call.chosen ? " chosen" : ""}">${esc(o.label)}</span>`).join("");
    return `<div class="call-window"><div class="cw-head">鸣牌窗口 · ${esc(S.agents[call.discarder] || "")} 打出 ${esc(call.pai)}</div>` +
      `<div class="cw-opts">${chips}</div>` +
      `<div class="cw-note">${esc(S.agents[call.caller] || "")} 响应 · 仅合法选项可选 · 他家可见窗口开放</div></div>`;
  }
  function winBlock(fr) {
    const w = fr.win;
    if (!w) return "";
    const how = w.tsumo ? "自摸" : "荣和";
    const score = w.yakuman ? "役满" : `${w.han}番${w.fu}符`;
    const yaku = (w.yaku || []).map((y) => `<span class="yaku">${esc(y)}</span>`).join("");
    const ura = (w.ura && w.ura.length) ? `<div class="ura-row"><span class="lbl">里宝</span>${w.ura.map((t) => Tiles.tileSVG(t, { w: 22, h: 31 })).join("")}</div>` : "";
    return `<div class="win-block"><div class="win-head">${esc(S.agents[w.seat] || "")} ${how}！</div>` +
      `<div class="win-score">${score} · ${w.points}点</div>` +
      `<div class="win-yaku">${yaku}</div>` +
      `<div class="win-tile">${w.win_tile ? Tiles.tileSVG(w.win_tile, { w: 26, h: 36, highlight: true }) : ""}</div>${ura}</div>`;
  }
  function renderCenter(fr) {
    const round = `${WIND[fr.bakaze] || "東"}${fr.kyoku}局`;
    const dora = (fr.dora || []).map((t) => Tiles.tileSVG(t, { w: 26, h: 36 })).join("");
    const sticks = Array.from({ length: Math.min(fr.kyotaku, 6) }, () => `<span class="stick"></span>`).join("");
    els.center.innerHTML =
      `<div class="round">${round}</div>` +
      `<div class="center-sub">${fr.honba} 本場 · 供託 ${fr.kyotaku}</div>` +
      `<div class="sticks">${sticks}</div>` +
      `<div class="wall">余牌 <b>${fr.wall != null ? fr.wall : "-"}</b></div>` +
      `<div class="dora-row"><span class="lbl">宝牌指示</span>${dora}</div>`;
  }
  function renderOverlay(fr, call) {
    const ev = fr.event || {};
    let html = "";
    if (ev.type === "reach") {
      const dbl = fr.seats[ev.actor] && fr.seats[ev.actor].double_riichi;
      html += `<div class="callout${dbl ? " double" : ""}">${dbl ? "双立直" : "立直"}</div>`;
    }
    html += callWindowHTML(call);
    if (fr.banner) html += `<div class="banner">${esc(fr.banner)}</div>`;
    html += winBlock(fr);
    els.overlay.innerHTML = html;
  }
  function renderReasoning(fr) {
    const lat = S.latest[fr.index] || [];
    let html = "";
    for (let seat = 0; seat < 4; seat++) {
      const d = lat[seat];
      const actor = fr.event && fr.event.actor === seat;
      if (!d) {
        html += `<div class="reason-card${actor ? " actor" : ""}"><div class="rc-head"><span class="rc-name">${avatar(seat, 20)}${esc(S.agents[seat] || "")}</span></div><div class="rc-reason" style="color:var(--muted)">等待行动…</div></div>`;
        continue;
      }
      const fb = d.fallback ? `<span class="fb">兜底</span>` : "";
      const reason = d.reason ? esc(d.reason) : (d.label ? "" : "(无推理)");
      html += `<div class="reason-card${actor ? " actor" : ""}">` +
        `<div class="rc-head"><span class="rc-name">${avatar(seat, 20)}${esc(d.name || S.agents[seat] || "")}</span><span class="rc-lat">${d.latency_ms != null ? d.latency_ms + "ms" : ""}</span></div>` +
        `<div class="rc-action">${esc(d.label || d.mjai || "")}${fb}</div>` +
        `<div class="rc-reason">${reason}</div>` +
        (d.raw ? `<details><summary>原始输出</summary><pre>${esc(d.raw)}</pre></details>` : "") +
        `</div>`;
    }
    els.reasoning.innerHTML = html;
  }
  function render() {
    const fr = S.frames[S.idx];
    if (!fr) return;
    const call = callInfo(fr);
    for (let s = 0; s < 4; s++) { renderIdentity(s, fr, call); renderHand(s, fr); renderMelds(s, fr); renderRiver(s, fr); }
    renderCenter(fr);
    renderOverlay(fr, call);
    renderReasoning(fr);
    els.counter.textContent = `${S.idx + 1} / ${S.frames.length}`;
    els.scrub.max = String(Math.max(0, S.frames.length - 1));
    els.scrub.value = String(S.idx);
    window.__VIEWER_FRAME__ = S.idx;
    window.__VIEWER_TOTAL__ = S.frames.length;
    maybeCommentary(fr);
  }

  /* ---------- commentary ---------- */
  function showSubtitle(text) {
    els.subtitle.textContent = text;
    els.subtitle.classList.add("show");
    clearTimeout(S.subTimer);
    S.subTimer = setTimeout(() => els.subtitle.classList.remove("show"), 6000);
  }
  function maybeCommentary(fr) {
    if (!S.commOn) return;
    const line = S.commByPos.get(fr.index);
    if (!line) return;
    if (!S.playedComm.has(fr.index)) { S.playedComm.add(fr.index); showSubtitle(line.text); }
    if (S.soundOn && line.audio_url && !S.audioPlayed.has(fr.index)) {
      S.audioPlayed.add(fr.index);
      const a = new Audio(line.audio_url);
      a.play().catch(() => {});
    }
  }
  function ingestCommentary(lines) {
    for (const ln of lines || []) {
      if (ln && ln.event_pos != null && !S.commByPos.has(ln.event_pos)) S.commByPos.set(ln.event_pos, ln);
    }
  }

  /* ---------- transport ---------- */
  function stopPlay() { S.playing = false; clearTimeout(S.timer); els.play.textContent = "▶"; }
  function tick() {
    if (!S.playing) return;
    const fr = S.frames[S.idx];
    const extra = fr && BANNER.has(fr.event && fr.event.type) ? S.bannerPauseMs : 0;
    S.timer = setTimeout(() => {
      if (S.idx < S.frames.length - 1) { S.idx++; render(); tick(); }
      else if (S.loop) { S.idx = 0; S.playedComm.clear(); S.audioPlayed.clear(); render(); tick(); }
      else { stopPlay(); window.__VIEWER_DONE__ = true; }
    }, S.paceMs + extra);
  }
  function startPlay() { S.playing = true; els.play.textContent = "⏸"; tick(); }
  function step(d) { stopPlay(); S.follow = false; S.idx = Math.min(S.frames.length - 1, Math.max(0, S.idx + d)); render(); }

  /* ---------- live ---------- */
  function setLiveBadge(status, n) {
    els.liveBadge.classList.remove("hidden");
    if (status === "running") { els.liveBadge.classList.remove("done"); els.liveText.textContent = `LIVE · ${n} 事件 · 进行中`; }
    else { els.liveBadge.classList.add("done"); els.liveText.textContent = status === "done" ? "直播结束" : ("直播 " + status); }
  }
  async function livePoll() {
    if (!S.live) return;
    try {
      const r = await fetch(`/api/live/state?game=${encodeURIComponent(S.liveId)}&since=${S.liveSince}`);
      const d = await r.json();
      if (d.error) { els.status.textContent = d.error; return; }
      if (d.frames && d.frames.length) { S.frames = S.frames.concat(d.frames); rebuildLatest(); }
      S.liveSince = d.n_frames;
      S.liveStatus = d.status;
      S.agents = d.agents || S.agents;
      ingestCommentary(d.commentary);
      setLiveBadge(d.status, d.n_frames);
      if (d.summary) els.status.textContent = `终分 ${(d.summary.scores || []).join(" / ")}`;
      if (S.follow) { S.idx = S.frames.length - 1; render(); } else render();
      if (d.status !== "running") { window.__VIEWER_DONE__ = true; }
    } catch (e) { /* transient */ }
    S.pollTimer = setTimeout(livePoll, 1000);
  }
  function startLive(id) {
    S.live = true; S.liveId = id; S.gameId = id; S.liveSince = 0; S.frames = []; S.latest = [];
    S.commByPos.clear(); S.playedComm.clear(); S.audioPlayed.clear(); S.follow = true;
    els.sel.value = id;
    els.status.textContent = "连接直播…";
    livePoll();
  }

  /* ---------- loading ---------- */
  function rebuildLatest() {
    const decs = [];
    for (const fr of S.frames) for (const d of fr.decisions || []) decs.push(d);
    decs.sort((a, b) => a.event_pos - b.event_pos);
    const latest = new Array(S.frames.length);
    const cur = [null, null, null, null];
    let p = 0;
    for (let i = 0; i < S.frames.length; i++) {
      while (p < decs.length && decs[p].event_pos <= i) { cur[decs[p].seat] = decs[p]; p++; }
      latest[i] = cur.slice();
    }
    S.latest = latest;
  }
  async function loadGame(id, wantFrame) {
    S.live = false; clearTimeout(S.pollTimer); els.liveBadge.classList.add("hidden");
    S.gameId = id;
    const r = await fetch(`/api/game/${encodeURIComponent(id)}/frames`);
    const d = await r.json();
    S.frames = d.frames || []; S.agents = d.agents || [];
    S.commByPos.clear(); S.playedComm.clear(); S.audioPlayed.clear();
    rebuildLatest();
    try {
      const c = await fetch(`/api/game/${encodeURIComponent(id)}/commentary`);
      const cd = await c.json();
      ingestCommentary(cd.lines);
    } catch (e) {}
    S.idx = Math.min(wantFrame || 0, S.frames.length - 1);
    els.status.textContent = `${S.agents.join(" / ")} · ${S.frames.length} 事件`;
    fitBoard();
    render();
    window.__VIEWER_READY__ = true;
    if (S.autoplay) startPlay();
  }
  async function loadGames() {
    const r = await fetch("/api/games");
    const d = await r.json();
    const games = d.games || [];
    els.sel.innerHTML = games.map((g) => {
      const tag = g.live ? (g.live === "running" ? "🔴 " : "✅ ") : "";
      return `<option value="${esc(g.id)}">${tag}${esc(g.id)} · ${esc(g.agents)}</option>`;
    }).join("");
    const wantLive = params.get("live");
    const wantGame = params.get("game");
    const wantFrame = parseInt(params.get("frame") || "0", 10);
    if (wantLive) {
      if (!games.some((g) => g.id === wantLive)) els.sel.innerHTML += `<option value="${esc(wantLive)}">🔴 ${esc(wantLive)}</option>`;
      startLive(wantLive);
    } else {
      const id = wantGame && games.some((g) => g.id === wantGame) ? wantGame : (games[0] && games[0].id);
      if (id) { els.sel.value = id; await loadGame(id, wantFrame); }
    }
    fitBoard();
  }

  /* ---------- new-game (human): per-seat roster picker ---------- */
  let CONFIGS = [];
  let ROSTER = [];
  const WINDS = ["东", "南", "西", "北"];
  async function loadConfigs() {
    try {
      const [rc, rr] = await Promise.all([fetch("/api/configs"), fetch("/api/roster")]);
      CONFIGS = (await rc.json()).configs || [];
      ROSTER = ((await rr.json()).players || []).filter((p) => p.enabled !== false);
    } catch (e) { CONFIGS = []; ROSTER = []; }
    const live = CONFIGS.filter((c) => c.kind === "live");
    els.ngConfig.innerHTML = `<option value="">自定义逐席选人…</option>` + live.map((c) =>
      `<option value="${esc(c.id)}">${esc(c.name)}（${c.seats.map((s) => s.name).join(" / ")}）</option>`).join("");
    renderNgSeats();
  }
  function seatOptions(sel) {
    return ROSTER.map((p) =>
      `<option value="${esc(p.id)}" ${p.id === sel ? "selected" : ""}>${esc(p.display || p.id)} · ${esc(p.model || p.type)}</option>`).join("");
  }
  function renderNgSeats() {
    const prev = [0, 1, 2, 3].map((i) => { const el = document.getElementById("ngSeat" + i); return el ? el.value : ""; });
    els.ngSeats.innerHTML = [0, 1, 2, 3].map((i) =>
      `<label class="ng-seat-row">${pdot(i)}<span class="ng-wind">${WINDS[i]}</span>
        <select id="ngSeat${i}"><option value="">选择选手…</option>${seatOptions(prev[i])}</select></label>`).join("");
  }
  function presetFill() {
    const c = CONFIGS.find((x) => x.id === els.ngConfig.value);
    if (!c) return;
    c.seats.forEach((s, i) => {
      const el = document.getElementById("ngSeat" + i);
      if (!el) return;
      const match = ROSTER.find((p) => p.display === s.name || p.id === s.name) ||
                    ROSTER.find((p) => (p.model || "") === (s.model || "") && s.model);
      if (match) el.value = match.id;
    });
  }
  async function refreshNgLive() {
    try {
      const r = await fetch("/api/live/list");
      const games = (await r.json()).games || [];
      const running = games.filter((g) => g.status === "running");
      els.ngLiveList.innerHTML = running.length
        ? running.map((g) => `<button class="ng-live-item" data-id="${esc(g.game_id)}">🔴 ${esc(g.game_id)}<em>${esc((g.agents || []).join(" / "))}</em></button>`).join("")
        : `<span class="ng-empty">暂无进行中的直播</span>`;
      els.ngLiveList.querySelectorAll(".ng-live-item").forEach((b) =>
        b.addEventListener("click", () => { closeNewGame(); startLive(b.dataset.id); }));
    } catch (e) { els.ngLiveList.innerHTML = `<span class="ng-empty">无法连接服务器</span>`; }
  }
  function openNewGame() { els.modal.classList.remove("hidden"); els.ngError.classList.add("hidden"); loadConfigs(); refreshNgLive(); }
  function closeNewGame() { els.modal.classList.add("hidden"); }
  async function startNewGame() {
    els.ngError.classList.add("hidden");
    els.ngStart.disabled = true;
    try {
      const seats = [0, 1, 2, 3].map((i) => (document.getElementById("ngSeat" + i) || {}).value || "");
      if (seats.some((s) => !s)) { els.ngError.textContent = "请为每个席位选择一名选手（可用预设填充）"; els.ngError.classList.remove("hidden"); return; }
      const body = { seats, seed: parseInt(els.ngSeed.value, 10) || 0 };
      if (els.ngId.value.trim()) body.game_id = els.ngId.value.trim();
      const r = await fetch("/api/live/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const d = await r.json();
      if (d.error) { els.ngError.textContent = d.error; els.ngError.classList.remove("hidden"); return; }
      closeNewGame();
      if (![...els.sel.options].some((o) => o.value === d.game_id))
        els.sel.innerHTML += `<option value="${esc(d.game_id)}">🔴 ${esc(d.game_id)}</option>`;
      startLive(d.game_id);
    } catch (e) {
      els.ngError.textContent = String(e); els.ngError.classList.remove("hidden");
    } finally { els.ngStart.disabled = false; }
  }

  /* ---------- wiring ---------- */
  els.newGameBtn.addEventListener("click", openNewGame);
  els.ngClose.addEventListener("click", closeNewGame);
  els.modal.addEventListener("click", (e) => { if (e.target === els.modal) closeNewGame(); });
  els.ngConfig.addEventListener("change", presetFill);
  els.ngStart.addEventListener("click", startNewGame);
  els.sel.addEventListener("change", () => {
    const id = els.sel.value;
    stopPlay();
    fetch("/api/live/list").then((r) => r.json()).then((d) => {
      const live = (d.games || []).find((x) => x.game_id === id && x.status === "running");
      if (live) startLive(id); else loadGame(id, 0);
    }).catch(() => loadGame(id, 0));
  });
  els.play.addEventListener("click", () => { if (S.live) { S.follow = !S.follow; els.play.textContent = S.follow ? "⏸" : "▶"; if (S.follow) { S.idx = S.frames.length - 1; render(); } } else if (S.playing) stopPlay(); else startPlay(); });
  els.prev.addEventListener("click", () => step(-1));
  els.next.addEventListener("click", () => step(1));
  els.restart.addEventListener("click", () => { stopPlay(); S.follow = false; S.idx = 0; S.playedComm.clear(); S.audioPlayed.clear(); render(); });
  els.scrub.addEventListener("input", () => { stopPlay(); S.follow = false; S.idx = parseInt(els.scrub.value, 10) || 0; render(); });
  els.speed.addEventListener("change", () => { S.paceMs = parseInt(els.speed.value, 10); });
  els.hideHands.addEventListener("change", () => { S.hideHands = els.hideHands.checked; render(); });
  els.sound.addEventListener("change", () => { S.soundOn = els.sound.checked; });
  els.comm.addEventListener("change", () => { S.commOn = els.comm.checked; if (!S.commOn) els.subtitle.classList.remove("show"); });
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT") return;
    if (e.code === "Space") { e.preventDefault(); els.play.click(); }
    else if (e.code === "ArrowLeft") step(-1);
    else if (e.code === "ArrowRight") step(1);
  });

  // URL config
  S.paceMs = parseInt(params.get("pace") || "2500", 10);
  S.bannerPauseMs = parseInt(params.get("bannerpause") || "3000", 10);
  S.loop = params.get("loop") === "1";
  S.autoplay = params.get("autoplay") === "1";
  S.hideHands = params.get("hide") === "1"; els.hideHands.checked = S.hideHands;
  S.commOn = params.get("commentary") !== "0"; els.comm.checked = S.commOn;
  S.soundOn = params.get("sound") !== "0"; els.sound.checked = S.soundOn;
  els.speed.value = String(S.paceMs);
  if (![...els.speed.options].some((o) => o.value === String(S.paceMs))) {
    const o = document.createElement("option"); o.value = String(S.paceMs); o.textContent = S.paceMs + "ms"; els.speed.appendChild(o); els.speed.value = String(S.paceMs);
  }

  fitBoard();
  loadProfiles().then(() => loadGames());
})();
