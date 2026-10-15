// Hilfsfunktionen für die Brauhelfer-Seite

// EBC -> Farbe, übernommen aus BierCalc::ebcToColor (kleiner-brauhelfer-core)
export const EBC = ["#fff6a9","#fff4a3","#fef19a","#feed8f","#fee881","#fee272","#fedb61","#fdd456","#fccd4b","#fbc541","#f9bc37","#f7b22d","#f5a723","#f29d19","#ef9410","#e98b07","#e18200","#d77900","#ce700f","#c4681e","#bb602b","#b25936","#a95240","#a04c48","#97464f","#8f4154","#873c58","#7f385b","#78345c","#71305c","#6a2d5b","#642a59","#5e2756","#592552","#54234e","#4f2149","#4b1f44","#471e3f","#431c3a","#3f1b36","#3c1a31","#38182d","#351729","#321625","#2f1522","#2d141f","#2a131c","#28121a","#261117","#241015","#220f13","#200e11","#1e0d10","#1c0c0e","#1b0b0d","#190b0c","#180a0b","#170a0a","#150909","#140908","#130808","#120807","#110707","#100706","#0f0606","#0e0605","#0e0605","#0d0504","#0c0504","#0c0504","#0b0404","#0a0403","#0a0403","#090403","#090303","#080303","#080303","#080302","#070302","#070302","#070202","#060202","#060202","#060202","#050202","#050202","#050201","#050201","#040201","#040201","#040101","#040101","#040101","#030101","#030101","#030101","#030101","#030101","#030101"];

export const STATUS_GEPLANT = 0;
export const ALT_TAGE = 60; // ab hier Hinweis "noch nicht abgefüllt?"

export function ebcColor(ebc) {
  let i = Math.trunc((ebc || 0) - 2);
  if (i < 0) i = 0;
  if (i > 98) i = 98;
  return EBC[i];
}

export function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    c /= 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

// Linienfarbe: helle Biere abdunkeln, sehr dunkle aufhellen, damit die Kurve lesbar bleibt
export function lineColor(hex, dark) {
  const n = parseInt(hex.slice(1), 16);
  let rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  const l = luminance(hex);
  if (!dark && l > 0.35) rgb = rgb.map((c) => Math.round(c * 0.62));
  if (dark && l < 0.06) rgb = rgb.map((c) => Math.round(c + (255 - c) * 0.45));
  return `rgb(${rgb.join(",")})`;
}

export function sgToPlato(sg) {
  return -616.868 + 1111.14 * sg - 630.272 * sg ** 2 + 135.997 * sg ** 3;
}

export function toTre(sw, sre) {
  return 0.1808 * sw + 0.8192 * sre;
}
export function platoToDichte(p) {
  return 1 + p / (258.6 - (p / 258.2) * 227.1);
}
export function alkohol(sw, sre) {
  if (sw <= 0) return 0;
  const tre = toTre(sw, sre);
  const a = ((sw - tre) / (2.0665 - 0.010665 * sw)) * platoToDichte(tre) / 0.794;
  return Math.max(a, 0);
}
export function vg(sw, sre) {
  return sw > 0 ? (1 - sre / sw) * 100 : 0;
}

export const nf = {};
export function fmt(v, d = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  nf[d] = nf[d] || new Intl.NumberFormat("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
  return nf[d].format(v);
}

export const nfInput = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 3, useGrouping: false });
export function fmtInput(v) {
  return v === null || v === undefined || Number.isNaN(v) ? "" : nfInput.format(v);
}

