# bewerk.py – stap 1 (huishoudens opnieuw splitsen) en stap 2 (OCR-correctie)
# voor de database van het Status-Animarum-notebook.
#
# Uitgangspunten:
#  * paginas.ruwe_tekst (de OCR) wordt nooit gewijzigd;
#  * elke automatische wijziging is terug te voeren op een regel en een versie
#    (tabellen bewerkingen, regels, correcties);
#  * het script is herhaalbaar: opnieuw draaien bouwt huishoudens, personen,
#    correcties en zoekindex opnieuw op uit de ruwe OCR.

import collections, datetime, difflib, json, re, sqlite3, statistics, unicodedata
from rapidfuzz import process, distance

VERSIE = "2026-11-04.1"

# ---------------------------------------------------------------- algemeen
WOORD = r"[A-Za-zÄÖÜäöüßéèáàëïæ]+"

def plak_regels(regels):
    """Regels aan elkaar plakken en afbrekingen herstellen ('Theo-' + 'dorus')."""
    uit = ""
    for r in regels:
        r = r.strip()
        if uit.endswith("-") and r[:1].islower():
            uit = uit[:-1] + r
        else:
            uit = (uit + " " + r).strip()
    return re.sub(r"\s+", " ", uit)

# ---------------------------------------------------------------- stap 1: splitsen
KOP_OUD = re.compile(r"^(f\.\s?\d+\S*|[A-Z]\.?|Hs\.\s?\d+.*|.{0,3})$")          # regel uit notebook v1
KOP = re.compile(r"^([f*£t]\s?\.\s?\d+\S*|[A-Z]\.?|Hs\.\s?\d+.*|.{0,3}|[^A-Za-zÄÖÜäöüß]*)$")
MARGE = re.compile(r"^\s*(f\.\s?\d+['’]?\s+|\d{1,3}\.\s+)")
KOPWOORD = re.compile(
    r"^(colonus|coloni|vidua|viduus|vid|kötter|kotter|pferdekötter|brinksitzer|brincksitzer|"
    r"mercenarius|mercenaria|mercen|villicus|incola|incolae|inquilinus|inquilini|inquil|textor|zeller|"
    r"schultetus|casatus|casat|par|familia|herr|operarius|operaria|heuerling|heuerman|arbeitsman|"
    r"einwohner|einwohnerin|tagelöhner|taglöhner)\b\.?", re.I)

def is_kop(l):
    return bool(KOP.match(l.strip()))

def oude_bereiken(lines, hh_teksten):
    """Koppelt de huishoudens uit het notebook (gesplitst op witregels) terug aan regelnummers."""
    idx = [k for k, l in enumerate(lines) if l.strip() and not KOP_OUD.match(l.strip())]
    res, p = [], 0
    for t in hh_teksten:
        for q in range(p + 1, len(idx) + 1):
            if plak_regels([lines[k] for k in idx[p:q]]) == t:
                res.append((idx[p], idx[q - 1])); p = q; break
        else:
            return None
    return res

def schoon_einde(l):
    """Rommel aan het regeleinde weghalen (':', '||!', 'a RUE') vóór de eindcontrole."""
    l = MARGE.sub("", l).rstrip()
    vorige = None
    while vorige != l:
        vorige = l
        m = re.search(r"\s+(\S+)$", l)
        if m:
            tok = m.group(1)
            if not re.fullmatch(r"(\d{1,3}([/.]\d)?[.,;]?|\d/\d|[A-Za-zÄÖÜäöüß]{2,}[.,;:]?|[A-Za-zÄÖÜäöüß]+-)", tok) \
               or (len(tok) <= 3 and not tok[:1].isdigit()
                   and tok.lower().strip(".,") not in ("ux", "fil", "vid", "anc", "fam", "et")):
                l = l[:m.start()].rstrip()
    return l

def eind_signaal(l):
    l = l.rstrip(" |!'\"")
    if not l or l.endswith("-"):
        return "afbreking"
    if l.endswith(","):
        return "komma"
    if re.search(r"(\d|infans|[)\]])[.;]?$", l):
        return "getal"
    return "anders"

