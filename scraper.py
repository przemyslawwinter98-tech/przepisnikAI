from __future__ import annotations

import os
import re
import csv
import sys
import json
import time
import warnings
import unicodedata
from urllib.parse import urljoin, urlparse
from datetime import datetime, date
from typing import Optional

warnings.filterwarnings("ignore")

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9",
}

PORTAL_HOMES = [
    "https://www.okazjum.pl/",
    "https://www.ding.pl/",
    "https://gazetkowo.pl/",
    "https://blix.pl/",
]

DIRECT_STORE_SEEDS = {
    "Lidl": [
        "https://blix.pl/sklep/lidl/",
        "https://www.okazjum.pl/lidl",
        "https://www.ding.pl/sklepy/lidl",
        "https://gazetkowo.pl/sklep/lidl",
    ],
    "Biedronka": [
        "https://blix.pl/sklep/biedronka/",
        "https://www.okazjum.pl/biedronka",
        "https://www.ding.pl/sklepy/biedronka",
        "https://gazetkowo.pl/sklep/biedronka",
    ],
    "Netto": [
        "https://blix.pl/sklep/netto/",
        "https://www.okazjum.pl/netto",
        "https://www.ding.pl/sklepy/netto",
        "https://gazetkowo.pl/sklep/netto",
    ],
}

STORES = ["Lidl", "Biedronka", "Netto"]

EXCLUDED_URL_PATTERNS = [
    "/blog", "blog.", "/artykul", "/artykuly", "/poradnik", "/poradniki",
    "/aktualnosci", "/news", "/przepis", "/przepisy", "/ciekawostki",
    "/ranking", "/test-", "/opinie", "/konkurs", "/kontakt", "/regulamin",
    "/polityka", "/o-nas", "/kariera", "/faq", "/godziny-otwarcia", "/sklepy-w-"
]

