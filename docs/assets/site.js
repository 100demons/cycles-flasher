/* model27 (from Modded-Cycles) — shared page behaviour: language, version, the Model:Cycles drawings.
 * Each part runs only if its elements are on the page.
 * The flasher handles its own language switch (app.js); here it only gets the version. */
(function () {
"use strict";

const root = document.documentElement;
const page = document.body.getAttribute("data-page") || "";
const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
const D = window.MCDevice;
const reduced = D ? D.reduced() : false;

// ---------------------------------------------------------------------------
// Language (same storage key as the flasher)
// ---------------------------------------------------------------------------
const lang = () => (root.lang === "fr" ? "fr" : "en");

function setLang(l) {
  root.lang = l === "fr" ? "fr" : "en";
  try { localStorage.setItem("mc-lang", root.lang); } catch (e) { /* private mode */ }
  $$(".lang button[data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === root.lang)));
  renderRelease();
}

if (page !== "flasher") {
  $$(".lang button[data-lang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
  setLang(lang());
}

// ---------------------------------------------------------------------------
// Theme: follows the system until the moon/sun button is used, then remembers the choice
// (all pages, flasher included)
// ---------------------------------------------------------------------------
const darkMQ = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
const theme = () => root.getAttribute("data-theme") || (darkMQ && darkMQ.matches ? "dark" : "light");
function paintTheme() {
  const fr = root.lang === "fr", dark = theme() === "dark";
  $$(".theme-btn").forEach((b) => {
    b.setAttribute("aria-label", dark ? (fr ? "Mode clair" : "Light mode") : (fr ? "Mode sombre" : "Dark mode"));
    b.title = b.getAttribute("aria-label");
  });
}
$$(".theme-btn").forEach((b) => b.addEventListener("click", () => {
  const next = theme() === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", next);
  try { localStorage.setItem("mc-theme", next); } catch (e) { /* private mode */ }
  paintTheme();
}));
if (darkMQ && darkMQ.addEventListener) darkMQ.addEventListener("change", paintTheme);
new MutationObserver(paintTheme).observe(root, { attributes: true, attributeFilter: ["lang"] });
paintTheme();

// ---------------------------------------------------------------------------
// Version (assets/release.js)
// ---------------------------------------------------------------------------
function fmtDate(iso) {
  try {
    return new Date(iso + "T12:00:00Z").toLocaleDateString(lang() === "fr" ? "fr-FR" : "en-GB",
      { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  } catch (e) { return iso; }
}

function renderRelease() {
  const rels = window.MC_RELEASES || [];
  const rel = rels[0];
  if (!rel) return;
  $$("[data-rel=version]").forEach((el) => { el.textContent = rel.version; });
  $$("[data-rel=date]").forEach((el) => { el.textContent = fmtDate(rel.date); el.setAttribute("datetime", rel.date); });
  $$("[data-rel=changes]").forEach((el) => {
    el.innerHTML = "";
    if (!rel.changes.length) {
      const p = document.createElement("p");
      p.textContent = lang() === "fr" ? "Première version : rien à comparer pour l'instant."
        : "First release: nothing to compare with yet.";
      el.appendChild(p);
      return;
    }
    const p = document.createElement("p");
    p.textContent = (lang() === "fr" ? "Changements depuis la " : "Changes since ") + (rels[1] ? rels[1].version : "");
    const ul = document.createElement("ul");
    rel.changes.forEach((c) => {
      const li = document.createElement("li");
      li.textContent = c[lang()] || c.en;
      ul.appendChild(li);
    });
    el.append(p, ul);
  });
}
renderRelease();

// ---------------------------------------------------------------------------
// Model:Cycles drawings. data-device="seq" plays a pattern; data-lit="func,track" lights controls;
// data-lcd sets the screen ("logo", "menu", "~long name", "LINE 1/>LINE 2");
// data-scenes="track | track,func @MUTE/>LOCKED" steps through controls and screens.
// ---------------------------------------------------------------------------
const split = (s) => (s || "").split(",").map((x) => x.trim()).filter(Boolean);
const devices = $$("[data-device]").map((host) => {
  if (!D) return null;
  const dev = D.render(host, { seq: host.dataset.device === "seq", lit: split(host.dataset.lit), lcd: host.dataset.lcd });
  if (host.dataset.scenes) dev.scenes(host.dataset.scenes, +host.dataset.ms || 1100);
  return dev;
});

// home: hovering a mod lights the controls it touches and changes the screen
const bench = devices[0];
$$("[data-hl]").forEach((a) => {
  const on = () => { if (bench) { bench.light(split(a.dataset.hl)); bench.show(a.dataset.lcd); } };
  const off = () => { if (bench) { bench.light([]); bench.show("logo"); } };
  a.addEventListener("mouseenter", on);
  a.addEventListener("focus", on);
  a.addEventListener("mouseleave", off);
  a.addEventListener("blur", off);
});
})();
