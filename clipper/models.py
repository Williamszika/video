"""Structures de données partagées entre les étapes du pipeline.

Toutes sont sérialisables en JSON (méthodes to_dict / from_dict) afin de pouvoir
mettre en cache la transcription et l'analyse, et reprendre un traitement.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Word:
    start: float
    end: float
    text: str
    prob: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Word":
        return cls(start=d["start"], end=d["end"], text=d["text"], prob=d.get("prob", 1.0))


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "text": self.text,
                "words": [w.to_dict() for w in self.words]}

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(start=d["start"], end=d["end"], text=d["text"],
                   words=[Word.from_dict(w) for w in d.get("words", [])])


@dataclass
class Transcript:
    language: str
    duration: float
    segments: List[Segment] = field(default_factory=list)

    @property
    def words(self) -> List[Word]:
        """Liste à plat de tous les mots horodatés."""
        out: List[Word] = []
        for seg in self.segments:
            out.extend(seg.words)
        return out

    @property
    def text(self) -> str:
        return " ".join(seg.text.strip() for seg in self.segments).strip()

    def words_between(self, start: float, end: float) -> List[Word]:
        """Mots dont le centre tombe dans [start, end)."""
        result = []
        for w in self.words:
            mid = (w.start + w.end) / 2.0
            if start <= mid < end:
                result.append(w)
        return result

    def to_dict(self) -> dict:
        return {"language": self.language, "duration": self.duration,
                "segments": [s.to_dict() for s in self.segments]}

    @classmethod
    def from_dict(cls, d: dict) -> "Transcript":
        return cls(language=d["language"], duration=d["duration"],
                   segments=[Segment.from_dict(s) for s in d.get("segments", [])])


@dataclass
class Moment:
    """Un moment candidat repéré par l'analyse (avant sélection finale)."""
    start: float
    end: float
    hook: str                 # accroche courte / titre du short
    score: float              # score de viralité 0-100 (Claude)
    emotion: str = ""         # ex : "drôle", "émouvant", "choquant", "inspirant"
    reason: str = ""          # justification de l'analyse
    quote: str = ""           # phrase-clé du moment
    audio_score: float = 0.0  # énergie audio normalisée 0-100 (rempli plus tard)
    final_score: float = 0.0  # score combiné (rempli plus tard)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Moment":
        return cls(
            start=float(d["start"]), end=float(d["end"]),
            hook=d.get("hook", ""), score=float(d.get("score", 0.0)),
            emotion=d.get("emotion", ""), reason=d.get("reason", ""),
            quote=d.get("quote", ""), audio_score=float(d.get("audio_score", 0.0)),
            final_score=float(d.get("final_score", 0.0)),
        )


@dataclass
class Clip:
    """Un short final, prêt à être rendu."""
    index: int
    start: float
    end: float
    hook: str
    emotion: str
    final_score: float
    quote: str = ""
    reason: str = ""
    words: List[Word] = field(default_factory=list)
    output_path: Optional[str] = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration"] = self.duration
        d.pop("words", None)  # trop verbeux pour le manifeste
        return d
