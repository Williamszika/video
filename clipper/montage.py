"""Mode montage : une seule vidéo « bande-annonce » de ~5 min.

On réutilise l'analyse des moments forts (déjà en cache), on en extrait de
courts extraits des scènes les plus attirantes, on les assemble dans l'ordre
chronologique avec des transitions, et on incruste un carton d'appel à l'action
(CTA) sur la dernière scène pour renvoyer vers Telegram.

Le carton est rendu en image (Pillow) puis superposé par ffmpeg : aucune
dépendance à libass, donc ça fonctionne même avec un ffmpeg minimal.
"""

from __future__ import annotations

import os
from typing import List, Tuple

from . import media, select
from .config import Config
from .models import Moment, Transcript
from .utils import get_logger

log = get_logger()

Scene = Tuple[float, float, Moment]  # (start, end, moment)


# --------------------------------------------------------------------------- #
# Sélection des scènes
# --------------------------------------------------------------------------- #

def select_scenes(moments: List[Moment], transcript: Transcript, cfg: Config,
                  audio=None, video_duration: float = None,
                  window: Tuple[float, float] = None) -> List[Scene]:
    """Choisit les meilleurs extraits courts pour remplir la durée du montage.

    `window` limite la sélection à une portion chronologique du film (utile pour
    découper en plusieurs parties). Si les moments forts ne suffisent pas à
    remplir la durée visée, on complète avec des extraits régulièrement espacés
    sur la fenêtre (pour couvrir toute la portion).
    """
    if video_duration is None:
        video_duration = transcript.duration
    w0, w1 = window if window else (0.0, video_duration)
    w1 = min(w1, video_duration)

    select.compute_scores(moments, cfg, audio)
    D = cfg.scene_duration
    T = cfg.transition_duration
    n_target = max(2, round((cfg.montage_duration - T) / max(1e-6, D - T)))

    seg_starts = [s.start for s in transcript.segments]
    usable_end = max(w0, w1 - D)
    chosen: List[Scene] = []

    def _place(raw_start: float) -> Tuple[float, float]:
        start = select._nearest(raw_start, seg_starts, tolerance=5.0)
        start = max(w0, min(start, usable_end))
        return start, start + D

    def _fits(start: float, end: float) -> bool:
        if start < w0 - 1e-6 or end > w1 + 1e-6:
            return False
        return not any(not (end <= c[0] or start >= c[1]) for c in chosen)

    # 1) Les moments forts repérés par l'IA, dans la fenêtre, du meilleur au moins bon.
    in_window = [m for m in moments if w0 <= m.start < w1]
    for m in sorted(in_window, key=lambda m: m.final_score, reverse=True):
        if len(chosen) >= n_target:
            break
        start, end = _place(m.start)
        if _fits(start, end):
            chosen.append((start, end, m))

    # 2) Complément régulièrement espacé si la fenêtre n'est pas assez remplie.
    if len(chosen) < n_target and usable_end > w0:
        grid = n_target * 3
        for k in range(grid + 1):
            if len(chosen) >= n_target:
                break
            start, end = _place(w0 + (usable_end - w0) * k / grid)
            if _fits(start, end):
                chosen.append((start, end, Moment(start=start, end=end, hook="", score=0.0)))

    chosen.sort(key=lambda c: c[0])
    log.info("Montage : %d scène(s) sélectionnée(s)%s.", len(chosen),
             f" (fenêtre {w0:.0f}-{w1:.0f}s)" if window else "")
    return chosen


# --------------------------------------------------------------------------- #
# Carton d'appel à l'action (rendu en image via Pillow)
# --------------------------------------------------------------------------- #

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",     # macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int):
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:  # pragma: no cover
                continue
    return ImageFont.load_default()


