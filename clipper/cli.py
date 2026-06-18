"""Interface en ligne de commande : `clipper`."""

from __future__ import annotations

import argparse
import os
import sys

from .config import DEFAULT_MODEL, Config
from .utils import get_logger

log = get_logger()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clipper",
        description="Découpe intelligemment une vidéo longue en shorts verticaux "
                    "(TikTok/Reels/Shorts) à partir de ses moments les plus forts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("video", help="Chemin de la vidéo source (peut faire 2 h et plus).")

    g_clip = p.add_argument_group("Découpage")
    g_clip.add_argument("-n", "--clips", type=int, dest="num_clips", default=6,
                        help="Nombre de shorts à produire.")
    g_clip.add_argument("-d", "--duration", type=float, dest="target_duration", default=120.0,
                        help="Durée cible d'un short (secondes).")
    g_clip.add_argument("--min-duration", type=float, default=45.0,
                        help="Durée minimale d'un short (secondes).")
    g_clip.add_argument("--max-duration", type=float, default=140.0,
                        help="Durée maximale d'un short (secondes).")

    g_fmt = p.add_argument_group("Format vertical")
    g_fmt.add_argument("--crop", dest="crop_mode", choices=["center", "blur"], default="center",
                       help="Recadrage 9:16 : centré ou fond flou.")
    g_fmt.add_argument("--width", type=int, default=1080)
    g_fmt.add_argument("--height", type=int, default=1920)

    g_tr = p.add_argument_group("Transcription (Whisper local)")
    g_tr.add_argument("-l", "--language", default="fr", help="Langue (fr, en, auto).")
    g_tr.add_argument("--whisper-model", default=None,
                      help="Modèle Whisper (tiny|base|small|medium|large-v3).")
    g_tr.add_argument("--whisper-device", default=None, help="cpu, cuda ou auto.")

    g_ai = p.add_argument_group("Analyse (Claude)")
    g_ai.add_argument("--model", default=None,
                      help=f"Modèle Claude pour l'analyse (défaut {DEFAULT_MODEL}).")
    g_ai.add_argument("--effort", choices=["low", "medium", "high", "max"], default="high",
                      help="Profondeur de réflexion de l'analyse.")

    g_sub = p.add_argument_group("Sous-titres")
    g_sub.add_argument("--subtitles", dest="subtitle_style",
                       choices=["animated", "simple", "none"], default="animated",
                       help="Style des sous-titres incrustés.")
    g_sub.add_argument("--no-hook", dest="show_hook", action="store_false",
                       help="Ne pas afficher l'accroche en haut du clip.")
    g_sub.add_argument("--words-per-caption", type=int, default=4,
                       help="Nombre de mots affichés à la fois.")
    g_sub.add_argument("--font", dest="font_name", default="Arial")
    g_sub.add_argument("--font-size", type=int, default=92)
    g_sub.add_argument("--highlight-color", default="FFE000",
                       help="Couleur du mot surligné (hex RGB).")
    g_sub.add_argument("--primary-color", default="FFFFFF",
                       help="Couleur des mots (hex RGB).")

    g_out = p.add_argument_group("Sortie")
    g_out.add_argument("-o", "--output", dest="output_dir", default="output",
                       help="Dossier de sortie.")
    g_out.add_argument("--keep-audio", action="store_true",
                       help="Conserver le WAV extrait (debug).")
    g_out.add_argument("-v", "--verbose", action="store_true", help="Logs détaillés.")
    return p


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def _config_from_args(args: argparse.Namespace) -> Config:
    return Config.from_env(
        num_clips=args.num_clips,
        target_duration=args.target_duration,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        crop_mode=args.crop_mode,
        width=args.width,
        height=args.height,
        language=args.language,
        whisper_model=args.whisper_model,
        whisper_device=args.whisper_device,
        model=args.model,
        effort=args.effort,
        subtitle_style=args.subtitle_style,
        subtitles=args.subtitle_style != "none",
        show_hook=args.show_hook,
        words_per_caption=args.words_per_caption,
        font_name=args.font_name,
        font_size=args.font_size,
        highlight_color=args.highlight_color,
        primary_color=args.primary_color,
        output_dir=args.output_dir,
        keep_audio=args.keep_audio,
    )


def main(argv=None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)

    if args.verbose:
        import logging
        get_logger().setLevel(logging.DEBUG)

    if not os.path.isfile(args.video):
        log.error("Fichier introuvable : %s", args.video)
        return 2

    cfg = _config_from_args(args)

    # Vérification précoce de la clé API (l'analyse en a besoin), pour éviter
    # de transcrire une longue vidéo avant de découvrir qu'il manque la clé.
    if not (cfg.api_key or os.environ.get("ANTHROPIC_API_KEY")):
        log.error("Clé API Claude absente. Renseigne ANTHROPIC_API_KEY "
                  "(variable d'environnement ou fichier .env). Voir .env.example.")
        return 3

    try:
        cfg.validate()
    except ValueError as exc:
        log.error("Configuration invalide : %s", exc)
        return 2

    from . import pipeline  # import différé (dépendances lourdes)

    try:
        manifest = pipeline.run(args.video, cfg)
    except KeyboardInterrupt:
        log.warning("Interrompu par l'utilisateur.")
        return 130
    except Exception as exc:  # noqa: BLE001 - on présente une erreur propre à l'utilisateur
        log.error("Échec : %s", exc)
        if args.verbose:
            raise
        return 1

    print()
    print(f"✅ {manifest['num_clips']} short(s) généré(s) dans « {cfg.output_dir}/ » :")
    for clip in manifest["clips"]:
        mm = int(clip["duration"] // 60)
        ss = int(clip["duration"] % 60)
        print(f"   #{clip['index']:02d}  [{mm:d}:{ss:02d}]  score {clip['final_score']:>5}  "
              f"{clip['emotion']:<10}  « {clip['hook']} »")
        print(f"        → {clip['output_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
