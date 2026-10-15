// Brautag-Assistent: Schritt für Schritt mit Timern, Messwerten und Hefe
import { esc, icon, fmt, fmtInput, ebcColor, glassSvg, numIn, parseDate, dfTime } from "./lib.js";

const FELDER = {
  WuerzemengeKochbeginn: ["Würzemenge", "l"],
  SWKochbeginn: ["Stammwürze", "°P"],
  WuerzemengeVorHopfenseihen: ["Würzemenge vor Hopfenseihen", "l"],
  WuerzemengeKochende: ["Würzemenge nach Hopfenseihen", "l"],
  SWKochende: ["Stammwürze", "°P"],
  SWAnstellen: ["Stammwürze", "°P"],
  WuerzemengeAnstellen: ["Würzemenge", "l"],
  VerduennungAnstellen: ["Verdünnung", "l"],
  Speisemenge: ["Speisemenge", "l"],
  MengeHefestarter: ["Hefestarter", "l"],
  SWHefestarter: ["Stammwürze Hefestarter", "°P"],
};

export async function laden(p, id) {
  p.bt = { id, laden: true };
  p.render();
  try {
    const r = await p.ws("brautag", { sud_id: id });
    p.bt = { id, ...r, werte: { ...r.braudaten.werte } };
  } catch (err) {
    p.bt = { id, fehler: err?.message || String(err) };
  }
  p.render();
}

function sitzung(p) {
  // aktueller Stand kommt mit jedem Datenabruf (für andere Geräte)
  return p.entry?.brautag && p.entry.brautag.sud_id === p.bt?.id ? p.entry.brautag : p.bt?.sitzung;
}

export function render(p) {
  const bt = p.bt;
  if (!bt || bt.laden) return `<p class="muted">Lade Brautag …</p>`;
  if (bt.fehler) return `<div class="empty">${icon("alert-outline")}<p class="gross">Brautag nicht möglich</p><p class="muted">${esc(bt.fehler)}</p>
    <button class="btn" data-action="back">${icon("arrow-left")}Zurück</button></div>`;
  const s = p.sudById(bt.id) || { name: bt.braudaten.name, ebc: 0 };
  const c = ebcColor(s.ebc);
  const st = sitzung(p) || { schritt: "vorbereitung", erledigt: [] };
  const idx = Math.max(0, bt.schritte.findIndex((x) => x.key === st.schritt));
  const step = bt.schritte[idx];

  let phase = "";
  const liste = bt.schritte.map((x, i) => {
    const kopf = x.phase !== phase ? `<li class="phase">${esc(x.phase)}</li>` : "";
    phase = x.phase;
    const fertig = st.erledigt.includes(x.key);
    return `${kopf}<li class="${fertig ? "erledigt" : ""}"><button data-action="bt-schritt" data-key="${x.key}" ${i === idx ? 'aria-current="step"' : ""}>
      <span class="nr">${fertig ? icon("check") : i + 1}</span><span class="lbl">${esc(x.titel)}</span></button></li>`;
  }).join("");

  return `<div style="--beer:${c}">
    <header class="detail-head" style="align-items:center;margin-bottom:12px">${glassSvg(c, (idx + 1) / bt.schritte.length, { size: 64 })}
      <div><p class="meta">Brautag</p><h2 style="font-size:26px">${esc(s.name)}</h2></div></header>
    <div class="assistent">
      <ol class="schrittliste">${liste}</ol>
      <ha-card><div class="card-body schritt">
        <p class="meta">Schritt ${idx + 1} von ${bt.schritte.length}, ${esc(step.phase)}</p>
        <h2>${esc(step.titel)}</h2>
        ${step.untertitel ? `<p class="untertitel">${esc(step.untertitel)}</p>` : ""}
        <ul class="zeilen-text">${step.zeilen.map((z) => `<li>${esc(z)}</li>`).join("")}</ul>
        ${step.timer_min ? timer(p, st, step) : ""}
        ${step.felder ? felder(p, step) : ""}
        ${step.hefe ? hefe(p) : ""}
        ${step.abschluss ? abschluss(p) : ""}
        <div class="schritt-nav">
          <button class="btn quiet" data-action="bt-zurueck" ${idx === 0 ? "disabled" : ""}>${icon("chevron-left")}Zurück</button>
          ${step.abschluss
            ? `<button class="btn primary" data-action="bt-gebraut">${icon("check-decagram-outline")}${p.bt.confirm ? "Ja, Sud gebraut" : "Sud gebraut"}</button>`
            : `<button class="btn primary" data-action="bt-weiter">Weiter${icon("chevron-right")}</button>`}
        </div>
        ${p.bt.confirm ? `<p class="confirm">Der Sud wird auf „gebraut“ gesetzt und erscheint unter Gärung.</p>` : ""}
        ${p.bt.msg ? `<p class="${p.bt.msg.ok ? "ok" : "warn-box"}" style="margin-top:12px">${esc(p.bt.msg.text)}</p>` : ""}
      </div></ha-card>
    </div>
    <p style="margin-top:16px"><button class="btn quiet" data-action="bt-beenden">${icon("close")}Brautag abbrechen</button></p>
  </div>`;
}