# ESENCJA KUCHENNA: (czysta_nazwa, kategoria, slowa_kluczowe, wykluczenia, min_cena, max_cena)
CORE_CULINARY_ITEMS = {
    # Mięso i wędliny
    "piers_z_kurczaka": ("Pierś z kurczaka", "Mięso i świeże", ["piers z kurczaka", "filet z kurczaka", "filet z piersi"], ["przypraw", "wedlin", "szynk", "pasztet", "parowk", "kabanos", "panier", "nuggets", "strips", "konserw", "salatk", "karma"], 9.50, 24.00),
    "mieso_mielone": ("Mięso mielone", "Mięso i świeże", ["mieso mielone", "mielone wieprzow", "mielone wolow", "mielone drobiow"], ["przypraw", "fix", "pomysl na", "sos", "pierogi", "krokiety", "nalesniki"], 5.50, 16.00),
    "schab": ("Schab wieprzowy", "Mięso i świeże", ["schab wieprzow", "schab bez kosci", "schab ze"], ["wedlin", "szynk", "pieczon", "wedzon", "konserw"], 10.00, 22.00),
    "karkowka": ("Karkówka wieprzowa", "Mięso i świeże", ["karkowk"], ["wedlin", "szynk", "pieczon", "wedzon"], 10.00, 22.00),
    "kielbasa": ("Kiełbasa śląska", "Mięso i świeże", ["kielbasa slaska", "kielbasa podwawelska", "kielbasa zwyczajna"], ["sucha", "krakowska", "zywiecka", "salami", "kabanos"], 6.00, 24.00),
    "boczek": ("Wędzony boczek", "Mięso i świeże", ["boczek wedzon", "boczek surowy"], ["chips", "chrupk", "przypraw"], 5.00, 32.00),

    # Ryby
    "losos": ("Łosoś filet", "Mięso i świeże", ["losos filet", "filet z lososia", "losos swiezy", "losos atlantycki"], ["salatk", "pasta", "wedzon", "plastr", "karma"], 12.00, 45.00),
    "dorsz": ("Dorsz filet", "Mięso i świeże", ["dorsz", "filet z dorsza"], ["salatk", "pasta", "panier"], 8.00, 38.00),
    "tunczyk": ("Tuńczyk w puszce", "Konserwy i słoiki", ["tunczyk"], ["salatk", "pasta", "karma", "dla kota"], 3.00, 9.00),

    # Nabiał i jaja
    "maslo": ("Masło", "Lodówka i mrożonki", ["maslo ekstra", "maslo polskie", "maslo 82", "maslo 83", "maslo"], ["orzech", "roslinn", "margaryn", "mix", "oselk", "krem", "balsam", "do ciala", "shea", "czekolad"], 3.50, 9.50),
    "mleko": ("Mleko", "Lodówka i mrożonki", ["mleko uht", "mleko swieze", "mleko 3,2", "mleko 2%", "mleko"], ["kokos", "sojow", "owsian", "migdal", "zageszczon", "skondensowan", "w proszku", "czekolad", "do demakijazu", "balsam", "modifikowan", "bebiko", "nan", "ptasie"], 1.80, 4.80),
    "jajka": ("Jajka", "Lodówka i mrożonki", ["jajka", "jaja sciolkow", "jaja z wolnego", "jaja klasa"], ["niespodziank", "czekolad", "makaron", "majonez", "kinder"], 4.50, 14.00),
    "ser_zolty": ("Ser żółty", "Lodówka i mrożonki", ["ser zolty", "ser gouda", "ser edam", "ser morski", "ser ementaler", "gouda"], ["topion", "plesniow", "feta", "twarog", "wiejski", "mascarpone"], 4.00, 29.00),
    "twarog": ("Twaróg", "Lodówka i mrożonki", ["twarog poltlusty", "twarog chudy", "twarog tlusty", "twarog sernikowy", "twarog"], ["deser", "danio", "sernik", "baton"], 2.50, 14.00),
    "serek_wiejski": ("Serek wiejski", "Lodówka i mrożonki", ["serek wiejski"], ["deser"], 1.50, 4.50),
    "jogurt_naturalny": ("Jogurt naturalny", "Lodówka i mrożonki", ["jogurt naturalny", "jogurt grecki"], ["owocow", "pitny", "deser", "stracciatella", "czekolad"], 1.20, 6.00),
    "smietana": ("Śmietana", "Lodówka i mrożonki", ["smietana 18", "smietana 12", "smietanka 30"], ["deser", "spray", "w sprayu"], 1.50, 6.50),
    "mozzarella": ("Mozzarella", "Lodówka i mrożonki", ["mozzarella"], ["paluszki", "panier", "pizza"], 2.00, 7.00),

    # Suche i konserwy
    "ryz": ("Ryż", "Suche i makarony", ["ryz bialy", "ryz basmati", "ryz jasminowy", "ryz parboiled", "ryz w woreczkach"], ["preparowan", "wafle", "mleczn", "deser", "belriso", "muller"], 2.00, 8.00),
    "makaron": ("Makaron", "Suche i makarony", ["makaron penne", "makaron spaghetti", "makaron swiderki", "makaron fusilli", "makaron lubella", "makaron"], ["zupa", "blyskawiczn", "chinski", "kubek"], 2.00, 7.50),
    "kasza": ("Kasza pęczak / gryczana", "Suche i makarony", ["kasza peczak", "kasza gryczana", "kasza jaglana"], ["kaszka", "dla dzieci", "mleczno"], 2.00, 7.50),
    "czerwona_fasola": ("Czerwona fasola", "Konserwy i słoiki", ["fasola czerwona", "czerwona fasola"], ["po bretonsku", "zupa", "salatk"], 2.00, 5.50),
    "biala_fasola": ("Biała fasola", "Konserwy i słoiki", ["fasola biala", "biala fasola"], ["po bretonsku", "zupa"], 2.00, 5.50),
    "kukurydza": ("Kukurydza konserwowa", "Konserwy i słoiki", ["kukurydza konserwowa", "kukurydza zlocista", "kukurydza w puszce"], ["chrupki", "popcorn", "platki"], 2.00, 5.50),
    "passata_pomidorowa": ("Passata pomidorowa", "Konserwy i słoiki", ["passata", "przecier pomidorowy"], ["zupa", "krem"], 2.20, 6.50),
    "pomidory_krojone": ("Pomidory krojone", "Konserwy i słoiki", ["pomidory krojone", "pomidory pelati", "pomidory w puszce"], ["suszone", "zupa"], 2.20, 6.00),

    # Warzywa i owoce
    "ziemniaki": ("Ziemniaki", "Warzywa i owoce", ["ziemniaki"], ["frytki", "chipsy", "placki", "puree", "klusk"], 1.20, 8.00),
    "cebula": ("Cebula", "Warzywa i owoce", ["cebula"], ["prazona", "suszon", "krazki", "zupa"], 1.50, 7.00),
    "czosnek": ("Czosnek", "Warzywa i owoce", ["czosnek"], ["granulowan", "suszon", "sos", "bagietk", "maslo"], 1.20, 6.00),
    "pomidory": ("Pomidory", "Warzywa i owoce", ["pomidory malinowe", "pomidory rzymskie", "pomidory koktajlowe", "pomidory galazka", "pomidory"], ["passata", "koncentrat", "krojone", "suszone", "ketchup", "sok", "zupa"], 3.00, 15.00),
    "papryka": ("Papryka", "Warzywa i owoce", ["papryka czerwona", "papryka zolta", "papryka zielona", "papryka"], ["mielona", "slodka", "ostra", "wedzona", "przypraw", "chipsy"], 4.00, 16.00),
    "ogorek": ("Ogórek", "Warzywa i owoce", ["ogorek zielony", "ogorki gruntowe", "ogorek szklarniowy", "ogorki"], ["kiszon", "konserwow", "salatk"], 2.50, 12.00),
    "marchew": ("Marchew", "Warzywa i owoce", ["marchew", "marchewka"], ["sok", "kubus", "zupa", "groszek z"], 1.50, 6.00),
    "pieczarki": ("Pieczarki", "Warzywa i owoce", ["pieczarki"], ["zupa", "sos", "marynowan"], 3.00, 12.00),
    "brokul": ("Brokuł", "Warzywa i owoce", ["brokul", "brokuly"], ["zupa", "krem"], 3.00, 9.00),
    "kalafior": ("Kalafior", "Warzywa i owoce", ["kalafior"], ["zupa"], 3.50, 10.00),
    "cukinia": ("Cukinia", "Warzywa i owoce", ["cukinia"], ["leczo"], 3.00, 10.00),
    "kapusta": ("Kapusta", "Warzywa i owoce", ["kapusta biala", "kapusta mloda", "kapusta pekinska"], ["kiszona", "zasma"], 2.00, 8.00),
    "banany": ("Banany", "Warzywa i owoce", ["banany"], ["chipsy", "suszon", "jogurt", "deser", "sok"], 2.50, 7.50),
    "jablka": ("Jabłka", "Warzywa i owoce", ["jablka"], ["sok", "mus", "chipsy", "ocet", "cydr", "szarlotk"], 1.80, 6.50),
    "cytryny": ("Cytryny", "Warzywa i owoce", ["cytryny"], ["sok", "herbata", "napoj"], 3.00, 10.00),
    "mandarynki": ("Mandarynki", "Warzywa i owoce", ["mandarynki"], ["puszk", "sok"], 3.50, 10.00),
    "pomarancze": ("Pomarańcze", "Warzywa i owoce", ["pomarancze"], ["sok", "napoj"], 3.50, 10.00),
    "borowki": ("Borówki amerykańskie", "Warzywa i owoce", ["borowki", "borowka amerykanska"], ["jogurt", "dzem", "sok"], 4.00, 14.00),
    "winogrona": ("Winogrona", "Warzywa i owoce", ["winogrona", "winogrono"], ["sok", "wino"], 5.00, 15.00),

    # Tłuszcze
    "oliwa": ("Oliwa z oliwek", "Przyprawy i dodatki", ["oliwa z oliwek"], ["balsam", "krem", "mydlo", "szampon"], 12.00, 38.00),
    "olej": ("Olej rzepakowy", "Przyprawy i dodatki", ["olej rzepakowy", "olej slonecznikowy"], ["silnikow", "do ciala", "olejek"], 4.50, 13.00),
}

