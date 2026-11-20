import os
import re
import json
from datetime import datetime
from difflib import SequenceMatcher
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright

# 1. Połączenie z Firebase Firestore
service_account_info = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT"])
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred)
db = firestore.client()

HOUSEHOLD_ID = os.environ.get("HOUSEHOLD_ID", "KUCHNIA-2026").strip()

# Punkty wejścia do aktualnych gazetek Lidl, Biedronka, Netto
STORE_LEAFLET_URLS = [
    ("Biedronka", "https://blix.pl/sklep/biedronka/"),
    ("Lidl", "https://blix.pl/sklep/lidl/"),
    ("Netto", "https://blix.pl/sklep/netto/"),
    ("Biedronka", "https://ding.pl/gazetki/biedronka"),
    ("Lidl", "https://ding.pl/gazetki/lidl"),
    ("Netto", "https://ding.pl/gazetki/netto"),
]

JUNK_WORDS = [
    "jak zrobić", "ile piec", "czy to się opłaca", "przepisy", "gotowanie",
    "zobacz ", "sprawdź ", "poradnik", "blog", "artykuł", "gazetka ważna",
    "godziny otwarcia", "regulamin", "polityka prywatności", "wszystkie gazetki",
    "newsletter", "aplikacja mobilna"
]


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    replacements = str.maketrans("ąćęłńóśźż", "acelnoszz")
    return re.sub(r"\s+", " ", text.translate(replacements))


def is_valid_product_name(name: str) -> bool:
    t = name.lower().strip()
    if len(t) < 3 or len(t) > 120:
        return False
    if "?" in t or re.search(r"\b\d{2}\.\d{2}\.\d{4}\b", t):
        return False
    return not any(w in t for w in JUNK_WORDS)


def extract_unit_price(title: str, price: float) -> tuple[str, float | None, str | None]:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b", title.lower())
    if not match:
        return "", None, None

    val = float(match.group(1).replace(",", "."))
    unit = match.group(2)
    if val <= 0:
        return "", None, None

    if unit == "g":
        return f"{int(val)} g", round(price / (val / 1000.0), 2), "kg"
    if unit == "kg":
        return f"{val:g} kg", round(price / val, 2), "kg"
    if unit == "ml":
        return f"{int(val)} ml", round(price / (val / 1000.0), 2), "l"
    if unit == "l":
        return f"{val:g} l", round(price / val, 2), "l"
    return "", None, None


def parse_price(raw) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("amount") or raw.get("gross")
    try:
        val = float(str(raw).replace(",", ".").replace("zł", "").strip())
        # Jeśli API zwraca kwotę w groszach (np. 1299 zamiast 12.99)
        if val > 300 and isinstance(raw, int):
            val = round(val / 100.0, 2)
        return round(val, 2) if 0.2 <= val <= 500.0 else None
    except (ValueError, TypeError):
        return None


def extract_offers_from_json(payload, default_shop: str) -> list[dict]:
    """
    Przeszukuje przechwycone pakiety JSON z wewnętrznych API gazetek
    i wyciąga wszystkie ustrukturyzowane oferty (bez ograniczania kategorii).
    """
    offers = []

    def walk(node):
        if isinstance(node, dict):
            name = (
                node.get("name")
                or node.get("title")
                or node.get("productName")
                or node.get("offerName")
                or node.get("label")
            )
            price = parse_price(
                node.get("price")
                or node.get("promoPrice")
                or node.get("currentPrice")
                or node.get("grossPrice")
                or node.get("salePrice")
            )
            old_price = parse_price(
                node.get("oldPrice")
                or node.get("regularPrice")
                or node.get("beforePrice")
                or node.get("omnibusPrice")
            )

            if isinstance(name, str) and price is not None:
                unit_str = str(node.get("unit") or node.get("weight") or node.get("packaging") or "").strip()
                full_title = f"{name.strip()} {unit_str}".strip()

                if is_valid_product_name(full_title):
                    shop_raw = node.get("shopName") or node.get("retailerName") or node.get("brandName") or default_shop
                    if isinstance(shop_raw, dict):
                        shop_raw = shop_raw.get("name") or default_shop

                    offers.append({
                        "shop": str(shop_raw).strip() or default_shop,
                        "title": full_title,
                        "price": price,
                        "old_price": old_price,
                    })

            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return offers


