# 🍳 KuchniaBudżet PRO — Wspólna Spiżarnia, Planer Obiadów & Cennik AI

**KuchniaBudżet PRO** to aplikacja webowa (SPA) typu *multi-tenant* stworzona do wspólnego zarządzania domową kuchnią, budżetem spożywczym oraz zapasami w czasie rzeczywistym (synchronizacja Live Sync pomiędzy wieloma urządzeniami domowników).

Aplikacja działa w architekturze bezserwerowej (*Serverless*) w oparciu o **Firebase Firestore**, **Firebase Authentication** oraz **Google Gemini AI (Vision & Text)**.

---

## 📱 Instrukcja obsługi dla Domowników (Jak korzystać na co dzień?)

Aplikacja działa na telefonie i komputerze — wszystko, co kliknie jedna osoba, w ułamku sekundy pojawia się u drugiej.

### 1. Pierwsze uruchomienie i połączenie telefonów
1. Otwórz link do aplikacji w przeglądarce (na telefonie warto kliknąć *„Dodaj do ekranu głównego”*, żeby działała jak zwykła apka).
2. Wybierz opcję **Dołącz do istniejącej kuchni**, wpisz nasz **6-znakowy Kod Kuchni** i kliknij **Wejdź do kuchni**.
3. Gotowe! Urządzenia są połączone na stałe. (Swój kod możesz w każdej chwili skopiować przyciskiem **📋 Kopiuj** w menu).

### 2. Dodawanie przepisów z linku (AI) lub z głowy
Nie trzeba przepisywać przepisów ręcznie!
1. Kliknij zielony przycisk **+ Przepis** (w prawym górnym rogu na telefonie lub na dole lewego menu na komputerze).
2. **Import z linku (URL):** Wklej adres strony z przepisem (np. z Kwestii Smaku, AniGotuje, Jadłonomii) w pole **Opcja A: Wklej link do przepisu** i kliknij **Pobierz z linku**. Sztuczna inteligencja sama wejdzie na stronę, wyciągnie tytuł, składniki z gramaturami, kroki przygotowania oraz oszacuje ceny!
3. **Pomysł lub wklejony tekst:** Możesz też w **Opcji B** po prostu napisać np. *"Zapiekanka makaronowa z tuńczykiem i kukurydzą"* albo wkleić skopiowany tekst — AI ułoży z tego gotowy przepis.

### 3. Skanowanie paragonów telefonem (Aktualizacja Cennika & Spiżarni)
Po powrocie ze sklepu (Lidl, Biedronka, Netto, Frisco) nie musisz wpisywać cen ani zakupów ręcznie:
1. Wejdź w zakładkę **Cennik & Paragon AI**.
2. Kliknij **📸 Wgraj zdjęcie paragonu** i zrób zdjęcie paragonu aparatem (lub wybierz je z galerii).
3. AI samo odczyta produkty spożywcze (pomijając chemię i reklamówki), przeliczy wielosztuki i wagę na **cenę za 1 sztukę / 1 kg** i pokaże podsumowanie.
4. Upewnij się, że zaznaczony jest checkbox **„Dodaj też kupione ilości do Spiżarni / Lodówki”** i kliknij **✓ Zapisz zaznaczone w Cenniku**. Ceny przepisów od razu się zaktualizują, a kupione produkty trafią do naszych zapasów!

### 4. Spiżarnia, Lodówka & Zamrażarka („Co mam w domu?”)
W zakładce **Spiżarnia & Zamrażarka** kontrolujemy, co mamy na stanie:
* **Dodawanie produktów:** Wpisz nazwę na górze (nie musisz martwić się o literówki czy polskie znaki — np. *"piers z kurczaka"* apka sama poprawi na *"Pierś z kurczaka"*), wybierz ilość, jednostkę (`szt.`, `g`, `kg`, `l`) oraz miejsce (**🧊 Lodówka** lub **🥫 Spiżarnia**).
* **Zmiana ilości:** Przy każdym posiadanym produkcie możesz klikać **`−`** i **`+`** lub wpisać dokładną ilość po zużyciu części opakowania.
* **❄️ Zamrażarka (Gotowe dania):** W niebieskiej sekcji na górze wpisujemy ugotowane obiady schowane na później (np. *„Chili con carne — 4 porcje”*). Gdy wyjmiemy pudełko na obiad, klikamy **`−`**, żeby odjąć porcję. (Możesz też wrzucić nadwyżkę do zamrażarki jednym kliknięciem z okna przepisu przyciskiem **❄️ Zamroź porcje**).
* **Podpowiedzi obiadów:** Poniżej aplikacja sama segreguje przepisy na **Gotowe do zrobienia (100% w domu)** oraz **Prawie gotowe (brakuje 1–2 rzeczy)**.

### 5. Wspólna Lista Zakupów
* Przy dowolnym przepisie kliknij **+ Zakupy**, a brakujące składniki (których nie ma w Spiżarni) same wpadną na **Listę Zakupów** wraz z szacunkowym kosztem koszyka.
* W sklepie odhaczasz włożone do koszyka rzeczy, a po powrocie do domu klikasz jeden przycisk: **✓ Przenieś kupione do Spiżarni** — zakupy znikają z listy i lądują w domowych zapasach.

