// Dialoge: jeweils open/render/actions. Formularwerte über name-Attribute (p.form()).
import { esc, icon, fmt, fmtInput, ebcColor, glassSvg, numIn, platoToDichte, sgToPlato, sterne, VERKOSTUNG, dfFull } from "./lib.js";

const val = (d, k, def = "") => (d.form[k] !== undefined ? d.form[k] : def);

function kopf(p, d, kicker, titel, fuell = 1) {
  const s = d.sudId !== undefined ? p.sudById(d.sudId) : null;
  return `<header class="dlg-head">${s ? glassSvg(ebcColor(s.ebc), fuell, { size: 56 }) : ""}
    <div><p class="dlg-kicker">${kicker}</p><h2 id="dlg-title">${esc(titel || s?.name || "")}</h2></div></header>`;
}

function aktionen(d, ...knoepfe) {
  return `<div class="dlg-actions"><button class="btn quiet" data-action="dlg:close" ${d.busy ? "disabled" : ""}>Abbrechen</button>
    ${knoepfe.map((k) => k.replace("<button", `<button ${d.busy ? "disabled" : ""}`)).join("")}</div>`;
}

function zahl(d, name, label, unit, def = "", ph = "") {
  return `<label class="feld"><span>${label}</span><span class="eingabe">
    <input name="${name}" inputmode="decimal" autocomplete="off" placeholder="${esc(ph)}" value="${esc(val(d, name, def))}"><em>${unit}</em></span></label>`;
}

function auswahl(d, name, label, liste, aktuell, leer = "– keine –") {
  const v = val(d, name, aktuell || "");
  return `<label class="feld"><span>${label}</span><select name="${name}">
    <option value="">${leer}</option>
    ${(liste || []).map((x) => `<option value="${esc(x.id)}" ${x.id === v ? "selected" : ""}>${esc(x.name)}</option>`).join("")}
    ${v && !(liste || []).some((x) => x.id === v) ? `<option value="${esc(v)}" selected>${esc(v)}</option>` : ""}
  </select></label>`;
}

function n(v, label) {
  const x = numIn(v);
  if (Number.isNaN(x)) throw new Error(`Bitte eine Zahl bei „${label}“ eintragen.`);
  return x;
}

const farbe = (p, d) => (d.sudId !== undefined && p.sudById(d.sudId) ? ebcColor(p.sudById(d.sudId).ebc) : null);

async function fertig(p, text) {
  p.closeDialog();
  if (text) p.toast(text);
  await p.fetch();
}

