// Übersicht: Geplant → Gärung → Gebraut
import { esc, icon, fmt, ebcColor, lineColor, glassSvg, sparkline, parseDate, daysSince, dfLong, vg } from "./lib.js";
import { prognoseText } from "./view-sud.js";

const ALT_TAGE = 60;

export function render(p) {
  const e = p.entry;
  const tab = (key, label, n) => `<button role="tab" data-action="tab" data-tab="${key}" aria-selected="${p.tab === key}">
    ${label} <span class="count">${n}</span></button>`;
  const tabs = `<nav class="tabs" role="tablist">
    ${tab("geplant", "Geplant", e.geplant.length)}${tab("gaerung", "Gärung", e.gaerend.length)}${tab("gebraut", "Gebraut", e.abgefuellt.length)}</nav>`;
  let body;
  if (p.tab === "geplant") body = geplant(p, e);
  else if (p.tab === "gebraut") body = gebraut(p, e);
  else body = gaerung(p, e);
  return `${tabs}${body}`;
}

function leer(ic, gross, text) {
  return `<div class="empty">${icon(ic)}<p class="gross">${gross}</p><p class="muted">${text}</p></div>`;
}

// ---------------------------------------------------------------- Geplant
function geplant(p, e) {
  if (!e.geplant.length) {
    return leer("clipboard-text-outline", "Keine Rezepte auf der Merkliste.",
      "Setz im Brauhelfer bei einem Rezept den Haken „Merken“, dann erscheint es hier.");
  }
  const bt = e.brautag;
  return `<div class="sudliste">${e.geplant.map((s) => {
    const c = ebcColor(s.ebc);
    const laeuft = bt && bt.sud_id === s.id;
    const badges = [];
    if (laeuft) badges.push(`<span class="badge live">${icon("timer-outline")}Brautag läuft</span>`);
    if (e.einstellungen?.lager) {
      badges.push(s.lager_fehlt?.length
        ? `<span class="badge warn">${icon("archive-alert-outline")}${s.lager_fehlt.length} ${s.lager_fehlt.length === 1 ? "Rohstoff fehlt" : "Rohstoffe fehlen"}</span>`
        : `<span class="badge live">${icon("archive-check-outline")}Lager reicht</span>`);
    }
    return `<ha-card style="--beer:${c}">
      <button class="sudkarte" data-action="open-sud" data-sud="${s.id}" aria-label="${esc(s.name)}: Rezept öffnen">
        ${glassSvg(c, 1, { size: 76 })}
        <div class="titel">
          <h2>${esc(s.name)}</h2>
          <p class="meta">${esc(s.kategorie || "Rezept")}${s.hefe?.length ? `, ${s.hefe.map(esc).join(", ")}` : ""}</p>
        </div>
        <div class="rechts">${icon("chevron-right", "chev")}</div>
        <dl class="kpis">
          <div><dt>Stammwürze</dt><dd>${fmt(s.sw_rezept, 1)}<small> °P</small></dd></div>
          <div><dt>Menge</dt><dd>${fmt(s.menge, 0)}<small> l</small></dd></div>
          <div><dt>Bittere</dt><dd>${fmt(s.ibu, 0)}<small> IBU</small></dd></div>
          <div><dt>Alkohol</dt><dd>${s.alkohol_rezept ? `${fmt(s.alkohol_rezept, 1)}<small> %</small>` : "–"}</dd></div>
          <div class="hide-narrow"><dt>Farbe</dt><dd>${fmt(s.ebc, 0)}<small> EBC</small></dd></div>
        </dl>
        ${badges.length ? `<div class="fortschritt reihe">${badges.join("")}</div>` : ""}
      </button>
      <div class="card-actions">
        <button class="btn" data-action="dialog" data-typ="braudaten" data-sud="${s.id}">${icon("pencil-outline")}Werte eintragen</button>
        <button class="btn primary" data-action="brautag-start" data-sud="${s.id}">${icon(laeuft ? "play" : "kettle-steam-outline")}${laeuft ? "Weiter brauen" : "Brautag starten"}</button>
      </div>
    </ha-card>`;
  }).join("")}</div>`;
}

