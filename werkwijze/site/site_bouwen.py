# site_bouwen.py – bouwt de statische website uit de database.
#
#   python site_bouwen.py <database> <uitvoermap> [boek-id ...]
#
# Zonder boek-id's worden alle boeken gebouwd. De teksten van de pagina's staan in
# teksten/nl.md, de.md en en.md (bewerkbaar), de opmaak in assets/.
import datetime, html, json, os, re, shutil, sqlite3, sys
from collections import defaultdict
from urllib.parse import quote
import markdown

HIER = os.path.dirname(os.path.abspath(__file__))

CONFIG = {
    "basis_url": "https://gerritjan-bit.github.io/status-animarum-1749",
    "achternaam": "",                     # wordt achter 'Gerrit Jan' gezet in de citeerwijze
    "form_url": "https://docs.google.com/forms/d/e/1FAIpQLSeDhnPuMdOucA1lrcOqP5-UFvIKwl2-bu_aB4c4PSp03bxOaA/viewform",
    "form_sleutel": "entry.1080154027",
    "form_tekst": "entry.179589507",
    "csv_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTUAVPU3T2PtGCL34-_W14rzaQOcZNDNwVcTQqfDTTgLNEA1Oi0jRImmr5BEZ1wGFm2O6wxYyc9lOsF/pub?gid=891391070&single=true&output=csv",
    "repo_url": "https://github.com/gerritjan-bit/status-animarum-1749",
    "zoekmachines": True,                 # False = 'noindex' op alle pagina's (proefversie)
    "ga_id": "",                          # Google Analytics-meet-ID (G-…); leeg = geen statistiek
    "fonts_lokaal": True,                 # lettertypen op de eigen site zetten i.p.v. bij Google laden
}
FONTS_URL = ("https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700"
             "&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;1,7..72,400&display=swap")
_FONTS_OK = {"lokaal": False}