export const dfDay = new Intl.DateTimeFormat("de-DE", { day: "numeric", month: "short" });
export const dfFull = new Intl.DateTimeFormat("de-DE", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
export const dfLong = new Intl.DateTimeFormat("de-DE", { day: "numeric", month: "long", year: "numeric" });

export function parseDate(s) {
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function since(d) {
  if (!d) return "";
  const min = Math.round((Date.now() - d.getTime()) / 60000);
  if (min < 1) return "gerade eben";
  if (min < 60) return `vor ${min} min`;
  const h = Math.round(min / 60);
  if (h < 48) return `vor ${h} h`;
  return `vor ${Math.round(h / 24)} Tagen`;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function daysSince(d) {
  return d ? Math.floor((Date.now() - d.getTime()) / 86400000) : null;
}

// ---------------------------------------------------------------------------
// Glas
// ---------------------------------------------------------------------------

export let glassSeq = 0;
export function glassSvg(color, fill, { size = 96, bubbles = false } = {}) {
  // fill: 0..1 (Anteil bis Ziel-Vergärung)
  const id = `g${++glassSeq}`;
  const f = Math.max(0, Math.min(1, fill));
  const top = 22, bottom = 132;
  const level = bottom - (bottom - top) * (0.15 + 0.85 * f);
  const bub = bubbles
    ? [18, 30, 41, 26, 36].map((x, i) =>
        `<circle class="bubble" cx="${x}" cy="${bottom - 6}" r="${1.4 + (i % 3) * 0.5}" style="animation-delay:${i * 0.9}s"/>`
      ).join("")
    : "";
  return `
  <svg class="glass" viewBox="0 0 60 140" width="${size * 0.43}" height="${size}" aria-hidden="true">
    <defs>
      <clipPath id="${id}"><path d="M6 14 L54 14 L48 134 Q47 138 43 138 L17 138 Q13 138 12 134 Z"/></clipPath>
      <linearGradient id="${id}s" x1="0" x2="1">
        <stop offset="0" stop-color="#fff" stop-opacity=".0"/>
        <stop offset=".22" stop-color="#fff" stop-opacity=".28"/>
        <stop offset=".3" stop-color="#fff" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <g clip-path="url(#${id})">
      <rect x="0" y="0" width="60" height="140" class="glass-empty"/>
      <rect x="0" y="${level}" width="60" height="${140 - level}" fill="${color}"/>
      <rect x="0" y="${level - 7}" width="60" height="8" class="foam" rx="3"/>
      <g class="bubbles">${bub}</g>
      <rect x="0" y="0" width="60" height="140" fill="url(#${id}s)"/>
    </g>
    <path d="M6 14 L54 14 L48 134 Q47 138 43 138 L17 138 Q13 138 12 134 Z" class="glass-outline"/>
  </svg>`;
}

// ---------------------------------------------------------------------------
// Gärkurve
// ---------------------------------------------------------------------------

export function chartSvg(sud, color, width) {
  const pts = (sud.verlauf || [])
    .map((m) => ({ t: parseDate(m.zeit), sre: m.restextrakt, temp: m.temperatur }))
    .filter((p) => p.t);
  const brau = parseDate(sud.braudatum);
  if (brau && sud.sw > 0) pts.unshift({ t: brau, sre: sud.sw, temp: null, start: true });
  if (pts.length < 2) return null;

  const W = Math.round(width), H = W < 520 ? 200 : 240, L = 34, R = 38, T = 14, B = 28;
  const t0 = pts[0].t.getTime();
  const t1 = Math.max(pts[pts.length - 1].t.getTime(), t0 + 86400000);
  const yMax = Math.ceil(Math.max(sud.sw, ...pts.map((p) => p.sre)) + 1);
  const temps = pts.filter((p) => p.temp !== null).map((p) => p.temp);
  const tMin = temps.length ? Math.floor(Math.min(...temps) - 2) : 10;
  const tMax = temps.length ? Math.ceil(Math.max(...temps) + 2) : 25;

  const x = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
  const y = (v) => T + (1 - v / yMax) * (H - T - B);
  const yt = (v) => T + (1 - (v - tMin) / (tMax - tMin || 1)) * (H - T - B);

  const sreLine = pts.map((p, i) => `${i ? "L" : "M"}${x(p.t.getTime()).toFixed(1)} ${y(p.sre).toFixed(1)}`).join(" ");
  const area = `${sreLine} L${x(pts[pts.length - 1].t.getTime()).toFixed(1)} ${y(0)} L${x(pts[0].t.getTime()).toFixed(1)} ${y(0)} Z`;
  const gid = `area${++glassSeq}`;
  // Schnellgärprobe: letzter Wert als waagrechte Linie (= erreichbarer Endvergärungsgrad)
  const schnell = (sud.schnell || []).filter((m) => m.restextrakt !== null && m.restextrakt !== undefined);
  const sgWert = schnell.length ? schnell[schnell.length - 1].restextrakt : null;
  const schnellLine = sgWert !== null ? `M${L} ${y(sgWert).toFixed(1)} L${W - R} ${y(sgWert).toFixed(1)}` : "";
  const tp = pts.filter((p) => p.temp !== null);
  const tempLine = tp.map((p, i) => `${i ? "L" : "M"}${x(p.t.getTime()).toFixed(1)} ${yt(p.temp).toFixed(1)}`).join(" ");

  // Achsen
  const stepY = yMax > 16 ? 4 : 2;
  let grid = "";
  for (let v = 0; v <= yMax; v += stepY) {
    grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="grid"/>
             <text x="${L - 8}" y="${y(v) + 4}" class="ax" text-anchor="end">${v}</text>`;
  }
  const tStep = tMax - tMin > 8 ? 4 : 2;
  for (let v = Math.ceil(tMin / tStep) * tStep; v <= tMax; v += tStep) {
    grid += `<text x="${W - R + 8}" y="${yt(v) + 4}" class="ax temp-ax">${v}°</text>`;
  }
  const days = (t1 - t0) / 86400000;
  const maxTicks = Math.max(2, Math.floor((W - L - R) / 72));
  const dStep = [1, 2, 3, 7, 14, 30, 60, 90, 180, 365].find((n) => days / n <= maxTicks) || 365;
  for (let d = 0; d <= days; d += dStep) {
    const tx = x(t0 + d * 86400000);
    grid += `<text x="${tx}" y="${H - 8}" class="ax" text-anchor="middle">${d === 0 ? "Brautag" : `Tag ${d}`}</text>`;
  }

  const target = sud.sre_erwartet > 0
    ? `<line x1="${L}" x2="${W - R}" y1="${y(sud.sre_erwartet)}" y2="${y(sud.sre_erwartet)}" class="target"/>
       <text x="${L + 6}" y="${y(sud.sre_erwartet) + 15}" class="target-label">Ziel ${fmt(sud.sre_erwartet, 1)} °P</text>`
    : "";

  // Viele Messwerte: nur Start und letzten Punkt zeigen, die übrigen erscheinen beim Antippen
  const leise = pts.length > 16;
  const dots = pts.map((p, i) => {
    const sichtbar = p.start || !leise || i === pts.length - 1;
    return `<circle cx="${x(p.t.getTime())}" cy="${y(p.sre)}" r="${p.start ? 3.5 : sichtbar && leise ? 4 : 3}" class="dot${p.start ? " start" : ""}${sichtbar ? "" : " leise"}" style="--c:${color}" data-i="${i}"/>`;
  }).join("");

  return {
    pts,
    svg: `
    <svg class="chart" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img"
         aria-label="Gärverlauf: Restextrakt und Temperatur über die Zeit">
      ${grid}
      ${target}
      <defs><linearGradient id="${gid}" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color="${color}" stop-opacity=".28"/><stop offset="1" stop-color="${color}" stop-opacity="0"/>
      </linearGradient></defs>
      <path d="${area}" fill="url(#${gid})" stroke="none"/>
      <path d="${tempLine}" class="temp-line"/>
      ${schnellLine ? `<path d="${schnellLine}" class="schnell-line"/>
        <text x="${W - R - 4}" y="${y(sgWert) - 6}" class="target-label" text-anchor="end">Schnellgärprobe ${fmt(sgWert, 1)} °P</text>` : ""}
      <path d="${sreLine}" class="sre-line" style="stroke:${color}"/>
      ${dots}
      <line class="cursor" x1="0" x2="0" y1="${T}" y2="${H - B}" style="display:none"/>
      <rect class="hit" x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" data-x0="${L}" data-x1="${W - R}"/>
    </svg>`,
    x, W, H,
  };
}



// ---------------------------------------------------------------------------
// Weitere Bausteine
// ---------------------------------------------------------------------------

export function icon(name, cls = "") {
  return `<ha-icon class="i ${cls}" icon="mdi:${name}"></ha-icon>`;
}

export const dfDate = new Intl.DateTimeFormat("de-DE", { day: "numeric", month: "short", year: "numeric" });
export const dfTime = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit" });

export function numIn(v) {
  if (v === null || v === undefined) return NaN;
  const s = String(v).trim().replace(/\s/g, "").replace(",", ".");
  return s === "" ? NaN : Number(s);
}

export function sparkline(verlauf, color, w = 120, h = 34) {
  const pts = (verlauf || []).map((m) => ({ t: parseDate(m.zeit)?.getTime(), v: m.restextrakt })).filter((p) => p.t);
  if (pts.length < 2) return "";
  const t0 = pts[0].t, t1 = pts[pts.length - 1].t || t0 + 1;
  const vs = pts.map((p) => p.v), lo = Math.min(...vs), hi = Math.max(...vs) || 1;
  const x = (t) => 2 + ((t - t0) / (t1 - t0 || 1)) * (w - 4);
  const y = (v) => 3 + (1 - (v - lo) / (hi - lo || 1)) * (h - 6);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)} ${y(p.v).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">
    <path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(last.t)}" cy="${y(last.v)}" r="3" fill="${color}"/></svg>`;
}

export function sterne(n, { input = false, name = "sterne" } = {}) {
  let out = "";
  for (let i = 1; i <= 5; i++) {
    out += input
      ? `<button type="button" class="star ${i <= n ? "on" : ""}" data-action="dlg:stern" data-wert="${i}" aria-label="${i} Sterne">${icon(i <= n ? "star" : "star-outline")}</button>`
      : `<span class="star ${i <= n ? "on" : ""}">${icon(i <= n ? "star" : "star-outline")}</span>`;
  }
  return `<span class="stars" ${input ? `role="radiogroup" aria-label="Sterne" data-name="${name}"` : `aria-label="${n} von 5 Sternen"`}>${out}</span>`;
}

// Verkostung: Bitmasken wie im Brauhelfer (DlgBewertungen). Gruppen schließen sich gegenseitig aus.
export const VERKOSTUNG = [
  { key: "farbe", titel: "Farbe", gruppen: [
    [[4, "hellgelb, lichthell"], [5, "gelb"], [6, "golden"], [7, "bernstein"], [8, "kupferrot, bernsteinfarben"], [9, "braun bis tiefbraun"], [10, "schwarz, tiefdunkel"]],
    [[0, "satt, intensiv"], [1, "glänzend"], [2, "matt, blass"], [3, "gräulich, fahl"]]] },
  { key: "schaum", titel: "Schaum", gruppen: [
    [[0, "feinporig, fest"], [1, "grobporig, schwach"]], [[2, "gut haftend am Glas"], [3, "schlecht haftend"]],
    [[4, "gute Haltbarkeit"], [5, "mässige Haltbarkeit"], [6, "keine Haltbarkeit"]],
    [[7, "geringes Volumen"], [8, "kräftiges Volumen"], [9, "sehr voluminös, mächtig"], [10, "überschäumend"]]] },
  { key: "geruch", titel: "Geruch", mehrfach: true, gruppen: [[[0, "rein, abgerundet"], [1, "frisch"], [2, "wohlriechend"], [3, "unangenehm, unausgewogen"], [4, "hopfenaromatisch, hopfig"], [5, "malzaromatisch, malzig"], [6, "süsslich, nach Würze"], [7, "hefig"], [8, "fruchtig"], [9, "gewürzig"], [10, "säuerlich"], [11, "Geruchsfehler"]]] },
  { key: "geschmack", titel: "Geschmack", mehrfach: true, gruppen: [[[0, "rein"], [1, "ausgewogen, rund"], [2, "gehaltvoll"], [3, "unausgewogen, kantig"], [4, "unreif, unrein"], [5, "hopfenaromatisch, hopfig"], [6, "malzaromatisch, malzig"], [7, "süsslich, klebrig"], [8, "säuerlich"], [9, "gewürzig"], [10, "fruchtig"], [11, "hefig"], [12, "Geschmacksfehler"]]] },
  { key: "antrunk", titel: "Antrunk", gruppen: [[[0, "angenehm rezent"], [1, "rezent, fein perlend"], [2, "gut eingebunden"], [3, "prickelnd"], [4, "stark prickelnd, aufdringlich"], [5, "wenig rezent"], [6, "schal"], [7, "sehr schal"]]] },
  { key: "haupttrunk", titel: "Haupttrunk", gruppen: [[[0, "wässrig, leer, dünn"], [1, "etwas leer"], [2, "schlank"], [3, "vollmundig"], [4, "mastig, breit"]]] },
  { key: "nachtrunk", titel: "Nachtrunk", gruppen: [[[0, "sehr fein"], [1, "angenehm, ausgewogen"], [2, "nicht anhängend"], [3, "nachhängend"], [4, "stark nachhängend"], [5, "wenig herb, unterentwickelt"], [6, "sehr herb, kräftig betont"], [7, "nicht oder kaum wahrnehmbar"], [8, "unangenehm"]]] },
  { key: "gesamteindruck", titel: "Gesamteindruck", gruppen: [[[0, "toll, macht Lust auf mehr"], [1, "gutes, typisches Bier"], [2, "interessant"], [3, "überraschend, ungewöhnlich"], [4, "kunstvoll, kreativ, mutig"], [5, "unauffällig, gewöhnlich"], [6, "einmal ist genug, langweilig"], [7, "nicht trinkbar, problematisch"]]] },
];

export function verkostungText(kat, maske) {
  const out = [];
  for (const g of kat.gruppen) for (const [bit, text] of g) if (maske & (1 << bit)) out.push(text);
  return out;
}

export function navigate(path) {
  const url = `/brauhelfer${path}`;
  if (location.pathname + location.search !== url) history.pushState(null, "", url);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
}
