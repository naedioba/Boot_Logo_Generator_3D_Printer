#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur de logo de démarrage pour imprimantes 3D
Boot Logo Generator for 3D printers

Génère la séquence d'images qui forment l'animation de démarrage de l'écran
d'une imprimante 3D. Réglages par défaut : Ender-3 V3 SE (39 images 200x89
nommées 2386_200x89.png …, à remplacer dans le fichier tjc.tft, par ex. avec
TJC TFT Tool). Toute autre imprimante dont l'animation de démarrage est une
suite d'images peut être prise en charge en adaptant nombre, taille et numéros.

Copyright (C) 2026 Mamadou Bâ Neige — neigeba.com — github.com/naedioba

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details: <https://www.gnu.org/licenses/>.

Dépendances / Requirements :  pip install pillow numpy
"""

import math
import os
import re
import sys
import glob
import random
import threading

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

APP_VERSION = "1.2.0"
SS = 4  # facteur de suréchantillonnage (anticrénelage)

# ════════════════════════════════════════════════════════════════════════
#  MOTEUR DE RENDU (indépendant de l'interface)
# ════════════════════════════════════════════════════════════════════════

DEFAULTS = {
    "width": 200, "height": 89,
    "text": "CREALITY",
    "font_path": "",
    "font_size": 0,          # 0 = taille automatique
    "fit_ratio": 0.88,       # largeur max du texte (taille auto)
    "letter_spacing": 0,     # px (image finale)
    "y_offset": 0,           # px (décale le bloc de texte entier)
    "line2_on": False,       # 2e ligne de texte
    "text2": "ENDER-3 V3 SE",
    "font_path2": "",        # "" = même police que la 1re ligne
    "font_size2": 0,         # 0 = auto (45 % de la 1re ligne)
    "letter_spacing2": 1,
    "line_gap": 4,           # px entre les deux lignes
    "text_color2": "#8FD3E8",
    "anim": "outline",       # outline | fade | typewriter | wipe | zoom
    "n_frames": 39,
    "hold_frames": 0,
    "text_color": "#F6F6FF",
    "outline_color": "#9AA6D0",
    "fill_start_color": "#5A658B",
    "bg_mode": "wave",       # wave | solid | gradient | image
    "bg_color1": "#001452",
    "bg_color2": "#18708C",
    "bg_image": "",
    "rgb565": True,
    "seed": 7,
    "start_id": 2386,
    "pattern": "{id}_{w}x{h}.png",
}


def hex2rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def phase(p, a, b):
    """Progression locale 0..1 de p dans l'intervalle [a, b]."""
    if b <= a:
        return 1.0 if p >= b else 0.0
    return min(1.0, max(0.0, (p - a) / (b - a)))


def lerp_color(c1, c2, t):
    return tuple(c1[i] + (c2[i] - c1[i]) * t for i in range(3))


# ─── Polices ────────────────────────────────────────────────────────────

def font_dirs():
    dirs = []
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(os.path.join(windir, "Fonts"))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    elif sys.platform == "darwin":
        dirs += ["/System/Library/Fonts", "/Library/Fonts",
                 os.path.expanduser("~/Library/Fonts")]
    else:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts",
                 os.path.expanduser("~/.fonts"),
                 os.path.expanduser("~/.local/share/fonts")]
    return [d for d in dirs if os.path.isdir(d)]


def list_fonts():
    """Retourne une liste triée de (nom affiché, chemin)."""
    found, seen = [], set()
    for d in font_dirs():
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".ttf", ".otf")):
                    path = os.path.join(root, f)
                    try:
                        fam, sty = ImageFont.truetype(path, 12).getname()
                        name = f"{fam} {sty}".strip()
                    except Exception:
                        continue
                    if name in seen:
                        continue
                    seen.add(name)
                    found.append((name, path))
    found.sort(key=lambda x: x[0].lower())
    return found


def default_font_path(fonts):
    prefs = ["Arial Black Regular", "Arial Bold", "Segoe UI Bold",
             "DejaVu Sans Bold", "Liberation Sans Bold", "Helvetica Bold"]
    names = {n: p for n, p in fonts}
    for p in prefs:
        if p in names:
            return names[p]
    return fonts[0][1] if fonts else ""


def load_font(path, size):
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


# ─── Fond ───────────────────────────────────────────────────────────────

def make_background(cfg):
    W, H = cfg["width"], cfg["height"]
    c1, c2 = hex2rgb(cfg["bg_color1"]), hex2rgb(cfg["bg_color2"])
    mode = cfg["bg_mode"]

    if mode == "image" and cfg["bg_image"] and os.path.isfile(cfg["bg_image"]):
        im = Image.open(cfg["bg_image"]).convert("RGB")
        # recadrage « couvrir »
        r = max(W / im.width, H / im.height)
        im = im.resize((max(W, round(im.width * r)), max(H, round(im.height * r))),
                       Image.LANCZOS)
        l, t = (im.width - W) // 2, (im.height - H) // 2
        return np.asarray(im.crop((l, t, l + W, t + H)), dtype=np.float32)

    if mode == "solid":
        return np.tile(np.array(c1, np.float32), (H, W, 1))

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    if mode == "gradient":
        t = (yy / max(1, H - 1))[..., None]
        return np.array(c1, np.float32) * (1 - t) + np.array(c2, np.float32) * t

    # mode « wave » : dégradé sombre + nappe de points ondulée (style Creality)
    t = ((xx / W) * 0.55 + (yy / H) * 0.45)[..., None]
    dark = np.array([c * 0.68 for c in c1], np.float32)
    base = np.array(c1, np.float32) * (1 - t) + dark * t

    S = SS
    dots = Image.new("L", (W * S, H * S), 0)
    dr = ImageDraw.Draw(dots)
    cols, rows = 46, 16
    for j in range(rows):
        v = j / (rows - 1)
        for i in range(cols):
            u = i / (cols - 1)
            x = (-0.08 + 1.16 * u + 0.10 * v * v) * W
            y = (0.42 + 0.58 * v) * H + math.sin(u * 2 * math.pi * 1.15 + v * 2.6) * H * 0.07 * (1 - 0.4 * v)
            x += math.sin(v * 3.0 + u * 5.0) * W * 0.012
            bright = (v ** 1.4) * (0.35 + 0.65 * u) * 1.25 + 0.08
            rad = (0.45 + 0.35 * v) * S
            g = int(255 * min(1.0, bright))
            dr.ellipse((x * S - rad, y * S - rad, x * S + rad, y * S + rad), fill=g)
    dots = np.asarray(dots.resize((W, H), Image.BOX), np.float32)[..., None] / 255.0
    return base * (1 - dots) + np.array(c2, np.float32) * dots


# ─── Texte : mise en page et masques par lettre ─────────────────────────