// ---------------------------------------------------------------- Gärung
function gaerung(p, e) {
  if (!e.gaerend.length) {
    return leer("glass-mug-variant", "Gerade gärt nichts.",
      "Unter „Geplant“ einen Brautag starten – nach „Sud gebraut“ erscheint der Sud hier.");
  }
  const rec = e.aufzeichnungen;
  const order = [...e.gaerend].sort((a, b) =>
    (!!rec[b.id]) - (!!rec[a.id]) || (parseDate(b.braudatum)?.getTime() || 0) - (parseDate(a.braudatum)?.getTime() || 0));
  const dark = !!p.hass?.themes?.darkMode;
  return `<div class="sudliste">${order.map((s) => gaerKarte(p, e, s, dark)).join("")}</div>`;
}

function gaerKarte(p, e, s, dark) {
  const c = ebcColor(s.ebc);
  const lc = lineColor(c, dark);
  const last = s.verlauf?.[s.verlauf.length - 1];
  const tage = daysSince(parseDate(s.braudatum));
  const a = e.aufzeichnungen[String(s.id)];
  const live = a ? p.live(a) : null;
  const sre = live && live.fresh ? live.plato : last ? last.restextrakt : s.sw;
  const vgIst = vg(s.sw, sre);
  const ziel = s.vg_rezept || 0;
  const anteil = ziel > 0 ? Math.max(0, Math.min(1, vgIst / ziel)) : 0;
  const reg = e.regelung[String(s.id)];
  const schrank = reg?.schrank_id ? e.schraenke.find((x) => x.id === reg.schrank_id) : null;
  const sst = schrank ? e.schrank_status[schrank.id] : null;
  const badges = [];
  if (a) badges.push(live?.fresh ? `<span class="badge live">${icon("bluetooth")}${esc(a.name)}</span>` : `<span class="badge warn">${icon("bluetooth-off")}Pill ohne Werte</span>`);
  if (sst && sst.soll !== null && sst.soll !== undefined) {
    badges.push(`<span class="badge">${icon(sst.modus === "kuehlen" ? "snowflake" : sst.modus === "heizen" ? "fire" : "thermometer")}${fmt(sst.ist, 1)} / ${fmt(sst.soll, 1)} °C</span>`);
  }
  if (tage !== null && tage > ALT_TAGE) badges.push(`<span class="badge warn">${icon("alert-outline")}seit ${tage} Tagen</span>`);
  return `<ha-card style="--beer:${c};--line:${lc}">
    <button class="sudkarte" data-action="open-sud" data-sud="${s.id}" aria-label="${esc(s.name)} öffnen">
      ${glassSvg(c, anteil, { size: 84, bubbles: !!(live && live.fresh) })}
      <div class="titel">
        <h2>${esc(s.name)}</h2>
        <p class="meta">${tage !== null ? `Tag ${tage}` : ""}${s.kategorie ? `, ${esc(s.kategorie)}` : ""}</p>
      </div>
      <div class="rechts">${sparkline(s.verlauf, lc)}${icon("chevron-right", "chev")}</div>
      <dl class="kpis">
        <div><dt>Restextrakt</dt><dd>${fmt(sre, 1)}<small> °P</small></dd></div>
        <div><dt>Alkohol</dt><dd>${fmt(last ? last.alkohol : 0, 1)}<small> %</small></dd></div>
        <div><dt>Temperatur</dt><dd>${live && live.fresh && !Number.isNaN(live.temp) ? fmt(live.temp, 1) : last ? fmt(last.temperatur, 1) : "–"}<small> °C</small></dd></div>
      </dl>
      <div class="fortschritt">
        <div class="bar"><span style="width:${(anteil * 100).toFixed(0)}%"></span></div>
        <div class="bar-label"><span><b>${fmt(vgIst, 0)} %</b> vergoren</span><span>${anteil >= 1 ? "Ziel erreicht" : s.prognose ? `Ziel ${fmt(ziel, 0)} %, ${prognoseText(s.prognose, true)}` : `Ziel ${fmt(ziel, 0)} %`}</span></div>
        ${badges.length ? `<div class="reihe" style="margin-top:10px">${badges.join("")}</div>` : ""}
      </div>
    </button>
  </ha-card>`;
}

