import os
import re
import json
import base64
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

STORE_URLS = [
    ("Biedronka", "https://blix.pl/sklep/biedronka/"),
    ("Lidl", "https://blix.pl/sklep/lidl/"),
    ("Netto", "https://blix.pl/sklep/netto/"),
]


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    replacements = str.maketrans("ąćęłńóśźż", "acelnoszz")
    return re.sub(r"\s+", " ", text.translate(replacements))


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


def collect_leaflet_page_images(max_pages_per_store: int = 6) -> list[dict]:
    """
    Otwiera aktualną gazetkę Biedronki, Lidla i Netto w Playwright
    i zbiera adresy URL obrazów stron gazetki (duże obrazy JPG/WEBP).
    """
    collected_images = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="pl-PL",
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()

        for shop_name, store_url in STORE_URLS:
            print(f"Szukam aktualnej gazetki dla: {shop_name}...")
            try:
                page.goto(store_url, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(1200)

                # Wejdź w pierwszą (najnowszą) gazetkę danego sklepu
                leaflet_link = page.locator("a[href*='/gazetka/']").first
                if leaflet_link.count() == 0:
                    leaflet_link = page.locator("a[href*='gazetka']").first

                if leaflet_link.count() > 0:
                    href = leaflet_link.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://blix.pl{href}"
                        print(f"  -> Otwieram: {full_url}")
                        page.goto(full_url, wait_until="networkidle", timeout=25000)

                # Przewiń gazetkę, aby wyrenderować lazy-loaded strony
                for _ in range(7):
                    page.mouse.wheel(0, 1600)
                    page.wait_for_timeout(700)

                # Wyciągnij duże obrazy stron gazetki z DOM
                img_urls = page.evaluate(
                    """() => {
                        const imgs = Array.from(document.querySelectorAll('img'));
                        return imgs
                            .filter(img => {
                                const src = img.currentSrc || img.src || '';
                                const w = img.naturalWidth || img.width || 0;
                                const h = img.naturalHeight || img.height || 0;
                                return src.startsWith('http') && w >= 350 && h >= 450 && !src.includes('logo');
                            })
                            .map(img => img.currentSrc || img.src);
                    }"""
                )

                seen = set()
                store_imgs = []
                for u in img_urls:
                    if u not in seen:
                        seen.add(u)
                        store_imgs.append(u)

                print(f"  -> Znaleziono {len(store_imgs)} stron gazetki dla {shop_name} (pobieram maks. {max_pages_per_store}).")
                for idx, img_url in enumerate(store_imgs[:max_pages_per_store]):
                    collected_images.append({
                        "shop": shop_name,
                        "page": idx + 1,
                        "url": img_url,
                    })

            except Exception as e:
                print(f"  ! Błąd przy pobieraniu stron gazetki {shop_name}: {e}")

        browser.close()

    return collected_images


def parse_images_with_gemini_vision(page_images: list[dict]) -> list[dict]:
    """
    Wysyła pobrane strony gazetek do Gemini Vision (gemini-3-flash-preview)
    i zamienia je na czysty JSON z produktami i cenami.
    """
    if not GEMINI_API_KEY:
        print("BŁĄD: Brak GEMINI_API_KEY w GitHub Secrets! Dodaj klucz, aby włączyć OCR gazetek.")
        return []

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={GEMINI_API_KEY}"
    all_extracted = []

    # Przetwarzamy po 3 strony na jedno zapytanie API (szybko i stabilnie)
    batch_size = 3
    for i in range(0, len(page_images), batch_size):
        batch = page_images[i : i + batch_size]
        parts = []
        meta_desc = []

        for idx, item in enumerate(batch):
            try:
                img_resp = requests.get(item["url"], timeout=15)
                img_resp.raise_for_status()
                mime = img_resp.headers.get("content-type", "image/jpeg").split(";")[0]
                if not mime.startswith("image/"):
                    mime = "image/jpeg"
                b64_data = base64.b64encode(img_resp.content).decode("utf-8")
                parts.append({"inline_data": {"mime_type": mime, "data": b64_data}})
                meta_desc.append(f"Obraz {idx + 1}: sklep {item['shop']}, strona {item['page']}")
            except Exception as e:
                print(f"  ! Nie udało się pobrać obrazu {item['url']}: {e}")

        if not parts:
            continue

        prompt = (
            "Odczytaj WSZYSTKIE produkty spożywcze oraz ich ceny ze załączonych stron gazetek promocyjnych.\n"
            f"Kontekst obrazów: {'; '.join(meta_desc)}.\n"
            "Zwróć WYŁĄCZNIE poprawny JSON w postaci listy obiektów:\n"
            '[{"shop": "Biedronka", "title": "Pierś z kurczaka 1 kg", "price": 14.99, "old_price": 23.99}]\n'
            "Zasady:\n"
            "1. Do pola 'title' wpisz nazwę produktu ORAZ gramaturę/pojemność, jeśli jest widoczna (np. '500 g', '1 kg', '200 ml', '1 l').\n"
            "2. 'price' to aktualna cena promocyjna (liczba zmiennoprzecinkowa, np. 9.99).\n"
            "3. 'old_price' to cena regularna/przed obniżką (jeśli brak na grafice, wpisz null).\n"
            "4. Pomijaj narzędzia, ubrania, elektronikę i zabawki — interesuje nas żywność, napoje i podstawowe artykuły kuchenne.\n"
        )
        parts.insert(0, {"text": prompt})

        try:
            resp = requests.post(
                url,
                json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=45,
            )
            resp.raise_for_status()
            raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw_text)
            if isinstance(parsed, list):
                print(f"  -> Gemini Vision odczytało {len(parsed)} produktów z paczki obrazów {i // batch_size + 1}.")
                all_extracted.extend(parsed)
        except Exception as e:
            print(f"  ! Błąd Gemini Vision OCR: {e}")

    return all_extracted


