from __future__ import annotations

import os
import re
import csv
import sys
import json
import time
import hashlib
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
    "/polityka", "/o-nas", "/kariera", "/faq", "/godziny-otwarcia", "/sklepy-w-",
    "archiwaln"
]

# Znane składniki kulinarne (do kanonicznego ujednolicania nazw + priorytetu, jeśli pasują)
CORE_CULINARY_ITEMS = {
    "piers_z_kurczaka": ("Pierś z kurczaka", "Mięso i świeże", ["piers z kurczaka", "filet z kurczaka", "filet z piersi"], ["przypraw", "wedlin", "szynk", "pasztet", "parowk", "kabanos", "panier", "nuggets", "strips", "paski", "konserw", "salatk", "karma"], 8.00, 28.00),
    "mieso_mielone": ("Mięso mielone", "Mięso i świeże", ["mieso mielone", "mielone wieprzow", "mielone wolow", "mielone drobiow"], ["przypraw", "fix", "pomysl na", "sos", "pierogi", "krokiety", "nalesniki"], 5.00, 18.00),
    "schab": ("Schab wieprzowy", "Mięso i świeże", ["schab wieprzow", "schab bez kosci", "schab ze"], ["wedlin", "szynk", "pieczon", "wedzon", "konserw"], 9.00, 26.00),
    "karkowka": ("Karkówka wieprzowa", "Mięso i świeże", ["karkowk"], ["wedlin", "szynk", "pieczon", "wedzon"], 9.00, 26.00),
    "kielbasa": ("Kiełbasa śląska", "Mięso i świeże", ["kielbasa slaska", "kielbasa podwawelska", "kielbasa zwyczajna"], ["sucha", "krakowska", "zywiecka", "salami", "kabanos"], 5.00, 26.00),
    "boczek": ("Wędzony boczek", "Mięso i świeże", ["boczek wedzon", "boczek surowy"], ["chips", "chrupk", "przypraw"], 4.50, 35.00),
    "losos": ("Łosoś filet", "Mięso i świeże", ["losos filet", "filet z lososia", "losos swiezy", "losos atlantycki"], ["salatk", "pasta", "karma"], 10.00, 55.00),
    "dorsz": ("Dorsz filet", "Mięso i świeże", ["dorsz", "filet z dorsza"], ["salatk", "pasta"], 7.00, 42.00),
    "tunczyk": ("Tuńczyk w puszce", "Konserwy i słoiki", ["tunczyk w", "tunczyk kawalki", "tunczyk rozdrobniony", "filet z tunczyka"], ["pesto", "sos", "salatk", "pasta", "karma", "dla kota", "makaron"], 2.50, 11.00),
    "maslo": ("Masło", "Lodówka i mrożonki", ["maslo ekstra", "maslo polskie", "maslo 82", "maslo 83", "maslo"], ["orzech", "roslinn", "margaryn", "mix", "krem", "balsam", "do ciala", "shea", "czekolad"], 3.00, 11.00),
    "mleko": ("Mleko", "Lodówka i mrożonki", ["mleko uht", "mleko swieze", "mleko 3,2", "mleko 2%", "mleko"], ["kokos", "sojow", "owsian", "migdal", "zageszczon", "skondensowan", "w proszku", "czekolad", "do demakijazu", "balsam", "modifikowan", "bebiko", "nan", "ptasie"], 1.50, 5.50),
    "jajka": ("Jajka", "Lodówka i mrożonki", ["jajka", "jaja sciolkow", "jaja z wolnego", "jaja klasa"], ["niespodziank", "czekolad", "makaron", "majonez", "kinder"], 4.00, 16.00),
    "ser_zolty": ("Ser żółty", "Lodówka i mrożonki", ["ser zolty", "ser gouda", "ser edam", "ser edamski", "ser morski", "ser ementaler", "gouda"], ["topion", "plesniow", "feta", "twarog", "wiejski", "mascarpone", "deser", "sernik", "serduszk"], 3.50, 32.00),
    "twarog": ("Twaróg", "Lodówka i mrożonki", ["twarog poltlusty", "twarog chudy", "twarog tlusty", "twarog sernikowy", "twarog"], ["deser", "danio", "sernik", "baton"], 2.00, 16.00),
    "serek_wiejski": ("Serek wiejski", "Lodówka i mrożonki", ["serek wiejski"], ["deser"], 1.40, 5.00),
    "jogurt_naturalny": ("Jogurt naturalny", "Lodówka i mrożonki", ["jogurt naturalny", "jogurt grecki"], ["owocow", "pitny", "deser", "stracciatella", "czekolad"], 1.00, 7.00),
    "smietana": ("Śmietana", "Lodówka i mrożonki", ["smietana 18", "smietana 12", "smietanka 30"], ["deser", "spray", "w sprayu"], 1.40, 7.50),
    "mozzarella": ("Mozzarella", "Lodówka i mrożonki", ["mozzarella"], ["paluszki", "panier", "pizza"], 1.80, 8.00),
    "ryz": ("Ryż", "Suche i makarony", ["ryz bialy", "ryz basmati", "ryz jasminowy", "ryz parboiled", "ryz w woreczkach"], ["preparowan", "wafle", "mleczn", "deser", "belriso", "muller"], 1.80, 9.00),
    "makaron": ("Makaron", "Suche i makarony", ["makaron penne", "makaron spaghetti", "makaron swiderki", "makaron fusilli", "makaron lubella", "makaron"], ["zupa", "blyskawiczn", "chinski", "kubek"], 1.80, 8.50),
    "kasza": ("Kasza pęczak / gryczana", "Suche i makarony", ["kasza peczak", "kasza gryczana", "kasza jaglana"], ["kaszka", "dla dzieci", "mleczno"], 1.80, 8.50),
    "czerwona_fasola": ("Czerwona fasola", "Konserwy i słoiki", ["fasola czerwona", "czerwona fasola"], ["po bretonsku", "zupa", "salatk"], 1.80, 6.00),
    "biala_fasola": ("Biała fasola", "Konserwy i słoiki", ["fasola biala", "biala fasola"], ["po bretonsku", "zupa"], 1.80, 6.00),
    "kukurydza": ("Kukurydza konserwowa", "Konserwy i słoiki", ["kukurydza konserwowa", "kukurydza zlocista", "kukurydza w puszce"], ["chrupki", "popcorn", "platki"], 1.80, 6.00),
    "passata_pomidorowa": ("Passata pomidorowa", "Konserwy i słoiki", ["passata", "przecier pomidorowy"], ["zupa", "krem"], 2.00, 7.50),
    "pomidory_krojone": ("Pomidory krojone", "Konserwy i słoiki", ["pomidory krojone", "pomidory pelati", "pomidory w puszce"], ["suszone", "zupa"], 2.00, 6.50),
    "ziemniaki": ("Ziemniaki", "Warzywa i owoce", ["ziemniaki"], ["frytki", "chipsy", "placki", "puree", "klusk"], 1.00, 9.00),
    "cebula": ("Cebula", "Warzywa i owoce", ["cebula"], ["prazona", "suszon", "krazki", "zupa"], 1.20, 8.00),
    "czosnek": ("Czosnek", "Warzywa i owoce", ["czosnek"], ["granulowan", "suszon", "sos", "bagietk", "maslo"], 1.00, 7.00),
    "pomidory": ("Pomidory", "Warzywa i owoce", ["pomidory malinowe", "pomidory rzymskie", "pomidory koktajlowe", "pomidory galazka", "pomidory"], ["passata", "koncentrat", "krojone", "suszone", "ketchup", "sok", "zupa"], 2.50, 18.00),
    "papryka": ("Papryka", "Warzywa i owoce", ["papryka czerwona", "papryka zolta", "papryka zielona", "papryka"], ["mielona", "slodka", "ostra", "wedzona", "przypraw", "chipsy"], 3.50, 18.00),
    "ogorek": ("Ogórek", "Warzywa i owoce", ["ogorek zielony", "ogorki gruntowe", "ogorek szklarniowy", "ogorki"], ["kiszon", "konserwow", "salatk"], 2.00, 14.00),
    "marchew": ("Marchew", "Warzywa i owoce", ["marchew", "marchewka"], ["sok", "kubus", "zupa", "groszek z"], 1.20, 7.00),
    "pieczarki": ("Pieczarki", "Warzywa i owoce", ["pieczarki"], ["zupa", "sos", "marynowan"], 2.50, 14.00),
    "brokul": ("Brokuł", "Warzywa i owoce", ["brokul", "brokuly"], ["zupa", "krem"], 2.50, 10.00),
    "kalafior": ("Kalafior", "Warzywa i owoce", ["kalafior"], ["zupa"], 3.00, 11.00),
    "cukinia": ("Cukinia", "Warzywa i owoce", ["cukinia"], ["leczo"], 2.50, 11.00),
    "kapusta": ("Kapusta", "Warzywa i owoce", ["kapusta biala", "kapusta mloda", "kapusta pekinska"], ["kiszona", "zasma"], 1.80, 9.00),
    "banany": ("Banany", "Warzywa i owoce", ["banany"], ["chipsy", "suszon", "jogurt", "deser", "sok"], 2.20, 8.50),
    "jablka": ("Jabłka", "Warzywa i owoce", ["jablka"], ["sok", "mus", "chipsy", "ocet", "cydr", "szarlotk"], 1.50, 7.50),
    "cytryny": ("Cytryny", "Warzywa i owoce", ["cytryny"], ["sok", "herbata", "napoj"], 2.50, 11.00),
    "mandarynki": ("Mandarynki", "Warzywa i owoce", ["mandarynki"], ["puszk", "sok"], 3.00, 11.00),
    "pomarancze": ("Pomarańcze", "Warzywa i owoce", ["pomarancze"], ["sok", "napoj"], 3.00, 11.00),
    "borowki": ("Borówki amerykańskie", "Warzywa i owoce", ["borowki", "borowka amerykanska"], ["jogurt", "dzem", "sok"], 3.50, 16.00),
    "winogrona": ("Winogrona", "Warzywa i owoce", ["winogrona", "winogrono"], ["sok", "wino"], 4.50, 17.00),
    "oliwa": ("Oliwa z oliwek", "Przyprawy i dodatki", ["oliwa z oliwek"], ["balsam", "krem", "mydlo", "szampon"], 10.00, 42.00),
    "olej": ("Olej rzepakowy", "Przyprawy i dodatki", ["olej rzepakowy", "olej slonecznikowy"], ["silnikow", "do ciala", "olejek"], 4.00, 14.00),
}

