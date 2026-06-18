from clipper.config import Config
from clipper.models import Moment
from clipper.select import (adjust_window, compute_scores, select_clips,
                            snap_to_sentences)
from tests.helpers import make_transcript


def test_adjust_window_extends_short_moment():
    cfg = Config(target_duration=120, min_duration=45, max_duration=140)
    start, end = adjust_window(100, 130, cfg, video_duration=600)
    assert abs((end - start) - 120) < 1e-6  # étiré vers la cible


def test_adjust_window_caps_long_moment():
    cfg = Config(target_duration=120, min_duration=45, max_duration=140)
    start, end = adjust_window(100, 400, cfg, video_duration=600)
    assert end - start <= 140


def test_adjust_window_respects_video_end():
    cfg = Config(target_duration=120, min_duration=45, max_duration=140)
    start, end = adjust_window(560, 580, cfg, video_duration=600)
    assert end <= 600


def test_snap_to_sentences_aligns_on_boundaries():
    cfg = Config()
    t = make_transcript(duration=600, seg_len=10)
    start, end = snap_to_sentences(103, 224, t, cfg, 600)
    # Les segments commencent/terminent sur des multiples de 10.
    assert start % 10 == 0
    assert end % 10 == 0


def test_compute_scores_without_audio():
    cfg = Config()
    moments = [Moment(start=0, end=120, hook="a", score=80, emotion="drôle")]
    compute_scores(moments, cfg, audio=None)
    assert moments[0].final_score == 80


def test_select_clips_no_overlap_and_count():
    cfg = Config(num_clips=3, target_duration=120, min_duration=45,
                 max_duration=140, min_gap=20)
    t = make_transcript(duration=900, seg_len=10)
    moments = [
        Moment(start=50, end=120, hook="A", score=95, emotion="choquant"),
        Moment(start=130, end=200, hook="B", score=92, emotion="drôle"),   # proche de A -> doit être écarté
        Moment(start=400, end=470, hook="C", score=90, emotion="émouvant"),
        Moment(start=700, end=780, hook="D", score=85, emotion="inspirant"),
    ]
    clips = select_clips(moments, t, cfg, audio=None, video_duration=900)

    assert 1 <= len(clips) <= 3
    # Pas de chevauchement et écart respecté.
    for i in range(len(clips) - 1):
        assert clips[i + 1].start >= clips[i].end + cfg.min_gap
    # Ordre chronologique et indices renumérotés.
    assert [c.index for c in clips] == list(range(1, len(clips) + 1))
    # Durées dans les bornes.
    for c in clips:
        assert cfg.min_duration * 0.6 <= c.duration <= cfg.max_duration + 1


def test_select_clips_prefers_higher_score():
    cfg = Config(num_clips=1, min_gap=20)
    t = make_transcript(duration=900, seg_len=10)
    moments = [
        Moment(start=100, end=220, hook="faible", score=40, emotion="plat"),
        Moment(start=500, end=620, hook="fort", score=98, emotion="choquant"),
    ]
    clips = select_clips(moments, t, cfg, audio=None, video_duration=900)
    assert len(clips) == 1
    assert clips[0].hook == "fort"
