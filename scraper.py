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

NON_FOOD_AND_NOISE_KEYWORDS = [
    "proszek", "plyn do", "kapsulki", "papier toaletowy", "recznik papierowy",
    "szampon", "zel pod prysznic", "mydlo", "pasta do zebow", "dezodorant",
    "karma", "zwirek", "pieluchy", "pampers", "patelnia", "garnek", "skarpetki",
    "koszulka", "spodnie", "buty", "zabawka", "baterie", "zarowka", "wiertarka",
    "szlifierka", "kosiarka", "doniczka", "ziemia ogrodowa", "piwo", "wodka",
    "wino", "whisky", "likier", "cydr", "papierosy", "tyton", "krem do", "balsam",
    "reklamowka", "torba na zakupy", "folia aluminiowa", "papier do pieczenia",
    "przyprawa do", "przyprawy", "fix ", "pomysl na", "marynata", "zupa blyskawiczna",
    "goracy kubek", "kostka rosolowa", "bulionetka", "karma dla", "parkside", "esmara",
    "lupilu", "crivit", "silvercrest", "livarno", "zobacz aktualna", "gazetka ",
    "strona ", "oferta wazna", "wszystkie promocje", "wybrane sklepy", "sprawdz oferte",
    "kup teraz", "dodaj do koszyka", "cena regularna", "najtaniej w"
]

PRODUCT_GUARDRAILS = {
    "piers_z_kurczaka": {
        "must_have_any": ["piers", "filet"],
        "exclude": ["przypraw", "wedlin", "szynk", "poledwic", "pasztet", "parowk", "kabanos", "panier", "nuggets", "strips", "konserw", "salatk", "karma"],
        "min_price": 9.50,
    },
    "mieso_mielone": {
        "must_have_any": ["mielon"],
        "exclude": ["przypraw", "fix", "pomysl na", "sos", "pierogi", "krokiety", "nalesniki"],
        "min_price": 5.50,
    },
    "maslo": {
        "must_have_any": ["maslo"],
        "exclude": ["orzech", "roslinn", "margaryn", "mix", "oselk", "krem", "balsam", "do ciala", "shea"],
        "min_price": 3.50,
    },
    "mleko": {
        "must_have_any": ["mleko"],
        "exclude": ["kokos", "sojow", "owsian", "migdal", "zageszczon", "skondensowan", "w proszku", "czekolad", "do demakijazu", "balsam", "modifikowan", "bebiko", "nan"],
        "min_price": 1.80,
    },
    "jajka": {
        "must_have_any": ["jaj"],
        "exclude": ["niespodziank", "czekolad", "makaron", "majonez", "kinder"],
        "min_price": 4.50,
    },
    "tunczyk": {
        "must_have_any": ["tunczyk"],
        "exclude": ["salatk", "pasta", "karma", "dla kota"],
        "min_price": 3.00,
    },
    "passata_pomidorowa": {
        "must_have_any": ["passata", "przecier pomidor"],
        "exclude": ["zupa", "krem"],
        "min_price": 2.20,
    },
}

BRAND_WORDS = [
    "mlekovita", "piatnica", "laciate", "mlekpol", "lubelska", "krasnystaw",
    "wloszczowa", "sierpc", "hochland", "president", "almette", "danone",
    "bakoma", "zott", "muller", "pudliszki", "dawtona", "lowicz", "kotlin",
    "roleski", "winiary", "knorr", "prymat", "kamis", "bonduelle", "lisner",
    "graal", "marinero", "sokolow", "morliny", "berlinki", "tarczynski",
    "krakus", "pikok", "dulano", "milbona", "pilos", "lidl", "biedronka", "netto",
    "fruvita", "mleczna dolina", "kraina wedlin", "kraina mies", "nasze smaki",
    "lubella", "barilla", "sonko", "kupiec", "kujawski", "rama", "delma",
    "kasia", "ekstra", "uht", "zobacz aktualna", "ryneczek lidla", "rzeznik"
]

def normalize_ascii(text: str) -> str:
    text = str(text or "").lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("ł", "l")

