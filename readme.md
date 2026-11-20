# 🍳 KuchniaBudżet PRO

**KuchniaBudżet PRO** to domowy asystent gotowania, spiżarni i zakupów, który działa na żywo między wszystkimi domownikami (bez zakładania kont i haseł). Pomaga gotować z tego, co już masz w domu, planować obiady na cały tydzień, skanować paragony ze zdjęć i automatycznie wyłapywać promocje na jedzenie z **Lidla, Biedronki i Netto**.

---

## 🚀 Jak zacząć korzystać? (Podstawowa instrukcja)

### Krok 1: Utwórz kuchnię lub dołącz do domowników
1. Otwórz aplikację w przeglądarce (na komputerze lub telefonie).
2. Kliknij **„✨ Utwórz kuchnię”** — aplikacja wygeneruje unikalny **6-znakowy kod kuchni** (np. `8CXHKH`) i wgra 15 sprawdzonych, tanich przepisów na start.
3. Wyślij ten 6-znakowy kod domownikom — gdy wpiszą go w polu **„Dołącz do istniejącej kuchni”**, będziecie widzieć tę samą spiżarnię, plan posiłków i listę zakupów w czasie rzeczywistym.

### Krok 2: Uzupełnij to, co masz w domu (Spiżarnia, Lodówka, Zamrażarka)
1. Wejdź w zakładkę **Spiżarnia & Zamrażarka**.
2. Dodaj produkty, które masz już w szafkach i lodówce (apka sama poprawia literówki i polskie znaki).
3. W sekcji **Zamrażarka** wpisz ugotowane porcje obiadów schowane „na czarną godzinę”.

### Krok 3: Wybierz obiad i gotuj bez marnowania jedzenia
1. W zakładce **Przepisy & Społeczność** włącz filtr **„🥫 Z tego co mam”** — zobaczysz dania, do których masz 100% składników w domu (lub brakuje Ci tylko 1–2 rzeczy).
2. Brakujące składniki wrzucisz jednym kliknięciem na **Listę Zakupów**.
3. Po ugotowaniu kliknij **„🍳 Ugotowane!”**, wpisz kwotę z paragonu i liczbę porcji — aplikacja sama **odejmie zużyte składniki ze spiżarni** i policzy realny koszt 1 porcji na osobę.

### Krok 4: Zbieraj promocje i skanuj paragony
1. W zakładce **Weryfikacja Scrapera** codziennie rano czekają świeże promocje z Lidla, Biedronki i Netto (filtrowane po sklepie, dziale jedzenia i dacie ważności).
2. Kliknij **„🛒 + Zakupy”**, aby wrzucić okazję na Listę Zakupów razem z informacją, do kiedy trwa promocja, albo **„✓ Zatwierdź do Cennika”**.
3. Po zakupach zrób zdjęcie paragonu w zakładce **Cennik & Paragon AI** (wymaga darmowego klucza Google Gemini API wpisanego w *Nazwa & Klucz AI*) — AI odczyta ceny żywności i automatycznie uzupełni Twoją spiżarnię.

---

## ✨ Wszystkie funkcje aplikacji

### 1. Wspólna Kuchnia w czasie rzeczywistym (Multi-Tenant)
* **Logowanie samym 6-znakowym kodem:** Zero rejestracji e-mailem czy haseł dla domowników.
* **Synchronizacja na żywo (Firebase Firestore):** Zmiany na liście zakupów czy w spiżarni pojawiają się u wszystkich domowników w ułamku sekundy.
* **Własna nazwa kuchni:** Możesz ustawić nazwę swojego domu (np. *Kuchnia Kowalskich*), widoczną w nagłówku i przy udostępnianych przepisach.
* **Wygodny tryb mobilny (iPhone / Android):** Dolny pasek nawigacji z 5 głównymi sekcjami, wysuwana szuflada *„Więcej”* oraz blokada przypadkowego zoomowania ekranu przy wpisywaniu danych.

### 2. Książka Kucharska, Import z Linków, AI i Społeczność
* **15 gotowych przepisów na start:** Tanie, sycące obiady, zupy i śniadania z gotowymi składnikami i krokami.
* **Import przepisów z linku (URL):** Wklejasz link do przepisu z internetu (np. Kwestia Smaku), a aplikacja sama pobiera tytuł, składniki i instrukcję (działa zarówno z AI, jak i wbudowanym parserem lokalnym).
* **Generator przepisów AI i edycja:** Możesz wygenerować przepis z krótkiego pomysłu, wpisać go ręcznie lub edytować istniejący przepis (np. zamieniając drogi składnik na tańszy).
* **Społeczność kuchni:** Jednym kliknięciem udostępniasz swoje przepisy innym użytkownikom aplikacji i zapisujesz u siebie przepisy innych kuchni.
* **Kopia zapasowa (JSON i TXT):** Eksport wszystkich przepisów do pliku zapasowego JSON (do przywrócenia 1:1) lub czytelnego pliku tekstowego TXT.

### 3. Inteligentny Przelicznik Kosztów i Jednostek Kulinarnych
* **Przeliczanie ułamków opakowań:** Aplikacja wie, że **4 kromki chleba** to 1/4 bochenka, **2 ząbki czosnku** to 1/5 główki, a **1 cebula** to ok. 130 g z kilograma — dzięki czemu wylicza realny koszt dania, a nie cenę całych opakowań.
* **Zero zawyżania przez przyprawy:** Sól, pieprz, zioła, przyprawy sypkie, woda i olej do smażenia są automatycznie wyceniane na `0.00 zł` i nie blokują możliwości ugotowania obiadu.