class TextLayout:
    """Mise en page du texte (1 ou 2 lignes) et masques haute résolution par lettre."""

    def __init__(self, cfg):
        W, H, S = cfg["width"], cfg["height"], SS
        self.W, self.H = W, H
        text1 = cfg["text"] or " "
        path1 = cfg["font_path"]
        sp1 = cfg["letter_spacing"] * S
        two = bool(cfg.get("line2_on")) and bool(str(cfg.get("text2", "")).strip())
        text2 = cfg.get("text2", "") if two else ""
        path2 = cfg.get("font_path2") or path1
        sp2 = cfg.get("letter_spacing2", 0) * S
        gap = cfg.get("line_gap", 4) * S if two else 0

        def measure(text, path, size, sp):
            f = load_font(path, size)
            xs = [f.getlength(text[:i]) + i * sp for i in range(len(text))]
            x0, y0, x1, y1 = 1e9, 1e9, -1e9, -1e9
            for ch, x in zip(text, xs):
                if ch.isspace():
                    continue
                b = f.getbbox(ch)
                x0, y0 = min(x0, x + b[0]), min(y0, b[1])
                x1, y1 = max(x1, x + b[2]), max(y1, b[3])
            if x1 < x0:
                x0, y0, x1, y1 = 0, 0, 1, 1
            return f, xs, (x0, y0, x1, y1)

        def size2_for(s1):
            if cfg.get("font_size2", 0) and cfg["font_size2"] > 0:
                return int(cfg["font_size2"] * S)
            return max(4 * S, int(s1 * 0.45))   # auto : 45 % de la 1re ligne

        def block(s1):
            m1 = measure(text1, path1, s1, sp1)
            m2 = measure(text2, path2, size2_for(s1), sp2) if two else None
            w = m1[2][2] - m1[2][0]
            h = m1[2][3] - m1[2][1]
            if m2:
                w = max(w, m2[2][2] - m2[2][0])
                h += gap + (m2[2][3] - m2[2][1])
            return m1, m2, w, h

        if cfg["font_size"] and cfg["font_size"] > 0:
            size1 = int(cfg["font_size"] * S)
            m1, m2, bw, bh = block(size1)
        else:  # taille automatique (recherche dichotomique)
            max_h = (0.80 if two else 0.62) * H * S
            lo, hi = 4 * S, H * S * 2
            best = None
            while lo <= hi:
                mid = (lo + hi) // 2
                r = block(mid)
                if r[2] <= cfg["fit_ratio"] * W * S and r[3] <= max_h:
                    best = (mid,) + r
                    lo = mid + 1
                else:
                    hi = mid - 1
            if best is None:
                best = (4 * S,) + block(4 * S)
            size1, m1, m2, bw, bh = best
        self.font_px = size1 / S
        self.font_px2 = size2_for(size1) / S if two else 0

        top = (H * S - bh) / 2 + cfg["y_offset"] * S
        self.letters, self.letter_line = [], []
        placements = []
        f1, xs1, bb1 = m1
        placements.append((0, text1, f1, xs1, (W * S - (bb1[2] - bb1[0])) / 2 - bb1[0], top - bb1[1]))
        if m2:
            f2, xs2, bb2 = m2
            top2 = top + (bb1[3] - bb1[1]) + gap
            placements.append((1, text2, f2, xs2, (W * S - (bb2[2] - bb2[0])) / 2 - bb2[0], top2 - bb2[1]))

        line_imgs = [Image.new("L", (W * S, H * S), 0) for _ in placements]
        for li, text, f, xs, ox, oy in placements:
            for ch, x in zip(text, xs):
                if ch.isspace():
                    continue
                m = Image.new("L", (W * S, H * S), 0)
                ImageDraw.Draw(m).text((ox + x, oy), ch, font=f, fill=255)
                self.letters.append(m)
                self.letter_line.append(li)
                line_imgs[li] = Image.fromarray(np.maximum(np.asarray(line_imgs[li]), np.asarray(m)))
        if not self.letters:
            self.letters.append(Image.new("L", (W * S, H * S), 0))
            self.letter_line.append(0)

        self.line_imgs = line_imgs                      # une image par ligne
        self.line_masks = [np.asarray(im, np.float32) / 255.0 for im in line_imgs]
        self.full = np.maximum.reduce(self.line_masks) if len(self.line_masks) > 1 else self.line_masks[0]
        self.full_img = Image.fromarray((self.full * 255).astype(np.uint8))
        self._outline_cache = None

    def outline_data(self, seed):
        """Contours fins/épais + carte angulaire (pour le tracé progressif)."""
        if self._outline_cache is not None:
            return self._outline_cache
        rng = random.Random(seed)
        S = SS
        Hh, Wh = self.H * S, self.W * S
        thin = np.zeros((Hh, Wh), np.float32)
        thick = np.zeros((Hh, Wh), np.float32)
        per_letter = []
        yy, xx = np.mgrid[0:Hh, 0:Wh].astype(np.float32)
        for m in self.letters:
            o1 = (np.asarray(m.filter(ImageFilter.MaxFilter(5)), np.float32)
                  - np.asarray(m.filter(ImageFilter.MinFilter(3)), np.float32)) / 255.0
            o2 = (np.asarray(m.filter(ImageFilter.MaxFilter(7)), np.float32)
                  - np.asarray(m.filter(ImageFilter.MinFilter(7)), np.float32)) / 255.0
            o1, o2 = np.clip(o1, 0, 1), np.clip(o2, 0, 1)
            a = np.asarray(m, np.float32)
            tot = a.sum()
            if tot > 0:
                cx, cy = (xx * a).sum() / tot, (yy * a).sum() / tot
            else:
                cx, cy = Wh / 2, Hh / 2
            theta = (np.arctan2(yy - cy, xx - cx) / (2 * math.pi)) % 1.0
            if rng.random() < 0.5:
                theta = 1.0 - theta
            heads = rng.choice([2, 2, 3])
            off = rng.random()
            key = (theta * heads + off) % 1.0   # plusieurs « têtes » de tracé
            per_letter.append((o1, key))
            thin = np.maximum(thin, o1)
            thick = np.maximum(thick, o2)
        self._outline_cache = (thin, thick, per_letter)
        return self._outline_cache


def down(mask_hi, W, H):
    """Réduit un masque haute résolution (0..1) à la taille finale."""
    im = Image.fromarray(np.clip(mask_hi * 255, 0, 255).astype(np.uint8))
    return np.asarray(im.resize((W, H), Image.BOX), np.float32)[..., None] / 255.0


def composite(bg, layers, W, H):
    out = bg.copy()
    for mask_hi, color, alpha in layers:
        if alpha <= 0:
            continue
        m = down(mask_hi, W, H) * alpha
        out = out * (1 - m) + np.array(color, np.float32) * m
    return out


def to_image(arr, rgb565):
    a = np.clip(np.rint(arr), 0, 255).astype(np.uint8)
    if rgb565:  # simule l'affichage 16 bits de l'écran TJC
        r, g, b = a[..., 0] >> 3, a[..., 1] >> 2, a[..., 2] >> 3
        a = np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1).astype(np.uint8)
    return Image.fromarray(a, "RGB")


