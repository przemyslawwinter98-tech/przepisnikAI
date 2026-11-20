import os
import json
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import firebase_admin
from firebase_admin import credentials, firestore
import requests

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

FALLBACK_TRACKED = [
    {"name": "Pierś z kurczaka", "query": "filet z piersi kurczaka", "keywords": ["piers z kurczaka", "filet z kurczaka", "kurczak filet"], "maxPrice": 18.00},
    {"name": "Mięso mielone", "query": "mięso mielone 500g", "keywords": ["mieso mielone", "mielone wieprzowe", "mielone wolowe"], "maxPrice": 11.50},
    {"name": "Passata pomidorowa", "query": "passata pomidorowa 500g", "keywords": ["passata"], "maxPrice": 4.20},
    {"name": "Tuńczyk w puszce", "query": "tuńczyk w sosie własnym puszka", "keywords": ["tunczyk"], "maxPrice": 5.50},
    {"name": "Czerwona fasola", "query": "fasola czerwona puszka", "keywords": ["fasola czerwona", "czerwona fasola"], "maxPrice": 3.20},
    {"name": "Kukurydza konserwowa", "query": "kukurydza konserwowa puszka", "keywords": ["kukurydza"], "maxPrice": 3.40}
]

PANTRY_DISCOVERY_KEYWORDS = [
    "passata", "pomidory krojone", "pomidory w puszce", "koncentrat pomidorowy",
    "fasola", "kukurydza", "ciecierzyca", "soczewica", "groszek", "tunczyk", "makrela", "szprot",
    "piers z kurczaka", "filet z kurczaka", "udo z kurczaka", "indyk", "mieso mielone", "schab", "karkowka", "boczek", "kielbasa",
    "makaron", "ryz", "kasza", "platki owsiane", "maka",
    "warzywa na patelnie", "mrozone", "brokul", "kalafior", "szpinak", "ziemniaki", "cebula", "papryka", "pieczarki",
    "ser zolty", "gouda", "mozzarella", "twarog", "jajka", "jaja", "smietana", "maslo", "olej", "oliwa", "mleczko kokosowe"
]

BLACKLIST_KEYWORDS = [
    "piwo", "wino", "wodka", "chipsy", "czekolada", "ciastka", "lody", "napoj", "cola",
    "karma", "papier", "proszek", "plyn do", "szampon", "krem do", "pieluchy", "parowki", "przyprawa do",
    "jak zrobic", "ile piec", "czy to sie oplaca", "zobacz gotowanie", "zobacz jedzenie", "przepisy", "gazetka", "promocje w"
]


def strip_diacritics(text):
    if not text:
        return ""
    text = text.lower().replace("ł", "l")
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def is_blog_or_garbage(text, text_ascii):
    # Odrzuć artykuły blogowe (pytajniki, daty typu 25.03.2025, nagłówki poradników)
    if "?" in text:
        return True
    if re.search(r'\b\d{2}\.\d{2}\.\d{4}\b', text):
        return True
    if any(bad in text_ascii for bad in BLACKLIST_KEYWORDS):
        return True
    return False


def fuzzy_matches(keyword_ascii, target_text_ascii):
    if not keyword_ascii or not target_text_ascii:
        return False
    if keyword_ascii in target_text_ascii:
        return True

    kw_words = keyword_ascii.split()
    target_words = re.findall(r'[a-z0-9]+', target_text_ascii)
    if len(kw_words) == 1 and len(kw_words[0]) >= 5:
        kw = kw_words[0]
        for tw in target_words:
            if len(tw) >= 5 and SequenceMatcher(None, kw, tw).ratio() >= 0.85:
                return True
    return False


def extract_price_strict(text):
    """Wymaga jawnego oznaczenia waluty (zł / PLN) przy cenie, aby wykluczyć daty i liczby."""
    if not text:
        return None
    matches = re.findall(r'(?<!\d)(\d{1,3})[,.](\d{2})\s*(?:zł|PLN)\b', text, flags=re.IGNORECASE)
    for zl, gr in matches:
        val = float(f"{zl}.{gr}")
        if 0.99 <= val <= 45.0:
            return val
    return None


def extract_weight_and_unit_price(text, price):
    """Wykrywa gramaturę (np. 500 g, 1 kg, 400 ml) i przelicza cenę za 1 kg / 1 l."""
    if not text or not price:
        return None, None
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b', text, flags=re.IGNORECASE)
    if not m:
        return None, None

    qty = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    if qty <= 0:
        return None, None

    if unit == "g":
        unit_price = round((price / qty) * 1000.0, 2)
        return f"{int(qty)} g", f"{unit_price:.2f} zł/kg"
    elif unit == "kg":
        unit_price = round(price / qty, 2)
        return f"{qty:g} kg", f"{unit_price:.2f} zł/kg"
    elif unit == "ml":
        unit_price = round((price / qty) * 1000.0, 2)
        return f"{int(qty)} ml", f"{unit_price:.2f} zł/l"
    elif unit == "l":
        unit_price = round(price / qty, 2)
        return f"{qty:g} l", f"{unit_price:.2f} zł/l"

    return None, None


