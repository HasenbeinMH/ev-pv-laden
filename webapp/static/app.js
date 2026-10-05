"use strict";
// Oberflaeche EV PV-Laden – Optik angelehnt an eedc. Icons: Lucide (ISC-Lizenz, lucide.dev).

// ── Icons ───────────────────────────────────────────────────────────────────
const ICONS = {
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  zap: '<path d="M15.914 4a1.5 1.5 0 00-2.474-1.561l-9 9A1.5 1.5 0 005.5 14h4.002a.5.5 0 01.471.666L8.086 20a1.5 1.5 0 002.475 1.56l9-9A1.5 1.5 0 0018.5 10h-3.997a.5.5 0 01-.472-.667z"/>',
  plug: '<path d="M12 22v-5"/><path d="M15 8V2"/><path d="M17 8a1 1 0 0 1 1 1v4a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1z"/><path d="M9 8V2"/>',
  "battery-charging": '<path d="m11 7-3 5h4l-3 5"/><path d="M14.856 6H16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.935"/><path d="M22 14v-4"/><path d="M5.14 18H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h2.936"/>',
  car: '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>',
  activity: '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
  gauge: '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
  "list-checks": '<path d="M13 5h8"/><path d="M13 12h8"/><path d="M13 19h8"/><path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/>',
  settings: '<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"/><circle cx="12" cy="12" r="3"/>',
  moon: '<path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"/>',
  "chart-line": '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="m19 9-5 5-4-4-3 3"/>',
  scale: '<path d="M12 3v18"/><path d="m19 8 3 8a5 5 0 0 1-6 0zV7"/><path d="M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1"/><path d="m5 8 3 8a5 5 0 0 1-6 0zV7"/><path d="M7 21h10"/>',
  history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  stethoscope: '<path d="M11 2v2"/><path d="M5 2v2"/><path d="M5 3H4a2 2 0 0 0-2 2v4a6 6 0 0 0 12 0V5a2 2 0 0 0-2-2h-1"/><path d="M8 15a6 6 0 0 0 12 0v-3"/><circle cx="20" cy="10" r="2"/>',
  house: '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  "utility-pole": '<path d="M12 2v20"/><path d="M2 5h20"/><path d="M3 3v2"/><path d="M7 3v2"/><path d="M17 3v2"/><path d="M21 3v2"/><path d="m19 5-7 7-7-7"/>',
};
const icon = n => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;
document.querySelectorAll("[data-icon]").forEach(el => { el.innerHTML = icon(el.dataset.icon); });

// ── Hilfen ──────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const zahl = (v, st = 0) => v.toLocaleString("de-DE", {minimumFractionDigits: st, maximumFractionDigits: st});
const watt = v => v === null || v === undefined ? "–" : zahl(Math.round(v)) + " W";
const wattHtml = v => v === null || v === undefined ? "–" : `${zahl(Math.round(v))}<small>W</small>`;
const kwh = v => v === null || v === undefined ? "–" : zahl(v, 2) + " kWh";
const kwhHtml = v => v === null || v === undefined ? "–" : `${zahl(v, 2)}<small>kWh</small>`;
const zeit = iso => iso ? new Date(iso).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}) : "läuft";
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const holen = async url => (await fetch(url)).json();
function fmt(v, art) {
  if (v === null || v === undefined) return "–";
  if (typeof v === "boolean") return v ? "ja" : "nein";
  if (typeof v !== "number") return String(v);
  if (art === "leistung") return watt(v);
  if (art === "energie") return zahl(v, 3) + " kWh";
  if (art === "prozent") return zahl(v, 1) + " %";
  if (art === "strom") return zahl(v, 1) + " A";
  return v.toLocaleString("de-DE");
}

// ── Reiter und Hell/Dunkel ──────────────────────────────────────────────────
const diagramme = [];
function seiteZeigen() {
  const name = (location.hash || "#live").slice(1);
  document.querySelectorAll(".seite").forEach(s => s.classList.toggle("aktiv", s.id === "seite-" + name));
  document.querySelectorAll("nav.reiter a").forEach(a => a.classList.toggle("aktiv", a.dataset.seite === name));
  if (!document.querySelector(".seite.aktiv")) { location.hash = "#live"; return; }
  setTimeout(() => diagramme.forEach(d => d && d.resize()), 0);
  laden();
}
window.addEventListener("hashchange", seiteZeigen);

function dunkel() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}
function themeKnopf() { $("theme").innerHTML = icon(dunkel() ? "sun" : "moon"); }
$("theme").onclick = () => {
  const neu = dunkel() ? "light" : "dark";
  document.documentElement.dataset.theme = neu;
  try { localStorage.setItem("evpv-theme", neu); } catch (e) {}
  themeKnopf();
  verlauf(); prognoseZeichnen(); sauberkeitZeichnen(); heuteLaden();
  flussAufbauen(); flussSetzen(letzteWerte);
};
themeKnopf();

// ── Energiefluss (eigenes SVG im Stil von eedc) ─────────────────────────────
// Sternpunkt in der Mitte = Hausnetz (wie die Sammelschiene im Verteiler): Erzeuger und
// Speicher speisen ein, Haus und Auto beziehen.
const MITTE = {x: 450, y: 260, r: 34};
const KNOTEN = {
  pv:   {x: 365, y: 16,  farbe: "--solar",     icon: "sun", name: "PV"},
  netz: {x: 20,  y: 217, farbe: "--netz",      icon: "utility-pole", name: "Stromnetz"},
  haus: {x: 710, y: 217, farbe: "--verbrauch", icon: "house", name: "Haus"},
  akku: {x: 150, y: 412, farbe: "--akku",      icon: "battery-charging", name: "Hausakku"},
  auto: {x: 580, y: 412, farbe: "--auto",      icon: "car", name: "Auto"},
};
const LINIEN = {   // Richtung des Pfads: Quelle -> Sternpunkt (pv, netz, akku), Sternpunkt -> Verbraucher (haus, auto)
  pv:   "M450,102 C450,160 450,180 450,226",
  netz: "M190,260 C280,260 340,260 416,260",
  haus: "M484,260 C560,260 620,260 710,260",
  akku: "M235,412 C235,330 360,296 426,284",
  auto: "M474,284 C540,296 665,330 665,412",
};
const NS = "http://www.w3.org/2000/svg";
let flussZustand = {};
let hausEnthaeltAuto = true;
let letzteWerte = {};

