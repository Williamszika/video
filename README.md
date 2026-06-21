# 🎬 clipper — des vidéos longues aux shorts TikTok, automatiquement

`clipper` analyse une vidéo **longue (2 h et plus)**, repère ses **moments les
plus forts** (émouvants, drôles, choquants, captivants) grâce à l'IA, et en tire
plusieurs **shorts verticaux d'environ 2 minutes** prêts à être postés sur
**TikTok, Reels et Shorts** — avec recadrage 9:16 et **sous-titres animés**.

Pensé pour faire grossir une audience : le système va chercher tout seul les
extraits qui donnent envie d'arrêter de scroller.

---

## ✨ Ce que fait le système

```
Vidéo longue (2h+)
      │
      ▼
1. Extraction de l'audio ........................ ffmpeg
2. Transcription mot-à-mot ...................... Whisper (local, gratuit)
3. Analyse des moments forts .................... Claude (Opus 4.8)  ← le cerveau
   + énergie audio (rires, cris, emphase) ....... analyse du signal
4. Sélection des meilleurs clips ~2 min ......... sans chevauchement
5. Recadrage vertical 9:16 ...................... recadrage centré ou fond flou
6. Sous-titres animés mot-à-mot ................. style viral (mot surligné)
      │
      ▼
N shorts .mp4 prêts pour TikTok  +  un manifeste JSON
```

Approche **hybride** : la transcription tourne **en local** (gratuit, hors-ligne),
et seule l'analyse intelligente des moments passe par l'**API Claude**.

---

## 🧠 Pourquoi c'est « intelligent »

- **Analyse sémantique par Claude** : le modèle lit la transcription horodatée et
  note chaque moment sur une échelle de viralité (0–100), avec une émotion, une
  accroche et la phrase-clé. Il cherche précisément ce qui retient l'attention.
- **Double signal** : le score IA est combiné à l'**énergie audio** (les pics
  sonores trahissent souvent les moments chauds : rires, cris, applaudissements).
- **Bornes propres** : les clips sont recalés sur des **débuts/fins de phrase**
  (jamais de coupe en plein mot), grâce aux horodatages au niveau du mot.
- **Sous-titres animés** : chaque mot s'illumine au moment où il est prononcé —
  le style qui cartonne sur TikTok et booste la rétention.
- **Accroche en haut** du clip pendant les premières secondes.

---

## 📦 Prérequis

- **Python 3.9+**
- **ffmpeg** et **ffprobe** installés sur le système :
  - Ubuntu/Debian : `sudo apt install ffmpeg`
  - macOS : `brew install ffmpeg`
  - Windows : <https://ffmpeg.org/download.html>
- Une **clé API Claude** (<https://console.anthropic.com/>)
- *(Optionnel mais recommandé)* un **GPU NVIDIA** pour accélérer la transcription
  des longues vidéos.

---

## 🚀 Installation

```bash
git clone <ce-dépôt> && cd video
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Configure ta clé API
cp .env.example .env
# puis édite .env pour y mettre ANTHROPIC_API_KEY=sk-ant-...
```

---

## ▶️ Utilisation

```bash
# Le plus simple : 6 shorts d'~2 min depuis une conférence de 2 h
clipper conference.mp4

# 8 shorts de 90 s, fond flou, sous-titres animés
clipper podcast.mp4 -n 8 -d 90 --crop blur

# Anglais, modèle Whisper plus léger sur CPU, dossier de sortie dédié
clipper interview.mp4 -l en --whisper-model medium --whisper-device cpu -o shorts/

# Sans sous-titres, recadrage centré
clipper film.mp4 --subtitles none
```

### 🎞️ Mode montage (bande-annonce de ~5 min)

Au lieu de plusieurs shorts, produire **une seule vidéo** qui condense le film :
elle enchaîne les scènes les plus fortes (ordre chronologique) avec des
**transitions**, et affiche un **carton d'appel à l'action** sur la dernière
scène pour renvoyer vers ta page (Telegram, etc.).

```bash
# Bande-annonce verticale de 5 min, avec CTA personnalisé
clipper film.mp4 --montage \
  --cta "Abonne-toi sur Film HD sur Telegram pour voir le film complet. Lien dans ma Bio"

# Avec générique animé (nom du film) en ouverture
clipper film.mp4 --montage --title "Le Destin de Michael" \
  --cta "Abonne-toi sur Film HD sur Telegram. Lien dans ma Bio"

# Découper le film en 5 parties chronologiques de 5 min (Partie 1 → Partie 5)
clipper film.mp4 --parts 5 --crop blur --title "Le Destin de Michael" \
  --cta "Abonne-toi sur Film HD sur Telegram pour voir le film complet. Lien dans ma Bio"
```

- **Générique animé** : `--title "Nom du film"` ajoute un carton d'ouverture (nom
  en fondu + montée, fond flou). Réglable avec `--intro-duration`.
- **Plusieurs parties** : `--parts 5` découpe le film en 5 portions
  **chronologiques** qui se suivent logiquement (Partie 1 = début … Partie 5 = fin).
  Chaque partie a son générique « Partie N / 5 » et son carton CTA. Idéal pour
  poster un film en feuilleton et faire revenir l'audience.

