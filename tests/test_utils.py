from clipper.utils import (format_ass_time, format_timestamp, human_duration,
                           slugify)


def test_format_timestamp():
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(3661) == "01:01:01"
    assert format_timestamp(75.25, millis=True) == "00:01:15.250"
    assert format_timestamp(-5) == "00:00:00"


def test_format_ass_time():
    assert format_ass_time(0) == "0:00:00.00"
    assert format_ass_time(3661.5) == "1:01:01.50"
    assert format_ass_time(1.234) == "0:00:01.23"


def test_slugify():
    assert slugify("Il a dit QUOI ?!") == "il-a-dit-quoi"
    assert slugify("Émotion forte à 100%") == "emotion-forte-a-100"
    assert slugify("") == "clip"
    assert len(slugify("x" * 100, max_len=20)) <= 20


def test_human_duration():
    assert human_duration(75) == "01m 15s"
    assert human_duration(3661) == "1h 01m 01s"
    assert human_duration(5) == "05s"
