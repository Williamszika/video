from clipper.config import Config
from clipper.models import Word
from clipper.subtitles import build_ass, hex_to_ass


def _words(n=8, start=0.0, step=0.5):
    return [Word(start=start + i * step, end=start + i * step + step * 0.9, text=f"mot{i}")
            for i in range(n)]


def test_hex_to_ass():
    assert hex_to_ass("FFE000") == "&H0000E0FF"   # RGB -> BBGGRR
    assert hex_to_ass("#FFFFFF") == "&H00FFFFFF"
    assert hex_to_ass("bad") == "&H00FFFFFF"       # repli


def test_build_ass_has_header_and_styles():
    cfg = Config()
    ass = build_ass(_words(), cfg)
    assert "[Script Info]" in ass
    assert f"PlayResX: {cfg.width}" in ass
    assert "Style: Default" in ass
    assert "[Events]" in ass


def test_animated_highlights_active_word():
    cfg = Config(subtitle_style="animated", words_per_caption=4,
                 highlight_color="FFE000")
    ass = build_ass(_words(4), cfg)
    # La couleur de surlignage doit apparaître dans une réplique animée.
    assert hex_to_ass("FFE000") in ass
    assert "\\fscx118" in ass  # agrandissement du mot actif
    assert ass.count("Dialogue:") >= 4  # une réplique par mot actif


def test_simple_style_one_line_per_chunk():
    cfg = Config(subtitle_style="simple", words_per_caption=4, show_hook=False)
    ass = build_ass(_words(8), cfg)
    dialogues = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogues) == 2  # 8 mots / 4 = 2 cartes


def test_hook_rendered_on_top():
    cfg = Config(show_hook=True, hook_duration=3.0)
    ass = build_ass(_words(4), cfg, hook="Tu vas halluciner", clip_duration=120)
    assert "Hook" in ass
    assert "TU VAS HALLUCINER" in ass  # mis en majuscules


def test_times_relative_to_clip_start():
    cfg = Config(subtitle_style="simple", show_hook=False, words_per_caption=4)
    words = _words(4, start=300.0, step=0.5)  # mots situés à 5 min dans la vidéo
    ass = build_ass(words, cfg, clip_start=300.0)
    # Les temps doivent repartir de ~0, pas de 5 minutes.
    assert "0:05:00" not in ass
    assert "Dialogue: 0,0:00:00" in ass


def test_ass_escapes_braces():
    cfg = Config(subtitle_style="simple", show_hook=False)
    words = [Word(start=0, end=1, text="a{b}c")]
    ass = build_ass(words, cfg)
    assert "a(b)c" in ass  # accolades neutralisées