function flussAufbauen() {
  const svg = $("fluss");
  flussZustand = {};
  let h = "";
  for (const [k, d] of Object.entries(LINIEN)) {
    h += `<path class="linie leer" d="${d}" stroke-width="3"/><path class="linie" id="l-${k}" d="${d}" stroke-width="0"/><g id="p-${k}"></g>`;
  }
  for (const [k, n] of Object.entries(KNOTEN)) {
    const f = `var(${n.farbe})`;
    h += `<g class="knoten" id="n-${k}">
      <rect x="${n.x}" y="${n.y}" width="170" height="86" rx="16"
        style="fill:color-mix(in srgb, ${f} 14%, var(--karte));stroke:color-mix(in srgb, ${f} 55%, transparent)"/>
      <svg x="${n.x + 72}" y="${n.y + 8}" width="26" height="26" viewBox="0 0 24 24" class="i" style="color:${f}">${ICONS[n.icon]}</svg>
      <text class="wert" x="${n.x + 85}" y="${n.y + 57}" text-anchor="middle" id="w-${k}">–</text>
      <text class="name" x="${n.x + 85}" y="${n.y + 77}" text-anchor="middle" id="t-${k}">${n.name}</text>
    </g>`;
  }
  // Auto: Aufteilung PV/Akku/Netz als Balken unter der Kachel
  h += `<g id="auto-balken"></g>`;
  h += `<circle class="mitte" cx="${MITTE.x}" cy="${MITTE.y}" r="${MITTE.r}"><title>Hausnetz</title></circle>
    <svg x="${MITTE.x - 14}" y="${MITTE.y - 14}" width="28" height="28" viewBox="0 0 24 24" class="i"
      style="color:var(--primary)">${ICONS.zap}</svg>`;
  svg.innerHTML = h;
}

function linieSetzen(k, p, richtung, farbe) {
  const linie = $("l-" + k), punkte = $("p-" + k);
  const aktiv = p !== null && Math.abs(p) > 30;
  linie.setAttribute("stroke-width", aktiv ? (2 + Math.min(Math.abs(p) / 1000, 8) * 1.1).toFixed(1) : 0);
  linie.style.stroke = `var(${farbe})`;
  const dauer = !aktiv ? 0 : Math.abs(p) > 5000 ? 1.3 : Math.abs(p) > 2000 ? 2 : Math.abs(p) > 500 ? 3 : 4.5;
  const schluessel = `${aktiv}|${richtung}|${farbe}|${dauer}`;
  if (flussZustand[k] === schluessel) return;   // Animation nicht neu starten
  flussZustand[k] = schluessel;
  punkte.innerHTML = "";
  if (!aktiv) return;
  for (let i = 0; i < 3; i++) {
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("r", "4.5");
    c.style.fill = `var(${farbe})`;
    const a = document.createElementNS(NS, "animateMotion");
    a.setAttribute("dur", dauer + "s");
    a.setAttribute("begin", (-i * dauer / 3).toFixed(2) + "s");
    a.setAttribute("repeatCount", "indefinite");
    a.setAttribute("path", LINIEN[k]);
    a.setAttribute("keyPoints", richtung > 0 ? "0;1" : "1;0");
    a.setAttribute("keyTimes", "0;1");
    a.setAttribute("calcMode", "linear");
    c.appendChild(a);
    punkte.appendChild(c);
  }
}

function aufteilen(p, netz, akku) {    // wie bilanz.py: Haus zuerst, Auto bekommt den Ueberschuss
  p = Math.max(p, 0);
  const n = Math.min(p, Math.max(netz, 0));
  const a = Math.min(p - n, Math.max(akku, 0));
  return {pv: p - n - a, akku: a, netz: n};
}

function flussSetzen(w) {
  if (!$("w-haus")) return;
  const pv = w.pv_w ?? null, netz = w.netz_w ?? null, akku = w.akku_w ?? null, auto = w.auto_w ?? null;
  $("w-pv").textContent = watt(pv);
  $("w-netz").textContent = watt(netz === null ? null : Math.abs(netz));
  $("t-netz").textContent = netz === null ? "Stromnetz" : netz >= 0 ? "Netzbezug" : "Einspeisung";
  $("w-akku").textContent = watt(akku === null ? null : Math.abs(akku));
  const soc = w.akku_soc;
  $("t-akku").innerHTML = soc === null || soc === undefined ? "Hausakku"
    : `<tspan class="soc" style="fill:var(${soc >= 50 ? "--ok" : soc >= 20 ? "--warnung" : "--kritisch"})">${zahl(soc)} %</tspan> · ${akku === null ? "" : akku > 30 ? "entlädt" : akku < -30 ? "lädt" : "ruht"}`;
  $("w-auto").textContent = watt(auto);
  const phasen = ["auto_i1", "auto_i2", "auto_i3"].filter(n => (w[n] ?? 0) >= 1).length;
  $("t-auto").textContent = w.auto_steckt === false ? "nicht angesteckt" : phasen ? `Auto · ${phasen}-phasig` : "Auto";
  // Hausverbrauch: eigener Sensor (ohne Auto, falls er die Wallbox mitmisst), sonst Bilanz
  let haus = null;
  if (w.haus_w !== null && w.haus_w !== undefined) {
    haus = hausEnthaeltAuto ? (auto === null ? null : w.haus_w - auto) : w.haus_w;
    if (haus === null && hausEnthaeltAuto) haus = w.haus_w;   // Wallbox unbekannt: Gesamtwert
  } else if (![pv, netz, akku, auto].some(v => v === null)) {
    haus = pv + netz + akku - auto;
  }
  if (haus !== null) haus = Math.max(haus, 0);
  $("w-haus").textContent = watt(haus);
  kpiSetzen(pv, haus, akku, soc, auto, phasen, w);
  $("t-haus").textContent = w.haus_w !== null && w.haus_w !== undefined ? "Haus" : "Haus (berechnet)";

  linieSetzen("pv", pv, 1, "--solar");
  linieSetzen("netz", netz, netz !== null && netz >= 0 ? 1 : -1, netz !== null && netz >= 0 ? "--netz" : "--einspeisung");
  linieSetzen("akku", akku, akku !== null && akku >= 0 ? 1 : -1, akku !== null && akku >= 0 ? "--akku" : "--akku-laden");
  linieSetzen("auto", auto, 1, "--auto");
  linieSetzen("haus", haus, 1, "--verbrauch");

  const b = $("auto-balken");
  if (auto !== null && netz !== null && akku !== null && auto > 30) {
    const t = aufteilen(auto, netz, akku), x0 = KNOTEN.auto.x + 12, breite = 146;
    let x = x0, h = "";
    for (const [q, f] of [["pv", "--solar"], ["akku", "--akku"], ["netz", "--netz"]]) {
      const bw = breite * t[q] / auto;
      if (bw > 0.5) h += `<rect x="${x.toFixed(1)}" y="505" width="${bw.toFixed(1)}" height="7" style="fill:var(${f})"/>`;
      x += bw;
    }
    b.innerHTML = `<rect x="${x0}" y="505" width="${breite}" height="7" rx="3.5" style="fill:var(--linie)"/>${h}`;
  } else {
    b.innerHTML = "";
  }
}

