// Sud-Detail: Gärung, Zutaten & Proben, Gärschrank, Fässer, Nachgärung, Verkostung, Lebenslauf
import {
  esc, icon, fmt, ebcColor, lineColor, glassSvg, chartSvg, parseDate, daysSince, since,
  dfLong, dfFull, dfDate, vg, sterne, VERKOSTUNG, verkostungText,
} from "./lib.js";

const ALT_TAGE = 60;

const TABS = {
  0: [["rezept", "Rezept"], ["lebenslauf", "Lebenslauf"]],
  1: [["gaerung", "Gärung"], ["zutaten", "Zutaten & Proben"], ["gaerschrank", "Gärschrank"], ["lebenslauf", "Lebenslauf"]],
  2: [["faesser", "Fässer"], ["nachgaerung", "Nachgärung"], ["verkostung", "Verkostung"], ["lebenslauf", "Lebenslauf"]],
};

export function render(p) {
  const id = p.view.id;
  const s = p.sudById(id);
  const d = p.details[id];
  if (!s) {
    return `<div class="empty">${icon("help-circle-outline")}<p class="gross">Diesen Sud gibt es hier nicht (mehr).</p>
      <p class="muted">Er ist vielleicht verbraucht oder nicht auf der Merkliste.</p>
      <button class="btn" data-action="back">${icon("arrow-left")}Zur Übersicht</button></div>`;
  }
  const c = ebcColor(s.ebc);
  const dark = !!p.hass?.themes?.darkMode;
  const tabs = TABS[s.status] || TABS[1];
  const aktiv = p.subtab[id] && tabs.some(([k]) => k === p.subtab[id]) ? p.subtab[id] : tabs[0][0];
  let body;
  if (!d) body = `<p class="muted">Lade Details …</p>`;
  else if (d.fehler) body = `<p class="warn-box">${esc(d.fehler)}</p>`;
  else body = SEKTIONEN[aktiv](p, s, d, { c, lc: lineColor(c, dark) });
  return `<div style="--beer:${c};--line:${lineColor(c, dark)}">
    ${kopf(p, s, d, c)}
    <nav class="subtabs" role="tablist">${tabs.map(([k, l]) =>
      `<button role="tab" data-action="subtab" data-sud="${id}" data-tab="${k}" aria-selected="${k === aktiv}">${l}</button>`).join("")}</nav>
    ${body}
  </div>`;
}

// ---------------------------------------------------------------- Kopf
function kopf(p, s, d, c) {
  const e = p.entry;
  const last = s.verlauf?.[s.verlauf.length - 1];
  const a = e.aufzeichnungen[String(s.id)];
  const live = a ? p.live(a) : null;
  let fuell = 1, facts = "", meta = "", badges = [];
  if (s.status === 0) {
    meta = esc(s.kategorie || "Rezept");
    facts = `
      <div><dt>Stammwürze</dt><dd>${fmt(s.sw_rezept, 1)}<small> °P</small></dd></div>
      <div><dt>Menge</dt><dd>${fmt(s.menge, 0)}<small> l</small></dd></div>
      <div><dt>Bittere</dt><dd>${fmt(s.ibu, 0)}<small> IBU</small></dd></div>
      <div><dt>Alkohol</dt><dd>${s.alkohol_rezept ? fmt(s.alkohol_rezept, 1) : "–"}<small> %</small></dd></div>`;
  } else if (s.status === 1) {
    const brau = parseDate(s.braudatum);
    const tage = daysSince(brau);
    const sre = live && live.fresh ? live.plato : last ? last.restextrakt : s.sw;
    const vgIst = vg(s.sw, sre);
    fuell = s.vg_rezept > 0 ? vgIst / s.vg_rezept : 0;
    meta = [s.kategorie, brau ? `gebraut am ${dfLong.format(brau)}` : null, tage !== null ? `Tag ${tage}` : null].filter(Boolean).map(esc).join(", ");
    facts = `
      <div><dt>Restextrakt</dt><dd class="big">${fmt(sre, 1)}<small> °P</small></dd></div>
      <div><dt>Alkohol</dt><dd>${fmt(last ? last.alkohol : 0, 1)}<small> % vol</small></dd></div>
      <div><dt>Vergärungsgrad</dt><dd>${fmt(vgIst, 0)}<small> % von ${fmt(s.vg_rezept, 0)} %</small></dd></div>
      <div><dt>Temperatur</dt><dd>${live && live.fresh && !Number.isNaN(live.temp) ? fmt(live.temp, 1) : last ? fmt(last.temperatur, 1) : "–"}<small> °C</small></dd></div>`;
    if (a) badges.push(live?.fresh ? `<span class="badge live">${icon("bluetooth")}${esc(a.name)} zeichnet auf</span>` : `<span class="badge warn">${icon("bluetooth-off")}${esc(a.name)} ohne Werte</span>`);
    const reg = e.regelung[String(s.id)];
    const sst = reg?.schrank_id ? e.schrank_status[reg.schrank_id] : null;
    if (sst && sst.soll !== null && sst.soll !== undefined) badges.push(`<span class="badge">${icon("fridge-industrial-outline")}${esc(sst.modus_text)}, Soll ${fmt(sst.soll, 1)} °C</span>`);
  } else {
    const abf = parseDate(s.abfuelldatum);
    const faesser = e.faesser.filter((f) => f.sud_id === s.id);
    const rest = faesser.reduce((n, f) => n + (f.leer ? 0 : f.rest_l), 0);
    const voll = faesser.reduce((n, f) => n + f.inhalt_l, 0);
    fuell = voll ? rest / voll : 1;
    meta = abf ? `abgefüllt am ${dfLong.format(abf)}` : "abgefüllt";
    facts = `
      <div><dt>Im Fass</dt><dd class="big">${fmt(rest, 1)}<small> l</small></dd></div>
      <div><dt>Alkohol</dt><dd>${last ? fmt(last.alkohol, 1) : "–"}<small> % vol</small></dd></div>
      <div><dt>Stammwürze</dt><dd>${fmt(s.sw, 1)}<small> °P</small></dd></div>
      <div><dt>Reifung</dt><dd>${reifung(abf)}</dd></div>`;
  }
  let aktionen = "";
  if (s.status === 0) {
    const bt = e.brautag && e.brautag.sud_id === s.id;
    aktionen = `<button class="btn" data-action="dialog" data-typ="braudaten" data-sud="${s.id}">${icon("pencil-outline")}Werte eintragen</button>
      <button class="btn primary" data-action="brautag-start" data-sud="${s.id}">${icon(bt ? "play" : "kettle-steam-outline")}${bt ? "Weiter brauen" : "Brautag starten"}</button>`;
  } else if (s.status === 1) {
    const fertig = s.vg_rezept > 0 && fuell >= 1;
    aktionen = `<button class="btn ${fertig ? "primary" : ""}" data-action="dialog" data-typ="fertig" data-sud="${s.id}">${icon("flag-checkered")}Gärung fertig</button>`;
  }
  return `<header class="detail-head">
    <div class="hero-glas">${glassSvg(c, fuell, { size: p._narrow || p.clientWidth < 600 ? 96 : 140, bubbles: !!(live && live.fresh) })}</div>
    <div class="hero-text">
      <p class="kicker">${["Geplant", "In Gärung", "Abgefüllt", "Verbraucht"][s.status] || ""}</p>
      <h2>${esc(s.name)}</h2>
      <p class="meta">${meta}</p>
      ${badges.length ? `<div class="badges">${badges.join("")}</div>` : ""}
    </div>
    <dl class="facts">${facts}</dl>
    ${aktionen ? `<div class="hero-aktionen">${aktionen}</div>` : ""}
  </header>`;
}

