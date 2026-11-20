import os
import json
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# 1. Połączenie z Twoją bazą Firebase (klucz z GitHub Secrets)
sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
if not sa_json:
    raise ValueError("Brak sekretu FIREBASE_SERVICE_ACCOUNT w ustawieniach GitHub Actions!")

cred_dict = json.loads(sa_json)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

HOUSEHOLD_ID = os.environ.get("HOUSEHOLD_ID", "KUCHNIA-2026").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9"
}

# Domyślna lista startowa (używana tylko, jeśli w bazie jeszcze nie ma własnej listy trackedProducts)
FALLBACK_TRACKED = [
    {"name": "Pierś z kurczaka", "query": "filet z piersi kurczaka", "keywords": ["piers z kurczaka", "filet z kurczaka", "kurczak"], "maxPrice": 16.00},
    {"name": "Mięso mielone", "query": "mięso mielone 500g", "keywords": ["mieso mielone", "mielone"], "maxPrice": 10.50},
    {"name": "Passata pomidorowa", "query": "passata pomidorowa 500g", "keywords": ["passata"], "maxPrice": 3.90},
    {"name": "Tuńczyk w puszce", "query": "tuńczyk w sosie własnym puszka", "keywords": ["tunczyk"], "maxPrice": 5.20},
    {"name": "Czerwona fasola", "query": "fasola czerwona puszka", "keywords": ["fasola czerwona", "czerwona fasola"], "maxPrice": 2.90},
    {"name": "Kukurydza konserwowa", "query": "kukurydza konserwowa puszka", "keywords": ["kukurydza"], "maxPrice": 3.20}
]

# Biała lista półproduktów dla ogólnego polowania w gazetkach
PANTRY_DISCOVERY_KEYWORDS = [
    "passata", "pomidory w puszce", "pomidory krojone", "koncentrat pomidorowy",
    "fasola", "kukurydza", "ciecierzyca", "soczewica", "groszek", "tunczyk", "makrela", "szprot",
    "piers z kurczaka", "filet z kurczaka", "udo z kurczaka", "indyk", "mieso mielone", "schab", "karkowka", "boczek", "kielbasa",
    "makaron", "ryz", "kasza", "platki owsiane", "maka",
    "warzywa na patelnie", "mrozone", "brokul", "kalafior", "szpinak", "ziemniaki", "cebula", "papryka", "pieczarki",
    "ser zolty", "gouda", "mozzarella", "twarog", "jajka", "jaja", "smietana", "maslo", "olej", "oliwa", "mleczko kokosowe"
]

# Czarna lista odrzucająca gotowce, słodycze, alkohol i chemię
BLACKLIST_KEYWORDS = [
    "piwo", "wino", "wodka", "chipsy", "czekolada", "ciastka", "lody", "napoj", "cola",
    "karma", "papier", "proszek", "plyn do", "szampon", "krem do", "pieluchy", "parowki", "przyprawa do"
]


def strip_diacritics(text):
    """Usuwa polskie znaki diakrytyczne (np. 'Mięso żółte' -> 'mieso zolte')."""
    if not text:
        return ""
    text = text.lower().replace("ł", "l")
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def fuzzy_matches(keyword_ascii, target_text_ascii):
    """Sprawdza dokładne zawieranie LUB wysokie podobieństwo wyrazów (odporne na literówki)."""
    if not keyword_ascii or not target_text_ascii:
        return False
    if keyword_ascii in target_text_ascii:
        return True

    # Porównanie słowo po słowie z tolerancją literówek (>= 0.84)
    kw_words = keyword_ascii.split()
    target_words = re.findall(r'[a-z0-9]+', target_text_ascii)
    if len(kw_words) == 1 and len(kw_words[0]) >= 5:
        kw = kw_words[0]
        for tw in target_words:
            if len(tw) >= 5 and SequenceMatcher(None, kw, tw).ratio() >= 0.84:
                return True
    return False


def extract_price(text):
    """Wyciąga cenę w PLN z tekstu (np. '12,99 zł' -> 12.99)."""
    if not text:
        return None
    matches = re.findall(r'(\d{1,3})[,.](\d{2})\s*(?:zł|PLN)?', text)
    for zl, gr in matches:
        val = float(f"{zl}.{gr}")
        if 0.99 <= val <= 45.0:
            return val
    return None