// ── Dashboard ───────────────────────────────────────────────────────────────
const kwHtml = v => v === null || v === undefined ? "–"
  : Math.abs(v) >= 1000 ? `${zahl(v / 1000, 1)}<small>kW</small>` : `${zahl(Math.round(v))}<small>W</small>`;
function kpiSetzen(pv, haus, akku, soc, auto, phasen, w) {
  $("kp-pv").innerHTML = kwHtml(pv);
  $("kp-haus").innerHTML = kwHtml(haus);
  $("kp-haus-unter").textContent = w.haus_w !== null && w.haus_w !== undefined ? "Verbrauch ohne Auto" : "Verbrauch (berechnet)";
  $("kp-akku").innerHTML = akku === null ? "–" : (akku < -30 ? "+" : akku > 30 ? "−" : "") + kwHtml(Math.abs(akku));
  $("kp-akku-unter").textContent = (soc === null || soc === undefined ? "" : zahl(soc) + " % · ")
    + (akku === null ? "" : akku < -30 ? "wird geladen" : akku > 30 ? "entlädt" : "ruht");
  $("kp-akku-box").style.setProperty("--c", akku !== null && akku < -30 ? "var(--akku-laden)" : "var(--akku)");
  $("kp-auto").innerHTML = kwHtml(auto);
  $("kp-auto-unter").textContent = w.auto_steckt === false ? "nicht angesteckt"
    : phasen ? `Ladeleistung · ${phasen}-phasig` : "Ladeleistung";
}

let laufendeLadung = null, letzteRegelung = null;
const MODUS_TEXT = {aus: "Laden gesperrt", nur_pv: "nur Überschuss", min_pv: "6 A + Überschuss",
                    sofort: "volle Leistung", zielzeit: "bis zur Abfahrt"};
function autoKarte() {
  const r = letzteRegelung, w = letzteWerte;
  if (!r) return;
  const z = r.zielzeit || {}, a = r.ausgang || {}, soc = z.soc;
  $("ac-soc").textContent = soc === null || soc === undefined ? "–" : zahl(soc);
  $("ac-fuell").style.width = (soc || 0) + "%";
  const ziel = $("ac-ziel");
  ziel.style.display = r.modus === "zielzeit" ? "block" : "none";
  ziel.style.left = `calc(${r.parameter.ziel_soc}% - 1px)`;
  $("ac-steckt").textContent = w.auto_steckt === true ? "angesteckt" : w.auto_steckt === false ? "nicht angesteckt" : "";
  $("ac-leistung").textContent = watt(w.auto_w);
  const l = laufendeLadung;
  $("ac-geladen").textContent = l ? `${zahl(l.eto, 1)} kWh geladen` : (soc === null || soc === undefined ? "SoC unter „Details“ eintragen" : "");
  const laedt = (w.auto_w || 0) > 100;
  $("ac-status").className = "auto-status " + (laedt ? "laedt" : a.freigabe ? "wartet" : "");
  const grund = (a.grund || "").split(" · ")[0];   // Zielzeit-Teil steht im Plan-Kasten
  $("ac-status-text").textContent = laedt ? (a.freigabe ? grund || "lädt" : "lädt") : grund || "–";
  $("ac-status-text").title = a.grund || "";
  const strom = Math.max(...["auto_i1", "auto_i2", "auto_i3"].map(n => w[n] || 0));
  const phasen = ["auto_i1", "auto_i2", "auto_i3"].filter(n => (w[n] ?? 0) >= 1).length;
  $("ac-info").textContent = [r.modi[r.modus], phasen ? `${phasen}-phasig` : null,
                              strom >= 1 ? `${zahl(strom, 1)} A` : null, "Treiber " + r.treiber].filter(Boolean).join(" · ");
  $("ac-pause").textContent = r.modus === "aus" ? "Laden fortsetzen" : "Laden pausieren";
  // Zielzeit-Plan bzw. Herkunft des SoC
  const p = z.plan, zeilen = [];
  if (r.modus === "zielzeit" && p) {
    zeilen.push(`<b>Zielzeit: ${zahl(r.parameter.ziel_soc)} % bis ${esc(uhr(p.abfahrt))}</b>`);
    if (p.erreicht) zeilen.push("Ziel erreicht – weiter nur PV");
    else if (p.benoetigt_kwh !== null) zeilen.push(`noch ${zahl(p.benoetigt_kwh, 1)} kWh`
      + (p.sofort ? " · lädt mit Netz" : p.spaetester_start ? ` · Netz ab ${esc(uhr(p.spaetester_start))}` : ""));
    else zeilen.push("SoC fehlt – unter „Details“ eintragen");
  }
  if (z.soc_quelle) zeilen.push(`SoC: ${esc(z.soc_quelle)} ${zahl(z.soc_gesetzt_wert)} % (${esc(uhr(z.soc_gesetzt))}), hochgerechnet`);
  $("ac-plan").innerHTML = zeilen.map(t => `<div>${t}</div>`).join("");
}
$("ac-pause").onclick = () => {
  const r = letzteRegelung;
  if (!r) return;
  if (r.modus === "aus") {
    let vorher = "nur_pv";
    try { vorher = localStorage.getItem("evpv-modus-vorher") || vorher; } catch (e) {}
    parameterSenden({modus: vorher});
  } else {
    try { localStorage.setItem("evpv-modus-vorher", r.modus); } catch (e) {}
    parameterSenden({modus: "aus"});
  }
};

let heuteDiagramm = null;
async function heuteLaden() {
  if (!window.echarts || (location.hash && location.hash !== "#live")) return;
  try {
    const v = await holen("api/heute");
    if (!v.daten) return;
    heuteDiagramm = heuteDiagramm || echarts.init($("heute-diagramm"));
    diagramme[3] = heuteDiagramm;
    const i = Object.fromEntries(v.spalten.map((n, j) => [n, j]));
    const reihe = (name, sp, farbe, flaeche) => ({name, type: "line", showSymbol: false, smooth: true,
      data: v.daten.map(d => [d[i.zeit] * 1000, d[i[sp]] === null ? null : Math.max(d[i[sp]], 0)]),
      lineStyle: {width: 1.5}, color: css(farbe), ...(flaeche ? {areaStyle: {opacity: .25}} : {})});
    const a = achsen();
    const tag = new Date(); tag.setHours(0, 0, 0, 0);
    heuteDiagramm.setOption({
      animation: false, grid: {left: 44, right: 8, top: 26, bottom: 22},
      legend: {top: 0, itemWidth: 12, textStyle: {color: a.text, fontSize: 11}},
      tooltip: a.tooltip,
      xAxis: {...a.x, min: tag.getTime(), max: tag.getTime() + 86400e3},
      yAxis: {...a.y, axisLabel: {...a.y.axisLabel,
        formatter: x => zahl(x / 1000, Number.isInteger(x / 1000) ? 0 : 1) + " kW"}},
      series: [reihe("PV", "pv", "--solar", true), reihe("Haus", "haus", "--verbrauch", true),
               reihe("Auto", "auto", "--auto", true),
               ...(prognose && prognose.stunden ? [{name: "PV-Prognose", type: "line", step: "middle",
                 showSymbol: false, color: css("--solar"), lineStyle: {width: 1.5, type: "dashed"},
                 data: prognose.stunden.map(s => [new Date(s.zeit).getTime() - 1800e3, s.wh])
                   .filter(([t]) => t >= tag.getTime() && t < tag.getTime() + 86400e3)}] : [])],
    }, true);
    $("heute-unter").textContent = v.daten.length && v.daten[0][0] * 1000 > tag.getTime() + 3600e3
      ? "seit Add-on-Start " + new Date(v.daten[0][0] * 1000).toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"})
      : "Minutenmittel seit Mitternacht";
  } catch (e) {}
}
function uhrStellen() {
  $("uhr").textContent = new Date().toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"});
}

