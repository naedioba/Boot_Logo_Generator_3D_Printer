## Générateur de logo de démarrage v1.2.0 — première publication / first release

### 🇫🇷 Français

Première version publique du générateur de logo de démarrage pour imprimantes 3D. Il crée, avec votre propre texte, la séquence d'images de l'animation de démarrage de l'écran. Il convient à toute imprimante dont l'animation de démarrage est une suite d'images ; les réglages par défaut correspondent à l'Ender-3 V3 SE (39 images de 200 × 89 px, à réinsérer dans `tjc.tft`).

**Nouveautés**

- Texte sur une ou deux lignes, avec police, taille, espacement et couleur propres à chaque ligne
- 5 styles d'animation, dont la reproduction du style Creality d'origine (contour tracé puis remplissage)
- 4 types de fond, dont la réutilisation du fond Creality d'origine
- Analyse d'un dossier d'images existant (nombre, dimensions, numérotation)
- Aperçu animé en direct et simulation des couleurs RGB565 de l'écran
- Export PNG et GIF d'aperçu
- Interface moderne bilingue français / anglais
- Manuel PDF intégré (bouton **Manuel** ou touche **F1**)

**Installation** : téléchargez `Generateur_Logo_Demarrage.exe` ci-dessous et lancez-le. Si Windows SmartScreen s'affiche : **Informations complémentaires → Exécuter quand même** (exe non signé).

**Important** : gardez le même nombre d'images, les mêmes dimensions et les mêmes numéros que l'original, et sauvegardez le firmware d'écran d'origine (`tjc.tft` sur l'Ender-3 V3 SE) avant de flasher.

### 🇬🇧 English

First public release of the boot logo generator for 3D printers. It creates the screen's boot animation image sequence with your own text. It suits any printer whose boot animation is a series of images; the default settings match the Ender-3 V3 SE (39 images of 200 × 89 px, to be put back into `tjc.tft`).

**Highlights**

- Text on one or two lines, with font, size, spacing and color set per line
- 5 animation styles, including a reproduction of the original Creality style (outline drawn then filled)
- 4 background types, including reuse of the original Creality background
- Analysis of an existing image folder (count, size, numbering)
- Live animated preview and simulation of the screen's RGB565 colors
- PNG export and preview GIF
- Modern bilingual French / English interface
- Built-in PDF manual (**Manual** button or **F1** key)

**Installation**: download `Generateur_Logo_Demarrage.exe` below and run it. If Windows SmartScreen appears: **More info → Run anyway** (unsigned exe).

**Important**: keep the same image count, size and numbers as the original, and back up the original screen firmware (`tjc.tft` on the Ender-3 V3 SE) before flashing.

### Fichiers / Assets

| Fichier / File | Description |
| --- | --- |
| `Generateur_Logo_Demarrage.exe` | Application Windows (64 bits), aucune installation / Windows app (64-bit), no install |
| `Manuel_FR.pdf` | Manuel d'utilisation en français |
| `Manual_EN.pdf` | User manual in English |
| `Generateur_Logo_Demarrage_source.zip` | Code source Python / Python source code |

Licence / License: GNU GPL v3 — © 2026 Mamadou Bâ Neige
