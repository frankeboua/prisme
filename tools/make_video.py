"""Monte une visite du site à partir de captures nettes, avec légendes et fondus.

Usage : python tools/make_video.py URL DOSSIER_TEMPORAIRE CHEMIN_FFMPEG
Produit web/video/prisme-30s.mp4 et son image d'attente.
"""
import os
import subprocess
import sys

from playwright.sync_api import sync_playwright

BASE, TMP, FFMPEG = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "web", "video")
SHOW, FADE = 5.0, 0.7
CAPTION = """t => {
  let b = document.getElementById('__cap');
  if (!b) { b = document.createElement('div'); b.id = '__cap'; document.body.appendChild(b);
    b.style.cssText = 'position:fixed;left:50%;bottom:34px;transform:translateX(-50%);background:#16140f;color:#f7f3ea;padding:13px 24px;font:600 25px "Instrument Sans",sans-serif;z-index:99;width:max-content;max-width:1100px;text-align:center;border-bottom:4px solid #c9391f'; }
  b.textContent = t;
}"""
READY = "Promise.all([...document.images].filter(i => !i.complete).map(i => new Promise(r => { i.onload = i.onerror = r; setTimeout(r, 6000); })))"
os.makedirs(TMP, exist_ok=True)
os.makedirs(DEST, exist_ok=True)
stills = []

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    page = b.new_context(viewport={"width": 1280, "height": 720}, locale="fr-FR", color_scheme="light").new_page()

    def shot(text, top_of=None, offset=80):
        if top_of:
            page.evaluate("([s, o]) => window.scrollTo(0, document.querySelector(s).getBoundingClientRect().top + scrollY - o)", [top_of, offset])
        page.evaluate(READY)
        page.evaluate(CAPTION, text)
        page.wait_for_timeout(500)
        path = os.path.join(TMP, f"s{len(stills)}.png")
        page.screenshot(path=path)
        stills.append(path)

    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_selector(".front")
    page.wait_for_selector(".topic a.go")
    shot("Prisme réunit l'actualité de 14 médias")
    shot("Une vraie une, mise à jour automatiquement", ".lead-story h2", 130)
    shot("Le spectre : une barre par média qui couvre l'événement", "#topics", 60)
    page.locator(".topic a.go").first.click()
    page.wait_for_selector(".cmp-col")
    shot("Un événement, plusieurs regards, côte à côte", "main", 0)
    shot("Chaque média garde sa source et son lien d'origine", ".compare-grid", 90)
    page.goto(BASE + "/methode", wait_until="networkidle")
    shot("Prisme mesure la couverture. Il ne certifie pas les faits.", "main", 0)
    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_selector(".front")
    shot("Prisme : l'actualité comparée, média par média")
    b.close()

inputs, chain, last, offset = [], [], "[0:v]", 0.0
for path in stills:
    inputs += ["-loop", "1", "-t", str(SHOW), "-i", path]
for i in range(1, len(stills)):
    offset += SHOW - FADE
    chain.append(f"{last}[{i}:v]xfade=transition=fade:duration={FADE}:offset={offset:.2f}[v{i}]")
    last = f"[v{i}]"
out = os.path.join(DEST, "prisme-30s.mp4")
subprocess.run([FFMPEG, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(chain), "-map", last, "-an", "-r", "25", "-c:v", "libx264",
                "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", stills[2], "-frames:v", "1", "-q:v", "5", os.path.join(DEST, "prisme-30s.jpg")], check=True)
print("vidéo prête :", os.path.getsize(out), "octets")