// ── Status / Live ───────────────────────────────────────────────────────────
async function status() {
  try {
    const s = await holen("api/status");
    const m = $("marke");
    trackerZeigen(s.tracker);
    m.textContent = s.trockenlauf ? "Trockenlauf" : "LIVE";
    m.className = "marke " + (s.trockenlauf ? "trocken" : "live");
    m.title = s.trockenlauf_option ? "Trockenlauf fest über die Add-on-Option (trockenlauf: true)"
      : "Klicken zum Umschalten";
    m.dataset.trocken = s.trockenlauf ? "1" : "";
    m.dataset.gesperrt = s.trockenlauf_option ? "1" : "";
    $("konfig-fehler").hidden = s.konfig_ok;
    $("konfig-fehler").innerHTML = s.konfig_fehler.map(f => "<div>" + esc(f) + "</div>").join("");

    hausEnthaeltAuto = s.haus_enthaelt_auto !== false;
    const w = {};
    s.signale.forEach(z => { w[z.name] = z.gueltig ? z.wert : null; });
    letzteWerte = w;
    flussSetzen(w);

    $("s-ha").className = "punkt-status " + (s.ha.verbunden ? "ok" : "schlecht");
    $("s-mqtt").className = "punkt-status " + (s.mqtt.verbunden ? "ok" : "schlecht");
    $("s-goe").className = "punkt-status " + (w.goe_lebenszeichen !== null && w.goe_lebenszeichen !== undefined ? "ok" : "schlecht");
    if (s.treiber) $("s-treiber").textContent = `Treiber ${s.treiber.name}${s.trockenlauf ? " (Trockenlauf)" : ""}`
      + (s.treiber.verriegelt ? " · VERRIEGELT" : "");

    if (location.hash === "#diagnose") diagnose(s);
    const g = s.grenzen;
    if (g) $("einst-grenzen").textContent = `Ladestrom ${g.min_strom_a}–${g.max_strom_a} A · einphasig höchstens ${g.strom_1ph_max_a} A`
      + ` · Messwerte gelten bis ${g.max_alter_s} s Alter · Trockenlauf ${s.trockenlauf_option ? "fest über die Add-on-Option" : "über Kennzeichen oben schaltbar"}`;
    autoKarte();
  } catch (e) { /* Add-on startet gerade neu */ }
}

function diagnose(s) {
  $("d-konfig").innerHTML = s.konfig_ok ? '<span class="ok">in Ordnung</span>' : '<span class="schlecht">fehlerhaft</span>';
  const g = s.grenzen;
  $("d-grenzen").textContent = g ? `${g.min_strom_a}–${g.max_strom_a} A · einphasig ≤ ${g.strom_1ph_max_a} A · Alter ≤ ${g.max_alter_s} s` : "";
  $("d-ha").innerHTML = s.ha.verbunden ? '<span class="ok">verbunden</span>' : '<span class="schlecht">getrennt</span>';
  $("d-ha-unter").textContent = s.ha.verbunden ? "Version " + (s.ha.version || "") : (s.ha.fehler || "");
  $("d-mqtt").innerHTML = s.mqtt.verbunden ? '<span class="ok">verbunden</span>' : '<span class="schlecht">getrennt</span>';
  $("d-mqtt-unter").textContent = s.mqtt.verbunden ? "Gerät „EV PV-Laden“" : (s.mqtt.fehler || "");
  $("signale").innerHTML = s.signale.map(z => {
    const st = z.gueltig ? '<span class="ok">gültig</span>'
      : !z.empfangen ? `<span class="schlecht">${z.pflicht ? "fehlt" : "fehlt (optional)"}</span>`
      : '<span class="schlecht">ungültig</span>';
    return `<tr><td>${esc(z.beschreibung)}${z.invertiert ? ' <span class="klein">(invertiert)</span>' : ""}</td>
      <td class="mono">${esc(z.entity_id)}</td><td class="zahl">${fmt(z.wert, z.art)}</td>
      <td class="mono klein">${esc(z.roh)} ${esc(z.einheit || "")}</td>
      <td class="zahl">${z.alter_s === null ? "–" : zahl(z.alter_s, 1) + " s"}</td>
      <td class="zahl klein">${z.intervall_s === null ? "–" : zahl(z.intervall_s, 1) + " s (" + zahl(z.intervall_max_s, 1) + ")"}</td><td>${st}</td></tr>`;
  }).join("");
  if (s.treiber) {
    $("verriegelt").textContent = s.treiber.verriegelt ? "VERRIEGELT: " + s.treiber.verriegelt
      : s.treiber.wiederanlauf && s.treiber.wiederanlauf !== "ok" ? "Wiederanlauf: " + s.treiber.wiederanlauf : "";
    $("aktionen").innerHTML = s.treiber.aktionen.map(([z, t, e]) =>
      `<tr><td class="klein">${esc(z)}</td><td class="mono">${esc(t)}</td>
       <td class="${e === "ok" ? "ok" : e === "Trockenlauf" ? "klein" : "schlecht"}">${esc(e)}</td></tr>`).join("")
      || '<tr><td class="klein">noch keine Aktionen</td></tr>';
  }
}

