"""Traduction automatique (API MyMemory, gratuite) avec cache en base de données."""
import html
import json
import re
import urllib.parse
import urllib.request

from . import db, nlp


# Langues testées une par une auprès du service. Le bambara, le dioula et le kinyarwanda sont exclus :
# leurs traductions d'essai étaient fausses. Le baoulé est refusé par le service.
LANGUAGES = {
    "fr": "Français", "en": "Anglais", "es": "Espagnol", "pt": "Portugais", "ar": "Arabe", "de": "Allemand", "it": "Italien", "nl": "Néerlandais",
    "ru": "Russe", "zh": "Chinois", "ja": "Japonais", "ko": "Coréen", "hi": "Hindi", "bn": "Bengali", "ur": "Ourdou", "fa": "Persan", "tr": "Turc",
    "id": "Indonésien", "ms": "Malais", "vi": "Vietnamien", "th": "Thaï", "tl": "Tagalog", "pl": "Polonais", "uk": "Ukrainien", "ro": "Roumain",
    "el": "Grec", "sv": "Suédois", "da": "Danois", "no": "Norvégien", "fi": "Finnois", "cs": "Tchèque", "hu": "Hongrois", "he": "Hébreu",
    "sw": "Swahili", "ha": "Haoussa", "yo": "Yoruba", "ig": "Igbo", "am": "Amharique", "wo": "Wolof", "ff": "Peul", "ln": "Lingala",
    "mg": "Malgache", "so": "Somali", "zu": "Zoulou", "xh": "Xhosa", "af": "Afrikaans",
}
RTL = {"ar", "fa", "he", "ur"}
UNEVEN = {"sw", "ha", "yo", "ig", "am", "wo", "ff", "ln", "mg", "so", "zu", "xh"}


def _chunks(text, size=450):
    out, cur = [], ""
    for s in nlp.sentences(text) or [text]:
        if len(cur) + len(s) + 1 > size and cur:
            out.append(cur)
            cur = ""
        cur = (cur + " " + s).strip()
    if cur:
        out.append(cur)
    return [c[:size] for c in out]


def _call(text, src, dst):
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode({"q": text, "langpair": f"{src}|{dst}"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Prisme"}), timeout=12) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = data.get("responseData", {}).get("translatedText") or ""
    if "MYMEMORY WARNING" in out.upper() or not out:
        raise RuntimeError("quota de traduction atteint")
    return html.unescape(out)


def translate_article(conn, art, dst):
    cached = db.row(conn, "SELECT * FROM translations WHERE article_id=? AND lang=?", (art["id"], dst))
    if cached:
        return {**cached, "cached": True}
    src = art["language"]
    if src == dst:
        return {"title": art["title"], "body": nlp.strip_html(art["summary"]), "engine": "aucune (même langue)", "cached": False}
    body = nlp.strip_html(art.get("content") or art.get("summary") or "")[:2200]
    try:
        title = _call(art["title"], src, dst)
        parts = [_call(c, src, dst) for c in _chunks(body)]
    except RuntimeError:
        return {"error": "Le service de traduction gratuit a atteint sa limite du jour. Réessayez demain ou lisez l'article original."}
    except Exception:
        return {"error": "Le service de traduction ne répond pas pour le moment. Réessayez dans quelques minutes."}
    res = {"title": title, "body": re.sub(r"\s+", " ", " ".join(parts)), "engine": "MyMemory (traduction automatique)"}
    with db._lock:
        conn.execute("INSERT OR REPLACE INTO translations(article_id, lang, title, body, engine) VALUES (?,?,?,?,?)",
                     (art["id"], dst, res["title"], res["body"], res["engine"]))
        conn.commit()
    return {**res, "cached": False}