def scrape_full_leaflets() -> list[dict]:
    """
    Otwiera aktualne gazetki Lidla, Biedronki i Netto, przewija strony,
    przechwytuje paczki JSON z API oraz otwiera pierwszą najnowszą gazetkę każdego sklepu.
    """
    all_offers = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="pl-PL",
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        active_shop = "Gazetka"

        def on_response(response):
            nonlocal all_offers
            try:
                ct = response.headers.get("content-type", "")
                if response.status == 200 and ("application/json" in ct or "text/json" in ct):
                    data = response.json()
                    extracted = extract_offers_from_json(data, active_shop)
                    if extracted:
                        all_offers.extend(extracted)
            except Exception:
                pass

        page.on("response", on_response)

        for shop_name, url in STORE_LEAFLET_URLS:
            active_shop = shop_name
            print(f"Pobieranie danych JSON dla: {shop_name} ({url})")
            try:
                page.goto(url, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(1500)

                # Spróbuj kliknąć w najnowszą aktualną gazetkę na stronie sklepu, aby dociągnąć jej JSON ze stronami/ofertami
                leaflet_link = page.locator("a[href*='gazetka']").first
                if leaflet_link.count() > 0:
                    href = leaflet_link.get_attribute("href")
                    if href:
                        full_leaflet_url = href if href.startswith("http") else f"https://{url.split('/')[2]}{href}"
                        print(f"  -> Otwieram aktualną gazetkę: {full_leaflet_url}")
                        page.goto(full_leaflet_url, wait_until="networkidle", timeout=25000)
                        # Przewiń gazetkę w dół, żeby API załadowało kolejne strony oferty
                        for _ in range(5):
                            page.mouse.wheel(0, 1800)
                            page.wait_for_timeout(800)
            except Exception as e:
                print(f"  ! Ostrzeżenie dla {shop_name} ({url}): {e}")

        browser.close()

    # Deduplikacja po (sklep + znormalizowana nazwa + cena)
    unique_map = {}
    for item in all_offers:
        key = (item["shop"].lower(), normalize_text(item["title"]), item["price"])
        if key not in unique_map:
            unique_map[key] = item

    return list(unique_map.values())


def main():
    print(f"Start pełnego scrapera gazetek (JSON API) dla domu: {HOUSEHOLD_ID}")
    house_ref = db.collection("households").document(HOUSEHOLD_ID)

    # Pobierz obecny cennik i śledzone produkty (tylko po to, by oznaczyć ewentualne dopasowania i rabaty)
    tracked = [{"id": d.id, **d.to_dict()} for d in house_ref.collection("tracked_products").stream()]
    ingredients = [{"id": d.id, **d.to_dict()} for d in house_ref.collection("ingredients").stream()]

    raw_offers = scrape_full_leaflets()
    print(f"Łącznie wyodrębniono {len(raw_offers)} unikalnych pozycji z JSON-ów gazetek.")

    # Zapisz surowy zrzut całej gazetki do pliku JSON (do podglądu / debugowania w repozytorium lub lokalnie)
    with open("ostatnia_gazetka.json", "w", encoding="utf-8") as f:
        json.dump(raw_offers, f, ensure_ascii=False, indent=2)

    pending_ref = house_ref.collection("pending_deals")
    saved_count = 0

    for offer in raw_offers:
        norm_offer = normalize_text(offer["title"])
        pack_str, unit_price, base_unit = extract_unit_price(offer["title"], offer["price"])

        # Sprawdź, czy produkt pasuje do któregoś ze śledzonych lub składników z bazy
        best_match = None
        best_score = 0.0
        is_tracked = False

        for t in tracked:
            norm_t = normalize_text(t.get("name", ""))
            if not norm_t:
                continue
            score = SequenceMatcher(None, norm_t, norm_offer).ratio()
            if norm_t in norm_offer:
                score = max(score, 0.85)
            if score > best_score:
                best_score = score
                best_match = t
                is_tracked = True

        for ing in ingredients:
            norm_i = normalize_text(ing.get("name", ""))
            if not norm_i:
                continue
            score = SequenceMatcher(None, norm_i, norm_offer).ratio()
            if norm_i in norm_offer:
                score = max(score, 0.82)
            if score > best_score:
                best_score = score
                best_match = ing
                is_tracked = False

        matched = best_match if best_score >= 0.58 else None
        base_price = float(matched.get("price") or matched.get("targetPrice") or 0) if matched else (offer["old_price"] or 0.0)
        compare_price = unit_price if (unit_price and base_price > 12.0) else offer["price"]

        discount_pct = 0
        if base_price > 0 and compare_price < base_price:
            discount_pct = round(((base_price - compare_price) / base_price) * 100)

        unit_info = f" ({pack_str} • {unit_price:.2f} zł/{base_unit})" if unit_price else ""
        doc_payload = {
            "ingredientId": matched.get("id", "") if matched else "",
            "title": f"{offer['title']}{unit_info}",
            "rawText": f"{offer['title']} — {offer['price']:.2f} zł ({offer['shop']})",
            "price": offer["price"],
            "unitPrice": unit_price,
            "basePrice": base_price,
            "discountPct": discount_pct,
            "source": f"Gazetka {offer['shop']}",
            "isTracked": is_tracked,
            "scrapedAt": datetime.now().strftime("%d.%m.%Y %H:%M"),
        }

        pending_ref.add(doc_payload)
        saved_count += 1

    house_ref.set({"lastScraped": datetime.now().strftime("%d.%m.%Y %H:%M")}, merge=True)
    print(f"Zakończono! Wysłano {saved_count} pozycji z całej gazetki do Firestore.")


if __name__ == "__main__":
    main()