# Twarde odrzucanie artykułów niespożywczych, chemii, alkoholu, słodyczy (bez chipsów i energetyków) oraz śmieci UI
NON_FOOD_AND_UI_NOISE = [
    # Kosmetyki, chemia, higiena
    "blyszczyk", "pomadk", "szmink", "tusz do rzes", "podklad", "puder", "krem do", "balsam",
    "chusteczk", "papier toaletowy", "recznik papierowy", "szampon", "zel pod prysznic",
    "mydlo", "pasta do zebow", "szczoteczk", "dezodorant", "antyperspirant", "perfum",
    "woda toaletowa", "woda po goleniu", "balsam po goleniu", "pianka do golenia", "maszynka do golenia",
    "str8", "axe", "old spice", "nivea", "dove", "fa ", "rexona", "garnier", "l'oreal", "loreal",
    "zestaw kosmetykow", "zestaw prezentowy", "zestaw str8", "zestaw axe", "zestaw nivea", "zestaw dove",
    "proszek do prania", "plyn do", "kapsulki do", "domestos", "wybielacz", "odplamiacz",
    "gabka", "zmywak", "folia aluminiowa", "papier do pieczenia", "worki na smieci",
    # Zwierzęta, dzieci, książki, zabawki, dom, elektronika
    "karma dla", "zwirek", "pieluchy", "pampers", "smoczek", "butelka dla",
    "ksiazka", "ksiazeczka", "kolorowank", "bajk", "historyjk", "katalog", "czasopismo", "gazeta",
    "koszulka", "t-shirt", "spodnie", "skarpetk", "majtki", "biustonosz", "kurtka", "buty",
    "kapcie", "klapki", "pizama", "sukienka", "bluza", "sweter", "legginsy", "rajstopy",
    "posciel", "przescieradlo", "koc ", "poduszka", "recznik kapielowy", "dywanik", "obrus", "bieznik", "firank", "zaslon",
    "patelnia", "garnek", "zestaw garnkow", "pojemnik", "szczotka", "mop ", "wiadro",
    "wiertarka", "wkretarka", "szlifierka", "mlotek", "klucz ", "baterie", "zarowka",
    "lampka", "latarka", "kabel", "ladowarka", "sluchawki", "glosnik", "powerbank", "smartwatch",
    "doniczka", "ziemia ogrodowa", "kosiarka", "sekator", "zabawka", "klocki", "lalka", "pluszak", "gra planszowa",
    "znicz", "wklad do znicza", "kwiaty", "bukiet", "roslina", "storczyk", "tulipan", "aranzacja w szkle", "dekoracj",
    "dyfuzor", "odswiezacz", "swieca", "swieczk", "olejek zapachowy", "zapach do",
    # Słodycze, ciasta, ciastka, herbaty, kawy, praliny, chipsy, energetyki, napoje
    "czekolad", "bombonierk", "pralin", "lindor", "raffaello", "ferrero", "merci", "toblerone",
    "baton", "wafel", "wafelk", "prince polo", "grzeski", "kitkat", "snickers", "mars", "twix",
    "ciastk", "ciasteczk", "ciasto", "sernik", "szarlotk", "makowiec", "keks", "babka",
    "herbatnik", "biszkopt", "markiz", "piernik", "delicj", "jezyki",
    "cukierk", "zelk", "lizak", "karmelk", "krowk", "chalw", "sezamk", "piank", "marshmallow",
    "ptasie mleczko", "nutella", "krem czekoladowy", "krem orzechowy",
    "dekoracji cukrow", "dekoracje cukrow", "posypka cukrow", "lukier", "masa cukrow",
    "lody", "lodow", "rozek", "sorbet", "paczek", "donut", "drozdzowk",
    "croissant", "rogali", "babeczk", "muffin", "tort ",
    "chipsy", "chrupki", "prazynki", "popcorn", "paluszki", "krakersy", "nachosy", "lays", "pringles", "crunchips",
    "herbat", "lipton", "dilmah", "saga", "tetley", "earl grey", "yerba", "kawa ", "kawy ", "kawowa ", "kawowy ", "nescafe", "jacobs", "tchibo", "lavazza",
    "napoj", "cola", "pepsi", "fanta", "sprite", "oranzad", "energetyk", "energetyczn",
    "tiger", "red bull", "monster", "black ", "burn ", "oshee", "4move", "izotonik", "tymbark", "kubus", "nektar",
    # Alkohol i wyroby tytoniowe
    "piwo", "wodka", "whisky", "likier", "cydr", "gin ", "rum ", "tequila", "prosecco",
    "szampan", "browar", "harna", "tyskie", "zubr", "zywiec", "lech ", "perla", "heineken",
    "miod pitny", "poltorak", "dwojniak", "trojniak",
    # Dodatkowe wykluczenia z gazetek (sprzęt AGD, dekoracje, słodycze, przyprawy w młynkach, gotowce/fastfood)
    "frytkownica", "blender", "toster", "odkurzacz", "gofrownica", "siekacz", "dzbanek filtrujacy",
    "miska na pranie", "lancuch swietlny", "kurtyna swietlna", "girlanda", "drzewko led", "choinka",
    "dziadek do orzechow", "album na zdjecia", "akcesoria krawieckie", "akcesoria do czyszczenia",
    "akcesoria swiateczne", "opaski zaciskowe", "listki piorace", "calgon", "finish", "pronto",
    "air wick", "pachnaca szafa", "pachnace patyczki", "tolpa", "bielenda", "palette", "farba do wlosow",
    "bizuteria", "skarpety", "skarpetki", "bokserki", "chodaki", "dres ", "materac", "koldra",
    "torba na butelki", "worek na prezenty", "katalog zabawek", "produkty z gazetek",
    "kalendarz adwentowy", "mikolaj z czekolady", "figurka mikolaja", "figurka miko", "poinsecja",
    "cyclamen", "gaultheria", "pinus", "gwiazda betlejemska", "gozdziki carnaval",
    "mlynek z przyprawami", "barwnik spozywczy", "pisaki cukrowe", "pisaki pastelowe", "pisaki shrek",
    "pisaki koci", "aromat do ciast", "cukier wanilinowy", "cukier z wanilia", "cukier ze skorka",
    "polewa ", "masa makowa", "chatka z piernika", "cantuccini", "cannoli", "makaroniki",
    "marmoladki", "beziki", "ptasie mleczko", "krolewskie mleczko", "alpejskie mleczko",
    "krajanka piernikowa", "gwiazdka piernikowa", "warkocz makowy", "ciacho", "cynamonka",
    "malinianka", "kisiel", "granola", "cornflakes", "platki kukurydziane", "mus owocowy",
    "mus jablkowy", "mus bobovita", "przekaska owocowa", "daktyle smakowe", "daktyle suszone",
    "migdaly w ", "migdaly zimowe", "orzechy w czekoladzie", "orzechy laskowe o smaku",
    "pistacje prazone", "pomysl na danie", "panierka do nuggetsow", "zawartosc dla osob pelnoletnich",
    "brandy", "whiskey", "katalog ", "tablet lcd", "aparat natychmiastowy", "mysz bezprzewodowa",
    "hub usb", "przewod ", "pojazd zdalnie", "samochod zdalnie", "hulajnoga", "drewniana kolejka",
    "tor wyscigowy", "ukladanka", "puzzle", "gra karciana", "gra zrecznosciowa", "gry podrozne",
    "zestaw gier", "zestaw zabawek", "zestaw do zabawy", "zestaw kreatywny", "zestaw figurek",
    "zestaw superthings", "karty kolekcjonerskie", "squashi", "maskotka", "telefon chicco",
    "zestaw all'aura", "zestaw big star", "zestaw meski", "zestaw damski", "zestaw gloss",
    # Elementy nawigacji / teksty UI portali gazetek
    "gazetka ", "strona ", "oferta wazna", "wszystkie promocje",
    "sprawdz gazetke", "przejdz do", "pokaz wiecej", "wczytaj wiecej", "nastepna strona",
    "poprzednia strona", "kategoria", "filtry", "sortuj", "regulamin", "polityka prywatnosci",
    "zapisz sie", "newsletter", "aplikacja mobilna", "pobierz aplikacje", "opinie o",
    "godziny otwarcia", "znajdz sklep", "lista zakupow", "cena regularna", "najtansza cena z 30 dni"
]