function reifung(abf) {
  const t = daysSince(abf);
  if (t === null) return "–";
  if (t < 14) return `${t}<small> ${t === 1 ? "Tag" : "Tage"}</small>`;
  return `${fmt(t / 7, 0)}<small> Wochen</small>`;
}

function card(titel, ic, inhalt, { aktionen = "", kopfRechts = "" } = {}) {
  return `<ha-card>
    <div class="card-head"><h3>${icon(ic)}${titel}</h3>${kopfRechts}</div>
    <div class="card-body">${inhalt}</div>
    ${aktionen ? `<div class="card-actions">${aktionen}</div>` : ""}
  </ha-card>`;
}

function hinweis(text) {
  return `<p class="hint">${icon("information-outline")}<span>${text}</span></p>`;
}

// ---------------------------------------------------------------- Gärung
function gaerung(p, s, d, { lc }) {
  const e = p.entry;
  const tage = daysSince(parseDate(s.braudatum));
  const alt = tage !== null && tage > ALT_TAGE
    ? hinweis(`Dieser Sud gärt laut Datenbank seit ${tage} Tagen. Ist er schon abgefüllt? Dann unten „Gärung fertig“ wählen.`) : "";
  const schnell = d.schnellgaerverlauf || [];
  const chart = chartSvg({ ...s, schnell }, lc, p.chartWidth() - 40);
  if (chart) p.charts[s.id] = { ...chart, sud: s };
  const last = s.verlauf?.[s.verlauf.length - 1];
  const kurve = card("Gärverlauf", "chart-bell-curve-cumulative", `
      <div class="chart-head"><p class="legend"><span class="sw-line"></span>Restextrakt
        ${schnell.length ? `<span class="sw-schnell"></span>Schnellgärprobe` : ""}<span class="sw-temp"></span>Temperatur</p></div>
      <p class="readout" data-readout="${s.id}">${last ? `Letzter Messwert ${dfFull.format(parseDate(last.zeit))}. Kurve antippen für Details.` : "Noch keine Messwerte"}</p>
      ${chart ? `<div class="chart-box" data-chart="${s.id}" style="aspect-ratio:${chart.W} / ${chart.H}">${chart.svg}</div>`
        : `<p class="muted">Ab zwei Messwerten wird hier die Kurve gezeichnet.</p>`}`);
  return `${alt}${pill(p, e, s)}${kurve}${messwerte(p, s)}`;
}

