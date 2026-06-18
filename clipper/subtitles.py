"""Génération de sous-titres au format ASS (libass), incrustables par ffmpeg.

Style « animé » : on affiche quelques mots à la fois et on surligne le mot en
cours de prononciation (effet karaoké / pop très utilisé sur TikTok). Les temps
sont relatifs au début du clip.

Module pur (aucune dépendance externe) -> testable directement.
"""

from __future__ import annotations

from typing import List, Optional

from .config import Config
from .models import Word
from .utils import format_ass_time


def hex_to_ass(hex_rgb: str) -> str:
    """Convertit 'RRGGBB' (hex) en couleur ASS '&H00BBGGRR'."""
    hex_rgb = hex_rgb.lstrip("#")
    if len(hex_rgb) != 6:
        hex_rgb = "FFFFFF"
    r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
    return f"&H00{b}{g}{r}".upper()


def _ass_escape(text: str) -> str:
    """Neutralise les caractères spéciaux ASS dans le texte."""
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def _header(cfg: Config) -> str:
    primary = hex_to_ass(cfg.primary_color)
    highlight = hex_to_ass(cfg.highlight_color)
    outline = hex_to_ass(cfg.outline_color)
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {cfg.width}
PlayResY: {cfg.height}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{cfg.font_name},{cfg.font_size},{primary},{highlight},{outline},&H64000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,{cfg.margin_vertical},1
Style: Hook,{cfg.font_name},{int(cfg.font_size * 0.8)},{highlight},{highlight},{outline},&H64000000,-1,0,0,0,100,100,0,0,1,5,2,8,80,80,140,1

[Events]
Format: Layer, Start, End, Style, MarginL, MarginR, Effect, Text
"""


def _dialogue(start: float, end: float, text: str, style: str = "Default") -> str:
    return f"Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},{style},,0,0,0,,{text}"


def _chunk_words(words: List[Word], size: int) -> List[List[Word]]:
    return [words[i:i + size] for i in range(0, len(words), max(1, size))]


def _render_highlighted(chunk: List[Word], active: int, cfg: Config) -> str:
    """Construit le texte d'une carte avec le mot actif surligné et agrandi."""
    primary = hex_to_ass(cfg.primary_color)
    highlight = hex_to_ass(cfg.highlight_color)
    parts = []
    for i, w in enumerate(chunk):
        token = _ass_escape(w.text)
        if i == active:
            parts.append(f"{{\\1c{highlight}\\fscx118\\fscy118}}{token}{{\\1c{primary}\\fscx100\\fscy100}}")
        else:
            parts.append(token)
    return " ".join(parts)


def build_ass(words: List[Word], cfg: Config, clip_start: float = 0.0,
              hook: Optional[str] = None, clip_duration: Optional[float] = None) -> str:
    """Génère le contenu ASS pour un clip.

    `words` porte des temps ABSOLUS (ceux de la vidéo) ; on les ramène au début
    du clip via `clip_start`.
    """
    lines = [_header(cfg)]

    # Accroche en haut pendant les premières secondes.
    if hook and cfg.show_hook:
        end = cfg.hook_duration
        if clip_duration:
            end = min(end, clip_duration)
        lines.append(_dialogue(0.0, end, _ass_escape(hook.upper()), style="Hook"))

    rel = [Word(start=max(0.0, w.start - clip_start), end=max(0.0, w.end - clip_start),
                text=w.text, prob=w.prob) for w in words]

    if cfg.subtitle_style == "animated":
        for chunk in _chunk_words(rel, cfg.words_per_caption):
            if not chunk:
                continue
            for i, w in enumerate(chunk):
                seg_start = w.start
                seg_end = chunk[i + 1].start if i + 1 < len(chunk) else w.end
                if seg_end <= seg_start:
                    seg_end = seg_start + 0.3
                lines.append(_dialogue(seg_start, seg_end, _render_highlighted(chunk, i, cfg)))

    elif cfg.subtitle_style == "simple":
        for chunk in _chunk_words(rel, cfg.words_per_caption):
            if not chunk:
                continue
            text = _ass_escape(" ".join(w.text for w in chunk))
            lines.append(_dialogue(chunk[0].start, chunk[-1].end, text))

    return "\n".join(lines) + "\n"


def write_ass(path: str, words: List[Word], cfg: Config, clip_start: float = 0.0,
              hook: Optional[str] = None, clip_duration: Optional[float] = None) -> str:
    """Écrit le fichier .ass sur le disque et renvoie son chemin."""
    import os

    content = build_ass(words, cfg, clip_start=clip_start, hook=hook, clip_duration=clip_duration)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path