function timer(p, st, step) {
  const t = st.timer && st.timer.schritt === step.key ? st.timer : null;
  const ev = step.ereignisse || [];
  const start = t ? parseDate(t.start) : null;
  const evListe = ev.length ? `<ul class="ereignisse">${ev.map((e) => {
    const vorbei = t && t.gemeldet.includes(`e${e.min}`);
    const uhr = start ? ` (${dfTime.format(new Date(start.getTime() + e.min * 60000))})` : "";
    return `<li class="${vorbei ? "vorbei" : ""}">${icon(vorbei ? "check" : "hops")}${e.rest_min === step.timer_min ? "Kochbeginn" : e.rest_min === 0 ? "Kochende" : `${e.rest_min} min vor Ende`}${uhr}: ${esc(e.text)}</li>`;
  }).join("")}</ul>` : "";
  return `<div class="timer" data-timer="${t ? esc(t.ende) : ""}" data-gesamt="${step.timer_min * 60}">
    <svg viewBox="0 0 120 120"><circle class="ring-bg" cx="60" cy="60" r="50"/>
      <circle class="ring" cx="60" cy="60" r="50" stroke-dasharray="314.16" stroke-dashoffset="${t ? 0 : 314.16}"/>
      <text class="zeit" x="60" y="68" text-anchor="middle">${t ? "" : `${step.timer_min}:00`}</text></svg>
    <div>
      <p style="margin:0;font-weight:500">${t ? `Läuft seit ${dfTime.format(start)}, fertig um ${dfTime.format(parseDate(t.ende))}` : `Timer ${step.timer_min} min`}</p>
      <p class="muted" style="margin:4px 0 10px">${t ? "Die Meldungen kommen aufs Handy und als Ansage – auch wenn diese Seite zu ist." : "Erinnerungen und Ansagen kommen über die Einstellungen unter Meldungen."}</p>
      ${t ? `<button class="btn" data-action="bt-timer-stop">${icon("stop")}Timer stoppen</button>`
        : `<button class="btn primary" data-action="bt-timer" data-key="${step.key}">${icon("timer-play-outline")}Timer starten</button>`}
      ${evListe}
    </div>
  </div>`;
}

export function tick(p) {
  const el = p.shadowRoot.querySelector(".timer[data-timer]");
  if (!el || !el.dataset.timer) return;
  const ende = parseDate(el.dataset.timer);
  const gesamt = Number(el.dataset.gesamt);
  const rest = Math.max(0, Math.round((ende.getTime() - Date.now()) / 1000));
  const m = Math.floor(rest / 60), s = rest % 60;
  el.querySelector(".zeit").textContent = rest > 0 ? `${m}:${String(s).padStart(2, "0")}` : "fertig";
  el.querySelector(".ring").setAttribute("stroke-dashoffset", (314.16 * (1 - rest / gesamt)).toFixed(1));
}

function felder(p, step) {
  const w = p.bt.werte;
  return `<div class="felder" style="margin-top:20px">${step.felder.map((k) => {
    const [label, unit] = FELDER[k];
    const v = typeof w[k] === "number" ? fmtInput(w[k]) : w[k];
    return `<label class="feld"><span>${label}</span><span class="eingabe">
      <input inputmode="decimal" autocomplete="off" data-bt-feld="${k}" value="${esc(v ?? "")}"><em>${unit}</em></span></label>`;
  }).join("")}</div>`;
}

function hefe(p) {
  if (!p.bt.hefe?.length) return "";
  return `<ul class="zeilen" style="margin-top:16px">${p.bt.hefe.map((h) => `<li>
    <span class="rund ${h.zugegeben ? "done" : ""}">${icon("bacteria-outline")}</span>
    <div class="text"><b>${esc(h.name)}</b><p class="muted">${h.zugegeben ? "angestellt" : "noch nicht angestellt"}</p></div>
    ${h.zugegeben ? "" : `<button class="btn klein" data-action="bt-hefe" data-id="${h.id}">${icon("check")}Angestellt</button>`}</li>`).join("")}</ul>`;
}

function abschluss(p) {
  const bd = p.bt.braudaten;
  const now = new Date();
  now.setSeconds(0, 0);
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  return `<div class="felder" style="margin-top:20px">
    <label class="feld"><span>Braudatum</span><input type="datetime-local" data-bt-extra="braudatum" value="${esc(p.bt.braudatum || (bd.braudatum ? bd.braudatum.slice(0, 16) : local))}"></label>
    <label class="feld voll"><span>Bemerkung zum Brautag</span><textarea rows="3" data-bt-extra="bemerkung">${esc(p.bt.bemerkung ?? bd.bemerkung ?? "")}</textarea></label>
  </div>`;
}