function pill(p, e, s) {
  const a = e.aufzeichnungen[String(s.id)];
  const msg = p.msg[s.id];
  const st = e.sud_status[String(s.id)];
  const notice = msg ? `<p class="${msg.ok ? "ok" : "warn-box"}" role="status">${esc(msg.text)}</p>`
    : a && st?.fehler ? `<p class="warn-box" role="status">Letzter Versuch ${st.letzter_versuch ? since(parseDate(st.letzter_versuch)) : ""}: ${esc(st.fehler)}</p>` : "";
  if (!a) {
    if (!e.pills.length) {
      return card("Aufzeichnung", "bluetooth", `<p class="muted" style="margin:0">Keine Pill gefunden. Richte die Integration „RAPT Bluetooth“ ein, dann erscheint die Pill hier zur Auswahl.</p>${notice}`);
    }
    const chosen = p.pillChoice[s.id] || (e.pills.find((x) => !x.belegt_von) || e.pills[0]).gravity;
    const opts = e.pills.map((x) => {
      const other = x.belegt_von && x.belegt_von !== s.id ? p.sudById(x.belegt_von) : null;
      return `<option value="${esc(x.gravity)}" ${x.gravity === chosen ? "selected" : ""} ${other ? "disabled" : ""}>${esc(x.name)}${other ? ` (zeichnet für ${esc(other.name)} auf)` : ""}</option>`;
    }).join("");
    const busy = p.busy[`start:${s.id}`];
    return card("Aufzeichnung", "bluetooth", `<div class="pill">
      <p class="muted">Die Pill trägt alle ${takt(e)} einen Wert in den Gärverlauf ein.</p>
      <div class="reihe">
        <label class="pill-pick"><span>Pill</span><select data-pill-sud="${s.id}">${opts}</select></label>
        <button class="btn primary" data-action="pill-start" data-sud="${s.id}" ${busy ? "disabled" : ""} style="align-self:end">
          ${icon("record-circle-outline")}${busy ? "Starte …" : "Aufzeichnung starten"}</button>
      </div>${notice}</div>`);
  }
  const live = p.live(a);
  let txt = "Keine Werte von der Pill.";
  if (live && !live.offline) {
    const parts = [`${fmt(live.plato, 2)} °P`];
    if (live.sg) parts.push(`SG ${fmt(live.sg, 3)}`);
    if (!Number.isNaN(live.temp)) parts.push(`${fmt(live.temp, 1)} °C`);
    txt = `${parts.join(", ")}, ${since(live.updated)}`;
    if (!live.fresh) txt += ", zu alt zum Eintragen";
  }
  const start = parseDate(a.start);
  const busyLog = p.busy[`log:${s.id}`];
  return card("Aufzeichnung", "bluetooth", `<div class="pill">
    <div class="pill-live"><span class="dot-live ${live?.fresh ? "fresh" : ""}" aria-hidden="true"></span>
      <div><p class="pill-title">${esc(a.name)}</p><p class="pill-values">${esc(txt)}</p>
      <p class="muted">Trägt alle ${takt(e)} ein${start ? `, seit ${dfFull.format(start)}` : ""}.</p></div></div>${notice}</div>`,
  { aktionen: `
    <button class="btn quiet" data-action="pill-stop" data-sud="${s.id}">${icon("stop-circle-outline")}Aufzeichnung beenden</button>
    <button class="btn primary" data-action="pill-log" data-sud="${s.id}" ${busyLog ? "disabled" : ""}>${icon("database-plus-outline")}${busyLog ? "Trage ein …" : "Jetzt eintragen"}</button>` });
}

function takt(e) {
  const h = e.intervall_min / 60;
  return e.intervall_min >= 60 ? `${fmt(h, h % 1 ? 1 : 0)} Stunden` : `${e.intervall_min} Minuten`;
}

function messwerte(p, s) {
  const rows = [...(s.verlauf || [])].reverse();
  if (!rows.length) return "";
  const alle = p.expanded[`mw${s.id}`];
  const shown = alle ? rows : rows.slice(0, 5);
  return card("Messwerte", "table", `<table class="nums">
      <thead><tr><th>Zeit</th><th>Restextrakt</th><th>Alkohol</th><th>Temp.</th><th class="hide-narrow">Bemerkung</th></tr></thead>
      <tbody>${shown.map((m) => `<tr><td>${m.zeit ? dfFull.format(parseDate(m.zeit)) : "–"}</td>
        <td>${fmt(m.restextrakt, 2)} °P</td><td>${fmt(m.alkohol, 1)} %</td><td>${fmt(m.temperatur, 1)} °C</td>
        <td class="hide-narrow muted">${esc(m.bemerkung || "")}</td></tr>`).join("")}</tbody></table>
    ${rows.length > 5 ? `<button class="btn quiet" data-action="mehr" data-key="mw${s.id}" style="margin-top:8px">${alle ? "Weniger anzeigen" : `Alle ${rows.length} Messwerte`}</button>` : ""}`);
}

