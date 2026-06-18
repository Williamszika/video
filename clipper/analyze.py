"""Analyse intelligente des moments forts via l'API Claude.

C'est le cerveau du système. On découpe la transcription en tranches, on demande
à Claude (modèle Opus 4.8 par défaut) de repérer les moments les plus
émouvants, drôles, choquants ou captivants — ceux qui donnent envie de
s'arrêter de scroller — et de proposer une accroche pour chacun.

On utilise :
  - les sorties structurées (JSON schema) pour un parsing 100 % fiable ;
  - la réflexion adaptative (adaptive thinking) + effort réglable ;
  - le cache de prompt sur la consigne système (identique entre tranches).
"""

from __future__ import annotations

import json
from typing import List, Optional

from .config import Config
from .models import Moment, Transcript
from .utils import format_timestamp, get_logger

log = get_logger()


SYSTEM_PROMPT = """\
Tu es un monteur expert en contenu viral pour TikTok, Reels et Shorts. Ta \
spécialité : repérer dans une longue vidéo les instants qui captent \
l'attention en moins de 2 secondes et donnent envie de regarder jusqu'au bout.

On va te donner la transcription horodatée d'une tranche de vidéo. Tu dois \
identifier les MEILLEURS moments à transformer en shorts verticaux.

Un bon moment de short :
- déclenche une émotion forte : rire, surprise, émotion, indignation, frisson, \
inspiration, suspense ;
- est « chaud » et captivant : confession, révélation, punchline, retournement, \
moment gênant, dispute, déclaration choc, histoire personnelle intense ;
- se suffit à lui-même : on comprend sans contexte extérieur ;
- commence par une accroche naturelle (une phrase qui intrigue) et se termine \
sur une chute ou une montée d'intensité ;
- dure idéalement autour de la cible demandée (proche de 2 minutes), jamais \
en dessous du minimum ni au-dessus du maximum indiqués.

Règles importantes :
- start et end sont exprimés EN SECONDES, dans la fenêtre temporelle fournie ;
- choisis des bornes qui tombent sur des débuts/fins de phrase ;
- évite les blancs, les hésitations interminables, les passages plats ;
- le champ "hook" est une accroche très courte (max 60 caractères), percutante, \
en français, qui donnerait envie de cliquer (pas de hashtags) ;
- "quote" est la phrase-clé exacte du moment ;
- "emotion" est un seul mot : drôle, émouvant, choquant, inspirant, tendu, \
gênant, motivant, etc. ;
- "score" est une note de viralité ABSOLUE de 0 à 100 (sois exigeant et \
cohérent d'une tranche à l'autre : 90+ = exceptionnel, 70-89 = très bon, \
50-69 = correct, <50 = faible) ;
- "reason" explique en une phrase pourquoi ce moment marche.

Ne retourne que les meilleurs moments réellement marquants ; mieux vaut peu de \
pépites que beaucoup de passages moyens.\
"""


MOMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "moments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "hook": {"type": "string"},
                    "quote": {"type": "string"},
                    "emotion": {"type": "string"},
                    "score": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["start", "end", "hook", "quote", "emotion", "score", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["moments"],
    "additionalProperties": False,
}


def _build_chunks(transcript: Transcript, chunk_seconds: float):
    """Découpe les segments en tranches temporelles successives."""
    if not transcript.segments:
        return []
    chunks = []
    current = []
    chunk_start = transcript.segments[0].start
    for seg in transcript.segments:
        if seg.start - chunk_start >= chunk_seconds and current:
            chunks.append((chunk_start, current[-1].end, current))
            current = []
            chunk_start = seg.start
        current.append(seg)
    if current:
        chunks.append((chunk_start, current[-1].end, current))
    return chunks


def _format_chunk(segments) -> str:
    """Représente une tranche en lignes 't=<sec>  [hh:mm:ss]  texte'."""
    lines = []
    for seg in segments:
        if not seg.text:
            continue
        lines.append(f"t={seg.start:.1f}  [{format_timestamp(seg.start)}]  {seg.text}")
    return "\n".join(lines)


def _get_client(cfg: Config):
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Le paquet anthropic n'est pas installé. Lance : pip install anthropic"
        ) from exc
    if cfg.api_key:
        return anthropic.Anthropic(api_key=cfg.api_key)
    return anthropic.Anthropic()  # lit ANTHROPIC_API_KEY dans l'environnement


def _extract_json(message) -> dict:
    """Récupère le bloc texte JSON d'une réponse Claude (en ignorant le thinking)."""
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)
    raise RuntimeError("Réponse de Claude sans bloc texte exploitable.")


def analyze_transcript(transcript: Transcript, cfg: Config) -> List[Moment]:
    """Renvoie tous les moments candidats repérés dans la vidéo."""
    client = _get_client(cfg)
    chunk_seconds = cfg.analysis_chunk_minutes * 60.0
    chunks = _build_chunks(transcript, chunk_seconds)
    log.info("Analyse de %d tranche(s) avec %s…", len(chunks), cfg.model)

    all_moments: List[Moment] = []
    for i, (start, end, segments) in enumerate(chunks, 1):
        body = _format_chunk(segments)
        if not body.strip():
            continue

        user_prompt = (
            f"Fenêtre temporelle de cette tranche : de {start:.1f}s à {end:.1f}s.\n"
            f"Durée cible d'un short : {cfg.target_duration:.0f}s "
            f"(minimum {cfg.min_duration:.0f}s, maximum {cfg.max_duration:.0f}s).\n"
            f"Propose jusqu'à {cfg.candidates_per_chunk} moments candidats, "
            f"classés du meilleur au moins bon.\n\n"
            f"Transcription :\n{body}"
        )

        message = client.messages.create(
            model=cfg.model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": cfg.effort,
                "format": {"type": "json_schema", "schema": MOMENTS_SCHEMA},
            },
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_prompt}],
        )

        data = _extract_json(message)
        moments = [Moment.from_dict(m) for m in data.get("moments", [])]
        # On borne les temps à la fenêtre de la tranche par sécurité.
        for m in moments:
            m.start = max(start, min(m.start, end))
            m.end = max(m.start, min(m.end, end))
        all_moments.extend(moments)
        log.info("  tranche %d/%d : %d moment(s) candidat(s).", i, len(chunks), len(moments))

    log.info("Analyse terminée : %d moment(s) candidat(s) au total.", len(all_moments))
    return all_moments


def load_or_analyze(transcript: Transcript, cfg: Config,
                    cache_path: Optional[str] = None) -> List[Moment]:
    """Charge l'analyse depuis le cache si présent, sinon l'effectue."""
    import os

    if cache_path and os.path.isfile(cache_path):
        log.info("Analyse chargée depuis le cache : %s", cache_path)
        with open(cache_path, "r", encoding="utf-8") as fh:
            return [Moment.from_dict(m) for m in json.load(fh)]

    moments = analyze_transcript(transcript, cfg)

    if cache_path:
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump([m.to_dict() for m in moments], fh, ensure_ascii=False)
        log.info("Analyse mise en cache : %s", cache_path)

    return moments