# BIAŁA LISTA KULINARNA: produkt spoza CORE_CULINARY_ITEMS przejdzie TYLKO wtedy, gdy zawiera słowo prawdziwego jedzenia!
POSITIVE_FOOD_KEYWORDS = re.compile(
    r"\b("
    # Mięso i wędliny
    r"kurczak\w*|indyk\w*|wieprzow\w*|wolow\w*|cielec\w*|kaczk\w*|ges\w*|krolik\w*|"
    r"schab\w*|karkowk\w*|lopatk\w*|szynk\w*|poledwic\w*|boczek|boczku|golonk\w*|zeberk\w*|"
    r"mielon\w*|gulasz\w*|udk\w*|skrzydelk\w*|podudzi\w*|filet\w*|piers\w*|mieso|miesa|"
    r"kielbas\w*|parowk\w*|kabanos\w*|salami|pasztet\w*|kaszank\w*|baleron\w*|karkow\w*|"
    # Ryby i owoce morza
    r"losos\w*|dorsz\w*|tunczyk\w*|sledz\w*|pstrag\w*|makrel\w*|mintaj\w*|morszczuk\w*|"
    r"halibut\w*|sandacz\w*|karp\w*|tilapi\w*|krewetk\w*|kalmar\w*|ryb\w*|"
    # Nabiał i jaja
    r"mleko|mleka|maslo|masla|ser zolty|ser gouda|ser edam\w*|ser mozzarella|ser camembert|ser feta|ser plesniowy|gouda|edam\w*|ementaler\w*|mozzarell\w*|"
    r"twarog\w*|serek|serki|jogurt\w*|smietan\w*|kefir\w*|maslank\w*|jaj\w*|feta|camembert|brie|parmezan\w*|ricotta|mascarpone|"
    # Pieczywo
    r"chleb\w*|bulk\w*|bagietk\w*|tortill\w*|pieczyw\w*|kajzerk\w*|graham\w*|tostow\w*|"
    # Warzywa
    r"pomidor\w*|ogor\w*|papryk\w*|cebul\w*|czosn\w*|ziemniak\w*|marchew\w*|pietruszk\w*|"
    r"seler\w*|kapust\w*|brokul\w*|kalafior\w*|cukini\w*|baklazan\w*|szpinak\w*|salat\w*|"
    r"rzodkiew\w*|burak\w*|por|pora|pory|pieczark\w*|grzyb\w*|dyni\w*|awokado|fasolk\w*|groszek|szparag\w*|kukurydz\w*|"
    # Owoce
    r"jablk\w*|banan\w*|cytryn\w*|pomarancz\w*|mandarynk\w*|grejpfrut\w*|borowk\w*|"
    r"malin\w*|truskawk\w*|winogron\w*|gruszk\w*|sliwk\w*|brzoskwini\w*|nektarynk\w*|"
    r"ananas\w*|mango|kiwi|arbuz\w*|melon\w*|wisni\w*|czeresni\w*|jagod\w*|porzeczk\w*|zurawin\w*|rodzynk\w*|daktyl\w*|"
    # Produkty sypkie, makarony, kasze, mąki
    r"ryz\w*|makaron\w*|spaghetti|penne|swiderk\w*|fusilli|tagliatelle|lasagne|kasz\w*|"
    r"mak[ai]|maka|platki owsiane|platki jaglane|otr[eę]b\w*|soczewic\w*|ciecierzyc\w*|groch\w*|fasol\w*|"
    # Konserwy, przetwory, tłuszcze, przyprawy, dodatki kuchenne
    r"passat\w*|przecier\w*|koncentrat\w*|oliw\w*|olej\w*|smalec|maslo orzechowe|"
    r"sos\w*|pesto|ketchup\w*|majonez\w*|musztard\w*|chrzan\w*|ocet|bulion\w*|"
    r"miod|miodu|dzem\w*|powidl\w*|konfitur\w*|przypraw\w*|sol|pieprz|cukier|drozdze|"
    # Gotowe dania obiadowe / mrożonki
    r"pierog\w*|krokiet\w*|nalesnik\w*|pyz\w*|kopytk\w*|kluski|frytk\w*|pizza|lazani\w*|hummus\w*|tofu"
    r")\b",
    re.I,
)