// ---------------------------------------------------------------- Zutaten & Proben
function zutaten(p, s, d) {
  const gz = d.zutaten.filter((z) => z.zeitpunkt === 0);
  const jetzt = Date.now();
  const zl = gz.length ? `<ul class="zeilen">${gz.map((z) => {
    const zug = parseDate(z.zugabe_datum), ent = parseDate(z.entnahme_datum);
    let status, knopf = "";
    if (z.status === 0) {
      status = zug ? `${zug.getTime() <= jetzt ? "fällig seit" : "geplant am"} ${dfDate.format(zug)}` : "noch nicht zugegeben";
      knopf = `<button class="btn klein" data-action="zutat" data-id="${z.id}" data-art="zugeben">${icon("check")}Zugegeben</button>`;
    } else if (z.status === 1) {
      status = `zugegeben${zug ? ` am ${dfDate.format(zug)}` : ""}${z.mit_entnahme && ent ? `, raus am ${dfDate.format(ent)}` : ""}`;
      if (z.mit_entnahme) knopf = `<button class="btn klein" data-action="zutat" data-id="${z.id}" data-art="entnehmen">${icon("tray-arrow-up")}Entnommen</button>`;
    } else {
      status = `entnommen nach ${fmt(z.dauer_tage, 0)} Tagen`;
    }
    const faellig = z.status === 0 && zug && zug.getTime() <= jetzt;
    return `<li><span class="rund ${z.status ? "done" : ""}">${icon(z.hopfen ? "hops" : "flask-outline")}</span>
      <div class="text"><b>${fmt(z.menge, 0)} ${esc(z.einheit)} ${esc(z.name)}</b>${z.hopfen ? `<span class="muted"> Hopfenstopfen</span>` : ""}
      <p class="muted" ${faellig ? 'style="color:var(--warn)"' : ""}>${status}</p></div>${knopf}</li>`;
  }).join("")}</ul>` : `<p class="muted" style="margin:0">Für die Gärung sind keine Zutaten oder Hopfengaben geplant.</p>`;

  const hl = d.hefe.length ? `<ul class="zeilen">${d.hefe.map((h) => `<li>
      <span class="rund ${h.zugegeben ? "done" : ""}">${icon("bacteria-outline")}</span>
      <div class="text"><b>${esc(h.name)}</b>${h.menge ? `<span class="muted">, ${h.menge} Einheit${h.menge > 1 ? "en" : ""}</span>` : ""}
      <p class="muted">${h.zugegeben ? `zugegeben am Tag ${h.zugabe_nach_tagen}` : "noch nicht als zugegeben markiert"}</p></div>
      ${h.zugegeben ? "" : `<button class="btn klein" data-action="hefe" data-id="${h.id}">${icon("check")}Zugegeben</button>`}</li>`).join("")}</ul>`
    : `<p class="muted" style="margin:0">Keine Hefe im Rezept.</p>`;

  const sg = d.schnellgaerverlauf || [];
  const sgl = sg.length ? `<table class="nums"><thead><tr><th>Zeit</th><th>Restextrakt</th><th>Vergärung</th><th>Temp.</th></tr></thead>
    <tbody>${[...sg].reverse().map((m) => `<tr><td>${m.zeit ? dfFull.format(parseDate(m.zeit)) : "–"}</td><td>${fmt(m.restextrakt, 2)} °P</td>
      <td>${fmt(vg(s.sw, m.restextrakt), 0)} %</td><td>${fmt(m.temp, 1)} °C</td></tr>`).join("")}</tbody></table>
    <p class="muted" style="margin:10px 0 0">Die Schnellgärprobe zeigt den Endvergärungsgrad. Ist die Hauptgärung dort angekommen, ist der Sud fertig.</p>`
    : `<p class="muted" style="margin:0">Eine kleine Probe warm (ca. 25 °C) mit etwas Hefe vergären lassen. Der Wert zeigt, wie weit der Sud höchstens vergären kann.</p>`;

  return card("Zutaten in der Gärung", "hops", zl)
    + card("Hefe", "bacteria-outline", hl)
    + card("Schnellgärprobe", "test-tube", sgl, { aktionen: `<button class="btn" data-action="dialog" data-typ="schnellgaer" data-sud="${s.id}">${icon("plus")}Wert eintragen</button>` });
}

// ---------------------------------------------------------------- Gärschrank
function gaerschrank(p, s) {
  const e = p.entry;
  if (!e.schraenke.length) {
    return card("Gärschrank", "fridge-industrial-outline", `<p class="muted" style="margin:0">Noch kein Gärschrank eingerichtet. Lege in den Einstellungen einen an: Temperatursensor, Steckdose für Kühlung und für Heizung.</p>`,
      { aktionen: `<button class="btn primary" data-action="settings">${icon("cog-outline")}Zu den Einstellungen</button>` });
  }
  const reg = e.regelung[String(s.id)];
  const schrank = reg?.schrank_id ? e.schraenke.find((x) => x.id === reg.schrank_id) : null;
  if (!schrank) {
    return card("Gärschrank", "fridge-industrial-outline", `<p class="muted" style="margin:0">Dieser Sud wird nicht geregelt. Wähle einen Gärschrank und lege ein Temperaturprofil fest, z. B. 12 °C und ab 70 % Vergärung 16 °C für die Diacetylrast.</p>`,
      { aktionen: `<button class="btn primary" data-action="dialog" data-typ="regelung" data-sud="${s.id}">${icon("thermometer-auto")}Regelung einrichten</button>` });
  }
  const st = e.schrank_status[schrank.id] || {};
  const live = e.aufzeichnungen[String(s.id)] ? p.live(e.aufzeichnungen[String(s.id)]) : null;
  const last = s.verlauf?.[s.verlauf.length - 1];
  const vgIst = vg(s.sw, live && live.fresh ? live.plato : last ? last.restextrakt : s.sw);
  const profil = (reg.profil || []).map((x) => {
    const aktiv = st.stufe && st.stufe.ab_vg === x.ab_vg && st.stufe.soll === x.soll;
    return `<li><span class="rund ${aktiv ? "done" : ""}">${icon(aktiv ? "thermometer-check" : "thermometer")}</span>
      <div class="text"><b>${fmt(x.soll, 1)} °C</b><p class="muted">${x.ab_vg > 0 ? `ab ${fmt(x.ab_vg, 0)} % Vergärung` : "ab Anstellen"}</p></div>
      ${aktiv ? `<span class="badge live">aktiv</span>` : ""}</li>`;
  }).join("");
  const modusIcon = { kuehlen: "snowflake", heizen: "fire", fehler: "alert-outline", pause: "timer-sand" }[st.modus] || "thermometer";
  return card(`Gärschrank ${esc(schrank.name)}`, "fridge-industrial-outline", `
    <dl class="facts" style="margin-top:0">
      <div><dt>Ist</dt><dd class="big">${st.ist !== null && st.ist !== undefined ? fmt(st.ist, 1) : "–"}<small> °C</small></dd></div>
      <div><dt>Soll</dt><dd>${st.soll !== null && st.soll !== undefined ? fmt(st.soll, 1) : "–"}<small> °C</small></dd></div>
      <div><dt>Zustand</dt><dd style="font-size:17px;display:flex;gap:6px;align-items:center">${icon(modusIcon)}${esc(reg.aktiv === false ? "Regelung pausiert" : st.modus_text || "–")}</dd></div>
      <div><dt>Vergärung</dt><dd>${fmt(vgIst, 0)}<small> %</small></dd></div>
    </dl>
    <h3 style="margin:20px 0 4px">Temperaturprofil</h3>
    <ul class="zeilen">${profil}</ul>`,
  { aktionen: `
    <button class="switch" role="switch" aria-checked="${reg.aktiv !== false}" data-action="regelung-aktiv" data-sud="${s.id}"><span class="knob"></span>Regelung aktiv</button>
    <span style="flex:1"></span>
    <button class="btn" data-action="dialog" data-typ="regelung" data-sud="${s.id}">${icon("pencil-outline")}Profil bearbeiten</button>` });
}

