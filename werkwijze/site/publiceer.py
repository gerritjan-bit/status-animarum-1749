# publiceer.py – zet de gebouwde site in één commit op GitHub, via de GitHub-API.
# Alleen gewijzigde bestanden worden geüpload. Bestanden buiten de 'beheerde' mappen
# (README, LICENSE, werkwijze/ …) blijven ongemoeid, behalve wat hier expliciet wordt meegegeven.
import base64, hashlib, os, time
import requests

API = "https://api.github.com"
BEHEERD = ("nl/", "de/", "en/", "data/", "assets/")
BEHEERDE_BESTANDEN = {"index.html", "sitemap.xml", "robots.txt", ".nojekyll"}

class GitHub:
    def __init__(self, token, eigenaar, repo, tak="main"):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})
        self.r = f"{API}/repos/{eigenaar}/{repo}"
        self.tak = tak

    def _req(self, methode, pad, **kw):
        for poging in range(4):
            r = self.s.request(methode, self.r + pad, timeout=60, **kw)
            if r.status_code in (502, 503, 504) or (r.status_code == 403 and "rate limit" in r.text.lower()):
                time.sleep(5 * (poging + 1)); continue
            return r
        return r

    def check(self):
        r = self._req("GET", "")
        if r.status_code == 401:
            raise RuntimeError("GitHub weigert het token (401). Controleer of het goed is geplakt en nog geldig is.")
        if r.status_code == 404:
            raise RuntimeError("Repository niet gevonden (404). Klopt de naam, en heeft het token toegang tot deze repository?")
        r.raise_for_status()
        return r.json()

    def bestand(self, pad):
        """Inhoud van één bestand in de repository, of None als het er niet is."""
        r = self._req("GET", f"/contents/{pad}", params={"ref": self.tak})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return base64.b64decode(r.json()["content"])

    def boom(self):
        ref = self._req("GET", f"/git/ref/heads/{self.tak}"); ref.raise_for_status()
        commit_sha = ref.json()["object"]["sha"]
        c = self._req("GET", f"/git/commits/{commit_sha}"); c.raise_for_status()
        boom_sha = c.json()["tree"]["sha"]
        t = self._req("GET", f"/git/trees/{boom_sha}", params={"recursive": "1"}); t.raise_for_status()
        j = t.json()
        if j.get("truncated"):
            raise RuntimeError("De bestandslijst van de repository is te groot om in één keer op te halen.")
        return commit_sha, boom_sha, {e["path"]: e["sha"] for e in j["tree"] if e["type"] == "blob"}

    def blob(self, data):
        r = self._req("POST", "/git/blobs", json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
        if r.status_code == 403:
            raise RuntimeError("GitHub staat schrijven niet toe (403). Geef het token 'Contents: Read and write' voor deze repository.")
        r.raise_for_status()
        return r.json()["sha"]

def git_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def lokale_bestanden(map_, voorvoegsel=""):
    uit = {}
    for wortel, _, namen in os.walk(map_):
        for n in namen:
            p = os.path.join(wortel, n)
            rel = voorvoegsel + os.path.relpath(p, map_).replace(os.sep, "/")
            uit[rel] = p
    return uit

def publiceer(gh, site_map, extra=None, bericht="Site bijgewerkt", log=print):
    """extra: {pad_in_repo: lokaal_bestand} voor bestanden buiten de site (bijv. werkwijze/…)."""
    commit_sha, boom_sha, op_github = gh.boom()
    lokaal = lokale_bestanden(site_map)
    lokaal.update(extra or {})
    nieuw, gelijk = [], 0
    for pad, bestand in sorted(lokaal.items()):
        data = open(bestand, "rb").read()
        sha = git_sha(data)
        if op_github.get(pad) == sha:
            gelijk += 1; continue
        nieuw.append((pad, data, sha))
    weg = [p for p in op_github if (p.startswith(BEHEERD) or p in BEHEERDE_BESTANDEN) and p not in lokaal]
    if not nieuw and not weg:
        log(f"Niets veranderd ({gelijk} bestanden al gelijk); geen nieuwe versie nodig.")
        return {"nieuw_of_gewijzigd": 0, "verwijderd": 0, "gelijk": gelijk}
    log(f"{len(nieuw)} bestanden uploaden, {len(weg)} verwijderen, {gelijk} ongewijzigd…")
    boom = []
    for i, (pad, data, sha) in enumerate(nieuw, 1):
        b = gh.blob(data)
        assert b == sha, f"onverwachte controlesom voor {pad}"
        boom.append({"path": pad, "mode": "100644", "type": "blob", "sha": b})
        if i % 50 == 0:
            log(f"  {i}/{len(nieuw)}")
    boom += [{"path": p, "mode": "100644", "type": "blob", "sha": None} for p in weg]
    t = gh._req("POST", "/git/trees", json={"base_tree": boom_sha, "tree": boom}); t.raise_for_status()
    c = gh._req("POST", "/git/commits", json={"message": bericht, "tree": t.json()["sha"], "parents": [commit_sha]}); c.raise_for_status()
    r = gh._req("PATCH", f"/git/refs/heads/{gh.tak}", json={"sha": c.json()["sha"]}); r.raise_for_status()
    log(f"Klaar: nieuwe versie {c.json()['sha'][:7]} staat op GitHub. De site is over een minuut of twee bijgewerkt.")
    return {"nieuw_of_gewijzigd": len(nieuw), "verwijderd": len(weg), "gelijk": gelijk}