def grenzen(lines, witregel_grenzen, lijstboek, factor=0.82):
    """{regelnr: reden} – na deze regel eindigt een huishouden."""
    g = {a: "witregel" for a in witregel_grenzen}
    inhoud = [k for k, l in enumerate(lines) if l.strip() and not is_kop(l)]
    if lijstboek or len(inhoud) < 4:
        return g                     # lijstboeken: één persoon per regel, zie stap 3
    schoon = {k: schoon_einde(lines[k]) for k in inhoud}
    lens = sorted(len(schoon[k]) for k in inhoud)
    W = lens[int(0.85 * (len(lens) - 1))]
    for a, b in zip(inhoud, inhoud[1:]):
        if a in g:
            continue
        sig = eind_signaal(schoon[a])
        if sig in ("komma", "afbreking"):
            continue
        volgende = MARGE.sub("", lines[b]).lstrip(' |*"\'')
        m = KOPWOORD.match(volgende)
        if m and sig in ("getal", "anders"):
            g[a] = "volgende regel begint met '" + m.group(1).lower() + "'"
        elif sig == "getal" and len(schoon[a]) < factor * W:
            g[a] = "korte regel eindigend op een leeftijd"
    return g

def splits_pagina(lines, g):
    """Geeft [(regel_van, regel_tot, begin_reden, tekst)]."""
    uit, huidig, reden = [], [], "begin van de pagina"
    for k, l in enumerate(lines):
        if not l.strip() or is_kop(l):
            continue
        huidig.append(k)
        if k in g:
            uit.append((huidig[0], huidig[-1], reden, plak_regels([lines[i] for i in huidig])))
            huidig, reden = [], g[k]
    if huidig:
        uit.append((huidig[0], huidig[-1], reden, plak_regels([lines[i] for i in huidig])))
    return [u for u in uit if u[3].strip()]

# ---------------------------------------------------------------- stap 2: correctie
VERWARD_BEGIN = {
    "M": ["l", "L", "h", "k", "K", "N", "li", "Li", "ll", "lI", "Il"],
    "B": ["P", "D", "d", "S", "8"],
    "H": ["E", "h", "I"],
    "G": ["V", "C", "6"],
    "C": ["V", "G"],
    "E": ["L", "B"],
    "T": ["I", "l"],
    "J": ["d", "I", "l"],
}
# vormen die in dit corpus alleen als OCR-fout voorkomen, maar vaak genoeg om als 'naam' door te gaan
HANDMATIG = {"Meria": "Maria", "Naria": "Maria", "Neria": "Maria", "leria": "Maria", "lieria": "Maria",
             "eria": "Maria", "Mergaretha": "Margaretha", "Nargaretha": "Margaretha"}
VERV = {("s","a"),("g","a"),("z","a"),("r","n"),("n","r"),("e","c"),("c","e"),("i","l"),("l","i"),
        ("i","t"),("t","i"),("k","h"),("b","h"),("t","r"),("ä","d"),("ü","d"),("ü","u"),("ä","a"),
        ("m","n"),("h","n"),("e","s"),("o","a"),("t","b"),("p","o"),("T","F"),("c","d"),("v","c"),
        ("ö","o"),("á","a"),("é","e"),("I","l"),("l","I")}
RUIS = re.compile(r"^[^\wäöüÄÖÜß&/()'.,;:-]+$")
RAND = re.compile(r"^[|^»«*$#_~=<>{}\[\]\\\"!]+|[|^»«*$#_~=<>{}\[\]\\\"!]+$")
CIJFER = re.compile(r"^(\d)([CO])$|^([CO])(\d)$|^(ll)$")

