"""Génère les illustrations de web/illustrations/ pour les articles sans photo : python tools/make_illustrations.py

Ce sont des compositions abstraites par rubrique, volontairement non photographiques :
une image réaliste inventée ferait croire qu'elle montre l'événement.
"""
import math
import os
import random

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "illustrations")
S = ["#c9391f", "#d98a14", "#3f8a56", "#1b8797", "#2f62a8", "#74479f"]
W, H = 800, 500
BACKS = ["#16140f", "#efe9dc", "#1d2a3a"]


def ink(i):
    return "#f7f3ea" if i != 1 else "#16140f"


def politique(r, c, f):
    n = r.randint(5, 7)
    gap = 460 / n
    out = [f'<path d="M170 210 L400 {r.randint(90, 115)} L630 210Z" fill="none" stroke="{f}" stroke-width="6"/>']
    for k in range(n):
        x = 170 + gap * k + gap / 2
        out.append(f'<rect x="{x - 11:.0f}" y="225" width="22" height="160" fill="{c[k % 6]}"/>')
    out.append(f'<rect x="150" y="390" width="500" height="10" fill="{f}"/>')
    return out


def economie(r, c, f):
    out, h = [], r.randint(50, 90)
    for k in range(9):
        h = max(40, min(310, h + r.randint(-20, 62)))
        out.append(f'<rect x="{130 + k * 62}" y="{410 - h}" width="42" height="{h}" fill="{c[k % 6]}"/>')
    out.append(f'<rect x="110" y="410" width="580" height="5" fill="{f}"/>')
    return out


def societe(r, c, f):
    out = []
    for row in range(3):
        for col in range(7):
            x, y = 165 + col * 78 + (row % 2) * 30, 145 + row * 105
            colr = c[r.randrange(6)] if r.random() < .45 else f
            out.append(f'<circle cx="{x}" cy="{y}" r="17" fill="{colr}"/><path d="M{x - 26} {y + 62} a26 34 0 0 1 52 0Z" fill="{colr}"/>')
    return out


def sport(r, c, f):
    out = []
    for k in range(6):
        out.append(f'<path d="M100 {430 - k * 6} Q 400 {r.randint(20, 70) + k * 34} 700 {430 - k * 6}" fill="none" stroke="{c[k]}" stroke-width="9"/>')
    out.append(f'<circle cx="{r.randint(250, 550)}" cy="{r.randint(150, 215)}" r="27" fill="{f}"/>')
    return out


def sante(r, c, f):
    a, b = r.choice(c), r.choice(c)
    return [f'<rect x="345" y="125" width="110" height="250" fill="{a}"/><rect x="275" y="195" width="250" height="110" fill="{a}"/>',
            f'<path d="M90 250 h130 l24 -60 l36 120 l28 -60 h34 M482 250 h66 l26 -60 l32 120 l24 -60 h82" fill="none" stroke="{f}" stroke-width="6" stroke-linejoin="round"/>',
            f'<circle cx="400" cy="250" r="28" fill="{b}"/>']


def tech(r, c, f):
    out = []
    for k in range(13):
        x, y = r.randrange(120, 680, 40), r.randrange(100, 400, 40)
        x2, y2 = x + r.choice((-120, -80, 80, 120)), y + r.choice((-80, 0, 80))
        out.append(f'<path d="M{x} {y} H{x2} V{y2}" fill="none" stroke="{c[k % 6]}" stroke-width="5"/><circle cx="{x}" cy="{y}" r="8" fill="{f}"/>')
    out.append(f'<rect x="325" y="175" width="150" height="150" fill="{c[r.randrange(6)]}" stroke="{f}" stroke-width="6"/>')
    return out


def culture(r, c, f):
    out = []
    for k in range(6):
        rad = 215 - k * 32
        out.append(f'<path d="M{400 - rad} 400 A{rad} {rad} 0 0 1 {400 + rad} 400Z" fill="{c[(k + r.randrange(6)) % 6]}"/>')
    out.append(f'<rect x="130" y="400" width="540" height="7" fill="{f}"/>')
    return out


def environnement(r, c, f):
    out = [f'<circle cx="{r.randint(180, 620)}" cy="135" r="48" fill="{c[1]}"/>']
    for k in range(5):
        y = 245 + k * 46
        d = f"M0 {y}"
        for x in range(0, 800, 100):
            d += f" q50 {r.randint(-44, -18)} 100 0"
        out.append(f'<path d="{d} V500 H0Z" fill="{[c[3], c[2], c[4], c[3], c[2]][k]}" opacity=".88"/>')
    return out


def international(r, c, f):
    cx, cy, R = 400, 250, 165
    out = [f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{f}" stroke-width="6"/>']
    for k, rx in enumerate((165, 110, 50)):
        out.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{R}" fill="none" stroke="{c[k + r.randrange(3)]}" stroke-width="5"/>')
    for k, dy in enumerate((-95, 0, 95)):
        half = math.sqrt(R * R - dy * dy)
        out.append(f'<path d="M{cx - half:.0f} {cy + dy} H{cx + half:.0f}" stroke="{c[(k + 3) % 6]}" stroke-width="5"/>')
    return out


def actualite(r, c, f):
    out = [f'<path d="M400 90 L560 390 H240Z" fill="none" stroke="{f}" stroke-width="8" stroke-linejoin="round"/>',
           f'<path d="M60 {r.randint(250, 300)} L340 270" stroke="{f}" stroke-width="6"/>']
    for k in range(6):
        out.append(f'<path d="M460 270 L780 {150 + k * 48}" stroke="{c[k]}" stroke-width="9"/>')
    return out


for name, fn in dict(politique=politique, economie=economie, societe=societe, sport=sport, sante=sante, tech=tech, culture=culture,
                     environnement=environnement, international=international, actualite=actualite).items():
    for v in range(3):
        rng = random.Random(f"{name}{v}")
        back = BACKS[v]
        colors = S[:]
        rng.shuffle(colors)
        parts = fn(rng, colors, ink(v))
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice"><rect width="{W}" height="{H}" fill="{back}"/>{"".join(parts)}</svg>\n'
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, f"{name}-{v}.svg"), "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)
print("illustrations générées")
