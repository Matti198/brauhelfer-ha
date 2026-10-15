// Einstellungen: Meldungen und Gärschränke
import { esc, icon, fmt, fmtInput, numIn, parseDate, dfDate } from "./lib.js";

const EREIGNISSE = [
  ["stagnation", "Gärung steht", "kein Fortschritt über längere Zeit – fertig?"],
  ["ziel_vg", "Ziel-Vergärungsgrad erreicht", ""],
  ["temperatur", "Temperatur außerhalb des Bereichs", "nur bei Suden mit Gärschrank-Regelung"],
  ["pill_offline", "Pill sendet nicht mehr", ""],
  ["akku", "Akku der Pill schwach", ""],
  ["zutaten", "Hopfenstopfen und Zutaten fällig", "Zugabe und Entnahme"],
  ["fass", "Fass fast leer oder leer", ""],
  ["brautag", "Brautag-Timer und Hopfengaben", "kommen auch als Ansage über die Lautsprecher"],
  ["gaerschrank", "Gärschrank: Stufenwechsel und Sensorausfall", ""],
];

function name(id) {
  return id.replace(/^mobile_app_/, "").replace(/_/g, " ");
}

const LAUTSTAERKEN = [null, 20, 30, 40, 50, 60, 70, 80];

export function render(p) {
  const e = p.entry;
  // Standardwerte, falls das Backend (noch) eine ältere Version ist
  const cfg = { ziele: [], lautsprecher: [], tts: null, lautstaerke: null, ereignisse: {}, ...(e.benachrichtigung || {}) };
  const aw = p.auswahl;
  const notify = aw?.notify || [];
  const push = notify;
  const check = (liste, wert, gruppe, label, sub) => `<button class="switch" role="switch" aria-checked="${liste.includes(wert)}" data-action="cfg-ziel" data-gruppe="${gruppe}" data-wert="${esc(wert)}">
    <span class="knob"></span><span>${esc(label)}<br><span class="muted">${esc(sub)}</span></span></button>`;
  const lautsprecher = aw?.lautsprecher || [];
  const engines = aw?.tts || [];
  const ansage = !aw ? `<p class="muted">Lade …</p>`
    : !lautsprecher.length ? `<p class="muted">Keine Lautsprecher gefunden. Sonos- oder Music-Assistant-Player erscheinen hier automatisch.</p>`
    : `${cfg.lautsprecher.length ? `<ul class="zeilen">${cfg.lautsprecher.map((id) => {
        const l = lautsprecher.find((x) => x.id === id);
        return `<li><span class="rund">${icon("speaker")}</span>
          <div class="text"><b>${esc(l ? l.name : id)}</b>${l?.quelle ? `<span class="muted"> · ${esc(l.quelle)}</span>` : ""}
            <p class="muted">${!l ? "nicht gefunden" : l.ankuendigen ? "Musik wird für die Ansage leiser" : "unterbricht laufende Musik"}</p></div>
          <button class="btn klein quiet" data-action="cfg-ziel" data-gruppe="lautsprecher" data-wert="${esc(id)}" aria-label="${esc(l ? l.name : id)} entfernen">${icon("close")}</button></li>`;
      }).join("")}</ul>` : ""}
      <label class="feld" style="margin-top:8px"><span>${cfg.lautsprecher.length ? "Weiteren Lautsprecher hinzufügen" : "Lautsprecher auswählen"}</span>
        <select data-cfg-lautsprecher><option value="">–</option>
          ${lautsprecher.filter((l) => !cfg.lautsprecher.includes(l.id)).map((l) =>
            `<option value="${esc(l.id)}">${esc(l.name)}${l.quelle ? ` (${esc(l.quelle)})` : ""}</option>`).join("")}
        </select></label>
      ${!engines.length ? `<p class="warn-box" style="margin-top:10px">Keine Sprachausgabe gefunden. Richte unter Einstellungen → Sprachassistenten eine TTS-Engine ein (z. B. Piper oder Home Assistant Cloud).</p>`
        : `<div class="felder" style="margin-top:12px">
        <label class="feld"><span>Stimme (TTS)</span><select data-cfg-sel="tts">
          ${engines.map((t) => `<option value="${esc(t.id)}" ${(cfg.tts || engines[0].id) === t.id ? "selected" : ""}>${esc(t.name)}</option>`).join("")}
        </select></label>
        <label class="feld"><span>Lautstärke der Ansage</span><select data-cfg-sel="lautstaerke">
          ${LAUTSTAERKEN.map((v) => `<option value="${v ?? ""}" ${(cfg.lautstaerke ?? null) === v ? "selected" : ""}>${v ? `${v} %` : "wie am Lautsprecher"}</option>`).join("")}
        </select></label></div>`}`;
  const zahl = (k, label, unit) => `<label class="feld"><span>${label}</span><span class="eingabe">
    <input inputmode="decimal" data-cfg="${k}" value="${esc(fmtInput(cfg[k]))}"><em>${unit}</em></span></label>`;

  const meldungen = `<ha-card>
    <div class="card-head"><h3>${icon("bell-outline")}Meldungen</h3></div>
    <div class="card-body">
      <h3 style="margin:0 0 6px">Push aufs Handy</h3>
      ${aw ? (push.length ? `<div class="liste-check">${push.map((n) => check(cfg.ziele, n, "ziele", name(n), `notify.${n}`)).join("")}</div>`
        : `<p class="muted">Keine Handys gefunden. Installiere die Home-Assistant-App auf dem iPhone und melde dich an, dann erscheint hier „mobile_app_…“.</p>`)
        : `<p class="muted">Lade …</p>`}
      ${!cfg.ziele.length ? `<p class="muted" style="margin-top:6px">Ohne Auswahl erscheinen Meldungen nur in Home Assistant unter Benachrichtigungen.</p>` : ""}
      <h3 style="margin:18px 0 2px">Ansagen am Brautag</h3>
      <p class="muted" style="margin:0 0 6px">Timer und Hopfengaben werden angesagt. Bei Sonos und Music Assistant wird laufende Musik dafür nur kurz leiser. Steht ein Lautsprecher doppelt da (Sonos und Music Assistant), nur einen davon wählen.</p>
      ${ansage}
      <h3 style="margin:18px 0 6px">Worüber melden</h3>
      <div class="liste-check">${EREIGNISSE.map(([k, t, h]) => `<button class="switch" role="switch" aria-checked="${!!cfg.ereignisse[k]}" data-action="cfg-ereignis" data-key="${k}">
        <span class="knob"></span><span>${t}${h ? `<br><span class="muted">${h}</span>` : ""}</span></button>`).join("")}</div>
      <h3 style="margin:18px 0 10px">Schwellen</h3>
      <div class="felder">
        ${zahl("stagnation_h", "Gärung steht nach", "h")}
        ${zahl("stagnation_plato", "…wenn Änderung unter", "°P")}
        ${zahl("temp_toleranz", "Temperatur-Toleranz", "°C")}
        ${zahl("temp_dauer_min", "…länger als", "min")}
        ${zahl("akku_prozent", "Akku schwach unter", "%")}
        ${zahl("fass_rest_l", "Fass fast leer unter", "l")}
      </div>
    </div>
    <div class="card-actions">
      <button class="btn quiet" data-action="cfg-test">${icon("bell-ring-outline")}Testmeldung</button>
      ${cfg.lautsprecher.length ? `<button class="btn quiet" data-action="cfg-test" data-ansage="1">${icon("bullhorn-outline")}Testansage</button>` : ""}
      <button class="btn primary" data-action="cfg-speichern">${icon("content-save-outline")}Schwellen speichern</button>
    </div>
  </ha-card>`;

  const est = e.einstellungen || {};
  const todos = aw?.todo || [];
  const lager = `<ha-card>
    <div class="card-head"><h3>${icon("archive-outline")}Lager</h3></div>
    <div class="card-body">
      <button class="switch" role="switch" aria-checked="${!!est.lager}" data-action="cfg-lager">
        <span class="knob"></span><span>Lager führen<br><span class="muted">Nach „Sud gebraut“ und beim Zugeben von Hopfen, Zutaten und später Hefe die Mengen vom Lager im Brauhelfer abziehen – wie die Lagerverwaltung im Programm.</span></span></button>
      ${est.lager ? `<div class="felder" style="margin-top:14px">
        <label class="feld"><span>Einkaufsliste für fehlende Rohstoffe</span><select data-cfg-einkauf>
          <option value="">${todos.some((t) => t.id === "todo.shopping_list") ? "Einkaufsliste (Standard)" : "– automatisch –"}</option>
          ${todos.map((t) => `<option value="${esc(t.id)}" ${est.einkaufsliste === t.id ? "selected" : ""}>${esc(t.name)}</option>`).join("")}
        </select></label></div>` : ""}
    </div>
  </ha-card>`;

  const GLAETTUNG = [0, 10, 30, 60, 120];
  const pill = `<ha-card>
    <div class="card-head"><h3>${icon("test-tube")}Pill</h3></div>
    <div class="card-body">
      <div class="felder">
        <label class="feld"><span>Werte glätten</span><select data-cfg-glaettung>
          ${GLAETTUNG.map((g) => `<option value="${g}" ${(est.glaettung_min ?? 30) === g ? "selected" : ""}>${g ? `über ${g} min` : "aus"}</option>`).join("")}
        </select></label>
      </div>
      <p class="muted" style="margin:10px 0 0">Beim Eintragen in den Gärverlauf nimmt Home Assistant den Median der Pill-Werte aus diesem Zeitraum. Einzelne Ausreißer landen so nicht in der Kurve. Den Abgleich mit einer Spindel machst du beim Sud unter „Aufzeichnung → Abgleichen“.</p>
    </div>
  </ha-card>`;

  const schraenke = `<ha-card>
    <div class="card-head"><h3>${icon("fridge-industrial-outline")}Gärschränke</h3></div>
    <div class="card-body">
      ${e.schraenke.length ? `<ul class="zeilen">${e.schraenke.map((s) => {
        const st = e.schrank_status[s.id] || {};
        const sud = st.sud_id ? p.sudById(st.sud_id) : null;
        return `<li><span class="rund">${icon("fridge-industrial-outline")}</span>
          <div class="text"><b>${esc(s.name)}</b>
            <p class="muted">${st.ist !== null && st.ist !== undefined ? `${fmt(st.ist, 1)} °C, ` : ""}${esc(st.modus_text || "")}${sud ? ` für „${esc(sud.name)}“` : ""}</p>
            <p class="muted">Kühlung ${esc(s.kuehlung || "–")}, Heizung ${esc(s.heizung || "–")}</p></div>
          <button class="btn klein" data-action="dialog" data-typ="schrank" data-extra='${JSON.stringify({ schrankId: s.id })}'>${icon("pencil-outline")}Bearbeiten</button></li>`;
      }).join("")}</ul>` : `<p class="muted" style="margin:0">Ein Gärschrank besteht aus einem Temperatursensor und schaltbaren Steckdosen für Kühlung (z. B. Kühlschrank) und Heizung (z. B. Heizmatte). Zuordnen und Temperaturprofil legst du dann beim Sud fest.</p>`}
    </div>
    <div class="card-actions"><button class="btn primary" data-action="dialog" data-typ="schrank">${icon("plus")}Gärschrank anlegen</button></div>
  </ha-card>`;

  const geaendert = parseDate(e.geaendert);
  return meldungen + pill + lager + schraenke + `<footer>Datenbank ${esc(e.path)}, Version ${e.db_version}, zuletzt geändert ${geaendert ? dfDate.format(geaendert) : "–"}.<br>
    Intervall der Pill-Aufzeichnung, Höchstalter der Werte und Sicherungen stellst du bei der Integration unter „Konfigurieren“ ein.</footer>`;
}