def clean_product_title(raw_txt):
    """Czyści surowy tekst z gazetki na zwięzłą nazwę produktu."""
    cleaned = re.sub(r'\d{1,3}[,.]\d{2}\s*(?:zł|PLN)?', '', raw_txt)
    cleaned = re.sub(r'-\d{1,2}%', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(" -–•:,.")
    return cleaned[:55].capitalize() if cleaned else raw_txt[:45]


def fetch_tracked_products_from_firebase():
    """Pobiera aktualną listę obserwowanych produktów wpisanych przez użytkownika w aplikacji."""
    try:
        doc_snap = db.collection("households").document(HOUSEHOLD_ID).get()
        if doc_snap.exists:
            data = doc_snap.to_dict()
            tracked = data.get("trackedProducts")
            if isinstance(tracked, list) and len(tracked) > 0:
                print(f"Pobrano {len(tracked)} śledzonych produktów z Firebase.")
                return tracked
    except Exception as e:
        print(f"Ostrzeżenie przy odczycie trackedProducts z Firebase: {e}")
    return FALLBACK_TRACKED


def scrape_frisco_price(query):
    """Sprawdza aktualną cenę orientacyjną w wyszukiwarce Frisco.pl."""
    try:
        url = f"https://www.frisco.pl/stn,search/n,{requests.utils.quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None, None
        soup = BeautifulSoup(resp.text, "html.parser")
        price_el = soup.select_one("[class*='price'], [data-testid*='price']")
        title_el = soup.select_one("[class*='product-box'] h3, [class*='title']")
        if price_el:
            price = extract_price(price_el.get_text(" ", strip=True))
            raw_title = title_el.get_text(" ", strip=True) if title_el else query
            return price, raw_title[:85]
    except Exception as e:
        print(f"[Frisco] Błąd dla '{query}': {e}")
    return None, None


def scrape_promos_and_discoveries(tracked_list):
    """Skanuje gazetki (Lidl, Biedronka, Netto) pod kątem śledzonej listy ORAZ ogólnych okazji na półprodukty."""
    tracked_promos = {}
    general_discoveries = {}

    stores = [
        ("Lidl", "https://www.okazjum.pl/lidl/"),
        ("Biedronka", "https://www.okazjum.pl/biedronka/"),
        ("Netto", "https://www.okazjum.pl/netto/")
    ]

    for store_name, url in stores:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            text_blocks = soup.find_all(["h3", "h4", "p", "div"], limit=550)

            for block in text_blocks:
                txt = block.get_text(" ", strip=True)
                if len(txt) < 6 or len(txt) > 130:
                    continue

                txt_ascii = strip_diacritics(txt)
                if any(bad in txt_ascii for bad in BLACKLIST_KEYWORDS):
                    continue

                price = extract_price(txt)
                if not price:
                    continue

                # 1. Dopasowanie do dynamicznej listy śledzonych produktów użytkownika
                matched_tracked = False
                for item in tracked_list:
                    prod_name = item.get("name", "")
                    max_p = item.get("maxPrice")
                    kws = item.get("keywords") or [strip_diacritics(prod_name)]

                    if any(fuzzy_matches(strip_diacritics(k), txt_ascii) for k in kws):
                        matched_tracked = True
                        # Jeśli użytkownik ustawił cenę max, sprawdź czy mieści się w budżecie
                        if max_p and price > float(max_p):
                            continue

                        existing = tracked_promos.get(prod_name)
                        if not existing or price < existing["price"]:
                            tracked_promos[prod_name] = {
                                "price": price,
                                "oldPrice": float(max_p) if max_p else round(price * 1.2, 2),
                                "source": f"Promocja {store_name}",
                                "rawText": txt[:115],
                                "isPromo": True
                            }

                # 2. Ogólne polowanie na okazje półproduktów spożywczych
                if not matched_tracked and len(general_discoveries) < 18:
                    matched_kw = next((kw for kw in PANTRY_DISCOVERY_KEYWORDS if kw in txt_ascii), None)
                    if matched_kw:
                        nice_title = clean_product_title(txt)
                        if len(nice_title) >= 5 and nice_title not in general_discoveries:
                            general_discoveries[nice_title] = {
                                "name": nice_title,
                                "detectedPrice": price,
                                "oldPrice": round(price * 1.25, 2),
                                "source": f"Okazja {store_name}",
                                "rawText": txt[:115],
                                "isPromo": True,
                                "isDiscovery": True
                            }

        except Exception as e:
            print(f"[Gazetki {store_name}] Błąd: {e}")

    return tracked_promos, general_discoveries


def filter_pending_with_gemini(pending_dict):
    """Opcjonalny filtr AI (gdy ustawiono GEMINI_API_KEY w GitHub Secrets) — odrzuca fałszywe dopasowania."""
    if not GEMINI_API_KEY or not pending_dict:
        return pending_dict

    try:
        items_summary = [
            {"key": k, "name": v["name"], "rawText": v["rawText"], "price": v["detectedPrice"]}
            for k, v in pending_dict.items()
        ]
        prompt = f"""Jesteś kontrolerem jakości listy zakupów spożywczych.
Sprawdź poniższą listę dopasowań ze sklepu. Odrzuć pozycje, które NIE są prawdziwym produktem spożywczym lub są oczywistą pomyłką (np. przyprawa zamiast mięsa, karma dla zwierząt, słodycze).
Zwróć TYLKO poprawną tablicę JSON z kluczami ('key') pozycji, które są poprawne i warto je pokazać użytkownikowi:
{json.dumps(items_summary, ensure_ascii=False)}"""

        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            },
            timeout=15
        )
        if resp.status_code == 200:
            raw_ans = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            valid_keys = set(json.loads(raw_ans))
            filtered = {k: v for k, v in pending_dict.items() if k in valid_keys}
            print(f"[Gemini AI Filter] Zostawiono {len(filtered)}/{len(pending_dict)} pozycji.")
            return filtered
    except Exception as e:
        print(f"[Gemini AI Filter] Pominięto z powodu błędu: {e}")

    return pending_dict