class Corrector:
    def __init__(self, ruwe_teksten):
        self.freq = collections.Counter(); nb = collections.defaultdict(set)
        for boek, t in ruwe_teksten:
            for w in re.findall(WOORD, t or ""):
                self.freq[w] += 1; nb[w].add(boek)
        self.regels = self._bouw_regels()
        self.lexicon = {w for w, c in self.freq.items() if c >= 30 and len(nb[w]) >= 5
                        and len(w) >= 3 and w not in self.regels}
        self.lexlijst = sorted(self.lexicon)
        self.cache = {}

    def _bouw_regels(self, n_namen=200, min_freq=150):
        f = self.freq
        namen = [w for w, c in f.most_common() if w[:1].isupper() and len(w) >= 4
                 and w[1:].islower() and c >= min_freq and w not in HANDMATIG][:n_namen]
        echt = set(namen); regels = {}
        for n in namen:
            kand = {n[1:]: "beginletter weggevallen"}
            for ocr in VERWARD_BEGIN.get(n[0], []):
                kand[ocr + n[1:]] = f"{n[0]} gelezen als {ocr}"
            kand[n.lower()] = "hoofdletter gelezen als kleine letter"
            for v, reden in kand.items():
                if v in echt or len(v) < 3:
                    continue
                if f.get(v, 0) and f[v] * 3 <= f[n]:
                    regels[v] = (n, reden)
        for v, n in HANDMATIG.items():
            regels[v] = (n, "handmatig: komt in dit corpus alleen als OCR-fout voor")
        return regels

    @staticmethod
    def _verdacht(w, i):
        c = w[i]
        return (i > 0 and c.isupper()) or not c.isalpha() or c in "ßæ" or \
               (i > 0 and w[i-1].lower() == c.lower()) or (i + 1 < len(w) and w[i+1].lower() == c.lower())

    def _toegestaan(self, w, doel):
        if len(doel) < 4 or w.lower() == doel.lower():
            return False
        ops = distance.Levenshtein.editops(w, doel)
        if len(ops) != 1:
            return False
        op = ops[0]
        if op.tag == "replace":
            return len(w) >= 5 and ((w[op.src_pos], doel[op.dest_pos]) in VERV or self._verdacht(w, op.src_pos))
        if op.tag == "delete":
            return op.src_pos > 0 and len(w) >= 6 and self._verdacht(w, op.src_pos)
        if op.tag == "insert":
            return op.dest_pos == 0 and doel[0].isupper() and w[0].islower() and len(doel) >= 6
        return False

    def woord(self, w):
        """(nieuw, laag, regel) of None."""
        if w in self.cache:
            return self.cache[w]
        res = None
        if w in self.regels:
            res = (self.regels[w][0], "naamregel", w)
        elif len(w) >= 4 and self.freq.get(w, 0) <= 3 and w not in self.lexicon:
            beste = None
            for doel, dist, _ in process.extract(w, self.lexlijst, scorer=distance.Levenshtein.distance,
                                                 score_cutoff=1, limit=8):
                if self.freq[doel] >= 20 * max(self.freq.get(w, 1), 1) and self._toegestaan(w, doel):
                    if beste is None or self.freq[doel] > self.freq[beste]:
                        beste = doel
            if beste:
                res = (beste, "één teken", None)
        self.cache[w] = res
        return res

    def tekst(self, t):
        """Verbetert een huishoudtekst. Geeft (nieuwe tekst, [(positie_ocr, positie_nieuw, ocr, nieuw, laag, regel)]).
        positie_ocr = woordnummer in tekst_ocr, positie_nieuw = woordnummer in de verbeterde tekst (None als weg)."""
        uit, wijz = [], []
        for pos, tok in enumerate(t.split(" ")):
            if not tok:
                continue
            nu = len(uit)
            if RUIS.match(tok):
                wijz.append((pos, None, tok, "", "rommelteken", None)); continue
            kern = RAND.sub("", tok)
            if kern != tok:
                if not kern:
                    wijz.append((pos, None, tok, "", "rommelteken", None)); continue
                wijz.append((pos, nu, tok, kern, "rommelteken", None)); tok = kern
            if CIJFER.match(tok):
                n = tok.replace("C", "0").replace("O", "0").replace("ll", "11")
                wijz.append((pos, nu, tok, n, "cijfer", None)); uit.append(n); continue
            def vervang(m):
                r = self.woord(m.group(0))
                if r and r[0] != m.group(0):
                    wijz.append((pos, nu, m.group(0), r[0], r[1], r[2])); return r[0]
                return m.group(0)
            uit.append(re.sub(WOORD, vervang, tok))
        return " ".join(uit), wijz

