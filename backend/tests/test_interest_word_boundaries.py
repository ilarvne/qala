from backend.retrieval import infer_interests, interest_mentions


def test_night_transport_does_not_add_a_sports_venue_constraint():
    interests = infer_interests("Поздно ночью хочу погулять и найти транспорт домой.")
    assert "night" in interests
    assert "sport" not in interests


def test_word_start_keeps_explicit_sport_inflections_and_negation():
    assert "sport" in infer_interests("Хочу спортивную площадку поблизости")
    positive, negative = interest_mentions("Ночная прогулка без спортивных площадок")
    assert "sport" not in positive
    assert "sport" in negative


def test_russian_and_kazakh_stems_still_accept_inflected_venue_words():
    assert "culture" in infer_interests("Интересуюсь архитектурой")
    assert "nature" in infer_interests("Саябаққа барғым келеді")
