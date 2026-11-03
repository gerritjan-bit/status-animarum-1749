/* Status Animarum Münster 1749/50 — zoeken in de browser.
   Alle gegevens staan als vaste bestanden op de site; er is geen server.
   window.SA (per pagina gezet) bevat taal, teksten en adressen. */
(function () {
  "use strict";
  const SA = window.SA;
  const T = SA.ui;

  /* ---------- klanknormalisatie (zelfde regels als in het notebook) ---------- */
  function norm(w) {
    w = w.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
    w = w.replace(/[^a-zß]/g, "").replace(/ß/g, "s");
    const paren = [["ck", "k"], ["c", "k"], ["th", "t"], ["ph", "f"], ["y", "i"], ["j", "i"],
                   ["v", "f"], ["w", "f"], ["z", "s"]];
    for (const [a, b] of paren) w = w.split(a).join(b);
    w = w.replace(/([aeiou])h(?![aeiou])/g, "$1");
    w = w.replace(/(.)\1+/g, "$1");
    w = w.replace(/(ink|ing|ik)$/, "ink");
    return w;
  }
  /* overeenkomst 0–100: 2·(langste gemeenschappelijke deelreeks)/(lengte a + lengte b) */
  function ratio(a, b) {
    const la = a.length, lb = b.length;
    if (!la || !lb) return 0;
    let vorig = new Uint8Array(lb + 1), rij = new Uint8Array(lb + 1);
    for (let i = 1; i <= la; i++) {
      const ca = a.charCodeAt(i - 1);
      for (let j = 1; j <= lb; j++) {
        rij[j] = ca === b.charCodeAt(j - 1) ? vorig[j - 1] + 1 : Math.max(vorig[j], rij[j - 1]);
      }
      [vorig, rij] = [rij, vorig];
    }
    return 200 * vorig[lb] / (la + lb);
  }

  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

  /* ---------- weergave (zelfde opmaak als de parochiepagina's) ---------- */
  function vertaalReden(r) {
    if (!r) return "";
    const R = T.reden;
    let m;
    if (r === "witregel") return R.witregel;
    if (r === "korte regel eindigend op een leeftijd") return R.kort;
    if (r === "begin van de pagina") return R.begin;
    if (r === "volgende kolom op de pagina") return R.kolom;
    if ((m = r.match(/^volgende regel begint met '(.*)'$/))) return R.kopwoord.replace("{w}", m[1]);
    if ((m = r.match(/^rol '(.*)' opent een huishouden$/))) return R.rol.replace("{w}", m[1]);
    return r;
  }
  function tekstHTML(tekst, corr, termen) {
    const cmap = {};
    for (const [pos, ocr, laag] of corr || []) cmap[pos] = [ocr, laag];
    return tekst.split(" ").map((tok, i) => {
      let e = esc(tok);
      if (termen && termen.length && tok.match(/\p{L}+/gu)?.some(w => termen.some(t => t(w)))) e = "<mark>" + e + "</mark>";
      if (cmap[i]) e = `<u title="${esc(T.ocrLas + ": " + cmap[i][0] + " (" + (T.laag[cmap[i][1]] || cmap[i][1]) + ")")}">${e}</u>`;
      return e;
    }).join(" ");
  }
  function hhHTML(h, boek, termen) {
    const [sleutel, pg, tekst, ocr, corr, pers, reden] = h;
    const label = boek.labels[pg] || ("pg " + pg);
    const rijen = (pers || []).map(([rel, naam, lft, geb]) =>
      `<tr><td>${esc(T.rel[rel] || rel)}</td><td>${esc(naam || "–")}</td><td class="getal">${lft == null ? "" : lft}</td><td class="getal">${geb == null ? "" : geb}</td></tr>`).join("");
    return `<article class="hh" id="${esc(sleutel)}" data-sleutel="${esc(sleutel)}">
<div class="hh-kop"><span class="plaats"><a href="${SA.basis}${SA.taal}/p/${esc(boek.id)}.html#${esc(sleutel)}">${esc(boek.plaats)}</a></span><a href="${esc(boek.url)}?pg=${pg}" target="_blank" rel="noopener">${esc(T.scan)} ${esc(label)}</a><span>${esc(sleutel)}</span></div>
<p class="hh-tekst">${tekstHTML(tekst, corr, termen)}</p>${h[7] ? `<div class="voorstel"><span class="label">${esc(T.voorstel)}</span>${tekstHTML(h[7], [], termen)}</div>` : ""}
<details><summary>${esc(T.details)}</summary>
${detailsHTML(h)}
</details>
<p class="verbeter"><a class="verbeterlink" href="${esc(formLink(sleutel, null))}" target="_blank" rel="noopener">${esc(T.verbeter)}</a></p>
</article>`;
  }
  function formLink(sleutel, tekst) {
    let u = SA.form.url + "?usp=pp_url&" + SA.form.sleutel + "=" + encodeURIComponent(sleutel);
    if (tekst) u += "&" + SA.form.tekst + "=" + encodeURIComponent(tekst);
    return u;
  }

  /* ---------- verbeteringen van gebruikers (gepubliceerde Google Sheet) ---------- */
  function leesCSV(t) {
    const rijen = []; let rij = [], veld = "", q = false;
    for (let i = 0; i < t.length; i++) {
      const c = t[i];
      if (q) {
        if (c === '"' && t[i + 1] === '"') { veld += '"'; i++; }
        else if (c === '"') q = false; else veld += c;
      } else if (c === '"') q = true;
      else if (c === ",") { rij.push(veld); veld = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && t[i + 1] === "\n") i++;
        rij.push(veld); rijen.push(rij); rij = []; veld = "";
      } else veld += c;
    }
    if (veld || rij.length) { rij.push(veld); rijen.push(rij); }
    return rijen;
  }
  let voorstellen = null;
  async function laadVoorstellen() {
    if (voorstellen) return voorstellen;
    voorstellen = {};
    if (!SA.csv) return voorstellen;
    try {
      const r = await fetch(SA.csv, {cache: "no-store"});
      if (!r.ok) return voorstellen;
      const rijen = leesCSV(await r.text()).slice(1);
      for (const [tijd, sleutel, tekst, soort] of rijen) {
        if (!sleutel || !tekst) continue;
        voorstellen[sleutel.trim()] = {tijd, tekst: tekst.trim(), soort};   // nieuwste wint (onderaan)
      }
    } catch (e) { /* geen verbinding met Google: dan zonder voorstellen */ }
    return voorstellen;
  }
  function toonVoorstellen(wortel) {
    laadVoorstellen().then(v => {
      wortel.querySelectorAll("[data-sleutel]").forEach(el => {
        const s = el.dataset.sleutel, vs = v[s];
        if (!vs) return;
        const huidige = el.querySelector(".hh-tekst").textContent.trim();
        if (vs.tekst === huidige) return;
        let d = el.querySelector(".voorstel");          // al ingebouwd bij het bouwen? dan alleen bijwerken
        if (d && d.textContent.endsWith(vs.tekst)) return;
        if (!d) { d = document.createElement("div"); d.className = "voorstel"; el.querySelector(".hh-tekst").after(d); }
        d.innerHTML = `<span class="label">${esc(T.voorstel)}</span>${esc(vs.tekst)}`;
      });
    });
  }
  /* verbeterlink: de huidige tekst pas bij het klikken meegeven (houdt de pagina's klein) */
  document.addEventListener("click", ev => {
    const a = ev.target.closest(".verbeterlink");
    if (!a) return;
    const el = a.closest("[data-sleutel]");
    a.href = formLink(el.dataset.sleutel, el.querySelector(".hh-tekst").textContent.trim());
  });

  /* ---------- parochiepagina: voorstellen tonen en details pas bij openklappen laden ---------- */
  function detailsHTML(h) {
    const [sleutel, pg, tekst, ocr, corr, pers, reden] = h;
    const rijen = (pers || []).map(([rel, naam, lft, geb]) =>
      `<tr><td>${esc(T.rel[rel] || rel)}</td><td>${esc(naam || "–")}</td><td class="getal">${lft == null ? "" : lft}</td><td class="getal">${geb == null ? "" : geb}</td></tr>`).join("");
    return `<div class="tabel"><table><thead><tr><th>${esc(T.kolRel)}</th><th>${esc(T.kolNaam)}</th><th class="getal">${esc(T.kolLft)}</th><th class="getal">${esc(T.kolGeb)}</th></tr></thead><tbody>${rijen}</tbody></table></div>
<p class="ocr">${esc(T.ocrOrig)}: ${esc(ocr)}</p>
<p class="klein">${esc(T.grens)}: ${esc(vertaalReden(reden))}</p>`;
  }
  if (SA.pagina !== "zoeken") {
    toonVoorstellen(document);
    const main = document.querySelector("main[data-boek]");
    let boekData = null;
    document.addEventListener("toggle", async ev => {
      const d = ev.target;
      if (!(d instanceof HTMLDetailsElement) || !d.open || !d.hasAttribute("data-laad")) return;
      d.removeAttribute("data-laad");
      if (!boekData) boekData = fetch(SA.basis + "data/hh/" + main.dataset.boek + ".json").then(r => r.json());
      const lijst = await boekData;
      const s = d.closest("[data-sleutel]").dataset.sleutel;
      const h = lijst.find(x => x[0] === s);
      if (h) d.insertAdjacentHTML("beforeend", detailsHTML(h));
    }, true);
    return;
  }

  /* ---------- zoekpagina ---------- */
  const $ = id => document.getElementById(id);
  const vak = $("q"), uit = $("uitkomst"), status = $("status");
  let IDX = null, BOEKEN = null, normGroepen = null;
  const boekCache = {};

  async function laadIndex() {
    if (IDX) return;
    status.textContent = T.laden;
    const [i, b] = await Promise.all([
      fetch(SA.basis + "data/index.json").then(r => r.json()),
      fetch(SA.basis + "data/boeken.json").then(r => r.json())]);
    IDX = i; BOEKEN = b;
    // woorden met dezelfde klank samen nemen: één vergelijking per klankvorm
    const g = new Map();
    IDX.w.forEach((w, k) => { const n = norm(w); if (!n) return; if (!g.has(n)) g.set(n, []); g.get(n).push(k); });
    normGroepen = [...g.entries()];
    const sel = $("boek");
    BOEKEN.forEach((bk, k) => { const o = document.createElement("option"); o.value = k; o.textContent = bk.plaats; sel.appendChild(o); });
    status.textContent = "";
  }
  async function laadBoek(k) {
    const id = BOEKEN[k].id;
    if (!boekCache[id]) boekCache[id] = fetch(SA.basis + "data/hh/" + id + ".json").then(r => r.json());
    return boekCache[id];
  }

  function zoekWoorden(term, fuzzy, drempel) {
    // geeft per huishouden de beste score voor deze term
    const best = new Map();
    const voeg = (k, s) => { for (const h of IDX.p[k]) if ((best.get(h) || 0) < s) best.set(h, s); };
    if (fuzzy) {
      const t = norm(term);
      if (!t) return best;
      for (const [n, ks] of normGroepen) {
        if (Math.abs(n.length - t.length) > Math.max(2, t.length * 0.45)) continue;
        const s = ratio(t, n);
        if (s >= drempel) for (const k of ks) voeg(k, s);
      }
    } else {
      const t = term.toLowerCase();
      IDX.w.forEach((w, k) => { if (w.includes(t)) voeg(k, 100); });
    }
    return best;
  }
  function markeerders(termen, fuzzy, drempel) {
    return termen.map(t => fuzzy
      ? (n => w => ratio(n, norm(w)) >= Math.max(drempel, 80))(norm(t))
      : (l => w => w.toLowerCase().includes(l))(t.toLowerCase()));
  }

  let resultaten = [], getoond = 0, laatsteTermen = [];
  async function zoek() {
    await laadIndex();
    const q = vak.value.trim();
    const fuzzy = $("fuzzy").checked;
    const drempel = +$("drempel").value;
    const gv = +$("gebvan").value || 0, gt = +$("gebtot").value || 9999;
    const bk = $("boek").value === "" ? null : +$("boek").value;
    history.replaceState(null, "", "#" + new URLSearchParams({q, m: fuzzy ? "f" : "e", d: drempel, gv: gv || "", gt: gt === 9999 ? "" : gt, b: bk == null ? "" : BOEKEN[bk].id}).toString());
    const termen = q.split(/\s+/).filter(t => t.length >= (fuzzy ? 2 : 3));
    uit.innerHTML = "";
    if (!termen.length) { status.textContent = fuzzy ? T.teKort : T.teKortExact; return; }
    status.textContent = T.bezig;
    await new Promise(r => setTimeout(r, 0));
    // alle termen moeten voorkomen; score = de zwakste term
    let totaal = null;
    for (const t of termen) {
      const m = zoekWoorden(t, fuzzy, drempel);
      if (totaal === null) totaal = m;
      else { const n = new Map(); for (const [h, s] of totaal) if (m.has(h)) n.set(h, Math.min(s, m.get(h))); totaal = n; }
    }
    resultaten = [...totaal.entries()].filter(([h]) => {
      if (bk != null && IDX.h[h][0] !== bk) return false;
      if (gv || gt !== 9999) return (IDX.g[h] || []).some(j => j >= gv && j <= gt);
      return true;
    }).sort((a, b) => b[1] - a[1] || a[0] - b[0]);
    laatsteTermen = markeerders(termen, fuzzy, drempel);
    getoond = 0;
    status.textContent = resultaten.length === 1 ? T.een : T.aantal.replace("{n}", resultaten.length.toLocaleString(SA.taal));
    await toonMeer();
  }
  async function toonMeer() {
    const stuk = resultaten.slice(getoond, getoond + 50);
    getoond += stuk.length;
    const boekNrs = [...new Set(stuk.map(([h]) => IDX.h[h][0]))];
    const data = {};
    await Promise.all(boekNrs.map(async k => { data[k] = await laadBoek(k); }));
    const html = stuk.map(([h]) => { const [k, i] = IDX.h[h]; return hhHTML(data[k][i], BOEKEN[k], laatsteTermen); }).join("");
    const meer = $("meer"); if (meer) meer.remove();
    uit.insertAdjacentHTML("beforeend", html);
    if (getoond < resultaten.length) uit.insertAdjacentHTML("beforeend", `<p class="meer"><button id="meer" type="button">${esc(T.meer)}</button></p>`);
    toonVoorstellen(uit);
  }
  uit.addEventListener("click", e => { if (e.target.id === "meer") toonMeer(); });
  $("zoekform").addEventListener("submit", e => { e.preventDefault(); zoek(); });
  $("drempel").addEventListener("input", () => { $("drempelwaarde").textContent = $("drempel").value; });
  $("fuzzy").addEventListener("change", () => { $("drempelvak").hidden = !$("fuzzy").checked; });

  // zoekopdracht uit de link (#q=…) herstellen, zodat je een zoekopdracht kunt delen
  (async function () {
    const p = new URLSearchParams(location.hash.slice(1));
    if (!p.get("q")) return;
    await laadIndex();
    vak.value = p.get("q");
    if (p.get("m") === "e") { $("exact").checked = true; $("drempelvak").hidden = true; }
    if (p.get("d")) { $("drempel").value = p.get("d"); $("drempelwaarde").textContent = p.get("d"); }
    if (p.get("gv")) $("gebvan").value = p.get("gv");
    if (p.get("gt")) $("gebtot").value = p.get("gt");
    if (p.get("b")) { const k = BOEKEN.findIndex(b => b.id === p.get("b")); if (k >= 0) $("boek").value = k; }
    zoek();
  })();
  vak.addEventListener("focus", laadIndex, {once: true});
})();
