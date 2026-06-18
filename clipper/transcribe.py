"""Transcription locale avec faster-whisper, horodatage au niveau du mot.

faster-whisper gère nativement les fichiers longs (découpage interne + VAD),
ce qui permet de traiter des vidéos de plus de 2 heures sans tout charger en
mémoire. L'import est différé pour que le reste du package reste utilisable
sans la dépendance installée.
"""

from __future__ import annotations

import os
from typing import Optional

from .config import Config
from .models import Segment, Transcript, Word
from .utils import get_logger, human_duration

log = get_logger()


def _pick_device(requested: str) -> tuple[str, str]:
    """Choisit (device, compute_type) en fonction de la demande et du matériel."""
    if requested == "cpu":
        return "cpu", "int8"
    if requested == "cuda":
        return "cuda", "float16"
    # auto : on tente CUDA, sinon CPU.
    try:
        import ctranslate2  # faster-whisper dépend de ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:  # pragma: no cover - dépend du matériel
        pass
    return "cpu", "int8"


def transcribe(audio_path: str, cfg: Config) -> Transcript:
    """Transcrit un fichier audio et renvoie un Transcript avec mots horodatés."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "faster-whisper n'est pas installé. Lance : pip install faster-whisper"
        ) from exc

    device, compute_type = _pick_device(cfg.whisper_device)
    if cfg.whisper_compute_type != "auto":
        compute_type = cfg.whisper_compute_type

    log.info("Chargement du modèle Whisper '%s' (%s, %s)…",
             cfg.whisper_model, device, compute_type)
    model = WhisperModel(cfg.whisper_model, device=device, compute_type=compute_type)

    language = None if cfg.language == "auto" else cfg.language
    log.info("Transcription en cours (cela peut prendre un moment sur les longues vidéos)…")

    segments_iter, info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,          # indispensable pour les sous-titres animés
        vad_filter=True,               # supprime les silences -> meilleur découpage
        vad_parameters={"min_silence_duration_ms": 500},
        beam_size=5,
    )

    detected_lang = getattr(info, "language", None) or cfg.language
    segments: list[Segment] = []
    last_log = 0.0

    for seg in segments_iter:
        words = []
        for w in (seg.words or []):
            text = (w.word or "").strip()
            if not text:
                continue
            words.append(Word(start=float(w.start), end=float(w.end),
                              text=text, prob=float(getattr(w, "probability", 1.0))))
        segments.append(Segment(start=float(seg.start), end=float(seg.end),
                                text=(seg.text or "").strip(), words=words))

        # Log de progression toutes les ~2 minutes de contenu transcrit.
        if seg.end - last_log > 120:
            log.info("  … transcrit jusqu'à %s", human_duration(seg.end))
            last_log = seg.end

    duration = float(getattr(info, "duration", 0.0)) or (segments[-1].end if segments else 0.0)
    log.info("Transcription terminée : %d segments, langue=%s.", len(segments), detected_lang)
    return Transcript(language=detected_lang, duration=duration, segments=segments)


def load_or_transcribe(audio_path: str, cfg: Config, cache_path: Optional[str] = None) -> Transcript:
    """Charge la transcription depuis le cache si présent, sinon la calcule."""
    import json

    if cache_path and os.path.isfile(cache_path):
        log.info("Transcription chargée depuis le cache : %s", cache_path)
        with open(cache_path, "r", encoding="utf-8") as fh:
            return Transcript.from_dict(json.load(fh))

    transcript = transcribe(audio_path, cfg)

    if cache_path:
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(transcript.to_dict(), fh, ensure_ascii=False)
        log.info("Transcription mise en cache : %s", cache_path)

    return transcript
