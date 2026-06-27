from clipper.analyze import _clean_hashtags


def test_clean_hashtags_basic_prefix_and_count():
    raw = ["pourtoi", "#film", "cinema", "drame", "michael", "extra"]
    out = _clean_hashtags(raw, count=5)
    assert out == ["#pourtoi", "#film", "#cinema", "#drame", "#michael"]
    assert len(out) == 5


def test_clean_hashtags_strips_punctuation_and_spaces():
    raw = ["#pourtoi !", "film-culte", "  viral.  "]
    out = _clean_hashtags(raw, count=10)
    # la ponctuation et les espaces sont retirés ; "!" seul disparaît
    assert out == ["#pourtoi", "#filmculte", "#viral"]


def test_clean_hashtags_dedupes_case_insensitive():
    raw = ["#FYP", "fyp", "Fyp", "viral"]
    out = _clean_hashtags(raw, count=10)
    assert out == ["#FYP", "#viral"]


def test_clean_hashtags_splits_multiple_in_one_string():
    raw = ["#pourtoi #fyp #film"]
    out = _clean_hashtags(raw, count=10)
    assert out == ["#pourtoi", "#fyp", "#film"]


def test_clean_hashtags_keeps_accents_and_digits():
    raw = ["émotion", "top10", "année2026"]
    out = _clean_hashtags(raw, count=10)
    assert out == ["#émotion", "#top10", "#année2026"]


def test_clean_hashtags_handles_empty_and_garbage():
    raw = ["", None, "#", "!!!", "   ", "ok"]
    out = _clean_hashtags(raw, count=10)
    assert out == ["#ok"]