def render_frames(cfg, layout=None, bg=None, progress_cb=None, cancel=None):
    W, H = cfg["width"], cfg["height"]
    if layout is None:
        layout = TextLayout(cfg)
    if bg is None:
        bg = make_background(cfg)
    n = max(2, int(cfg["n_frames"]))
    hold = min(max(0, int(cfg["hold_frames"])), n - 2)
    na = n - hold
    tc, oc, fc = hex2rgb(cfg["text_color"]), hex2rgb(cfg["outline_color"]), hex2rgb(cfg["fill_start_color"])
    tc2 = hex2rgb(cfg.get("text_color2", cfg["text_color"]))
    line_cols = [tc, tc2]
    lines = list(zip(layout.line_masks, line_cols))   # (masque, couleur finale) par ligne
    anim = cfg["anim"]
    frames = []

    for k in range(n):
        if cancel is not None and cancel():
            return None
        p = min(1.0, k / (na - 1))
        layers = []

        if anim == "outline":
            thin, thick, per_letter = layout.outline_data(cfg["seed"])
            a = phase(p, 0.0, 0.45)
            b = smooth(phase(p, 0.45, 0.66))
            c = smooth(phase(p, 0.66, 1.0))
            if p < 0.45:
                rev = np.zeros_like(thin)
                ea = smooth(a)
                for o1, key in per_letter:
                    rev = np.maximum(rev, o1 * (key < ea))
                layers.append((rev, lerp_color(fc, oc, 0.4 + 0.6 * a), 0.55 + 0.45 * a))
            else:
                ol = thin * (1 - b) + thick * b
                col = lerp_color(oc, lerp_color(oc, tc, 0.35), b)
                layers.append((ol, col, 1.0 - c))
                if c > 0:
                    for m, col_l in lines:
                        layers.append((m, lerp_color(fc, col_l, c), c))

        elif anim == "fade":
            for m, col_l in lines:
                layers.append((m, col_l, smooth(p)))

        elif anim == "typewriter":
            nl = len(layout.letters)
            for i, m in enumerate(layout.letters):
                t = smooth(phase(p * nl, i, i + 1.0))
                if t > 0:
                    layers.append((np.asarray(m, np.float32) / 255.0, line_cols[layout.letter_line[i]], t))

        elif anim == "wipe":
            Wh = W * SS
            soft = Wh * 0.12
            edge = -soft + p * (Wh + 2 * soft)
            ramp = np.clip((edge - np.arange(Wh, dtype=np.float32)) / soft, 0, 1)[None, :]
            for m, col_l in lines:
                layers.append((m * ramp, col_l, 1.0))
            glow = np.clip(1 - np.abs(np.arange(Wh, dtype=np.float32) - edge) / (soft * 0.5), 0, 1)[None, :]
            if 0 < p < 1:
                layers.append((layout.full * glow, (255, 255, 255), 0.6))

        elif anim == "zoom":
            e = smooth(p)
            sc = 0.55 + 0.45 * e
            for img, col_l in zip(layout.line_imgs, line_cols):
                Wh, Hh = img.size
                zw, zh = max(1, int(Wh * sc)), max(1, int(Hh * sc))
                z = img.resize((zw, zh), Image.LANCZOS)
                canvas = Image.new("L", (Wh, Hh), 0)
                canvas.paste(z, ((Wh - zw) // 2, (Hh - zh) // 2))
                layers.append((np.asarray(canvas, np.float32) / 255.0, lerp_color(fc, col_l, e), e))

        frames.append(to_image(composite(bg, layers, W, H), cfg["rgb565"]))
        if progress_cb:
            progress_cb(k + 1, n)
    return frames


def export_frames(frames, cfg, folder):
    os.makedirs(folder, exist_ok=True)
    W, H = cfg["width"], cfg["height"]
    paths = []
    for i, im in enumerate(frames):
        name = cfg["pattern"].format(id=cfg["start_id"] + i, i=i, n=i + 1, w=W, h=H)
        p = os.path.join(folder, name)
        im.save(p, "PNG")
        paths.append(p)
    return paths


def export_gif(frames, path, ms=40, scale=2):
    big = [f.resize((f.width * scale, f.height * scale), Image.NEAREST) for f in frames]
    big[0].save(path, save_all=True, append_images=big[1:], duration=ms, loop=0)


NAME_RE = re.compile(r"^(\d+)_(\d+)x(\d+)\.png$", re.I)


def analyze_folder(folder):
    """Analyse un jeu d'images existant (ex. extrait d'un tjc.tft)."""
    items = []
    for f in os.listdir(folder):
        m = NAME_RE.match(f)
        if m:
            items.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), f))
    if not items:
        return None
    items.sort()
    ids = [i[0] for i in items]
    sizes = {(i[1], i[2]) for i in items}
    contiguous = ids == list(range(ids[0], ids[0] + len(ids)))
    return {
        "count": len(items), "start_id": ids[0], "end_id": ids[-1],
        "sizes": sizes, "contiguous": contiguous,
        "first_file": os.path.join(folder, items[0][3]),
    }


# ════════════════════════════════════════════════════════════════════════
#  INTERFACE GRAPHIQUE (Tkinter) — bilingue FR / EN
# ════════════════════════════════════════════════════════════════════════