# ---------------------------------------------------------------- ruwe structuur
RELATIES = {
    # Latijn, voluit en afgekort
    "uxor": "echtgenote", "ux": "echtgenote", "conj": "echtgenote", "conjux": "echtgenote",
    "maritus": "echtgenoot", "filius": "zoon", "filia": "dochter", "fil": "kind", "filii": "kinderen",
    "filiae": "dochters", "filiolus": "zoontje", "filiola": "dochtertje", "prol": "kind", "proles": "kind",
    "lib": "kind", "liberi": "kind", "pater": "vader", "mater": "moeder", "frater": "broer", "soror": "zus",
    "avus": "grootvader", "avia": "grootmoeder", "nepos": "kleinzoon/neef", "neptis": "kleindochter/nicht",
    "socrus": "schoonmoeder", "socer": "schoonvader", "gener": "schoonzoon", "nurus": "schoondochter",
    "privignus": "stiefzoon", "privigna": "stiefdochter", "ancilla": "dienstmeid", "ancillae": "dienstmeid",
    "anc": "dienstmeid", "serva": "dienstmeid", "servus": "knecht", "servi": "knecht", "serv": "knecht",
    "famulus": "knecht", "famula": "dienstmeid", "famuli": "dienstpersoneel", "fam": "dienstpersoneel",
    "bubulcus": "koeherder", "pastor": "herder", "vidua": "weduwe", "viduus": "weduwnaar", "vid": "weduwe",
    "incola": "inwoner", "incolae": "inwoners", "inc": "inwoner", "inquilinus": "inwoner", "inquil": "inwoner",
    # Duits
    "ehefrau": "echtgenote", "frau": "echtgenote", "kinder": "kind", "kind": "kind", "kindt": "kind",
    "sohn": "zoon", "tochter": "dochter", "vatter": "vader", "vater": "vader", "mutter": "moeder",
    "bruder": "broer", "schwester": "zus", "knecht": "knecht", "knegt": "knecht", "knegte": "knecht",
    "magd": "dienstmeid", "mohne": "tante", "wittibe": "weduwe", "witwe": "weduwe",
    "einwohner": "inwoner", "einwohnerin": "inwoonster", "ehel": "echtpaar",
}
_REL_TOK = re.compile(r"^(" + "|".join(sorted(map(re.escape, RELATIES), key=len, reverse=True)) + r")\.?:?$", re.I)
_LEEFTIJD = re.compile(r"^(\d{1,3}|\d?\s?1/[24]|3/4|[13]/4|1/2|infans)[.,;:]?$", re.I)

def _leeftijd_waarde(tok):
    t = tok.strip(".,;:").lower()
    if t == "infans" or "/" in t:
        return 0
    try:
        n = int(t)
        return n if n <= 110 else None
    except ValueError:
        return None

def ontleed(tekst, refjaar):
    """Heuristische opsplitsing van één huishouden in personen (zoekhulp, geen transcriptie)."""
    tekst = re.sub(r"\b(ux|fil|prol|lib|conj|vid|anc|fam|inc|serv|inquil)\.(?=\S)", r"\1. ", tekst, flags=re.I)
    tekst = re.sub(r"([A-Za-zäöüß]\.)(\d)", r"\1 \2", tekst)          # 'col.60' -> 'col. 60'
    personen, overerf = [], "hoofd"
    for i, seg in enumerate(s.strip() for s in tekst.split(",")):
        if not seg:
            continue
        toks = seg.split()
        rel = None; naam = []; leeftijd = None
        for j, t in enumerate(toks):
            m = _REL_TOK.match(t)
            if m and rel is None:
                rel = RELATIES[m.group(1).lower()]
            elif rel is None and j == 0 and len(t.strip(".:;,")) >= 5 and (
                    k := difflib.get_close_matches(t.strip(".:;,").lower(),
                                                   [x for x in RELATIES if len(x) >= 5], n=1, cutoff=0.75)):
                rel = RELATIES[k[0]]                 # OCR-variant van een rolwoord ('Shefrau', 'Kinat')
            elif _LEEFTIJD.match(t):
                if leeftijd is None:                     # eerste getal = leeftijd; later losse cijfers zijn meestal ruis
                    leeftijd = _leeftijd_waarde(t)
            else:
                naam.append(t)
        tekst_p = " ".join(naam).strip(" :")
        if rel is None and personen and personen[-1]["leeftijd"] is None and i > 0:
            vorige = personen[-1]                       # 'Bernardus Almerinck, faber lignarius 35'
            vorige["tekst"] = (vorige["tekst"] + ", " + tekst_p).strip(", ")
            vorige["leeftijd"] = leeftijd
            continue
        if rel is None:
            rel = (overerf if overerf != "hoofd" else "huisgenoot (relatie niet vermeld)") if personen else "hoofd"
        else:
            overerf = rel
        personen.append({"relatie": rel, "tekst": tekst_p, "leeftijd": leeftijd})
    for p in personen:
        p["geb_ca"] = (refjaar - p["leeftijd"]) if (refjaar and p["leeftijd"] is not None) else None
    return personen