def clean_product_title(raw_txt):
    cleaned = re.sub(r'^zobacz\s+', '', raw_txt, flags=re.IGNORECASE)
    cleaned = re.sub(r'\d{1,3}[,.]\d{2}\s*(?:zł|PLN)?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'-\d{1,2}%', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(" -–•:,.")
    return cleaned[:55].capitalize() if cleaned else raw_txt[:45]


def fetch_tracked_products_from_firebase():
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


def scrape_with_browser(tracked_list):
    tracked_promos = {}
    general_discoveries = {}
    frisco_results = {}

    promo_sources = [
        ("Lidl", "https://blix.pl/sklep/lidl/"),
        ("Biedronka", "https://blix.pl/sklep/biedronka/"),
        ("Netto", "https://blix.pl/sklep/netto/"),
        ("Lidl", "https://ding.pl/promocje/lidl"),
        ("Biedronka", "https://ding.pl/promocje/biedronka")
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="pl-PL",
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        # ETAP 1: Gazetki promocyjne (Blix / Ding)
        for store_name, url in promo_sources:
            try:
                print(f"[Gazetki] Pobieram {store_name} ({url})...")
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2500)
                page.mouse.wheel(0, 1600)
                page.wait_for_timeout(1000)

                soup = BeautifulSoup(page.content(), "html.parser")
                # Wytnij stopkę i sekcje artykułów blogowych
                for bad_tag in soup.select("footer, nav, [class*='blog'], [class*='article'], [class*='news']"):
                    bad_tag.decompose()

                blocks = soup.find_all(["article", "li", "div", "a"], limit=800)

                for block in blocks:
                    txt = block.get_text(" ", strip=True)
                    if len(txt) < 8 or len(txt) > 125:
                        continue

                    txt_ascii = strip_diacritics(txt)
                    if is_blog_or_garbage(txt, txt_ascii):
                        continue

                    price = extract_price_strict(txt)
                    if not price:
                        continue

                    weight_str, unit_price_str = extract_weight_and_unit_price(txt, price)
                    unit_badge = f" [{weight_str} • {unit_price_str}]" if weight_str else ""

                    # 1) Dopasowanie do śledzonej listy
                    matched_tracked = False
                    for item in tracked_list:
                        prod_name = item.get("name", "")
                        max_p = item.get("maxPrice")
                        kws = item.get("keywords") or [strip_diacritics(prod_name)]

                        if any(fuzzy_matches(strip_diacritics(k), txt_ascii) for k in kws):
                            matched_tracked = True
                            if max_p and price > float(max_p):
                                continue
                            existing = tracked_promos.get(prod_name)
                            if not existing or price < existing["price"]:
                                tracked_promos[prod_name] = {
                                    "price": price,
                                    "oldPrice": float(max_p) if max_p else round(price * 1.2, 2),
                                    "source": f"Promocja {store_name}",
                                    "rawText": f"{txt[:105]}{unit_badge}",
                                    "weight": weight_str,
                                    "unitPrice": unit_price_str,
                                    "isPromo": True
                                }

                    # 2) Ogólne okazje na półprodukty
                    if not matched_tracked and len(general_discoveries) < 16:
                        matched_kw = next((kw for kw in PANTRY_DISCOVERY_KEYWORDS if kw in txt_ascii), None)
                        if matched_kw:
                            nice_title = clean_product_title(txt)
                            if weight_str and weight_str not in nice_title:
                                nice_title = f"{nice_title} ({weight_str})"
                            if len(nice_title) >= 5 and nice_title not in general_discoveries:
                                general_discoveries[nice_title] = {
                                    "name": nice_title,
                                    "detectedPrice": price,
                                    "oldPrice": round(price * 1.25, 2),
                                    "source": f"Okazja {store_name}",
                                    "rawText": f"{txt[:105]}{unit_badge}",
                                    "isPromo": True,
                                    "isDiscovery": True
                                }
            except Exception as e:
                print(f"[Gazetki {store_name}] Błąd: {e}")

        # ETAP 2: Frisco.pl dla śledzonych produktów nieznalezionych w gazetkach
        for item in tracked_list:
            name = item.get("name", "")
            if name in tracked_promos:
                continue
            query = item.get("query", name)
            try:
                search_url = f"https://www.frisco.pl/stn,search/n,{query.replace(' ', '%20')}"
                print(f"[Frisco] Szukam: {query}...")
                page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                soup = BeautifulSoup(page.content(), "html.parser")
                candidates = soup.select("[class*='product'], [data-testid*='product'], article, li")
                for cand in candidates[:25]:
                    cand_txt = cand.get_text(" ", strip=True)
                    if len(cand_txt) < 10 or len(cand_txt) > 180:
                        continue
                    price = extract_price_strict(cand_txt)
                    if price:
                        w_str, u_str = extract_weight_and_unit_price(cand_txt, price)
                        badge = f" [{w_str} • {u_str}]" if w_str else ""
                        frisco_results[name] = {
                            "price": price,
                            "rawText": f"{cand_txt[:105]}{badge}"
                        }
                        print(f"[Frisco] Znaleziono {name}: {price} zł")
                        break
            except Exception as e:
                print(f"[Frisco] Błąd dla '{query}': {e}")

        browser.close()

    return tracked_promos, general_discoveries, frisco_results


def clean_and_filter_with_gemini(pending_dict):
    """Używa Gemini 3 Flash do odrzucenia błędnych dopasowań i wyczyszczenia nazw produktów."""
    if not GEMINI_API_KEY or not pending_dict:
        return pending_dict

    try:
        items_summary = [
            {"key": k, "name": v["name"], "rawText": v["rawText"], "price": v["detectedPrice"]}
            for k, v in pending_dict.items()
        ]
        prompt = f"""Jesteś kontrolerem jakości ofert spożywczych z gazetek.
Przeanalizuj poniższą listę dopasowań.
1. ODRZUĆ wszystko, co jest artykułem blogowym, poradnikiem kulinarnym, przyprawą w torebce zamiast mięsa, karmą dla zwierząt, słodyczami albo ma bzdurną cenę niepasującą do produktu (np. 1 kg kurczaka za 1 zł).
2. Dla poprawnych ofert spożywczych podaj czystą, krótką nazwę produktu wraz z gramaturą (jeśli występuje w rawText, np. "Schab wędzony (100 g)" lub "Pierś z kurczaka (1 kg)").

Zwróć TYLKO poprawny JSON (tablicę obiektów):
[{{"key": "oryginalny klucz", "cleanName": "Poprawiona czysta nazwa produktu"}}]
Lista wejściowa:
{json.dumps(items_summary, ensure_ascii=False)}"""

        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            },
            timeout=20
        )
        if resp.status_code == 200:
            raw_ans = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            approved_list = json.loads(raw_ans)
            filtered = {}
            for entry in approved_list:
                k = entry.get("key")
                if k in pending_dict:
                    item_copy = dict(pending_dict[k])
                    if entry.get("cleanName") and item_copy.get("isDiscovery"):
                        item_copy["name"] = entry["cleanName"]
                    filtered[k] = item_copy
            print(f"[Gemini 3 AI Filter] Zatwierdzono {len(filtered)}/{len(pending_dict)} prawdziwych ofert.")
            return filtered
        else:
            print(f"[Gemini 3 AI Filter] HTTP {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        print(f"[Gemini 3 AI Filter] Pominięto z powodu błędu: {e}")

    return pending_dict


def main():
    print(f"Start inteligentnego scrapera v2 dla domu: {HOUSEHOLD_ID}")
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    tracked_list = fetch_tracked_products_from_firebase()
    tracked_promos, general_discoveries, frisco_results = scrape_with_browser(tracked_list)

    pending_items = {}

    for item in tracked_list:
        name = item.get("name", "")
        max_p = item.get("maxPrice")

        if name in tracked_promos:
            hit = tracked_promos[name]
            display_name = f"{name} ({hit['weight']})" if hit.get("weight") else name
            pending_items[name] = {
                "name": display_name,
                "detectedPrice": hit["price"],
                "oldPrice": hit["oldPrice"],
                "source": hit["source"],
                "rawText": hit["rawText"],
                "isPromo": True,
                "isDiscovery": False,
                "status": "pending",
                "scrapedAt": now_str
            }
        elif name in frisco_results:
            fr = frisco_results[name]
            is_promo = bool(max_p and fr["price"] <= float(max_p))
            pending_items[name] = {
                "name": name,
                "detectedPrice": fr["price"],
                "oldPrice": float(max_p) if max_p else fr["price"],
                "source": "Frisco.pl",
                "rawText": fr["rawText"],
                "isPromo": is_promo,
                "isDiscovery": False,
                "status": "pending",
                "scrapedAt": now_str
            }

    for disc_key, disc_item in general_discoveries.items():
        if disc_key not in pending_items:
            pending_items[disc_key] = {
                **disc_item,
                "status": "pending",
                "scrapedAt": now_str
            }

    pending_items = clean_and_filter_with_gemini(pending_items)

    doc_ref = db.collection("households").document(HOUSEHOLD_ID)
    doc_ref.set({
        "pendingScraper": pending_items,
        "lastScraped": now_str
    }, merge=True)

    print(f"Zakończono! Wysłano {len(pending_items)} czystych pozycji do Poczekalni w Firebase.")


if __name__ == "__main__":
    main()
```

Podmień **`scraper.py`** na tę wersję, kliknij **Wyczyść poczekalnię** w aplikacji i odpal ponownie **Run workflow** — zobaczysz teraz czyste oferty z gramaturą, ceną za 1 kg i bez żadnych artykułów blogowych!