// ---------------------------------------------------------------- Gebraut
function gebraut(p, e) {
  if (!e.abgefuellt.length) {
    return leer("keg", "Noch nichts abgefüllt.", "Wenn eine Gärung fertig ist, erscheint der Sud hier, bis er leer ist.");
  }
  const alle = p.expanded.gebraut;
  const liste = alle ? e.abgefuellt : e.abgefuellt.slice(0, 8);
  const mehr = e.abgefuellt.length > 8
    ? `<button class="btn quiet" data-action="mehr-gebraut">${alle ? "Weniger anzeigen" : `Alle ${e.abgefuellt.length} anzeigen`}</button>` : "";
  return `<div class="sudliste">${liste.map((s) => {
    const c = ebcColor(s.ebc);
    const last = s.verlauf?.[s.verlauf.length - 1];
    const abf = parseDate(s.abfuelldatum);
    const tage = daysSince(abf);
    const faesser = e.faesser.filter((f) => f.sud_id === s.id);
    const rest = faesser.reduce((n, f) => n + (f.leer ? 0 : f.rest_l), 0);
    const voll = faesser.reduce((n, f) => n + f.inhalt_l, 0);
    const fassText = faesser.length
      ? `${fmt(rest, 1)} l in ${faesser.filter((f) => !f.leer).length} von ${faesser.length} ${faesser.length === 1 ? "Fass" : "Fässern"}`
      : "Kein Fass angelegt";
    return `<ha-card style="--beer:${c}">
      <button class="sudkarte" data-action="open-sud" data-sud="${s.id}" aria-label="${esc(s.name)} öffnen">
        ${glassSvg(c, voll ? rest / voll : 1, { size: 76 })}
        <div class="titel">
          <h2>${esc(s.name)}</h2>
          <p class="meta">${abf ? `abgefüllt am ${dfLong.format(abf)}${tage === 0 ? ", heute" : tage === 1 ? ", gestern" : tage !== null ? `, vor ${tage} Tagen` : ""}` : esc(s.kategorie || "")}</p>
        </div>
        <div class="rechts">${icon("chevron-right", "chev")}</div>
        <dl class="kpis">
          <div><dt>Stammwürze</dt><dd>${fmt(s.sw, 1)}<small> °P</small></dd></div>
          <div><dt>Alkohol</dt><dd>${last ? `${fmt(last.alkohol, 1)}<small> %</small>` : "–"}</dd></div>
          <div><dt>Vergärungsgrad</dt><dd>${last ? `${fmt(vg(s.sw, last.restextrakt), 0)}<small> %</small>` : "–"}</dd></div>
        </dl>
        <div class="fortschritt">${faesser.length ? `
          <div class="bar"><span style="width:${voll ? Math.round((rest / voll) * 100) : 0}%"></span></div>` : ""}
          <div class="bar-label"><span>${icon("keg")}${fassText}</span>${faesser.length && rest > 0 ? `<span>etwa ${fmt(Math.floor(rest / 0.5), 0)} Gläser</span>` : ""}</div>
        </div>
      </button>
    </ha-card>`;
  }).join("")}</div>${mehr}`;
}

export const actions = {
  "mehr-gebraut": (p) => {
    p.expanded.gebraut = !p.expanded.gebraut;
    p.render();
  },
  "brautag-start": (p, btn, id) => p.go("brautag", id),
};