// ---------------------------------------------------------------- Fässer
function kegSvg(anteil, farbe) {
  const a = Math.max(0, Math.min(1, anteil));
  const h = 62 * a;
  return `<svg class="fass-grafik" viewBox="0 0 54 80" aria-hidden="true">
    <rect x="6" y="6" width="42" height="70" rx="8" fill="color-mix(in srgb, var(--primary-text-color) 6%, transparent)"/>
    <clipPath id="kc"><rect x="6" y="6" width="42" height="70" rx="8"/></clipPath>
    <rect x="6" y="${74 - h}" width="42" height="${h + 2}" fill="${farbe}" clip-path="url(#kc)"/>
    <rect x="6" y="6" width="42" height="70" rx="8" fill="none" stroke="color-mix(in srgb, var(--primary-text-color) 35%, transparent)" stroke-width="1.6"/>
    <rect x="18" y="1" width="18" height="7" rx="2" fill="color-mix(in srgb, var(--primary-text-color) 40%, transparent)"/>
    <line x1="6" y1="22" x2="48" y2="22" stroke="color-mix(in srgb, var(--primary-text-color) 25%, transparent)"/>
    <line x1="6" y1="60" x2="48" y2="60" stroke="color-mix(in srgb, var(--primary-text-color) 25%, transparent)"/>
  </svg>`;
}

function faesser(p, s, d, { c }) {
  const e = p.entry;
  const liste = e.faesser.filter((f) => f.sud_id === s.id);
  const inhalt = liste.length ? liste.map((f) => {
    const tags = e.tags.filter((t) => t.fass_id === f.id);
    const glas = tags[0]?.glas_l || 0.5;
    const lernen = e.fass_lernen && e.fass_lernen.fass_id === f.id;
    return `<div class="fass">${kegSvg(f.inhalt_l ? f.rest_l / f.inhalt_l : 0, c)}
      <div><h4>${esc(f.name)}${f.leer ? ` <span class="badge">leer</span>` : ""}</h4>
        <p class="rest">${fmt(f.rest_l, 1)}<small> l von ${fmt(f.inhalt_l, 1)} l, etwa ${Math.floor(f.rest_l / glas)} Gläser à ${fmt(glas, 2).replace(/,?0+$/, "")} l</small></p>
        <p class="muted">Leergewicht ${fmt(f.tara_kg, 2)} kg${f.letzte_wiegung ? `, zuletzt gewogen ${since(parseDate(f.letzte_wiegung.zeit))}` : ""}${f.waage ? ", Waage verbunden" : ""}</p>
        <div class="tags">${tags.map((t) => `<span class="badge">${icon("nfc-variant")}${esc(t.name)} (${fmt(t.glas_l, 2)} l)
          <button class="btn quiet klein" data-action="tag-weg" data-tag="${esc(t.tag_id)}" aria-label="Tag ${esc(t.name)} entfernen" style="min-height:0;padding:0 2px">${icon("close")}</button></span>`).join("")}
          ${lernen ? `<span class="badge live">${icon("nfc-search-variant")}Jetzt den Tag mit dem iPhone scannen …</span>` : ""}</div>
        <div class="reihe">
          <button class="btn klein" data-action="fass-glas" data-fass="${f.id}" data-liter="${glas}" ${f.leer ? "disabled" : ""}>${icon("glass-mug-variant")}Glas abziehen</button>
          <button class="btn klein" data-action="dialog" data-typ="wiegen" data-sud="${s.id}" data-extra='${JSON.stringify({ fassId: f.id })}'>${icon("scale")}Wiegen</button>
          <button class="btn klein" data-action="dialog" data-typ="tag" data-sud="${s.id}" data-extra='${JSON.stringify({ fassId: f.id })}'>${icon("nfc-variant")}NFC-Tag</button>
          <button class="btn klein quiet" data-action="dialog" data-typ="fass" data-sud="${s.id}" data-extra='${JSON.stringify({ fassId: f.id })}'>${icon("pencil-outline")}Bearbeiten</button>
        </div></div></div>`;
  }).join("") : `<p class="muted" style="margin:0">Noch kein Fass angelegt. Lege für jedes Fass Leergewicht und Füllmenge fest – danach ziehen NFC-Scans Gläser ab und Wiegen aktualisiert den Rest.</p>`;
  const alleLeer = liste.length && liste.every((f) => f.leer);
  return card("Fässer", "keg", inhalt, { aktionen: `
      ${alleLeer ? `<span class="muted" style="margin-right:auto;align-self:center">Alle Fässer sind leer.</span>` : ""}
      <button class="btn" data-action="dialog" data-typ="fass" data-sud="${s.id}">${icon("plus")}Fass anlegen</button>
      <button class="btn ${alleLeer ? "primary" : "quiet"}" data-action="dialog" data-typ="leer" data-sud="${s.id}">${icon("glass-mug-off")}Sud leer</button>` });
}

