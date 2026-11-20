import os
import re
import json
import time
import urllib.parse
from datetime import datetime
from difflib import SequenceMatcher
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright

# 1. Połączenie z Firebase Firestore
service_account_info = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT"])
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred)
db = firestore.client()

HOUSEHOLD_ID = os.environ.get("HOUSEHOLD_ID", "KUCHNIA-2026").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Słowa wskazujące na artykuły blogowe / śmieciowe nagłówki (twarda blokada)
BLOG_BLACKLIST = [
    "jak zrobić", "ile piec", "czy to się opłaca", "przepisy", "gotowanie",
    "zobacz ", "sprawdź ", "poradnik", "blog", "artykuł", "gazetka ważna",
    "godziny otwarcia", "regulamin", "polityka prywatności", "wszystkie gazetki"
]


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    replacements = str.maketrans("ąćęłńóśźż", "acelnoszz")
    return re.sub(r"\s+", " ", text.translate(replacements))


def is_junk_title(title: str) -> bool:
    t = title.lower().strip()
    if len(t) < 3 or len(t) > 110:
        return True
    if "?" in t:
        return True
    # Odrzuć tytuły zawierające daty (np. 25.03.2025), które myliły parser cen
    if re.search(r"\b\d{2}\.\d{2}\.\d{4}\b", t):
        return True
    return any(bad in t for bad in BLOG_BLACKLIST)


def extract_unit_price(title: str, price: float) -> tuple[str, float | None, str | None]:
    """
    Wyciąga gramaturę (np. '500 g', '1 kg', '250 ml', '1 l') i wylicza cenę za 1 kg / 1 l.
    """
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b", title.lower())
    if not match:
        return "", None, None

    val = float(match.group(1).replace(",", "."))
    unit = match.group(2)

    if val <= 0:
        return "", None, None

    if unit == "g":
        unit_price = round(price / (val / 1000.0), 2)
        return f"{int(val)} g", unit_price, "kg"
    if unit == "kg":
        unit_price = round(price / val, 2)
        return f"{val:g} kg", unit_price, "kg"
    if unit == "ml":
        unit_price = round(price / (val / 1000.0), 2)
        return f"{int(val)} ml", unit_price, "l"
    if unit == "l":
        unit_price = round(price / val, 2)
        return f"{val:g} l", unit_price, "l"

    return "", None, None