### 6. Ocenianie obiadów i liczenie kosztu 1 porcji
* Po zjedzeniu obiadu wejdź w przepis i kliknij **⭐ Oceń** (*Ugotowane! Oceń i rozlicz*).
* Wpisz kwotę z paragonu, na ile obiadów dla dwojga wystarczyło jedzenie oraz ocenę (1–5 gwiazdek). W zakładce **Historia & Koszt Porcji** apka wyliczy, ile realnie kosztuje nas 1 porcja obiadu na osobę.

---

## ✅ Co już działa (Podsumowanie techniczne)

### 1. Architektura Multi-Tenant & Panel Administratora (`#admin`)
* **Izolacja danych po Kodzie Kuchni:** Każde gospodarstwo domowe posiada własny, odizolowany dokument w bazie (`kuchnie/{kodKuchni}`) zabezpieczony regułami Firestore Security Rules.
* **Ekran powitalny:** Możliwość utworzenia nowej kuchni (automatyczne generowanie 6-znakowego kodu dostępu i pakietu startowego 15 przepisów) lub dołączenia do istniejącej kuchni za pomocą kodu.
* **Panel Administratora (`#admin`):** Chroniony logowaniem e-mail/hasło (Firebase Auth) widok pozwalający na podgląd wszystkich utworzonych kuchni, blokowanie/odblokowywanie dostępu (`active: true/false`), podgląd zawartości danej kuchni oraz jej trwałe usunięcie.

### 2. Domowa Spiżarnia, Lodówka & Zamrażarka
* Zarządzanie ilościami (`−` / `+`), jednostkami (`szt.`, `g`, `kg`, `ml`, `l`, `opak.`, `puszka`) oraz lokalizacją (**Lodówka** / **Spiżarnia**) z autokorektą nazw.
* Ewidencja zamrożonych porcji gotowych dań oraz automatyczne dopasowanie przepisów do posiadanych zapasów.

### 3. Przepisy, Import z Linku & Rozliczanie Kosztów
* Wycena dań na żywo na podstawie Cennika, import przepisów z adresów URL (przez Gemini AI oraz lokalny parser fallbackowy) oraz dziennik kosztów porcji.

### 4. Cennik Bazowy & Skaner Paragonów AI (OCR)
* Cennik z jednostkami opakowań (`1 puszka`, `1 kg`, `1 szt.`, `1 opak.`, `1 l`, `500 g`) oraz skanowanie paragonów ze zdjęć przez **Gemini Vision**.

### 5. Wspólna Lista Zakupów
* Automatyczne dodawanie brakujących składników z przepisów, podliczanie kosztu koszyka oraz przenoszenie kupionych produktów do Spiżarni.

---

## 🚧 W budowie / Planowane usprawnienia (Roadmap)

Poniższe moduły są obecnie na etapie testów lub wdrożenia i wymagają dalszych prac:

1. **Automatyczne odejmowanie składników ze spiżarni po ugotowaniu (`deductRecipeFromPantry`):**
   * *Status:* Zaprojektowano logikę przeliczania gramatur (`g` ↔ `kg`, `ml` ↔ `l`) oraz blokadę przycisku *„Ugotowane!”* w przypadku braku składników w spiżarni — **wymaga wpięcia do głównego pliku `index.html`**.
2. **Automatyczny Scraper Gazetek Promocyjnych (`scraper.py` + GitHub Actions):**
   * *Status:* Wstrzymany / w przebudowie. Polskie agregatory gazetek (Blix, Ding) serwują oferty wyłącznie jako obrazy stron (JPG/WEBP), a nie czysty JSON. Docelowo robot w GitHub Actions będzie pobierał obrazy stron aktualnych gazetek (Lidl, Biedronka, Netto) i odczytywał je przez **Gemini Vision OCR** do zakładki *Weryfikacja Scrapera*.
3. **Radar Śledzonych Produktów & Weryfikacja Scrapera:**
   * *Status:* Interfejs w aplikacji jest gotowy i połączony z bazą, oczekuje na docelowe podpięcie stabilnego źródła danych z robota cenowego oraz migrację ścieżki zapisu robota z `households/` na nową kolekcję `kuchnie/{kodKuchni}`.
4. **Migracja starych danych (`households` → `kuchnie`):**
   * *Status:* Reguły Firestore zachowują tymczasowo wsteczną kompatybilność ze starą kolekcją `households`. Po przeniesieniu danych docelowo zostanie ona wyłączona.

---

## 🛠️ Konfiguracja i Uruchomienie (Dla Administratora)

### 1. Hosting (GitHub Pages)
Aplikacja składa się z pojedynczego pliku `index.html` (HTML + Tailwind CSS CDN + Firebase SDK v11 ES Modules) i nie wymaga procesu budowania (*build step*). Wystarczy opublikować repozytorium przez **GitHub Pages**.

### 2. Konfiguracja Firebase
1. **Authentication:** Włącz dostawcę **Email/Password** i utwórz konto administratora w zakładce *Users*. W *Settings → Authorized domains* dodaj domenę swojego GitHub Pages.
2. **Firestore Security Rules:** Wdróż reguły izolujące dokumenty w kolekcji `kuchnie/{kodKuchni}` (z blokadą zapisu, gdy `active == false`, oraz pełnymi uprawnieniami dla zalogowanego administratora).
3. **Klucz Google Gemini API:** Klucz nie jest przechowywany w kodzie źródłowym repozytorium. Wpisuje się go jednorazowo w aplikacji (*Ustawienia → Klucz AI*), skąd synchronizuje się wyłącznie wewnątrz prywatnego dokumentu danej kuchni.