def _wrap_lines(draw, text: str, font, max_width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def make_cta_image(text: str, cfg: Config, out_png: str) -> str:
    """Génère un PNG transparent 9:16 avec le texte CTA centré dans un bandeau."""
    from PIL import Image, ImageDraw

    W, H = cfg.width, cfg.height
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = _load_font(int(W * 0.072))
    max_text_w = int(W * 0.80)
    lines = _wrap_lines(draw, text, font, max_text_w)

    ascent = font.getbbox("Ag")
    line_h = (ascent[3] - ascent[1]) + int(W * 0.025)
    pad = int(W * 0.06)
    text_w = max((draw.textlength(l, font=font) for l in lines), default=0)
    box_w = min(W - pad, int(text_w) + pad * 2)
    box_h = line_h * len(lines) + pad * 2
    bx0 = (W - box_w) // 2
    by0 = (H - box_h) // 2

    draw.rounded_rectangle([bx0, by0, bx0 + box_w, by0 + box_h],
                           radius=int(W * 0.03), fill=(0, 0, 0, 180))

    y = by0 + pad
    highlight = _hex_rgb(cfg.highlight_color)
    for line in lines:
        lw = draw.textlength(line, font=font)
        # On surligne la ligne contenant l'appel "Telegram" / "Bio".
        color = (highlight + (255,)) if any(k in line.lower() for k in ("telegram", "bio")) \
            else (255, 255, 255, 255)
        draw.text(((W - lw) / 2, y), line, font=font, fill=color,
                  stroke_width=3, stroke_fill=(0, 0, 0, 255))
        y += line_h

    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    img.save(out_png)
    return out_png


def make_title_image(title: str, cfg: Config, out_png: str, subtitle: str = "") -> str:
    """Génère un PNG transparent 9:16 avec le nom du film (et un sous-titre)."""
    from PIL import Image, ImageDraw

    W, H = cfg.width, cfg.height
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    accent = _hex_rgb(cfg.highlight_color)

    font = _load_font(int(W * 0.11))
    lines = _wrap_lines(draw, title.upper(), font, int(W * 0.86))
    ascent = font.getbbox("Ag")
    line_h = (ascent[3] - ascent[1]) + int(W * 0.03)
    block_h = line_h * len(lines)
    y = (H - block_h) // 2

    for line in lines:
        lw = draw.textlength(line, font=font)
        draw.text(((W - lw) / 2, y), line, font=font, fill=(255, 255, 255, 255),
                  stroke_width=4, stroke_fill=(0, 0, 0, 255))
        y += line_h

    # Petit liseré d'accent sous le titre.
    uw = int(W * 0.22)
    ux = (W - uw) // 2
    uy = y + int(W * 0.015)
    draw.rounded_rectangle([ux, uy, ux + uw, uy + int(W * 0.013)],
                           radius=6, fill=accent + (255,))

    # Sous-titre (ex. « PARTIE 1 ») sous le liseré.
    if subtitle.strip():
        sfont = _load_font(int(W * 0.058))
        sw = draw.textlength(subtitle.upper(), font=sfont)
        draw.text(((W - sw) / 2, uy + int(W * 0.04)), subtitle.upper(), font=sfont,
                  fill=accent + (255,), stroke_width=2, stroke_fill=(0, 0, 0, 255))

    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    img.save(out_png)
    return out_png


def make_suite_image(next_part: int, cfg: Config, out_png: str) -> str:
    """Carton de fin des parties intermédiaires : renvoie vers la partie suivante.

    Objectif : transformer le spectateur en abonné (« reviens pour la suite »),
    au lieu de l'envoyer hors de TikTok. C'est ce qui fait grimper un compte.
    """
    from PIL import Image, ImageDraw

    W, H = cfg.width, cfg.height
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    accent = _hex_rgb(cfg.highlight_color)

    big = _load_font(int(W * 0.105))
    small = _load_font(int(W * 0.055))
    line1, line2 = "LA SUITE DANS", f"LA PARTIE {next_part}"
    sub_lines = _wrap_lines(draw, "Abonne-toi pour ne pas rater la suite", small, int(W * 0.80))

    ab = big.getbbox("Ag")
    lh_big = (ab[3] - ab[1]) + int(W * 0.03)
    asb = small.getbbox("Ag")
    lh_sm = (asb[3] - asb[1]) + int(W * 0.02)
    gap = int(W * 0.045)
    pad = int(W * 0.07)

    text_w = max(draw.textlength(line1, font=big), draw.textlength(line2, font=big),
                 max((draw.textlength(l, font=small) for l in sub_lines), default=0))
    box_w = min(W - int(W * 0.08), int(text_w) + pad * 2)
    box_h = lh_big * 2 + gap + lh_sm * len(sub_lines) + pad * 2
    bx0, by0 = (W - box_w) // 2, (H - box_h) // 2
    draw.rounded_rectangle([bx0, by0, bx0 + box_w, by0 + box_h],
                           radius=int(W * 0.03), fill=(0, 0, 0, 190))

    y = by0 + pad
    for line, color in ((line1, (255, 255, 255, 255)), (line2, accent + (255,))):
        lw = draw.textlength(line, font=big)
        draw.text(((W - lw) / 2, y), line, font=big, fill=color,
                  stroke_width=3, stroke_fill=(0, 0, 0, 255))
        y += lh_big
    y += gap
    for line in sub_lines:
        lw = draw.textlength(line, font=small)
        draw.text(((W - lw) / 2, y), line, font=small, fill=(255, 255, 255, 255),
                  stroke_width=2, stroke_fill=(0, 0, 0, 255))
        y += lh_sm

    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    img.save(out_png)
    return out_png


def make_hook_image(text: str, cfg: Config, out_png: str) -> str:
    """Bandeau d'accroche affiché en haut de l'écran pendant les premières secondes."""
    from PIL import Image, ImageDraw

    W, H = cfg.width, cfg.height
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = _load_font(int(W * 0.066))
    lines = _wrap_lines(draw, text, font, int(W * 0.84))
    asc = font.getbbox("Ag")
    line_h = (asc[3] - asc[1]) + int(W * 0.022)
    pad = int(W * 0.045)
    text_w = max((draw.textlength(l, font=font) for l in lines), default=0)
    box_w = min(W - int(W * 0.06), int(text_w) + pad * 2)
    box_h = line_h * len(lines) + pad * 2
    bx0 = (W - box_w) // 2
    by0 = int(H * 0.13)  # vers le haut, sous l'UI de TikTok

    draw.rounded_rectangle([bx0, by0, bx0 + box_w, by0 + box_h],
                           radius=int(W * 0.025), fill=(0, 0, 0, 170))
    y = by0 + pad
    for line in lines:
        lw = draw.textlength(line, font=font)
        draw.text(((W - lw) / 2, y), line, font=font, fill=(255, 255, 255, 255),
                  stroke_width=3, stroke_fill=(0, 0, 0, 255))
        y += line_h

    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    img.save(out_png)
    return out_png


def _hex_rgb(hex_rgb: str) -> tuple:
    hex_rgb = hex_rgb.lstrip("#")
    if len(hex_rgb) != 6:
        hex_rgb = "FFE000"
    return tuple(int(hex_rgb[i:i + 2], 16) for i in (0, 2, 4))


# --------------------------------------------------------------------------- #
# Orchestration du rendu
# --------------------------------------------------------------------------- #

def render_montage(video_path: str, scenes: List[Scene], cfg: Config,
                   key: str, out_path: str, subtitle: str = "",
                   part: int = None, n_parts: int = 1) -> dict:
    """Rend chaque scène puis les assemble avec transitions et incrustations.

    Ouverture optimisée pour la rétention TikTok :
      - le titre du film est incrusté SUR la première scène (pas de carton figé
        qui ferait fuir avant l'action) ;
      - la meilleure accroche de la partie s'affiche en bandeau haut au démarrage.

    Carton de fin : les parties intermédiaires renvoient vers la partie suivante
    (« La suite dans la Partie N+1 ») pour gagner des abonnés ; seule la dernière
    partie (ou un montage unique) affiche le CTA Telegram.
    """
    fps = cfg.montage_fps
    is_last_part = (part is None) or (part >= n_parts)

    # (C) Accroche : la plus forte de la partie -> bandeau haut en ouverture.
    hook_png = None
    best = max(scenes, key=lambda s: s[2].final_score, default=None)
    hook_text = (best[2].hook or "").strip() if best else ""
    if cfg.show_hook and hook_text:
        hook_png = os.path.join(cfg.work_dir, f"{key}_hook.png")
        make_hook_image(hook_text, cfg, hook_png)

    # (A) Titre incrusté sur l'action plutôt qu'un générique figé.
    title_png = None
    if cfg.intro_title.strip():
        title_png = os.path.join(cfg.work_dir, f"{key}_title.png")
        make_title_image(cfg.intro_title, cfg, title_png, subtitle=subtitle)

    # (B) Carton de fin : « suite » pour les parties intermédiaires, sinon CTA.
    end_png = end_kind = None
    if not is_last_part:
        end_png = os.path.join(cfg.work_dir, f"{key}_suite.png")
        make_suite_image(part + 1, cfg, end_png)
        end_kind = f"suite → Partie {part + 1}"
    elif cfg.cta_enabled and cfg.cta_text.strip():
        end_png = os.path.join(cfg.work_dir, f"{key}_cta.png")
        make_cta_image(cfg.cta_text, cfg, end_png)
        end_kind = "carton CTA"

    scene_files: List[str] = []
    last_i = len(scenes) - 1
    for i, (start, end, _moment) in enumerate(scenes):
        scene_file = os.path.join(cfg.work_dir, f"{key}_montage_scene{i:02d}.mp4")
        first, is_last = (i == 0), (i == last_i)
        extras = []
        if first and title_png:
            extras.append(f"titre « {cfg.intro_title} »")
        if first and hook_png:
            extras.append("accroche")
        if is_last and end_png:
            extras.append(end_kind)
        log.info("  scène %d/%d  [%.0fs → %.0fs]%s", i + 1, len(scenes), start, end,
                 ("  + " + " + ".join(extras)) if extras else "")
        media.render_scene(video_path, start, cfg.scene_duration, scene_file, cfg, fps,
                           cta_png=end_png if is_last else None,
                           title_png=title_png if first else None,
                           hook_png=hook_png if first else None,
                           title_hold=cfg.intro_duration, hook_hold=cfg.hook_duration)
        scene_files.append(scene_file)

    log.info("Assemblage des %d scène(s) avec transitions « %s »…", len(scene_files), cfg.transition)
    media.concat_scenes(scene_files, out_path, cfg, fps)

    # Nettoyage des fichiers intermédiaires (libère le disque, important en multi-parties).
    for f in scene_files:
        try:
            os.remove(f)
        except OSError:
            pass

    info = media.probe(out_path)
    return {
        "output_path": out_path,
        "duration": info.duration,
        "hook": hook_text,
        "scenes": [
            {"index": i + 1, "start": s, "end": e, "hook": m.hook, "emotion": m.emotion,
             "final_score": round(m.final_score, 1)}
            for i, (s, e, m) in enumerate(scenes)
        ],
    }