def canonical_product_key(name: str) -> str:
    a = normalize_ascii(name)
    if ("piers" in a and "kurczak" in a) or ("filet" in a and "kurczak" in a):
        return "piers_z_kurczaka"
    if "mielon" in a:
        return "mieso_mielone"
    if "masl" in a and "maslank" not in a and "orzech" not in a:
        return "maslo"
    if re.search(r"\bmlek[oa]\b", a):
        return "mleko"
    if "jajk" in a or re.search(r"\bjaj[ao]?\b", a):
        return "jajka"
    if "tunczyk" in a:
        return "tunczyk"
    if "passat" in a or "przecier pomidor" in a:
        return "passata_pomidorowa"
    return re.sub(r"[^a-z0-9_]", "_", a).strip("_")

def expand_keywords(t_name: str, raw_kws: list[str]) -> list[str]:
    canon = canonical_product_key(t_name)
    kws = set(normalize_ascii(k) for k in raw_kws if k)
    kws.add(normalize_ascii(t_name))

    if canon == "piers_z_kurczaka":
        kws.discard("kurczak")
        kws.update(["piers z kurczaka", "filet z kurczaka", "filet z piersi", "piers kurczaka", "filet kurczaka"])
    elif canon == "jajka":
        kws.update(["jajka", "jaja", "jaj"])
    elif canon == "passata_pomidorowa":
        kws.update(["passata", "przecier pomidorowy"])
    elif canon == "mieso_mielone":
        kws.update(["mieso mielone", "mielone"])

    return [k for k in kws if len(k) >= 3]

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
        dt = date(y, m, d)
        return dt.strftime("%Y-%m-%d")
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
        end_year = y2 or y1
        start_year = y1 or y2
        v_from = parse_polish_date(d1, m1, start_year)
        v_to = parse_polish_date(d2, m2, end_year)
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
        end_dt = datetime.strptime(valid_to, "%Y-%m-%d").date()
        return end_dt >= datetime.now().date()
    except ValueError:
        return True