### 4. Spiżarnia, Lodówka i Zamrażarka
* **Podział na Lodówkę i Spiżarnię:** Kontrola dokładnych ilości (`g`, `kg`, `ml`, `l`, `szt.`, `puszka`, `opak.`) z automatyczną poprawą literówek.
* **Automatyczne odejmowanie po gotowaniu:** Zatwierdzenie ugotowania dania automatycznie zmniejsza stan składników w domu.
* **Ewidencja Zamrażarki:** Osobna lista gotowych, zamrożonych porcji dań (np. *Chili con carne – 4 porc.*, *Pierogi – 6 porc.*) z szybkim odejmowaniem po wyjęciu pudełka.

### 5. Tygodniowy Planer Posiłków i Budżet Tygodnia
* **Plan na 7 dni (Poniedziałek – Niedziela):** Przypisujesz **Śniadanie**, **Obiad** i **Kolację** do każdego dnia tygodnia.
* **Koszt tygodnia z góry:** Podsumowanie łącznego kosztu wyżywienia na cały tydzień oraz na każdy pojedynczy dzień.
* **Zakupy na cały tydzień jednym kliknięciem:** Aplikacja sumuje składniki z całego planu, odejmuje to, co już masz w spiżarni, i wrzuca wyłącznie brakujące opakowania na Listę Zakupów.

### 6. Cennik Bazowy & Skaner Paragonów AI
* **Odczyt paragonu ze zdjęcia:** AI ignoruje chemię, kosmetyki, reklamówki i rabaty, wyłapując **wyłącznie artykuły spożywcze**.
* **Czyszczenie nazw marek:** Zamienia długie nazwy paragonowe (np. *„MASŁO EKSTRA MLEKOVITA 200G”*) na czyste nazwy ogólne (***„Masło”***), wyciągając cenę za 1 jednostkę (`1 kg`, `1 szt.`, `10 szt.` dla jajek).
* **Automatyczne zatowarowanie domu:** Jednym zaznaczeniem dodajesz wszystkie kupione produkty z paragonu prosto do Spiżarni i Lodówki.

### 7. Automatyczny Scraper Promocji (Lidl, Biedronka, Netto) + Poczekalnia
* **Codzienna aktualizacja w tle:** Skrypt `scraper.py` uruchamia się automatycznie raz dziennie przez GitHub Actions, skanuje aktualne gazetki (z pominięciem blogów, kosmetyków i słodyczy) i wysyła czyste okazje żywnościowe do wszystkich aktywnych kuchni.
* **Zaawansowane filtrowanie w Poczekalni (`Weryfikacja Scrapera`):**
  * po sklepie (`Lidl`, `Biedronka`, `Netto`),
  * po dziale jedzenia (`Mięso i wędliny`, `Nabiał i jaja`, `Warzywa i owoce`, `Pieczywo`, `Suche i konserwy`, `Ryby`, `Tłuszcze`),
  * po zakresie dat (`Ważne dzisiaj`, `Kończą się do 3 dni`, `Ten tydzień` lub własny zakres z kalendarza),
  * po nazwie produktu.
* **Wysyłka prosto na Listę Zakupów z datą ważności:** Przycisk **„🛒 + Zakupy”** przenosi okazję na Listę Zakupów z widoczną plakietką sklepu i terminem obowiązywania promocji (w tym ostrzeżeniem, gdy dziś jest ostatni dzień promki).

### 8. Wspólna Lista Zakupów i Historia Wydatków
* **Grupowanie działami sklepowymi:** Produkty układają się kategoriami z podsumowaniem szacunkowej wartości koszyka.
* **Przenoszenie zakupów do Spiżarni:** Odhaczone produkty jednym przyciskiem trafiają do domowych zapasów.
* **Historia wydatków:** Statystyki wydatków z ostatnich 7 dni, bieżącego miesiąca i łącznie, wraz z podglądem pojedynczych paragonów i zakupów.

### 9. Dziennik Ugotowanych Dań, Oceny i Koszt Porcji
* **Rzeczywisty koszt porcji:** Historia wszystkich ugotowanych obiadów z wyliczeniem średniego kosztu 1 porcji na osobę, oceną smaku (1–5 gwiazdek) i notatkami na przyszłość.

### 10. Zgłaszanie Pomysłów & Panel Administratora
* **Zakładka „Zgłoś Pomysł / Błąd”:** Użytkownicy mogą zgłaszać propozycje nowych funkcji i śledzić status ich wdrożenia.
* **Panel Administratora (`#admin`):** Zabezpieczony logowaniem Firebase Auth panel do podglądu zarejestrowanych kuchni, zarządzania dostępem oraz przeglądania zgłoszeń od użytkowników.

---

## 🛠️ Konfiguracja techniczna (dla właściciela projektu)

* **Frontend:** Pojedynczy plik statyczny `index.html` (Tailwind CSS + Firebase SDK v11 — Firestore & Auth), gotowy do hostowania na GitHub Pages, Vercel lub Netlify.
* **Scraper (`scraper.py`):** Python 3.9+, `requests`, `beautifulsoup4`, `firebase-admin`.
* **Automatyzacja (`.github/workflows/`):** Codzienne uruchamianie przez `cron: '0 5 * * *'` z wykorzystaniem sekretu repozytorium `FIREBASE_SERVICE_ACCOUNT`.