PORTAL_PREFIX_RE = re.compile(
    r"^(?:zobacz\s+(?:aktualn[aąe]|archiwaln[aąe]|najnowsz[aąe]|od\s+dzi[sś]|ju[zż]\s+od\s+jutr[ao]|jutro|w\s+sklepie|ofert[eę])?\s*|"
    r"ju[zż]\s+za\s+\d+\s+dni\s+|aktualn[aąe]\s+|archiwaln[aąe]\s+|od\s+dzi[sś]\s+|ju[zż]\s+w\s+sprzeda[zż]y\s+|oferta\s+)",
    re.I,
)


def strip_portal_prefixes(text: str) -> str:
    """Usuwa wielokrotnie sklejone prefiksy portali typu 'Zobacz archiwalna ', 'Zobacz od dziś '."""
    s = " ".join(str(text or "").split()).strip(" -–|:•,./")
    for _ in range(4):
        updated = PORTAL_PREFIX_RE.sub("", s).strip(" -–|:•,./")
        if updated == s:
            break
        s = updated
    return s


def normalize_ascii(text: str) -> str:
    text = str(text or "").lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("ł", "l")


def extract_weight_from_text(text: str) -> Optional[str]:
    """Wyciąga gramaturę / pojemność / liczbę sztuk z tytułu oferty (np. '500 g', '1 kg', '200 g', '10 szt.')."""
    if not text:
        return None
    cleaned = re.sub(r"\d+[.,]\d+\s*zł\s*/\s*(?:1\s*)?(?:kg|l|100\s*g)", " ", text, flags=re.I)
    cleaned = re.sub(r"\(\s*\d+[.,]\d+\s*zł\s*/\s*[^)]+\)", " ", cleaned, flags=re.I)

    m_multi = re.search(r"\b(\d+\s*[x×]\s*\d+(?:[.,]\d+)?\s*(?:kg|g|dag|ml|l))\b", cleaned, re.I)
    if m_multi:
        return re.sub(r"\s+", " ", m_multi.group(1).lower()).replace("×", "x")

    m_std = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(kg|g|dag|ml|l|szt\.?)\b", cleaned, re.I)
    if m_std:
        num = m_std.group(1).replace(".", ",")
        unit = m_std.group(2).lower().rstrip(".")
        if unit == "szt":
            unit = "szt."
        return f"{num} {unit}"

    return None


