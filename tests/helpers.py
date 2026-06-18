"""Fabriques d'objets synthétiques pour les tests."""

from __future__ import annotations

from clipper.models import Segment, Transcript, Word


def make_transcript(duration: float = 600.0, seg_len: float = 10.0,
                    words_per_seg: int = 5, language: str = "fr") -> Transcript:
    """Transcription régulière : un segment toutes les `seg_len` secondes."""
    segments = []
    t = 0.0
    idx = 0
    while t < duration:
        end = min(t + seg_len, duration)
        words = []
        step = (end - t) / words_per_seg
        for i in range(words_per_seg):
            ws = t + i * step
            we = ws + step * 0.9
            words.append(Word(start=ws, end=we, text=f"mot{idx}", prob=0.99))
            idx += 1
        segments.append(Segment(start=t, end=end, text=" ".join(w.text for w in words),
                                words=words))
        t = end
    return Transcript(language=language, duration=duration, segments=segments)