// Eingaben des aktuellen Schritts sichern und speichern
function sammeln(p) {
  const root = p.shadowRoot;
  const werte = {};
  let bad = null;
  root.querySelectorAll("[data-bt-feld]").forEach((inp) => {
    const v = numIn(inp.value);
    p.bt.werte[inp.dataset.btFeld] = inp.value;
    if (Number.isNaN(v) || v < 0) bad = bad || FELDER[inp.dataset.btFeld][0];
    else werte[inp.dataset.btFeld] = v;
  });
  root.querySelectorAll("[data-bt-extra]").forEach((inp) => { p.bt[inp.dataset.btExtra] = inp.value; });
  return { werte, bad };
}

async function speichern(p, gebraut = false) {
  const { werte, bad } = sammeln(p);
  if (bad) throw new Error(`Bitte eine gültige Zahl bei „${bad}“ eintragen.`);
  if (Object.keys(werte).length || gebraut) {
    await p.ws("braudaten_speichern", {
      sud_id: p.bt.id, werte, gebraut,
      ...(p.bt.braudatum ? { braudatum: p.bt.braudatum } : {}),
      ...(p.bt.bemerkung !== undefined ? { bemerkung: p.bt.bemerkung } : {}),
    });
  }
}

async function wechseln(p, delta) {
  const st = sitzung(p);
  const idx = p.bt.schritte.findIndex((x) => x.key === st.schritt);
  const ziel = p.bt.schritte[Math.max(0, Math.min(p.bt.schritte.length - 1, idx + delta))];
  try {
    if (delta > 0) await speichern(p);
    const r = await p.ws("brautag_aktion", { aktion: "schritt", schritt: ziel.key });
    p.bt.sitzung = r.sitzung;
    if (p.entry) p.entry.brautag = r.sitzung;
    p.bt.msg = null;
    p.bt.confirm = false;
  } catch (err) {
    p.bt.msg = { ok: false, text: err?.message || String(err) };
  }
  p.render();
  window.scrollTo?.(0, 0);
}

export const actions = {
  "bt-weiter": (p) => wechseln(p, 1),
  "bt-zurueck": (p) => wechseln(p, -1),
  "bt-schritt": async (p, btn) => {
    sammeln(p);
    const r = await p.ws("brautag_aktion", { aktion: "schritt", schritt: btn.dataset.key });
    p.bt.sitzung = r.sitzung;
    if (p.entry) p.entry.brautag = r.sitzung;
    p.render();
  },
  "bt-timer": async (p, btn) => {
    sammeln(p);
    try {
      const r = await p.ws("brautag_aktion", { aktion: "timer_starten", schritt: btn.dataset.key });
      p.bt.sitzung = r.sitzung;
      if (p.entry) p.entry.brautag = r.sitzung;
    } catch (err) {
      p.bt.msg = { ok: false, text: err?.message || String(err) };
    }
    p.render();
  },
  "bt-timer-stop": async (p) => {
    sammeln(p);
    const r = await p.ws("brautag_aktion", { aktion: "timer_stoppen" });
    p.bt.sitzung = r.sitzung;
    if (p.entry) p.entry.brautag = r.sitzung;
    p.render();
  },
  "bt-hefe": async (p, btn) => {
    sammeln(p);
    try {
      await p.ws("hefe", { hefe_id: Number(btn.dataset.id) });
      const h = p.bt.hefe.find((x) => x.id === Number(btn.dataset.id));
      if (h) h.zugegeben = true;
    } catch (err) {
      p.bt.msg = { ok: false, text: err?.message || String(err) };
    }
    p.render();
  },
  "bt-gebraut": async (p) => {
    if (!p.bt.confirm) {
      sammeln(p);
      p.bt.confirm = true;
      p.render();
      return;
    }
    try {
      await speichern(p, true);
      const name = p.sudById(p.bt.id)?.name || "Der Sud";
      const id = p.bt.id;
      p.bt = null;
      p.tab = "gaerung";
      await p.fetch();
      p.go("sud", id);
      if (p.entry?.einstellungen?.lager) p.openDialog("lager", { sudId: id, anlass: "brautag" });
      else p.toast(`${name} ist gebraut. Jetzt die Pill-Aufzeichnung starten.`);
    } catch (err) {
      p.bt.confirm = false;
      p.bt.msg = { ok: false, text: err?.message || String(err) };
      p.render();
    }
  },
  "bt-beenden": async (p) => {
    if (!p.bt?.abbrechen) {
      p.bt.abbrechen = true;
      p.bt.msg = { ok: false, text: "Nochmal tippen zum Abbrechen. Eingetragene Werte bleiben gespeichert, Timer werden gestoppt." };
      p.render();
      return;
    }
    await p.ws("brautag_aktion", { aktion: "beenden" });
    p.bt = null;
    await p.fetch();
    p.go("liste");
  },
};