def main():
    print(f"Start scrapera gazetek (Gemini Vision OCR) dla domu: {HOUSEHOLD_ID}")
    house_ref = db.collection("households").document(HOUSEHOLD_ID)

    tracked = [{"id": d.id, **d.to_dict()} for d in house_ref.collection("tracked_products").stream()]
    ingredients = [{"id": d.id, **d.to_dict()} for d in house_ref.collection("ingredients").stream()]

    page_images = collect_leaflet_page_images(max_pages_per_store=6)
    print(f"Łącznie pobrano {len(page_images)} stron gazetek do analizy.")

    raw_offers = parse_images_with_gemini_vision(page_images)

    # Deduplikacja
    unique_offers = {}
    for item in raw_offers:
        title = str(item.get("title") or "").strip()
        shop = str(item.get("shop") or "Gazetka").strip()
        try:
            price = round(float(item.get("price")), 2)
        except (TypeError, ValueError):
            continue

        if not title or price <= 0.1 or price > 300:
            continue

        old_p = None
        if item.get("old_price") is not None:
            try:
                old_p = round(float(item.get("old_price")), 2)
            except (TypeError, ValueError):
                old_p = None

        key = (shop.lower(), normalize_text(title), price)
        unique_offers[key] = {
            "shop": shop,
            "title": title,
            "price": price,
            "old_price": old_p,
        }

    offers_list = list(unique_offers.values())
    print(f"Łącznie wyodrębniono {len(offers_list)} unikalnych produktów z gazetek.")

    with open("ostatnia_gazetka.json", "w", encoding="utf-8") as f:
        json.dump(offers_list, f, ensure_ascii=False, indent=2)

    pending_ref = house_ref.collection("pending_deals")
    saved_count = 0

    for offer in offers_list:
        norm_offer = normalize_text(offer["title"])
        pack_str, unit_price, base_unit = extract_unit_price(offer["title"], offer["price"])

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
        base_price = (
            float(matched.get("price") or matched.get("targetPrice") or 0)
            if matched
            else (offer["old_price"] or 0.0)
        )
        compare_price = unit_price if (unit_price and base_price > 12.0) else offer["price"]

        discount_pct = 0
        if base_price > 0 and compare_price < base_price:
            discount_pct = round(((base_price - compare_price) / base_price) * 100)

        unit_info = f" ({pack_str} • {unit_price:.2f} zł/{base_unit})" if unit_price else ""
        pending_ref.add({
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
        })
        saved_count += 1

    house_ref.set({"lastScraped": datetime.now().strftime("%d.%m.%Y %H:%M")}, merge=True)
    print(f"Zakończono! Wysłano {saved_count} pozycji z całej gazetki do Firestore.")


if __name__ == "__main__":
    main()