"""Traduction automatique (API MyMemory, gratuite) avec cache en base de données."""
import json
import re
import urllib.parse
import urllib.request

from . import db, nlp


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
    return out


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
    except Exception as e:
        return {"error": f"Traduction indisponible (connexion Internet requise) : {e}"}
    res = {"title": title, "body": re.sub(r"\s+", " ", " ".join(parts)), "engine": "MyMemory (traduction automatique)"}
    with db._lock:
        conn.execute("INSERT OR REPLACE INTO translations(article_id, lang, title, body, engine) VALUES (?,?,?,?,?)",
                     (art["id"], dst, res["title"], res["body"], res["engine"]))
        conn.commit()
    return {**res, "cached": False}