TR = {
    "fr": {
        "title": "Générateur de logo de démarrage",
        "manual": "Manuel", "no_manual": "Manuel introuvable :\n{p}",
        "app_name": "Générateur de logo de démarrage", "subtitle": "",
        "preview": "Aperçu", "colors": "Couleurs", "timing": "Images",
        "b_export": "Générer les images", "b_analyze": "Analyser un dossier", "b_gif": "GIF d'aperçu",
        "export_hint": "Astuce : « Analyser un dossier » reprend automatiquement le nombre d'images, "
                       "la taille et le numéro de départ d'un jeu d'images extrait du firmware "
                       "de l'écran (par ex. tjc.tft pour l'Ender-3 V3 SE).",
        "tab_l2": "2e ligne", "l2_on": "Ajouter une 2e ligne sous le texte",
        "same_font": "(même police que la ligne 1)", "gap": "Écart entre les lignes (px) :",
        "size2": "Taille (px, 0 = auto 45 %) :", "c_text2": "Couleur finale de la 2e ligne",
        "ready2": "Prêt. Police : {px:.1f} px / 2e ligne : {px2:.1f} px",
        "tab_text": "Texte", "tab_anim": "Animation", "tab_bg": "Fond", "tab_export": "Export",
        "text": "Texte :", "font": "Police :", "browse": "Parcourir…",
        "size": "Taille (px, 0 = auto) :", "fit": "Largeur max. (auto) % :",
        "spacing": "Espacement des lettres (px) :", "yoff": "Décalage vertical (px) :",
        "c_text": "Couleur finale du texte", "c_outline": "Couleur du contour",
        "c_start": "Couleur de départ du remplissage",
        "anim": "Style d'animation :", "frames": "Nombre d'images :",
        "hold": "Images fixes à la fin :", "seed": "Variante du tracé (graine) :",
        "anims": {"outline": "Contour tracé puis remplissage (style Creality)",
                  "fade": "Fondu", "typewriter": "Lettre par lettre",
                  "wipe": "Balayage lumineux", "zoom": "Zoom avant"},
        "bgmode": "Type de fond :",
        "bgmodes": {"wave": "Nappe de points ondulée (style Creality)", "solid": "Couleur unie",
                    "gradient": "Dégradé vertical", "image": "Image"},
        "c_bg1": "Couleur 1 (fond)", "c_bg2": "Couleur 2 (points / bas)",
        "bgimg": "Image de fond :",
        "size_img": "Dimensions (L × H) :", "start_id": "N° de la 1re image :",
        "pattern": "Modèle de nom :", "rgb565": "Simuler les couleurs 16 bits (RGB565) de l'écran",
        "analyze": "Analyser un dossier d'images existant…",
        "export": "Générer les images…", "gif": "Exporter un GIF d'aperçu…",
        "play": "▶  Lecture", "pause": "❚❚  Pause", "frame": "Image {k}/{n} — {name}",
        "rendering": "Calcul de l'aperçu… {k}/{n}", "ready": "Prêt. Police : {px:.1f} px",
        "lang": "Langue :", "about": "À propos",
        "done": "{n} images enregistrées dans :\n{folder}",
        "analyzed": "{count} images trouvées (n° {start} à {end}), taille {size}.\n"
                    "Les réglages ont été adaptés.{extra}\n\nUtiliser la 1re image ({first}) comme fond ?",
        "noncontig": "\n⚠ Les numéros ne se suivent pas.",
        "nofiles": "Aucune image au format 1234_200x89.png dans ce dossier.",
        "warn_overwrite": "Le dossier contient déjà des fichiers portant ces noms. Les remplacer ?",
        "about_txt": "Générateur de logo de démarrage v{v}\n\nCrée la séquence d'images de l'animation "
                     "de démarrage de l'écran d'une imprimante 3D. Réglages par défaut : "
                     "Ender-3 V3 SE (images à réinsérer dans tjc.tft, par ex. avec TJC TFT Tool).\n\nImportant : gardez le même nombre d'images, "
                     "les mêmes dimensions et les mêmes numéros que l'original.\n\n"
                     "© 2026 Mamadou Bâ Neige — neigeba.com\nLicence GNU GPL v3",
        "err": "Erreur",
    },
    "en": {
        "title": "Boot Logo Generator",
        "manual": "Manual", "no_manual": "Manual not found:\n{p}",
        "app_name": "Boot Logo Generator", "subtitle": "",
        "preview": "Preview", "colors": "Colors", "timing": "Frames",
        "b_export": "Generate images", "b_analyze": "Analyze a folder", "b_gif": "Preview GIF",
        "export_hint": "Tip: “Analyze a folder” automatically picks up the image count, size and "
                       "first number of an image set extracted from the screen firmware "
                       "(e.g. tjc.tft for the Ender-3 V3 SE).",
        "tab_l2": "Line 2", "l2_on": "Add a second line below the text",
        "same_font": "(same font as line 1)", "gap": "Gap between lines (px):",
        "size2": "Size (px, 0 = auto 45%):", "c_text2": "Final color of line 2",
        "ready2": "Ready. Font: {px:.1f} px / line 2: {px2:.1f} px",
        "tab_text": "Text", "tab_anim": "Animation", "tab_bg": "Background", "tab_export": "Export",
        "text": "Text:", "font": "Font:", "browse": "Browse…",
        "size": "Size (px, 0 = auto):", "fit": "Max width (auto) %:",
        "spacing": "Letter spacing (px):", "yoff": "Vertical offset (px):",
        "c_text": "Final text color", "c_outline": "Outline color",
        "c_start": "Fill start color",
        "anim": "Animation style:", "frames": "Number of frames:",
        "hold": "Still frames at the end:", "seed": "Stroke variant (seed):",
        "anims": {"outline": "Outline drawn then filled (Creality style)",
                  "fade": "Fade in", "typewriter": "Letter by letter",
                  "wipe": "Light sweep", "zoom": "Zoom in"},
        "bgmode": "Background type:",
        "bgmodes": {"wave": "Wavy dot field (Creality style)", "solid": "Solid color",
                    "gradient": "Vertical gradient", "image": "Image"},
        "c_bg1": "Color 1 (background)", "c_bg2": "Color 2 (dots / bottom)",
        "bgimg": "Background image:",
        "size_img": "Size (W × H):", "start_id": "First image number:",
        "pattern": "File name pattern:", "rgb565": "Simulate the screen's 16-bit colors (RGB565)",
        "analyze": "Analyze an existing image folder…",
        "export": "Generate images…", "gif": "Export preview GIF…",
        "play": "▶  Play", "pause": "❚❚  Pause", "frame": "Frame {k}/{n} — {name}",
        "rendering": "Rendering preview… {k}/{n}", "ready": "Ready. Font: {px:.1f} px",
        "lang": "Language:", "about": "About",
        "done": "{n} images saved to:\n{folder}",
        "analyzed": "{count} images found (#{start} to #{end}), size {size}.\n"
                    "Settings were updated.{extra}\n\nUse the first image ({first}) as background?",
        "noncontig": "\n⚠ Numbers are not consecutive.",
        "nofiles": "No images named like 1234_200x89.png in this folder.",
        "warn_overwrite": "The folder already contains files with these names. Replace them?",
        "about_txt": "Boot Logo Generator v{v}\n\nCreates the boot animation image sequence of a "
                     "3D printer's screen. Default settings: Ender-3 V3 SE (images to be put "
                     "back into tjc.tft, e.g. with TJC TFT Tool).\n\n"
                     "Important: keep the same number of images, the same size and the same "
                     "numbers as the original.\n\n© 2026 Mamadou Bâ Neige — neigeba.com\nGNU GPL v3 license",
        "err": "Error",
    },
}