EXCLUDED_GLOBAL_NOISE = [
    "blyszczyk", "pomadk", "szmink", "tusz do rzes", "chusteczk", "papier toaletowy",
    "recznik papierowy", "szampon", "zel pod prysznic", "mydlo", "pasta do zebow",
    "proszek", "plyn do", "kapsulki", "karma", "zwirek", "pieluchy", "pampers",
    "czekolad", "baton", "wafel", "ciastk", "cukierk", "zelk", "lody", "lodow",
    "ptasie mleczko", "nutella", "paczek", "donut", "drozdzowk", "chipsy", "chrupki",
    "piwo", "wodka", "wino", "whisky", "likier", "cydr", "cola", "pepsi", "energetyk",
    "zobacz aktualna", "gazetka ", "strona ", "oferta wazna", "wszystkie promocje"
]

def normalize_ascii(text: str) -> str:
    text = str(text or "").lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("ł", "l")

def extract_weight_from_text(text: str) -> Optional[str]:
    """Wyciąga gramaturę / pojemność / liczbę sztuk z tytułu oferty (np. '500 g', '1 kg', '200 g', '10 szt.')."""
    if not text:
        return None
    # Ignorujemy przelicznik ceny za kilogram typu "24,99 zł/kg" lub "/ 1 kg"
    cleaned = re.sub(r"\d+[.,]\d+\s*zł\s*/\s*(?:1\s*)?(?:kg|l|100\s*g)", " ", text, flags=re.I)
    cleaned = re.sub(r"\(\s*\d+[.,]\d+\s*zł\s*/\s*[^)]+\)", " ", cleaned, flags=re.I)

    # Wzorzec wielopaku np. "4 x 100 g"
    m_multi = re.search(r"\b(\d+\s*[x×]\s*\d+(?:[.,]\d+)?\s*(?:kg|g|dag|ml|l))\b", cleaned, re.I)
    if m_multi:
        return re.sub(r"\s+", " ", m_multi.group(1).lower()).replace("×", "x")

    # Standardowa gramatura / objętość / sztuki (np. 400 g, 1 kg, 250 ml, 1,5 l, 10 szt.)
    m_std = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(kg|g|dag|ml|l|szt\.?)\b", cleaned, re.I)
    if m_std:
        num = m_std.group(1).replace(".", ",")
        unit = m_std.group(2).lower().rstrip(".")
        if unit == "szt":
            unit = "szt."
        return f"{num} {unit}"

    return None

