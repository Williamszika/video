from clipper.models import Moment, Transcript
from tests.helpers import make_transcript


def test_words_between():
    t = make_transcript(duration=100, seg_len=10, words_per_seg=5)
    words = t.words_between(20, 40)
    assert words, "doit contenir des mots"
    for w in words:
        mid = (w.start + w.end) / 2
        assert 20 <= mid < 40


def test_transcript_roundtrip():
    t = make_transcript(duration=60)
    t2 = Transcript.from_dict(t.to_dict())
    assert t2.language == t.language
    assert len(t2.segments) == len(t.segments)
    assert t2.words[0].text == t.words[0].text


def test_transcript_text():
    t = make_transcript(duration=30, seg_len=10)
    assert "mot0" in t.text


def test_moment_roundtrip():
    m = Moment(start=10, end=130, hook="Choc total", score=88, emotion="choquant",
               quote="phrase", reason="punchline")
    m2 = Moment.from_dict(m.to_dict())
    assert m2.hook == "Choc total"
    assert m2.duration == 120
    assert m2.score == 88