// ---------------------------------------------------------------- Nachgärung
function nachgaerung(p, s, d) {
  const rows = [...(d.nachgaerverlauf || [])].reverse();
  const inhalt = rows.length ? `<table class="nums"><thead><tr><th>Zeit</th><th>Druck</th><th>Temp.</th><th>CO₂</th></tr></thead>
    <tbody>${rows.map((m) => `<tr><td>${m.zeit ? dfFull.format(parseDate(m.zeit)) : "–"}</td><td>${fmt(m.druck, 2)} bar</td>
      <td>${fmt(m.temp, 1)} °C</td><td>${fmt(m.co2, 1)} g/l</td></tr>`).join("")}</tbody></table>
    <p class="muted" style="margin:10px 0 0">Ziel laut Rezept: ${fmt(d.co2_soll, 1)} g/l CO₂.</p>`
    : `<p class="muted" style="margin:0">Noch keine Werte.</p>`;
  return card("Nachgärung", "gauge", inhalt, { aktionen: `<button class="btn" data-action="dialog" data-typ="nachgaer" data-sud="${s.id}">${icon("plus")}Druck eintragen</button>` });
}

// ---------------------------------------------------------------- Verkostung
function verkostung(p, s, d) {
  const b = [...(d.bewertungen || [])].reverse();
  const inhalt = b.length ? b.map((x) => {
    const texte = VERKOSTUNG.map((k) => {
      const t = verkostungText(k, x[k.key] || 0);
      const bem = x[`${k.key}_bemerkung`];
      return t.length || bem ? `<p><b>${k.titel}:</b> ${esc([...t, bem].filter(Boolean).join(", "))}</p>` : "";
    }).join("");
    return `<div class="bewertung"><div class="kopf">${sterne(x.sterne)}
      <span class="muted">${x.datum ? dfDate.format(parseDate(x.datum)) : ""}${x.woche ? `, Woche ${x.woche}` : ""}</span></div>
      ${x.bemerkung ? `<p>${esc(x.bemerkung)}</p>` : ""}${texte}</div>`;
  }).join("") : `<p class="muted" style="margin:0">Noch keine Verkostung. Die Kategorien sind dieselben wie im Brauhelfer.</p>`;
  return card("Verkostung", "glass-wine", inhalt, { aktionen: `<button class="btn primary" data-action="dialog" data-typ="verkostung" data-sud="${s.id}">${icon("star-plus-outline")}Verkosten</button>` });
}

// ---------------------------------------------------------------- Rezept (geplant)
function rezept(p, s, d) {
  const malz = d.malz.map((m) => `<tr><td>${esc(m.name)}</td><td>${fmt(m.menge_kg, 2)} kg</td><td class="hide-narrow">${fmt(m.prozent, 0)} %</td></tr>`).join("");
  const rasten = d.maischplan.map((m) => `<tr><td>${esc(m.name)}</td><td>${fmt(m.temp_rast, 0)} °C</td><td>${m.dauer > 1 ? `${m.dauer} min` : ""}</td></tr>`).join("");
  const hopfen = d.hopfen.map((h) => `<tr><td>${esc(h.name)}</td><td>${fmt(h.menge_g, 0)} g</td><td>${esc(h.zeitpunkt_text)}${h.zeitpunkt === 3 || h.zeitpunkt === 0 ? `, ${h.zeit} min` : ""}</td></tr>`).join("");
  const zt = d.zutaten.map((z) => `<tr><td>${esc(z.name)}</td><td>${fmt(z.menge, 0)} ${esc(z.einheit)}</td><td>${esc(z.zeitpunkt_text)}</td></tr>`).join("");
  return `
    ${malz ? card("Schüttung", "barley", `<table class="nums"><tbody>${malz}</tbody></table>
      ${d.schuettung > 0 ? `<p class="muted" style="margin:10px 0 0">Gesamt ${fmt(d.schuettung, 2)} kg, Hauptguss ${fmt(d.hauptguss, 1)} l, Nachguss ${fmt(d.nachguss, 1)} l</p>` : ""}`) : ""}
    ${rasten ? card("Maischplan", "pot-mix-outline", `<table class="nums"><tbody>${rasten}</tbody></table>`) : ""}
    ${hopfen ? card("Hopfen", "hops", `<table class="nums"><tbody>${hopfen}</tbody></table><p class="muted" style="margin:10px 0 0">Kochdauer ${d.kochdauer} min</p>`) : ""}
    ${zt ? card("Weitere Zutaten", "flask-outline", `<table class="nums"><tbody>${zt}</tbody></table>`) : ""}
    ${p.entry.einstellungen?.lager ? lagerKarte(s) : ""}
`;
}

