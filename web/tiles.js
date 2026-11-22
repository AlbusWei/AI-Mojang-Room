/* Majsoul-inspired riichi tile renderer (self-drawn, CC0 — no external assets).
 * Tiles.tileSVG(code, {w,h,down,dim,highlight,rot}) -> SVG string.
 * Codes: 1m..9m / 1p..9p / 1s..9s, red 5mr/5pr/5sr, honors E S W N P F C.
 */
(function () {
  const HONOR = { E: "東", S: "南", W: "西", N: "北", P: "白", F: "發", C: "中" };
  const MAN_NUM = ["一", "二", "三", "四", "五", "六", "七", "八", "九"];
  const NAVY = "#1f3a5f", RED = "#c0392b", GREEN = "#1e8449", BLUE = "#2471a3";

  // pin (circle) layouts: [x,y,r,color] in 60x84 face coords
  const P = BLUE, R = RED, G = GREEN;
  const PIN = {
    1: [[30, 42, 15, R]],
    2: [[30, 24, 9, P], [30, 60, 9, P]],
    3: [[16, 20, 8, P], [30, 42, 8, R], [44, 64, 8, P]],
    4: [[18, 24, 8, P], [42, 24, 8, P], [18, 60, 8, P], [42, 60, 8, P]],
    5: [[16, 20, 7, P], [44, 20, 7, P], [30, 42, 7, R], [16, 64, 7, P], [44, 64, 7, P]],
    6: [[18, 20, 7, G], [42, 20, 7, G], [18, 42, 7, R], [42, 42, 7, R], [18, 64, 7, R], [42, 64, 7, R]],
    7: [[14, 16, 6, G], [30, 22, 6, G], [46, 28, 6, G], [18, 50, 7, R], [42, 50, 7, R], [18, 68, 7, R], [42, 68, 7, R]],
    8: [[18, 16, 6, P], [42, 16, 6, P], [18, 34, 6, P], [42, 34, 6, P], [18, 52, 6, P], [42, 52, 6, P], [18, 70, 6, P], [42, 70, 6, P]],
    9: [[16, 18, 6, R], [30, 18, 6, R], [44, 18, 6, R], [16, 42, 6, P], [30, 42, 6, P], [44, 42, 6, P], [16, 66, 6, G], [30, 66, 6, G], [44, 66, 6, G]],
  };
  // sou (bamboo) stick positions [x,y]
  const SOU = {
    2: [[30, 24], [30, 60]],
    3: [[30, 20], [18, 60], [42, 60]],
    4: [[18, 24], [42, 24], [18, 60], [42, 60]],
    5: [[16, 20], [44, 20], [30, 42], [16, 64], [44, 64]],
    6: [[16, 24], [30, 24], [44, 24], [16, 60], [30, 60], [44, 60]],
    7: [[30, 16], [16, 42], [30, 42], [44, 42], [16, 68], [30, 68], [44, 68]],
    8: [[16, 16], [44, 16], [16, 34], [44, 34], [16, 52], [44, 52], [16, 70], [44, 70]],
    9: [[16, 18], [30, 18], [44, 18], [16, 42], [30, 42], [44, 42], [16, 66], [30, 66], [44, 66]],
  };

  function stick(x, y, color) {
    return `<rect x="${x - 3}" y="${y - 9}" width="6" height="18" rx="3" fill="${color}"/>` +
      `<rect x="${x - 3}" y="${y - 2}" width="6" height="3" fill="#f6f1e3" opacity=".7"/>`;
  }
  function circle(x, y, r, color) {
    return `<circle cx="${x}" cy="${y}" r="${r}" fill="none" stroke="${color}" stroke-width="3"/>` +
      `<circle cx="${x}" cy="${y}" r="${Math.max(1.5, r * 0.35)}" fill="${color}"/>`;
  }
  function bird() {
    // stylized 1-sou peacock
    return `<path d="M30 14 C20 22 18 34 24 44 C18 46 16 54 22 60 C26 66 34 66 38 60 C44 54 42 46 36 44 C42 34 40 22 30 14 Z" fill="${GREEN}"/>` +
      `<circle cx="27" cy="26" r="2" fill="#f6f1e3"/>` +
      `<path d="M30 44 C34 50 34 56 30 62 C26 56 26 50 30 44 Z" fill="${RED}"/>`;
  }

  function face(code) {
    const red = code.endsWith("r");
    const b = red ? code.slice(0, -1) : code;
    if (HONOR[b]) {
      const ch = HONOR[b];
      if (b === "P") return `<rect x="14" y="18" width="32" height="48" rx="6" fill="none" stroke="${BLUE}" stroke-width="3"/>`;
      const color = b === "C" ? RED : b === "F" ? GREEN : NAVY;
      return `<text x="30" y="56" font-size="40" text-anchor="middle" fill="${color}" font-family="'Noto Serif SC','SimSun',serif" font-weight="700">${ch}</text>`;
    }
    const n = parseInt(b, 10);
    const suit = b.slice(-1);
    if (suit === "m") {
      const nc = red ? RED : NAVY;
      return `<text x="30" y="34" font-size="26" text-anchor="middle" fill="${nc}" font-family="'Noto Serif SC','SimSun',serif" font-weight="700">${MAN_NUM[n - 1]}</text>` +
        `<text x="30" y="70" font-size="26" text-anchor="middle" fill="${RED}" font-family="'Noto Serif SC','SimSun',serif" font-weight="700">萬</text>`;
    }
    if (suit === "p") return PIN[n].map((c) => circle(c[0], c[1], c[2], red ? RED : c[3])).join("");
    if (suit === "s") {
      if (n === 1) return bird();
      return SOU[n].map((p, i) => stick(p[0], p[1], red ? RED : (n === 5 && i === 2 ? RED : GREEN))).join("");
    }
    return "";
  }

  function tileSVG(code, o) {
    o = o || {};
    const w = o.w || 30, h = o.h || 42;
    const rot = o.rot ? ` transform="rotate(90 30 42)"` : "";
    let inner;
    if (o.down) {
      inner = `<rect x="2" y="2" width="56" height="80" rx="7" fill="#0e6b5c"/>` +
        `<rect x="7" y="7" width="46" height="70" rx="5" fill="#0a4f44"/>` +
        `<rect x="7" y="7" width="46" height="10" rx="5" fill="#12836f" opacity=".6"/>`;
    } else {
      inner = `<rect x="2" y="2" width="56" height="80" rx="7" fill="#d8d2c0"/>` +
        `<rect x="2" y="2" width="56" height="76" rx="7" fill="#f6f1e3"/>` +
        `<rect x="4" y="4" width="52" height="12" rx="6" fill="#fffdf5" opacity=".8"/>` +
        `<g${rot}>${face(code)}</g>`;
      if (code.endsWith("r")) inner += `<circle cx="50" cy="10" r="4" fill="${RED}"/>`;
    }
    const stroke = o.highlight ? "#e8c15a" : "#b9b2a0";
    const sw = o.highlight ? 3 : 1;
    const opacity = o.dim ? 0.35 : 1;
    const filt = o.dim ? ` filter="grayscale(1)"` : "";
    const glow = o.highlight ? `<rect x="0.5" y="0.5" width="59" height="83" rx="8" fill="none" stroke="#e8c15a" stroke-width="2" opacity=".9"/>` : "";
    return `<svg class="tile" width="${w}" height="${h}" viewBox="0 0 60 84" style="opacity:${opacity}"${filt ? "" : ""}>` +
      `<rect x="2" y="2" width="56" height="80" rx="7" fill="none" stroke="${stroke}" stroke-width="${sw}"/>` +
      inner + glow + `</svg>`;
  }

  window.Tiles = { tileSVG, HONOR };
})();
