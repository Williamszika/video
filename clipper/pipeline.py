"""Orchestration de bout en bout : d'une vidéo longue aux shorts verticaux."""

from __future__ import annotations

import json
import os
from typing import List

from . import analyze, audio_energy, media, montage, select, subtitles, transcribe
from .config import Config
from .models import Clip
from .utils import get_logger, human_duration, slugify

log = get_logger()


def _base_key(video_path: str) -> str:
    return slugify(os.path.splitext(os.path.basename(video_path))[0], max_len=60)


def run(video_path: str, cfg: Config) -> dict:
    """Exécute le pipeline complet et renvoie un manifeste (dict)."""
    cfg.validate()
    media.ensure_tools()

    os.makedirs(cfg.output_dir, exist_ok=True)
    os.makedirs(cfg.work_dir, exist_ok=True)
    key = _base_key(video_path)

    # 1. Sonde du fichier source -------------------------------------------------
    info = media.probe(video_path)
    log.info("Source : %dx%d, %.1f fps, durée %s, audio=%s.",
             info.width, info.height, info.fps, human_duration(info.duration), info.has_audio)
    if not info.has_audio:
        raise RuntimeError("La vidéo ne contient pas de piste audio ; impossible d'analyser le contenu.")

    # 2. Extraction audio --------------------------------------------------------
    audio_wav = os.path.join(cfg.work_dir, f"{key}.wav")
    if not os.path.isfile(audio_wav):
        log.info("Extraction de l'audio…")
        media.extract_audio(video_path, audio_wav)

    # 3. Transcription (avec cache) ---------------------------------------------
    transcript_cache = os.path.join(cfg.work_dir, f"{key}.transcript.json")
    transcript = transcribe.load_or_transcribe(audio_wav, cfg, cache_path=transcript_cache)
    if not transcript.segments:
        raise RuntimeError("Transcription vide : la vidéo ne contient peut-être pas de parole.")

    # 4. Énergie audio -----------------------------------------------------------
    energy = None
    try:
        energy = audio_energy.analyze(audio_wav)
    except Exception as exc:  # l'analyse audio est un bonus, jamais bloquante
        log.warning("Analyse audio ignorée (%s).", exc)

    # 5. Analyse des moments forts (avec cache) ---------------------------------
    analysis_cache = os.path.join(cfg.work_dir, f"{key}.moments.json")
    moments = analyze.load_or_analyze(transcript, cfg, cache_path=analysis_cache)
    if not moments:
        raise RuntimeError("Aucun moment fort détecté par l'analyse.")

    # 6bis. Mode montage : une seule vidéo « bande-annonce » ---------------------
    if cfg.mode == "montage":
        scenes = montage.select_scenes(moments, transcript, cfg, audio=energy,
                                       video_duration=info.duration)
        if not scenes:
            raise RuntimeError("Aucune scène retenue pour le montage.")
        out_name = f"{cfg.seed_label}{key}_montage.mp4"
        out_path = os.path.join(cfg.output_dir, out_name)
        log.info("Rendu du montage (~%.0f min)…", cfg.montage_duration / 60.0)
        result = montage.render_montage(video_path, scenes, cfg, key, out_path)

        manifest = {
            "source": os.path.abspath(video_path),
            "source_duration": info.duration,
            "mode": "montage",
            "config": cfg.to_dict(),
            "language": transcript.language,
            "output_path": result["output_path"],
            "duration": result["duration"],
            "scenes": result["scenes"],
        }
        manifest_path = os.path.join(cfg.output_dir, f"{key}.montage.manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        log.info("Terminé : montage de %s dans %s (manifeste : %s).",
                 human_duration(result["duration"]), result["output_path"],
                 os.path.basename(manifest_path))
        return manifest

    # 6. Sélection des clips -----------------------------------------------------
    clips = select.select_clips(moments, transcript, cfg, audio=energy,
                                video_duration=info.duration)
    if not clips:
        raise RuntimeError("Aucun clip retenu après sélection.")

    # 7. Sous-titres + rendu -----------------------------------------------------
    subtitles_enabled = cfg.subtitles and cfg.subtitle_style != "none"
    ass_available = media.has_filter("ass")
    if subtitles_enabled and not ass_available:
        log.warning(
            "Le filtre 'ass' est absent de ton ffmpeg (compilé sans libass) : "
            "les shorts seront produits SANS sous-titres incrustés. Pour activer "
            "les sous-titres animés, installe un ffmpeg avec libass "
            "(macOS : « brew install ffmpeg-full »)."
        )

    rendered: List[Clip] = []
    for clip in clips:
        out_name = f"{cfg.seed_label}{key}_short{clip.index:02d}_{slugify(clip.hook)}.mp4"
        out_path = os.path.join(cfg.output_dir, out_name)
        ass_path = None

        if subtitles_enabled and ass_available and clip.words:
            ass_path = os.path.join(cfg.work_dir, f"{key}_short{clip.index:02d}.ass")
            subtitles.write_ass(ass_path, clip.words, cfg, clip_start=clip.start,
                                hook=clip.hook, clip_duration=clip.duration)

        log.info("Rendu du short %d/%d  [%s]  « %s » (%s)…",
                 clip.index, len(clips), human_duration(clip.duration), clip.hook, clip.emotion)
        media.render_clip(video_path, clip.start, clip.duration, out_path, cfg, ass_path=ass_path)
        clip.output_path = out_path
        rendered.append(clip)

    # 8. Manifeste ---------------------------------------------------------------
    manifest = {
        "source": os.path.abspath(video_path),
        "source_duration": info.duration,
        "config": cfg.to_dict(),
        "language": transcript.language,
        "num_clips": len(rendered),
        "clips": [c.to_dict() for c in rendered],
    }
    manifest_path = os.path.join(cfg.output_dir, f"{key}.manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    log.info("Terminé : %d short(s) dans %s/ (manifeste : %s).",
             len(rendered), cfg.output_dir, os.path.basename(manifest_path))

    return manifest
