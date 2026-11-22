/* Kerkboeken West-Münsterland 1750–1820 — zoeken in de browser.
   De database (SQLite) staat in stukken op GitHub Pages; de browser leest alleen de delen die nodig zijn
   (sql.js-httpvfs). Namen, spellingsgroepen en aliaskoppelingen staan in namen.json.
   window.KB (per pagina gezet) bevat taal, adressen en teksten. */
(function () {
  "use strict";
  const KB = window.KB, T = KB.ui;
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const fmt = n => Number(n).toLocaleString(KB.taal);

  /* ---------- naamnormalisatie: precies dezelfde regels als in het notebook ---------- */
  const PARTIKELS = /^(ten|ter|te|to|tom|tor|von der|von dem|von|van der|van den|van|vom|zum|zur|op de|op ten|in de|in der)\s+/;
  function naamNorm(s) {
    s = String(s || "").normalize("NFC").toLowerCase().trim();
    s = s.replace(/\(.*?\)|\[.*?\]|[?!]/g, "").replace(PARTIKELS, "");
    for (const [a, b] of [["ä","a"],["ö","o"],["ü","u"],["ú","u"],["ß","s"],["ae","a"],["oe","o"],["ue","u"],
                          ["ij","i"],["y","i"],["ck","k"],["th","t"],["ph","f"],["dt","t"],["gh","g"]]) s = s.split(a).join(b);
    s = s.replace(/[^a-z]/g, "");
    s = s.replace(/^(ten|ter|tom|tor|zum|zur|von|van|vom)(?=[a-z]{4})/, "");
    s = s.replace(/(?<=[aeio])u(?=[aeiou])/g, "v");
    s = s.replace(/(.)\1+/g, "$1");
    for (const [p, r] of [[/(haus|hous|hues|hus|huis|hos|has)$/, "hus"], [/(ink|ing|inc|ingk)$/, "ink"], [/(bek|beke|bech|bik)$/, "bek"],
                          [/(kamp|kampf|camp)$/, "kamp"], [/(hof|hove|hoven)$/, "hof"], [/(man|mans)$/, "man"], [/sche$/, ""],
                          [/(?<=[^aeiou])in$/, ""], [/(?<=..)s$/, ""], [/(?<=..e)n$/, ""]]) s = s.replace(p, r);
    return s;
  }
  function koelner(w) {
    let codes = "";
    for (let i = 0; i < w.length; i++) {
      const c = w[i], v = i ? w[i - 1] : "", n = i + 1 < w.length ? w[i + 1] : "";
      let k = "";
      if ("aeiouj".includes(c)) k = "0";
      else if (c === "h") k = "";
      else if (c === "b") k = "1";
      else if (c === "p") k = n === "h" ? "3" : "1";
      // let op: zoals in Python geldt '' als onderdeel van elke tekenreeks (einde van het woord)
      else if (c === "d" || c === "t") k = "csz".includes(n) ? "8" : "2";
      else if ("fvw".includes(c)) k = "3";
      else if ("gkq".includes(c)) k = "4";
      else if (c === "c") k = i === 0 ? ("ahkloqrux".includes(n) ? "4" : "8") : (("sz".includes(v) || !"ahkoqux".includes(n)) ? "8" : "4");
      else if (c === "x") k = "ckq".includes(v) ? "8" : "48";
      else if (c === "l") k = "5";
      else if (c === "m" || c === "n") k = "6";
      else if (c === "r") k = "7";
      else if (c === "s" || c === "z") k = "8";
      codes += k;
    }
    let out = "";
    for (const ch of codes) if (!out || ch !== out[out.length - 1]) out += ch;
    return out ? out[0] + out.slice(1).split("0").join("") : "";
  }
  /* overeenkomst 0–100, zoals rapidfuzz.fuzz.ratio */
  function ratio(a, b) {
    const la = a.length, lb = b.length;
    if (!la && !lb) return 100;
    if (!la || !lb) return 0;
    let vorig = new Uint16Array(lb + 1), rij = new Uint16Array(lb + 1);
    for (let i = 1; i <= la; i++) {
      const ca = a.charCodeAt(i - 1);
      for (let j = 1; j <= lb; j++) rij[j] = ca === b.charCodeAt(j - 1) ? vorig[j - 1] + 1 : Math.max(vorig[j], rij[j - 1]);
      [vorig, rij] = [rij, vorig];
    }
    return 200 * vorig[lb] / (la + lb);
  }

  /* ---------- voornamen gelijktrekken (Joes = Joan = Johann → johannes) ---------- */
  const VN = {
    johannes: "joes joan joann joannes johann johan johannes jan jo joa jois joh hans johannis joannis",
    henricus: "henricus henrich hendrik hendrich hinrich hindrich henr hen henrick henrik heinrich hendricus henric",
    gerhardus: "gerhardus gerardus gerhard gerard gerd gert gerh gerrit",
    bernardus: "bernardus bernard bernd berend bern bernhard bernh bernardt",
    hermannus: "hermannus herman hermann herm harmen", wilhelmus: "wilhelmus wilhelm willem wilh wilm",
    theodorus: "theodorus theodor diderich dirk derk diderick theod didrich dietrich",
    arnoldus: "arnoldus arnold arend arnd", everhardus: "everhardus everhard evert everd",
    antonius: "antonius anton tonnis thonis antoni", josephus: "josephus joseph josep jos",
    fridericus: "fridericus friderich friedrich frid fridrich fred", georgius: "georgius georg jurgen jorgen jorg",
    christophorus: "christophorus christoph christoffer stoffer", engelbertus: "engelbertus engelbert engelb",
    conradus: "conradus conrad coert cord curt", jacobus: "jacobus jacob jakob", petrus: "petrus peter peer",
    casparus: "casparus caspar jaspar jasper", albertus: "albertus albert albrecht", lambertus: "lambertus lambert",
    rudolphus: "rudolphus rudolph rudolf roelof roloff", godefridus: "godefridus gottfried godfried",
    wolterus: "wolterus wolter walter", matthias: "matthias mathias matthis thijs",
    anna: "anna anne ann", maria: "maria marie mar mria ma",
    catharina: "catharina catharin catrina trine trina katharina cath catha cathar",
    margaretha: "margaretha margareta margarethe grete greta margreta marg margr margareth",
    gertrudis: "gertrudis gertrud gertraud geertruid gerdrut trude gertr",
    elisabetha: "elisabetha elisabeth elsche else elisabet lisbeth elis elsabe",
    adelheidis: "adelheidis adelheid aleid alheid aleida alida aleke adelh",
    christina: "christina christine stine stina chr christ", johanna: "johanna joanna jenne jenna janna",
    henrica: "henrica hendrina henrika hendrika henriette", gesina: "gesina gese gesche gesken",
    clara: "clara clare", helena: "helena lena helene", agnes: "agnes neesken",
    engela: "engela engel engele", sophia: "sophia sophie fieke", theresia: "theresia therese",
    wilhelmina: "wilhelmina mina wilmina", bernardina: "bernardina berendina dina", magdalena: "magdalena magdalene lena"
  };
  function _vn(t) {
    t = String(t).normalize("NFKC").toLowerCase().replace(/е/g, "e").replace(/а/g, "a").replace(/о/g, "o");
    for (const [a, b] of [["ä","a"],["ö","o"],["ü","u"],["ß","s"],["ph","f"],["th","t"],["dt","d"],["y","i"],["ck","k"],["c","k"]]) t = t.split(a).join(b);
    return t.replace(/[^a-z]/g, "");
  }
  const VN_MAP = new Map();
  for (const [k, vs] of Object.entries(VN)) for (const v of vs.split(" ")) VN_MAP.set(_vn(v), k);
  const VN_KEYS = [...VN_MAP.keys()], VN_LANG = [...VN_KEYS].sort((a, b) => b.length - a.length);
  const vnCache = new Map();
  function vnToken(t) {
    t = _vn(t);
    if (t.length < 2) return "";
    if (vnCache.has(t)) return vnCache.get(t);
    let r = VN_MAP.get(t);
    if (!r && t.length >= 4) { const k = VN_LANG.find(k => k.startsWith(t)); if (k) r = VN_MAP.get(k); }
    if (!r) { let best = -1, bk = null; for (const k of VN_KEYS) { const s = ratio(t, k); if (s > best) { best = s; bk = k; } } r = best >= 85 ? VN_MAP.get(bk) : t; }
    vnCache.set(t, r); return r;
  }
  const vnNorm = s => String(s || "").split(/[\s.,;:\/-]+/).map(vnToken).filter(Boolean).join(" ");

  /* ---------- gegevens laden ---------- */
  let NAMEN = null, META = null, DB = null, LEDEN = null, KOP = null, BOEK = null, VNSET = null;
  async function laad() {
    if (NAMEN) return;
    status(T.laden);
    const [n, m] = await Promise.all([fetch(KB.data + "namen.json", {cache: "no-cache"}).then(r => r.json()), fetch(KB.data + "meta.json", {cache: "no-cache"}).then(r => r.json())]);
    NAMEN = n; META = m;
    LEDEN = NAMEN.b.map(() => []);
    for (const [nm, b, nr, sl, a] of NAMEN.n) LEDEN[b].push([nm, a]);
    for (const l of LEDEN) l.sort((x, y) => y[1] - x[1]);
    KOP = new Map();
    for (const [a, b, n, w] of NAMEN.k) {
      if (!KOP.has(a)) KOP.set(a, []); if (!KOP.has(b)) KOP.set(b, []);
      KOP.get(a).push([b, n, w]); KOP.get(b).push([a, n, w]);
    }
    BOEK = new Map(META.boeken.map(([id, p, code, type, url]) => [id, {p, code, type, url}]));
    VNSET = NAMEN.vn.map(v => new Set(v.split(" ")));
    for (const sel of document.querySelectorAll("select[data-parochies]")) {
      META.parochies.forEach((p, i) => { const o = document.createElement("option"); o.value = i; o.textContent = p; sel.appendChild(o); });
    }
    status("");
  }
  async function db() {
    if (DB) return DB;
    await laad();
    status(T.verbinden);
    const abs = u => new URL(u, location.href).href;   // de worker zoekt relatieve adressen vanuit zijn eigen map
    const w = await window.createDbWorker([{from: "jsonconfig", configUrl: abs(KB.data + "db/config.json?v=" + META.gemaakt + "-" + META.vermeldingen)}],
      abs(KB.basis + "assets/lib/sqlite.worker.js"), abs(KB.basis + "assets/lib/sql-wasm.wasm"));
    DB = w.db; return DB;
  }
  async function sql(q, params) {
    const d = await db();
    const r = await d.exec(q, params || []);
    if (!r.length) return [];
    return r[0].values;
  }
  function inLijst(ids) { return ids.map(Number).filter(Number.isFinite).join(","); }

  /* ---------- welke basisvormen horen bij een zoeknaam ---------- */
  function basisvormen(term, drempel, exact) {
    const uit = new Map();
    if (exact) {
      const t = term.trim().toLowerCase();
      for (const [nm, b] of NAMEN.n) if (nm.toLowerCase() === t) uit.set(b, 100);
      return uit;
    }
    const t = naamNorm(term), k = koelner(t);
    if (!t) return uit;
    for (const [nm, b, nr, sl] of NAMEN.n) {
      const sc = nr === t ? 100 : (sl === k ? ratio(t, nr) : ratio(t, nr) - 10);
      if (sc >= drempel && sc > (uit.get(b) || 0)) uit.set(b, sc);
    }
    return uit;
  }
  const basisAantal = b => LEDEN[b].reduce((s, x) => s + x[1], 0);

  /* ---------- zoekformulier ---------- */
  const MAX_NAMEN = 3;
  const keuzes = {};        // per regel: {uit: Set(basis_id), bij: Set(basis_id)} — handmatig aan/uit gezet
  function regelHTML(i) {
    const rollen = META ? META.rollen : [];
    return `<div class="kb-regel" data-i="${i}">
<input type="search" class="kb-naam" placeholder="${esc(T.achternaam)}" aria-label="${esc(T.achternaam)}" autocomplete="off">
<input type="search" class="kb-vn" placeholder="${esc(T.voornaam)}" aria-label="${esc(T.voornaam)}" autocomplete="off">
<select class="kb-rol" aria-label="${esc(T.rol)}"><option value="">${esc(T.elkeRol)}</option>${rollen.map((r, k) => `<option value="${k}">${esc(T.rollen[r] || r)}</option>`).join("")}</select>
${i ? `<button type="button" class="kb-weg" aria-label="${esc(T.weg)}" title="${esc(T.weg)}">×</button>` : ""}</div>`;
  }
  function regels() {
    return [...document.querySelectorAll("#kb-regels .kb-regel")].map(el => ({
      i: +el.dataset.i, naam: el.querySelector(".kb-naam").value.trim(), vn: el.querySelector(".kb-vn").value.trim(),
      rol: el.querySelector(".kb-rol").value === "" ? null : +el.querySelector(".kb-rol").value
    })).filter(r => r.naam);
  }
  function voegRegelToe(waarden) {
    const n = document.querySelectorAll("#kb-regels .kb-regel").length;
    if (n >= MAX_NAMEN) return;
    const vrij = [0, 1, 2].find(i => !document.querySelector(`#kb-regels .kb-regel[data-i="${i}"]`));
    $("kb-regels").insertAdjacentHTML("beforeend", regelHTML(vrij));
    const el = document.querySelector(`#kb-regels .kb-regel[data-i="${vrij}"]`);
    if (waarden) { el.querySelector(".kb-naam").value = waarden.naam || ""; el.querySelector(".kb-vn").value = waarden.vn || ""; if (waarden.rol != null) el.querySelector(".kb-rol").value = waarden.rol; }
    werkSamenBij();
  }
  function werkSamenBij() {
    const n = document.querySelectorAll("#kb-regels .kb-regel").length;
    $("kb-samenvak").hidden = n < 2;
    $("kb-plus").hidden = n >= MAX_NAMEN;
  }
  const status = t => { const el = $("kb-status") || $("gz-status"); if (el) el.textContent = t; };
  const opties = () => ({
    exact: $("kb-exact").checked, drempel: +$("kb-drempel").value, alias: $("kb-alias").checked,
    par: $("kb-par").value === "" ? null : +$("kb-par").value, soort: $("kb-soort").value === "" ? null : +$("kb-soort").value,
    van: +$("kb-van").value || null, tot: +$("kb-tot").value || null, samen: $("kb-samen").value
  });

  /* ---------- zoeken ---------- */
  let RES = [], getoond = 0, TERMEN = [], ZOEKNAAM = "";
  async function zoek() {
    await laad();
    const rs = regels(), o = opties();
    $("kb-uitkomst").innerHTML = ""; $("kb-namen").innerHTML = ""; $("kb-csv").hidden = true;
    if (!rs.length) { status(T.geenNaam); return; }
    bewaarInLink(rs, o);
    // 1. per zoeknaam de basisvormen (+ aliassen) bepalen
    TERMEN = rs.map(r => {
      const auto = basisvormen(r.naam, o.drempel, o.exact);
      const k = keuzes[r.i] || (keuzes[r.i] = {uit: new Set(), bij: new Set(), naam: r.naam});
      if (k.naam !== r.naam) { k.uit.clear(); k.bij.clear(); k.naam = r.naam; }
      const basis = new Set([...auto.keys(), ...k.bij].filter(b => !k.uit.has(b)));
      const alias = new Set();
      if (o.alias) for (const b of basis) for (const [a] of (KOP.get(b) || [])) if (!basis.has(a) && !k.uit.has(a)) alias.add(a);
      const bijna = o.exact ? new Map() : basisvormen(r.naam, o.drempel - 15, false);
      for (const b of [...basis, ...alias]) bijna.delete(b);
      return {...r, auto, basis, alias, bijna, k, vnSet: r.vn ? new Set(vnNorm(r.vn).split(" ").filter(Boolean)) : null};
    });
    toonNamen(o);
    const ids = new Set(); for (const t of TERMEN) { for (const b of t.basis) ids.add(b); for (const b of t.alias) ids.add(b); }
    if (!ids.size) { status(T.niets); return; }
    status(T.bezig);
    // 2. alle vermeldingen van die basisvormen ophalen (staan achter elkaar in de database)
    let w = `basis_id in (${inLijst([...ids])})`;
    const p = [];
    if (o.van) { w += " and jaar >= ?"; p.push(o.van); }
    if (o.tot) { w += " and jaar <= ?"; p.push(o.tot); }
    if (o.soort != null) { w += " and soort = ?"; p.push(o.soort); }
    if (o.par != null) { const bk = META.boeken.filter(b => b[1] === o.par).map(b => b[0]); w += ` and boek_id in (${inLijst(bk)})`; }
    const rijen = await sql(`select basis_id, akte_id, i, via, rol, vnn, boek_id, pg, jaar, soort from zoek where ${w}`, p);
    // 3. per zoeknaam markeren (rol en voornaam filteren in de browser)
    const treffers = TERMEN.map(() => new Map());   // per term: akte_id -> [persoon-index, via-alias]
    const aktes = new Map();
    for (const [b, a, i, via, rol, vnn, bk, pg, jaar, soort] of rijen) {
      aktes.set(a, {bk, pg, jaar, soort});
      TERMEN.forEach((t, ti) => {
        const viaAlias = t.alias.has(b);
        if (!t.basis.has(b) && !viaAlias) return;
        if (t.rol != null && rol !== t.rol) return;
        if (t.vnSet && t.vnSet.size) { const s = vnn == null ? null : VNSET[vnn]; if (!s || ![...t.vnSet].every(x => s.has(x))) return; }
        const m = treffers[ti]; if (!m.has(a)) m.set(a, []); m.get(a).push([i, viaAlias]);
      });
    }
    // 4. samen in akte / scan / jaar
    const sleutel = a => { const x = aktes.get(a); return o.samen === "pagina" ? x.bk + "|" + x.pg : o.samen === "jaar" ? BOEK.get(x.bk).p + "|" + x.jaar : String(a); };
    let gekozen;
    if (TERMEN.length > 1) {
      const per = treffers.map(m => { const s = new Set(); for (const a of m.keys()) s.add(sleutel(a)); return s; });
      const goed = new Set([...per[0]].filter(k => per.every(s => s.has(k))));
      gekozen = new Set();
      treffers.forEach(m => { for (const a of m.keys()) if (goed.has(sleutel(a))) gekozen.add(a); });
    } else gekozen = new Set(treffers[0].keys());
    RES = [...gekozen].map(a => ({a, ...aktes.get(a), groep: sleutel(a)}));
    RES.sort((x, y) => BOEK.get(x.bk).p - BOEK.get(y.bk).p || (x.jaar || 9999) - (y.jaar || 9999) || x.a - y.a);
    RES.treffers = treffers;
    getoond = 0;
    const nGroep = new Set(RES.map(r => r.groep)).size;
    status(!RES.length ? T.niets : (TERMEN.length > 1 ? T.aantalSamen.replace("{n}", fmt(nGroep)).replace("{a}", fmt(RES.length)) : (RES.length === 1 ? T.een : T.aantal.replace("{n}", fmt(RES.length)))));
    ZOEKNAAM = rs.map(r => r.naam).join("_");
    $("kb-csv").hidden = !RES.length;
    if (window.gtag) gtag("event", "view_search_results", {search_term: rs.map(r => r.naam).join(" + "), bron: "kerkboeken", aantal: RES.length});
    await toonMeer();
  }

  function toonNamen(o) {
    const html = TERMEN.map((t, ti) => {
      const chips = [...t.auto.keys(), ...t.k.bij].filter((b, i, l) => l.indexOf(b) === i)
        .sort((a, b) => basisAantal(b) - basisAantal(a))
        .map(b => `<button type="button" class="kb-chip${t.k.uit.has(b) ? " uit" : ""}" data-t="${t.i}" data-b="${b}" aria-pressed="${!t.k.uit.has(b)}" title="${esc(LEDEN[b].map(x => x[0]).join(", "))}">${esc(NAMEN.b[b])} <span>${fmt(basisAantal(b))}</span></button>`).join("");
      const spell = [...t.basis].map(b => `<li><b>${esc(NAMEN.b[b])}</b>: ${LEDEN[b].map(([nm, a]) => `${esc(nm)} <span class="klein">(${fmt(a)})</span>`).join(", ")}</li>`).join("");
      const alias = [...t.alias].map(b => `<button type="button" class="kb-chip alias" data-t="${t.i}" data-b="${b}" data-alias="1" title="${esc(T.aliasUitleg)}">${esc(NAMEN.b[b])} <span>${esc((KOP.get(b).find(x => t.basis.has(x[0])) || [0, 0, ""])[2])}</span></button>`).join("");
      const bijna = [...t.bijna.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10)
        .map(([b]) => `<button type="button" class="kb-chip bijna" data-t="${t.i}" data-b="${b}" data-bij="1" title="${esc(T.voegToe)}">+ ${esc(NAMEN.b[b])} <span>${fmt(basisAantal(b))}</span></button>`).join("");
      const kop = [t.vn, t.naam].filter(Boolean).join(" ") + (t.rol != null ? ` (${T.rollen[META.rollen[t.rol]] || ""})` : "");
      return `<div class="kb-term"><p class="kb-termkop"><b>${esc(kop)}</b> — ${esc(T.meegenomen)}</p>
<p class="kb-chips">${chips || `<span class="klein">${esc(T.geenSpelling)}</span>`}</p>
${alias ? `<p class="kb-chips"><span class="klein">${esc(T.viaAlias)}</span> ${alias}</p>` : ""}
${bijna ? `<p class="kb-chips"><span class="klein">${esc(T.lijktOp)}</span> ${bijna}</p>` : ""}
${spell ? `<details><summary>${esc(T.alleSpellingen)}</summary><ul class="kb-spell">${spell}</ul></details>` : ""}</div>`;
    }).join("");
    $("kb-namen").innerHTML = html;
  }
  $("kb-namen") && $("kb-namen").addEventListener("click", e => {
    const c = e.target.closest(".kb-chip"); if (!c) return;
    const k = keuzes[+c.dataset.t], b = +c.dataset.b;
    if (c.dataset.bij) { k.bij.add(b); k.uit.delete(b); }
    else if (c.dataset.alias) { k.uit.add(b); }
    else if (k.uit.has(b)) k.uit.delete(b); else k.uit.add(b);
    zoek();
  });

  async function haalAktes(ids) {
    const uit = new Map();
    for (let i = 0; i < ids.length; i += 200) {
      const stuk = ids.slice(i, i + 200);
      for (const [id, bk, pg, nr, soort, jaar, datum, p] of await sql(`select id, boek_id, pg, nr, soort, jaar, datum, p from akte where id in (${inLijst(stuk)})`))
        uit.set(id, {id, bk, pg, nr, soort, jaar, datum, p: JSON.parse(p)});
    }
    return uit;
  }
  function gemarkeerd(a) {
    const m = new Map();
    RES.treffers.forEach((t, ti) => { for (const [i, viaAlias] of (t.get(a) || [])) m.set(i, viaAlias ? "alias" : "ja"); });
    return m;
  }
  function persoonExtra(x) {
    const e = x[3] || {}, d = [];
    if (e.an) d.push(`${esc(e.aw || "alias")} <b>${esc(e.an)}</b>`);
    if (e.l) d.push(`${esc(T.lees)} <i>${esc(e.l)}</i>`);
    if (e.b) d.push(esc(e.b));
    if (e.z) d.push(`<span class="kb-onzeker">${esc(e.z === 2 ? T.zekLaag : T.zekMidden)}</span>`);
    if (e.c) d.push(`<span class="kb-onzeker">${esc(T.controle)}: ${esc(e.c)}</span>`);
    if (e.o) d.push(`<span class="klein">${esc(e.o)}</span>`);
    return d.join(" · ");
  }
  function scanLink(bk, pg) { const b = BOEK.get(bk); return `${b.url}?pg=${pg}`; }
  function akteHTML(r, akte) {
    const b = BOEK.get(r.bk), m = gemarkeerd(r.a);
    const rijen = akte.p.map((x, i) => {
      const mk = m.get(i), naam = esc(x[0] || "–");
      return `<tr${mk ? ` class="kb-treffer${mk === "alias" ? " alias" : ""}"` : ""}><td>${esc(T.rollen[META.rollen[x[2]]] || "")}</td><td>${esc(x[1] || "")}</td><td>${mk ? `<mark>${naam}</mark>` : naam}</td><td>${persoonExtra(x)}</td></tr>`;
    }).join("");
    return `<article class="hh kb-akte">
<div class="hh-kop"><span class="plaats">${esc(META.parochies[b.p])}</span><span>${esc(T.soorten[META.soorten[akte.soort]] || "")} ${akte.jaar || ""}${akte.datum ? ` · ${esc(akte.datum)}` : ""}</span><span>${esc(b.code)}</span><a href="${esc(scanLink(r.bk, r.pg))}" target="_blank" rel="noopener">${esc(T.scan)} ${r.pg}</a></div>
<div class="tabel"><table><thead><tr><th>${esc(T.rol)}</th><th>${esc(T.voornaam)}</th><th>${esc(T.achternaam)}</th><th>${esc(T.toelichting)}</th></tr></thead><tbody>${rijen}</tbody></table></div>
</article>`;
  }
  async function toonMeer() {
    const stuk = RES.slice(getoond, getoond + 50);
    getoond += stuk.length;
    if (!stuk.length) return;
    const meer = $("kb-meer"); if (meer) meer.parentNode.remove();
    const oud = $("kb-status").textContent; status(T.laadAkten);
    const akten = await haalAktes(stuk.map(r => r.a));
    status(oud);
    $("kb-uitkomst").insertAdjacentHTML("beforeend", stuk.map(r => akten.has(r.a) ? akteHTML(r, akten.get(r.a)) : "").join(""));
    if (getoond < RES.length) $("kb-uitkomst").insertAdjacentHTML("beforeend", `<p class="meer"><button id="kb-meer" type="button">${esc(T.meer)} (${fmt(RES.length - getoond)})</button></p>`);
  }
  $("kb-uitkomst") && $("kb-uitkomst").addEventListener("click", e => { if (e.target.id === "kb-meer") toonMeer(); });

  /* ---------- CSV ---------- */
  function csvDownload(naam, kop, rijen) {
    const q = v => { v = v == null ? "" : String(v); return /[;"\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    const tekst = "﻿" + [kop, ...rijen].map(r => r.map(q).join(";")).join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([tekst], {type: "text/csv;charset=utf-8"}));
    a.download = naam; document.body.appendChild(a); a.click(); a.remove();
  }
  async function csvZoek() {
    status(T.csvBezig);
    const akten = await haalAktes(RES.map(r => r.a));
    const rij = [];
    for (const r of RES) {
      const ak = akten.get(r.a); if (!ak) continue;
      const b = BOEK.get(r.bk), m = gemarkeerd(r.a);
      ak.p.forEach((x, i) => {
        const e = x[3] || {};
        rij.push([TERMEN.length > 1 ? r.groep : "", m.has(i) ? (m.get(i) === "alias" ? "alias" : "x") : "", META.parochies[b.p], b.code, ak.jaar, ak.datum,
                  T.soorten[META.soorten[ak.soort]], T.rollen[META.rollen[x[2]]], x[1], x[0], e.l || "", e.aw || "", e.an || "", e.b || "",
                  e.z ? (e.z === 2 ? T.zekLaag : T.zekMidden) : "", e.c || "", e.o || "", scanLink(r.bk, r.pg)]);
      });
    }
    csvDownload(`kerkboeken_${ZOEKNAAM.replace(/[^\p{L}\p{N}_-]+/gu, "")}.csv`, T.csvKop, rij);
    status(T.csvKlaar);
  }
  $("kb-csv") && $("kb-csv").addEventListener("click", csvZoek);

  /* ---------- zoekopdracht in de link (#…) bewaren en herstellen ---------- */
  function bewaarInLink(rs, o) {
    const p = new URLSearchParams();
    rs.forEach((r, k) => { const s = k ? String(k + 1) : ""; p.set("q" + s, r.naam); if (r.vn) p.set("v" + s, r.vn); if (r.rol != null) p.set("r" + s, META.rollen[r.rol]); });
    if (rs.length > 1) p.set("samen", o.samen);
    if (o.exact) p.set("m", "e");
    if (o.drempel !== 80) p.set("d", o.drempel);
    if (!o.alias) p.set("alias", "0");
    if (o.par != null) p.set("par", META.parochies[o.par]);
    if (o.soort != null) p.set("s", META.soorten[o.soort]);
    if (o.van) p.set("van", o.van);
    if (o.tot) p.set("tot", o.tot);
    history.replaceState(null, "", "#" + p.toString());
  }
  function zoekParochie(naam) {
    if (!naam) return null;
    const vgl = s => s.toLowerCase().replace(/ß/g, "ss").replace(/,/g, "").replace(/\s+/g, " ").trim();
    let i = META.parochies.findIndex(p => vgl(p) === vgl(naam));
    if (i >= 0) return i;
    const plaats = vgl(naam).split(" ")[0];
    const kand = META.parochies.map((p, k) => [vgl(p).split(" ")[0], k]).filter(([pl]) => pl === plaats);
    return kand.length === 1 ? kand[0][1] : null;
  }
  async function herstel() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (!p.get("q")) return;
    await laad();
    $("kb-regels").innerHTML = "";
    for (const s of ["", "2", "3"]) {
      if (!p.get("q" + s)) continue;
      const r = p.get("r" + s); voegRegelToe({naam: p.get("q" + s), vn: p.get("v" + s) || "", rol: r ? META.rollen.indexOf(r) : null});
    }
    if (p.get("samen")) $("kb-samen").value = p.get("samen");
    if (p.get("m") === "e") { $("kb-exact").checked = true; $("kb-drempelvak").hidden = true; }
    if (p.get("d")) { $("kb-drempel").value = p.get("d"); $("kb-drempelwaarde").textContent = p.get("d"); }
    if (p.get("alias") === "0") $("kb-alias").checked = false;
    const par = zoekParochie(p.get("par")); if (par != null) $("kb-par").value = par;
    if (p.get("s")) $("kb-soort").value = META.soorten.indexOf(p.get("s"));
    if (p.get("van")) $("kb-van").value = p.get("van");
    if (p.get("tot")) $("kb-tot").value = p.get("tot");
    if (KB.pagina === "zoeken") zoek();
  }

  /* ---------- gezinnen ---------- */
  const HULP = {nl: "ouders schatten", de: "Eltern schätzen", en: "estimate parents"}[KB.taal] || "estimate parents";
  let GEZ = [], GZ = null;   // GZ: laatste zoekvraag met alle gevonden gezinnen; aan/uit zetten filtert lokaal
  async function zoekGezin() {
    await laad();
    const naam = $("gz-naam").value.trim(), als = $("gz-als").value, par = $("gz-par").value === "" ? null : +$("gz-par").value;
    $("gz-uitkomst").innerHTML = ""; $("gz-csv").hidden = true; $("gz-namen").innerHTML = "";
    if (!naam) { $("gz-status").textContent = T.geenNaam; return; }
    const bv = [...basisvormen(naam, 80, false).keys()];
    if (!bv.length) { $("gz-status").textContent = T.niets; GZ = null; return; }
    $("gz-status").textContent = T.bezig;
    const l = inLijst(bv);
    const w = als === "vader" ? `v_basis in (${l})` : als === "moeder" ? `m_basis in (${l})` : `(v_basis in (${l}) or m_basis in (${l}))`;
    const rijen = await sql(`select id, parochie_id, vader, moeder, n, van, tot, k, v_basis, m_basis from gezin where ${w}${par != null ? " and parochie_id = " + par : ""} order by parochie_id, van`);
    const oud = GZ && GZ.naam === naam ? GZ.uit : new Set();
    GZ = {naam, als, bv, uit: new Set([...oud].filter(b => bv.includes(b))), rijen};
    toonGezin();
  }
  function toonGezin() {
    const {als, bv, uit, rijen} = GZ;
    const heeft = (r, b) => (als !== "moeder" && r[8] === b) || (als !== "vader" && r[9] === b);
    const tel = new Map(bv.map(b => [b, rijen.filter(r => heeft(r, b)).length]));
    const chips = bv.filter(b => tel.get(b) > 0).sort((a, b) => tel.get(b) - tel.get(a))
      .map(b => `<button type="button" class="kb-chip${uit.has(b) ? " uit" : ""}" data-b="${b}" aria-pressed="${!uit.has(b)}" title="${esc(LEDEN[b].map(x => x[0]).join(", "))}">${esc(NAMEN.b[b])} <span>${fmt(tel.get(b))}</span></button>`).join("");
    $("gz-namen").className = "kb-chips";
    $("gz-namen").innerHTML = chips ? `<span class="klein">${esc(T.meegenomen)}:</span> ${chips}` : "";
    GEZ = rijen.filter(r => bv.some(b => !uit.has(b) && heeft(r, b)));
    $("gz-status").textContent = GEZ.length === 1 ? T.gezinEen : T.gezinAantal.replace("{n}", fmt(GEZ.length));
    $("gz-csv").hidden = !GEZ.length;
    $("gz-uitkomst").innerHTML = GEZ.length ? `<div class="tabel"><table><thead><tr><th>${esc(T.parochie)}</th><th>${esc(T.rollen.vader)}</th><th>${esc(T.rollen.moeder)}</th><th class="getal">${esc(T.kinderen)}</th><th>${esc(T.dopen)}</th></tr></thead><tbody>${
      GEZ.map(([id, p, v, m, n, van, tot, k]) => `<tr><td>${esc(META.parochies[p])}</td><td>${esc(v)}</td><td>${esc(m)}</td><td class="getal">${n}${van ? `<br><a class="klein" href="${KB.basis}${KB.taal}/hulpmiddelen.html#oudste=${van}${tot && tot !== van ? "&jongste=" + tot : ""}" title="${esc(HULP)}">${esc(HULP)}</a>` : ""}</td><td>${
        JSON.parse(k).map(([j, kind, bk, pg]) => `<a href="${esc(scanLink(bk, pg))}" target="_blank" rel="noopener">${j || "?"}</a> ${esc(kind || "")}`).join("; ")}</td></tr>`).join("")}</tbody></table></div>` : "";
  }
  $("gz-namen") && $("gz-namen").addEventListener("click", e => {
    const c = e.target.closest(".kb-chip"); if (!c || !GZ) return;
    const b = +c.dataset.b;
    if (GZ.uit.has(b)) GZ.uit.delete(b); else GZ.uit.add(b);
    toonGezin();
  });
  function csvGezin() {
    const rij = [];
    for (const [id, p, v, m, n, van, tot, k] of GEZ) for (const [j, kind, bk, pg] of JSON.parse(k)) rij.push([id, META.parochies[p], v, m, j, kind, scanLink(bk, pg)]);
    csvDownload(`gezinnen_${$("gz-naam").value.trim()}.csv`, T.csvGezinKop, rij);
  }

  /* ---------- namen bladeren ---------- */
  async function zoekNamen() {
    await laad();
    const q = $("nm-naam").value.trim();
    if (!q) { $("nm-uitkomst").innerHTML = ""; return; }
    const exact = q.endsWith("*"), pre = q.replace(/\*$/, "").toLowerCase();
    let bv;
    if (exact) bv = NAMEN.b.map((b, i) => [i, 100]).filter(([i]) => LEDEN[i].some(([nm]) => nm.toLowerCase().startsWith(pre)));
    else bv = [...basisvormen(q, 70, false).entries()];
    bv.sort((a, b) => b[1] - a[1] || basisAantal(b[0]) - basisAantal(a[0]));
    $("nm-uitkomst").innerHTML = bv.length ? `<div class="tabel"><table><thead><tr><th>${esc(T.basisvorm)}</th><th class="getal">${esc(T.vermeldingen)}</th><th>${esc(T.spellingen)}</th><th>${esc(T.koppelingen)}</th></tr></thead><tbody>${
      bv.slice(0, 200).map(([b]) => `<tr><td><a href="${esc(KB.zoekpagina)}#q=${encodeURIComponent(NAMEN.b[b])}">${esc(NAMEN.b[b])}</a></td><td class="getal">${fmt(basisAantal(b))}</td><td>${
        LEDEN[b].map(([nm, a]) => `${esc(nm)} <span class="klein">(${fmt(a)})</span>`).join(", ")}</td><td>${
        (KOP.get(b) || []).map(([a, n, w]) => `<a href="${esc(KB.zoekpagina)}#q=${encodeURIComponent(NAMEN.b[a])}">${esc(NAMEN.b[a])}</a> <span class="klein">(${esc(w || "alias")}, ${n}×)</span>`).join(", ")}</td></tr>`).join("")}</tbody></table></div>` : `<p>${esc(T.niets)}</p>`;
  }

  /* ---------- dekking (pagina "Over") ---------- */
  async function toonDekking() {
    await laad();
    const per = new Map();
    for (const [p, s, n, a, z] of META.dekking) { if (!per.has(p)) per.set(p, {}); per.get(p)[s] = [n, a, z]; }
    const cel = x => x ? `${fmt(x[0])} <span class="klein">(${x[1] || "?"}–${x[2] || "?"})</span>` : "–";
    $("kb-dekking").innerHTML = `<div class="tabel"><table><thead><tr><th>${esc(T.parochie)}</th><th>${esc(T.soorten.doop)}</th><th>${esc(T.soorten.huwelijk)}</th><th>${esc(T.soorten.overlijden)}</th></tr></thead><tbody>${
      [...per.entries()].map(([p, s]) => `<tr><td>${esc(META.parochies[p])}</td><td>${cel(s[0])}</td><td>${cel(s[1])}</td><td>${cel(s[2])}</td></tr>`).join("")}</tbody></table></div>`;
    $("kb-totaal").textContent = T.totaal.replace("{v}", fmt(META.vermeldingen)).replace("{a}", fmt(META.akten)).replace("{p}", fmt(META.parochies.length)).replace("{d}", META.gemaakt);
  }

  /* ---------- starten ---------- */
  (async function () {
    try {
      if (KB.pagina === "zoeken") {
        await laad();
        voegRegelToe();
        $("kb-plus").addEventListener("click", () => voegRegelToe());
        $("kb-regels").addEventListener("click", e => { const b = e.target.closest(".kb-weg"); if (b) { delete keuzes[+b.parentNode.dataset.i]; b.parentNode.remove(); werkSamenBij(); } });
        $("kb-form").addEventListener("submit", e => { e.preventDefault(); zoek().catch(fout); });
        $("kb-drempel").addEventListener("input", () => { $("kb-drempelwaarde").textContent = $("kb-drempel").value; });
        $("kb-exact").addEventListener("change", () => { $("kb-drempelvak").hidden = true; });
        $("kb-fuzzy").addEventListener("change", () => { $("kb-drempelvak").hidden = false; });
        await herstel();
        window.addEventListener("hashchange", () => herstel().catch(fout));
      } else if (KB.pagina === "gezinnen") {
        await laad();
        $("gz-form").addEventListener("submit", e => { e.preventDefault(); zoekGezin().catch(fout); });
        $("gz-csv").addEventListener("click", csvGezin);
        const p = new URLSearchParams(location.hash.slice(1)); if (p.get("q")) { $("gz-naam").value = p.get("q"); zoekGezin().catch(fout); }
      } else if (KB.pagina === "namen") {
        await laad();
        $("nm-form").addEventListener("submit", e => { e.preventDefault(); zoekNamen(); });
      } else if (KB.pagina === "over") {
        await toonDekking();
      }
    } catch (e) { fout(e); }
  })();
  function fout(e) {
    console.error(e);
    const el = $("kb-status") || $("gz-status");
    if (el) el.textContent = T.fout;
  }
})();
