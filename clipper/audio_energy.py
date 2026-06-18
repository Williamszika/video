"""Analyse de l'énergie audio comme signal secondaire de « chaleur ».

Les moments forts d'une vidéo coïncident souvent avec des pics sonores : rires,
cris, applaudissements, musique qui monte, voix qui s'emballe. On calcule une
enveloppe RMS par fenêtre d'une seconde, puis on score n'importe quelle plage
temporelle. Lecture du WAV par blocs pour rester léger même sur 2 h+ d'audio.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from typing import List

import numpy as np

from .utils import get_logger

log = get_logger()


@dataclass
class AudioEnergy:
    hop: float                 # durée d'une fenêtre (secondes)
    envelope: np.ndarray       # RMS par fenêtre
    duration: float

    def window_score(self, start: float, end: float) -> float:
        """Score brut d'une plage : mélange de l'énergie moyenne et du pic."""
        if len(self.envelope) == 0 or end <= start:
            return 0.0
        i0 = max(0, int(start / self.hop))
        i1 = min(len(self.envelope), int(np.ceil(end / self.hop)))
        if i1 <= i0:
            return 0.0
        window = self.envelope[i0:i1]
        return float(0.6 * window.mean() + 0.4 * window.max())

    def normalized_window_score(self, start: float, end: float) -> float:
        """Score 0-100 d'une plage, normalisé par rapport à toute la vidéo."""
        raw = self.window_score(start, end)
        lo = float(self.envelope.min()) if len(self.envelope) else 0.0
        hi = float(np.percentile(self.envelope, 99)) if len(self.envelope) else 1.0
        if hi <= lo:
            return 0.0
        return float(np.clip((raw - lo) / (hi - lo), 0.0, 1.0) * 100.0)


def analyze(wav_path: str, hop: float = 1.0) -> AudioEnergy:
    """Calcule l'enveloppe d'énergie RMS d'un WAV mono 16 bits."""
    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        total_frames = wf.getnframes()
        duration = total_frames / float(sample_rate) if sample_rate else 0.0

        if sample_width != 2:
            log.warning("Largeur d'échantillon inattendue (%d octets) ; analyse audio approximative.",
                        sample_width)

        frames_per_hop = max(1, int(hop * sample_rate))
        envelope: List[float] = []

        while True:
            raw = wf.readframes(frames_per_hop)
            if not raw:
                break
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            if n_channels > 1:
                data = data.reshape(-1, n_channels).mean(axis=1)
            if data.size == 0:
                continue
            rms = float(np.sqrt(np.mean(np.square(data / 32768.0))))
            envelope.append(rms)

    arr = np.asarray(envelope, dtype=np.float32)
    log.info("Énergie audio analysée : %d fenêtres de %.0fs.", len(arr), hop)
    return AudioEnergy(hop=hop, envelope=arr, duration=duration)
