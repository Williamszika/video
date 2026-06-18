"""Sélection finale des clips à partir des moments candidats.

Étapes :
  1. score combiné (Claude + énergie audio) ;
  2. ajustement de la fenêtre vers la durée cible (~2 min) ;
  3. recalage des bornes sur des débuts/fins de phrase (pas de coupe en plein mot) ;
  4. sélection gloutonne des meilleurs clips sans chevauchement.

Module volontairement « pur » (aucune dépendance externe) afin d'être testable.
"""

from __future__ import annotations

from typing import List, Optional

from .config import Config
from .models import Clip, Moment, Transcript
from .utils import get_logger

log = get_logger()


def _nearest(value: float, candidates: List[float], tolerance: float = 5.0) -> float:
    """Renvoie le candidat le plus proche de value s'il est dans la tolérance."""
    if not candidates:
        return value
    best = min(candidates, key=lambda c: abs(c - value))
    return best if abs(best - value) <= tolerance else value


def adjust_window(start: float, end: float, cfg: Config, video_duration: float) -> tuple[float, float]:
    """Étire ou rogne la fenêtre pour viser la durée cible, dans les bornes min/max."""
    start = max(0.0, start)
    end = min(video_duration, max(end, start))
    duration = end - start

    if duration < cfg.target_duration:
        # On complète vers l'avant (suite), puis vers l'arrière (mise en contexte).
        extra = cfg.target_duration - duration
        forward = min(extra, video_duration - end)
        end += forward
        extra -= forward
        if extra > 0:
            back = min(extra, start)
            start -= back

    if end - start > cfg.max_duration:
        end = start + cfg.max_duration

    return start, end


def snap_to_sentences(start: float, end: float, transcript: Transcript,
                      cfg: Config, video_duration: float) -> tuple[float, float]:
    """Recale les bornes sur des débuts/fins de segment (phrases)."""
    seg_starts = [s.start for s in transcript.segments]
    seg_ends = [s.end for s in transcript.segments]

    snapped_start = _nearest(start, seg_starts)
    snapped_end = _nearest(end, seg_ends)

    snapped_start = max(0.0, snapped_start)
    snapped_end = min(video_duration, snapped_end)
    if snapped_end <= snapped_start:
        snapped_end = min(video_duration, snapped_start + cfg.min_duration)

    # Si le recalage a trop raccourci, on réétire vers une fin de phrase.
    if snapped_end - snapped_start < cfg.min_duration:
        target_end = min(video_duration, snapped_start + cfg.target_duration)
        candidates = [e for e in seg_ends if e > snapped_start + cfg.min_duration]
        if candidates:
            snapped_end = _nearest(target_end, candidates, tolerance=cfg.max_duration)
        else:
            snapped_end = target_end

    # Garde-fou final sur la durée maximale.
    if snapped_end - snapped_start > cfg.max_duration:
        snapped_end = snapped_start + cfg.max_duration

    return snapped_start, snapped_end


def compute_scores(moments: List[Moment], cfg: Config, audio=None) -> None:
    """Remplit audio_score et final_score (sur place) pour chaque moment."""
    if audio is not None:
        w_ai, w_audio = cfg.weight_ai, cfg.weight_audio
    else:
        w_ai, w_audio = 1.0, 0.0
    total = w_ai + w_audio or 1.0

    for m in moments:
        if audio is not None:
            m.audio_score = audio.normalized_window_score(m.start, m.end)
        m.final_score = (w_ai * m.score + w_audio * m.audio_score) / total


def _overlaps(start: float, end: float, chosen: List[Clip], gap: float) -> bool:
    for c in chosen:
        if not (end + gap <= c.start or start - gap >= c.end):
            return True
    return False


def select_clips(moments: List[Moment], transcript: Transcript, cfg: Config,
                 audio=None, video_duration: Optional[float] = None) -> List[Clip]:
    """Sélectionne jusqu'à cfg.num_clips clips finaux, sans chevauchement."""
    if video_duration is None:
        video_duration = transcript.duration

    compute_scores(moments, cfg, audio)
    ranked = sorted(moments, key=lambda m: m.final_score, reverse=True)

    chosen: List[Clip] = []
    for m in ranked:
        if len(chosen) >= cfg.num_clips:
            break
        start, end = adjust_window(m.start, m.end, cfg, video_duration)
        start, end = snap_to_sentences(start, end, transcript, cfg, video_duration)

        if end - start < cfg.min_duration * 0.6:
            continue  # trop court même après ajustement
        if _overlaps(start, end, chosen, cfg.min_gap):
            continue

        clip = Clip(
            index=len(chosen) + 1,
            start=start,
            end=end,
            hook=m.hook,
            emotion=m.emotion,
            final_score=round(m.final_score, 1),
            quote=m.quote,
            reason=m.reason,
            words=transcript.words_between(start, end),
        )
        chosen.append(clip)

    # On renumérote dans l'ordre chronologique pour des noms de fichiers cohérents.
    chosen.sort(key=lambda c: c.start)
    for i, clip in enumerate(chosen, 1):
        clip.index = i

    log.info("%d clip(s) sélectionné(s) sur %d candidat(s).", len(chosen), len(moments))
    return chosen
