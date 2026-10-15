// Styles der Brauhelfer-Seite. Farben und Radien kommen aus dem HA-Theme,
// damit die Seite in hell, dunkel und eigenen Themes passt.
export const CSS = `
:host {
  display: block;
  min-height: 100%;
  background: var(--primary-background-color);
  color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif));
  -webkit-font-smoothing: antialiased;
  --label-font: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  --muted: var(--secondary-text-color);
  --card: var(--ha-card-background, var(--card-background-color, #fff));
  --rule: var(--divider-color, rgba(0,0,0,.12));
  --radius: var(--ha-card-border-radius, 12px);
  --hop: #4f7a28;
  --warn: #b5530b;
  --danger: var(--error-color, #c62828);
  font-variant-numeric: tabular-nums;
}
* { box-sizing: border-box; }
ha-icon.i { --mdc-icon-size: 20px; width: 20px; height: 20px; display: inline-flex; flex: none; color: inherit; }
ha-icon:not(:defined) { display: inline-block; width: 20px; height: 20px; }

/* ---------- Kopfzeile */
.toolbar {
  display: flex; align-items: center; gap: 4px;
  height: var(--header-height, 56px); padding: 0 8px 0 4px;
  background: var(--app-header-background-color, var(--primary-color));
  color: var(--app-header-text-color, #fff);
  position: sticky; top: 0; z-index: 3;
  border-bottom: var(--app-header-border-bottom, none);
}
.toolbar h1 { font: 400 21px/1 var(--label-font); margin: 0 0 0 6px; flex: 1; letter-spacing: .01em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.toolbar .tb { all: unset; display: inline-grid; place-items: center; width: 44px; height: 44px; border-radius: 50%; cursor: pointer; }
.toolbar .tb:hover { background: rgba(255,255,255,.12); }
.toolbar .tb:focus-visible { outline: 2px solid currentColor; outline-offset: -4px; }
.toolbar ha-icon.i { --mdc-icon-size: 24px; width: 24px; height: 24px; }
:host(:not([narrow])) ha-menu-button { display: none; }
ha-menu-button { color: inherit; }

main { max-width: 900px; margin: 0 auto; padding: 18px 16px 48px; }

/* ---------- Reiter */
.tabs { display: inline-flex; gap: 2px; padding: 3px; border-radius: 12px; background: var(--rule); margin-bottom: 18px; max-width: 100%; overflow-x: auto; }
.tabs button { border: 0; background: transparent; color: var(--muted); font: 500 15px/1 inherit;
  padding: 9px 16px; border-radius: 9px; cursor: pointer; display: flex; gap: 8px; align-items: center; white-space: nowrap; }
.tabs button[aria-selected="true"] { background: var(--card); color: var(--primary-text-color); box-shadow: 0 1px 2px rgba(0,0,0,.12); }
.tabs .count { font-size: 13px; color: var(--muted); }

/* ---------- Karten (ha-card; Rückfall ohne HA) */
ha-card { display: block; margin-bottom: 16px; }
ha-card:not(:defined) { background: var(--card); border-radius: var(--radius); border: 1px solid var(--rule); }
.card-body { padding: 18px 20px; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 20px 0; }
.card-head h3 { margin: 0; font: 500 17px/1.3 inherit; display: flex; align-items: center; gap: 8px; }
.card-head h3 ha-icon.i { box-sizing: content-box; padding: 7px; border-radius: 10px; margin-right: 2px;
  background: color-mix(in srgb, var(--beer, var(--primary-color)) 16%, transparent); color: var(--primary-text-color); }
.card-actions { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 20px 16px; border-top: 1px solid var(--rule); justify-content: flex-end; }

/* ---------- Sud-Karten in der Liste */
.sudliste { display: grid; gap: 14px; }
.sudliste ha-card { margin: 0; overflow: hidden; }
.sudkarte { all: unset; box-sizing: border-box; display: grid; grid-template-columns: auto 1fr auto; gap: 6px 18px; align-items: center;
  width: 100%; padding: 18px 20px; cursor: pointer; border-radius: var(--radius); position: relative;
  background: linear-gradient(100deg, color-mix(in srgb, var(--beer, transparent) 14%, transparent) 0, transparent 210px); }
.sudkarte:not(:last-child) { border-radius: var(--radius) var(--radius) 0 0; }
button.sudkarte:hover { background-color: color-mix(in srgb, var(--primary-text-color) 3%, transparent); }
.sudkarte:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.sudkarte .glass { grid-column: 1; grid-row: 1 / span 3; align-self: start; }
.sudkarte .titel { grid-column: 2; grid-row: 1; min-width: 0; }
.sudkarte h2 { font: 400 24px/1.15 var(--label-font); margin: 0; overflow-wrap: anywhere; }
.sudkarte .meta { margin: 0; }
.sudkarte .rechts { grid-column: 3; grid-row: 1 / span 2; display: flex; align-items: center; gap: 8px; justify-content: flex-end; text-align: right; }
.sudkarte .kpis { grid-column: 2; grid-row: 2; display: flex; flex-wrap: wrap; gap: 4px 22px; margin: 4px 0 0; }
.sudkarte .kpis dd { font-size: 18px; }
.sudkarte .kpis dd small { font-size: 12px; }
.sudkarte .fortschritt { grid-column: 2 / span 2; grid-row: 3; margin-top: 6px; }
.chev { color: var(--muted); }
.badge { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; padding: 4px 10px; border-radius: 999px;
  background: color-mix(in srgb, var(--primary-text-color) 7%, transparent); color: var(--primary-text-color); white-space: nowrap; }
.badge.live { background: color-mix(in srgb, var(--hop) 14%, transparent); color: var(--hop); }
.badge.warn { background: color-mix(in srgb, var(--warn) 14%, transparent); color: var(--warn); }
.badge ha-icon.i { --mdc-icon-size: 16px; width: 16px; height: 16px; }
.bar { height: 8px; border-radius: 4px; background: var(--rule); overflow: hidden; }
.bar > span { display: block; height: 100%; border-radius: 4px; min-width: 8px;
  background: linear-gradient(90deg, var(--beer, var(--primary-color)), var(--line, var(--beer, var(--primary-color)))); }
.bar-label { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; color: var(--muted); margin-top: 6px; }
.bar-label span { display: inline-flex; align-items: center; gap: 6px; }
.bar-label b { color: var(--primary-text-color); font-weight: 600; }
.bar-label ha-icon.i { --mdc-icon-size: 16px; width: 16px; height: 16px; }
.spark { display: block; }

/* ---------- Glas */
.glass { flex: none; overflow: visible; }
.glass-empty { fill: color-mix(in srgb, var(--primary-text-color) 5%, transparent); }
.glass-outline { fill: none; stroke: color-mix(in srgb, var(--primary-text-color) 35%, transparent); stroke-width: 1.6; }
.foam { fill: #fbf7ee; }
.bubble { fill: rgba(255,255,255,.75); animation: rise 4.5s linear infinite; }
@keyframes rise { 0% { transform: translateY(0); opacity: 0 } 15% { opacity: 1 } 100% { transform: translateY(-96px); opacity: 0 } }
@media (prefers-reduced-motion: reduce) { .bubble { animation: none; opacity: 0; } }

/* ---------- Sud-Detail */
.detail-head { display: grid; grid-template-columns: auto 1fr; grid-template-areas: "glas text" "glas facts" "glas aktionen";
  gap: 0 26px; align-items: start; padding: 22px 26px; margin-bottom: 16px; border-radius: 20px; border: 1px solid var(--rule);
  background: radial-gradient(130% 150% at 0% 0%, color-mix(in srgb, var(--beer) 24%, var(--card)) 0%, var(--card) 65%); }
.hero-glas { grid-area: glas; align-self: center; display: grid; place-items: center; }
.hero-text { grid-area: text; min-width: 0; }
.kicker { margin: 0 0 2px; font-size: 12px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  color: color-mix(in srgb, var(--beer) 55%, var(--primary-text-color)); }
.detail-head h2 { font: 400 34px/1.1 var(--label-font); margin: 0 0 4px; overflow-wrap: anywhere; }
.detail-head .badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 0; }
.hero-aktionen { grid-area: aktionen; display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.meta { margin: 0; color: var(--muted); font-size: 14px; }
.facts { grid-area: facts; display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 0; }
.facts > div { min-width: 104px; padding: 10px 14px; border-radius: 14px; border: 1px solid var(--rule);
  background: color-mix(in srgb, var(--card) 72%, transparent); }
dt { font-size: 13px; color: var(--muted); margin-bottom: 2px; }
dd { margin: 0; font-size: 20px; font-weight: 500; }
dd small { font-size: 13px; font-weight: 400; color: var(--muted); }
dd.big { font-size: 20px; font-weight: 600; }
.subtabs { display: flex; gap: 4px; border-bottom: 1px solid var(--rule); margin: 0 0 16px; overflow-x: auto; scrollbar-width: none; }
.subtabs::-webkit-scrollbar { display: none; }
.subtabs button { all: unset; cursor: pointer; padding: 10px 14px; font: 500 15px/1 inherit; color: var(--muted);
  border-bottom: 2px solid transparent; margin-bottom: -1px; white-space: nowrap; }
.subtabs button[aria-selected="true"] { color: var(--primary-text-color); border-bottom: 3px solid var(--beer, var(--primary-color)); }
.subtabs button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; border-radius: 6px; }
.hint { margin: 0 0 16px; padding: 12px 14px; border-radius: 10px; font-size: 14px; display: flex; gap: 10px; align-items: flex-start;
  background: color-mix(in srgb, var(--warn) 10%, transparent); }

/* ---------- Pill */
.pill { display: grid; gap: 12px; }
.pill-live { display: flex; gap: 12px; align-items: flex-start; }
.pill p { margin: 0; }
.pill-title { font-weight: 500; }
.pill-values { font-size: 15px; }
.dot-live { width: 10px; height: 10px; border-radius: 50%; margin-top: 6px; flex: none; background: var(--muted); opacity: .5; }
.dot-live.fresh { background: var(--hop); opacity: 1; box-shadow: 0 0 0 4px color-mix(in srgb, var(--hop) 20%, transparent); }
.reihe { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.pill-pick { display: grid; gap: 4px; flex: 1 1 220px; font-size: 13px; color: var(--muted); }

/* ---------- Meldungen */
.ok, .warn-box { font-size: 14px; padding: 9px 12px; border-radius: 8px; margin: 0; }
.ok { color: var(--hop); background: color-mix(in srgb, var(--hop) 10%, transparent); }
.warn-box { color: var(--warn); background: color-mix(in srgb, var(--warn) 10%, transparent); }

/* ---------- Knöpfe */
.btn { display: inline-flex; align-items: center; gap: 6px; font: 500 14px/1 inherit; padding: 10px 14px; border-radius: 10px; cursor: pointer;
  border: 1px solid var(--rule); background: var(--card); color: var(--primary-text-color); min-height: 40px; }
.btn ha-icon.i { --mdc-icon-size: 18px; width: 18px; height: 18px; }
.btn.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
.btn.quiet { border-color: transparent; background: transparent; color: var(--primary-color); }
.btn.danger { color: var(--danger); }
.btn.klein { min-height: 32px; padding: 6px 10px; font-size: 13px; }
.btn:disabled { opacity: .55; cursor: default; }
button:focus-visible, select:focus-visible, input:focus-visible, textarea:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.switch { display: inline-flex; align-items: center; gap: 10px; font: 400 15px/1.3 inherit; color: var(--primary-text-color);
  background: none; border: 0; cursor: pointer; padding: 6px 0; text-align: left; }
.switch .knob { width: 36px; height: 20px; border-radius: 10px; background: var(--rule); position: relative; flex: none; transition: background .15s; }
.switch .knob::after { content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.3); transition: transform .15s; }
.switch[aria-checked="true"] .knob { background: var(--primary-color); }
.switch[aria-checked="true"] .knob::after { transform: translateX(16px); }

/* ---------- Diagramm */
h3 { font: 500 16px/1.2 inherit; margin: 0; }
.chart-head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 6px; }
.legend { margin: 0; font-size: 13px; color: var(--muted); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.legend span { display: inline-block; width: 18px; height: 0; border-top: 3px solid var(--line); margin-left: 8px; }
.legend .sw-temp { border-top: 1.5px solid var(--muted); opacity: .7; }
.legend .sw-schnell { border-top: 2px dashed var(--hop); }
.readout { margin: 6px 0 4px; font-size: 14px; min-height: 1.3em; color: var(--muted); }
.chart-box { width: 100%; touch-action: pan-y; }
.chart { width: 100%; height: auto; display: block; overflow: visible; }
.chart .grid { stroke: var(--rule); stroke-width: 1; }
.chart .ax { font-size: 11px; fill: var(--muted); }
.chart .sre-line { fill: none; stroke-width: 2.5; stroke-linejoin: round; }
.chart .temp-line { fill: none; stroke: var(--muted); stroke-width: 1.2; opacity: .7; }
.chart .schnell-line { fill: none; stroke: var(--hop); stroke-width: 1.6; stroke-dasharray: 5 4; }
.chart .target { stroke: var(--hop); stroke-width: 1.2; stroke-dasharray: 6 4; }
.chart .target-label { font-size: 11px; fill: var(--hop); }
.chart .dot { fill: var(--card); stroke: var(--c); stroke-width: 2; }
.chart .dot.start { fill: var(--c); }
.chart .dot.active { r: 5.5; }
.chart .dot.leise { opacity: 0; }
.chart .dot.leise.active { opacity: 1; }
.chart .cursor { stroke: var(--muted); stroke-width: 1; }
.chart .hit { fill: transparent; cursor: crosshair; }

/* ---------- Tabellen */
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th { text-align: left; font-weight: 400; color: var(--muted); font-size: 13px; padding: 6px 8px 6px 0; border-bottom: 1px solid var(--rule); }
td { padding: 9px 8px 9px 0; border-bottom: 1px solid var(--rule); white-space: nowrap; }
td:last-child { white-space: normal; }
.muted { color: var(--muted); font-size: 14px; }
.nums td { font-variant-numeric: tabular-nums; }

/* ---------- Listen mit Aktionen (Zutaten, Fässer, Gärschränke) */
.zeilen { list-style: none; margin: 0; padding: 0; }
.zeilen > li { display: flex; gap: 14px; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--rule); }
.zeilen > li:last-child { border-bottom: 0; }
.zeilen .text { flex: 1; min-width: 0; }
.zeilen .text b { font-weight: 500; }
.zeilen .text p { margin: 2px 0 0; }
.zeilen .rund { width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; flex: none;
  background: color-mix(in srgb, var(--beer, var(--primary-color)) 16%, transparent); color: var(--primary-text-color); }
.zeilen .rund.done { background: color-mix(in srgb, var(--hop) 18%, transparent); color: var(--hop); }

/* ---------- Lebenslauf */
.timeline { list-style: none; margin: 0; padding: 4px 0 0; position: relative; }
.timeline::before { content: ""; position: absolute; left: 15px; top: 8px; bottom: 8px; width: 2px; background: var(--rule); }
.timeline li { display: grid; grid-template-columns: 32px 1fr; gap: 12px; padding: 0 0 18px; position: relative; }
.timeline .knoten { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; z-index: 1;
  background: var(--card); border: 2px solid var(--beer, var(--primary-color)); color: var(--primary-text-color); }
.timeline .knoten ha-icon.i { --mdc-icon-size: 16px; width: 16px; height: 16px; }
.timeline li.zukunft .knoten { border-style: dashed; border-color: var(--rule); color: var(--muted); }
.timeline li.heute .knoten { background: var(--beer, var(--primary-color)); color: #fff; }
.timeline .wann { font-size: 13px; color: var(--muted); }
.timeline .was { font-weight: 500; margin: 1px 0 0; }
.timeline .detail { margin: 2px 0 0; font-size: 14px; color: var(--muted); }

/* ---------- Verkostung */
.stars { display: inline-flex; gap: 2px; color: #d29b0e; }
.star { all: unset; cursor: default; display: inline-flex; }
button.star { cursor: pointer; padding: 4px; border-radius: 6px; }
.star ha-icon.i { --mdc-icon-size: 22px; width: 22px; height: 22px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font: 400 14px/1 inherit; padding: 8px 12px; border-radius: 999px; border: 1px solid var(--rule); background: var(--card);
  color: var(--primary-text-color); cursor: pointer; }
.chip[aria-pressed="true"] { background: color-mix(in srgb, var(--beer, var(--primary-color)) 22%, var(--card)); border-color: transparent; font-weight: 500; }
.kat { padding: 12px 0; border-bottom: 1px solid var(--rule); }
.kat h4 { margin: 0 0 8px; font: 500 14px/1.2 inherit; }
.kat .gruppe + .gruppe { margin-top: 6px; }
.bewertung { padding: 14px 0; border-bottom: 1px solid var(--rule); }
.bewertung:last-child { border-bottom: 0; }
.bewertung .kopf { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.bewertung p { margin: 6px 0 0; font-size: 14px; }

/* ---------- Fässer */
.fass { display: grid; grid-template-columns: auto 1fr; gap: 16px; align-items: center; padding: 16px 0; border-bottom: 1px solid var(--rule); }
.fass:last-child { border-bottom: 0; }
.fass-grafik { width: 54px; height: 80px; }
.fass h4 { margin: 0; font: 500 16px/1.2 inherit; }
.fass .rest { font-size: 26px; font-weight: 400; margin: 4px 0; }
.fass .rest small { font-size: 14px; color: var(--muted); }
.fass .reihe { margin-top: 8px; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }

/* ---------- Brautag-Assistent */
.assistent { display: grid; grid-template-columns: 230px 1fr; gap: 22px; align-items: start; }
.schrittliste { list-style: none; margin: 0; padding: 0; position: sticky; top: calc(var(--header-height, 56px) + 16px); }
.schrittliste li button { all: unset; box-sizing: border-box; display: flex; gap: 10px; align-items: center; width: 100%;
  padding: 8px 10px; border-radius: 10px; cursor: pointer; font-size: 14px; }
.schrittliste li button[aria-current="step"] { background: color-mix(in srgb, var(--beer) 18%, transparent); font-weight: 500; }
.schrittliste .nr { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; font-size: 12px; flex: none;
  border: 1.5px solid var(--rule); }
.schrittliste .erledigt .nr { background: var(--hop); border-color: var(--hop); color: #fff; }
.schrittliste .phase { font-size: 12px; color: var(--muted); margin: 12px 10px 4px; }
.schritt h2 { font: 400 30px/1.15 var(--label-font); margin: 0; }
.schritt .untertitel { font-size: 18px; color: var(--muted); margin: 4px 0 0; }
.schritt .zeilen-text { margin: 18px 0 0; padding: 0; list-style: none; font-size: 17px; line-height: 1.5; }
.schritt .zeilen-text li { padding: 6px 0; border-bottom: 1px solid var(--rule); }
.timer { display: grid; grid-template-columns: auto 1fr; gap: 20px; align-items: center; margin-top: 20px; padding: 18px;
  border-radius: 16px; background: color-mix(in srgb, var(--beer) 12%, var(--card)); }
.timer svg { width: 120px; height: 120px; }
.timer .ring-bg { fill: none; stroke: var(--rule); stroke-width: 10; }
.timer .ring { fill: none; stroke: var(--beer); stroke-width: 10; stroke-linecap: round; transform: rotate(-90deg); transform-origin: 50% 50%; }
.timer .zeit { font-size: 22px; font-weight: 500; fill: var(--primary-text-color); }
.timer .ereignisse { list-style: none; margin: 8px 0 0; padding: 0; font-size: 14px; }
.timer .ereignisse li { padding: 3px 0; display: flex; gap: 8px; align-items: center; }
.timer .ereignisse li.vorbei { color: var(--muted); text-decoration: line-through; }
.schritt-nav { display: flex; justify-content: space-between; gap: 10px; margin-top: 24px; }

/* ---------- Formulare */
.felder { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px 14px; align-items: end; }
.feld { display: grid; gap: 4px; font-size: 13px; color: var(--muted); }
.feld.voll { grid-column: 1 / -1; }
.eingabe { display: flex; align-items: center; gap: 6px; }
.eingabe em { font-style: normal; color: var(--muted); min-width: 22px; }
select, .feld input, .feld textarea {
  font: 16px/1.3 inherit; color: var(--primary-text-color); background: var(--card);
  border: 1px solid color-mix(in srgb, var(--primary-text-color) 25%, transparent); border-radius: 10px; padding: 9px 10px; width: 100%; min-height: 42px;
}
.info { display: flex; flex-wrap: wrap; gap: 4px 24px; margin: 16px 0 0; padding: 12px 14px; border-radius: 12px;
  background: color-mix(in srgb, var(--beer, var(--primary-color)) 12%, var(--card)); }
.info dd { font-size: 16px; }
.liste-check { display: grid; gap: 2px; }
.profil { display: grid; gap: 8px; }
.profil .stufe { display: grid; grid-template-columns: 1fr 1fr auto; gap: 8px; align-items: end; }

/* ---------- Lager */
table.lager td { vertical-align: middle; }
table.lager input { font-family: inherit; font-size: 16px; box-sizing: border-box; color: var(--primary-text-color); background: var(--card); min-height: 38px;
  border: 1px solid color-mix(in srgb, var(--primary-text-color) 25%, transparent); border-radius: 8px; padding: 6px 8px; }
table.lager input:disabled { opacity: .45; }
table.lager td:first-child { white-space: normal; }
table.lager .badge { margin-top: 4px; font-size: 12px; padding: 2px 8px; }
.lager-gruppe { padding-top: 14px; font-weight: 500; color: var(--primary-text-color); border-bottom: 1px solid var(--rule); }

/* ---------- Leer */
.empty { text-align: center; padding: 56px 16px; }
.empty .gross { font: 400 24px/1.3 var(--label-font); margin: 0 0 8px; }
.empty ha-icon.i { --mdc-icon-size: 40px; width: 40px; height: 40px; color: var(--muted); margin-bottom: 10px; }
footer { margin-top: 28px; font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }

/* ---------- Dialoge */
.scrim { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 10; }
.dialog { position: fixed; z-index: 11; left: 50%; top: 50%; transform: translate(-50%, -50%);
  width: min(620px, calc(100vw - 24px)); max-height: calc(100vh - 40px); overflow: auto;
  background: var(--card); color: var(--primary-text-color); border-radius: 20px; padding: 22px;
  box-shadow: 0 18px 48px rgba(0,0,0,.35); border-top: 6px solid var(--beer, var(--primary-color)); }
.dialog:focus { outline: none; }
.dialog > p { margin: 10px 0; }
.dlg-head { display: flex; gap: 14px; align-items: center; margin-bottom: 8px; }
.dlg-head h2 { margin: 0; font: 400 26px/1.15 var(--label-font); }
.dlg-kicker { margin: 0; color: var(--muted); font-size: 14px; }
.dlg-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 18px; }
.seg { display: inline-flex; gap: 2px; padding: 3px; border-radius: 10px; background: var(--rule); margin: 4px 0 12px; }
.seg button { border: 0; background: transparent; color: var(--muted); font: 500 14px/1 inherit; padding: 8px 14px; border-radius: 8px; cursor: pointer; }
.seg button[aria-checked="true"] { background: var(--card); color: var(--primary-text-color); box-shadow: 0 1px 2px rgba(0,0,0,.12); }
.brautag-form section { margin-top: 14px; }
.brautag-form h3 { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.step { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; font-size: 13px;
  background: color-mix(in srgb, var(--beer) 35%, var(--card)); }
.confirm { padding: 10px 12px; border-radius: 10px; background: color-mix(in srgb, var(--hop) 12%, transparent); font-size: 14px; }

.toast { position: fixed; left: 50%; bottom: 24px; transform: translate(-50%, 20px); opacity: 0; pointer-events: none;
  background: var(--primary-text-color); color: var(--card); padding: 12px 16px; border-radius: 12px; font-size: 14px;
  transition: opacity .2s, transform .2s; z-index: 12; max-width: calc(100vw - 32px); }
.toast.show { opacity: 1; transform: translate(-50%, 0); }
@media (prefers-reduced-motion: reduce) { .toast, .switch .knob, .switch .knob::after { transition: none; } }

@media (max-width: 720px) {
  .assistent { grid-template-columns: 1fr; }
  .schrittliste { position: static; display: flex; overflow-x: auto; gap: 4px; padding-bottom: 6px; }
  .schrittliste .phase { display: none; }
  .schrittliste li button { width: auto; white-space: nowrap; }
  .schrittliste li button .lbl { display: none; }
  .schrittliste li button[aria-current="step"] .lbl { display: inline; }
}
@media (max-width: 600px) {
  main { padding: 12px 12px 40px; }
  .card-body { padding: 16px; }
  .card-head { padding: 14px 16px 0; }
  .card-actions { padding: 12px 16px 14px; }
  .detail-head { grid-template-areas: "glas text" "facts facts" "aktionen aktionen"; gap: 0 14px; padding: 16px; border-radius: 18px; }
  .detail-head h2 { font-size: 26px; }
  .facts { display: grid; grid-template-columns: 1fr 1fr; margin-top: 14px; }
  .facts > div { min-width: 0; }
  .hero-aktionen .btn { flex: 1 1 auto; justify-content: center; }
  .tabs { display: flex; width: 100%; }
  .tabs button { flex: 1; justify-content: center; padding: 9px 6px; }
  .subtabs { -webkit-mask-image: linear-gradient(90deg, #000 88%, transparent); mask-image: linear-gradient(90deg, #000 88%, transparent); }
  .subtabs button { padding: 10px 11px; font-size: 14px; }
  .hide-narrow { display: none; }
  .sudkarte { grid-template-columns: auto 1fr auto; padding: 14px; gap: 4px 14px; }
  .sudkarte .rechts { grid-column: 3; grid-row: 1; }
  .sudkarte .rechts .spark, .sudkarte .rechts .badge { display: none; }
  .sudkarte .kpis { grid-column: 2 / span 2; }
  .sudkarte .fortschritt { grid-column: 1 / -1; grid-row: 4; }
  .sudkarte h2 { font-size: 21px; }
  .sudkarte .kpis { gap: 4px 16px; }
  .sudliste .card-actions .btn { flex: 1 1 0; justify-content: center; }
  .timer { grid-template-columns: 1fr; justify-items: center; text-align: center; }
  .dialog { top: auto; bottom: 0; transform: translateX(-50%); width: 100vw; border-radius: 20px 20px 0 0;
    max-height: calc(100vh - 24px); padding: 18px 16px calc(18px + env(safe-area-inset-bottom)); }
  .felder { grid-template-columns: 1fr 1fr; }
  .dlg-actions { position: sticky; bottom: calc(-18px - env(safe-area-inset-bottom)); background: var(--card);
    margin: 18px -16px 0; padding: 12px 16px calc(12px + env(safe-area-inset-bottom)); border-top: 1px solid var(--rule); }
  .dlg-actions .btn { flex: 1 1 auto; justify-content: center; }
  .schritt h2 { font-size: 25px; }
  .schritt .zeilen-text { font-size: 16px; }
}
`;
