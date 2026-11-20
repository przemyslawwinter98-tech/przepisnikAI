import os
import re
import json
import time
import unicodedata
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------------------
# 1. INICJALIZACJA FIREBASE
# ---------------------------------------------------------------------------
def init_firestore():
    if not firebase_admin._apps:
        sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        if sa_json:
            cred = credentials.Certificate(json.loads(sa_json))
        elif os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
        else:
            raise RuntimeError("Brak klucza FIREBASE_SERVICE_ACCOUNT lub pliku serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ---------------------------------------------------------------------------
# 2. NORMALIZACJA TEKSTU I FILTR WYŁĄCZNIE ŻYWNOŚCI
# ---------------------------------------------------------------------------
NON_FOOD_KEYWORDS = [
    "proszek", "plyn do", "kapsulki", "papier toaletowy", "recznik papierowy",
    "szampon", "zel pod prysznic", "mydlo", "pasta do zebow", "dezodorant",
    "karma", "zwirek", "pieluchy", "pampers", "patelnia", "garnek", "skarpetki",
    "koszulka", "spodnie", "buty", "zabawka", "baterie", "zarowka", "wiertarka",
    "szlifierka", "kosiarka", "doniczka", "ziemia ogrodowa", "piwo", "wodka",
    "wino", "whisky", "likier", "cydr", "papierosy", "tyton"
]

def normalize_ascii(text: str) -> str:
    text = str(text or "").lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("ł", "l")

def is_food_offer(title: str) -> bool:
    norm = normalize_ascii(title)
    if len(norm) < 3:
        return False
    return not any(bad in norm for bad in NON_FOOD_KEYWORDS)

# ---------------------------------------------------------------------------
# 3. POBIERANIE OFERT Z GAZETEK (LIDL, BIEDRONKA, NETTO)
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9",
}

STORE_SOURCES = {
    "Lidl": [
        "https://www.ding.pl/sklepy/lidl/oferty",
        "https://gazetkowo.pl/lidl/oferty",
    ],
    "Biedronka": [
        "https://www.ding.pl/sklepy/biedronka/oferty",
        "https://gazetkowo.pl/biedronka/oferty",
    ],
    "Netto": [
        "https://www.ding.pl/sklepy/netto/oferty",
        "https://gazetkowo.pl/netto/oferty",
    ],
}

def extract_offers_from_html(store_name: str, url: str) -> list[dict]:
    offers = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        print(f"[{store_name}] GET {url} -> HTTP {resp.status_code} ({len(resp.text)} B)")
        if resp.status_code != 200 or len(resp.text) < 500:
            return offers

        soup = BeautifulSoup(resp.text, "html.parser")

        # Szukamy kart ofertowych zawierających cenę w zł
        cards = soup.find_all(["article", "div", "li", "a"])
        seen_raw = set()

        for el in cards:
            text = " ".join(el.get_text(" ", strip=True).split())
            if len(text) < 8 or len(text) > 220 or text in seen_raw:
                continue

            price_match = re.search(r"(\d{1,3}[.,]\d{2})\s*zł", text, re.I)
            if not price_match:
                continue

            price_val = float(price_match.group(1).replace(",", "."))
            if price_val <= 0.20 or price_val > 250.0:
                continue

            # Wyciągamy nazwę produktu przed ceną
            name_part = text[:price_match.start()].strip(" -–|:•")
            if len(name_part) < 3:
                continue
            if not is_food_offer(name_part):
                continue

            seen_raw.add(text)
            offers.append({
                "store": store_name,
                "raw_name": name_part,
                "price": round(price_val, 2),
                "raw_text": text,
                "source_url": url
            })
    except Exception as exc:
        print(f"[{store_name}] Błąd pobierania {url}: {exc}")

    return offers

def fetch_all_store_offers() -> list[dict]:
    all_offers = []
    for store_name, urls in STORE_SOURCES.items():
        store_found = []
        for url in urls:
            store_found = extract_offers_from_html(store_name, url)
            if store_found:
                break
            time.sleep(1.5)
        print(f"-> Zebrano {len(store_found)} ofert spożywczych dla sieci: {store_name}")
        all_offers.extend(store_found)
        time.sleep(1.5)
    return all_offers

# ---------------------------------------------------------------------------
# 4. DOPASOWANIE DO ŚLEDZONYCH PRODUKTÓW W KUCHNIACH (kuchnie/{kodKuchni})
# ---------------------------------------------------------------------------
def match_offers_for_kitchen(offers: list[dict], tracked_products: list[dict]) -> dict:
    pending = {}
    today_str = datetime.now().strftime("%Y-%m-%d")

    for tracked in tracked_products:
        t_name = tracked.get("name", "")
        keywords = [normalize_ascii(k) for k in tracked.get("keywords", []) if k]
        if not keywords and t_name:
            keywords = [normalize_ascii(t_name)]
        max_price = tracked.get("maxPrice")

        best_offer = None
        for off in offers:
            norm_offer = normalize_ascii(off["raw_name"])
            if any(kw in norm_offer for kw in keywords):
                if max_price is not None and off["price"] > float(max_price):
                    continue
                if best_offer is None or off["price"] < best_offer["price"]:
                    best_offer = off

        if best_offer:
            safe_key = re.sub(r"[^a-z0-9_]", "_", normalize_ascii(t_name))
            pending[safe_key] = {
                "name": t_name,
                "detectedPrice": best_offer["price"],
                "source": f"Promocja {best_offer['store']}",
                "rawText": f"{best_offer['raw_text']} (z dn. {today_str})",
                "sourceUrl": best_offer["source_url"]
            }

    return pending

# ---------------------------------------------------------------------------
# 5. GŁÓWNA PĘTLA AKTUALIZACJI
# ---------------------------------------------------------------------------
def main():
    print("=== START SCRAPERA PROMOCJI SPOŻYWCZYCH ===")
    db = init_firestore()
    all_offers = fetch_all_store_offers()
    print(f"Łącznie znaleziono {len(all_offers)} aktualnych ofert spożywczych.")

    if not all_offers:
        print("UWAGA: Nie pobrano żadnych ofert z indeksów gazetek. Sprawdź logi HTTP powyżej.")
        return

    kitchens_ref = db.collection("kuchnie").stream()
    updated_kitchens = 0

    for doc_snap in kitchens_ref:
        data = doc_snap.to_dict() or {}
        if data.get("active") is False:
            continue

        code = doc_snap.id
        tracked = data.get("trackedProducts", [])
        if not tracked:
            continue

        matched = match_offers_for_kitchen(all_offers, tracked)
        if matched:
            existing_pending = data.get("pendingScraper") or {}
            existing_pending.update(matched)
            db.collection("kuchnie").document(code).set({
                "pendingScraper": existing_pending,
                "lastScraped": datetime.now().isoformat()
            }, merge=True)
            updated_kitchens += 1
            print(f"[Kuchnia {code}] Zapisano {len(matched)} dopasowanych promocji do poczekalni.")

    print(f"=== ZAKOŃCZONO. Zaktualizowano {updated_kitchens} kuchni. ===")

if __name__ == "__main__":
    main()