// ── Regelung ────────────────────────────────────────────────────────────────
const ZUSTAND = {bereit: "bereit", startet: "Start läuft", laedt: "lädt", stoppt: "Stopp läuft", pause: "Pause"};
const PARAM = [
  ["akku_soc_schwelle", "Akku-SoC-Schwelle (%) – darunter lädt der Hausakku zuerst"],
  ["akku_unterstuetzung_w", "Akku darf Auto unterstützen mit max. (W)"],
  ["akku_unterstuetzung_soc", "… oberhalb SoC (%)"],
  ["tau_s", "Glättung, Zeitkonstante (s)"],
  ["start_w", "Start ab Überschuss (W)"], ["start_verz_s", "… anliegend für (s)"],
  ["stopp_w", "Stopp unter Überschuss (W)"], ["stopp_verz_s", "… anliegend für (s)"],
  ["min_ladedauer_s", "Mindestladedauer (s)"], ["min_pause_s", "Mindestpause (s)"],
  ["ohne_pv", "Min + PV, wenn keine PV da ist (Nacht)", "ohne_pv_wahl"],
  ["ohne_pv_unter_w", "„keine PV“ unter (W)"], ["ohne_pv_unter_s", "… für (s)"],
  ["ohne_pv_ueber_w", "„PV wieder da“ über (W)"], ["ohne_pv_ueber_s", "… für (s)"],
  ["wiederanlauf", "Lädt nach Pause nicht wieder an (nur Treiber ids)", "wiederanlauf_wahl"],
  ["wiederanlauf_s", "… erkannt nach Freigabe ohne Ladung (s)"],
];
let paramGeladen = false;
async function parameterSenden(daten) {
  const r = await fetch("api/parameter", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(daten)});
  const j = await r.json();
  const m = $("param-meldung");
  m.textContent = j.ok ? "gespeichert" : j.fehler.join("; ");
  m.className = j.ok ? "ok" : "schlecht";
  regelung();
}
$("param-speichern").onclick = () => {
  const daten = {};
  $("param-form").querySelectorAll("input, select").forEach(e => {
    daten[e.name] = e.tagName === "SELECT" ? e.value : Number(e.value);
  });
  parameterSenden(daten);
};

// ── Zielzeit ────────────────────────────────────────────────────────────────
let zzGeladen = false;
const uhr = iso => iso ? new Date(iso).toLocaleString("de-DE", {weekday: "short", hour: "2-digit", minute: "2-digit"}) : "–";
function pvBis(bisIso) {
  // Erwartete PV-Erzeugung bis zur Abfahrt aus der Prognose (nur Hinweis, nicht geplant)
  if (!prognose || !prognose.verfuegbar || !bisIso) return null;
  const jetzt = Date.now(), bis = new Date(bisIso).getTime();
  let wh = 0;
  for (const h of prognose.stunden) {
    const ende = new Date(h.zeit).getTime(), beginn = ende - 3600e3;
    const anteil = (Math.min(ende, bis) - Math.max(beginn, jetzt)) / 3600e3;
    if (anteil > 0) wh += h.wh * Math.min(anteil, 1);
  }
  return wh / 1000;
}
function zielzeitZeigen(r) {
  const z = r.zielzeit, p = r.parameter, plan = z.plan;
  $("zz-soc").textContent = z.soc === null ? "–" : zahl(z.soc) + " %";
  $("zz-soc-quelle").textContent = z.soc === null ? (z.sensor ? "Sensor liefert noch nichts" : "beim Anstecken eintragen")
    : `${z.soc_quelle} ${zahl(z.soc_gesetzt_wert)} % (${uhr(z.soc_gesetzt)}), hochgerechnet`;
  $("zz-status").textContent = r.modus === "zielzeit"
    ? (plan && plan.sofort ? "aktiv – lädt mit Netz" : "aktiv") : "Modus „Zielzeit“ wählen, um sie zu nutzen";
  if (!zzGeladen) {
    $("zz-ziel").value = p.ziel_soc; $("zz-abfahrt").value = p.abfahrt; $("zz-puffer").value = p.puffer_min;
    zzGeladen = true;
  }
  const teile = [];
  if (plan) {
    teile.push(`Abfahrt ${uhr(plan.abfahrt)}`);
    if (plan.benoetigt_kwh !== null) teile.push(`noch ${zahl(plan.benoetigt_kwh, 1)} kWh`);
    if (plan.spaetester_start) teile.push(`spätester Netzstart ${uhr(plan.spaetester_start)}`);
    const pv = pvBis(plan.abfahrt);
    if (pv !== null) teile.push(`PV bis Abfahrt erwartet ≈ ${zahl(pv, 1)} kWh (Hinweis)`);
  }
  teile.push(`geplant mit ${zahl(z.p_plan_w / 1000, 1)} kW`);
  $("zz-plan").innerHTML = teile.map(t => `<span>${esc(t)}</span>`).join("");
}
$("zz-soc-setzen").onclick = async () => {
  const v = $("zz-soc-neu").value;
  if (v === "") return;
  const r = await fetch("api/auto_soc", {method: "POST", headers: {"Content-Type": "application/json"},
                                         body: JSON.stringify({soc: Number(v)})});
  const j = await r.json();
  $("zz-meldung").textContent = j.ok ? "SoC übernommen" : j.fehler.join("; ");
  $("zz-meldung").className = j.ok ? "ok" : "schlecht";
  if (j.ok) $("zz-soc-neu").value = "";
  regelung();
};
$("zz-speichern").onclick = async () => {
  const r = await fetch("api/parameter", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ziel_soc: Number($("zz-ziel").value), abfahrt: $("zz-abfahrt").value,
                          puffer_min: Number($("zz-puffer").value)})});
  const j = await r.json();
  $("zz-meldung").textContent = j.ok ? "gespeichert" : j.fehler.join("; ");
  $("zz-meldung").className = j.ok ? "ok" : "schlecht";
  regelung();
};

$("marke").onclick = async () => {
  const m = $("marke");
  if (m.dataset.gesperrt) {
    alert("Der Trockenlauf ist in den Add-on-Optionen fest eingeschaltet (trockenlauf: true).\n"
          + "Erst wenn die Option aus ist, lässt er sich hier oder in HA umschalten.");
    return;
  }
  const an = !m.dataset.trocken;
  if (!an && !confirm("Trockenlauf ausschalten?\nDas Add-on schreibt dann auf die Wallbox (go-e).")) return;
  const r = await fetch("api/trockenlauf", {method: "POST", headers: {"Content-Type": "application/json"},
                                            body: JSON.stringify({an})});
  const j = await r.json();
  if (!j.ok) alert(j.fehler.join("\n"));
  status();
};