async function speichern(p, cfg, text) {
  try {
    await p.ws("einstellungen", { benachrichtigung: cfg });
    if (text) p.toast(text);
  } catch (err) {
    p.toast(err?.message || String(err));
  }
  await p.fetch();
}

export const actions = {
  "cfg-ziel": (p, btn) => {
    const cfg = p.entry.benachrichtigung;
    const gruppe = btn.dataset.gruppe;
    const liste = new Set(cfg[gruppe] || []);
    if (liste.has(btn.dataset.wert)) liste.delete(btn.dataset.wert);
    else liste.add(btn.dataset.wert);
    speichern(p, { [gruppe]: [...liste] });
  },
  "cfg-ereignis": (p, btn) => {
    const k = btn.dataset.key;
    speichern(p, { ereignisse: { [k]: !p.entry.benachrichtigung.ereignisse[k] } });
  },
  "cfg-speichern": (p) => {
    const out = {};
    let bad = false;
    p.shadowRoot.querySelectorAll("[data-cfg]").forEach((inp) => {
      const v = numIn(inp.value);
      if (Number.isNaN(v)) bad = true;
      else out[inp.dataset.cfg] = v;
    });
    if (bad) {
      p.toast("Bitte überall eine Zahl eintragen.");
      return;
    }
    speichern(p, out, "Gespeichert.");
  },
  "cfg-lager": async (p) => {
    try {
      await p.ws("einstellungen", { einstellungen: { lager: !p.entry.einstellungen?.lager } });
    } catch (err) {
      p.toast(err?.message || String(err));
    }
    await p.fetch();
  },
  "cfg-test": async (p, btn) => {
    try {
      await p.ws("test_meldung", { ansage: btn.dataset.ansage === "1" });
      p.toast(btn.dataset.ansage ? "Testansage gesendet." : "Testmeldung gesendet.");
    } catch (err) {
      p.toast(err?.message || String(err));
    }
  },
};