def is_valid_leaflet_url(url: str, store_slug: str, link_text: str = "") -> bool:
    low_url = normalize_ascii(url)
    low_txt = normalize_ascii(link_text)
    if any(bad in low_url for bad in EXCLUDED_URL_PATTERNS):
        return False
    if any(w in low_txt for w in ["blog", "artykul", "poradnik", "czytaj dalej", "przepis na", "godziny otwarcia"]):
        return False
    return (store_slug in low_url) or (store_slug in low_txt)

def parse_polish_date(day_str: str, month_str: str, year_str: Optional[str] = None) -> Optional[str]:
    try:
        d = int(day_str)
        m = int(month_str)
        now = datetime.now()
        if year_str:
            y = int(year_str)
            if y < 100:
                y += 2000
        else:
            y = now.year
            if now.month == 12 and m == 1:
                y += 1
            elif now.month == 1 and m == 12:
                y -= 1
        return date(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return None

def extract_validity_dates(text: str) -> tuple[Optional[str], Optional[str]]:
    if not text:
        return None, None
    m_range = re.search(
        r"(?:od\s*)?(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\s*(?:-|–|—|do)\s*(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?",
        text,
        re.I,
    )
    if m_range:
        d1, m1, y1, d2, m2, y2 = m_range.groups()
        v_from = parse_polish_date(d1, m1, y1 or y2)
        v_to = parse_polish_date(d2, m2, y2 or y1)
        if v_from and v_to:
            return v_from, v_to
    m_until = re.search(r"(?:wazn[ae]|obowiazuje|oferta)?\s*do\s*(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", text, re.I)
    if m_until:
        d2, m2, y2 = m_until.groups()
        v_to = parse_polish_date(d2, m2, y2)
        if v_to:
            return None, v_to
    m_iso = re.findall(r"\b(202\d-\d{2}-\d{2})\b", text)
    if len(m_iso) >= 2:
        return m_iso[0], m_iso[1]
    if len(m_iso) == 1:
        return None, m_iso[0]
    return None, None

def is_promotion_active(valid_to: Optional[str]) -> bool:
    if not valid_to:
        return True
    try:
        return datetime.strptime(valid_to, "%Y-%m-%d").date() >= datetime.now().date()
    except ValueError:
        return True

def match_core_culinary_item(raw_title: str, price_val: float) -> Optional[tuple[str, str, str]]:
    """Zwraca (canon_key, czysta_nazwa, kategoria) dla podstawowych składników kulinarnych."""
    norm = normalize_ascii(raw_title)
    if len(norm) < 4 or len(norm) > 100:
        return None
    if any(bad in norm for bad in EXCLUDED_GLOBAL_NOISE):
        return None

    for canon_key, (clean_label, cat_name, must_kws, excl_kws, min_p, max_p) in CORE_CULINARY_ITEMS.items():
        if price_val < min_p or price_val > max_p:
            continue
        if any(ex in norm for ex in excl_kws):
            continue
        if any(kw in norm for kw in must_kws):
            if canon_key == "serek_wiejski" and ("lekk" in norm or "light" in norm):
                return "serek_wiejski_lekki", "Serek wiejski lekki", cat_name
            return canon_key, clean_label, cat_name

    return None

def parse_offers(html: str, store_name: str, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    offers = []
    seen = set()

    page_header_text = " ".join([
        soup.title.get_text(" ", strip=True) if soup.title else "",
        " ".join(h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2"], limit=4)),
    ])
    page_valid_from, page_valid_to = extract_validity_dates(page_header_text)

    if not is_promotion_active(page_valid_to):
        return []

    def try_add(raw_prod: str, price_val: float, raw_text: str, v_from: Optional[str], v_to: Optional[str]):
        matched = match_core_culinary_item(raw_prod, price_val)
        if not matched:
            return
        canon_key, clean_label, cat_name = matched
        weight_str = extract_weight_from_text(raw_prod) or extract_weight_from_text(raw_text)
        sig = f"{canon_key}_{price_val}_{weight_str or ''}"
        if sig not in seen:
            seen.add(sig)
            offers.append({
                "store": store_name,
                "canon_key": canon_key,
                "category": cat_name,
                "raw_name": raw_prod,
                "generic_name": clean_label,
                "weight": weight_str,
                "price": round(price_val, 2),
                "valid_from": v_from,
                "valid_to": v_to,
                "raw_text": raw_text,
                "source_url": source_url,
            })

    for script in soup.find_all("script"):
        s_text = script.string or ""
        if not s_text:
            continue
        for m in re.finditer(
            r'"(?:name|title|productName)"\s*:\s*"([^"]{3,110})".{0,450}?"(?:price|lowPrice|promoPrice|value)"\s*:\s*"?(\d{1,3}[.,]\d{2})"?',
            s_text,
            re.S,
        ):
            raw_prod = m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore").strip()
            price_val = float(m.group(2).replace(",", "."))
            try_add(raw_prod, price_val, f"{raw_prod} — {price_val:.2f} zł", page_valid_from, page_valid_to)

    for img in soup.find_all("img", alt=True):
        alt_txt = " ".join((img.get("alt") or "").split())
        if len(alt_txt) < 8 or len(alt_txt) > 220:
            continue
        price_matches = list(re.finditer(r"(\d{1,3}[.,]\d{2})\s*zł", alt_txt, re.I))
        if 1 <= len(price_matches) <= 2:
            first_m = price_matches[0]
            price_val = float(first_m.group(1).replace(",", "."))
            raw_prod = re.sub(r"^zobacz\s+aktualn[aą]\s+", "", alt_txt[:first_m.start()], flags=re.I).strip(" -–|:•,")
            try_add(raw_prod, price_val, alt_txt, page_valid_from, page_valid_to)

    for el in soup.find_all(["article", "div", "li", "a", "tr", "section"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if len(text) < 8 or len(text) > 260:
            continue
        price_matches = list(re.finditer(r"(\d{1,3}[.,]\d{2})\s*zł", text, re.I))
        if not (1 <= len(price_matches) <= 2):
            continue
        first_m = price_matches[0]
        price_val = float(first_m.group(1).replace(",", "."))
        raw_prod = re.sub(r"^zobacz\s+aktualn[aą]\s+", "", text[:first_m.start()], flags=re.I).strip(" -–|:•,")
        card_from, card_to = extract_validity_dates(text)
        v_from = card_from or page_valid_from
        v_to = card_to or page_valid_to
        if not is_promotion_active(v_to):
            continue
        try_add(raw_prod, price_val, f"{raw_prod} — {price_val:.2f} zł", v_from, v_to)

    return offers

def find_leaflet_links_from_home(session: requests.Session) -> dict[str, list[str]]:
    store_links = {s: list(DIRECT_STORE_SEEDS.get(s, [])) for s in STORES}
    for home in PORTAL_HOMES:
        try:
            resp = session.get(home, timeout=15)
            if resp.status_code != 200 or len(resp.text) < 500:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            base_domain = urlparse(home).netloc
            for a in soup.find_all("a", href=True):
                full = urljoin(home, a["href"]).split("#")[0]
                if urlparse(full).netloc != base_domain:
                    continue
                link_txt = a.get_text(" ", strip=True)
                for store in STORES:
                    if is_valid_leaflet_url(full, store.lower(), link_txt) and full not in store_links[store]:
                        store_links[store].append(full)
        except Exception:
            pass
        time.sleep(0.35)
    return store_links

def fetch_all_store_offers() -> list[dict]:
    session = requests.Session()
    session.headers.update(HEADERS)
    discovered = find_leaflet_links_from_home(session)
    all_offers = []

    for store in STORES:
        slug = store.lower()
        links = discovered.get(store, [])
        store_offers = []
        visited = set()
        queue = list(links[:15])
        expanded_leaflet_ids = set()

        while queue and len(visited) < 35:
            url = queue.pop(0)
            if url in visited or not is_valid_leaflet_url(url, slug):
                continue
            visited.add(url)

            m_blix_gaz = re.match(r"^(https?://blix\.pl/sklep/[^/]+/gazetka/\d+/?)$", url)
            if m_blix_gaz and url not in expanded_leaflet_ids:
                expanded_leaflet_ids.add(url)
                base_gaz = m_blix_gaz.group(1).rstrip("/") + "/"
                for page_num in range(2, 11):
                    paged_url = f"{base_gaz}?pageNumber={page_num}"
                    if paged_url not in visited and paged_url not in queue:
                        queue.insert(0, paged_url)

            try:
                time.sleep(0.3)
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    continue
                store_offers.extend(parse_offers(resp.text, store, url))

                soup = BeautifulSoup(resp.text, "html.parser")
                base_domain = urlparse(url).netloc
                for a in soup.find_all("a", href=True):
                    sub = urljoin(url, a["href"]).split("#")[0]
                    sub_txt = a.get_text(" ", strip=True)
                    if urlparse(sub).netloc == base_domain and sub not in visited and sub not in queue:
                        if is_valid_leaflet_url(sub, slug, sub_txt):
                            queue.append(sub)
            except Exception:
                pass

        dedup = {}
        for o in store_offers:
            k = f"{o['canon_key']}_{o['price']}_{o.get('weight') or ''}"
            if k not in dedup:
                dedup[k] = o

        final_list = list(dedup.values())
        print(f"==> {store}: zebrano {len(final_list)} esencjonalnych ofert kulinarnych.", flush=True)
        all_offers.extend(final_list)

    return all_offers

def build_essential_food_pending(offers: list[dict], max_items: int = 85) -> dict:
    """Zwraca 1 najtańszą ofertę na każdy podstawowy składnik kuchenny w danym sklepie wraz z gramaturą (weight) i kategorią."""
    best_per_store_prod = {}
    for off in offers:
        key = f"{normalize_ascii(off['store'])}_{off['canon_key']}"
        if key not in best_per_store_prod or off["price"] < best_per_store_prod[key]["detectedPrice"]:
            best_per_store_prod[key] = {
                "name": off["generic_name"],
                "weight": off.get("weight"),
                "category": off.get("category") or "Inne",
                "detectedPrice": off["price"],
                "store": off["store"],
                "validFrom": off.get("valid_from"),
                "validTo": off.get("valid_to"),
                "source": off["store"],
                "rawText": off["raw_text"],
                "sourceUrl": off["source_url"],
            }

    sorted_items = sorted(best_per_store_prod.items(), key=lambda x: (x[1]["name"], x[1]["detectedPrice"]))[:max_items]
    return dict(sorted_items)

def purge_expired_pending(existing_pending: dict) -> dict:
    cleaned = {}
    for k, v in (existing_pending or {}).items():
        if isinstance(v, dict) and is_promotion_active(v.get("validTo")):
            cleaned[k] = v
    return cleaned

def export_csv(offers: list[dict], filename="promocje_spozywcze.csv"):
    with open(filename, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["store", "category", "generic_name", "weight", "raw_name", "price", "valid_from", "valid_to", "source_url", "collection_date"])
        today = datetime.now().strftime("%Y-%m-%d")
        for o in offers:
            writer.writerow([
                o["store"],
                o.get("category") or "Inne",
                o["generic_name"],
                o.get("weight") or "NULL",
                o["raw_name"],
                f"{o['price']:.2f}",
                o.get("valid_from") or "NULL",
                o.get("valid_to") or "NULL",
                o["source_url"],
                today,
            ])
    print(f"Zapisano CSV: {filename} ({len(offers)} wierszy)", flush=True)

def init_firestore():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        if sa_json:
            cred = credentials.Certificate(json.loads(sa_json))
        elif os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
        else:
            raise RuntimeError("Brak FIREBASE_SERVICE_ACCOUNT lub serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()

def main():
    dry_run = "--dry-run" in sys.argv
    print(f"=== START SCRAPERA ({'TRYB LOKALNY --dry-run' if dry_run else 'TRYB FIREBASE'}) ===", flush=True)

    offers = fetch_all_store_offers()
    export_csv(offers)

    essential_promos = build_essential_food_pending(offers)
    print(f"Przygotowano {len(essential_promos)} esencjonalnych promocji (z gramaturą i kategorią Warzywa i owoce).", flush=True)

    if dry_run:
        with open("wynik_testu.json", "w", encoding="utf-8") as f:
            json.dump({"total_offers": len(offers), "essential_count": len(essential_promos), "items": essential_promos}, f, ensure_ascii=False, indent=2)
        for v in essential_promos.values():
            w_badge = f" [{v['weight']}]" if v.get("weight") else ""
            print(f"  ✓ [{v['store']}] ({v['category']}) {v['name']}{w_badge} -> {v['detectedPrice']:.2f} zł ({v['validFrom']} - {v['validTo']})", flush=True)
        return

    if not essential_promos:
        print("Brak pobranych ofert — przerywam zapis do Firebase.", flush=True)
        return

    db = init_firestore()
    updated = 0
    for doc_snap in db.collection("kuchnie").stream():
        data = doc_snap.to_dict() or {}
        if data.get("active") is False:
            continue

        active_existing = purge_expired_pending(data.get("pendingScraper") or {})
        active_existing.update(essential_promos)

        db.collection("kuchnie").document(doc_snap.id).set({
            "pendingScraper": active_existing,
            "lastScraped": datetime.now().isoformat(),
        }, merge=True)
        updated += 1
        print(f"[Kuchnia {doc_snap.id}] Aktywnych pozycji w poczekalni: {len(active_existing)}.", flush=True)

    print(f"=== ZAKOŃCZONO. Zaktualizowano {updated} kuchni w Firebase. ===", flush=True)

if __name__ == "__main__":
    main()