def main():
    print(f"Start inteligentnego scrapera dla domu: {HOUSEHOLD_ID}")
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    tracked_list = fetch_tracked_products_from_firebase()
    tracked_promos, general_discoveries = scrape_promos_and_discoveries(tracked_list)

    pending_items = {}

    # 1. Wyniki dla śledzonych produktów użytkownika
    for item in tracked_list:
        name = item.get("name", "")
        query = item.get("query", name)
        max_p = item.get("maxPrice")

        if name in tracked_promos:
            hit = tracked_promos[name]
            pending_items[name] = {
                "name": name,
                "detectedPrice": hit["price"],
                "oldPrice": hit["oldPrice"],
                "source": hit["source"],
                "rawText": hit["rawText"],
                "isPromo": True,
                "isDiscovery": False,
                "status": "pending",
                "scrapedAt": now_str
            }
        else:
            frisco_price, frisco_title = scrape_frisco_price(query)
            if frisco_price:
                is_promo = bool(max_p and frisco_price <= float(max_p))
                pending_items[name] = {
                    "name": name,
                    "detectedPrice": frisco_price,
                    "oldPrice": float(max_p) if max_p else frisco_price,
                    "source": "Frisco.pl",
                    "rawText": frisco_title or query,
                    "isPromo": is_promo,
                    "isDiscovery": False,
                    "status": "pending",
                    "scrapedAt": now_str
                }

    # 2. Ogólne okazje na półprodukty z gazetek
    for disc_key, disc_item in general_discoveries.items():
        if disc_key not in pending_items:
            pending_items[disc_key] = {
                **disc_item,
                "status": "pending",
                "scrapedAt": now_str
            }

    # 3. Opcjonalna weryfikacja przez Gemini AI (jeśli ustawiono sekret GEMINI_API_KEY)
    pending_items = filter_pending_with_gemini(pending_items)

    # 4. Zapis do Poczekalni (pendingScraper) w Firestore
    doc_ref = db.collection("households").document(HOUSEHOLD_ID)
    doc_ref.set({
        "pendingScraper": pending_items,
        "lastScraped": now_str
    }, merge=True)

    print(f"Zakończono! Wysłano {len(pending_items)} pozycji do Poczekalni w Firebase.")


if __name__ == "__main__":
    main()