def clean_generic_offer_name(raw_title: str) -> str:
    """Czyści surową nazwę z gazetki z prefiksów portali, cen, gramatur i dopisków promocyjnych."""
    s = strip_portal_prefixes(raw_title)
    s = re.sub(r"\b\d+\s*\+\s*\d+\s*gratis\b", " ", s, flags=re.I)
    s = re.sub(r"\bdrugi\s+(?:produkt\s+)?\d+%\s*taniej\b", " ", s, flags=re.I)
    s = re.sub(r"[-–]\s*\d{1,2}\s*%", " ", s)
    s = re.sub(r"\bsuper\s*cena\b|\bhit\s*cenowy\b|\btaniej\b|\bpromocja\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d+\s*[x×]\s*\d+(?:[.,]\d+)?\s*(?:kg|g|dag|ml|l)\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:kg|g|dag|ml|l|szt\.?)\b", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -–|:•,./")
    if not s:
        return strip_portal_prefixes(raw_title)
    return s[0].upper() + s[1:]


def guess_food_category(norm_text: str) -> str:
    """Dopasowuje kategorię zgodną z frontendem aplikacji."""
    if re.search(r"(kurczak|indyk|wieprzow|wolow|schab|karkowk|lopatk|szynk|poledwic|mielon|kielbas|boczek|boczku|parowk|kabanos|kaczk|gulasz|zeberk|udk|skrzydelk|filet|piers|mieso|losos|dorsz|tunczyk|sledz|pstrag|makrel|mintaj|morszczuk|krewetk|ryb|chleb|bulk|bagietk|tortill|pieczyw)", norm_text):
        return "Mięso i świeże"
    if re.search(r"(mleko|maslo|ser|gouda|edam|ementaler|morski|mozzarell|twarog|serek|jogurt|smietan|kefir|maslank|jaj|feta|camembert|parmezan|ricotta|mascarpone)", norm_text) and "maslo orzech" not in norm_text:
        return "Lodówka i mrożonki"
    if re.search(r"(pomidor|ogor|papryk|cebul|czosn|ziemniak|marchew|pietruszk|seler|kapust|brokul|kalafior|cukini|baklazan|szpinak|salat|rzodkiew|burak|por|pieczark|dyni|awokado|jablk|banan|cytryn|pomarancz|mandarynk|grejpfrut|borowk|malin|truskawk|winogron|gruszk|sliwk|brzoskwini|ananas|mango|kiwi|arbuz)", norm_text) and not re.search(r"(passat|przecier|koncentrat|krojon|puszk)", norm_text):
        return "Warzywa i owoce"
    if re.search(r"(oliw|olej|maslo orzech|sos sojowy|bulion|ketchup|majonez|musztard|przypraw|pesto)", norm_text):
        return "Przyprawy i dodatki"
    if re.search(r"(puszk|sloik|passat|koncentrat|fasol|kukurydz|groszek konserw|ogorki kiszon|ogorki konserw)", norm_text):
        return "Konserwy i słoiki"
    return "Suche i makarony"


def is_valid_leaflet_url(url: str, store_slug: str, link_text: str = "") -> bool:
    low_url = normalize_ascii(url)
    low_txt = normalize_ascii(link_text)
    if any(bad in low_url for bad in EXCLUDED_URL_PATTERNS):
        return False
    if any(w in low_txt for w in ["blog", "artykul", "poradnik", "czytaj dalej", "przepis na", "godziny otwarcia", "archiwaln"]):
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
        return date(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def extract_validity_dates(text: str) -> tuple[Optional[str], Optional[str]]:
    if not text:
        return None, None
    # Wzorzec pełny: "19.11 - 21.11" lub "od 19.11 do 21.11"
    m_range = re.search(
        r"(?:od\s*)?(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\s*(?:-|–|—|do)\s*(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?",
        text,
        re.I,
    )
    if m_range:
        d1, m1, y1, d2, m2, y2 = m_range.groups()
        v_from = parse_polish_date(d1, m1, y1 or y2)
        v_to = parse_polish_date(d2, m2, y2 or y1)
        if v_from and v_to:
            return v_from, v_to

    # Wzorzec skrócony typu "19-21.11" lub "19–21.11.2026"
    m_short_range = re.search(
        r"\b(\d{1,2})\s*(?:-|–|—)\s*(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b",
        text,
        re.I,
    )
    if m_short_range:
        d1, d2, m2, y2 = m_short_range.groups()
        v_from = parse_polish_date(d1, m2, y2)
        v_to = parse_polish_date(d2, m2, y2)
        if v_from and v_to:
            return v_from, v_to

    # Wzorzec "do soboty 21.11", "do 21.11", "ważne do 21.11"
    m_until = re.search(
        r"(?:wazn[ae]|obowiazuje|oferta|tylko)?\s*do\s+(?:[a-ząćęłńóśźż]+\s+)?(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?",
        text,
        re.I,
    )
    if m_until:
        d2, m2, y2 = m_until.groups()
        v_to = parse_polish_date(d2, m2, y2)
        if v_to:
            return None, v_to

    # Wzorzec jednodniowy: "tylko w sobotę 21.11", "w piątek 20.11", "tylko 21.11"
    m_single_day = re.search(
        r"(?:tylko\s+)?(?:w\s+)?(?:poniedzialek|wtorek|srod[eę]|czwartek|piatek|sobot[eę]|niedziel[eę]|tylko)\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?",
        normalize_ascii(text),
        re.I,
    )
    if m_single_day:
        d1, m1, y1 = m_single_day.groups()
        v_exact = parse_polish_date(d1, m1, y1)
        if v_exact:
            return v_exact, v_exact

    m_iso = re.findall(r"\b(202\d-\d{2}-\d{2})\b", text)
    if len(m_iso) >= 2:
        return m_iso[0], m_iso[1]
    if len(m_iso) == 1:
        return None, m_iso[0]
    return None, None


def is_promotion_active(valid_to: Optional[str], valid_from: Optional[str] = None) -> bool:
    today = datetime.now().date()
    if valid_to:
        try:
            if datetime.strptime(valid_to, "%Y-%m-%d").date() < today:
                return False
        except ValueError:
            pass
    # Odrzuć gazetki z dalekiej przyszłości (np. startujące za 7-10 dni)
    if valid_from:
        try:
            days_until_start = (datetime.strptime(valid_from, "%Y-%m-%d").date() - today).days
            if days_until_start > 2:
                return False
        except ValueError:
            pass
    return True


def classify_any_food_offer(raw_title: str, price_val: float) -> Optional[tuple[str, str, str, bool]]:
    """
    Akceptuje WYŁĄCZNIE realne produkty spożywcze / składniki kulinarne:
    1) odrzuca oferty archiwalne oraz zapowiedzi 'już za X dni'
    2) odrzuca czarną listę (chemia, elektronika, książki, zabawki, słodycze, ciasta, kawa/herbata, napoje, alkohol)
    3) wymaga dopasowania do CORE_CULINARY_ITEMS lub białej listy słów spożywczych POSITIVE_FOOD_KEYWORDS
    """
    if price_val < 0.50 or price_val > 120.00:
        return None

    raw_norm = normalize_ascii(raw_title)
    if "archiwaln" in raw_norm or re.search(r"\bjuz\s+za\s+\d+\s+dni\b", raw_norm):
        return None

    clean_title = clean_generic_offer_name(raw_title)
    norm = normalize_ascii(clean_title)

    if len(norm) < 3 or len(norm) > 85 or not re.search(r"[a-z]{3,}", norm):
        return None

    if any(bad in norm for bad in NON_FOOD_AND_UI_NOISE):
        return None
    if re.search(r"\bwino\b", norm):
        return None

    # 1. Podstawowe składniki kulinarne (sprawdzamy zarówno surową nazwę przed wycięciem przymiotników, jak i oczyszczoną)
    combined_check = f"{raw_norm} {norm}"
    for canon_key, (clean_label, cat_name, must_kws, excl_kws, min_p, max_p) in CORE_CULINARY_ITEMS.items():
        if min_p <= price_val <= max_p and not any(ex in combined_check for ex in excl_kws):
            if any(kw in combined_check for kw in must_kws):
                if canon_key == "serek_wiejski" and ("lekk" in combined_check or "light" in combined_check):
                    return "serek_wiejski_lekki", "Serek wiejski lekki", cat_name, True
                return canon_key, clean_label, cat_name, True

    # 2. Pozostałe oferty przechodzą TYLKO jeśli zawierają rozpoznane słowo spożywcze
    if not POSITIVE_FOOD_KEYWORDS.search(norm):
        return None

    cat_name = guess_food_category(norm)
    slug = re.sub(r"[^a-z0-9]+", "_", norm).strip("_")[:48]
    if not slug:
        slug = hashlib.md5(norm.encode("utf-8")).hexdigest()[:12]

    return slug, clean_title, cat_name, False


def parse_offers(html: str, store_name: str, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    offers = []
    seen = set()

    page_header_text = " ".join([
        soup.title.get_text(" ", strip=True) if soup.title else "",
        " ".join(h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2"], limit=4)),
    ])
    if "archiwaln" in normalize_ascii(page_header_text):
        return []

    page_valid_from, page_valid_to = extract_validity_dates(page_header_text)

    if not is_promotion_active(page_valid_to, page_valid_from):
        return []

    def try_add(raw_prod: str, price_val: float, raw_text: str, v_from: Optional[str], v_to: Optional[str]):
        matched = classify_any_food_offer(raw_prod, price_val)
        if not matched:
            return
        offer_slug, clean_label, cat_name, is_core = matched
        weight_str = extract_weight_from_text(raw_prod) or extract_weight_from_text(raw_text)
        clean_raw_display = strip_portal_prefixes(raw_text)
        sig = f"{offer_slug}_{price_val}_{weight_str or ''}"
        if sig not in seen:
            seen.add(sig)
            offers.append({
                "store": store_name,
                "canon_key": offer_slug,
                "category": cat_name,
                "raw_name": strip_portal_prefixes(raw_prod),
                "generic_name": clean_label,
                "weight": weight_str,
                "price": round(price_val, 2),
                "is_core": is_core,
                "valid_from": v_from,
                "valid_to": v_to,
                "raw_text": clean_raw_display,
                "source_url": source_url,
            })

    # 1. Dane osadzone w JSON / skryptach na stronie (sprawdzamy też daty ważności samej oferty w oknie JSON!)
    for script in soup.find_all("script"):
        s_text = script.string or ""
        if not s_text:
            continue
        for m in re.finditer(
            r'"(?:name|title|productName)"\s*:\s*"([^"]{3,110})".{0,550}?"(?:price|lowPrice|promoPrice|value)"\s*:\s*"?(\d{1,3}[.,]\d{2})"?',
            s_text,
            re.S,
        ):
            raw_prod = m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore").strip()
            price_val = float(m.group(2).replace(",", "."))
            snippet = s_text[max(0, m.start() - 120):min(len(s_text), m.end() + 260)]
            j_from, j_to = extract_validity_dates(snippet)
            v_from = j_from or page_valid_from
            v_to = j_to or page_valid_to
            if not is_promotion_active(v_to, v_from):
                continue
            clean_p = strip_portal_prefixes(raw_prod)
            try_add(raw_prod, price_val, f"{clean_p} — {price_val:.2f} zł", v_from, v_to)

    # 2. Atrybuty alt obrazków gazetek + tekst rodzica karty (gdzie często jest podana data końca sub-promocji np. "do soboty 21.11")
    for img in soup.find_all("img", alt=True):
        alt_txt = " ".join((img.get("alt") or "").split())
        if len(alt_txt) < 8 or len(alt_txt) > 220:
            continue
        price_matches = list(re.finditer(r"(\d{1,3}[.,]\d{2})\s*zł", alt_txt, re.I))
        if 1 <= len(price_matches) <= 2:
            first_m = price_matches[0]
            price_val = float(first_m.group(1).replace(",", "."))
            raw_prod = alt_txt[:first_m.start()].strip(" -–|:•,")
            parent_txt = " ".join(img.parent.get_text(" ", strip=True).split()) if img.parent else ""
            c_from, c_to = extract_validity_dates(f"{alt_txt} {parent_txt[:220]}")
            v_from = c_from or page_valid_from
            v_to = c_to or page_valid_to
            if not is_promotion_active(v_to, v_from):
                continue
            try_add(raw_prod, price_val, alt_txt, v_from, v_to)

    # 3. Kafelki ofert HTML
    for el in soup.find_all(["article", "div", "li", "a", "tr", "section"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if len(text) < 8 or len(text) > 260:
            continue
        price_matches = list(re.finditer(r"(\d{1,3}[.,]\d{2})\s*zł", text, re.I))
        if not (1 <= len(price_matches) <= 2):
            continue
        first_m = price_matches[0]
        price_val = float(first_m.group(1).replace(",", "."))
        raw_prod = text[:first_m.start()].strip(" -–|:•,")
        card_from, card_to = extract_validity_dates(text)
        v_from = card_from or page_valid_from
        v_to = card_to or page_valid_to
        if not is_promotion_active(v_to, v_from):
            continue
        clean_p = strip_portal_prefixes(raw_prod)
        try_add(raw_prod, price_val, f"{clean_p} — {price_val:.2f} zł", v_from, v_to)

    return offers


def find_leaflet_links_from_home(session: requests.Session) -> dict[str, list[str]]:
    store_links = {s: list(DIRECT_STORE_SEEDS.get(s, [])) for s in STORES}
    for home in PORTAL_HOMES:
        try:
            resp = session.get(home, timeout=15)
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
                    if is_valid_leaflet_url(full, store.lower(), link_txt) and full not in store_links[store]:
                        store_links[store].append(full)
        except Exception:
            pass
        time.sleep(0.35)
    return store_links


def fetch_all_store_offers() -> list[dict]:
    session = requests.Session()
    session.headers.update(HEADERS)
    discovered = find_leaflet_links_from_home(session)
    all_offers = []

    for store in STORES:
        slug = store.lower()
        links = discovered.get(store, [])
        store_offers = []
        visited = set()
        queue = list(links[:20])
        expanded_leaflet_ids = set()

        while queue and len(visited) < 45:
            url = queue.pop(0)
            if url in visited or not is_valid_leaflet_url(url, slug):
                continue
            visited.add(url)

            m_blix_gaz = re.match(r"^(https?://blix\.pl/sklep/[^/]+/gazetka/\d+/?)$", url)
            if m_blix_gaz and url not in expanded_leaflet_ids:
                expanded_leaflet_ids.add(url)
                base_gaz = m_blix_gaz.group(1).rstrip("/") + "/"
                for page_num in range(2, 16):
                    paged_url = f"{base_gaz}?pageNumber={page_num}"
                    if paged_url not in visited and paged_url not in queue:
                        queue.insert(0, paged_url)

            try:
                time.sleep(0.25)
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    continue
                store_offers.extend(parse_offers(resp.text, store, url))

                soup = BeautifulSoup(resp.text, "html.parser")
                base_domain = urlparse(url).netloc
                for a in soup.find_all("a", href=True):
                    sub = urljoin(url, a["href"]).split("#")[0]
                    sub_txt = a.get_text(" ", strip=True)
                    if urlparse(sub).netloc == base_domain and sub not in visited and sub not in queue:
                        if is_valid_leaflet_url(sub, slug, sub_txt):
                            queue.append(sub)
            except Exception:
                pass

        dedup = {}
        for o in store_offers:
            k = f"{o['canon_key']}_{o['price']}_{o.get('weight') or ''}"
            if k not in dedup:
                dedup[k] = o

        final_list = list(dedup.values())
        print(f"==> {store}: zebrano {len(final_list)} promocji spożywczych.", flush=True)
        all_offers.extend(final_list)

    return all_offers


def build_all_food_pending(offers: list[dict], max_items: int = 350) -> dict:
    """
    Zwraca wszystkie unikalne promocje spożywcze (z pominięciem słodyczy, alkoholu i archiwalnych),
    zachowując najniższą cenę dla identycznego (sklep + produkt + gramatura).
    """
    best_offers = {}
    for off in offers:
        weight_part = normalize_ascii(off.get("weight") or "").replace(" ", "")
        key = f"{normalize_ascii(off['store'])}_{off['canon_key']}_{weight_part}".rstrip("_")

        if key not in best_offers or off["price"] < best_offers[key]["detectedPrice"]:
            best_offers[key] = {
                "name": off["generic_name"],
                "weight": off.get("weight"),
                "category": off.get("category") or "Inne",
                "detectedPrice": off["price"],
                "isCore": bool(off.get("is_core")),
                "store": off["store"],
                "validFrom": off.get("valid_from"),
                "validTo": off.get("valid_to"),
                "source": off["store"],
                "rawText": off["raw_text"],
                "sourceUrl": off["source_url"],
            }

    sorted_items = sorted(
        best_offers.items(),
        key=lambda x: (not x[1]["isCore"], x[1]["name"], x[1]["detectedPrice"])
    )[:max_items]
    return dict(sorted_items)


def purge_expired_pending(existing_pending: dict) -> dict:
    cleaned = {}
    for k, v in (existing_pending or {}).items():
        if not isinstance(v, dict):
            continue
        if "archiwaln" in normalize_ascii(f"{v.get('name', '')} {v.get('rawText', '')}"):
            continue
        if is_promotion_active(v.get("validTo")):
            cleaned[k] = v
    return cleaned


def export_csv(offers: list[dict], filename="promocje_spozywcze.csv"):
    with open(filename, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["store", "category", "generic_name", "weight", "raw_name", "price", "valid_from", "valid_to", "source_url", "collection_date"])
        today = datetime.now().strftime("%Y-%m-%d")
        for o in offers:
            writer.writerow([
                o["store"],
                o.get("category") or "Inne",
                o["generic_name"],
                o.get("weight") or "NULL",
                o["raw_name"],
                f"{o['price']:.2f}",
                o.get("valid_from") or "NULL",
                o.get("valid_to") or "NULL",
                o["source_url"],
                today,
            ])
    print(f"Zapisano CSV: {filename} ({len(offers)} wierszy)", flush=True)



def filter_pending_with_gemini(pending_dict: dict, api_key: str) -> dict:
    """Opcjonalny filtr AI (Gemini Flash) po stronie Pythona — odrzuca wszystko, co nie jest realnym jedzeniem/składnikiem kuchennym."""
    if not api_key or not pending_dict:
        return pending_dict

    items_payload = [
        {"key": k, "name": v.get("name"), "raw": v.get("rawText")}
        for k, v in pending_dict.items()
    ]
    kept_keys = set()
    cleaned_names = {}
    cleaned_cats = {}

    chunk_size = 90
    for i in range(0, len(items_payload), chunk_size):
        chunk = items_payload[i:i + chunk_size]
        prompt = (
            "Jesteś filtrem bazy produktów spożywczych do gotowania w domu. "
            "Z poniższej listy wybierz WYŁĄCZNIE prawdziwe produkty spożywcze / składniki kulinarne "
            "(mięso, wędliny, ryby, nabiał, jaja, warzywa, owoce, pieczywo, makarony, ryż, kasze, mąka, konserwy, przyprawy, oleje, masło, bakalie, miód, dżem). "
            "BEZWZGLĘDNIE ODRZUĆ: artykuły niespożywcze (dyfuzory zapachowe, świeczki, chemię, kosmetyki, zestawy prezentowe, odzież, zabawki), "
            "słodycze (ciastka, praliny, czekolady, batony, wafelki, lody, żelki), "
            "chipsy, chrupki, herbaty, kawy, napoje gazowane, soki, energetyki oraz alkohol. "
            "Zwróć JSON jako listę obiektów dla ZAAKCEPTOWANYCH pozycji: "
            '[{"key": "...", "cleanName": "Krótka czysta nazwa po polsku", "category": "Mięso i świeże|Lodówka i mrożonki|Warzywa i owoce|Konserwy i słoiki|Suche i makarony|Przyprawy i dodatki"}]\n\n'
            f"Lista: {json.dumps(chunk, ensure_ascii=False)}"
        )
        chunk_ok = False
        for model_name in ["gemini-3.8-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]:
            try:
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}",
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"responseMimeType": "application/json"},
                    },
                    timeout=35,
                )
                if resp.status_code == 200:
                    raw_txt = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "[]")
                    raw_txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_txt.strip())
                    parsed = json.loads(raw_txt)
                    if isinstance(parsed, list):
                        for row in parsed:
                            k = row.get("key")
                            if k in pending_dict:
                                kept_keys.add(k)
                                if row.get("cleanName"):
                                    cleaned_names[k] = row["cleanName"]
                                if row.get("category"):
                                    cleaned_cats[k] = row["category"]
                    chunk_ok = True
                    break
                elif resp.status_code in (429, 503):
                    time.sleep(0.8)
                    continue
                else:
                    continue
            except Exception:
                continue
        if not chunk_ok:
            print("[AI Filter] Wszystkie modele AI przeciążone, używam filtra regułowego.", flush=True)
            return pending_dict

    if not kept_keys:
        return pending_dict

    filtered = {}
    for k in kept_keys:
        entry = dict(pending_dict[k])
        if k in cleaned_names:
            entry["name"] = cleaned_names[k]
        if k in cleaned_cats:
            entry["category"] = cleaned_cats[k]
        filtered[k] = entry

    print(f"[AI Filter] Gemini zaakceptowało {len(filtered)}/{len(pending_dict)} pozycji spożywczych.", flush=True)
    return filtered

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
    print(f"=== START SCRAPERA — CZYSTE PROMOCJE ({'TRYB LOKALNY --dry-run' if dry_run else 'TRYB FIREBASE'}) ===", flush=True)

    offers = fetch_all_store_offers()
    export_csv(offers)

    all_promos = build_all_food_pending(offers)
    print(f"Przygotowano {len(all_promos)} promocji spożywczych po filtrze regułowym.", flush=True)

    if dry_run:
        with open("wynik_testu.json", "w", encoding="utf-8") as f:
            json.dump({"total_offers": len(offers), "pending_count": len(all_promos), "items": all_promos}, f, ensure_ascii=False, indent=2)
        for v in list(all_promos.values())[:40]:
            w_badge = f" [{v['weight']}]" if v.get("weight") else ""
            print(f"  ✓ [{v['store']}] ({v['category']}) {v['name']}{w_badge} -> {v['detectedPrice']:.2f} zł ({v['validFrom']} - {v['validTo']})", flush=True)
        return

    if not all_promos:
        print("Brak pobranych ofert — przerywam zapis do Firebase.", flush=True)
        return

    db = init_firestore()
    updated = 0
    for doc_snap in db.collection("kuchnie").stream():
        data = doc_snap.to_dict() or {}
        if data.get("active") is False:
            continue

        # Użyj klucza Gemini z env lub z ustawień danej kuchni, aby AI odsiało wszelkie śmieci
        gemini_key = os.environ.get("GEMINI_API_KEY") or data.get("geminiApiKey") or ""
        active_existing = filter_pending_with_gemini(dict(all_promos), gemini_key) if gemini_key else dict(all_promos)

        db.collection("kuchnie").document(doc_snap.id).update({
            "pendingScraper": active_existing,
            "lastScraped": datetime.now().isoformat(),
        })
        updated += 1
        print(f"[Kuchnia {doc_snap.id}] Aktywnych pozycji w zakładce Promocje: {len(active_existing)}.", flush=True)

    print(f"=== ZAKOŃCZONO. Zaktualizowano {updated} kuchni w Firebase. ===", flush=True)


if __name__ == "__main__":
    main()
