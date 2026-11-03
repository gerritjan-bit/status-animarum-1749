# lijst_ocr.py – stap 3: kolomgewijze OCR voor boeken met één persoon per regel
import os, re
from concurrent.futures import ThreadPoolExecutor
# Tesseract mag per aanroep maar één kern gebruiken; we draaien zelf meerdere kolommen tegelijk.
# Dat verandert niets aan de uitkomst, alleen aan de snelheid.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
import numpy as np
import cv2
import pytesseract

LIJST_VERSIE = "2026-11-04.1"   # snellere code, uitkomst gelijk aan de eerste versie
WERKERS = max(1, min(4, os.cpu_count() or 1))
LEEFTIJD = re.compile(r"^(\d{1,3}|\d?\s?1/[24]|[13]/4|1/2)[.,;:]?$")

def _gamma(g):
    return np.clip(((g / 255.0) ** 2.0) * 255, 0, 255).astype(np.uint8)

def _inkt(g):
    thr = min(170, cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[0])
    return (g < thr).astype(np.uint8)

def _inhoud_x(ink):
    """x-bereik van de bladspiegel: zwarte randen (rug, scanrand) eraf."""
    h, w = ink.shape
    frac = ink.sum(axis=0) / h
    ok = np.where(frac < 0.35)[0]
    if len(ok) == 0:
        return 0, w
    x0, x1 = ok[0], ok[-1]
    # randstroken met veel inkt aan de buitenkant overslaan
    while x0 < w // 4 and frac[x0] > 0.15:
        x0 += 1
    while x1 > 3 * w // 4 and frac[x1] > 0.15:
        x1 -= 1
    return int(x0) + 5, int(x1) - 5

def _segmenten(ink, x0, x1, min_gat):
    """Kolommen: x-stroken met tekst, gescheiden door verticale witruimte van minstens min_gat px."""
    h = ink.shape[0]
    prof = ink[int(0.04 * h):int(0.97 * h), x0:x1].sum(axis=0)
    prof = np.convolve(prof, np.ones(5) / 5, mode="same")
    leeg = prof <= max(2, 0.08 * np.percentile(prof, 95))
    seg, start, gat = [], None, 0
    for i, l in enumerate(leeg):
        if not l:
            if start is None:
                start = i
            gat = 0
        else:
            if start is not None:
                gat += 1
                if gat >= min_gat:
                    seg.append([start, i - gat + 1]); start = None; gat = 0
    if start is not None:
        seg.append([start, len(leeg)])
    seg = [[a + x0, b + x0] for a, b in seg if b - a > 12]
    return seg

def _blokken(seg, x0, x1):
    """Twee blokken naast elkaar (dubbele pagina, of twee huishoudlijsten naast elkaar) als er
    rond het midden een brede goot zit met aan beide kanten veel tekst."""
    w = x1 - x0
    for i in range(len(seg) - 1):
        gat = seg[i + 1][0] - seg[i][1]
        midden = (seg[i][1] + seg[i + 1][0]) / 2
        if gat > 0.05 * w and 0.33 * w < midden - x0 < 0.67 * w:
            links, rechts = seg[:i + 1], seg[i + 1:]
            if links[-1][1] - links[0][0] > 0.25 * w and rechts[-1][1] - rechts[0][0] > 0.25 * w:
                return [links, rechts]
    return [seg]

def _ocr_strook(g, a, b, psm=6):
    crop = _gamma(g[:, max(0, a - 6):b + 6])
    d = pytesseract.image_to_data(crop, lang="lat+deu", config=f"--psm {psm}",
                                  output_type=pytesseract.Output.DICT)
    woorden = []
    for i, t in enumerate(d["text"]):
        if t.strip() and float(d["conf"][i]) >= 0:
            woorden.append({"t": t, "y": d["top"][i] + d["height"][i] / 2, "top": d["top"][i],
                            "bot": d["top"][i] + d["height"][i], "x": d["left"][i] + a, "h": d["height"][i]})
    return woorden