def lokale_fonts(uit):
    """Haalt de lettertypen eenmalig op en zet ze in assets/fonts, zodat bezoekers niets bij Google laden."""
    import urllib.request
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
    try:
        css = urllib.request.urlopen(urllib.request.Request(FONTS_URL, headers=ua), timeout=30).read().decode()
        map_ = os.path.join(uit, "assets", "fonts"); os.makedirs(map_, exist_ok=True)
        def haal(m):
            url = m.group(1); naam = url.rsplit("/", 1)[-1]
            data = urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=30).read()
            open(os.path.join(map_, naam), "wb").write(data)
            return f"url(fonts/{naam})"
        css = re.sub(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", haal, css)
        open(os.path.join(uit, "assets", "fonts.css"), "w").write(css)
        return True
    except Exception as ex:
        print("Lettertypen konden niet lokaal worden gezet; de site gebruikt dan systeemletters.", ex)
        return False
TALEN = ["nl", "de", "en"]
TAALNAAM = {"nl": "Nederlands", "de": "Deutsch", "en": "English"}

UI = {
 "nl": dict(privacy="Privacy en cookies", instellingen="Cookie-instellingen", ga_tekst="Mag deze site met Google Analytics bijhouden hoe hij gebruikt wordt? Dat gebeurt alleen als je dat toestaat.", ga_ja="Toestaan", ga_nee="Weigeren",
   zoeken="Zoeken", parochies="Parochies", over="Over deze index", werkwijze="Werkwijze",
   ondertitel="Doorzoek de zielenregisters van het Prinsbisdom Münster",
   paginatitel="Status Animarum Münster 1749/50 – zielenregisters doorzoeken",
   beschrijving="Zoek op naam en geboortejaar in de Status Animarum van het Prinsbisdom Münster (1749/50): {n} parochies, met links naar de scans op Matricula.",
   zoekveld="Naam of woord", zoekknop="Zoeken", fuzzy="Op klank en spelling", exact="Letterlijk",
   streng="Strengheid", gebvan="Geboren ca. van", gebtot="tot", alleboeken="Alle parochies", boek="Parochie",
   laden="Index wordt geladen…", bezig="Bezig met zoeken…", aantal="{n} huishoudens gevonden", een="1 huishouden gevonden",
   teKort="Typ minstens twee letters.", teKortExact="Typ minstens drie tekens.", meer="Meer tonen",
   scan="Scan", details="Personen en oorspronkelijke OCR", kolRel="Relatie", kolNaam="Naam en beschrijving",
   kolLft="Leeftijd", kolGeb="Geb. ca.", ocrOrig="Oorspronkelijke OCR", ocrLas="OCR las", grens="Huishouden begint door",
   verbeter="Verbetering voorstellen", voorstel="Voorstel van een gebruiker, niet gecontroleerd",
   pp_titel="{plaats} – Status Animarum 1749/50",
   pp_beschr="Alle huishoudens uit de Status Animarum van {plaats} (1749/50), doorzoekbaar op naam, met links naar de scans op Matricula.",
   pp_intro="{h} huishoudens op {s} scans. Boek {id} op Matricula Online. Opmaak: {opmaak}.",
   op_lijst="lijst", op_proza="lopende tekst", par_titel="Parochies", par_intro="De index bevat {n} boeken met samen {s} scans en {h} huishoudens uit 1749–1751. Plaatsnamen staan zoals op Matricula.",
   par_kol=("Parochie", "Huishoudens", "Scans", "Opmaak", "Matricula"), werk_titel="Werkwijze",
   werk_intro="Hoe de tekst van de scans is gemaakt en bewerkt. De oorspronkelijke OCR is nooit overschreven; elke automatische wijziging is vastgelegd.",
   werk_regels="Naamregels", werk_regels_intro="Systematische OCR-fouten bij veelvoorkomende namen en wat ervan is gemaakt, met het aantal keer dat de regel is toegepast.",
   werk_kol=("OCR las", "Verbeterd tot", "Soort fout", "Toegepast"), aantallen="Aantallen", meting="Gemeten", versie="versie",
   voet="Bron: Bistumsarchiv Münster, via Matricula Online. Deze site bevat geen scans, alleen met OCR gelezen tekst.",
   noscript="Voor het zoeken is JavaScript nodig. Alle huishoudens staan ook per parochie op de pagina Parochies."),
 "de": dict(privacy="Datenschutz und Cookies", instellingen="Cookie-Einstellungen", ga_tekst="Darf diese Website mit Google Analytics erfassen, wie sie genutzt wird? Das geschieht nur mit Ihrer Zustimmung.", ga_ja="Zulassen", ga_nee="Ablehnen",
   zoeken="Suche", parochies="Kirchspiele", over="Über diesen Index", werkwijze="Arbeitsweise",
   ondertitel="Die Seelenregister des Fürstbistums Münster durchsuchen",
   paginatitel="Status Animarum Münster 1749/50 – Seelenregister durchsuchen",
   beschrijving="Suche nach Namen und Geburtsjahr im Status Animarum des Fürstbistums Münster (1749/50): {n} Kirchspiele, mit Links zu den Scans bei Matricula.",
   zoekveld="Name oder Wort", zoekknop="Suchen", fuzzy="Nach Klang und Schreibweise", exact="Wörtlich",
   streng="Strenge", gebvan="Geboren ca. von", gebtot="bis", alleboeken="Alle Kirchspiele", boek="Kirchspiel",
   laden="Index wird geladen…", bezig="Suche läuft…", aantal="{n} Haushalte gefunden", een="1 Haushalt gefunden",
   teKort="Bitte mindestens zwei Buchstaben eingeben.", teKortExact="Bitte mindestens drei Zeichen eingeben.", meer="Weitere anzeigen",
   scan="Scan", details="Personen und ursprünglicher OCR-Text", kolRel="Stellung", kolNaam="Name und Beschreibung",
   kolLft="Alter", kolGeb="Geb. ca.", ocrOrig="Ursprünglicher OCR-Text", ocrLas="OCR las", grens="Haushalt beginnt wegen",
   verbeter="Verbesserung vorschlagen", voorstel="Vorschlag eines Nutzers, nicht geprüft",
   pp_titel="{plaats} – Status Animarum 1749/50",
   pp_beschr="Alle Haushalte aus dem Status Animarum von {plaats} (1749/50), durchsuchbar nach Namen, mit Links zu den Scans bei Matricula.",
   pp_intro="{h} Haushalte auf {s} Scans. Band {id} bei Matricula Online. Format: {opmaak}.",
   op_lijst="Liste", op_proza="Fließtext", par_titel="Kirchspiele", par_intro="Der Index enthält {n} Bände mit zusammen {s} Scans und {h} Haushalten aus 1749–1751. Ortsnamen wie bei Matricula.",
   par_kol=("Kirchspiel", "Haushalte", "Scans", "Format", "Matricula"), werk_titel="Arbeitsweise",
   werk_intro="Wie der Text der Scans entstanden ist und bearbeitet wurde. Der ursprüngliche OCR-Text wurde nie überschrieben; jede automatische Änderung ist festgehalten.",
   werk_regels="Namensregeln", werk_regels_intro="Systematische OCR-Fehler bei häufigen Namen und ihre Korrektur, mit der Zahl der Anwendungen.",
   werk_kol=("OCR las", "Korrigiert zu", "Art des Fehlers", "Angewendet"), aantallen="Zahlen", meting="Gemessen", versie="Version",
   voet="Quelle: Bistumsarchiv Münster, über Matricula Online. Diese Website enthält keine Scans, nur per OCR erkannten Text.",
   noscript="Für die Suche ist JavaScript nötig. Alle Haushalte stehen auch je Kirchspiel auf der Seite Kirchspiele."),
 "en": dict(privacy="Privacy and cookies", instellingen="Cookie settings", ga_tekst="May this site use Google Analytics to see how it is used? This only happens if you allow it.", ga_ja="Allow", ga_nee="Decline",
   zoeken="Search", parochies="Parishes", over="About this index", werkwijze="Method",
   ondertitel="Search the 1749/50 census of souls of the Prince-Bishopric of Münster",
   paginatitel="Status Animarum Münster 1749/50 – search the census of souls",
   beschrijving="Search the Status Animarum of the Prince-Bishopric of Münster (1749/50) by name and year of birth: {n} parishes, with links to the scans on Matricula.",
   zoekveld="Name or word", zoekknop="Search", fuzzy="By sound and spelling", exact="Exact",
   streng="Strictness", gebvan="Born c. from", gebtot="to", alleboeken="All parishes", boek="Parish",
   laden="Loading the index…", bezig="Searching…", aantal="{n} households found", een="1 household found",
   teKort="Type at least two letters.", teKortExact="Type at least three characters.", meer="Show more",
   scan="Scan", details="People and original OCR", kolRel="Relationship", kolNaam="Name and description",
   kolLft="Age", kolGeb="Born c.", ocrOrig="Original OCR", ocrLas="OCR read", grens="Household starts because of",
   verbeter="Suggest a correction", voorstel="Suggestion by a user, not checked",
   pp_titel="{plaats} – Status Animarum 1749/50",
   pp_beschr="All households in the Status Animarum of {plaats} (1749/50), searchable by name, with links to the scans on Matricula.",
   pp_intro="{h} households on {s} scans. Volume {id} on Matricula Online. Layout: {opmaak}.",
   op_lijst="list", op_proza="running text", par_titel="Parishes", par_intro="The index contains {n} volumes with {s} scans and {h} households from 1749–1751. Place names as on Matricula.",
   par_kol=("Parish", "Households", "Scans", "Layout", "Matricula"), werk_titel="Method",
   werk_intro="How the text of the scans was made and processed. The original OCR was never overwritten; every automatic change is recorded.",
   werk_regels="Name rules", werk_regels_intro="Systematic OCR errors in common names and what they were corrected to, with the number of times each rule was applied.",
   werk_kol=("OCR read", "Corrected to", "Type of error", "Applied"), aantallen="Counts", meting="Measured", versie="version",
   voet="Source: Bistumsarchiv Münster, via Matricula Online. This site contains no scans, only OCR text.",
   noscript="Searching needs JavaScript. All households are also listed per parish on the Parishes page."),
}
REDEN = {
 "nl": dict(witregel="witregel", kort="korte regel die op een leeftijd eindigt", begin="begin van de pagina",
            kolom="volgende kolom op de pagina", kopwoord="regel begint met '{w}'", rol="rol '{w}'"),
 "de": dict(witregel="Leerzeile", kort="kurze Zeile, die mit einem Alter endet", begin="Seitenanfang",
            kolom="nächste Spalte auf der Seite", kopwoord="Zeile beginnt mit ‚{w}‘", rol="Rolle ‚{w}‘"),
 "en": dict(witregel="blank line", kort="short line ending in an age", begin="start of the page",
            kolom="next column on the page", kopwoord="line starts with '{w}'", rol="role '{w}'"),
}
LAAG = {"nl": {"naamregel": "naamregel", "één teken": "één teken", "cijfer": "cijfer"},
        "de": {"naamregel": "Namensregel", "één teken": "ein Zeichen", "cijfer": "Ziffer"},
        "en": {"naamregel": "name rule", "één teken": "one character", "cijfer": "digit"}}
REL = {  # relatie (zoals opgeslagen) -> de, en
 "hoofd": ("Haushaltsvorstand", "head"), "huisgenoot (relatie niet vermeld)": ("Hausgenosse (Stellung nicht angegeben)", "household member (relationship not stated)"),
 "echtgenote": ("Ehefrau", "wife"), "echtgenoot": ("Ehemann", "husband"), "zoon": ("Sohn", "son"), "dochter": ("Tochter", "daughter"),
 "kind": ("Kind", "child"), "kinderen": ("Kinder", "children"), "dochters": ("Töchter", "daughters"), "zoontje": ("Söhnchen", "little son"),
 "dochtertje": ("Töchterchen", "little daughter"), "vader": ("Vater", "father"), "moeder": ("Mutter", "mother"), "broer": ("Bruder", "brother"),
 "zus": ("Schwester", "sister"), "grootvader": ("Großvater", "grandfather"), "grootmoeder": ("Großmutter", "grandmother"),
 "kleinzoon/neef": ("Enkel/Neffe", "grandson/nephew"), "kleindochter/nicht": ("Enkelin/Nichte", "granddaughter/niece"),
 "schoonmoeder": ("Schwiegermutter", "mother-in-law"), "schoonvader": ("Schwiegervater", "father-in-law"), "schoonzoon": ("Schwiegersohn", "son-in-law"),
 "schoondochter": ("Schwiegertochter", "daughter-in-law"), "stiefzoon": ("Stiefsohn", "stepson"), "stiefdochter": ("Stieftochter", "stepdaughter"),
 "dienstmeid": ("Magd", "maid"), "knecht": ("Knecht", "farmhand"), "dienstpersoneel": ("Gesinde", "servant"), "koeherder": ("Kuhhirte", "cowherd"),
 "herder": ("Hirte", "herdsman"), "weduwe": ("Witwe", "widow"), "weduwnaar": ("Witwer", "widower"), "inwoner": ("Einwohner", "lodger"),
 "inwoners": ("Einwohner", "lodgers"), "inwoonster": ("Einwohnerin", "lodger"), "tante": ("Tante", "aunt"), "echtpaar": ("Eheleute", "married couple"),
}
NAV = [("index.html", "zoeken"), ("parochies.html", "parochies"), ("over.html", "over"), ("werkwijze.html", "werkwijze")]

# vertalingen van de logboekteksten (de Nederlandse staan in de database)
STAP_VERTALING = {
 "1": {"de": ("Haushalte gliedern", "Die Haushalte wurden aus den Zeilen der OCR bestimmt. Ein Haushalt endet bei einer Leerzeile, bei einer Zeile, die deutlich kürzer als die volle Zeilenbreite ist und mit einem Alter endet (die Schreibmaschine gibt jedem Buchstaben gleich viel Raum, also entspricht die Zeilenlänge der Breite), oder wenn die nächste Zeile mit einem Wort beginnt, das einen Haushalt eröffnet (colonus, vidua, Kötter, incolae, …). Nie nach einer Zeile, die mit einem Komma oder Trennstrich endet. Folio- und Buchstabenköpfe werden übersprungen. Bei Bänden mit einer Person je Zeile (Spalten-OCR aus Schritt 3) beginnt ein Haushalt an einer Leerzeile oder bei einer Stellung, die kein Familienmitglied und kein Gesinde ist (Beruf, Einwohner, colonus, vidua …); Zeilen nur mit Störzeichen werden vorher entfernt.",
              "Geprüft an zwei zufälligen Seiten ohne Leerzeilen: Warendorf (SAA_WadM, Seite 13) alle Grenzen im geprüften Teil richtig; Greven (SAA_GreM, Seite 9) bis auf wenige richtig. Bekannte Schwäche: Ein Haushalt, dessen letzte Zeile zufällig die volle Breite hat, wird nicht vom nächsten getrennt. Listenbände (nach Schritt 3) neben den Scan gelegt: Sendenhorst AS_019 16 von 19 Haushalten richtig; Osterwick AS_009, wo der Schatten des Buchrückens viel Störung erzeugte, etwa 7 von 10; Harsewinkel und Beckum in den geprüften Teilen richtig."),
       "en": ("Dividing into households", "Households were determined from the OCR lines. A household ends at a blank line, at a line clearly shorter than the full line width that ends in an age (the typewriter gives every letter the same space, so line length equals width), or when the next line starts with a word that opens a household (colonus, vidua, Kötter, incolae, …). Never after a line ending in a comma or hyphen. Folio and letter headings are skipped. For volumes with one person per line (column OCR from step 3) a household starts at a blank line or at a position that is not a family member or servant (occupation, Einwohner, colonus, vidua …); lines containing only noise are removed first.",
              "Checked on two random pages without blank lines: Warendorf (SAA_WadM, page 13) all boundaries in the checked part correct; Greven (SAA_GreM, page 9) all but a few correct. Known weakness: a household whose last line happens to fill the full width is not separated from the next. List volumes (after step 3) checked against the scan: Sendenhorst AS_019 16 of 19 households correct; Osterwick AS_009, where the shadow of the spine caused much noise, about 7 of 10; Harsewinkel and Beckum correct in the parts checked.")},
 "2": {"de": ("OCR-Korrektur", "Automatische Korrektur in drei Schichten; der ursprüngliche OCR-Text bleibt immer erhalten. (1) Namensregeln: systematische Fehler am Anfang häufiger Namen, vor allem durch hochgestellt getippte Großbuchstaben (‚laria‘ → ‚Maria‘, ‚Pernardus‘ → ‚Bernardus‘, ‚enricus‘ → ‚Henricus‘); siehe die Tabelle unten. (2) Ein Zeichen: Ein seltenes Wort wird durch ein viel häufigeres ersetzt, wenn der Unterschied eine bekannte OCR-Verwechslung ist; e↔a bewusst ausgeschlossen wegen echter Varianten (Anne/Anna). (3) Störzeichen (|, », ^) entfernt und Ziffernfehler behoben (4C → 40, ll → 11).",
              "An zwei von Hand abgeschriebenen Seiten: Sendenhorst AS_019 von 80 % auf 87 % richtige Wörter, Ahaus AS_001 von 92 % auf 94 %. Bei einer Zufallsprüfung von 70 Namensregel-Korrekturen fast alle richtig; von 70 Ein-Zeichen-Korrekturen etwa jede siebte zweifelhaft oder falsch (z. B. ‚GroBe‘ → ‚Grote‘ statt ‚Große‘). Auch Schreibweisen der Abschrift selbst können ‚verbessert‘ werden (‚Hennricus‘ → ‚Henricus‘)."),
       "en": ("OCR correction", "Automatic correction in three layers; the original OCR is always kept. (1) Name rules: systematic errors at the start of common names, mostly caused by capital letters typed slightly raised ('laria' → 'Maria', 'Pernardus' → 'Bernardus', 'enricus' → 'Henricus'); see the table below. (2) One character: a rare word is replaced by a much more frequent one if the difference is a known OCR confusion; e↔a deliberately excluded because of genuine variants (Anne/Anna). (3) Stray characters (|, », ^) removed and digit errors fixed (4C → 40, ll → 11).",
              "On two pages transcribed by hand: Sendenhorst AS_019 from 80% to 87% correct words, Ahaus AS_001 from 92% to 94%. In a random check of 70 name-rule corrections almost all were right; of 70 one-character corrections about one in seven was doubtful or wrong (e.g. 'GroBe' → 'Grote' where 'Große' was meant). Spellings of the typist can also be 'corrected' ('Hennricus' → 'Henricus').")},
 "4": {"de": ("Vorschläge von Nutzern", "Verbesserungen, die Besucher über das Formular eingesandt haben, aus dem öffentlichen Tabellenblatt geholt. Sie werden neben dem Text als Nutzervorschlag angezeigt und sind nicht geprüft; der ursprüngliche OCR-Text und die automatische Korrektur bleiben unverändert. Je Haushalt gilt der neueste Vorschlag.", None),
       "en": ("Suggestions by users", "Corrections sent in by visitors through the form, taken from the public tab of the Google Sheet. They are shown next to the text as a user suggestion and have not been checked; the original OCR and the automatic correction stay unchanged. For each household the newest suggestion applies.", None)},
 "3": {"de": ("Spalten-OCR der Listenbände", "Bände mit einer Person je Zeile wurden spaltenweise neu gelesen: Die Spalten werden an senkrechtem Weißraum erkannt, jede Spalte wird einzeln gelesen und die Zeilen werden nach ihrer Höhe auf der Seite wieder zusammengesetzt. Die Spalte mit dem meisten Text ist der Name, links davon die Stellung, die erste Spalte rechts mit überwiegend Zahlen das Alter, der Rest Bemerkungen. Zwei Listen nebeneinander (oder eine Doppelseite) werden als zwei Blöcke gelesen. Ein Haushalt beginnt bei einer Leerzeile oder bei einer Stellung, die kein Familienmitglied und kein Gesinde ist (Beruf, Einwohner, colonus, …). Zeilen, die nur Störzeichen enthalten (etwa vom Schatten des Buchrückens), werden vorher entfernt.",
              "Getestet an 8 Stichprobenseiten verschiedener Listenbände; Spalten bei 7 richtig erkannt (Lüdinghausen Seite 4 ist anders aufgebaut). Auf einer von Hand abgeschriebenen Seite aus Sendenhorst (AS_019): 150 von 183 Wörtern in Namens- und Altersspalte richtig, und die Stellungsspalte (Ehefrau, Kinder, …) großenteils lesbar, die bei normaler OCR unbrauchbar war."),
       "en": ("Column OCR of the list volumes", "Volumes with one person per line were re-read column by column: columns are found from vertical white space, each column is read separately, and the lines are reassembled by their height on the page. The column with the most text is the name, to its left the position in the household, the first column to the right with mostly numbers the age, the rest remarks. Two lists side by side (or a double page) are read as two blocks. A household starts at a blank line or at a position that is not a family member or servant (occupation, Einwohner, colonus, …). Lines containing only noise (for instance from the shadow of the spine) are removed first.",
              "Tested on 8 sample pages from different list volumes; columns recognised correctly on 7 (Lüdinghausen page 4 has a different structure). On a page from Sendenhorst transcribed by hand (AS_019): 150 of 183 words in the name and age columns correct, and the position column (Ehefrau, Kinder, …) largely readable, where ordinary OCR made it unusable.")},
}
SOORT_VERTALING = [  # (patroon in de database, de, en)
    (r"^(\S+) gelezen als (\S+)$", r"\1 gelesen als \2", r"\1 read as \2"),
    (r"^beginletter weggevallen$", "Anfangsbuchstabe fehlt", "initial letter missing"),
    (r"^hoofdletter gelezen als kleine letter$", "Großbuchstabe als Kleinbuchstabe gelesen", "capital read as lower case"),
    (r"^handmatig:.*$", "manuell: kommt hier nur als OCR-Fehler vor", "manual: occurs here only as an OCR error"),
]
AANTAL_LABEL = {
 "huishoudens": ("huishoudens", "Haushalte", "households"), "witregel": ("grens bij witregel", "Grenze an Leerzeile", "boundary at blank line"),
 "korte regel eindigend op een leeftijd": ("grens bij korte regel", "Grenze an kurzer Zeile", "boundary at short line"),
 "volgende regel begint met": ("grens bij beginwoord", "Grenze an Anfangswort", "boundary at opening word"),
 "begin van de pagina": ("begin van een pagina", "Seitenanfang", "start of a page"), "rol": ("grens bij rol (lijstboeken)", "Grenze an Stellung (Listenbände)", "boundary at position (list volumes)"),
 "volgende kolom op de pagina": ("volgende kolom", "nächste Spalte", "next column"),
 "naamregel": ("naamregels toegepast", "Namensregeln angewendet", "name rules applied"), "één teken": ("correcties van één teken", "Ein-Zeichen-Korrekturen", "one-character corrections"),
 "cijfer": ("cijferfouten hersteld", "Ziffernfehler behoben", "digit errors fixed"), "rommelteken": ("rommeltekens verwijderd", "Störzeichen entfernt", "stray characters removed"),
 "paginas_kolom_ocr": ("pagina's per kolom gelezen", "Seiten spaltenweise gelesen", "pages read by column"),
 "voorstellen": ("voorstellen", "Vorschläge", "suggestions"), "huishoudens_met_voorstel": ("huishoudens met een voorstel", "Haushalte mit Vorschlag", "households with a suggestion"),
 "bron": ("bron", "Quelle", "source"),
}

PRIVACY = {
 "nl": """Deze site staat op GitHub Pages. GitHub verwerkt daarbij technische gegevens zoals je IP-adres om de pagina's te kunnen leveren (zie de [privacyverklaring van GitHub](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement)). De lettertypen staan op de site zelf; daarvoor wordt niets bij Google geladen.

**Verbeteringen van bezoekers.** Om recente verbeteringsvoorstellen te tonen, haalt de pagina een openbare tabel op bij Google (docs.google.com). Daarbij ziet Google je IP-adres. Wie zelf een verbetering instuurt, gebruikt een Google-formulier; wat je daar invult, komt bij de beheerder van deze site terecht. Je e-mailadres en toelichting worden nooit gepubliceerd.

{ga}

Vragen? Via de [GitHub-repository]({repo}/issues).""",
 "de": """Diese Website liegt bei GitHub Pages. GitHub verarbeitet dabei technische Daten wie Ihre IP-Adresse, um die Seiten auszuliefern (siehe die [Datenschutzerklärung von GitHub](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement)). Die Schriftarten liegen auf der Website selbst; dafür wird nichts bei Google geladen.

**Verbesserungen von Besuchern.** Um aktuelle Verbesserungsvorschläge anzuzeigen, lädt die Seite eine öffentliche Tabelle bei Google (docs.google.com). Dabei sieht Google Ihre IP-Adresse. Wer selbst eine Verbesserung einsendet, nutzt ein Google-Formular; was Sie dort eingeben, erhält der Betreiber dieser Website. E-Mail-Adresse und Anmerkung werden nie veröffentlicht.

{ga}

Fragen? Über das [GitHub-Repository]({repo}/issues).""",
 "en": """This site is hosted on GitHub Pages. GitHub processes technical data such as your IP address to deliver the pages (see the [GitHub privacy statement](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement)). The fonts are stored on the site itself; nothing is loaded from Google for them.

**Corrections by visitors.** To show recent correction suggestions, the page loads a public table from Google (docs.google.com). Google can see your IP address when this happens. If you send in a correction yourself, you use a Google form; what you enter there goes to the maintainer of this site. Your email address and note are never published.

{ga}

Questions? Via the [GitHub repository]({repo}/issues).""",
}
PRIVACY_GA = {
 "nl": """**Bezoekersstatistiek.** Alleen als je daar toestemming voor geeft, gebruikt deze site Google Analytics om te zien hoeveel mensen de site bezoeken, welke pagina's ze bekijken en waarop gezocht wordt. Google Analytics zet daarvoor cookies. Advertentiefuncties en Google-signalen staan uit, en Google slaat geen IP-adressen op. Google (Google Ireland Ltd.) kan gegevens ook in de Verenigde Staten verwerken; Google valt onder het EU-VS Data Privacy Framework. De gegevens worden na 2 maanden verwijderd. Zonder toestemming wordt Google Analytics niet geladen. Je kunt je keuze altijd wijzigen met de knop hieronder of onderaan elke pagina.""",
 "de": """**Besucherstatistik.** Nur wenn Sie zustimmen, nutzt diese Website Google Analytics, um zu sehen, wie viele Menschen die Seite besuchen, welche Seiten sie ansehen und wonach gesucht wird. Google Analytics setzt dafür Cookies. Werbefunktionen und Google-Signale sind ausgeschaltet, und Google speichert keine IP-Adressen. Google (Google Ireland Ltd.) kann Daten auch in den USA verarbeiten; Google ist nach dem EU-US Data Privacy Framework zertifiziert. Die Daten werden nach 2 Monaten gelöscht. Ohne Ihre Zustimmung wird Google Analytics nicht geladen. Sie können Ihre Entscheidung jederzeit mit der Schaltfläche unten oder am Fuß jeder Seite ändern.""",
 "en": """**Visitor statistics.** Only if you give permission does this site use Google Analytics to see how many people visit, which pages they view and what they search for. Google Analytics sets cookies for this. Advertising features and Google signals are switched off, and Google does not store IP addresses. Google (Google Ireland Ltd.) may also process data in the United States; Google is certified under the EU-US Data Privacy Framework. The data is deleted after 2 months. Without your permission Google Analytics is not loaded. You can change your choice at any time with the button below or at the foot of every page.""",
}

def e(s):
    return html.escape("" if s is None else str(s), quote=True)

def getal(n, taal):
    s = f"{n:,}"
    return s.replace(",", ".") if taal in ("nl", "de") else s

def rel_label(rel, taal):
    if taal == "nl" or rel not in REL:
        return rel
    return REL[rel][0 if taal == "de" else 1]

def reden_label(r, taal):
    R = REDEN[taal]
    if not r: return ""
    if r == "witregel": return R["witregel"]
    if r == "korte regel eindigend op een leeftijd": return R["kort"]
    if r == "begin van de pagina": return R["begin"]
    if r == "volgende kolom op de pagina": return R["kolom"]
    m = re.match(r"^volgende regel begint met '(.*)'$", r)
    if m: return R["kopwoord"].replace("{w}", m.group(1))
    m = re.match(r"^rol '(.*)' opent een huishouden$", r)
    if m: return R["rol"].replace("{w}", m.group(1))
    return r

def plaatsnaam(titel):
    return re.sub(r":\s*Status Animarum.*$", "", titel or "").strip()

# ------------------------------------------------------------------ gegevens
def lees_db(pad, alleen=None):
    db = sqlite3.connect(pad)
    boeken = []
    for bid, titel, url, opmaak in db.execute("SELECT boek_id, titel, basis_url, opmaak FROM boeken ORDER BY boek_id"):
        if alleen and bid not in alleen:
            continue
        labels = {pg: l for pg, l in db.execute("SELECT pg, label FROM paginas WHERE boek_id=?", (bid,))}
        boeken.append({"id": bid, "titel": titel, "plaats": plaatsnaam(titel), "url": url, "opmaak": opmaak or "proza",
                       "labels": labels, "scans": len(labels)})
    boeken.sort(key=lambda b: b["plaats"].lower().replace("(alt) ", ""))
    per_boek = defaultdict(list)
    ids = {b["id"] for b in boeken}
    hh_ids = {}
    for hid, sleutel, bid, pg, nr, tekst, ocr, reden in db.execute(
            "SELECT id, sleutel, boek_id, pg, nr, tekst, tekst_ocr, begin_reden FROM huishoudens ORDER BY boek_id, pg, nr"):
        if bid in ids:
            per_boek[bid].append([sleutel, pg, tekst or "", ocr or "", [], [], reden])
            hh_ids[hid] = (bid, len(per_boek[bid]) - 1)
    for hid, pos, ocr, laag in db.execute("SELECT huishouden_id, positie, ocr, laag FROM correcties "
                                          "WHERE laag != 'rommelteken' AND positie IS NOT NULL"):
        if hid in hh_ids:
            b, i = hh_ids[hid]; per_boek[b][i][4].append([pos, ocr, laag])
    for hid, rel, tekst, lft, geb in db.execute("SELECT huishouden_id, relatie, tekst, leeftijd, geb_ca FROM personen "
                                                "ORDER BY huishouden_id, volgnr"):
        if hid in hh_ids:
            b, i = hh_ids[hid]; per_boek[b][i][5].append([rel, tekst, lft, geb])
    if db.execute("SELECT name FROM sqlite_master WHERE name='gebruikerscorrecties'").fetchone():
        laatste = {}
        for sleutel, tekst in db.execute("SELECT sleutel, tekst FROM gebruikerscorrecties ORDER BY volgnr"):
            laatste[sleutel] = tekst                       # nieuwste (onderaan in de Sheet) wint
        for b, lijst in per_boek.items():
            for h in lijst:
                v = laatste.get(h[0])
                if v and v.strip() not in (h[2].strip(), h[3].strip()):
                    h.append(v.strip())
    bewerkingen = db.execute("SELECT stap, versie, beschrijving, aantallen, meting, datum FROM bewerkingen "
                             "WHERE id IN (SELECT MAX(id) FROM bewerkingen GROUP BY stap) ORDER BY stap").fetchall() \
        if db.execute("SELECT name FROM sqlite_master WHERE name='bewerkingen'").fetchone() else []
    regels = db.execute("SELECT ocr_vorm, verbeterd, soort, aantal FROM regels WHERE aantal > 0 ORDER BY aantal DESC").fetchall() \
        if db.execute("SELECT name FROM sqlite_master WHERE name='regels'").fetchone() else []
    return boeken, per_boek, bewerkingen, regels

def maak_index(boeken, per_boek):
    """Woordenlijst (kleine letters) met per woord de huishoudens; plus per huishouden boek en geboortejaren."""
    woorden = {}; post = []; h_ref = []; geb = []
    for k, b in enumerate(boeken):
        for i, h in enumerate(per_boek[b["id"]]):
            n = len(h_ref); h_ref.append([k, i])
            geb.append(sorted({p[3] for p in h[5] if p[3] is not None}))
            for w in set(re.findall(r"[^\W\d_]{2,}", (h[2] + " " + h[3] + " " + (h[7] if len(h) > 7 else "")).lower())):
                if w not in woorden:
                    woorden[w] = len(post); post.append([])
                post[woorden[w]].append(n)
    return {"w": list(woorden), "p": post, "h": h_ref, "g": geb}

# ------------------------------------------------------------------ html
def kop_html(taal, titel, beschrijving, pad, diepte, actief, extra=""):
    basis = "../" * diepte
    alt = "".join(f'<link rel="alternate" hreflang="{t}" href="{CONFIG["basis_url"]}/{t}/{pad}">' for t in TALEN)
    alt += f'<link rel="alternate" hreflang="x-default" href="{CONFIG["basis_url"]}/en/{pad}">'
    nav = "".join(f'<li><a href="{basis}{taal}/{href}"{" aria-current=\"page\"" if sleutel == actief else ""}>{e(UI[taal][sleutel])}</a></li>'
                  for href, sleutel in NAV)
    talen = "".join(f'<a href="{basis}{t}/{pad}" lang="{t}" hreflang="{t}"{" aria-current=\"true\"" if t == taal else ""}>{t.upper()}</a>' for t in TALEN)
    robots = "" if CONFIG["zoekmachines"] else '<meta name="robots" content="noindex">'
    fonts = (f'<link rel="stylesheet" href="{basis}assets/fonts.css">' if _FONTS_OK["lokaal"] else
             '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             f'<link href="{FONTS_URL}" rel="stylesheet">') if CONFIG["fonts_lokaal"] is not None else ""
    analyse = ""
    if CONFIG["ga_id"]:
        U = UI[taal]
        cfg = {"id": CONFIG["ga_id"], "t": {"tekst": U["ga_tekst"], "ja": U["ga_ja"], "nee": U["ga_nee"],
                                             "meer": U["privacy"], "privacy": f"{basis}{taal}/privacy.html"}}
        analyse = f'<script>window.SA_ANALYSE={json.dumps(cfg, ensure_ascii=False)};</script><script src="{basis}assets/analyse.js" defer></script>\n'
    return f"""<!DOCTYPE html>
<html lang="{taal}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titel)}</title>
<meta name="description" content="{e(beschrijving)}">
{robots}<link rel="canonical" href="{CONFIG["basis_url"]}/{taal}/{pad}">
{alt}
{fonts}
<link rel="stylesheet" href="{basis}assets/stijl.css">
{analyse}{extra}</head>
<body>
<header class="kop"><div class="kop-binnen">
<a class="merk" href="{basis}{taal}/index.html"><span>Status Animarum</span> Münster 1749/50</a>
<nav aria-label="{e(UI[taal]['zoeken'])}"><ul>{nav}</ul></nav>
<div class="talen">{talen}</div>
</div></header>
"""

def voet_html(taal, diepte=1):
    basis = "../" * diepte
    inst = f' · <a href="#" data-sa-instellingen>{e(UI[taal]["instellingen"])}</a>' if CONFIG["ga_id"] else ""
    return (f'<footer class="voet"><div>{e(UI[taal]["voet"])} <a href="{CONFIG["repo_url"]}">GitHub</a> · '
            f'<a href="{basis}{taal}/privacy.html">{e(UI[taal]["privacy"])}</a>{inst}</div></footer>\n</body>\n</html>\n')

def sa_script(taal, diepte, pagina):
    U = UI[taal]
    cfg = {"taal": taal, "basis": "../" * diepte, "pagina": pagina, "csv": CONFIG["csv_url"],
           "form": {"url": CONFIG["form_url"], "sleutel": CONFIG["form_sleutel"], "tekst": CONFIG["form_tekst"]},
           "ui": {k: U[k] for k in ("laden", "bezig", "aantal", "een", "teKort", "teKortExact", "meer", "scan", "details",
                                     "kolRel", "kolNaam", "kolLft", "kolGeb", "ocrOrig", "ocrLas", "grens", "verbeter", "voorstel")}}
    cfg["ui"]["reden"] = REDEN[taal]; cfg["ui"]["laag"] = LAAG[taal]
    cfg["ui"]["rel"] = {k: rel_label(k, taal) for k in REL}
    return f'<script>window.SA={json.dumps(cfg, ensure_ascii=False)};</script>\n<script src="{"../" * diepte}assets/zoek.js" defer></script>\n'

def hh_html(h, boek, taal, toon_plaats):
    """Statische weergave voor de parochiepagina's: de tekst staat in de HTML (vindbaar voor
    zoekmachines); personen en oorspronkelijke OCR worden pas geladen als je ze openklapt."""
    U = UI[taal]
    sleutel, pg, tekst, ocr, corr, pers, reden = h[:7]
    cmap = {p: (o, l) for p, o, l in corr}
    toks = []
    for i, tok in enumerate(tekst.split(" ")):
        t = e(tok)
        if i in cmap:
            t = f'<u title="{e(U["ocrLas"] + ": " + cmap[i][0] + " (" + LAAG[taal].get(cmap[i][1], cmap[i][1]) + ")")}">{t}</u>'
        toks.append(t)
    voorstel = f'<div class="voorstel"><span class="label">{e(U["voorstel"])}</span>{e(h[7])}</div>' if len(h) > 7 else ""
    return (f'<article class="hh" id="{e(sleutel)}" data-sleutel="{e(sleutel)}">'
            f'<p class="hh-tekst">{" ".join(toks)}</p>{voorstel}'
            f'<details data-laad><summary>{e(U["details"])}</summary></details>'
            f'<p class="verbeter klein">{e(sleutel)} · <a class="verbeterlink" href="#" target="_blank" rel="noopener">{e(U["verbeter"])}</a></p></article>\n')

def lees_teksten(taal, vars_):
    t = open(os.path.join(HIER, "teksten", f"{taal}.md"), encoding="utf-8").read()
    for k, v in vars_.items():
        t = t.replace("{" + k + "}", str(v))
    delen = {}
    for m in re.finditer(r"^## (\w+)\n(.*?)(?=^## |\Z)", t, re.S | re.M):
        delen[m.group(1)] = markdown.markdown(m.group(2).strip())
    return delen

# ------------------------------------------------------------------ bouwen
def bouw(db_pad, uit, alleen=None):
    boeken, per_boek, bewerkingen, regels = lees_db(db_pad, alleen)
    if os.path.exists(uit):
        shutil.rmtree(uit)
    os.makedirs(os.path.join(uit, "data", "hh"))
    shutil.copytree(os.path.join(HIER, "assets"), os.path.join(uit, "assets"))
    _FONTS_OK["lokaal"] = bool(CONFIG["fonts_lokaal"]) and lokale_fonts(uit)
    n_hh = sum(len(v) for v in per_boek.values())
    n_scans = sum(b["scans"] for b in boeken)
    n_lijst = sum(1 for b in boeken if b["opmaak"] == "lijst")

    # gegevens voor het zoeken
    json.dump([{"id": b["id"], "plaats": b["plaats"], "url": b["url"], "labels": b["labels"]} for b in boeken],
              open(os.path.join(uit, "data", "boeken.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(maak_index(boeken, per_boek), open(os.path.join(uit, "data", "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    for b in boeken:
        json.dump(per_boek[b["id"]], open(os.path.join(uit, "data", "hh", b["id"] + ".json"), "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))

    pagina_urls = []
    for taal in TALEN:
        U = UI[taal]
        d = os.path.join(uit, taal); os.makedirs(os.path.join(d, "p"))
        vars_ = {"n_boeken": len(boeken), "n_scans": getal(n_scans, taal), "n_huishoudens": getal(n_hh, taal),
                 "n_lijst": n_lijst, "basis_url": CONFIG["basis_url"], "achternaam": CONFIG["achternaam"]}
        tk = lees_teksten(taal, vars_)
        beschr = U["beschrijving"].format(n=len(boeken))

        # zoekpagina = startpagina
        opties = "".join(f'<option value="{k}">{e(b["plaats"])}</option>' for k, b in enumerate(boeken))
        zoek = f"""<main>
<h1><span class="ond">Status Animarum</span> Münster 1749/50</h1>
<p class="ondertitel">{e(U['ondertitel'])}</p>
<div class="tekst">{tk.get('start', '')}</div>
<form class="zoek" id="zoekform" role="search">
<div class="zoekregel"><label class="klein" for="q" hidden>{e(U['zoekveld'])}</label>
<input type="search" id="q" name="q" placeholder="{e(U['zoekveld'])}" autocomplete="off" aria-label="{e(U['zoekveld'])}">
<button type="submit">{e(U['zoekknop'])}</button></div>
<div class="opties">
<label><input type="radio" name="modus" id="fuzzy" checked> {e(U['fuzzy'])}</label>
<label><input type="radio" name="modus" id="exact"> {e(U['exact'])}</label>
<label id="drempelvak">{e(U['streng'])} <input type="range" id="drempel" min="60" max="100" value="85"> <span id="drempelwaarde">85</span></label>
<span class="geb"><label>{e(U['gebvan'])} <input type="number" id="gebvan" min="1630" max="1751" inputmode="numeric"></label>
<label>{e(U['gebtot'])} <input type="number" id="gebtot" min="1630" max="1751" inputmode="numeric"></label></span>
<label>{e(U['boek'])} <select id="boek"><option value="">{e(U['alleboeken'])}</option></select></label>
</div>
</form>
<noscript><p>{e(U['noscript'])}</p></noscript>
<p class="status" id="status" role="status" aria-live="polite"></p>
<div id="uitkomst"></div>
</main>
"""
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(
            kop_html(taal, U["paginatitel"], beschr, "index.html", 1, "zoeken") + zoek + sa_script(taal, 1, "zoeken") + voet_html(taal))
        pagina_urls.append("index.html")

        # over deze index
        over = f'<main class="tekst">\n<h1>{e(U["over"])}</h1>\n{tk.get("over", "")}\n</main>\n'
        open(os.path.join(d, "over.html"), "w", encoding="utf-8").write(
            kop_html(taal, f'{U["over"]} – Status Animarum Münster 1749/50', beschr, "over.html", 1, "over") + over + voet_html(taal))

        # parochies
        rijen = "".join(
            f'<tr><td><a href="p/{b["id"]}.html">{e(b["plaats"])}</a></td><td class="getal">{getal(len(per_boek[b["id"]]), taal)}</td>'
            f'<td class="getal">{b["scans"]}</td><td>{e(U["op_lijst"] if b["opmaak"] == "lijst" else U["op_proza"])}</td>'
            f'<td><a href="{e(b["url"])}" target="_blank" rel="noopener">{e(b["id"])}</a></td></tr>' for b in boeken)
        k = U["par_kol"]
        par = (f'<main>\n<h1>{e(U["par_titel"])}</h1>\n<p class="tekst">{e(U["par_intro"].format(n=len(boeken), s=getal(n_scans, taal), h=getal(n_hh, taal)))}</p>\n'
               f'<div class="tabel"><table><thead><tr><th>{k[0]}</th><th class="getal">{k[1]}</th><th class="getal">{k[2]}</th><th>{k[3]}</th><th>{k[4]}</th></tr></thead>'
               f'<tbody>{rijen}</tbody></table></div>\n</main>\n')
        open(os.path.join(d, "parochies.html"), "w", encoding="utf-8").write(
            kop_html(taal, f'{U["par_titel"]} – Status Animarum Münster 1749/50', beschr, "parochies.html", 1, "parochies") + par + voet_html(taal))

        # werkwijze
        delen = [f'<main class="tekst">\n<h1>{e(U["werk_titel"])}</h1>\n<p>{e(U["werk_intro"])}</p>\n']
        for stap, versie, beschrijving, aantallen, meting, datum in bewerkingen:
            nr = stap.split(" ")[0]
            naam = stap.split("·", 1)[-1].strip()
            if taal != "nl" and nr in STAP_VERTALING:
                naam, beschrijving, meting = STAP_VERTALING[nr][taal]
            delen.append(f'<h2>{e(nr)}. {e(naam)}</h2>\n<p class="klein">{e(U["versie"])} {e(versie)} · {e((datum or "")[:10])}</p>\n<p>{e(beschrijving)}</p>\n')
            try:
                tel = json.loads(aantallen or "{}")
            except ValueError:
                tel = {}
            if tel:
                regels_t = "".join(f'<tr><td>{e(AANTAL_LABEL.get(a, (a, a, a))[TALEN.index(taal)])}</td><td class="getal">{getal(v, taal) if isinstance(v, int) else e(v)}</td></tr>'
                                   for a, v in tel.items())
                delen.append(f'<h3>{e(U["aantallen"])}</h3>\n<div class="tabel"><table><tbody>{regels_t}</tbody></table></div>\n')
            if meting:
                delen.append(f'<h3>{e(U["meting"])}</h3>\n<p>{e(meting)}</p>\n')
        if regels:
            def soort(s):
                if taal == "nl": return s
                for pat, de, en in SOORT_VERTALING:
                    if re.match(pat, s): return re.sub(pat, de if taal == "de" else en, s)
                return s
            k = U["werk_kol"]
            rij = "".join(f'<tr><td>{e(o)}</td><td>{e(n)}</td><td>{e(soort(s))}</td><td class="getal">{getal(a, taal)}</td></tr>' for o, n, s, a in regels)
            delen.append(f'<h2>{e(U["werk_regels"])}</h2>\n<p>{e(U["werk_regels_intro"])}</p>\n<div class="tabel"><table><thead><tr><th>{k[0]}</th><th>{k[1]}</th><th>{k[2]}</th><th class="getal">{k[3]}</th></tr></thead><tbody>{rij}</tbody></table></div>\n')
        delen.append("</main>\n")
        open(os.path.join(d, "werkwijze.html"), "w", encoding="utf-8").write(
            kop_html(taal, f'{U["werk_titel"]} – Status Animarum Münster 1749/50', beschr, "werkwijze.html", 1, "werkwijze") + "".join(delen) + voet_html(taal))
        if taal == "nl":
            pagina_urls += ["over.html", "parochies.html", "werkwijze.html"]

        # privacy
        prv = PRIVACY[taal].replace("{ga}", PRIVACY_GA[taal] if CONFIG["ga_id"] else "").replace("{repo}", CONFIG["repo_url"])
        open(os.path.join(d, "privacy.html"), "w", encoding="utf-8").write(
            kop_html(taal, f'{U["privacy"]} – Status Animarum Münster 1749/50', beschr, "privacy.html", 1, "")
            + f'<main class="tekst">\n<h1>{e(U["privacy"])}</h1>\n{markdown.markdown(prv)}\n'
            + (f'<p><button type="button" data-sa-instellingen>{e(U["instellingen"])}</button></p>' if CONFIG["ga_id"] else "")
            + '</main>\n' + voet_html(taal))

        # parochiepagina's
        for b in boeken:
            hh = per_boek[b["id"]]
            blok = [f'<main data-boek="{e(b["id"])}">\n<h1>{e(b["plaats"])}</h1>\n<p class="ondertitel">Status Animarum 1749/50</p>\n'
                    f'<p>{e(U["pp_intro"].format(h=getal(len(hh), taal), s=b["scans"], id=b["id"], opmaak=U["op_lijst"] if b["opmaak"] == "lijst" else U["op_proza"])).replace(e(b["id"]), f"<a href=\"{e(b["url"])}\" target=\"_blank\" rel=\"noopener\">{e(b["id"])}</a>", 1)}</p>\n']
            vorige = None
            for h in hh:
                if h[1] != vorige:
                    vorige = h[1]
                    lab = b["labels"].get(h[1], f"pg {h[1]}")
                    blok.append(f'<h2 class="scankop" id="scan-{e(lab)}"><a href="{e(b["url"])}?pg={h[1]}" target="_blank" rel="noopener">{e(U["scan"])} {e(lab)}</a></h2>\n')
                blok.append(hh_html(h, b, taal, False))
            blok.append("</main>\n")
            titel = U["pp_titel"].format(plaats=b["plaats"])
            open(os.path.join(d, "p", b["id"] + ".html"), "w", encoding="utf-8").write(
                kop_html(taal, titel, U["pp_beschr"].format(plaats=b["plaats"]), f'p/{b["id"]}.html', 2, "parochies")
                + "".join(blok) + sa_script(taal, 2, "parochie") + voet_html(taal, 2))
            if taal == "nl":
                pagina_urls.append(f'p/{b["id"]}.html')

    # startpunt: taal kiezen
    talen_links = "".join(f'<li><a href="{t}/index.html" hreflang="{t}" lang="{t}">{TAALNAAM[t]}</a></li>' for t in TALEN)
    alt = "".join(f'<link rel="alternate" hreflang="{t}" href="{CONFIG["basis_url"]}/{t}/index.html">' for t in TALEN)
    robots = "" if CONFIG["zoekmachines"] else '<meta name="robots" content="noindex">'
    open(os.path.join(uit, "index.html"), "w", encoding="utf-8").write(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Status Animarum Münster 1749/50</title>
<meta name="description" content="{e(UI['en']['beschrijving'].format(n=len(boeken)))}">
{robots}{alt}<link rel="alternate" hreflang="x-default" href="{CONFIG['basis_url']}/">
<link rel="stylesheet" href="assets/stijl.css">
<script>(function(){{var l=(navigator.languages||[navigator.language||"en"]).map(function(x){{return x.slice(0,2)}});
for(var i=0;i<l.length;i++){{if(["nl","de","en"].indexOf(l[i])>=0){{location.replace(l[i]+"/index.html");return}}}}location.replace("en/index.html")}})();</script>
</head><body><main><h1><span class="ond">Status Animarum</span> Münster 1749/50</h1><ul>{talen_links}</ul></main></body></html>
""")
    # sitemap en robots.txt
    nu = datetime.date.today().isoformat()
    urls = []
    for p in pagina_urls:
        alts = "".join(f'<xhtml:link rel="alternate" hreflang="{t}" href="{CONFIG["basis_url"]}/{t}/{p}"/>' for t in TALEN)
        for t in TALEN:
            urls.append(f'<url><loc>{CONFIG["basis_url"]}/{t}/{p}</loc><lastmod>{nu}</lastmod>{alts}</url>')
    open(os.path.join(uit, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(urls) + "\n</urlset>\n")
    open(os.path.join(uit, "robots.txt"), "w").write(
        ("User-agent: *\nAllow: /\n" if CONFIG["zoekmachines"] else "User-agent: *\nDisallow: /\n") + f'Sitemap: {CONFIG["basis_url"]}/sitemap.xml\n')
    open(os.path.join(uit, ".nojekyll"), "w").write("")
    return {"boeken": len(boeken), "huishoudens": n_hh, "scans": n_scans}

if __name__ == "__main__":
    db_pad, uit = sys.argv[1], sys.argv[2]
    print(bouw(db_pad, uit, set(sys.argv[3:]) or None))