async function regelung() {
  try {
    const r = await holen("api/regelung");
    if (!r.modi) return;
    $("treiber").textContent = "Treiber: " + r.treiber;
    $("modi").innerHTML = Object.entries(r.modi).map(([k, n]) =>
      `<button type="button" data-modus="${k}" class="${k === r.modus ? "aktiv" : ""}">${esc(n)}</button>`).join("");
    $("modi-dash").innerHTML = Object.entries(r.modi).map(([k, n]) =>
      `<button type="button" data-modus="${k}" class="${k === r.modus ? "aktiv" : ""}">${esc(n)}
        <span class="klein" style="display:block">${esc(MODUS_TEXT[k] || "")}</span></button>`).join("");
    document.querySelectorAll("#modi button, #modi-dash button").forEach(b => {
      b.onclick = () => parameterSenden({modus: b.dataset.modus}); });
    letzteRegelung = r;
    autoKarte();
    const gewaehlt = r.parameter.treiber;
    $("treiber-wahl").innerHTML = Object.entries(r.treiber_wahl).map(([k, n]) =>
      `<button type="button" data-treiber="${k}" class="${k === gewaehlt ? "aktiv" : ""}">${esc(n)}</button>`).join("");
    document.querySelectorAll("#treiber-wahl button").forEach(b => { b.onclick = () => parameterSenden({treiber: b.dataset.treiber}); });
    const aktivA = r.treiber.startsWith("A");
    $("treiber-info").textContent = (aktivA !== (gewaehlt === "a") ? "Wechsel folgt, sobald nicht geladen wird · " : "")
      + `Start ab ${zahl(Math.round(r.start_wirksam))} W, Stopp unter ${zahl(Math.round(r.stopp_wirksam))} W`;
    $("md-info").textContent = `Start ab ${zahl(r.start_wirksam / 1000, 1)} kW Überschuss, `
      + `Stopp unter ${zahl(r.stopp_wirksam / 1000, 1)} kW · Hausakku zuerst bis ${zahl(r.parameter.akku_soc_schwelle)} %`
      + (r.modus === "min_pv" ? ` · ohne PV: ${r.ohne_pv_wahl[r.parameter.ohne_pv]}`
         + (r.ohne_pv_aktiv ? " (jetzt aktiv)" : "") : "");
    if (r.zielzeit) zielzeitZeigen(r);
    const a = r.ausgang;
    if (a) {
      $("k-entscheidung").innerHTML = a.freigabe ? '<span class="ok">Laden</span>' : '<span>Nicht laden</span>';
      $("k-entscheidung-box").style.setProperty("--c", a.freigabe ? "var(--ok)" : a.zustand === "pause" ? "var(--warnung)" : "var(--text-3)");
      $("k-grund").textContent = a.grund;
      $("k-erlaubt").innerHTML = wattHtml(a.p_erlaubt);
      $("k-virtuell").textContent = r.treiber.startsWith("A") ? "Treiber A stellt den Strom direkt"
        : "virtueller Netzwert " + watt(a.pgrid_virtuell);
      $("k-verfuegbar").innerHTML = wattHtml(a.p_glatt);
      $("k-roh").textContent = "roh " + watt(a.p_roh) + " · " + (ZUSTAND[a.zustand] || a.zustand);
    }
    if (!paramGeladen) {
      $("param-form").innerHTML = PARAM.map(([k, t, wahl]) => wahl
        ? `<label>${esc(t)}<select name="${k}">${Object.entries(r[wahl]).map(([w, n]) =>
            `<option value="${w}"${w === r.parameter[k] ? " selected" : ""}>${esc(n)}</option>`).join("")}</select></label>`
        : `<label>${esc(t)}<input type="number" step="any" name="${k}" value="${r.parameter[k]}"></label>`).join("");
      paramGeladen = true;
    }
  } catch (e) {}
}

// ── Diagramme ───────────────────────────────────────────────────────────────
function achsen() {
  const leise = css("--text-2"), linie = css("--linie");
  return {
    text: css("--text"),
    x: {type: "time", axisLine: {lineStyle: {color: linie}},
        axisLabel: {color: leise, hideOverlap: true,
                    formatter: {day: "{dd}.{MM}.", hour: "{HH}:{mm}", minute: "{HH}:{mm}", second: "{HH}:{mm}:{ss}"}}},
    y: {type: "value", axisLabel: {color: leise, formatter: v => zahl(v)}, splitLine: {lineStyle: {color: linie}}},
    tooltip: {trigger: "axis", backgroundColor: "#111827", borderColor: "#374151", textStyle: {color: "#fff"},
              valueFormatter: x => x === null || x === undefined ? "–" : zahl(Math.round(x)) + " W"},
  };
}
let diagramm = null;
async function verlauf() {
  if (!window.echarts || location.hash !== "#bilanz") return;
  try {
    const sek = Number($("zeitraum").value);
    const v = await holen(`api/verlauf?sekunden=${sek}&schritt=${sek > 1800 ? 4 : 2}`);
    if (!v.daten) return;
    diagramm = diagramm || echarts.init($("diagramm"));
    diagramme[0] = diagramm;
    const i = Object.fromEntries(v.spalten.map((n, j) => [n, j]));
    const reihe = (name, sp, farbe, extra = {}) => ({name, type: "line", showSymbol: false,
      data: v.daten.map(d => [d[i.zeit] * 1000, d[i[sp]]]), lineStyle: {width: 1.5}, color: css(farbe), ...extra});
    const a = achsen();
    diagramm.setOption({
      animation: false, grid: {left: 60, right: 16, top: 40, bottom: 30},
      legend: {top: 0, type: "scroll", textStyle: {color: a.text}, pageTextStyle: {color: a.text}},
      tooltip: a.tooltip, xAxis: a.x, yAxis: a.y,
      series: [
        reihe("Überschuss roh", "p_roh", "--text-3", {lineStyle: {width: 1, type: "dotted"}}),
        reihe("Überschuss geglättet", "p_glatt", "--einspeisung"),
        reihe("P erlaubt", "p_erlaubt", "--primary", {lineStyle: {width: 2.5}}),
        reihe("Auto", "p_auto", "--auto"),
        reihe("Netz (+Bezug)", "netz", "--netz"),
        reihe("Akku (+Entladung)", "akku", "--akku"),
      ],
    }, true);
  } catch (e) {}
}
$("zeitraum").onchange = verlauf;