// ---------------------------------------------------------------- Lebenslauf
function lebenslauf(p, s, d) {
  const ev = [];
  const add = (zeit, ic, was, detail = "", zukunft = false) => {
    const t = typeof zeit === "string" ? parseDate(zeit) : zeit;
    if (t) ev.push({ t, ic, was, detail, zukunft: zukunft || t.getTime() > Date.now() });
  };
  add(d.erstellt, "file-document-outline", "Rezept angelegt");
  const brau = parseDate(d.braudatum);
  if (brau) {
    add(brau, "kettle-steam-outline", "Brautag",
      `Angestellt mit ${fmt(d.sw_ist, 1)} °P${d.bemerkung_brauen ? `. ${esc(d.bemerkung_brauen)}` : ""}`);
    d.hefe.filter((h) => h.zugegeben).forEach((h) =>
      add(new Date(brau.getTime() + h.zugabe_nach_tagen * 864e5 + 60000), "bacteria-outline", `Hefe angestellt`, esc(h.name)));
  }
  d.zutaten.filter((z) => z.zeitpunkt === 0).forEach((z) => {
    const art = z.hopfen ? "Hopfenstopfen" : "Zutat";
    if (z.status === 0 && z.zugabe_datum) add(z.zugabe_datum, z.hopfen ? "hops" : "flask-outline", `${art} geplant`, `${fmt(z.menge, 0)} ${esc(z.einheit)} ${esc(z.name)}`, true);
    if (z.status >= 1 && z.zugabe_datum) add(z.zugabe_datum, z.hopfen ? "hops" : "flask-outline", `${art} zugegeben`, `${fmt(z.menge, 0)} ${esc(z.einheit)} ${esc(z.name)}`);
    if (z.status === 2 && z.entnahme_datum) add(z.entnahme_datum, "tray-arrow-up", `${esc(z.name)} entnommen`);
    if (z.status === 1 && z.mit_entnahme && z.entnahme_datum) add(z.entnahme_datum, "tray-arrow-up", `${esc(z.name)} entnehmen`, "", true);
  });
  const hgv = (d.hauptgaerverlauf || []).filter((m) => m.zeit);
  if (hgv.length > 1) {
    const ziel = hgv.find((m) => vg(d.sw_ist, m.restextrakt) >= d.vergaerungsgrad - 1);
    if (ziel) add(ziel.zeit, "flag-outline", "Ziel-Vergärung erreicht", `${fmt(ziel.restextrakt, 1)} °P, ${fmt(vg(d.sw_ist, ziel.restextrakt), 0)} %`);
    add(hgv[hgv.length - 1].zeit, "chart-line", "Letzter Messwert der Hauptgärung", `${fmt(hgv[hgv.length - 1].restextrakt, 2)} °P, ${hgv.length} Messwerte`);
  }
  (d.schnellgaerverlauf || []).forEach((m) => add(m.zeit, "test-tube", "Schnellgärprobe", `${fmt(m.restextrakt, 2)} °P`));
  if (d.abfuelldatum) {
    add(d.abfuelldatum, "flag-checkered", "Gärung fertig, abgefüllt");
    if (d.reifezeit_wochen) {
      const reif = new Date(parseDate(d.reifung_start || d.abfuelldatum).getTime() + d.reifezeit_wochen * 7 * 864e5);
      add(reif, "calendar-star", "Reif laut Rezept", `nach ${d.reifezeit_wochen} Wochen Reifung`);
    }
  }
  (d.faesser || []).forEach((f) => {
    (f.historie || []).forEach((h) => {
      if (h.typ === "fuellen") add(h.zeit, "keg", `Fass ${esc(f.name)} gefüllt`, `${fmt(h.liter, 1)} l`);
      if (h.typ === "wiegen") add(h.zeit, "scale", `Fass ${esc(f.name)} gewogen`, `noch ${fmt(h.rest, 1)} l`);
    });
    const leerEv = (f.historie || []).find((h) => h.rest <= 0.05 && h.typ !== "fuellen");
    if (leerEv) add(leerEv.zeit, "keg", `Fass ${esc(f.name)} leer`);
    const glaeser = (f.historie || []).filter((h) => h.typ === "glas");
    if (glaeser.length) add(glaeser[0].zeit, "glass-mug-variant", `Erstes Glas aus ${esc(f.name)}`, `${glaeser.length} Gläser bisher`);
  });
  (d.bewertungen || []).forEach((b) => add(b.datum, "star-outline", `Verkostung, ${b.sterne} von 5 Sternen`, esc(b.bemerkung || "")));
  (d.lager_buchungen || []).forEach((b) => add(b.zeit, "archive-arrow-down-outline",
    b.zurueck ? "Lager gutgeschrieben" : b.anlass === "brautag" ? "Rohstoffe vom Lager abgezogen" : "Zugabe vom Lager abgezogen",
    b.posten.map((x) => `${fmt(x.menge, x.typ === "malz" ? 2 : 0)} ${x.typ === "malz" ? "kg" : x.typ === "hefe" ? "Stk" : "g"} ${esc(x.name)}`).join(", ")));

  ev.sort((a, b) => a.t - b.t);
  const heute = { t: new Date(), heute: true };
  const idx = ev.findIndex((x) => x.t.getTime() > Date.now());
  if (idx >= 0) ev.splice(idx, 0, heute);
  return card("Lebenslauf", "timeline-clock-outline", ev.length ? `<ol class="timeline">${ev.map((x) => x.heute
    ? `<li class="heute"><span class="knoten">${icon("calendar-today")}</span><div><p class="was">Heute</p></div></li>`
    : `<li class="${x.zukunft ? "zukunft" : ""}"><span class="knoten">${icon(x.ic)}</span>
      <div><p class="wann">${dfDate.format(x.t)}</p><p class="was">${x.was}</p>${x.detail ? `<p class="detail">${x.detail}</p>` : ""}</div></li>`).join("")}</ol>`
    : `<p class="muted" style="margin:0">Noch keine Ereignisse.</p>`);
}

