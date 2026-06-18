"""Petites fonctions utilitaires partagées."""

from __future__ import annotations

import logging
import sys


def get_logger(name: str = "clipper") -> logging.Logger:
    """Logger configuré une seule fois, sortie sur stderr."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s",
                                                datefmt="%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def format_timestamp(seconds: float, *, sep: str = ":", millis: bool = False) -> str:
    """Formate un nombre de secondes en HH:MM:SS (ou avec millisecondes).

    >>> format_timestamp(3661.5)
    '01:01:01'
    >>> format_timestamp(75.25, millis=True)
    '00:01:15.250'
    """
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    base = f"{hours:02d}{sep}{minutes:02d}{sep}{secs:02d}"
    if millis:
        return f"{base}.{ms:03d}"
    return base


def format_ass_time(seconds: float) -> str:
    """Formate en H:MM:SS.cc (centisecondes), format attendu par les fichiers ASS."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    hours, rem = divmod(total_cs, 360_000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"


def slugify(text: str, max_len: int = 40) -> str:
    """Transforme un texte en nom de fichier sûr (ascii, tirets)."""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_len].strip("-") or "clip"


def human_duration(seconds: float) -> str:
    """'2h 14m 03s' pour l'affichage."""
    seconds = int(round(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes:02d}m")
    parts.append(f"{secs:02d}s")
    return " ".join(parts)