def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, colorchooser, messagebox
    import tkinter.font as tkfont
    from PIL import ImageTk

    class App(tk.Tk):
        ZOOM = 3
        PAL = {   # palette : fond sombre + accents vifs
            "bg": "#0B1220", "head": "#070C17", "panel": "#131C2E", "card": "#1A2540",
            "field": "#222F4C", "border": "#2F4066", "text": "#E8EEF8", "muted": "#8FA1C2",
            "ink": "#0B1220", "cyan": "#22D3EE", "cyan_h": "#67E8F9", "orange": "#FB923C",
            "violet": "#A78BFA", "green": "#34D399", "pink": "#F472B6", "yellow": "#FACC15",
        }

        def __init__(self):
            super().__init__()
            self.lang = "fr"
            self.fonts = list_fonts()
            self.font_map = {n: p for n, p in self.fonts}
            d = dict(DEFAULTS)
            d["font_path"] = default_font_path(self.fonts)
            self.v = {}
            for k, val in d.items():
                if isinstance(val, bool):
                    self.v[k] = tk.BooleanVar(value=val)
                elif isinstance(val, int):
                    self.v[k] = tk.IntVar(value=val)
                elif isinstance(val, float):
                    self.v[k] = tk.DoubleVar(value=val)
                else:
                    self.v[k] = tk.StringVar(value=val)
            self.v["font_name"] = tk.StringVar(value=self._font_name(d["font_path"]))
            self.v["font_name2"] = tk.StringVar(value=TR["fr"]["same_font"])
            self.v["lang"] = tk.StringVar(value="Français")
            self.frames, self.idx, self.playing = [], 0, True
            self.gen = 0
            self._after_render = None
            try:   # icône de la fenêtre (fichier à côté du script ou intégré dans l'exe)
                base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
                ico = os.path.join(base, "icone.ico")
                if os.path.isfile(ico) and sys.platform.startswith("win"):
                    self.iconbitmap(ico)
            except Exception:
                pass
            self.minsize(1100, 640)
            self.geometry("1240x740")
            self.apply_theme()
            self.build_ui()
            for k, var in self.v.items():
                if k not in ("lang", "font_name", "font_name2"):
                    var.trace_add("write", lambda *a: self.schedule_render())
            self.v["font_name"].trace_add("write", self._on_font_name)
            self.v["font_name2"].trace_add("write", self._on_font_name2)
            self.bind_all("<F1>", self.open_manual)
            self.schedule_render(10)
            self.after(60, self.tick)

        # ── utilitaires ──
        def t(self, key):
            return TR[self.lang][key]

        def _font_name(self, path):
            for n, p in self.fonts:
                if p == path:
                    return n
            return os.path.basename(path) if path else ""

        def _on_font_name(self, *a):
            name = self.v["font_name"].get()
            if name in self.font_map:
                self.v["font_path"].set(self.font_map[name])

        def _on_font_name2(self, *a):
            name = self.v["font_name2"].get()
            if name in (TR["fr"]["same_font"], TR["en"]["same_font"]):
                self.v["font_path2"].set("")
            elif name in self.font_map:
                self.v["font_path2"].set(self.font_map[name])

        def cfg(self):
            c = {}
            for k in DEFAULTS:
                try:
                    c[k] = self.v[k].get()
                except (tk.TclError, ValueError):
                    c[k] = DEFAULTS[k]
            c["width"] = max(8, min(1024, int(c["width"])))
            c["height"] = max(8, min(1024, int(c["height"])))
            c["n_frames"] = max(2, min(500, int(c["n_frames"])))
            c["fit_ratio"] = max(0.1, min(1.0, float(c["fit_ratio"])))
            for col in ("text_color", "text_color2", "outline_color", "fill_start_color", "bg_color1", "bg_color2"):
                try:
                    hex2rgb(c[col])
                except Exception:
                    c[col] = DEFAULTS[col]
            return c

        # ── thème visuel ──
        def apply_theme(self):
            P = self.PAL
            st = ttk.Style(self)
            try:
                st.theme_use("clam")
            except tk.TclError:
                pass
            fams = set(tkfont.families(self))
            fam = next((f for f in ("Segoe UI", "Inter", "Helvetica Neue", "Ubuntu", "DejaVu Sans")
                        if f in fams), "TkDefaultFont")
            self.FAM = fam
            for nm in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
                try:
                    tkfont.nametofont(nm).configure(family=fam, size=10)
                except tk.TclError:
                    pass
            self.configure(bg=P["bg"])
            self.option_add("*TCombobox*Listbox.background", P["field"])
            self.option_add("*TCombobox*Listbox.foreground", P["text"])
            self.option_add("*TCombobox*Listbox.selectBackground", P["cyan"])
            self.option_add("*TCombobox*Listbox.selectForeground", P["ink"])
            self.option_add("*TCombobox*Listbox.font", (fam, 10))

            st.configure(".", background=P["panel"], foreground=P["text"], font=(fam, 10),
                         bordercolor=P["border"], lightcolor=P["panel"], darkcolor=P["panel"],
                         troughcolor=P["field"], focuscolor=P["cyan"])
            st.configure("TFrame", background=P["panel"])
            st.configure("Bg.TFrame", background=P["bg"])
            st.configure("TLabel", background=P["panel"], foreground=P["text"])
            st.configure("Muted.TLabel", background=P["panel"], foreground=P["muted"], font=(fam, 9))
            st.configure("Card.TLabel", background=P["card"], foreground=P["text"])
            st.configure("CardMuted.TLabel", background=P["card"], foreground=P["muted"], font=(fam, 9, "bold"))
            st.configure("TSeparator", background=P["border"])

            # champs de saisie
            for w in ("TEntry", "TSpinbox", "TCombobox"):
                st.configure(w, fieldbackground=P["field"], foreground=P["text"], background=P["field"],
                             insertcolor=P["text"], bordercolor=P["border"], lightcolor=P["field"],
                             darkcolor=P["field"], arrowcolor=P["cyan"], padding=5,
                             selectbackground=P["cyan"], selectforeground=P["ink"])
                st.map(w, bordercolor=[("focus", P["cyan"])], lightcolor=[("focus", P["cyan"])],
                       fieldbackground=[("readonly", P["field"])],
                       background=[("active", P["border"]), ("readonly", P["field"])],
                       foreground=[("readonly", P["text"])])

            # onglets
            st.configure("TNotebook", background=P["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
            st.configure("TNotebook.Tab", background=P["card"], foreground=P["muted"],
                         padding=(14, 9), font=(fam, 10, "bold"), borderwidth=0,
                         lightcolor=P["card"], bordercolor=P["bg"])
            st.map("TNotebook.Tab",
                   background=[("selected", P["cyan"]), ("active", P["border"])],
                   foreground=[("selected", P["ink"]), ("active", P["text"])],
                   lightcolor=[("selected", P["cyan"])])

            # cases et curseurs
            for w in ("TCheckbutton", "TRadiobutton"):
                st.configure(w, background=P["panel"], foreground=P["text"], indicatorbackground=P["field"],
                             indicatorforeground=P["ink"], indicatormargin=(0, 0, 8, 0), padding=4)
                st.map(w, indicatorbackground=[("selected", P["green"]), ("active", P["border"])],
                       background=[("active", P["panel"])])
            st.configure("Horizontal.TScale", background=P["cyan"], troughcolor=P["field"],
                         bordercolor=P["border"], lightcolor=P["cyan"], darkcolor=P["cyan"])
            st.map("Horizontal.TScale", background=[("active", P["cyan_h"])])

            # choix « pilule » (styles d'animation, types de fond)
            st.configure("Pill.Toolbutton", background=P["card"], foreground=P["text"], anchor="w",
                         padding=(12, 8), font=(fam, 10), borderwidth=0, relief="flat",
                         lightcolor=P["card"], darkcolor=P["card"], bordercolor=P["card"])
            st.map("Pill.Toolbutton",
                   background=[("selected", P["violet"]), ("active", P["border"])],
                   foreground=[("selected", P["ink"])],
                   font=[("selected", (fam, 10, "bold"))])

            # boutons colorés
            def btn(name, bg, hover, press, fg=P["ink"], size=10, pad=(16, 9)):
                st.configure(name, background=bg, foreground=fg, font=(fam, size, "bold"),
                             padding=pad, borderwidth=0, relief="flat", focusthickness=0,
                             lightcolor=bg, darkcolor=bg, bordercolor=bg, anchor="center")
                st.map(name, background=[("pressed", press), ("active", hover)],
                       lightcolor=[("pressed", press), ("active", hover)],
                       darkcolor=[("pressed", press), ("active", hover)],
                       bordercolor=[("pressed", press), ("active", hover)])
            btn("Orange.TButton", P["orange"], "#FDBA74", "#EA580C", size=12, pad=(20, 13))
            btn("Green.TButton", P["green"], "#6EE7B7", "#059669", size=11, pad=(18, 11))
            btn("Violet.TButton", P["violet"], "#C4B5FD", "#7C3AED", size=11, pad=(18, 11))
            btn("Pink.TButton", P["pink"], "#F9A8D4", "#DB2777", size=10, pad=(14, 8))
            btn("Yellow.TButton", P["yellow"], "#FDE047", "#CA8A04", size=10, pad=(14, 6))
            btn("Ghost.TButton", P["field"], P["border"], P["card"], fg=P["text"], size=10, pad=(12, 6))

        def section(self, parent, row, text, color, cols=3):
            """Titre de section avec pastille colorée."""
            box = tk.Frame(parent, bg=self.PAL["panel"])
            box.grid(row=row, column=0, columnspan=cols, sticky="we", pady=(12 if row else 0, 6))
            tk.Frame(box, bg=color, width=4, height=18).pack(side="left", padx=(0, 8))
            tk.Label(box, text=text.rstrip(" :").upper(), bg=self.PAL["panel"], fg=color,
                     font=(self.FAM, 9, "bold")).pack(side="left")

        def new_tab(self, nb, title):
            f = ttk.Frame(nb, padding=(16, 14))
            nb.add(f, text=title)
            return f

        # ── construction de l'interface ──
        def build_ui(self):
            for w in self.winfo_children():
                w.destroy()
            P = self.PAL
            self.title(self.t("title"))

            # En-tête
            head = tk.Frame(self, bg=P["head"])
            head.pack(fill="x")
            inner = tk.Frame(head, bg=P["head"])
            inner.pack(fill="x", padx=18, pady=12)
            tk.Label(inner, text="◆", bg=P["head"], fg=P["cyan"], font=(self.FAM, 22, "bold")).pack(side="left")
            tbox = tk.Frame(inner, bg=P["head"])
            tbox.pack(side="left", padx=10, pady=4)
            tk.Label(tbox, text=self.t("app_name"), bg=P["head"], fg=P["text"],
                     font=(self.FAM, 16, "bold")).pack(anchor="w")
            ttk.Button(inner, text="ⓘ  " + self.t("about"), style="Ghost.TButton",
                       command=self.about).pack(side="right")
            ttk.Button(inner, text="?  " + self.t("manual"), style="Yellow.TButton",
                       command=self.open_manual).pack(side="right", padx=(0, 8))
            cb = ttk.Combobox(inner, textvariable=self.v["lang"], values=["Français", "English"],
                              state="readonly", width=10)
            cb.pack(side="right", padx=10)
            cb.bind("<<ComboboxSelected>>", self._change_lang)
            tk.Label(inner, text=self.t("lang"), bg=P["head"], fg=P["muted"]).pack(side="right")
            strip = tk.Frame(head, height=4, bg=P["head"])
            strip.pack(fill="x")
            for c in (P["cyan"], P["violet"], P["pink"], P["orange"], P["yellow"], P["green"]):
                tk.Frame(strip, bg=c, height=4).pack(side="left", fill="x", expand=True)

            body = ttk.Frame(self, style="Bg.TFrame", padding=14)
            body.pack(fill="both", expand=True)
            nb = ttk.Notebook(body)
            nb.pack(side="left", fill="y")
            right = tk.Frame(body, bg=P["bg"])
            right.pack(side="left", fill="both", expand=True, padx=(14, 0))

            # ─ Onglet Texte
            f = self.new_tab(nb, "✎  " + self.t("tab_text"))
            self.section(f, 0, self.t("tab_text"), P["cyan"])
            r = 1
            ttk.Label(f, text=self.t("text")).grid(row=r, column=0, sticky="w")
            ttk.Entry(f, textvariable=self.v["text"], width=24, font=(self.FAM, 11, "bold")).grid(
                row=r, column=1, columnspan=2, sticky="we", pady=3)
            r += 1
            ttk.Label(f, text=self.t("font")).grid(row=r, column=0, sticky="w")
            ttk.Combobox(f, textvariable=self.v["font_name"], values=[n for n, _ in self.fonts],
                         width=24).grid(row=r, column=1, sticky="we", pady=3)
            ttk.Button(f, text="•••", style="Ghost.TButton", width=4, command=self.browse_font).grid(
                row=r, column=2, padx=(6, 0))
            r += 1
            for key, var, lo, hi in [("size", "font_size", 0, 300), ("spacing", "letter_spacing", -20, 50),
                                     ("yoff", "y_offset", -200, 200)]:
                ttk.Label(f, text=self.t(key)).grid(row=r, column=0, sticky="w")
                ttk.Spinbox(f, textvariable=self.v[var], from_=lo, to=hi, width=7).grid(
                    row=r, column=1, sticky="w", pady=3)
                r += 1
            ttk.Label(f, text=self.t("fit")).grid(row=r, column=0, sticky="w")
            ttk.Scale(f, variable=self.v["fit_ratio"], from_=0.3, to=1.0).grid(
                row=r, column=1, columnspan=2, sticky="we", pady=6)
            r += 1
            self.section(f, r, self.t("colors"), P["pink"])
            r += 1
            for key, var in [("c_text", "text_color"), ("c_outline", "outline_color"),
                             ("c_start", "fill_start_color")]:
                self.color_row(f, r, key, var)
                r += 1
            f.columnconfigure(1, weight=1)

            # ─ Onglet 2e ligne
            f = self.new_tab(nb, "✚  " + self.t("tab_l2"))
            self.section(f, 0, self.t("tab_l2"), P["yellow"])
            ttk.Checkbutton(f, text=self.t("l2_on"), variable=self.v["line2_on"]).grid(
                row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))
            ttk.Label(f, text=self.t("text")).grid(row=2, column=0, sticky="w")
            ttk.Entry(f, textvariable=self.v["text2"], width=24, font=(self.FAM, 11, "bold")).grid(
                row=2, column=1, columnspan=2, sticky="we", pady=3)
            ttk.Label(f, text=self.t("font")).grid(row=3, column=0, sticky="w")
            ttk.Combobox(f, textvariable=self.v["font_name2"], width=24,
                         values=[self.t("same_font")] + [n for n, _ in self.fonts]).grid(
                row=3, column=1, sticky="we", pady=3)
            ttk.Button(f, text="•••", style="Ghost.TButton", width=4, command=self.browse_font2).grid(
                row=3, column=2, padx=(6, 0))
            r = 4
            for key, var, lo, hi in [("size2", "font_size2", 0, 300), ("spacing", "letter_spacing2", -20, 50),
                                     ("gap", "line_gap", -50, 100)]:
                ttk.Label(f, text=self.t(key)).grid(row=r, column=0, sticky="w")
                ttk.Spinbox(f, textvariable=self.v[var], from_=lo, to=hi, width=7).grid(
                    row=r, column=1, sticky="w", pady=3)
                r += 1
            self.section(f, r, self.t("colors"), P["pink"])
            self.color_row(f, r + 1, "c_text2", "text_color2")
            f.columnconfigure(1, weight=1)

            # ─ Onglet Animation
            f = self.new_tab(nb, "▶  " + self.t("tab_anim"))
            self.section(f, 0, self.t("anim"), P["violet"], cols=2)
            for i, (k, lbl) in enumerate(self.t("anims").items()):
                ttk.Radiobutton(f, text=lbl, value=k, variable=self.v["anim"], style="Pill.Toolbutton").grid(
                    row=1 + i, column=0, columnspan=2, sticky="we", pady=2)
            r = 7
            self.section(f, r, self.t("timing"), P["orange"], cols=2)
            r += 1
            for key, var, lo, hi in [("frames", "n_frames", 2, 500), ("hold", "hold_frames", 0, 200),
                                     ("seed", "seed", 0, 9999)]:
                ttk.Label(f, text=self.t(key)).grid(row=r, column=0, sticky="w")
                ttk.Spinbox(f, textvariable=self.v[var], from_=lo, to=hi, width=7).grid(
                    row=r, column=1, sticky="w", pady=3, padx=(8, 0))
                r += 1
            f.columnconfigure(1, weight=1)

            # ─ Onglet Fond
            f = self.new_tab(nb, "◧  " + self.t("tab_bg"))
            self.section(f, 0, self.t("bgmode"), P["green"])
            for i, (k, lbl) in enumerate(self.t("bgmodes").items()):
                ttk.Radiobutton(f, text=lbl, value=k, variable=self.v["bg_mode"], style="Pill.Toolbutton").grid(
                    row=1 + i, column=0, columnspan=3, sticky="we", pady=2)
            self.section(f, 5, self.t("colors"), P["pink"])
            self.color_row(f, 6, "c_bg1", "bg_color1")
            self.color_row(f, 7, "c_bg2", "bg_color2")
            self.section(f, 8, self.t("bgimg"), P["cyan"])
            ttk.Entry(f, textvariable=self.v["bg_image"], width=22).grid(row=9, column=0, columnspan=2, sticky="we")
            ttk.Button(f, text="•••", style="Ghost.TButton", width=4, command=self.browse_bg).grid(
                row=9, column=2, padx=(6, 0))
            f.columnconfigure(1, weight=1)

            # ─ Onglet Export
            f = self.new_tab(nb, "⇩  " + self.t("tab_export"))
            self.section(f, 0, self.t("tab_export"), P["orange"])
            ttk.Label(f, text=self.t("size_img")).grid(row=1, column=0, sticky="w")
            dim = ttk.Frame(f)
            dim.grid(row=1, column=1, columnspan=2, sticky="w", pady=3)
            ttk.Spinbox(dim, textvariable=self.v["width"], from_=8, to=1024, width=6).pack(side="left")
            ttk.Label(dim, text="  ×  ").pack(side="left")
            ttk.Spinbox(dim, textvariable=self.v["height"], from_=8, to=1024, width=6).pack(side="left")
            ttk.Label(f, text=self.t("start_id")).grid(row=2, column=0, sticky="w")
            ttk.Spinbox(f, textvariable=self.v["start_id"], from_=0, to=99999, width=8).grid(
                row=2, column=1, columnspan=2, sticky="w", pady=3)
            ttk.Label(f, text=self.t("pattern")).grid(row=3, column=0, sticky="w")
            ttk.Entry(f, textvariable=self.v["pattern"], width=20).grid(row=3, column=1, columnspan=2, sticky="we", pady=3)
            ttk.Checkbutton(f, text=self.t("rgb565"), variable=self.v["rgb565"]).grid(
                row=4, column=0, columnspan=3, sticky="w", pady=10)
            ttk.Label(f, text=self.t("export_hint"), style="Muted.TLabel", wraplength=330, justify="left").grid(
                row=5, column=0, columnspan=3, sticky="w")
            f.columnconfigure(1, weight=1)

            # ─ Aperçu
            card = tk.Frame(right, bg=P["card"], highlightthickness=1, highlightbackground=P["border"])
            card.pack(fill="x")
            ci = tk.Frame(card, bg=P["card"])
            ci.pack(fill="x", padx=16, pady=14)
            hdr = tk.Frame(ci, bg=P["card"])
            hdr.pack(fill="x", pady=(0, 10))
            tk.Label(hdr, text="●", bg=P["card"], fg=P["pink"], font=(self.FAM, 10)).pack(side="left")
            tk.Label(hdr, text=" " + self.t("preview").upper(), bg=P["card"], fg=P["muted"],
                     font=(self.FAM, 9, "bold")).pack(side="left")
            self.frame_lbl = tk.Label(hdr, text="", bg=P["card"], fg=P["text"], font=(self.FAM, 9))
            self.frame_lbl.pack(side="right")
            self.canvas = tk.Canvas(ci, bg=P["card"], highlightthickness=0, width=400, height=178)
            self.canvas.pack(fill="x")
            self.canvas.bind("<Configure>", lambda e: self.show_frame())
            ctr = tk.Frame(ci, bg=P["card"])
            ctr.pack(fill="x", pady=(12, 0))
            self.play_btn = ttk.Button(ctr, text=self.t("pause") if self.playing else self.t("play"),
                                       style="Pink.TButton", width=10, command=self.toggle_play)
            self.play_btn.pack(side="left")
            self.slider = ttk.Scale(ctr, from_=0, to=max(1, len(self.frames) - 1), command=self.on_slide)
            self.slider.pack(side="left", fill="x", expand=True, padx=(12, 0))
            self.status = tk.Label(ci, text="", bg=P["card"], fg=P["muted"], font=(self.FAM, 9), anchor="w")
            self.status.pack(fill="x", pady=(10, 0))

            # ─ Barre d'actions (gros boutons toujours visibles)
            act = tk.Frame(right, bg=P["bg"])
            act.pack(fill="x", pady=(14, 0))
            ttk.Button(act, text="⇩  " + self.t("b_export"), style="Orange.TButton",
                       command=self.export).pack(fill="x")
            row2 = tk.Frame(act, bg=P["bg"])
            row2.pack(fill="x", pady=(10, 0))
            ttk.Button(row2, text="⌕  " + self.t("b_analyze"), style="Green.TButton",
                       command=self.analyze).pack(side="left", fill="x", expand=True)
            tk.Frame(row2, bg=P["bg"], width=10).pack(side="left")
            ttk.Button(row2, text="◎  " + self.t("b_gif"), style="Violet.TButton",
                       command=self.export_gif).pack(side="left", fill="x", expand=True)
            if self.frames:
                self.show_frame()

        def color_row(self, parent, row, key, var):
            P = self.PAL
            ttk.Label(parent, text=self.t(key)).grid(row=row, column=0, sticky="w", pady=3)
            box = ttk.Frame(parent)
            box.grid(row=row, column=1, columnspan=2, sticky="w")
            sw = tk.Label(box, width=5, height=1, bd=0, bg=self.v[var].get(), cursor="hand2",
                          highlightthickness=2, highlightbackground=P["border"], highlightcolor=P["cyan"])
            sw.pack(side="left", ipady=3)
            ttk.Entry(box, textvariable=self.v[var], width=9).pack(side="left", padx=8)

            def pick(*_):
                c = colorchooser.askcolor(self.v[var].get(), parent=self)[1]
                if c:
                    self.v[var].set(c.upper())

            def upd(*_):
                try:
                    sw.config(bg="#%02x%02x%02x" % hex2rgb(self.v[var].get()))
                except Exception:
                    pass
            sw.bind("<Button-1>", pick)
            sw.bind("<Enter>", lambda e: sw.config(highlightbackground=P["cyan"]))
            sw.bind("<Leave>", lambda e: sw.config(highlightbackground=P["border"]))
            self.v[var].trace_add("write", upd)


        def _change_lang(self, *_):
            old = TR[self.lang]["same_font"]
            self.lang = "fr" if self.v["lang"].get() == "Français" else "en"
            if self.v["font_name2"].get() == old:
                self.v["font_name2"].set(self.t("same_font"))
            self.build_ui()

        # ── actions ──
        def browse_font(self):
            p = filedialog.askopenfilename(parent=self, filetypes=[("Fonts", "*.ttf *.otf *.ttc"), ("*", "*.*")])
            if p:
                self.v["font_path"].set(p)
                self.v["font_name"].set(os.path.basename(p))

        def browse_font2(self):
            p = filedialog.askopenfilename(parent=self, filetypes=[("Fonts", "*.ttf *.otf *.ttc"), ("*", "*.*")])
            if p:
                self.v["font_path2"].set(p)
                self.v["font_name2"].set(os.path.basename(p))

        def browse_bg(self):
            p = filedialog.askopenfilename(parent=self, filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp"), ("*", "*.*")])
            if p:
                self.v["bg_image"].set(p)
                self.v["bg_mode"].set("image")

        def analyze(self):
            folder = filedialog.askdirectory(parent=self)
            if not folder:
                return
            info = analyze_folder(folder)
            if not info:
                messagebox.showwarning(self.t("title"), self.t("nofiles"), parent=self)
                return
            w, h = sorted(info["sizes"])[0]
            self.v["width"].set(w)
            self.v["height"].set(h)
            self.v["n_frames"].set(info["count"])
            self.v["start_id"].set(info["start_id"])
            msg = self.t("analyzed").format(
                count=info["count"], start=info["start_id"], end=info["end_id"],
                size=f"{w}×{h}", first=os.path.basename(info["first_file"]),
                extra="" if info["contiguous"] else self.t("noncontig"))
            if messagebox.askyesno(self.t("title"), msg, parent=self):
                self.v["bg_image"].set(info["first_file"])
                self.v["bg_mode"].set("image")

        def export(self):
            if not self.frames or len(self.frames) != self.cfg()["n_frames"]:
                return
            folder = filedialog.askdirectory(parent=self)
            if not folder:
                return
            c = self.cfg()
            names = [c["pattern"].format(id=c["start_id"] + i, i=i, n=i + 1, w=c["width"], h=c["height"])
                     for i in range(len(self.frames))]
            if any(os.path.exists(os.path.join(folder, n)) for n in names):
                if not messagebox.askyesno(self.t("title"), self.t("warn_overwrite"), parent=self):
                    return
            try:
                export_frames(self.frames, c, folder)
                messagebox.showinfo(self.t("title"), self.t("done").format(n=len(self.frames), folder=folder), parent=self)
            except Exception as e:
                messagebox.showerror(self.t("err"), str(e), parent=self)

        def export_gif(self):
            if not self.frames:
                return
            p = filedialog.asksaveasfilename(parent=self, defaultextension=".gif", filetypes=[("GIF", "*.gif")])
            if p:
                try:
                    export_gif(self.frames, p)
                except Exception as e:
                    messagebox.showerror(self.t("err"), str(e), parent=self)

        def open_manual(self, *_):
            """Ouvre le manuel PDF dans la langue de l'interface."""
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            name = "Manuel_FR.pdf" if self.lang == "fr" else "Manual_EN.pdf"
            path = os.path.join(base, "manuels", name)
            if not os.path.isfile(path):
                messagebox.showerror(self.t("err"), self.t("no_manual").format(p=path), parent=self)
                return
            try:
                if getattr(sys, "frozen", False):
                    # l'exe se décompresse dans un dossier temporaire effacé à la fermeture :
                    # on copie le manuel dans le dossier temporaire de l'utilisateur
                    import shutil, tempfile
                    dst = os.path.join(tempfile.gettempdir(), name)
                    shutil.copyfile(path, dst)
                    path = dst
                if sys.platform.startswith("win"):
                    os.startfile(path)
                elif sys.platform == "darwin":
                    import subprocess
                    subprocess.Popen(["open", path])
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", path])
            except Exception as e:
                messagebox.showerror(self.t("err"), str(e), parent=self)

        def about(self):
            messagebox.showinfo(self.t("about"), self.t("about_txt").format(v=APP_VERSION), parent=self)

        # ── rendu en arrière-plan ──
        def schedule_render(self, delay=350):
            if self._after_render:
                self.after_cancel(self._after_render)
            self._after_render = self.after(delay, self.start_render)

        def start_render(self):
            self._after_render = None
            self.gen += 1
            gen = self.gen
            c = self.cfg()
            self._prog = (0, c["n_frames"])

            def work():
                try:
                    lay = TextLayout(c)
                    fr = render_frames(c, layout=lay,
                                       progress_cb=lambda k, n: setattr(self, "_prog", (k, n)),
                                       cancel=lambda: gen != self.gen)
                    if fr is not None and gen == self.gen:
                        self._result = (gen, fr, (lay.font_px, lay.font_px2))
                except Exception as e:
                    self._result = (gen, None, str(e))
            self._result = None
            threading.Thread(target=work, daemon=True).start()
            self.after(50, lambda: self.poll(gen))

        def poll(self, gen):
            if gen != self.gen:
                return
            k, n = self._prog
            try:
                self.status.config(text="◌  " + self.t("rendering").format(k=k, n=n), fg=self.PAL["yellow"])
            except tk.TclError:
                pass
            res = self._result
            if res and res[0] == gen:
                _, fr, extra = res
                if fr is None:
                    self.status.config(text=f"✖  {self.t('err')} : {extra}", fg=self.PAL["pink"])
                    return
                self.frames = fr
                self.idx = min(self.idx, len(fr) - 1)
                self.slider.config(to=len(fr) - 1)
                px, px2 = extra
                self.status.config(text="✔  " + (self.t("ready2").format(px=px, px2=px2) if px2
                                                 else self.t("ready").format(px=px)), fg=self.PAL["green"])
                self.show_frame()
            else:
                self.after(60, lambda: self.poll(gen))

        # ── lecture de l'aperçu ──
        def show_frame(self):
            if not self.frames:
                return
            im = self.frames[self.idx]
            cw = max(im.width, self.canvas.winfo_width() - 4)
            z = max(1, min(6, cw // im.width))      # zoom entier = pixels nets
            big = im.resize((im.width * z, im.height * z), Image.NEAREST)
            self._photo = ImageTk.PhotoImage(big)
            if int(self.canvas.cget("height")) != big.height + 6:
                self.canvas.config(height=big.height + 6)
            self.canvas.delete("all")
            x0 = max(0, (self.canvas.winfo_width() - big.width) // 2)
            self.canvas.create_rectangle(x0 - 3, 0, x0 + big.width + 2, big.height + 5,
                                         outline=self.PAL["border"], width=2)
            self.canvas.create_image(x0, 2, anchor="nw", image=self._photo)
            c = self.cfg()
            name = c["pattern"].format(id=c["start_id"] + self.idx, i=self.idx, n=self.idx + 1,
                                       w=c["width"], h=c["height"])
            self.frame_lbl.config(text=self.t("frame").format(k=self.idx + 1, n=len(self.frames), name=name))
            self._slider_lock = True
            self.slider.set(self.idx)
            self._slider_lock = False

        def on_slide(self, val):
            if getattr(self, "_slider_lock", False) or not self.frames:
                return
            self.idx = int(round(float(val)))
            self.show_frame()

        def toggle_play(self):
            self.playing = not self.playing
            self.play_btn.config(text=self.t("pause") if self.playing else self.t("play"))

        def tick(self):
            if self.playing and self.frames:
                self.idx = (self.idx + 1) % len(self.frames)
                pause = 900 if self.idx == len(self.frames) - 1 else 50
                self.show_frame()
                self.after(pause, self.tick)
                return
            self.after(60, self.tick)

    App().mainloop()


if __name__ == "__main__":
    run_gui()