export const DIALOGE = {
  // ---------------------------------------------------------------- Braudaten (schnelles Formular)
  braudaten: {
    farbe,
    async open(p, d) {
      d.loading = true;
      try {
        d.daten = await p.ws("braudaten", { sud_id: d.sudId });
        const now = new Date();
        now.setSeconds(0, 0);
        d.form.braudatum = d.daten.braudatum ? d.daten.braudatum.slice(0, 16)
          : new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        d.form.bemerkung = d.daten.bemerkung;
        for (const [k, v] of Object.entries(d.daten.werte)) d.form[k] = fmtInput(v);
      } catch (err) {
        d.error = err?.message || String(err);
      }
      d.loading = false;
      p.renderDialog();
    },
    render(p, d) {
      const head = kopf(p, d, "Braudaten eintragen", null, 0.2);
      if (d.loading || !d.daten) return `${head}<p class="muted">${d.loading ? "Lade …" : ""}</p>`;
      const f = (k, label, unit) => zahl(d, k, label, unit);
      const w = Object.fromEntries(Object.keys(d.daten.werte).map((k) => [k, numIn(val(d, k))]));
      const sw = w.SWKochende - d.daten.wz_maischen_kochen;
      const sha = d.daten.schuettung > 0 && w.WuerzemengeVorHopfenseihen > 0
        ? (sw * platoToDichte(w.SWKochende) * w.WuerzemengeVorHopfenseihen) / d.daten.schuettung : null;
      return `${head}
        <p class="muted">Ohne Assistent: Werte direkt eintragen, z. B. nachträglich. Der Sud bleibt geplant, bis du „Sud gebraut“ wählst.</p>
        <form class="brautag-form" onsubmit="return false">
          <section><h3><span class="step">1</span>Kochbeginn</h3><div class="felder">${f("WuerzemengeKochbeginn", "Würzemenge", "l")}${f("SWKochbeginn", "Stammwürze", "°P")}</div></section>
          <section><h3><span class="step">2</span>Kochende</h3><div class="felder">${f("WuerzemengeVorHopfenseihen", "vor Hopfenseihen", "l")}${f("WuerzemengeKochende", "nach Hopfenseihen", "l")}${f("SWKochende", "Stammwürze", "°P")}</div></section>
          <section><h3><span class="step">3</span>Anstellen</h3><div class="felder">${f("SWAnstellen", "Stammwürze", "°P")}${f("WuerzemengeAnstellen", "Würzemenge", "l")}
            ${f("VerduennungAnstellen", "Verdünnung", "l")}${f("Speisemenge", "Speisemenge", "l")}${f("MengeHefestarter", "Hefestarter", "l")}${f("SWHefestarter", "SW Hefestarter", "°P")}</div></section>
          <dl class="info" data-info>
            <div><dt>Ziel Stammwürze</dt><dd>${fmt(d.daten.rezept.sw, 1)} °P</dd></div>
            <div><dt>Ziel Menge</dt><dd>${fmt(d.daten.rezept.menge_soll_anstellen, 1)} l</dd></div>
            <div><dt>Sudhausausbeute</dt><dd>${sha !== null && Number.isFinite(sha) ? `${fmt(sha, 1)} %` : "–"}</dd></div>
          </dl>
          <div class="felder" style="margin-top:14px">
            <label class="feld"><span>Braudatum</span><input type="datetime-local" name="braudatum" value="${esc(val(d, "braudatum"))}"></label>
            <label class="feld voll"><span>Bemerkung</span><textarea name="bemerkung" rows="2">${esc(val(d, "bemerkung"))}</textarea></label>
          </div>
        </form>
        ${d.confirm ? `<p class="confirm">Der Sud wird auf „gebraut“ gesetzt und erscheint unter Gärung.</p>` : ""}
        ${aktionen(d, `<button class="btn" data-action="dlg:speichern">Speichern</button>`,
          `<button class="btn primary" data-action="dlg:gebraut">${d.confirm ? "Ja, Sud gebraut" : "Sud gebraut"}</button>`)}`;
    },
    input(p, d) {
      p.keepForm();
      const el = p.shadowRoot.querySelector(".dialog [data-info]");
      if (!el) return;
      const tmp = document.createElement("div");
      tmp.innerHTML = this.render(p, d);
      el.innerHTML = tmp.querySelector("[data-info]").innerHTML;
    },
    actions: {
      speichern: (p, d) => DIALOGE.braudaten.save(p, d, false),
      gebraut: (p, d) => {
        if (!d.confirm) {
          p.keepForm();
          d.confirm = true;
          p.renderDialog();
          return;
        }
        DIALOGE.braudaten.save(p, d, true);
      },
    },
    save(p, d, gebraut) {
      p.dialogRun(async () => {
        const f = d.form;
        const werte = {};
        for (const k of Object.keys(d.daten.werte)) werte[k] = n(f[k], k);
        await p.ws("braudaten_speichern", { sud_id: d.sudId, werte, braudatum: f.braudatum || null, bemerkung: f.bemerkung ?? null, gebraut });
        if (gebraut) {
          p.tab = "gaerung";
          await fertig(p, "Sud gebraut, er steht jetzt unter Gärung.");
          p.go("sud", d.sudId);
          if (p.entry?.einstellungen?.lager) p.openDialog("lager", { sudId: d.sudId, anlass: "brautag" });
        } else await fertig(p, "Braudaten gespeichert.");
      });
    },
  },

  // ---------------------------------------------------------------- Gärung fertig
  fertig: {
    farbe,
    open(p, d) {
      const a = p.entry.aufzeichnungen[String(d.sudId)];
      const live = a ? p.live(a) : null;
      d.unit = "plato";
      if (live && !live.offline) {
        d.form.wert = fmtInput(Math.round(live.plato * 100) / 100);
        if (!Number.isNaN(live.temp)) d.form.temp = fmtInput(Math.round(live.temp * 10) / 10);
      }
    },
    render(p, d) {
      const sg = d.unit === "sg";
      return `${kopf(p, d, "Gärung fertig")}
        <p>Möchtest du einen letzten Dichtewert eintragen? Danach steht der Sud unter „Gebraut“, und eine laufende Aufzeichnung endet. Fässer legst du dort an.</p>
        <div class="seg" role="radiogroup" aria-label="Einheit">
          <button role="radio" aria-checked="${!sg}" data-action="dlg:unit" data-unit="plato">°Plato</button>
          <button role="radio" aria-checked="${sg}" data-action="dlg:unit" data-unit="sg">SG</button></div>
        <div class="felder">${zahl(d, "wert", sg ? "Spezifische Dichte" : "Restextrakt", sg ? "SG" : "°P", "", sg ? "1,010" : "2,6")}
          ${zahl(d, "temp", "Temperatur (optional)", "°C")}</div>
        ${aktionen(d, `<button class="btn" data-action="dlg:ohne">Ohne Wert beenden</button>`,
          `<button class="btn primary" data-action="dlg:mit">Wert eintragen und beenden</button>`)}`;
    },
    actions: {
      unit: (p, d, btn) => {
        p.keepForm();
        if (d.unit !== btn.dataset.unit) d.form.wert = "";
        d.unit = btn.dataset.unit;
        p.renderDialog();
      },
      ohne: (p, d) => DIALOGE.fertig.submit(p, d, false),
      mit: (p, d) => DIALOGE.fertig.submit(p, d, true),
    },
    submit(p, d, mit) {
      p.dialogRun(async () => {
        const f = d.form;
        const payload = { sud_id: d.sudId };
        if (mit) {
          const v = n(f.wert, d.unit === "sg" ? "Dichte" : "Restextrakt");
          payload[d.unit === "sg" ? "dichte" : "restextrakt"] = v;
          const t = numIn(f.temp);
          if (!Number.isNaN(t)) payload.temperatur = t;
        }
        await p.ws("abfuellen", payload);
        p.subtab[d.sudId] = "faesser";
        await fertig(p, "Gärung beendet. Leg jetzt die Fässer an.");
      });
    },
  },

  // ---------------------------------------------------------------- Pill abgleichen
  abgleich: {
    farbe,
    open(p, d) {
      d.unit = "plato";
      d.eintragen = true;
    },
    render(p, d) {
      const sg = d.unit === "sg";
      const a = p.entry.aufzeichnungen[String(d.sudId)];
      const live = a ? p.live(a) : null;
      const korr = a ? p.entry.korrekturen?.[a.gravity] : null;
      const korrT = a?.temperature ? p.entry.korrekturen?.[a.temperature] : null;
      const vz = (x, dd) => `${x >= 0 ? "+" : "−"}${fmt(Math.abs(x), dd)}`;
      return `${kopf(p, d, "Pill abgleichen")}
        <p>Miss eine Probe mit der <b>Spindel</b> und trag den Wert ein. Home Assistant rechnet die Abweichung der Pill aus und korrigiert damit alle weiteren Werte – auch die schon angezeigten.</p>
        <p class="hint">${icon("information-outline")}<span>Ein Refraktometer zeigt während der Gärung wegen des Alkohols zu hoch an. Dafür nur die Spindel nehmen, die Probe vorher entgasen und bei der Temperatur messen, auf die die Spindel geeicht ist.</span></p>
        <dl class="info" style="margin:0 0 14px">
          <div><dt>Pill zeigt gerade</dt><dd>${live && !live.offline ? `${fmt(live.plato, 2)} °P${live.sg ? ` (SG ${fmt(live.sg + 0, 3)})` : ""}` : "keinen Wert"}</dd></div>
          <div><dt>Korrektur Dichte</dt><dd>${korr ? `${vz(korr.wert, 2)} °P` : "keine"}</dd></div>
          ${a?.temperature ? `<div><dt>Korrektur Temperatur</dt><dd>${korrT ? `${vz(korrT.wert, 1)} °C` : "keine"}</dd></div>` : ""}
        </dl>
        <div class="seg" role="radiogroup" aria-label="Einheit">
          <button role="radio" aria-checked="${!sg}" data-action="dlg:unit" data-unit="plato">°Plato</button>
          <button role="radio" aria-checked="${sg}" data-action="dlg:unit" data-unit="sg">SG</button></div>
        <div class="felder">${zahl(d, "wert", sg ? "Spindel: Dichte" : "Spindel: Restextrakt", sg ? "SG" : "°P", "", sg ? "1,012" : "3,1")}
          ${a?.temperature ? zahl(d, "temp", "Thermometer (optional)", "°C") : ""}</div>
        <button class="switch" role="switch" aria-checked="${d.eintragen}" data-action="dlg:eintragen" style="margin-top:12px">
          <span class="knob"></span><span>Spindelwert auch in den Gärverlauf eintragen</span></button>
        ${aktionen(d, korr || korrT ? `<button class="btn" data-action="dlg:reset">Korrektur löschen</button>` : "",
          `<button class="btn primary" data-action="dlg:abgleichen">${icon("tune-variant")}Abgleichen</button>`)}`;
    },
    actions: {
      unit: (p, d, btn) => {
        p.keepForm();
        if (d.unit !== btn.dataset.unit) d.form.wert = "";
        d.unit = btn.dataset.unit;
        p.renderDialog();
      },
      eintragen: (p, d) => {
        p.keepForm();
        d.eintragen = !d.eintragen;
        p.renderDialog();
      },
      reset: (p, d) => p.dialogRun(async () => {
        await p.ws("pill_abgleich", { sud_id: d.sudId, zuruecksetzen: true });
        await fertig(p, "Korrektur gelöscht. Die Pill-Werte gelten wieder unverändert.");
      }),
      abgleichen: (p, d) => p.dialogRun(async () => {
        const f = d.form;
        const payload = { sud_id: d.sudId, eintragen: d.eintragen, referenz: "Spindel" };
        const w = numIn(f.wert);
        const t = numIn(f.temp);
        if (Number.isNaN(w) && Number.isNaN(t)) throw new Error("Bitte den Spindelwert eintragen.");
        if (!Number.isNaN(w)) payload[d.unit === "sg" ? "dichte" : "restextrakt"] = w;
        if (!Number.isNaN(t)) payload.temperatur = t;
        const r = await p.ws("pill_abgleich", payload);
        const teile = [];
        if (r.dichte !== null && r.dichte !== undefined) teile.push(`${r.dichte >= 0 ? "+" : "−"}${fmt(Math.abs(r.dichte), 2)} °P`);
        if (r.temperatur !== null && r.temperatur !== undefined) teile.push(`${r.temperatur >= 0 ? "+" : "−"}${fmt(Math.abs(r.temperatur), 1)} °C`);
        await fertig(p, `Pill abgeglichen: ${teile.join(", ")}.`);
      }),
    },
  },

  // ---------------------------------------------------------------- Leer
  leer: {
    farbe,
    render(p, d) {
      return `${kopf(p, d, "Leer", null, 0)}
        <p>Ist das letzte Bier getrunken? Der Sud wird im Brauhelfer auf „verbraucht“ gesetzt und verschwindet aus der Liste. Die Fässer werden mit entfernt.</p>
        ${aktionen(d, `<button class="btn primary" data-action="dlg:ok">Als leer markieren</button>`)}`;
    },
    actions: {
      ok: (p, d) => p.dialogRun(async () => {
        await p.ws("verbraucht", { sud_id: d.sudId });
        for (const f of p.entry.faesser.filter((x) => x.sud_id === d.sudId)) await p.ws("fass", { aktion: "loeschen", fass_id: f.id });
        const name = p.sudById(d.sudId)?.name;
        p.closeDialog();
        await p.fetch();
        p.go("liste");
        p.toast(`„${name}“ ist als leer markiert.`);
      }),
    },
  },

  // ---------------------------------------------------------------- Fass anlegen/bearbeiten
  fass: {
    farbe,
    open(p, d) {
      const f = d.fassId ? p.entry.faesser.find((x) => x.id === d.fassId) : null;
      d.fass = f;
      const anzahl = p.entry.faesser.filter((x) => x.sud_id === d.sudId).length;
      d.form = f ? { name: f.name, tara_kg: fmtInput(f.tara_kg), rest_l: fmtInput(Math.round(f.rest_l * 10) / 10), waage: f.waage || "" }
        : { name: `Fass ${anzahl + 1}`, tara_kg: "", inhalt_l: "", waage: "" };
      p.loadAuswahl();
    },
    render(p, d) {
      const f = d.fass;
      return `${kopf(p, d, f ? "Fass bearbeiten" : "Fass anlegen")}
        <div class="felder">
          <label class="feld"><span>Name</span><input name="name" value="${esc(val(d, "name"))}"></label>
          ${zahl(d, "tara_kg", "Leergewicht (Tara)", "kg", "", "4,2")}
          ${f ? zahl(d, "rest_l", "Inhalt jetzt", "l") : zahl(d, "inhalt_l", "Abgefüllt", "l", "", "19")}
          ${auswahl(d, "waage", "Waage (optional)", p.auswahl?.waage, f?.waage, "keine – von Hand eintippen")}
        </div>
        <p class="muted">Das Leergewicht wird beim Wiegen abgezogen. Aus dem Rest und der Dichte des Biers ergibt sich die Menge in Litern.</p>
        ${aktionen(d, f ? `<button class="btn danger" data-action="dlg:loeschen">${icon("delete-outline")}Löschen</button>` : "",
          `<button class="btn primary" data-action="dlg:ok">${f ? "Speichern" : "Anlegen"}</button>`)}`;
    },
    actions: {
      ok: (p, d) => p.dialogRun(async () => {
        const f = d.form;
        if (d.fass) {
          await p.ws("fass", { aktion: "bearbeiten", fass_id: d.fass.id, name: f.name, tara_kg: n(f.tara_kg, "Leergewicht"), rest_l: n(f.rest_l, "Inhalt"), waage: f.waage || null });
        } else {
          await p.ws("fass", { aktion: "anlegen", sud_id: d.sudId, name: f.name || "Fass", tara_kg: n(f.tara_kg, "Leergewicht"), inhalt_l: n(f.inhalt_l, "Abgefüllt"), waage: f.waage || null });
        }
        await fertig(p, d.fass ? "Fass gespeichert." : "Fass angelegt.");
      }),
      loeschen: (p, d) => {
        if (!d.sicher) {
          d.sicher = true;
          d.error = "Nochmal auf „Löschen“ tippen, um das Fass samt NFC-Tags zu entfernen.";
          p.keepForm();
          p.renderDialog();
          return;
        }
        p.dialogRun(async () => {
          await p.ws("fass", { aktion: "loeschen", fass_id: d.fass.id });
          await fertig(p, "Fass gelöscht.");
        });
      },
    },
  },

  // ---------------------------------------------------------------- Wiegen
  wiegen: {
    farbe,
    open(p, d) {
      d.fass = p.entry.faesser.find((x) => x.id === d.fassId);
      const st = d.fass?.waage ? p.hass.states[d.fass.waage] : null;
      const zahlWert = st ? Number(st.state) : NaN;
      d.waageName = st?.attributes.friendly_name || d.fass?.waage;
      d.waageWert = st ? `${Number.isNaN(zahlWert) ? st.state : fmt(zahlWert, 2)} ${st.attributes.unit_of_measurement || ""}`.trim() : null;
    },
    render(p, d) {
      const f = d.fass;
      return `${kopf(p, d, "Fass wiegen", f?.name)}
        <p>Leergewicht ${fmt(f.tara_kg, 2)} kg. Der Rest in Litern wird aus dem Gewicht und der Dichte des Biers berechnet.</p>
        ${f.waage ? `<p class="info" style="margin:0 0 12px">${icon("scale")}<span>${esc(d.waageName)} zeigt <b>${esc(d.waageWert || "keinen Wert")}</b></span></p>` : ""}
        <div class="felder">${zahl(d, "brutto", f.waage ? "Oder von Hand: Gesamtgewicht" : "Gesamtgewicht mit Fass", "kg", "", "14,3")}</div>
        ${aktionen(d, f.waage ? `<button class="btn" data-action="dlg:waage">${icon("scale")}Waage übernehmen</button>` : "",
          `<button class="btn primary" data-action="dlg:hand">Gewicht übernehmen</button>`)}`;
    },
    actions: {
      waage: (p, d) => DIALOGE.wiegen.submit(p, d, null),
      hand: (p, d) => DIALOGE.wiegen.submit(p, d, "hand"),
    },
    submit(p, d, art) {
      p.dialogRun(async () => {
        const brutto = art === "hand" ? n(d.form.brutto, "Gesamtgewicht") : undefined;
        const r = await p.ws("fass", { aktion: "wiegen", fass_id: d.fass.id, ...(brutto !== undefined ? { brutto_kg: brutto } : {}) });
        await fertig(p, `${r.fass.name}: noch ${fmt(r.fass.rest_l, 1)} l.`);
      });
    },
  },

  // ---------------------------------------------------------------- NFC-Tag
  tag: {
    farbe,
    async open(p, d) {
      d.fass = p.entry.faesser.find((x) => x.id === d.fassId);
      d.form = { glas: "0,5", name: "" };
      try {
        d.tags = await p.hass.callWS({ type: "tag/list" });
      } catch {
        d.tags = [];
      }
      p.renderDialog();
    },
    render(p, d) {
      const vergeben = new Set(p.entry.tags.map((t) => t.tag_id));
      const frei = (d.tags || []).filter((t) => !vergeben.has(t.id));
      return `${kopf(p, d, "NFC-Tag zuordnen", d.fass?.name)}
        <p>Jeder Scan dieses Tags mit der Home-Assistant-App zieht ein Glas vom Fass ab. Für verschiedene Gläser kannst du mehrere Tags anlegen.</p>
        <div class="felder">
          ${zahl(d, "glas", "Glasgröße", "l", "0,5")}
          <label class="feld"><span>Bezeichnung (optional)</span><input name="name" placeholder="z. B. Zapfhahn, Krug" value="${esc(val(d, "name"))}"></label>
          ${frei.length ? `<label class="feld voll"><span>Vorhandener Tag aus Home Assistant</span><select name="tag_id">
            <option value="">– neuen Tag scannen –</option>${frei.map((t) => `<option value="${esc(t.id)}" ${val(d, "tag_id") === t.id ? "selected" : ""}>${esc(t.name || t.id)}</option>`).join("")}</select></label>` : ""}
        </div>
        <p class="muted">Ohne Auswahl: auf „Scannen“ tippen und innerhalb von 3 Minuten den Tag mit dem iPhone scannen (in der HA-App unter Einstellungen → Tags oder per Kurzbefehl).</p>
        ${aktionen(d, `<button class="btn primary" data-action="dlg:ok">${icon("nfc-variant")}${val(d, "tag_id") ? "Zuordnen" : "Scannen"}</button>`)}`;
    },
    change(p, d) {
      p.keepForm();
      p.renderDialog();
    },
    actions: {
      ok: (p, d) => p.dialogRun(async () => {
        const glas = n(d.form.glas, "Glasgröße");
        if (d.form.tag_id) {
          await p.ws("tag", { aktion: "zuordnen", fass_id: d.fass.id, tag_id: d.form.tag_id, glas_l: glas, name: d.form.name || "" });
          await fertig(p, "NFC-Tag zugeordnet.");
        } else {
          await p.ws("tag", { aktion: "lernen", fass_id: d.fass.id, glas_l: glas, name: d.form.name || "" });
          await fertig(p, "Jetzt den Tag mit dem iPhone scannen.");
        }
      }),
    },
  },

  // ---------------------------------------------------------------- Schnellgärprobe
  schnellgaer: {
    farbe,
    open(p, d) { d.unit = "plato"; d.form.temp = "24"; },
    render(p, d) {
      const sg = d.unit === "sg";
      return `${kopf(p, d, "Schnellgärprobe")}
        <div class="seg" role="radiogroup" aria-label="Einheit">
          <button role="radio" aria-checked="${!sg}" data-action="dlg:unit" data-unit="plato">°Plato</button>
          <button role="radio" aria-checked="${sg}" data-action="dlg:unit" data-unit="sg">SG</button></div>
        <div class="felder">${zahl(d, "wert", sg ? "Dichte" : "Restextrakt", sg ? "SG" : "°P")}${zahl(d, "temp", "Temperatur", "°C")}</div>
        ${aktionen(d, `<button class="btn primary" data-action="dlg:ok">Eintragen</button>`)}`;
    },
    actions: {
      unit: (p, d, btn) => { p.keepForm(); d.unit = btn.dataset.unit; d.form.wert = ""; p.renderDialog(); },
      ok: (p, d) => p.dialogRun(async () => {
        const v = n(d.form.wert, "Wert");
        await p.ws("schnellgaer", { sud_id: d.sudId, [d.unit === "sg" ? "dichte" : "restextrakt"]: v, temperatur: n(d.form.temp, "Temperatur") });
        await fertig(p, "Schnellgärprobe eingetragen.");
      }),
    },
  },

  // ---------------------------------------------------------------- Nachgärung
  nachgaer: {
    farbe,
    open(p, d) { d.form.temp = "20"; },
    render(p, d) {
      const druck = numIn(val(d, "druck")), temp = numIn(val(d, "temp"));
      const co2 = !Number.isNaN(druck) && !Number.isNaN(temp) ? (1.013 + druck) * Math.exp(-10.73797 + 2617.25 / (temp + 273.15)) * 10 : null;
      return `${kopf(p, d, "Nachgärung")}
        <div class="felder">${zahl(d, "druck", "Druck (Manometer)", "bar", "", "1,5")}${zahl(d, "temp", "Temperatur", "°C")}</div>
        <p class="info" data-co2>CO₂-Gehalt: <b>${co2 !== null ? `${fmt(co2, 1)} g/l` : "–"}</b></p>
        ${aktionen(d, `<button class="btn primary" data-action="dlg:ok">Eintragen</button>`)}`;
    },
    input(p, d) {
      p.keepForm();
      const druck = numIn(d.form.druck), temp = numIn(d.form.temp);
      const el = p.shadowRoot.querySelector(".dialog [data-co2] b");
      if (el) el.textContent = !Number.isNaN(druck) && !Number.isNaN(temp)
        ? `${fmt((1.013 + druck) * Math.exp(-10.73797 + 2617.25 / (temp + 273.15)) * 10, 1)} g/l` : "–";
    },
    actions: {
      ok: (p, d) => p.dialogRun(async () => {
        await p.ws("nachgaer", { sud_id: d.sudId, druck: n(d.form.druck, "Druck"), temperatur: n(d.form.temp, "Temperatur") });
        await fertig(p, "Nachgärung eingetragen.");
      }),
    },
  },

  // ---------------------------------------------------------------- Verkostung
  verkostung: {
    farbe,
    open(p, d) { d.werte = { sterne: 0 }; },
    render(p, d) {
      const w = d.werte;
      const kats = VERKOSTUNG.map((k) => `<div class="kat"><h4>${k.titel}</h4>
        ${k.gruppen.map((g, gi) => `<div class="gruppe chips">${g.map(([bit, text]) =>
          `<button type="button" class="chip" aria-pressed="${!!((w[k.key] || 0) & (1 << bit))}" data-action="dlg:chip" data-kat="${k.key}" data-gruppe="${gi}" data-bit="${bit}">${esc(text)}</button>`).join("")}</div>`).join("")}
        <input name="${k.key}_bemerkung" placeholder="Notiz zu ${k.titel}" value="${esc(val(d, `${k.key}_bemerkung`))}" style="margin-top:8px;font:15px/1.3 inherit;width:100%;padding:8px 10px;border-radius:10px;border:1px solid var(--rule);background:var(--card);color:var(--primary-text-color)">
      </div>`).join("");
      return `${kopf(p, d, "Verkostung")}
        <div style="display:flex;align-items:center;gap:12px;margin:6px 0">${sterne(w.sterne, { input: true })}<span class="muted">${w.sterne ? `${w.sterne} von 5` : "Gesamtnote"}</span></div>
        <label class="feld voll"><span>Eindruck in einem Satz</span><textarea name="bemerkung" rows="2">${esc(val(d, "bemerkung"))}</textarea></label>
        ${kats}
        ${aktionen(d, `<button class="btn primary" data-action="dlg:ok">Speichern</button>`)}`;
    },
    actions: {
      chip: (p, d, btn) => {
        p.keepForm();
        const k = VERKOSTUNG.find((x) => x.key === btn.dataset.kat);
        const bit = Number(btn.dataset.bit);
        let m = d.werte[k.key] || 0;
        if (m & (1 << bit)) m &= ~(1 << bit);
        else {
          if (!k.mehrfach) for (const [b] of k.gruppen[Number(btn.dataset.gruppe)]) m &= ~(1 << b);
          m |= 1 << bit;
        }
        d.werte[k.key] = m;
        p.renderDialog();
      },
      ok: (p, d) => p.dialogRun(async () => {
        const werte = { ...d.werte, bemerkung: d.form.bemerkung || "" };
        for (const k of VERKOSTUNG) werte[`${k.key}_bemerkung`] = d.form[`${k.key}_bemerkung`] || "";
        await p.ws("bewertung", { sud_id: d.sudId, werte });
        await fertig(p, "Verkostung gespeichert.");
      }),
    },
  },

  // ---------------------------------------------------------------- Regelung (pro Sud)
  regelung: {
    farbe,
    open(p, d) {
      const r = p.entry.regelung[String(d.sudId)];
      d.profil = (r?.profil || [{ ab_vg: 0, soll: 12 }, { ab_vg: 70, soll: 16 }]).map((x) => ({ ...x }));
      d.form.schrank = r?.schrank_id || (p.entry.schraenke[0]?.id ?? "");
      d.profil.forEach((x, i) => { d.form[`vg${i}`] = fmtInput(x.ab_vg); d.form[`soll${i}`] = fmtInput(x.soll); });
    },
    render(p, d) {
      const schraenke = p.entry.schraenke.map((s) => ({ id: s.id, name: s.name }));
      return `${kopf(p, d, "Gärschrank-Regelung")}
        <div class="felder">${auswahl(d, "schrank", "Gärschrank", schraenke, d.form.schrank, "– nicht regeln –")}</div>
        <h3 style="margin:18px 0 8px">Temperaturprofil</h3>
        <p class="muted" style="margin:0 0 10px">Die Solltemperatur richtet sich nach dem Vergärungsgrad. Typisch untergärig: 10–12 °C, ab 70 % zur Diacetylrast auf 16 °C.</p>
        <div class="profil">${d.profil.map((x, i) => `<div class="stufe">
          ${zahl(d, `vg${i}`, i === 0 ? "ab Vergärung" : "ab Vergärung", "%")}${zahl(d, `soll${i}`, "Solltemperatur", "°C")}
          <button class="btn quiet" data-action="dlg:weg" data-i="${i}" ${d.profil.length < 2 ? "disabled" : ""} aria-label="Stufe entfernen">${icon("close")}</button></div>`).join("")}</div>
        <button class="btn quiet" data-action="dlg:plus" style="margin-top:6px">${icon("plus")}Stufe hinzufügen</button>
        ${aktionen(d, `<button class="btn primary" data-action="dlg:ok">Speichern</button>`)}`;
    },
    actions: {
      plus: (p, d) => {
        p.keepForm();
        const i = d.profil.length;
        d.profil.push({ ab_vg: 70, soll: 16 });
        d.form[`vg${i}`] = "70";
        d.form[`soll${i}`] = "16";
        p.renderDialog();
      },
      weg: (p, d, btn) => {
        p.keepForm();
        const i = Number(btn.dataset.i);
        const werte = d.profil.map((_, j) => [d.form[`vg${j}`], d.form[`soll${j}`]]).filter((_, j) => j !== i);
        d.profil.splice(i, 1);
        werte.forEach(([v, s], j) => { d.form[`vg${j}`] = v; d.form[`soll${j}`] = s; });
        delete d.form[`vg${werte.length}`];
        delete d.form[`soll${werte.length}`];
        p.renderDialog();
      },
      ok: (p, d) => p.dialogRun(async () => {
        const f = d.form;
        if (!f.schrank) {
          await p.ws("regelung", { sud_id: d.sudId, schrank_id: null });
          await fertig(p, "Regelung entfernt.");
          return;
        }
        const profil = d.profil.map((_, i) => ({ ab_vg: n(f[`vg${i}`], "Vergärung"), soll: n(f[`soll${i}`], "Solltemperatur") }));
        if (!profil.some((x) => x.ab_vg === 0)) profil[0].ab_vg = 0;
        await p.ws("regelung", { sud_id: d.sudId, schrank_id: f.schrank, profil, aktiv: true });
        await fertig(p, "Regelung gespeichert.");
      }),
    },
  },

  // ---------------------------------------------------------------- Gärschrank anlegen/bearbeiten
  schrank: {
    open(p, d) {
      const s = d.schrankId ? p.entry.schraenke.find((x) => x.id === d.schrankId) : null;
      d.schrank = s;
      d.form = s ? { name: s.name, temp_sensor: s.temp_sensor || "", kuehlung: s.kuehlung || "", heizung: s.heizung || "",
        hysterese: fmtInput(s.hysterese ?? 0.5), pause: fmtInput(s.min_pause_min ?? 5) }
        : { name: "Gärschrank", temp_sensor: "", kuehlung: "", heizung: "", hysterese: "0,5", pause: "5" };
      p.loadAuswahl();
    },
    render(p, d) {
      const aw = p.auswahl || {};
      return `<header class="dlg-head"><div><p class="dlg-kicker">${d.schrank ? "Gärschrank bearbeiten" : "Gärschrank anlegen"}</p>
        <h2 id="dlg-title">${esc(val(d, "name") || "Gärschrank")}</h2></div></header>
        <div class="felder">
          <label class="feld voll"><span>Name</span><input name="name" value="${esc(val(d, "name"))}"></label>
          ${auswahl(d, "temp_sensor", "Temperatursensor", aw.temperatur, d.schrank?.temp_sensor, "– Temperatur der Pill nehmen –")}
          ${auswahl(d, "kuehlung", "Kühlung (Steckdose)", aw.schalter, d.schrank?.kuehlung)}
          ${auswahl(d, "heizung", "Heizung (Steckdose)", aw.schalter, d.schrank?.heizung)}
          ${zahl(d, "hysterese", "Schaltabstand ±", "°C")}
          ${zahl(d, "pause", "Kompressorpause mind.", "min")}
        </div>
        <p class="muted">Kühlt ab Soll + Abstand, heizt ab Soll − Abstand und schaltet am Sollwert wieder aus. Die Pause schützt den Kompressor. Fällt der Sensor aus, gehen beide Steckdosen aus.</p>
        ${aktionen(d, d.schrank ? `<button class="btn danger" data-action="dlg:loeschen">${icon("delete-outline")}Löschen</button>` : "",
          `<button class="btn primary" data-action="dlg:ok">Speichern</button>`)}`;
    },
    actions: {
      ok: (p, d) => p.dialogRun(async () => {
        const f = d.form;
        await p.ws("schrank", { aktion: "speichern", schrank: {
          ...(d.schrank ? { id: d.schrank.id } : {}), name: f.name, temp_sensor: f.temp_sensor || null,
          kuehlung: f.kuehlung || null, heizung: f.heizung || null,
          hysterese: n(f.hysterese, "Schaltabstand"), min_pause_min: n(f.pause, "Kompressorpause"),
        } });
        await fertig(p, "Gärschrank gespeichert.");
      }),
      loeschen: (p, d) => {
        if (!d.sicher) {
          d.sicher = true;
          d.error = "Nochmal auf „Löschen“ tippen. Kühlung und Heizung werden dabei ausgeschaltet.";
          p.keepForm();
          p.renderDialog();
          return;
        }
        p.dialogRun(async () => {
          await p.ws("schrank", { aktion: "loeschen", schrank_id: d.schrank.id });
          await fertig(p, "Gärschrank gelöscht.");
        });
      },
    },
  },
};