# ---------------------------------------------------------------- database
SCHEMA = """
DROP TABLE IF EXISTS huishoudens; DROP TABLE IF EXISTS personen; DROP TABLE IF EXISTS zoek;
DROP TABLE IF EXISTS correcties; DROP TABLE IF EXISTS regels;
CREATE TABLE IF NOT EXISTS bewerkingen(id INTEGER PRIMARY KEY, datum TEXT, stap TEXT, versie TEXT,
    beschrijving TEXT, instellingen TEXT, aantallen TEXT, meting TEXT);
CREATE TABLE huishoudens(id INTEGER PRIMARY KEY, sleutel TEXT UNIQUE, boek_id TEXT, pg INT, nr INT,
    regel_van INT, regel_tot INT, begin_reden TEXT, opmaak TEXT, bron TEXT,
    tekst_ocr TEXT, tekst TEXT, aantal_correcties INT);
CREATE TABLE personen(huishouden_id INT, sleutel TEXT, volgnr INT, relatie TEXT, tekst TEXT, leeftijd INT, geb_ca INT);
CREATE TABLE regels(ocr_vorm TEXT PRIMARY KEY, verbeterd TEXT, soort TEXT, aantal INT);
CREATE TABLE correcties(huishouden_id INT, sleutel TEXT, positie_ocr INT, positie INT, ocr TEXT, verbeterd TEXT,
    laag TEXT, regel TEXT, versie TEXT);
CREATE VIRTUAL TABLE zoek USING fts5(tekst, tekst_ocr, huishouden_id UNINDEXED, tokenize='trigram');
"""

def opmaak_van_boek(teksten):
    regels = [l for t in teksten for l in (t or "").splitlines() if len(l.strip()) > 3]
    if not regels:
        return "proza"
    return "lijst" if statistics.median(len(l) for l in regels) < 40 else "proza"

