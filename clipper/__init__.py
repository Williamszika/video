"""clipper — découpe intelligente de vidéos longues en shorts verticaux.

Pipeline :
    extraction audio -> transcription (Whisper) -> analyse des moments forts
    (Claude + énergie audio) -> sélection des meilleurs clips -> sous-titres
    animés -> rendu vertical 9:16.
"""

from .config import Config

__version__ = "0.1.0"
__all__ = ["Config", "__version__"]