let prognose = null, prognoseDiagramm = null;
async function prognoseLaden() {
  try { prognose = await holen("api/prognose"); } catch (e) { return; }
  $("k-prognose").innerHTML = prognose.verfuegbar ? kwhHtml(prognose.heute_rest_kwh) : "–";
  $("k-prognose-unter").textContent = prognose.verfuegbar
    ? `heute ${kwh(prognose.heute_kwh)} · morgen ${kwh(prognose.morgen_kwh)}` : (prognose.fehler || "keine Prognose");
  $("prognose-unter").textContent = prognose.verfuegbar
    ? `heute ${kwh(prognose.heute_kwh)}, Rest ${kwh(prognose.heute_rest_kwh)} · morgen ${kwh(prognose.morgen_kwh)}`
    : (prognose.fehler || "");
  $("prognose-quelle").textContent = prognose.quelle || "";
  $("prognose-quelle").className = "marke " + (prognose.quelle === "eigenes Modell" ? "trocken" : "");
  if (prognose.quelle) $("k-prognose-unter").textContent += " · " + prognose.quelle;
  if (prognose.gemessen_kwh !== undefined && prognose.prognose_bis_jetzt_kwh) {
    const abw = (prognose.gemessen_kwh / prognose.prognose_bis_jetzt_kwh - 1) * 100;
    $("prognose-unter").textContent += ` · bis jetzt gemessen ${kwh(prognose.gemessen_kwh)} gegenüber Prognose `
      + `${kwh(prognose.prognose_bis_jetzt_kwh)} (${abw >= 0 ? "+" : ""}${zahl(abw)} %)`;
  }
  $("tb-prognose").textContent = prognose.verfuegbar ? kwh(prognose.heute_rest_kwh) : "–";
  prognoseZeichnen();
}
function prognoseZeichnen() {
  if (!window.echarts || location.hash !== "#prognose" || !prognose) return;
  prognoseDiagramm = prognoseDiagramm || echarts.init($("prognose-diagramm"));
  diagramme[1] = prognoseDiagramm;
  const a = achsen();
  // Wh der Stunde (Zeitstempel = Stundenende) als mittlere Leistung in der Stundenmitte
  const daten = (prognose.stunden || []).map(s => [new Date(s.zeit).getTime() - 1800e3, s.wh]);
  const gemessen = (prognose.gemessen || []).map(s => [new Date(s.zeit).getTime() - 1800e3, s.wh]);
  prognoseDiagramm.setOption({
    animation: false, grid: {left: 60, right: 16, top: 16, bottom: 30},
    tooltip: a.tooltip, xAxis: a.x, yAxis: a.y,
    legend: {top: 0, textStyle: {color: a.text}},
    series: [{name: "PV gemessen (heute)", type: "bar", barWidth: "35%", barGap: "0%", data: gemessen,
              color: css("--einspeisung")},
             {name: prognose.quelle || "PV-Prognose", type: "bar", barWidth: "35%", data: daten, color: css("--solar"),
              markLine: {symbol: "none", silent: true, label: {formatter: "jetzt", color: a.text},
                         lineStyle: {color: css("--text-2"), type: "dashed"}, data: [{xAxis: Date.now()}]}},
             ...(prognose.vergleich ? [{name: "Vergleich: Home Assistant", type: "line", step: "middle",
               showSymbol: false, color: css("--text-3"), lineStyle: {width: 1.5, type: "dashed"},
               data: (prognose.vergleich.stunden || []).map(s => [new Date(s.zeit).getTime() - 1800e3, s.wh])}] : [])],
  }, true);
}

// ── PV-Anlage: Sauberkeit und Modell ──────────────────────────────────────────
let pvStatus = null, sauberDiagramm = null;
async function pvLaden() {
  try { pvStatus = await holen("api/pvmodell"); } catch (e) { return; }
  const p = pvStatus;
  const prozent = v => v === null || v === undefined ? "–" : zahl(v * 100) + "<small>%</small>";
  $("pv-sauberkeit").innerHTML = prozent(p.sauberkeit);
  $("pv-sauberkeit-unter").textContent = p.sauberkeit_stand
    ? `Stand ${new Date(p.sauberkeit_stand).toLocaleDateString("de-DE")} · Mittel ${zahl((p.sauberkeit_mittel || 1) * 100)} %` : (p.zustand || "");
  $("pv-sauberkeit-box").style.setProperty("--c", p.reinigung_empfohlen ? "var(--warnung)" : "var(--ok)");
  $("pv-verlust").innerHTML = p.verlust_prozent === null || p.verlust_prozent === undefined ? "–" : zahl(p.verlust_prozent) + "<small>%</small>";
  $("pv-verlust-unter").textContent = p.gereinigt_am
    ? `gereinigt am ${new Date(p.gereinigt_am).toLocaleDateString("de-DE")}` + (p.zuschlag > 1.001 ? ` · Prognose +${zahl((p.zuschlag - 1) * 100)} %` : "")
    : "gegenüber den saubersten Wochen";
  $("pv-modell").innerHTML = p.training_laeuft ? "Training läuft …"
    : p.trainiert_am ? '<span class="ok">trainiert</span>' : esc(p.zustand || "–");
  const k = p.kennzahlen || {};
  $("pv-modell-kennzahlen").textContent = p.trainiert_am
    ? `${new Date(p.trainiert_am).toLocaleDateString("de-DE")} · ${k.tage || "?"} Tage · ${k.felder || "?"} Felder` + (p.fehler ? " · " + p.fehler : "")
    : (p.fehler || "");
  $("pv-hinweis").textContent = p.reinigung_empfohlen
    ? "Die Anlage ist deutlich schmutziger als üblich – eine Reinigung lohnt sich."
    : "Sauberkeit: 100 % = so sauber wie die saubersten Wochen der Historie. Nach einer Reinigung den Knopf drücken.";
  $("pv-hinweis").className = p.reinigung_empfohlen ? "hinweis warnung" : "hinweis";
  sauberkeitZeichnen();
}
function sauberkeitZeichnen() {
  if (!window.echarts || location.hash !== "#prognose" || !pvStatus || !pvStatus.sauberkeit_wochen) return;
  sauberDiagramm = sauberDiagramm || echarts.init($("sauberkeit-diagramm"));
  diagramme[2] = sauberDiagramm;
  const a = achsen();
  const daten = Object.entries(pvStatus.sauberkeit_wochen).map(([w, v]) => [new Date(w).getTime(), Math.round(v * 100)]);
  sauberDiagramm.setOption({
    animation: false, grid: {left: 50, right: 16, top: 16, bottom: 30},
    tooltip: {...a.tooltip, valueFormatter: x => x + " %"}, xAxis: a.x,
    yAxis: {...a.y, min: 40, max: 110, axisLabel: {...a.y.axisLabel, formatter: v => v + " %"}},
    series: [{name: "Sauberkeit", type: "line", data: daten, showSymbol: true, symbolSize: 4, color: css("--primary"),
              markLine: {symbol: "none", silent: true, lineStyle: {color: css("--text-3"), type: "dashed"},
                         label: {formatter: "Mittel", color: a.text},
                         data: [{yAxis: Math.round((pvStatus.sauberkeit_mittel || 1) * 100)}]}}],
  }, true);
}
$("gereinigt").onclick = async () => {
  if (!confirm("Anlage heute gereinigt? Die Prognose wird dann angehoben.")) return;
  const r = await fetch("api/pvmodell/gereinigt", {method: "POST"});
  const j = await r.json();
  if (!j.ok) alert(j.fehler.join("; "));
  pvLaden(); prognoseLaden();
};
window.addEventListener("resize", () => diagramme.forEach(d => d && d.resize()));