Tous les textes (générique, CTA) sont rendus en image (Pillow) puis incrustés :
**pas besoin de libass**, ça marche même avec un ffmpeg minimal. Options :
`--montage-duration`, `--scene-duration`, `--transition`, `--transition-duration`,
`--cta`, `--no-cta`, `--title`, `--intro-duration`, `--parts`.

Sortie typique :

```
✅ 6 short(s) généré(s) dans « output/ » :
   #01  [2:00]  score  91.0  choquant    « Il avoue ce qu'il n'avait jamais dit »
        → output/conference_short01_il-avoue-ce-quil-navait.mp4
   #02  [1:58]  score  87.4  émouvant    « La lettre qui a tout changé »
        → output/conference_short02_la-lettre-qui-a-tout-change.mp4
   ...
```

Un fichier `…manifest.json` récapitule tous les clips (temps, score, accroche, émotion).

---

## ⚙️ Options principales

| Option | Effet | Défaut |
|---|---|---|
| `-n, --clips` | Nombre de shorts à produire | `6` |
| `-d, --duration` | Durée cible d'un short (s) | `120` |
| `--min-duration` / `--max-duration` | Bornes de durée (s) | `45` / `140` |
| `--crop {center,blur}` | Recadrage 9:16 centré, ou fond flou | `center` |
| `-l, --language` | Langue (`fr`, `en`, `auto`) | `fr` |
| `--whisper-model` | `tiny`…`large-v3` (précision ↔ vitesse) | `large-v3` |
| `--whisper-device` | `cpu`, `cuda`, `auto` | `auto` |
| `--model` | Modèle Claude pour l'analyse | `claude-opus-4-8` |
| `--effort {low..max}` | Profondeur de réflexion de l'analyse | `high` |
| `--subtitles {animated,simple,none}` | Style des sous-titres | `animated` |
| `--no-hook` | Masquer l'accroche en haut | (affichée) |
| `--words-per-caption` | Mots affichés à la fois | `4` |
| `--highlight-color` / `--primary-color` | Couleurs (hex RGB) | `FFE000` / `FFFFFF` |
| `-o, --output` | Dossier de sortie | `output` |
| `-v, --verbose` | Logs détaillés | — |

Voir `clipper --help` pour la liste complète.

---

## 💡 Conseils pour percer sur TikTok

- **Garde des clips courts et nerveux** : ~2 min est un bon plafond, mais
  n'hésite pas à descendre (`-d 60`) pour des extraits punchy.
- **Sous-titres animés activés** (par défaut) : énorme impact sur la rétention.
- **Soigne l'accroche** : le champ `hook` proposé par l'IA peut servir de
  légende/texte de couverture.
- **Teste plusieurs styles** : `--crop blur` rend bien quand le sujet n'est pas
  centré ; `center` est plus immersif.
- **Poste régulièrement** : génère un lot de shorts par vidéo et étale les
  publications.

---

## 💰 Coût

- **Transcription** : gratuite (Whisper en local).
- **Analyse Claude** : seule la transcription textuelle est envoyée (pas la
  vidéo). Le coût dépend de la longueur de la vidéo et du modèle. Pour réduire :
  `--model claude-sonnet-4-6` ou `--effort medium`.
- Les résultats intermédiaires (transcription, analyse) sont **mis en cache**
  dans `output/work/` : relancer le même fichier ne re-paie pas l'analyse.

---

## 🗂️ Structure du projet

```
clipper/
  config.py        Configuration centrale (durées, format, modèle…)
  media.py         ffmpeg : sonde, extraction audio, rendu vertical + sous-titres
  transcribe.py    Whisper local, horodatage au niveau du mot
  audio_energy.py  Enveloppe d'énergie RMS (pics d'intensité)
  analyze.py       Analyse des moments forts via Claude (sorties structurées)
  select.py        Scoring combiné, recalage sur les phrases, anti-chevauchement
  subtitles.py     Génération des sous-titres animés (.ass)
  pipeline.py      Orchestration de bout en bout
  cli.py           Interface en ligne de commande
tests/             Tests unitaires des modules « purs »
```

---

## ✅ Tests

```bash
pip install pytest
pytest
```

Les tests couvrent la logique pure (sélection, sous-titres, configuration,
utilitaires) sans nécessiter ffmpeg, Whisper ni l'API.

---

## ⚠️ Limites & notes

- La qualité de l'analyse dépend de la clarté de la **parole** : une vidéo sans
  dialogue (musique seule) n'a pas de « moments » textuels à exploiter.
- La transcription d'une vidéo de 2 h peut être longue sur CPU — préférez un GPU
  ou un modèle Whisper plus léger (`--whisper-model small`).
- Le recadrage `center` peut couper un sujet excentré ; utilisez `blur` dans ce
  cas. (Un recadrage à suivi de visage pourra être ajouté ultérieurement.)
- Pensez aux **droits** sur les vidéos que vous découpez et republiez.

---

## 📄 Licence

MIT.