// ---------------------------------------------------------------- Lager: Rohstoffe abziehen
const LAGER_GRUPPE = { malz: "Malz", hopfen: "Hopfen", hefe: "Hefe", zusatz: "Weitere Zutaten" };

DIALOGE.lager = {
  farbe,
  async open(p, d) {
    d.loading = true;
    try {
      const r = await p.ws("lager_bedarf", d.art ? { art: d.art, item_id: d.itemId } : { sud_id: d.sudId });
      d.posten = r.posten;
      d.schon = r.schon_gebucht || [];
      d.posten.forEach((x, i) => {
        d.form[`m${i}`] = x.gefunden && !x.spaeter ? fmtInput(Math.round(x.menge * 1000) / 1000) : "0";
      });
    } catch (err) {
      d.error = err?.message || String(err);
    }
    d.loading = false;
    p.renderDialog();
  },
  render(p, d) {
    const head = kopf(p, d, d.art ? "Zugabe vom Lager abziehen" : "Rohstoffe vom Lager abziehen");
    if (d.loading) return `${head}<p class="muted">Lade Lagerbestand …</p>`;
    if (!d.posten) return `${head}${aktionen(d)}`;
    if (!d.posten.length) return `${head}<p>Für diesen Sud sind keine Rohstoffe hinterlegt.</p>${aktionen(d)}`;
    const schon = d.schon?.length
      ? `<p class="warn-box">Für diesen Sud wurde am ${dfFull.format(new Date(d.schon[d.schon.length - 1].zeit))} schon abgezogen. Nochmal abziehen bucht doppelt.</p>` : "";
    let gruppe = "";
    const zeilen = d.posten.map((x, i) => {
      const kopfzeile = x.typ !== gruppe ? `<tr><th colspan="4" class="lager-gruppe">${LAGER_GRUPPE[x.typ]}</th></tr>` : "";
      gruppe = x.typ;
      const status = !x.gefunden ? `<span class="badge warn">nicht im Lager</span>`
        : x.spaeter ? `<span class="badge">beim Zugeben</span>`
        : x.fehlt > 0 ? `<span class="badge warn">fehlt ${fmt(x.fehlt, x.einheit === "kg" ? 2 : 0)} ${esc(x.einheit)}</span>` : "";
      return `${kopfzeile}<tr>
        <td><b>${esc(x.name)}</b><br>${status}</td>
        <td class="hide-narrow">${fmt(x.menge, x.einheit === "kg" ? 2 : 0)} ${esc(x.einheit)}</td>
        <td>${x.vorhanden !== null ? `${fmt(x.vorhanden, x.einheit === "kg" ? 2 : 0)} ${esc(x.einheit)}` : "–"}</td>
        <td><span class="eingabe"><input name="m${i}" inputmode="decimal" autocomplete="off" value="${esc(val(d, `m${i}`))}" ${x.gefunden ? "" : "disabled"} style="width:6.5em"><em>${esc(x.einheit)}</em></span></td>
      </tr>`;
    }).join("");
    return `${head}
      <p class="muted">Wie im Brauhelfer: Die Mengen kannst du vor dem Abziehen anpassen. Rohstoffe, die nicht unter genau diesem Namen im Lager stehen, werden übersprungen. Der Bestand geht nie unter null.</p>
      ${schon}
      <table class="nums lager"><thead><tr><th>Rohstoff</th><th class="hide-narrow">Rezept</th><th>Im Lager</th><th>Abziehen</th></tr></thead>
      <tbody>${zeilen}</tbody></table>
      ${aktionen(d, `<button class="btn primary" data-action="dlg:ok">${icon("archive-arrow-down-outline")}Abziehen</button>`).replace(">Abbrechen<", ">Nicht abziehen<")}`;
  },
  actions: {
    ok: (p, d) => p.dialogRun(async () => {
      const posten = [];
      d.posten.forEach((x, i) => {
        if (!x.gefunden) return;
        const m = n(d.form[`m${i}`], x.name);
        if (m > 0) posten.push({ typ: x.typ, name: x.name, menge: m });
      });
      if (!posten.length) {
        await fertig(p, "Nichts abgezogen.");
        return;
      }
      const r = await p.ws("lager_abziehen", { sud_id: d.sudId, anlass: d.anlass || "brautag", posten });
      await fertig(p, `${r.gebucht.length} ${r.gebucht.length === 1 ? "Rohstoff" : "Rohstoffe"} vom Lager abgezogen.`);
    }),
  },
};

// Sterne in der Verkostung (data-action="stern" liegt im Dialog, aber ohne "dlg:"-Präfix)
DIALOGE.verkostung.actions.stern = (p, d, btn) => {
  p.keepForm();
  d.werte.sterne = Number(btn.dataset.wert);
  p.renderDialog();
};
