import pytest

from clipper.config import Config
from clipper.models import Moment
from clipper.montage import _wrap_lines, select_scenes
from tests.helpers import make_transcript


def test_select_scenes_count_and_order():
    cfg = Config(mode="montage", scene_duration=30, montage_duration=150,
                 transition_duration=0.7)
    t = make_transcript(duration=900, seg_len=10)
    moments = [Moment(start=s, end=s + 30, hook=f"S{i}", score=90 - i, emotion="tendu")
               for i, s in enumerate([50, 200, 350, 500, 650, 800])]
    scenes = select_scenes(moments, t, cfg, audio=None, video_duration=900)

    # ~5 scènes pour 150s / 30s
    assert 3 <= len(scenes) <= 6
    # ordre chronologique
    starts = [s for s, _, _ in scenes]
    assert starts == sorted(starts)
    # pas de chevauchement
    for i in range(len(scenes) - 1):
        assert scenes[i][1] <= scenes[i + 1][0] + 1e-6
    # durée de scène respectée
    for s, e, _ in scenes:
        assert abs((e - s) - cfg.scene_duration) < 1e-6


def test_select_scenes_prefers_high_scores():
    cfg = Config(mode="montage", scene_duration=20, montage_duration=40,
                 transition_duration=0.5)
    t = make_transcript(duration=600, seg_len=10)
    moments = [
        Moment(start=100, end=120, hook="faible", score=30, emotion="plat"),
        Moment(start=300, end=320, hook="fort", score=99, emotion="choquant"),
    ]
    scenes = select_scenes(moments, t, cfg, audio=None, video_duration=600)
    hooks = [m.hook for _, _, m in scenes]
    assert "fort" in hooks


def test_wrap_lines_respects_width():
    PIL = pytest.importorskip("PIL")
    from PIL import Image, ImageDraw, ImageFont

    draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    font = ImageFont.load_default()
    text = "Abonne-toi sur Film HD sur Telegram pour regarder le film complet"
    lines = _wrap_lines(draw, text, font, max_width=200)
    assert len(lines) >= 2
    # tous les mots sont conservés
    assert " ".join(lines).split() == text.split()


def test_make_cta_image_creates_png(tmp_path):
    pytest.importorskip("PIL")
    from clipper.montage import make_cta_image

    cfg = Config(width=1080, height=1920)
    out = tmp_path / "cta.png"
    make_cta_image("Lien dans ma Bio sur Telegram", cfg, str(out))
    assert out.is_file()

    from PIL import Image
    im = Image.open(out).convert("RGBA")
    assert im.size == (1080, 1920)
    # le bandeau central doit être opaque
    assert im.getpixel((540, 960))[3] > 0