def bewerk(pad, log=print, meting_sweep=None, meting_split=None):
    db = sqlite3.connect(pad)
    db.execute("PRAGMA journal_mode=WAL")
    boeken = {b: j for b, j in db.execute("SELECT boek_id, jaar FROM boeken")}
    paginas = db.execute("SELECT boek_id, pg, ruwe_tekst FROM paginas ORDER BY boek_id, pg").fetchall()
    heeft_lijst = db.execute("SELECT name FROM sqlite_master WHERE name='lijstregels'").fetchone() is not None
    # bestaande (notebook-)splitsing bewaren voor de witregelgrenzen
    oud = collections.defaultdict(list)
    if db.execute("SELECT name FROM sqlite_master WHERE name='huishoudens'").fetchone():
        kol = [r[1] for r in db.execute("PRAGMA table_info(huishoudens)")]
        veld = "tekst_ocr" if "tekst_ocr" in kol else "tekst"
        if "regel_van" in kol:
            for b, pg, rv, rt, reden in db.execute("SELECT boek_id,pg,regel_van,regel_tot,begin_reden FROM huishoudens ORDER BY boek_id,pg,nr"):
                oud[(b, pg)].append(("bereik", rv, rt, reden))
        else:
            for b, pg, t in db.execute(f"SELECT boek_id,pg,{veld} FROM huishoudens ORDER BY boek_id,pg,nr"):
                oud[(b, pg)].append(t)
    if not db.execute("SELECT name FROM sqlite_master WHERE name='witregels'").fetchone():
        # eenmalig: witregelgrenzen uit de notebook-splitsing vastleggen, want die zijn
        # straks niet meer af te leiden (de OCR-posities zijn niet bewaard)
        db.execute("CREATE TABLE witregels(boek_id TEXT, pg INT, na_regel INT)")
        for (b, pg, t) in paginas:
            lst = oud.get((b, pg), [])
            if lst and isinstance(lst[0], str):
                rb = oude_bereiken((t or "").split("\n"), lst)
                for s, e in (rb or [])[:-1]:
                    db.execute("INSERT INTO witregels VALUES (?,?,?)", (b, pg, e))
        db.commit()
    wit = collections.defaultdict(set)
    for b, pg, e in db.execute("SELECT boek_id, pg, na_regel FROM witregels"):
        wit[(b, pg)].add(e)

    per_boek = collections.defaultdict(list)
    for b, pg, t in paginas:
        per_boek[b].append(t)
    opmaak = {b: opmaak_van_boek(ts) for b, ts in per_boek.items()}
    try:
        db.execute("ALTER TABLE boeken ADD COLUMN opmaak TEXT")
    except sqlite3.OperationalError:
        pass
    for b, o in opmaak.items():
        db.execute("UPDATE boeken SET opmaak=? WHERE boek_id=?", (o, b))

    db.executescript(SCHEMA)
    corr = Corrector([(b, t) for b, _, t in paginas])
    reden_tel = collections.Counter(); laag_tel = collections.Counter(); regel_tel = collections.Counter()
    n_hh = 0
    for b, pg, t in paginas:
        lines = (t or "").split("\n")
        lijst_hier = heeft_lijst and db.execute(
            "SELECT 1 FROM lijstregels WHERE boek_id=? AND pg=? LIMIT 1", (b, pg)).fetchone()
        if lijst_hier:
            stukken = lijst_huishoudens(db, b, pg); bron = "kolom-OCR (stap 3)"
        else:
            g = grenzen(lines, wit[(b, pg)], opmaak[b] == "lijst")
            stukken = splits_pagina(lines, g); bron = "OCR notebook v1"
        for nr, (rv, rt, reden, tekst_ocr) in enumerate(stukken, start=1):
            reden_tel[reden.split(" '")[0]] += 1
            sleutel = f"{b}-{pg}-{nr:02d}"
            tekst, wijz = corr.tekst(tekst_ocr)
            cur = db.execute("INSERT INTO huishoudens(sleutel,boek_id,pg,nr,regel_van,regel_tot,begin_reden,"
                             "opmaak,bron,tekst_ocr,tekst,aantal_correcties) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                             (sleutel, b, pg, nr, rv, rt, reden, opmaak[b], bron, tekst_ocr, tekst,
                              sum(1 for w in wijz if w[4] != "rommelteken")))
            hid = cur.lastrowid; n_hh += 1
            db.executemany("INSERT INTO correcties VALUES (?,?,?,?,?,?,?,?,?)",
                           [(hid, sleutel, p, q, o, n, l, r, VERSIE) for p, q, o, n, l, r in wijz])
            for _, _, o, n, l, r in wijz:
                laag_tel[l] += 1
                if r:
                    regel_tel[r] += 1
            db.execute("INSERT INTO zoek(tekst, tekst_ocr, huishouden_id) VALUES (?,?,?)", (tekst, tekst_ocr, hid))
            for i, p in enumerate(ontleed(tekst, boeken.get(b)), start=1):
                db.execute("INSERT INTO personen VALUES (?,?,?,?,?,?,?)",
                           (hid, sleutel, i, p["relatie"], p["tekst"], p["leeftijd"], p["geb_ca"]))
    for v, (n, soort) in corr.regels.items():
        db.execute("INSERT INTO regels VALUES (?,?,?,?)", (v, n, soort, regel_tel.get(v, 0)))
    nu = datetime.datetime.now().isoformat(timespec="seconds")
    db.execute("INSERT INTO bewerkingen(datum,stap,versie,beschrijving,instellingen,aantallen,meting) VALUES (?,?,?,?,?,?,?)",
        (nu, "1 · huishoudens splitsen", VERSIE,
         "Huishoudens bepaald uit de regels van de OCR. Een huishouden eindigt bij een witregel, bij een regel "
         "die duidelijk korter is dan de volle regelbreedte en op een leeftijd eindigt (de typemachine geeft elke "
         "letter even veel ruimte, dus regellengte = breedte), of als de volgende regel begint met een woord dat "
         "een huishouden opent (colonus, vidua, Kötter, incolae, …). Nooit na een regel die op een komma of "
         "afbreekstreepje eindigt. Folio- en letterkoppen worden overgeslagen. Boeken met één persoon per regel "
         "worden in deze stap alleen op witregels gesplitst (zie stap 3).",
         json.dumps({"korte_regel_factor": 0.82, "volle_breedte": "85e percentiel van de regellengte op de pagina"}),
         json.dumps({"huishoudens": n_hh, **reden_tel}, ensure_ascii=False), meting_split))
    db.execute("INSERT INTO bewerkingen(datum,stap,versie,beschrijving,instellingen,aantallen,meting) VALUES (?,?,?,?,?,?,?)",
        (nu, "2 · OCR-correctie", VERSIE,
         "Automatische correctie in drie lagen; de oorspronkelijke OCR blijft altijd bewaard (tekst_ocr). "
         "(1) Naamregels: systematische fouten in het begin van veelvoorkomende namen, vooral door de verhoogd "
         "getypte hoofdletters ('laria' → 'Maria', 'Pernardus' → 'Bernardus', 'enricus' → 'Henricus'); zie tabel "
         "regels. (2) Eén teken: een zeldzaam woord wordt vervangen door een veel vaker voorkomend woord als het "
         "verschil één bekende OCR-verwisseling is; e↔a bewust uitgesloten vanwege echte varianten (Anne/Anna). "
         "(3) Rommeltekens (|, », ^) verwijderd en cijferfouten hersteld (4C → 40, ll → 11). Elke wijziging staat "
         "in de tabel correcties.",
         json.dumps({"naamregels": len(corr.regels), "lexicon": len(corr.lexicon),
                     "min_frequentieverhouding_een_teken": 20}),
         json.dumps(dict(laag_tel), ensure_ascii=False), meting_sweep))
    db.commit()
    log(f"{n_hh} huishoudens; correcties per laag: {dict(laag_tel)}")
    return db

