import os
import re
import json
import time
import unicodedata
from urllib.parse import urljoin, urlparse
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
    "wino", "whisky", "likier", "cydr", "papierosy", "tyton", "krem do", "balsam"
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
# 3. POBIERANIE STRON + AUTOMATYCZNE ODKRYWANIE LINKÓW DO GAZETEK/OFERT
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
}

STORE_HUBS = {
    "Lidl": [
        "https://www.ding.pl/lidl",
        "https://gazetkowo.pl/lidl",
        "https://blix.pl/sklep/lidl/",
    ],
    "Biedronka": [
        "https://www.ding.pl/biedronka",
        "https://gazetkowo.pl/biedronka",
        "https://blix.pl/sklep/biedronka/",
    ],
    "Netto": [
        "https://www.ding.pl/netto",
        "https://gazetkowo.pl/netto",
        "https://blix.pl/sklep/netto/",
    ],
}

def extract_offers_from_soup(store_name: str, soup: BeautifulSoup, source_url: str) -> list[dict]:
    offers = []
    seen_raw = set()

    # A) Parsowanie bloków JSON-LD / Next.js jeśli są w HTML
    for script in soup.find_all("script"):
        s_text = script.string or ""
        if "zł" in s_text or "PLN" in s_text:
            for m in re.finditer(r'"(?:name|title)"\s*:\s*"([^"]{3,90})".{0,250}?"(?:price|lowPrice)"\s*:\s*"?(\d{1,3}[.,]\d{2})"?', s_text, re.S):
                prod_name = m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore").strip()
                price_val = float(m.group(2).replace(",", "."))
                if 0.20 < price_val <= 250.0 and is_food_offer(prod_name):
                    key = f"{prod_name}_{price_val}"
                    if key not in seen_raw:
                        seen_raw.add(key)
                        offers.append({
                            "store": store_name,
                            "raw_name": prod_name,
                            "price": round(price_val, 2),
                            "raw_text": f"{prod_name} - {price_val:.2f} zł",
                            "source_url": source_url
                        })

    # B) Parsowanie elementów HTML zawierających nazwę i cenę w zł
    for el in soup.find_all(["article", "div", "li", "a", "section"]):
        # Pomijamy duże kontenery mające wiele zagnieżdżonych cen
        text = " ".join(el.get_text(" ", strip=True).split())
        if len(text) < 8 or len(text) > 180 or text in seen_raw:
            continue

        prices = re.findall(r"(\d{1,3}[.,]\d{2})\s*zł", text, re.I)
        if len(prices) != 1:
            continue

        price_val = float(prices[0].replace(",", "."))
        if price_val <= 0.20 or price_val > 250.0:
            continue

        price_pos = re.search(r"\d{1,3}[.,]\d{2}\s*zł", text, re.I).start()
        name_part = text[:price_pos].strip(" -–|:•,")
        if len(name_part) < 3 or not is_food_offer(name_part):
            continue

        seen_raw.add(text)
        offers.append({
            "store": store_name,
            "raw_name": name_part,
            "price": round(price_val, 2),
            "raw_text": text,
            "source_url": source_url
        })

    return offers

def discover_subpages(base_url: str, soup: BeautifulSoup, store_slug: str) -> list[str]:
    base_domain = urlparse(base_url).netloc
    found = []
    for a in soup.find_all("a", href=True):
        full_url = urljoin(base_url, a["href"]).split("#")[0]
        parsed = urlparse(full_url)
        if parsed.netloc != base_domain:
            continue
        low = full_url.lower()
        if store_slug in low and any(k in low for k in ["gazetk", "ofert", "promocj", "produkt"]):
            if full_url != base_url and full_url not in found:
                found.append(full_url)
    return found[:4]  # Maksymalnie 4 najnowsze podstrony na źródło

def fetch_store_offers(session: requests.Session, store_name: str, hub_urls: list[str]) -> list[dict]:
    store_slug = normalize_ascii(store_name)
    collected = []

    for hub_url in hub_urls:
        try:
            resp = session.get(hub_url, timeout=20)
            print(f"[{store_name}] HUB {hub_url} -> HTTP {resp.status_code} ({len(resp.text)} B)")
            if resp.status_code != 200 or len(resp.text) < 500:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            hub_offers = extract_offers_from_soup(store_name, soup, hub_url)
            collected.extend(hub_offers)

            # Jeśli na samej stronie sklepu było mało ofert, wchodzimy w odkryte linki gazetek/ofert
            subpages = discover_subpages(hub_url, soup, store_slug)
            print(f"  Odkryto {len(subpages)} podstron z gazetkami/ofertami dla {store_name}")
            for sub_url in subpages:
                time.sleep(1.2)
                sub_resp = session.get(sub_url, timeout=20)
                print(f"  -> SUB {sub_url} -> HTTP {sub_resp.status_code}")
                if sub_resp.status_code == 200:
                    sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                    collected.extend(extract_offers_from_soup(store_name, sub_soup, sub_url))

            if collected:
                break
        except Exception as exc:
            print(f"[{store_name}] Błąd dla {hub_url}: {exc}")
        time.sleep(1.2)

    # Deduplikacja po (nazwa + cena)
    unique = {}
    for item in collected:
        k = f"{normalize_ascii(item['raw_name'])}_{item['price']}"
        if k not in unique:
            unique[k] = item
    return list(unique.values())

def fetch_all_store_offers() -> list[dict]:
    session = requests.Session()
    session.headers.update(HEADERS)
    all_offers = []

    for store_name, hubs in STORE_HUBS.items():
        store_offers = fetch_store_offers(session, store_name, hubs)
        print(f"==> Zebrano {len(store_offers)} unikalnych ofert spożywczych dla sieci: {store_name}")
        all_offers.extend(store_offers)

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
        print("UWAGA: Nie pobrano żadnych ofert. Sprawdź kody HTTP powyżej.")
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