def lijst_ocr(beeld_bytes):
    """Geeft rijen: dict(blok, regelnr, kolommen=[tekst per kolom], top, bot) en meta."""
    g = cv2.imdecode(np.frombuffer(beeld_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    ink = _inkt(g)
    x0, x1 = _inhoud_x(ink)
    min_gat = max(18, int(0.012 * (x1 - x0)))
    seg = _segmenten(ink, x0, x1, min_gat)
    rijen_uit = []
    with ThreadPoolExecutor(max_workers=WERKERS) as pool:     # kolommen tegelijk lezen
        res = list(pool.map(lambda s_: _ocr_strook(g, s_[0], s_[1]), seg))
    kolwoorden_seg = {tuple(s_): r for s_, r in zip(seg, res)}
    def numeriek(s_):
        ws = kolwoorden_seg[tuple(s_)]
        return bool(ws) and sum(1 for w in ws if LEEFTIJD.match(w["t"].strip(".,"))) / len(ws) > 0.5
    def tekst(s_):
        return sum(len(w["t"]) for w in kolwoorden_seg[tuple(s_)] if not LEEFTIJD.match(w["t"].strip(".,")))
    blokken = _blokken(seg, x0, x1)
    if len(blokken) == 2:
        maxt = max(tekst(s_) for s_ in seg) or 1
        if not all(any(not numeriek(s_) and tekst(s_) > 0.3 * maxt for s_ in b) for b in blokken):
            blokken = [seg]                       # rechts alleen leeftijden/opmerkingen: één blok
    for bi, blok in enumerate(blokken):
        kolwoorden = [kolwoorden_seg[tuple(s_)] for s_ in blok]
        alle = [w for kw in kolwoorden for w in kw]
        if not alle:
            continue
        hmed = float(np.median([w["h"] for w in alle])) or 20
        # regels vormen over alle kolommen heen, op verticale positie
        alle.sort(key=lambda w: w["y"])
        regels = []
        for w in alle:
            if regels and abs(w["y"] - regels[-1]["y"]) < 0.6 * hmed:
                r = regels[-1]; r["w"].append(w); r["y"] = np.mean([x["y"] for x in r["w"]])
                r["top"] = min(r["top"], w["top"]); r["bot"] = max(r["bot"], w["bot"])
            else:
                regels.append({"y": w["y"], "w": [w], "top": w["top"], "bot": w["bot"]})
        afstanden = [b["top"] - a["bot"] for a, b in zip(regels, regels[1:])]
        normaal = float(np.median(afstanden)) if afstanden else hmed * 0.5
        for ri, r in enumerate(regels):
            kols = []
            for (a, b) in blok:
                kols.append(" ".join(w["t"] for w in sorted(r["w"], key=lambda w: w["x"]) if a - 8 <= w["x"] < b + 8))
            wit = ri > 0 and (r["top"] - regels[ri - 1]["bot"]) > normaal + 0.7 * hmed
            rijen_uit.append({"blok": bi, "regelnr": ri, "kolommen": kols, "top": int(r["top"]),
                              "bot": int(r["bot"]), "witregel_boven": bool(wit)})
    return rijen_uit, {"kolommen": [[a, b] for a, b in seg], "blokken": len(blokken)}

def ken_kolommen_toe(rijen):
    """Per blok: welke kolom is rol / naam / leeftijd / opmerking (op basis van de inhoud)."""
    per_blok = {}
    for r in rijen:
        per_blok.setdefault(r["blok"], []).append(r)
    uit = []
    for b, rs in per_blok.items():
        n = max(len(r["kolommen"]) for r in rs)
        tekens = [sum(len(r["kolommen"][k]) for r in rs if k < len(r["kolommen"])) for k in range(n)]
        getal = [sum(1 for r in rs if k < len(r["kolommen"]) and r["kolommen"][k] and
                     LEEFTIJD.match(r["kolommen"][k].split()[0].strip(".,")) ) for k in range(n)]
        gevuld = [sum(1 for r in rs if k < len(r["kolommen"]) and r["kolommen"][k].strip()) for k in range(n)]
        naam = int(np.argmax(tekens))
        lft = [k for k in range(naam + 1, n) if gevuld[k] and getal[k] / gevuld[k] > 0.5]
        lft = lft[0] if lft else None
        for r in rs:
            k = r["kolommen"] + [""] * (n - len(r["kolommen"]))
            rol = " ".join(x for x in k[:naam] if x).strip()
            nm = k[naam].strip()
            leeftijd = k[lft].strip() if lft is not None else ""
            rest = " ".join(x for i, x in enumerate(k) if i > naam and i != lft and x).strip()
            if lft is None or not leeftijd:                    # leeftijd soms in de naamkolom
                m = re.search(r"\s(\d{1,3}|1/[24]|3/4)[.,]?$", nm)
                if m:
                    leeftijd, nm = m.group(1), nm[:m.start()].strip()
            # rol in de naamkolom ('filiae: Margaretha', 'ejus uxor: Aleidis')
            m = re.match(r"^((?:[A-Za-zÄÖÜäöüß()?.]+\s){0,2}[A-Za-zÄÖÜäöüß()?.]+)\s?[:;]\s*(.*)$", nm)
            if m and len(m.group(1)) <= 24 and not rol:
                rol, nm = m.group(1).strip(), m.group(2).strip()
            uit.append({**r, "rol": rol, "naam": nm, "leeftijd": leeftijd, "opmerking": rest})
    return uit