def clean_generic_name(raw_name: str) -> str:
    s = re.sub(r"^zobacz\s+aktualn[aą]\s+", "", raw_name, flags=re.I)
    s = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:kg|g|dag|ml|l|szt\.?|%)\b", " ", s, flags=re.I)
    for b in BRAND_WORDS:
        s = re.sub(r"\b" + re.escape(b) + r"\b", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -–|:•,")
    ascii_s = normalize_ascii(s)

    if "serek wiejski" in ascii_s:
        return "Serek wiejski lekki" if ("lekk" in ascii_s or "light" in ascii_s) else "Serek wiejski"
    if "masl" in ascii_s and "maslank" not in ascii_s and "orzech" not in ascii_s:
        return "Masło"
    if re.search(r"\bmlek[oa]\b", ascii_s):
        return "Mleko"
    if "jajk" in ascii_s or re.search(r"\bjaj[ao]?\b", ascii_s):
        return "Jajka"
    return (s[0].upper() + s[1:]) if s else raw_name.strip()

def is_food_offer(title: str) -> bool:
    norm = normalize_ascii(title)
    if len(norm) < 4 or len(norm) > 85:
        return False
    # Musi zawierać przynajmniej 3 litery (odrzuca same liczby/kody)
    if len(re.findall(r"[a-z]", norm)) < 3:
        return False
    return not any(bad in norm for bad in NON_FOOD_AND_NOISE_KEYWORDS)

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

    for script in soup.find_all("script"):
        s_text = script.string or ""
        if not s_text:
            continue
        for m in re.finditer(
            r'"(?:name|title|productName)"\s*:\s*"([^"]{3,95})".{0,400}?"(?:price|lowPrice|promoPrice|value)"\s*:\s*"?(\d{1,3}[.,]\d{2})"?',
            s_text,
            re.S,
        ):
            raw_prod = m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore").strip()
            price_val = float(m.group(2).replace(",", "."))
            if 0.40 <= price_val <= 150.0 and is_food_offer(raw_prod):
                generic = clean_generic_name(raw_prod)
                if not is_food_offer(generic):
                    continue
                sig = f"{normalize_ascii(generic)}_{price_val}"
                if sig not in seen:
                    seen.add(sig)
                    offers.append({
                        "store": store_name,
                        "raw_name": raw_prod,
                        "generic_name": generic,
                        "price": round(price_val, 2),
                        "valid_from": page_valid_from,
                        "valid_to": page_valid_to,
                        "raw_text": f"{raw_prod} ({price_val:.2f} zł)",
                        "source_url": source_url,
                    })

    for img in soup.find_all("img", alt=True):
        alt_txt = " ".join((img.get("alt") or "").split())
        if len(alt_txt) < 8 or len(alt_txt) > 180:
            continue
        prices = re.findall(r"(\d{1,3}[.,]\d{2})\s*zł", alt_txt, re.I)
        if len(prices) == 1:
            price_val = float(prices[0].replace(",", "."))
            price_pos = re.search(r"\d{1,3}[.,]\d{2}\s*zł", alt_txt, re.I).start()
            raw_prod = re.sub(r"^zobacz\s+aktualn[aą]\s+", "", alt_txt[:price_pos], flags=re.I).strip(" -–|:•,")
            if 0.40 <= price_val <= 150.0 and is_food_offer(raw_prod):
                generic = clean_generic_name(raw_prod)
                if not is_food_offer(generic):
                    continue
                sig = f"{normalize_ascii(generic)}_{price_val}"
                if sig not in seen:
                    seen.add(sig)
                    offers.append({
                        "store": store_name,
                        "raw_name": raw_prod,
                        "generic_name": generic,
                        "price": round(price_val, 2),
                        "valid_from": page_valid_from,
                        "valid_to": page_valid_to,
                        "raw_text": alt_txt,
                        "source_url": source_url,
                    })

    for el in soup.find_all(["article", "div", "li", "a", "tr", "section"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if len(text) < 8 or len(text) > 200:
            continue

        prices = re.findall(r"(\d{1,3}[.,]\d{2})\s*zł", text, re.I)
        if len(prices) != 1:
            continue

        price_val = float(prices[0].replace(",", "."))
        if price_val < 0.40 or price_val > 150.0:
            continue

        price_pos = re.search(r"\d{1,3}[.,]\d{2}\s*zł", text, re.I).start()
        raw_prod = re.sub(r"^zobacz\s+aktualn[aą]\s+", "", text[:price_pos], flags=re.I).strip(" -–|:•,")
        if not is_food_offer(raw_prod):
            continue

        card_from, card_to = extract_validity_dates(text)
        v_from = card_from or page_valid_from
        v_to = card_to or page_valid_to

        if not is_promotion_active(v_to):
            continue

        generic = clean_generic_name(raw_prod)
        if not is_food_offer(generic):
            continue

        sig = f"{normalize_ascii(generic)}_{price_val}"
        if sig not in seen:
            seen.add(sig)
            offers.append({
                "store": store_name,
                "raw_name": raw_prod,
                "generic_name": generic,
                "price": round(price_val, 2),
                "valid_from": v_from,
                "valid_to": v_to,
                "raw_text": f"{raw_prod} — {price_val:.2f} zł",
                "source_url": source_url,
            })

    return offers

def find_leaflet_links_from_home(session: requests.Session) -> dict[str, list[str]]:
    store_links = {s: list(DIRECT_STORE_SEEDS.get(s, [])) for s in STORES}

    for home in PORTAL_HOMES:
        try:
            resp = session.get(home, timeout=15)
            print(f"[HOME] {home} -> HTTP {resp.status_code} ({len(resp.text)} B)", flush=True)
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
                    slug = store.lower()
                    if is_valid_leaflet_url(full, slug, link_txt):
                        if full not in store_links[store]:
                            store_links[store].append(full)
        except Exception as exc:
            print(f"[HOME] Błąd {home}: {exc}", flush=True)
        time.sleep(0.5)

    return store_links

def fetch_all_store_offers() -> list[dict]:
    session = requests.Session()
    session.headers.update(HEADERS)

    discovered = find_leaflet_links_from_home(session)
    all_offers = []

    for store in STORES:
        slug = store.lower()
        links = discovered.get(store, [])
        print(f"\n[{store}] Sprawdzam {len(links)} linków startowych (bez blogów)...", flush=True)
        store_offers = []

        visited = set()
        queue = list(links[:15])

        while queue and len(visited) < 22:
            url = queue.pop(0)
            if url in visited or not is_valid_leaflet_url(url, slug):
                continue
            visited.add(url)

            try:
                time.sleep(0.45)
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    continue

                found = parse_offers(resp.text, store, url)
                if found:
                    print(f"  -> {url} (+{len(found)} ofert)", flush=True)
                store_offers.extend(found)

                soup = BeautifulSoup(resp.text, "html.parser")
                base_domain = urlparse(url).netloc
                for a in soup.find_all("a", href=True):
                    sub = urljoin(url, a["href"]).split("#")[0]
                    sub_txt = a.get_text(" ", strip=True)
                    if urlparse(sub).netloc == base_domain and sub not in visited and sub not in queue:
                        if is_valid_leaflet_url(sub, slug, sub_txt):
                            queue.append(sub)
            except Exception as exc:
                print(f"  -> Błąd {url}: {exc}", flush=True)

        dedup = {}
        for o in store_offers:
            k = f"{normalize_ascii(o['generic_name'])}_{o['price']}"
            if k not in dedup:
                dedup[k] = o

        final_list = list(dedup.values())
        print(f"==> {store}: zebrano {len(final_list)} unikalnych, aktualnych ofert spożywczych.", flush=True)
        all_offers.extend(final_list)

    return all_offers

def passes_guardrails(canon_key: str, offer: dict) -> tuple[bool, str]:
    rules = PRODUCT_GUARDRAILS.get(canon_key)
    if not rules:
        return True, "OK"

    haystack = normalize_ascii(f"{offer['raw_name']} {offer['generic_name']}")
    for bad in rules.get("exclude", []):
        if bad in haystack:
            return False, f"wykluczone słowo '{bad}'"

    must_any = rules.get("must_have_any", [])
    if must_any and not any(req in haystack for req in must_any):
        return False, f"brak wymaganego {must_any}"

    min_p = rules.get("min_price")
    if min_p is not None and offer["price"] < float(min_p):
        return False, f"cena {offer['price']:.2f} < min_price {min_p:.2f}"

    return True, "OK"

def build_all_food_pending(offers: list[dict], max_items: int = 250) -> dict:
    """Gdy lista śledzonych jest pusta — zwraca wszystkie unikalne promocje spożywcze (najtańsza dla każdego produktu w danym sklepie)."""
    best_per_store_prod = {}
    for off in offers:
        generic = off["generic_name"]
        canon = canonical_product_key(generic)
        ok, _ = passes_guardrails(canon, off)
        if not ok:
            continue

        key = f"{normalize_ascii(off['store'])}_{canon}"
        if not key or len(key) < 4:
            continue

        if key not in best_per_store_prod or off["price"] < best_per_store_prod[key]["detectedPrice"]:
            best_per_store_prod[key] = {
                "name": generic,
                "detectedPrice": off["price"],
                "store": off["store"],
                "validFrom": off.get("valid_from"),
                "validTo": off.get("valid_to"),
                "source": off["store"],
                "rawText": off["raw_text"],
                "sourceUrl": off["source_url"],
            }

    # Sortujemy po nazwie produktu, limitujemy do max_items żeby nie przeciążyć dokumentu Firestore (1 MB)
    sorted_items = sorted(best_per_store_prod.items(), key=lambda x: (x[1]["name"], x[1]["detectedPrice"]))[:max_items]
    return dict(sorted_items)

def match_offers(offers: list[dict], tracked_products: list[dict], debug: bool = True) -> dict:
    # TRYB WSZYSTKICH PROMOCJI: jeśli lista śledzonych jest pusta -> wyślij wszystkie czyste promocje na żywność!
    if not tracked_products:
        all_food = build_all_food_pending(offers)
        if debug:
            print(f"[TRYB WSZYSTKIE PROMOCJE] Brak filtrów śledzonych -> przygotowano {len(all_food)} promocji spożywczych.", flush=True)
        return all_food

    pending = {}
    for tracked in tracked_products:
        t_name = tracked.get("name", "")
        canon_key = canonical_product_key(t_name)
        keywords = expand_keywords(t_name, tracked.get("keywords", []))
        max_price = tracked.get("maxPrice")

        candidates = []
        for off in offers:
            haystack = f"{normalize_ascii(off['raw_name'])} {normalize_ascii(off['generic_name'])}"
            if any(kw in haystack for kw in keywords):
                ok, _ = passes_guardrails(canon_key, off)
                if not ok:
                    continue
                candidates.append(off)

        if not candidates:
            continue

        candidates.sort(key=lambda x: x["price"])
        best = candidates[0]
        price_note = ""
        if max_price is not None and best["price"] > float(max_price):
            price_note = f" [powyżej progu {float(max_price):.2f} zł]"

        safe_key = re.sub(r"[^a-z0-9_]", "_", normalize_ascii(t_name))
        pending[safe_key] = {
            "name": t_name,
            "detectedPrice": best["price"],
            "store": best["store"],
            "validFrom": best.get("valid_from"),
            "validTo": best.get("valid_to"),
            "source": best["store"],
            "rawText": f"{best['raw_text']}{price_note}",
            "sourceUrl": best["source_url"],
        }
    return pending

def export_csv(offers: list[dict], filename="promocje_spozywcze.csv"):
    with open(filename, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["store", "generic_name", "raw_name", "price", "valid_from", "valid_to", "source_url", "collection_date"])
        today = datetime.now().strftime("%Y-%m-%d")
        for o in offers:
            writer.writerow([
                o["store"],
                o["generic_name"],
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

    if dry_run:
        # Test trybu pustej listy (wszystkie promocje na żywność)
        matched = match_offers(offers, [], debug=True)
        with open("wynik_testu.json", "w", encoding="utf-8") as f:
            json.dump({"total_offers": len(offers), "all_food_pending_count": len(matched), "sample_pending": dict(list(matched.items())[:25])}, f, ensure_ascii=False, indent=2)
        print(f"\n[DRY-RUN] Wygenerowano {len(matched)} promocji spożywczych do poczekalni! Szczegóły w wynik_testu.json.", flush=True)
        for v in list(matched.values())[:15]:
            print(f"  ✓ [{v['store']}] {v['name']} -> {v['detectedPrice']:.2f} zł ({v['validFrom']} - {v['validTo']})", flush=True)
        return

    if not offers:
        print("Brak pobranych ofert — przerywam zapis do Firebase.", flush=True)
        return

    db = init_firestore()
    updated = 0
    for doc_snap in db.collection("kuchnie").stream():
        data = doc_snap.to_dict() or {}
        if data.get("active") is False:
            continue
        tracked = data.get("trackedProducts") or []
        print(f"\n--- Dopasowuję dla kuchni {doc_snap.id} (śledzone: {len(tracked)} -> {'WSZYSTKIE ŻYWNOŚCIOWE' if not tracked else 'FILTR RADARU'}) ---", flush=True)
        matched = match_offers(offers, tracked, debug=True)
        if matched:
            existing = data.get("pendingScraper") or {}
            existing.update(matched)
            db.collection("kuchnie").document(doc_snap.id).set({
                "pendingScraper": existing,
                "lastScraped": datetime.now().isoformat(),
            }, merge=True)
            updated += 1
            print(f"[Kuchnia {doc_snap.id}] Wysłano {len(matched)} okazji do Weryfikacji Scrapera.", flush=True)

    print(f"=== ZAKOŃCZONO. Zaktualizowano {updated} kuchni w Firebase. ===", flush=True)

if __name__ == "__main__":
    main()