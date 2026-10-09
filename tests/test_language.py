from jobhelper import language


def test_english_text_is_english():
    assert language.is_english(
        "We are looking for a Python developer to join our team. "
        "You will work with our data platform and REST APIs."
    )


def test_czech_text_is_not_english():
    assert not language.is_english(
        "Hledáme vývojáře v jazyce Python. Nabízíme zajímavou práci a "
        "možnost odborného růstu. Požadujeme znalost a zkušenosti."
    )


def test_czech_diacritics_detected():
    assert not language.is_english("Softwarový vývojář pro naši společnost")


def test_short_or_empty_defaults_english():
    assert language.is_english("")
    assert language.is_english("DevOps")


def test_english_title_only():
    assert language.is_english("Senior Backend Engineer (Python)")


# ── long English ads with a few Czech letters (found by the filtered-out list) ──
ENGLISH_AD = ("About us ČSOB is part of KBC Group which is an integrated bank-insurance group. We are looking for a "
              "colleague to join our team in Prague or Plzeň. You will build and validate risk models, work with the "
              "data and present the results. We offer flexible working hours and a friendly team. ") * 6


def test_a_long_english_ad_with_a_few_czech_letters_is_english():
    from jobhelper import language
    assert sum(ch in "čšžňřěýáíéůú" for ch in ENGLISH_AD.lower()) >= 3
    assert language.is_english(ENGLISH_AD) is True


def test_czech_text_is_still_czech_whatever_its_length():
    from jobhelper import language
    czech = "Hledáme vývojáře do našeho týmu. Nabízíme zajímavou práci, přátelský kolektiv a možnost růstu. " * 20
    assert language.is_english(czech) is False
    assert language.is_english("Softwarový vývojář") is False
    assert language.is_english("Vývojář") is True                     # too short to judge: kept, as before


def test_an_english_ad_inside_a_czech_page_frame_is_english():
    from jobhelper import language
    page = ("Nabídky práce Detail nabídky Aktualizováno včera UX Designer Plat neuveden. "
            + "We are looking for a designer who will work with our product team and the developers. "
              "You have experience with user research and you are able to present your work in English. " * 12)
    assert language.is_english(page) is True


# ── which language, when it is not English ──────────────────────────────────
ADS = {
    "German": "Wir suchen einen Softwareentwickler für unser Team in Wien. Ihre Aufgaben sind die Entwicklung und der Betrieb "
              "unserer Dienste. Sie bringen Erfahrung mit Python und gute Kenntnisse in SQL mit. Wir bieten flexible Arbeitszeiten.",
    "French": "Nous recherchons une infirmière pour notre équipe. Vous avez une première expérience dans un poste similaire et "
              "vous aimez le travail avec les patients. Le poste est à pourvoir dans notre clinique pour une durée indéterminée.",
    "Spanish": "Buscamos una persona para nuestro equipo de ventas. Ofrecemos un buen ambiente de trabajo y formación. "
               "Se requiere experiencia con clientes y ganas de aprender, para crecer con los proyectos del equipo.",
    "Italian": "Cerchiamo una persona per il nostro ufficio di Milano. Siamo una società che lavora nel settore della logistica "
               "e offriamo un contratto con formazione. Sono richieste esperienza e conoscenza delle procedure di magazzino.",
    "Polish": "Szukamy programisty do naszego zespołu w Warszawie. Oferujemy umowę o pracę oraz szkolenia. Wymagania: "
              "doświadczenie w Javie, znajomość SQL oraz chęć do nauki. Praca jest dla osób, które lubią pracę w zespole.",
    "Dutch": "Wij zoeken een collega voor ons team in Utrecht. Je hebt ervaring met klanten en je vindt het leuk om met "
             "mensen te werken. Wij bieden een goed salaris en ruimte voor ontwikkeling. De functie is voor 40 uur.",
    "Portuguese": "Procuramos uma pessoa para a nossa equipa em Lisboa. Oferecemos formação e um bom ambiente de trabalho. "
                  "É necessária experiência com clientes e vontade de aprender com os colegas da equipa.",
    "Czech": "Hledáme vývojáře do našeho týmu v Brně. Nabízíme zajímavou práci a příjemný kolektiv. Požadujeme znalost "
             "Pythonu a zkušenosti s databázemi. Místo výkonu práce je Brno, plný úvazek.",
    "Slovak": "Hľadáme vývojára do nášho tímu v Bratislave. Ponúkame zaujímavú prácu a príjemný kolektív. Požadujeme "
              "skúsenosti s Pythonom alebo Javou a znalosť databáz. Pracovné miesto je v Bratislave.",
    "Russian": "Мы ищем разработчика в нашу команду. Требуется опыт работы с Python и базами данных. Мы предлагаем гибкий график.",
    "Ukrainian": "Ми шукаємо розробника до нашої команди. Потрібен досвід роботи з Python і базами даних. Її чекає гнучкий графік.",
    "Japanese": "私たちはソフトウェアエンジニアを募集しています。Pythonの経験が必要です。",
    "Greek": "Ζητάμε προγραμματιστή για την ομάδα μας. Απαιτείται εμπειρία σε Python και βάσεις δεδομένων.",
}


def test_the_language_of_an_ad_is_named():
    for name, text in ADS.items():
        assert language.detect(text) == name, name
        assert language.is_english(text) is False, name


def test_english_ads_are_not_taken_for_another_language():
    ads = ["We are looking for a nurse to join our team in Vienna. You will work with patients and colleagues, and we offer "
           "training and flexible hours. Experience in a similar role is an advantage, and you will report to the ward manager.",
           # English with foreign names, a German company form and a few borrowed words
           "Müller & Söhne GmbH is hiring an accountant in Zürich. You will prepare the monthly reports for our offices in "
           "München and Wien, work with the finance team and help with the year-end closing. Good English is required.",
           "Junior Developer at Škoda Auto in Kolín. You will work on our internal tools with Python and SQL, "
           "in a team of five. We offer mentoring, a learning budget and the possibility to work from home two days a week.",
           "Data Analyst (m/w/d)", "Software Engineer", "", "QA"]
    for text in ads:
        assert language.detect(text) == "" and language.is_english(text) is True, text[:40]


def test_a_script_that_cannot_be_named_is_still_not_english():
    assert language.detect("ქართული ენა არის ქართველთა ენა და საქართველოს სახელმწიფო ენა") in ("", "another language")
    assert language.detect("สวัสดีครับ เรากำลังมองหานักพัฒนาซอฟต์แวร์ที่มีประสบการณ์") == "Thai"