export function change(p, ev) {
  const gl = ev.target.closest?.("select[data-cfg-glaettung]");
  if (gl) {
    p.ws("einstellungen", { einstellungen: { glaettung_min: Number(gl.value) } })
      .then(() => { p.toast("Gespeichert."); return p.fetch(); })
      .catch((err) => p.toast(err?.message || String(err)));
    return;
  }
  const ls = ev.target.closest?.("select[data-cfg-lautsprecher]");
  if (ls) {
    if (ls.value) speichern(p, { lautsprecher: [...(p.entry.benachrichtigung.lautsprecher || []), ls.value] }, "Lautsprecher hinzugefügt.");
    return;
  }
  const cs = ev.target.closest?.("select[data-cfg-sel]");
  if (cs) {
    const k = cs.dataset.cfgSel;
    speichern(p, { [k]: k === "lautstaerke" ? (cs.value ? Number(cs.value) : null) : cs.value || null }, "Gespeichert.");
    return;
  }
  const sel = ev.target.closest?.("select[data-cfg-einkauf]");
  if (!sel) return;
  p.ws("einstellungen", { einstellungen: { einkaufsliste: sel.value || null } })
    .then(() => { p.toast("Einkaufsliste gespeichert."); return p.fetch(); })
    .catch((err) => p.toast(err?.message || String(err)));
}