def extract_json_offers(payload, source_hint: str) -> list[dict]:
    """
    Rekurencyjnie przeszukuje przechwycone pakiety JSON z API (Blix / Frisco)
    i wyciąga wyłącznie ustrukturyzowane obiekty ofertowe (name + price).
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            # Szukamy obiektów wyglądających jak karta produktu w API
            name = (
                node.get("name")
                or node.get("title")
                or node.get("productName")
                or node.get("offerName")
            )
            raw_price = (
                node.get("price")
                or node.get("promoPrice")
                or node.get("currentPrice")
                or node.get("grossPrice")
            )
            if isinstance(raw_price, dict):
                raw_price = raw_price.get("value") or raw_price.get("amount")

            shop = (
                node.get("shopName")
                or node.get("retailerName")
                or node.get("brandName")
                or source_hint
            )
            if isinstance(shop, dict):
                shop = shop.get("name") or source_hint

            unit_str = node.get("unit") or node.get("weight") or node.get("packaging") or ""

            if isinstance(name, str) and raw_price is not None:
                try:
                    price_val = float(str(raw_price).replace(",", ".").strip())
                    # Jeśli API zwraca cenę w groszach (np. 1499 zamiast 14.99)
                    if price_val > 250 and isinstance(raw_price, int):
                        price_val = round(price_val / 100.0, 2)

                    full_title = f"{name.strip()} {unit_str}".strip()
                    if 0.5 <= price_val <= 250.0 and not is_junk_title(full_title):
                        found.append({
                            "title": full_title,
                            "price": round(price_val, 2),
                            "shop": str(shop).strip() or source_hint,
                            "raw_text": f"{full_title} — {price_val:.2f} zł ({shop})"
                        })
                except (ValueError, TypeError):
                    pass

            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def scrape_product_queries(queries: list[str]) -> list[dict]:
    """
    Uruchamia Playwrighta, odpytuje wyszukiwarki Blix i Frisco dla konkretnych produktów
    i przechwytuje czyste odpowiedzi JSON z ich wewnętrznych API (zero śmieci ze stopek).
    """
    collected = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="pl-PL"
        )
        page = context.new_page()
        current_source = "Gazetka"

        def handle_response(response):
            nonlocal collected
            try:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type and response.status == 200:
                    url_l = response.url.lower()
                    if any(k in url_l for k in ["search", "offer", "product", "promo", "catalog", "api"]):
                        data = response.json()
                        items = extract_json_offers(data, current_source)
                        collected.extend(items)
            except Exception:
                pass

        page.on("response", handle_response)

        for query in queries[:15]:  # Limit 15 zapytań na przebieg, żeby akcja trwała < 60s
            encoded = urllib.parse.quote(query)

            # 1. Wyszukiwarka ofert Blix (Lidl, Biedronka, Netto itp.)
            current_source = "Promocja Gazetka"
            try:
                page.goto(f"https://blix.pl/szukaj/?q={encoded}", wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(1200)

                # Fallback na ustrukturyzowane karty ofertowe DOM (tylko elementy z jawnym 'zł')
                cards = page.locator("[class*='offer'], [class*='product-card'], [data-offer-id]").all()
                for card in cards[:15]:
                    txt = re.sub(r"\s+", " ", card.inner_text()).strip()
                    price_m = re.search(r"(\d{1,3}[.,]\d{2})\s*(?:zł|PLN)", txt, re.IGNORECASE)
                    if price_m:
                        price_val = float(price_m.group(1).replace(",", "."))
                        clean_name = txt[:price_m.start()].strip(" -•|")
                        if 0.5 <= price_val <= 250.0 and not is_junk_title(clean_name):
                            shop_m = re.search(r"\b(Biedronka|Lidl|Netto|Kaufland|Auchan|Dino|Carrefour)\b", txt, re.I)
                            shop_name = f"Promocja {shop_m.group(1).capitalize()}" if shop_m else "Promocja Gazetka"
                            collected.append({
                                "title": clean_name,
                                "price": price_val,
                                "shop": shop_name,
                                "raw_text": f"{clean_name} — {price_val:.2f} zł"
                            })
            except Exception as e:
                print(f"Błąd Blix dla '{query}': {e}")

            # 2. Wyszukiwarka Frisco
            current_source = "Frisco"
            try:
                page.goto(f"https://www.frisco.pl/q,{encoded}/stn,searchResults", wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(1200)
            except Exception as e:
                print(f"Błąd Frisco dla '{query}': {e}")

        browser.close()

    # Deduplikacja po (znormalizowany tytuł + cena + sklep)
    unique = {}
    for item in collected:
        key = (normalize_text(item["title"]), item["price"], item["shop"])
        unique[key] = item

    return list(unique.values())


def verify_and_clean_with_gemini(candidates: list[dict]) -> list[dict]:
    """
    Używa gemini-3-flash-preview do oczyszczenia nazw produktów i odrzucenia
    wszelkich niepasujących dopasowań (np. karma dla psa zamiast mięsa).
    """
    if not GEMINI_API_KEY or not candidates:
        return candidates

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={GEMINI_API_KEY}"
    prompt_items = [
        {
            "id": i,
            "tracked": c["tracked_name"],
            "found_title": c["title"],
            "price": c["price"],
            "shop": c["shop"]
        }
        for i, c in enumerate(candidates)
    ]

    prompt = (
        "Jesteś asystentem zakupów spożywczych. Oceń dopasowania ze sklepu do śledzonych produktów.\n"
        "Zwróć WYŁĄCZNIE poprawny JSON w formacie listy obiektów:\n"
        '[{"id": 0, "valid": true, "clean_title": "Czysta nazwa produktu z gramaturą"}]\n'
        "Zasady:\n"
        "1. Ustaw valid=false, jeśli oferta to artykuł, przepis, karma dla zwierząt, chemia lub zupełnie inny produkt.\n"
        "2. W clean_title usuń śmieciowe dopiski typu 'Zobacz', 'Super cena', daty, zostaw nazwę i gramaturę.\n"
        f"Dane:\n{json.dumps(prompt_items, ensure_ascii=False)}"
    )

    try:
        resp = requests.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            },
            timeout=25
        )
        resp.raise_for_status()
        raw_json = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        decisions = {d["id"]: d for d in json.loads(raw_json)}

        cleaned = []
        for i, c in enumerate(candidates):
            dec = decisions.get(i)
            if dec and dec.get("valid") is True:
                if dec.get("clean_title"):
                    c["title"] = dec["clean_title"].strip()
                cleaned.append(c)
        return cleaned
    except Exception as e:
        print(f"Ostrzeżenie Gemini AI (używam lokalnego filtra): {e}")
        return candidates


def main():
    print(f"Start inteligentnego scrapera (JSON + Search) dla domu: {HOUSEHOLD_ID}")
    house_ref = db.collection("households").document(HOUSEHOLD_ID)

    # Pobierz śledzone produkty z Radaru oraz półprodukty z cennika
    tracked_docs = house_ref.collection("tracked_products").stream()
    tracked = [{"id": d.id, **d.to_dict()} for d in tracked_docs]

    ingredients_docs = house_ref.collection("ingredients").stream()
    ingredients = [{"id": d.id, **d.to_dict()} for d in ingredients_docs]

    # Zbuduj listę unikalnych haseł do wyszukania
    queries = []
    seen_q = set()
    for item in tracked + ingredients:
        name = (item.get("name") or "").strip()
        norm = normalize_text(name)
        if name and norm not in seen_q:
            seen_q.add(norm)
            queries.append(name)

    if not queries:
        queries = ["pierś z kurczaka", "masło", "ser żółty", "tuńczyk w puszce", "jajka"]

    print(f"Wyszukiwane hasła ({len(queries)}): {', '.join(queries[:10])}")
    raw_offers = scrape_product_queries(queries)
    print(f"Pobrano {len(raw_offers)} czystych ofert ze sklepów.")

    # Dopasuj oferty do śledzonych produktów / bazy cenowej
    candidates = []
    for offer in raw_offers:
        norm_offer = normalize_text(offer["title"])
        best_match = None
        best_score = 0.0
        is_tracked = False

        for t in tracked:
            t_name = t.get("name", "")
            norm_t = normalize_text(t_name)
            score = SequenceMatcher(None, norm_t, norm_offer).ratio()
            if norm_t in norm_offer:
                score = max(score, 0.85)
            if score > best_score:
                best_score = score
                best_match = t
                is_tracked = True

        for ing in ingredients:
            i_name = ing.get("name", "")
            norm_i = normalize_text(i_name)
            score = SequenceMatcher(None, norm_i, norm_offer).ratio()
            if norm_i in norm_offer:
                score = max(score, 0.82)
            if score > best_score:
                best_score = score
                best_match = ing
                is_tracked = False

        if best_match and best_score >= 0.55:
            pack_str, unit_price, base_unit = extract_unit_price(offer["title"], offer["price"])
            base_price = float(best_match.get("price") or best_match.get("targetPrice") or 0)

            # Jeśli w bazie cena jest za 1 kg/1 l i mamy wyliczoną cenę jednostkową, porównajmy jabłka do jabłek
            compare_price = unit_price if (unit_price and base_price > 12.0) else offer["price"]
            discount_pct = 0
            if base_price > 0 and compare_price < base_price:
                discount_pct = round(((base_price - compare_price) / base_price) * 100)

            unit_info = f" ({pack_str} • {unit_price:.2f} zł/{base_unit})" if unit_price else ""
            candidates.append({
                "tracked_name": best_match.get("name", ""),
                "ingredientId": best_match.get("id", ""),
                "title": f"{offer['title']}{unit_info}",
                "rawText": offer["raw_text"],
                "price": offer["price"],
                "unitPrice": unit_price,
                "basePrice": base_price,
                "discountPct": discount_pct,
                "source": offer["shop"],
                "isTracked": is_tracked,
                "scrapedAt": datetime.now().strftime("%d.%m.%Y %H:%M")
            })

    verified = verify_and_clean_with_gemini(candidates)

    # Wyczyść starą poczekalnię przed zapisem świeżych wyników (opcjonalnie można zostawić)
    pending_ref = house_ref.collection("pending_deals")
    for doc in verified[:30]:
        pending_ref.add(doc)

    house_ref.set({"lastScraped": datetime.now().strftime("%d.%m.%Y %H:%M")}, merge=True)
    print(f"Zakończono! Wysłano {len(verified[:30])} zweryfikowanych pozycji do Poczekalni w Firebase.")


if __name__ == "__main__":
    main()