# ---------------------------------------------------------------- lijstboeken (stap 3)
HOOFDROL = re.compile(r"^(?!ehefrau|frau|kinder|kind|kindt|sohn|tochter|vatter|vater|mutter|knecht|knegt|knegte|"
                      r"magd|mohne|bruder|schwester|ux|uxor|conj|fil|filius|filia|filii|prol|proles|lib|liberi|"
                      r"anc|ancilla|serv|servus|servi|fam|famul|famula|soror|frater|pater|mater|avia|avus|nepos|neptis|"
                      r"socrus|socer|gener|nurus|privign|dessen|deren|die|der|et|&|ejus|eius|illorum|prioris|item|ejusdem)", re.I)

def lijst_huishoudens(db, b, pg):
    """Huishoudens uit de kolomregels van stap 3: nieuw huishouden bij een witregel boven de regel
    of bij een rol die geen gezinslid of personeel aanduidt (beroep, Einwohner, colonus, …)."""
    rijen = db.execute("SELECT regelnr, blok, rol, naam, leeftijd, opmerking, witregel_boven FROM lijstregels "
                       "WHERE boek_id=? AND pg=? ORDER BY blok, regelnr", (b, pg)).fetchall()
    uit, huidig, reden, vorig_blok = [], [], "begin van de pagina", None
    def sluit():
        if huidig:
            delen = []
            for r in huidig:
                naam = r[3] or ""
                if r[4]:                                  # losse cijfers achter de naam zijn ruis (verhoogde letter)
                    naam = re.sub(r"(\s+[\d|:;.,]{1,3})+$", "", naam)
                stuk = " ".join(x for x in (r[2], naam, r[4], r[5]) if x)
                delen.append(stuk)
            uit.append((huidig[0][0], huidig[-1][0], reden, ", ".join(delen)))
    for r in rijen:
        regelnr, blok, rol, naam, lft, opm, wit = r
        nieuw = None
        if blok != vorig_blok and huidig:
            nieuw = "volgende kolom op de pagina"
        elif wit and huidig:
            nieuw = "witregel"
        elif rol and HOOFDROL.match(rol.strip(" .:")) and huidig and naam:
            nieuw = f"rol '{rol.strip(' .:')}' opent een huishouden"
        if nieuw:
            sluit(); huidig, reden = [], nieuw
        huidig.append(r); vorig_blok = blok
    sluit()
    return uit
