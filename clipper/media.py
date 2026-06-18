"""Enveloppe autour de ffmpeg / ffprobe.

On ne dépend d'aucune bibliothèque Python lourde pour la vidéo : tout passe par
les binaires `ffmpeg` et `ffprobe` via subprocess. Ils doivent être installés
sur le système.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .config import Config
from .utils import get_logger

log = get_logger()


class FFmpegError(RuntimeError):
    """Erreur d'exécution de ffmpeg/ffprobe."""


@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool

    @property
    def is_vertical(self) -> bool:
        return self.height >= self.width


def ensure_tools() -> None:
    """Vérifie que ffmpeg et ffprobe sont disponibles, sinon lève une erreur claire."""
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing:
        raise FFmpegError(
            "Outils manquants : " + ", ".join(missing) + ".\n"
            "Installe ffmpeg : `apt install ffmpeg` (Debian/Ubuntu), "
            "`brew install ffmpeg` (macOS), ou https://ffmpeg.org/download.html"
        )


def _run(cmd: List[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    log.debug("exec: %s", " ".join(cmd))
    try:
        return subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - dépend du système
        tail = (exc.stderr or "")[-1500:]
        raise FFmpegError(f"Échec de la commande {cmd[0]} :\n{tail}") from exc


def probe(path: str) -> VideoInfo:
    """Retourne durée, résolution, fps et présence d'audio d'un fichier média."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    out = _run(cmd, capture=True).stdout
    data = json.loads(out)

    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    if video_stream is None:
        raise FFmpegError("Aucun flux vidéo trouvé dans le fichier.")

    duration = float(data.get("format", {}).get("duration")
                     or video_stream.get("duration") or 0.0)
    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    fps = _parse_fraction(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0/1")

    return VideoInfo(duration=duration, width=width, height=height, fps=fps, has_audio=has_audio)


def _parse_fraction(value: str) -> float:
    try:
        num, _, den = value.partition("/")
        den_f = float(den) if den else 1.0
        return float(num) / den_f if den_f else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def extract_audio(path: str, out_wav: str, sample_rate: int = 16000) -> str:
    """Extrait l'audio en WAV mono PCM 16 kHz (format attendu par Whisper)."""
    os.makedirs(os.path.dirname(out_wav) or ".", exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", path,
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-c:a", "pcm_s16le", out_wav,
    ]
    _run(cmd)
    return out_wav


# --------------------------------------------------------------------------- #
# Construction des filtres vidéo
# --------------------------------------------------------------------------- #

def _escape_filter_path(path: str) -> str:
    """Échappe un chemin pour l'utiliser dans un filtre ffmpeg (ass=/subtitles=)."""
    path = path.replace("\\", "\\\\")
    path = path.replace(":", "\\:")
    path = path.replace("'", "\\'")
    path = path.replace(",", "\\,")
    return path


def build_vertical_filter(cfg: Config, ass_path: Optional[str]) -> str:
    """Construit le filtre complet : recadrage vertical (+ sous-titres éventuels)."""
    w, h = cfg.width, cfg.height

    if cfg.crop_mode == "blur":
        # Vidéo entière au centre, fond flou pour remplir le 9:16.
        base = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},boxblur=24:2[bgb];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[v]"
        )
        last = "[v]"
    else:
        # Recadrage centré : on agrandit pour couvrir puis on rogne au centre.
        base = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}[v]"
        )
        last = "[v]"

    if ass_path:
        # On nomme explicitement l'option (filename=) et on passe un chemin
        # absolu : certaines versions de ffmpeg (8.1.x) rejettent la forme
        # positionnelle « ass=chemin » avec l'erreur « No option name ».
        esc = _escape_filter_path(os.path.abspath(ass_path))
        base += f";{last}ass=filename={esc}[vout]"
        last = "[vout]"

    return base, last


def render_clip(
    src: str,
    start: float,
    duration: float,
    out_path: str,
    cfg: Config,
    ass_path: Optional[str] = None,
) -> str:
    """Découpe [start, start+duration], recadre en 9:16 et incruste les sous-titres.

    Le découpage se fait par seek en entrée (`-ss` avant `-i`) ce qui remet
    l'horodatage de sortie à zéro : les temps du fichier ASS doivent donc être
    relatifs au début du clip.
    """
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    filtergraph, last = build_vertical_filter(cfg, ass_path)

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", src,
        "-t", f"{duration:.3f}",
        "-filter_complex", filtergraph,
        "-map", last,
    ]
    # Audio : on mappe la piste du fichier source si elle existe.
    cmd += ["-map", "0:a?"]
    if cfg.fps:
        cmd += ["-r", str(cfg.fps)]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        out_path,
    ]
    _run(cmd)
    return out_path
