"""Copies allégées des photos des médias : le lecteur les reçoit de Prisme, en WebP, à la bonne taille.

Sans Pillow (lancement local minimal), le visiteur est simplement renvoyé vers la photo d'origine.
"""
import hashlib
import io
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from . import db, rss

try:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 40_000_000     # refuse les images anormalement grandes
except ImportError:
    Image = None

WIDTHS = (480, 960)
MAX_BYTES = 10 * 1024 * 1024
MAX_DECODED_PIXELS = 16_000_000     # après réduction JPEG ; au-delà, décoder demanderait des centaines de Mo
CACHE = os.path.join(os.path.dirname(db.DB_PATH), "imgcache")
_slots = threading.BoundedSemaphore(3)      # limite la mémoire et le processeur utilisés en même temps


def _path(url, width):
    return os.path.join(CACHE, f"{hashlib.sha1(url.encode()).hexdigest()}-{width}.webp")


def get(url, width):
    """Retourne le WebP en octets (créé au besoin), ou None si la photo est indisponible."""
    if Image is None or width not in WIDTHS:
        return None
    path = _path(url, width)
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        pass
    with _slots:
        try:
            raw = rss.fetch(url, max_bytes=MAX_BYTES)
            with Image.open(io.BytesIO(raw)) as im:
                im.draft("RGB", (width * 2, width * 2))    # JPEG : décodage directement à taille réduite
                if im.size[0] * im.size[1] > MAX_DECODED_PIXELS:
                    return None     # image géante (souvent un PNG) : trop de mémoire pour un petit serveur, la photo d'origine est servie
                im = im.convert("RGB")
                im.thumbnail((width, width * 2))
                buf = io.BytesIO()
                im.save(buf, "WEBP", quality=72, method=4)
        except Exception:
            return None
    data = buf.getvalue()
    os.makedirs(CACHE, exist_ok=True)
    tmp = f"{path}.{threading.get_ident()}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return data


def warm(conn, limit=150):
    """Après une collecte, prépare les photos les plus susceptibles d'être affichées."""
    if Image is None:
        return 0
    urls = [r["image_url"] for r in db.rows(conn, """SELECT image_url FROM articles WHERE image_url IS NOT NULL AND is_cluster_lead=1
                                                     ORDER BY published_at DESC LIMIT ?""", (limit,))]
    jobs = [(u, 480) for u in urls] + [(u, 960) for u in urls[:40]]
    with ThreadPoolExecutor(max_workers=2) as pool:
        return sum(1 for r in pool.map(lambda j: get(*j), jobs) if r)
