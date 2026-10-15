// Brauhelfer – Seitenleisten-Panel für Home Assistant
// Ohne Build-Schritt: ES-Module, Web Components von HA (ha-card, ha-icon, ha-menu-button).

import { esc, icon, parseDate, fmt, alkohol, vg, dfFull, navigate } from "./lib.js";
import { CSS } from "./styles.js";
import * as liste from "./view-liste.js";
import * as sud from "./view-sud.js";
import * as brautag from "./view-brautag.js";
import * as einstellungen from "./view-einstellungen.js";
import { DIALOGE } from "./dialoge.js";

const VIEWS = { liste, sud, brautag, einstellungen };

class BrauhelferPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.view = { name: "liste" };
    this.tab = null;
    this.subtab = {};
    this.details = {};
    this.expanded = {};
    this.busy = {};
    this.msg = {};
    this.pillChoice = {};
    this.data = null;
    this.error = null;
    this.dialog = null;
    this._sig = "";
  }

  // ------------------------------------------------------------ HA-Schnittstelle
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._menu) {
      this._menu.hass = hass;
      this._menu.narrow = this._narrow;
    }
    if (first) {
      this.fetch();
      return;
    }
    const e = this.entry;
    if (!e) return;
    const sig = [e.entities.uebersicht, e.entities.letzter_eintrag].map((id) => hass.states[id]?.last_updated).join("|");
    const pillSig = e.pills.map((p) => hass.states[p.gravity]?.last_updated).join("|")
      + e.schraenke.map((s) => hass.states[s.temp_sensor]?.last_updated).join("|");
    if (sig !== this._sig) {
      this._sig = sig;
      this.fetch();
    } else if (pillSig !== this._pillSig) {
      this._pillSig = pillSig;
      this.render();
    }
  }
  get hass() {
    return this._hass;
  }

  set narrow(n) {
    this._narrow = n;
    if (this._menu) this._menu.narrow = n;
    this.toggleAttribute("narrow", !!n);
  }

  set panel(p) {}

  set route(r) {
    const path = (r?.path || "").replace(/^\/+/, "");
    const [name, id] = path.split("/");
    const view = VIEWS[name] && name !== "liste" ? { name, id: id ? Number(id) : undefined } : { name: "liste" };
    if (view.name !== this.view.name || view.id !== this.view.id) {
      this.view = view;
      this.onViewChange();
    }
  }

  connectedCallback() {
    this._timer = setInterval(() => this.fetch(), 60000);
    this._tick = setInterval(() => this.view.name === "brautag" && brautag.tick(this), 1000);
    this._ro = new ResizeObserver(() => {
      const w = this.chartWidth();
      if (Math.abs(w - (this._lastW || 0)) > 8) {
        this._lastW = w;
        if (this.data) this.render();
      }
    });
    this._ro.observe(this);
    // Zurück-Geste/Browser-Zurück (HA setzt route ebenfalls; doppelt schadet nicht)
    this._pop = () => {
      const m = location.pathname.match(/^\/brauhelfer\/?(.*)$/);
      if (m) this.route = { path: `/${m[1]}` };
    };
    window.addEventListener("popstate", this._pop);
    if (this.data) this.render();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    clearInterval(this._tick);
    this._ro?.disconnect();
    window.removeEventListener("popstate", this._pop);
  }

  // ------------------------------------------------------------ Navigation
  go(name, id) {
    const path = name === "liste" ? "" : `/${name}${id !== undefined ? `/${id}` : ""}`;
    this.view = { name, id };
    this._intern = true;
    navigate(path);
    this.onViewChange();
  }

  back() {
    if (this._intern) history.back();
    else this.go("liste");
  }

  onViewChange() {
    window.scrollTo?.(0, 0);
    if (this.view.name === "sud" && this.view.id !== undefined) this.loadDetails(this.view.id);
    if (this.view.name === "brautag" && this.view.id !== undefined) brautag.laden(this, this.view.id);
    if (this.view.name === "einstellungen" || this.view.name === "sud") this.loadAuswahl();
    this.render();
  }

  // ------------------------------------------------------------ Daten
  get entry() {
    return this.data?.entries?.[0];
  }

  ws(type, data = {}) {
    return this._hass.callWS({ type: `brauhelfer/${type}`, entry_id: this.entry?.entry_id, ...data });
  }

  async fetch() {
    if (!this._hass) return;
    try {
      this.data = await this._hass.callWS({ type: "brauhelfer/data" });
      this.error = null;
      const e = this.entry;
      if (e) {
        this._sig = [e.entities.uebersicht, e.entities.letzter_eintrag].map((id) => this._hass.states[id]?.last_updated).join("|");
        if (!this.tab) this.tab = e.gaerend.length ? "gaerung" : e.geplant.length ? "geplant" : "gebraut";
      }
      if (this.view.name === "sud" && this.view.id !== undefined) await this.loadDetails(this.view.id, true);
    } catch (err) {
      this.error = err?.message || String(err);
    }
    this.render();
  }

  async loadDetails(id, silent = false) {
    try {
      this.details[id] = await this.ws("details", { sud_id: id });
    } catch (err) {
      this.details[id] = { fehler: err?.message || String(err) };
    }
    if (!silent) this.render();
  }

  async loadAuswahl(neu = false) {
    if (!this._hass || !this.entry) {
      setTimeout(() => this.loadAuswahl(neu), 500);
      return;
    }
    if (this.auswahl && !neu) return;
    try {
      this.auswahl = await this.ws("auswahl");
    } catch {
      this.auswahl = { schalter: [], temperatur: [], waage: [], notify: [] };
    }
    if (this.dialog) this.renderDialog();
    else this.render();
  }

  sudById(id) {
    const e = this.entry;
    if (!e) return null;
    return [...e.geplant, ...e.gaerend, ...e.abgefuellt].find((s) => s.id === id) || null;
  }

  chartWidth() {
    const panel = Math.min(this.clientWidth || 800, 900);
    const pad = panel < 600 ? 24 + 32 : 32 + 40;
    return Math.max(260, panel - pad);
  }

  // Live-Werte einer Pill aus hass.states
  live(a) {
    const g = this._hass?.states[a.gravity];
    const t = a.temperature ? this._hass?.states[a.temperature] : null;
    if (!g) return { offline: true };
    const gv = parseFloat(g.state);
    if (Number.isNaN(gv)) return { offline: true };
    const tv = t ? parseFloat(t.state) : NaN;
    const unit = (g.attributes.unit_of_measurement || "").toLowerCase().replace("°", "").trim();
    const plato = unit === "p" || unit === "plato" || gv > 1.5 ? gv : (-616.868 + 1111.14 * gv - 630.272 * gv ** 2 + 135.997 * gv ** 3);
    let temp = tv;
    if (t && t.attributes.unit_of_measurement === "°F") temp = ((tv - 32) * 5) / 9;
    const pill = this.entry.pills.find((p) => p.gravity === a.gravity);
    const times = [parseDate(g.last_updated), parseDate(pill?.zuletzt)].filter(Boolean);
    const updated = times.length ? new Date(Math.max(...times.map((x) => x.getTime()))) : null;
    const fresh = !!updated && Date.now() - updated.getTime() < this.entry.max_alter_min * 60000;
    return { sg: gv > 1.5 ? null : gv, plato, temp, updated, fresh };
  }

  // ------------------------------------------------------------ Aktionen
  async run(key, sudId, fn, { erfolg } = {}) {
    this.busy[key] = true;
    if (sudId !== undefined) delete this.msg[sudId];
    this.render();
    try {
      await fn();
      if (erfolg) this.toast(erfolg);
    } catch (err) {
      const text = err?.message || String(err);
      if (sudId !== undefined) this.msg[sudId] = { ok: false, text };
      else this.toast(text);
    }
    delete this.busy[key];
    await this.fetch();
  }

  toast(text) {
    this._toastText = text;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this._toastText = null;
      this.renderToast();
    }, 5000);
    this.renderToast();
  }

  renderToast() {
    const el = this.shadowRoot.querySelector(".toast");
    if (!el) return;
    el.textContent = this._toastText || "";
    el.classList.toggle("show", !!this._toastText);
  }

  openDialog(typ, daten = {}) {
    this.dialog = { typ, form: {}, ...daten };
    DIALOGE[typ].open?.(this, this.dialog);
    this.renderDialog();
  }

  closeDialog() {
    this.dialog = null;
    this.renderDialog();
  }

  // Formularwerte des Dialogs sichern (vor einem Neuzeichnen)
  keepForm() {
    const d = this.dialog;
    const root = this.shadowRoot.querySelector(".dialog");
    if (!d || !root) return;
    root.querySelectorAll("[name]").forEach((el) => {
      d.form[el.name] = el.type === "checkbox" ? el.checked : el.value;
    });
  }

  form() {
    this.keepForm();
    return this.dialog?.form || {};
  }

  async dialogRun(fn) {
    const d = this.dialog;
    this.keepForm();
    d.busy = true;
    d.error = null;
    this.renderDialog();
    try {
      await fn(d);
    } catch (err) {
      if (this.dialog === d) {
        d.busy = false;
        d.error = err?.message || String(err);
        this.renderDialog();
      }
    }
  }

  _onClick(ev) {
    const btn = ev.target.closest("[data-action]");
    if (!btn || btn.disabled) return;
    const a = btn.dataset.action;
    const id = btn.dataset.sud !== undefined ? Number(btn.dataset.sud) : undefined;

    if (a.startsWith("dlg:")) {
      const d = this.dialog;
      if (!d) return;
      const name = a.slice(4);
      if (name === "close") {
        if (!d.busy) this.closeDialog();
        return;
      }
      DIALOGE[d.typ].actions?.[name]?.(this, d, btn, ev);
      return;
    }
    switch (a) {
      case "back": this.back(); return;
      case "settings": this.go("einstellungen"); return;
      case "tab": this.tab = btn.dataset.tab; this.render(); return;
      case "subtab": this.subtab[id] = btn.dataset.tab; this.render(); return;
      case "retry": this.fetch(); return;
      case "open-sud": this.go("sud", id); return;
      case "dialog": {
        const extra = btn.dataset.extra ? JSON.parse(btn.dataset.extra) : {};
        this.openDialog(btn.dataset.typ, { sudId: id, ...extra });
        return;
      }
      default:
        for (const v of Object.values(VIEWS)) {
          if (v.actions?.[a]) {
            v.actions[a](this, btn, id, ev);
            return;
          }
        }
    }
  }

  _onChange(ev) {
    const sel = ev.target.closest("select[data-pill-sud]");
    if (sel) this.pillChoice[Number(sel.dataset.pillSud)] = sel.value;
    if (ev.target.closest(".dialog") && this.dialog) DIALOGE[this.dialog.typ].change?.(this, this.dialog, ev);
    for (const v of Object.values(VIEWS)) v.change?.(this, ev);
  }

  _onInput(ev) {
    if (ev.target.closest(".dialog") && this.dialog) DIALOGE[this.dialog.typ].input?.(this, this.dialog, ev);
  }

  // ------------------------------------------------------------ Rendering
  render() {
    const root = this.shadowRoot;
    const active = root.activeElement;
    if (active && active.closest?.("main") && /^(SELECT|INPUT|TEXTAREA)$/.test(active.tagName)) {
      this._renderPending = true;
      return;
    }
    this._renderPending = false;
    if (!this._menu) {
      root.innerHTML = `<style>${CSS}</style>
        <div class="toolbar"><ha-menu-button></ha-menu-button><span class="tb-back"></span><h1>Brauhelfer</h1><span class="tb-actions"></span></div>
        <main></main><div class="toast" role="status" aria-live="polite"></div><div class="dlg-host"></div>`;
      this._menu = root.querySelector("ha-menu-button");
      this._menu.hass = this._hass;
      this._menu.narrow = this._narrow;
      root.addEventListener("click", (ev) => this._onClick(ev));
      root.addEventListener("change", (ev) => this._onChange(ev));
      root.addEventListener("input", (ev) => this._onInput(ev));
      root.addEventListener("focusout", () => setTimeout(() => { if (this._renderPending) this.render(); }, 0));
      root.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape" && this.dialog && !this.dialog.busy) this.closeDialog();
      });
      root.addEventListener("pointermove", (ev) => this._onPointer(ev));
      root.addEventListener("pointerdown", (ev) => this._onPointer(ev));
    }

    // Kopfzeile
    const unter = this.view.name !== "liste";
    const titel = this.view.name === "einstellungen" ? "Einstellungen"
      : this.view.name === "brautag" ? "Brautag"
      : this.view.name === "sud" ? (this.sudById(this.view.id)?.name || this.details[this.view.id]?.name || "Sud")
      : "Brauhelfer";
    root.querySelector(".toolbar h1").textContent = titel;
    root.querySelector(".tb-back").innerHTML = unter
      ? `<button class="tb" data-action="back" aria-label="Zurück">${icon("arrow-left")}</button>` : "";
    this._menu.style.display = unter ? "none" : "";
    root.querySelector(".tb-actions").innerHTML = this.view.name === "liste"
      ? `<button class="tb" data-action="settings" aria-label="Einstellungen">${icon("cog-outline")}</button>` : "";

    const main = root.querySelector("main");
    this.charts = {};
    if (this.error) {
      main.innerHTML = `<div class="empty">${icon("database-alert-outline")}<p class="gross">Die Daten konnten nicht geladen werden.</p>
        <p class="muted">${esc(this.error)}</p><button class="btn" data-action="retry">${icon("refresh")}Erneut laden</button></div>`;
      return;
    }
    if (!this.data) {
      main.innerHTML = `<div class="empty"><p class="muted">Lade Daten aus der Brauhelfer-Datenbank …</p></div>`;
      return;
    }
    if (!this.entry) {
      main.innerHTML = `<div class="empty">${icon("puzzle-outline")}<p class="gross">Die Integration „Kleiner Brauhelfer“ ist nicht geladen.</p>
        <p class="muted">Prüfe unter Einstellungen → Geräte &amp; Dienste, ob die Datenbank erreichbar ist.</p></div>`;
      return;
    }
    try {
      main.innerHTML = VIEWS[this.view.name].render(this);
    } catch (err) {
      console.error("Brauhelfer:", err);
      main.innerHTML = `<div class="empty"><p class="gross">Diese Ansicht konnte nicht angezeigt werden.</p>
        <p class="muted">Meist hilft es, Home Assistant nach einem Update neu zu starten und die Seite neu zu laden.</p>
        <p class="muted" style="font-family:monospace;font-size:12px">${String(err?.message || err).replace(/[<>&]/g, "")}</p></div>`;
    }
    this.renderToast();
  }

  renderDialog() {
    const host = this.shadowRoot.querySelector(".dlg-host");
    if (!host) return;
    const d = this.dialog;
    if (!d) {
      host.innerHTML = "";
      return;
    }
    const def = DIALOGE[d.typ];
    const farbe = def.farbe?.(this, d) || "var(--primary-color)";
    host.innerHTML = `
      <div class="scrim" data-action="dlg:close"></div>
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-title" tabindex="-1" style="--beer:${farbe}">
        ${def.render(this, d)}
        ${d.error ? `<p class="warn-box" role="alert">${esc(d.error)}</p>` : ""}
      </div>`;
    if (!d.focused) {
      host.querySelector(".dialog")?.focus({ preventScroll: true });
      d.focused = true;
    }
  }

  // Kurve antippen: Werte des nächsten Messpunkts anzeigen
  _onPointer(ev) {
    const hit = ev.composedPath().find((n) => n.classList?.contains?.("hit"));
    if (!hit) return;
    const box = hit.closest(".chart-box");
    const id = Number(box.dataset.chart);
    const ch = this.charts?.[id];
    if (!ch) return;
    const svg = hit.ownerSVGElement;
    const r = svg.getBoundingClientRect();
    const vx = ((ev.clientX - r.left) / r.width) * ch.W;
    let best = 0, bd = Infinity;
    ch.pts.forEach((p, i) => {
      const d = Math.abs(ch.x(p.t.getTime()) - vx);
      if (d < bd) { bd = d; best = i; }
    });
    const p = ch.pts[best];
    const cx = ch.x(p.t.getTime());
    const cur = svg.querySelector(".cursor");
    cur.setAttribute("x1", cx); cur.setAttribute("x2", cx); cur.style.display = "";
    svg.querySelectorAll(".dot").forEach((d) => d.classList.toggle("active", Number(d.dataset.i) === best));
    const out = this.shadowRoot.querySelector(`[data-readout="${id}"]`);
    const s = ch.sud;
    out.textContent = p.start
      ? `${dfFull.format(p.t)}: Anstellen mit ${fmt(p.sre, 1)} °P`
      : `${dfFull.format(p.t)}: ${fmt(p.sre, 2)} °P, ${fmt(alkohol(s.sw, p.sre), 1)} % vol, ${fmt(vg(s.sw, p.sre), 0)} % vergoren${p.temp !== null ? `, ${fmt(p.temp, 1)} °C` : ""}`;
  }
}

customElements.define("brauhelfer-panel", BrauhelferPanel);