function lagerKarte(s) {
  const f = s.lager_fehlt || [];
  const einh = (x) => (x.einheit === "kg" ? 2 : 0);
  const inhalt = f.length
    ? `<ul class="zeilen">${f.map((x) => `<li><span class="rund" style="background:color-mix(in srgb, var(--warn) 14%, transparent)">${icon("alert-outline")}</span>
        <div class="text"><b>${esc(x.name)}</b><p class="muted">${x.gefunden ? `es fehlen ${fmt(x.fehlt, einh(x))} ${esc(x.einheit)}` : "steht nicht im Lager (anderer Name?)"}</p></div></li>`).join("")}</ul>`
    : `<p class="muted" style="margin:0">Alles da – das Lager reicht für diesen Sud.</p>`;
  return card("Lager", "archive-outline", inhalt, f.length ? {
    aktionen: `<button class="btn" data-action="einkaufsliste" data-sud="${s.id}">${icon("cart-plus")}Auf die Einkaufsliste</button>`,
  } : {});
}

const SEKTIONEN = { gaerung, zutaten, gaerschrank, faesser, nachgaerung, verkostung, rezept, lebenslauf };

// ---------------------------------------------------------------- Aktionen
export const actions = {
  "pill-start": (p, btn, id) => {
    const sel = p.shadowRoot.querySelector(`select[data-pill-sud="${id}"]`);
    const pill = p.entry.pills.find((x) => x.gravity === (sel?.value || p.pillChoice[id]));
    if (!pill) return;
    p.run(`start:${id}`, id, async () => {
      const r = await p.ws("aufzeichnung_starten", { sud_id: id, gravity: pill.gravity, temperature: pill.temperature, name: pill.name });
      p.msg[id] = r.warnung ? { ok: false, text: `Aufzeichnung läuft, der erste Wert fehlt aber: ${r.warnung}` }
        : { ok: true, text: "Aufzeichnung gestartet, erster Messwert eingetragen." };
    });
  },
  "pill-stop": (p, btn, id) => p.run(`stop:${id}`, id, () => p.ws("aufzeichnung_beenden", { sud_id: id }), { erfolg: "Aufzeichnung beendet." }),
  "pill-log": (p, btn, id) => p.run(`log:${id}`, id, async () => {
    await p.ws("eintragen", { sud_id: id });
    p.msg[id] = { ok: true, text: "Messwert eingetragen." };
  }),
  mehr: (p, btn) => {
    p.expanded[btn.dataset.key] = !p.expanded[btn.dataset.key];
    p.render();
  },
  zutat: async (p, btn, id) => {
    const zugeben = btn.dataset.art === "zugeben";
    const sudId = p.view.id;
    await p.run(`zutat:${btn.dataset.id}`, undefined,
      () => p.ws("zutat", { zutat_id: Number(btn.dataset.id), aktion: btn.dataset.art }),
      { erfolg: zugeben ? "Als zugegeben eingetragen." : "Als entnommen eingetragen." });
    // Wie im Brauhelfer: Zutaten zur Gärung werden erst bei der Zugabe vom Lager abgezogen
    if (zugeben && p.entry?.einstellungen?.lager) p.openDialog("lager", { sudId, anlass: "zugabe", art: "zutat", itemId: Number(btn.dataset.id) });
  },
  hefe: async (p, btn) => {
    const sudId = p.view.id;
    await p.run(`hefe:${btn.dataset.id}`, undefined, () => p.ws("hefe", { hefe_id: Number(btn.dataset.id) }), { erfolg: "Hefe als zugegeben eingetragen." });
    const h = p.details[sudId]?.hefe?.find((x) => x.id === Number(btn.dataset.id));
    // Hefe ab Tag 0 ist schon beim Brauen abgezogen; nur spätere Gaben hier
    if (p.entry?.einstellungen?.lager && h && h.zugabe_nach_tagen > 0) p.openDialog("lager", { sudId, anlass: "zugabe", art: "hefe", itemId: h.id });
  },
  einkaufsliste: (p, btn, id) => p.run(`ekl:${id}`, undefined, async () => {
    const r = await p.ws("einkaufsliste", { sud_id: id });
    p.toast(r.neu ? `${r.neu} ${r.neu === 1 ? "Eintrag" : "Einträge"} auf die Einkaufsliste gesetzt.` : "Steht schon alles auf der Einkaufsliste.");
  }),
  "regelung-aktiv": (p, btn, id) => {
    const an = btn.getAttribute("aria-checked") !== "true";
    p.run(`reg:${id}`, undefined, () => p.ws("regelung", { sud_id: id, aktiv: an }), { erfolg: an ? "Regelung läuft." : "Regelung pausiert, Steckdosen aus." });
  },
  "fass-glas": (p, btn) => p.run(`glas:${btn.dataset.fass}`, undefined,
    () => p.ws("fass", { aktion: "glas", fass_id: btn.dataset.fass, liter: Number(btn.dataset.liter) }), { erfolg: "Glas abgezogen. Prost!" }),
  "tag-weg": (p, btn) => p.run("tag", undefined, () => p.ws("tag", { aktion: "entfernen", tag_id: btn.dataset.tag }), { erfolg: "NFC-Tag entfernt." }),
};
