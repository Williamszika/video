"""Configuration centrale du pipeline.

Toutes les options réglables sont regroupées ici. Les valeurs par défaut
visent le cas d'usage TikTok : clips verticaux 9:16 d'environ 2 minutes,
sous-titres animés en français, analyse via Claude.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Optional


# Modèle Claude par défaut : le plus intelligent (cf. besoin « système très intelligent »).
DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class Config:
    # --- Découpage ---
    target_duration: float = 120.0   # durée visée d'un short (secondes) -> ~2 min
    min_duration: float = 45.0       # on refuse les clips plus courts
    max_duration: float = 140.0      # limite haute (TikTok accepte jusqu'à 10 min, mais 2 min = format roi)
    num_clips: int = 6               # nombre de shorts à produire
    min_gap: float = 20.0            # écart minimal entre deux clips retenus (anti-chevauchement)

    # --- Format vertical (TikTok / Reels / Shorts) ---
    width: int = 1080
    height: int = 1920
    crop_mode: str = "center"        # "center" (recadrage centré) | "blur" (fond flou)
    fps: Optional[int] = None        # None = conserver le fps source

    # --- Transcription (Whisper local) ---
    language: str = "fr"             # "fr", "en", ou "auto"
    whisper_model: str = "large-v3"  # tiny|base|small|medium|large-v3
    whisper_device: str = "auto"     # auto|cpu|cuda
    whisper_compute_type: str = "auto"  # auto|int8|float16|float32

    # --- Analyse intelligente (Claude) ---
    model: str = DEFAULT_MODEL
    analysis_chunk_minutes: float = 30.0  # taille des tranches de transcription envoyées à Claude
    effort: str = "high"             # low|medium|high|max (profondeur de réflexion)
    candidates_per_chunk: int = 8    # moments candidats demandés par tranche

    # --- Sous-titres animés ---
    subtitles: bool = True
    subtitle_style: str = "animated"  # "animated" (mot surligné) | "simple" | "none"
    words_per_caption: int = 4        # nombre de mots affichés par carte de sous-titre
    font_name: str = "Arial"
    font_size: int = 92
    primary_color: str = "FFFFFF"     # couleur des mots (hex RGB)
    highlight_color: str = "FFE000"   # couleur du mot actif (hex RGB)
    outline_color: str = "000000"
    margin_vertical: int = 360        # distance depuis le bas (px)

    # --- Accroche (hook) en haut du clip ---
    show_hook: bool = True
    hook_duration: float = 3.0        # durée d'affichage de l'accroche (secondes)

    # --- Mode montage (une seule vidéo ~5 min, façon bande-annonce) ---
    mode: str = "shorts"              # "shorts" | "montage"
    montage_duration: float = 300.0   # durée cible du montage (secondes) -> ~5 min
    scene_duration: float = 30.0      # durée de chaque scène piochée
    montage_fps: int = 30
    transition: str = "fade"          # transition xfade (fade, dissolve, wipeleft, slideright, …)
    transition_duration: float = 0.7  # durée des transitions (secondes)
    cta_enabled: bool = True          # carton d'appel à l'action en fin de montage
    cta_text: str = ("Abonne-toi sur Film HD sur Telegram pour regarder "
                     "l'intégralité du film. Lien dans ma Bio")
    intro_title: str = ""             # nom du film -> générique animé en ouverture (vide = auto/pas de générique)
    auto_title: bool = True           # si intro_title vide : laisser l'IA détecter le titre du film
    intro_duration: float = 3.0       # durée du générique (secondes)
    parts: int = 1                    # découper le film en N parties (1 = un seul montage)
    hashtags: bool = True             # générer des hashtags TikTok par montage/partie
    hashtags_count: int = 5           # nombre de hashtags par montage/partie

    # --- Pondération du score de viralité ---
    weight_ai: float = 0.75           # poids du score Claude
    weight_audio: float = 0.25        # poids de l'énergie audio (rires, cris, emphase)

    # --- Chemins ---
    output_dir: str = "output"
    work_dir: str = field(default="")  # vide -> <output_dir>/work

    # --- Divers ---
    api_key: Optional[str] = None     # None -> variable d'environnement ANTHROPIC_API_KEY
    keep_audio: bool = False          # garder le wav extrait (debug)
    seed_label: str = ""              # préfixe optionnel pour les noms de fichiers

    def __post_init__(self) -> None:
        if not self.work_dir:
            self.work_dir = os.path.join(self.output_dir, "work")

    # ------------------------------------------------------------------ #

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        """Construit une config en lisant les variables d'environnement, puis
        en appliquant les surcharges explicites (CLI)."""
        env_map = {
            "model": os.environ.get("CLIPPER_MODEL"),
            "whisper_model": os.environ.get("CLIPPER_WHISPER_MODEL"),
            "whisper_device": os.environ.get("CLIPPER_WHISPER_DEVICE"),
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
        }
        env_map = {k: v for k, v in env_map.items() if v}
        env_map.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**env_map)

    def validate(self) -> None:
        """Vérifie la cohérence des valeurs et lève ValueError si besoin."""
        if self.min_duration > self.target_duration:
            raise ValueError("min_duration ne peut pas dépasser target_duration.")
        if self.target_duration > self.max_duration:
            raise ValueError("target_duration ne peut pas dépasser max_duration.")
        if self.num_clips < 1:
            raise ValueError("num_clips doit valoir au moins 1.")
        if self.crop_mode not in {"center", "blur"}:
            raise ValueError("crop_mode doit valoir 'center' ou 'blur'.")
        if self.mode not in {"shorts", "montage"}:
            raise ValueError("mode doit valoir 'shorts' ou 'montage'.")
        if self.mode == "montage":
            if self.scene_duration <= self.transition_duration * 2:
                raise ValueError("scene_duration doit être nettement supérieure à transition_duration.")
            if self.montage_duration < self.scene_duration:
                raise ValueError("montage_duration doit être au moins égale à scene_duration.")
        if not (1 <= self.parts <= 20):
            raise ValueError("parts doit être compris entre 1 et 20.")
        if self.subtitle_style not in {"animated", "simple", "none"}:
            raise ValueError("subtitle_style doit valoir 'animated', 'simple' ou 'none'.")
        if not (0.0 <= self.weight_ai <= 1.0 and 0.0 <= self.weight_audio <= 1.0):
            raise ValueError("Les poids doivent être compris entre 0 et 1.")

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("api_key", None)  # ne jamais sérialiser la clé
        return d