// ── Bilanz, Ladevorgänge, Ereignisse ────────────────────────────────────────
async function bilanz() {
  try {
    const b = await holen("api/bilanz");
    if (!b.zaehler) return;
    const heute = new Date().toLocaleDateString("sv-SE");   // YYYY-MM-DD lokal
    const t = (b.tage || []).find(x => x.datum === heute) || {pv: 0, akku: 0, netz: 0, ohne: 0, eto: 0};
    $("h-pv").innerHTML = kwhHtml(t.pv);
    $("h-akku").innerHTML = kwhHtml(t.akku);
    $("h-netz").innerHTML = kwhHtml(t.netz);
    $("h-pv-anteil").textContent = t.eto > 0.01 ? `PV-Anteil ${zahl(t.pv / t.eto * 100)} %` : "";
    $("h-ohne").textContent = t.ohne > 0 ? `davon ohne Aufteilung ${kwh(t.ohne)}` : "";
    const l = b.ladung;
    laufendeLadung = l;
    $("tb-auto").textContent = kwh(t.eto);
    $("tb-pv").textContent = kwh(t.pv);
    $("tb-akku").textContent = kwh(t.akku);
    $("tb-netz").textContent = kwh(t.netz);
    $("tb-anteil").textContent = t.eto > 0.01 ? zahl((t.pv + t.akku) / t.eto * 100) + " %" : "–";
    $("tb-anteil").title = "PV + Hausakku (wie im EV Tracker)";
    $("h-ladung").innerHTML = l ? kwhHtml(l.eto) : "–";
    $("h-ladung-unter").textContent = l ? `seit ${zeit(l.start)} · PV ${kwh(l.pv)}` : "keine";
    const z = b.zaehler;
    $("zaehler").innerHTML = `PV ${kwh(z.pv)} · Akku ${kwh(z.akku)} · Netz ${kwh(z.netz)} · ohne Aufteilung ${kwh(z.ohne)} · unsicher ${kwh(z.unsicher)}`;
    $("tage").innerHTML = b.tage.map(t => {
      const abw = t.eto > 0.05 ? (t.trapez - t.eto) / t.eto * 100 : null;
      const kl = abw === null ? "" : Math.abs(abw) > 5 ? "schlecht" : "ok";
      return `<tr><td>${esc(t.datum)}</td><td class="zahl">${kwh(t.pv)}</td><td class="zahl">${kwh(t.akku)}</td>
        <td class="zahl">${kwh(t.netz)}</td><td class="zahl">${kwh(t.ohne)}</td><td class="zahl">${kwh(t.eto)}</td>
        <td class="zahl">${kwh(t.trapez)}</td><td class="zahl ${kl}">${abw === null ? "–" : zahl(abw, 1) + " %"}</td></tr>`;
    }).join("") || '<tr><td colspan="8" class="klein">noch keine Daten</td></tr>';
    $("vorgaenge").innerHTML = b.vorgaenge.map(v => {
      const summe = v.eto || 0;
      const balken = summe > 0 ? `<div class="balken" style="width:120px">
        <span style="width:${v.pv / summe * 100}%;background:var(--solar)"></span>
        <span style="width:${v.akku / summe * 100}%;background:var(--akku)"></span>
        <span style="width:${v.netz / summe * 100}%;background:var(--netz)"></span></div>` : "";
      return `<tr><td>${zeit(v.start)}</td><td>${zeit(v.ende)}</td><td class="zahl">${kwh(v.pv)}</td>
        <td class="zahl">${kwh(v.akku)}</td><td class="zahl">${kwh(v.netz)}</td><td class="zahl">${kwh(v.eto)}</td>
        <td>${summe > 0 ? zahl(v.pv / summe * 100) + " %" : "–"}${balken}</td><td class="klein">${esc(v.grund || "")}</td>
        <td class="klein">${trackerZelle(v)}</td></tr>`;
    }).join("") || '<tr><td colspan="9" class="klein">noch keine</td></tr>';
  } catch (e) {}
}
function trackerZelle(v) {
  const g = v.gesendet;
  if (!v.ende) return "–";
  if (!g) return '<span class="warnung">offen</span>';
  if (/^\d{4}-/.test(g)) return '<span class="ok">✓ ' + esc(zeit(g)) + "</span>";
  return `<span class="${g.startsWith("abgelehnt") ? "schlecht" : "klein"}">${esc(g)}</span>`;
}
function trackerZeigen(t) {
  const el = $("tracker-status"), knopf = $("tracker-senden");
  $("tracker-pruefen").hidden = !t || !t.aktiv;
  if (!t || !t.aktiv) { el.textContent = "EV Tracker: nicht eingerichtet"; knopf.hidden = true; return; }
  el.className = t.fehler ? "schlecht" : "klein";
  el.textContent = "EV Tracker: " + (t.fehler || (t.offen ? `${t.offen} offen` : "alles übergeben"));
  knopf.hidden = !t.offen;
}
$("tracker-pruefen").onclick = async () => {
  const el = $("tracker-test");
  el.hidden = false; el.className = "klein"; el.textContent = "teste …";
  try {
    const j = await (await fetch("api/tracker/pruefen", {method: "POST"})).json();
    el.className = j.ok ? "ok" : "schlecht";
    el.textContent = (j.ok ? "✓ " : "✗ ") + j.text;
  } catch (e) { el.className = "schlecht"; el.textContent = "✗ Add-on nicht erreichbar"; }
  status();
};
$("tracker-senden").onclick = async () => {
  const r = await fetch("api/tracker/senden", {method: "POST"});
  const j = await r.json();
  if (j.tracker) trackerZeigen(j.tracker);
  bilanz();
};

async function ereignisse() {
  try {
    const e = await holen("api/ereignisse?anzahl=60");
    $("ereignisse").innerHTML = e.ereignisse.map(x =>
      `<tr><td class="klein">${zeit(x.zeit)}</td><td class="${x.ebene === "warnung" ? "warnung" : "klein"}">${esc(x.ebene)}</td>
       <td class="klein">${esc(x.quelle)}</td><td>${esc(x.text)}</td></tr>`).join("");
    const p = await holen("api/protokoll?zeilen=120");
    const el = $("protokoll");
    el.textContent = p.zeilen.join("\n");
    el.scrollTop = el.scrollHeight;
  } catch (err) {}
}

// ── Takt ────────────────────────────────────────────────────────────────────
function laden() {
  const s = location.hash || "#live";
  if (s === "#live") { regelung(); bilanz(); heuteLaden(); prognoseLaden(); }
  if (s === "#laden" || s === "#einstellungen") { regelung(); bilanz(); prognoseLaden(); }
  if (s === "#bilanz") { verlauf(); bilanz(); }
  if (s === "#prognose") { prognoseLaden(); pvLaden(); }
  if (s === "#diagnose") ereignisse();
}
const auf = (...seiten) => seiten.includes(location.hash || "#live");
flussAufbauen();
seiteZeigen();
status();
setInterval(status, 2000);
setInterval(() => { if (auf("#live", "#laden")) regelung(); }, 2000);
setInterval(() => { if (auf("#bilanz")) verlauf(); }, 5000);
setInterval(() => { if (auf("#live", "#laden", "#bilanz")) bilanz(); }, 5000);
setInterval(() => { if (auf("#live")) heuteLaden(); }, 60000);
setInterval(() => { if (auf("#diagnose")) ereignisse(); }, 10000);
setInterval(prognoseLaden, 300000);
setInterval(() => { if (auf("#prognose")) pvLaden(); }, 60000);
uhrStellen();
setInterval(uhrStellen, 10000);
