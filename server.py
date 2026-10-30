"""PRISME — Serveur HTTP et API REST (bibliothèque standard Python uniquement).

Lancement :  python server.py   puis ouvrir http://127.0.0.1:8765
"""
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import webbrowser
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app import db, engine, nlp, rss, seed, translate

PORT = int(os.environ.get("PRISME_PORT", "8765"))
WEB = os.path.join(db.ROOT, "web")
CONN = None
ROUTES = []


def route(method, pattern, auth=None):
    """auth : None (public), 'user' (connecté), 'admin' (administrateur)."""
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), auth, fn))
        return fn
    return deco


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def need(body, *keys):
    for k in keys:
        if not str(body.get(k, "")).strip():
            raise ApiError(400, f"Champ obligatoire manquant : {k}")


def public_user(u):
    return {k: u[k] for k in ("id", "username", "email", "display_name", "role", "persona", "font_scale", "high_contrast",
                              "theme", "simple_mode", "preferred_lang", "diversity_ratio", "created_at")} if u else None


# =====================================================================
#  Authentification
# =====================================================================
@route("POST", "/api/register")
@db.write
def register(req, body, user):
    need(body, "username", "email", "password", "display_name")
    if len(body["password"]) < 6:
        raise ApiError(400, "Le mot de passe doit contenir au moins 6 caractères.")
    if not re.match(r"^[a-zA-Z0-9_.-]{3,30}$", body["username"]):
        raise ApiError(400, "Identifiant invalide (3 à 30 caractères : lettres, chiffres, . _ -).")
    if db.row(CONN, "SELECT id FROM users WHERE username=? OR email=?", (body["username"], body["email"])):
        raise ApiError(409, "Cet identifiant ou cet e-mail est déjà utilisé.")
    h, salt = seed.hash_password(body["password"])
    uid = CONN.execute("INSERT INTO users(username, email, display_name, password_hash, salt) VALUES (?,?,?,?,?)",
                       (body["username"], body["email"], body["display_name"], h, salt)).lastrowid
    cats = {r["slug"]: r["id"] for r in db.rows(CONN, "SELECT * FROM categories")}
    for slug in body.get("interests") or []:
        if slug in cats:
            CONN.execute("INSERT OR IGNORE INTO interests VALUES (?,?,1.0)", (uid, cats[slug]))
    CONN.execute("INSERT INTO notifications(user_id, kind, message) VALUES (?, 'systeme', ?)",
                 (uid, "Bienvenue sur Prisme ! Ajoutez des alertes par mots-clés pour être notifié(e)."))
    CONN.commit()
    return _open_session(uid)


def _open_session(uid):
    token = secrets.token_urlsafe(32)
    CONN.execute("INSERT INTO sessions(token, user_id, expires_at) VALUES (?,?,?)",
                 (token, uid, db.to_str(db.now() + timedelta(days=7))))
    CONN.commit()
    return {"token": token, "user": public_user(db.row(CONN, "SELECT * FROM users WHERE id=?", (uid,)))}


@route("POST", "/api/login")
@db.write
def login(req, body, user):
    need(body, "username", "password")
    u = db.row(CONN, "SELECT * FROM users WHERE username=? OR email=?", (body["username"], body["username"]))
    if not u or seed.hash_password(body["password"], u["salt"])[0] != u["password_hash"]:
        raise ApiError(401, "Identifiant ou mot de passe incorrect.")
    return _open_session(u["id"])


@route("POST", "/api/logout", "user")
@db.write
def logout(req, body, user):
    CONN.execute("DELETE FROM sessions WHERE user_id=? AND token=?", (user["id"], req.token))
    CONN.commit()
    return {"ok": True}


@route("GET", "/api/me")
def me(req, q, user):
    if not user:
        return {"user": None}
    return {"user": public_user(user),
            "unread": db.scalar(CONN, "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (user["id"],)),
            "profile": {k: v for k, v in engine.user_profile(CONN, user["id"]).items() if k in ("diversity_index", "history_size")}}


@route("PUT", "/api/me", "user")
@db.write
def update_me(req, body, user):
    fields = {"display_name": str, "email": str, "font_scale": float, "high_contrast": int, "theme": str,
              "simple_mode": int, "preferred_lang": str, "diversity_ratio": float}
    sets, vals = [], []
    for k, cast in fields.items():
        if k in body:
            v = cast(body[k])
            if k == "font_scale":
                v = min(max(v, 0.85), 1.6)
            if k == "diversity_ratio":
                v = min(max(v, 0.0), 0.5)
            if k == "theme" and v not in ("auto", "light", "dark"):
                continue
            sets.append(f"{k}=?"); vals.append(v)
    if body.get("new_password"):
        if len(body["new_password"]) < 6:
            raise ApiError(400, "Le nouveau mot de passe doit contenir au moins 6 caractères.")
        h, salt = seed.hash_password(body["new_password"])
        sets += ["password_hash=?", "salt=?"]; vals += [h, salt]
    if sets:
        CONN.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*vals, user["id"]))
        CONN.commit()
    return {"user": public_user(db.row(CONN, "SELECT * FROM users WHERE id=?", (user["id"],)))}


# =====================================================================
#  Référentiels
# =====================================================================
@route("GET", "/api/categories")
def categories(req, q, user):
    return db.rows(CONN, """SELECT c.*, (SELECT COUNT(*) FROM articles a WHERE a.category_id=c.id) articles FROM categories c ORDER BY c.id""")


@route("GET", "/api/sources")
def sources(req, q, user):
    return db.rows(CONN, """SELECT s.*, c.name category_name, (SELECT COUNT(*) FROM articles a WHERE a.source_id=s.id) articles
                            FROM sources s LEFT JOIN categories c ON c.id=s.default_category ORDER BY s.is_demo, s.name""")


@route("POST", "/api/sources", "admin")
@db.write
def add_source(req, body, user):
    need(body, "name", "feed_url")
    if not body["feed_url"].startswith(("http://", "https://")):
        raise ApiError(400, "L'URL du flux doit commencer par http:// ou https://")
    try:
        items = rss.parse_feed(rss.fetch(body["feed_url"]))
    except Exception as e:
        raise ApiError(400, f"Flux RSS illisible ou inaccessible : {e}")
    cat = db.scalar(CONN, "SELECT id FROM categories WHERE slug=?", (body.get("category"),))
    sid = CONN.execute("""INSERT INTO sources(name, website, feed_url, country, language, kind, default_category, reliability, certified, reliability_note)
                          VALUES (?,?,?,?,?,?,?,?,?,?)""",
                       (body["name"], body.get("website"), body["feed_url"], body.get("country"), body.get("language", "fr"),
                        body.get("kind", "web"), cat, int(body.get("reliability", 60)), int(body.get("certified", 0)), seed.NOTE)).lastrowid
    CONN.commit()
    return {"id": sid, "items_detected": len(items)}


@route("PUT", r"/api/sources/(\d+)", "admin")
@db.write
def edit_source(req, body, user, sid):
    for k in ("active", "reliability", "certified"):
        if k in body:
            CONN.execute(f"UPDATE sources SET {k}=? WHERE id=?", (int(body[k]), int(sid)))
    if "reliability_note" in body:
        CONN.execute("UPDATE sources SET reliability_note=? WHERE id=?", (body["reliability_note"], int(sid)))
    CONN.commit()
    return db.row(CONN, "SELECT * FROM sources WHERE id=?", (int(sid),))


@route("DELETE", r"/api/sources/(\d+)", "admin")
@db.write
def delete_source(req, q, user, sid):
    CONN.execute("DELETE FROM sources WHERE id=? AND is_demo=0", (int(sid),))
    CONN.commit()
    return {"ok": True}


# =====================================================================
#  Fil d'actualité, recherche, articles
# =====================================================================
def qv(q, k, default=None):
    v = q.get(k, [default])[0]
    return v if v not in ("", None) else default


@route("GET", "/api/feed")
def feed(req, q, user):
    return engine.feed(CONN, user, qv(q, "mode", "pour_vous"), qv(q, "category"), qv(q, "media"), qv(q, "source"),
                       int(qv(q, "limit", 24)), int(qv(q, "offset", 0)))


@route("GET", "/api/search")
def search(req, q, user):
    where, params = ["1=1"], []
    text = qv(q, "q")
    if text:
        for term in text.split()[:6]:
            where.append("(a.title LIKE ? OR a.summary LIKE ? OR a.content LIKE ? OR a.author LIKE ?)")
            params += [f"%{term}%"] * 4
    for key, col in (("source", "a.source_id"), ("category", "c.slug"), ("media", "a.media_type"),
                     ("status", "a.verification_status"), ("lang", "a.language")):
        v = qv(q, key)
        if v:
            where.append(f"{col}=?"); params.append(v)
    if qv(q, "author"):
        where.append("a.author LIKE ?"); params.append(f"%{qv(q, 'author')}%")
    if qv(q, "from"):
        where.append("date(a.published_at)>=date(?)"); params.append(qv(q, "from"))
    if qv(q, "to"):
        where.append("date(a.published_at)<=date(?)"); params.append(qv(q, "to"))
    if qv(q, "dedup") == "1":
        where.append("a.is_cluster_lead=1")
    order = {"date": "a.published_at DESC", "ancien": "a.published_at ASC", "fiabilite": "s.reliability DESC, a.published_at DESC",
             "verification": "a.verification_score DESC"}.get(qv(q, "sort", "date"), "a.published_at DESC")
    sql = engine.FEED_SQL.replace("WHERE s.active=1", "WHERE 1=1").format(where=" AND " + " AND ".join(where)) + f" ORDER BY {order} LIMIT 200"
    items = db.rows(CONN, sql, params)
    now = db.now()
    return {"total": len(items), "items": [engine.decorate(CONN, a, now) for a in items]}


def _article(aid):
    a = db.row(CONN, engine.FEED_SQL.replace("WHERE s.active=1", "WHERE 1=1").format(where=" AND a.id=?"), (int(aid),))
    if not a:
        raise ApiError(404, "Article introuvable.")
    return a


@route("GET", r"/api/articles/(\d+)")
def article(req, q, user, aid):
    a = _article(aid)
    content = nlp.strip_html(a.get("content") or a.get("summary") or "")
    out = engine.decorate(CONN, dict(a))
    out["content"] = content
    out["paragraphs"] = [p for p in content.split("\n") if p.strip()] or [content]
    out["reading_time"] = max(1, round(len(content.split()) / 200))
    out["readability"] = nlp.readability(content)
    out["tone"] = nlp.tone(a["title"] + " " + content)
    out["keywords"] = nlp.keywords(a["title"] + " " + content, 8)
    out["claims"] = engine.get_verification(CONN, a["id"])
    out["source"] = db.row(CONN, "SELECT * FROM sources WHERE id=?", (a["source_id"],))
    out["reports"] = db.rows(CONN, "SELECT reason, status, admin_response, created_at FROM reports WHERE article_id=? ORDER BY created_at DESC", (a["id"],))
    if user:
        out["favorite"] = db.row(CONN, "SELECT * FROM favorites WHERE user_id=? AND article_id=?", (user["id"], a["id"]))
        prof = engine.user_profile(CONN, user["id"])
        out["why"] = engine.explain(dict(a), prof, db.now())
        with db._lock:
            CONN.execute("INSERT INTO reading_history(user_id, article_id) VALUES (?,?)", (user["id"], a["id"]))
            CONN.execute("UPDATE articles SET views=views+1 WHERE id=?", (a["id"],))
            CONN.commit()
    else:
        out["why"] = engine.explain(dict(a), None, db.now())
    return out


@route("GET", r"/api/articles/(\d+)/summary")
def summary(req, q, user, aid):
    return engine.summarize(CONN, int(aid), int(qv(q, "n", 4)))


@route("POST", r"/api/articles/(\d+)/verify")
def reverify(req, body, user, aid):
    res = engine.verify_article(CONN, int(aid))
    return {**res, "claims": engine.get_verification(CONN, int(aid))}


@route("GET", r"/api/articles/(\d+)/translate")
def translate_article(req, q, user, aid):
    a = _article(aid)
    dst = qv(q, "lang", "fr" if a["language"] != "fr" else "en")
    return {"lang": dst, **translate.translate_article(CONN, a, dst)}


@route("GET", r"/api/articles/(\d+)/simplify")
def simplify_article(req, q, user, aid):
    a = _article(aid)
    text = nlp.strip_html(a.get("content") or a.get("summary") or "")
    gl = [(r["term"], r["simple"], r["definition"]) for r in db.rows(CONN, "SELECT * FROM glossary")]
    simple, used = nlp.simplify(text, gl)
    return {"original": nlp.readability(text), "simplified": nlp.readability(simple), "text": simple, "glossary": used}


@route("GET", r"/api/clusters/(\d+)")
def compare(req, q, user, cid):
    res = engine.compare_cluster(CONN, int(cid))
    if not res:
        raise ApiError(404, "Sujet introuvable.")
    lead = res["cluster"]["lead_article_id"]
    res["summary"] = engine.summarize(CONN, lead, 4) if lead else None
    return res


@route("POST", r"/api/articles/(\d+)/share")
@db.write
def share(req, body, user, aid):
    CONN.execute("INSERT INTO shares(user_id, article_id, channel) VALUES (?,?,?)", (user["id"] if user else None, int(aid), body.get("channel", "lien")))
    CONN.execute("UPDATE articles SET shares=shares+1 WHERE id=?", (int(aid),))
    CONN.commit()
    return {"ok": True}


# =====================================================================
#  Favoris, dossiers de veille, alertes, notifications
# =====================================================================
@route("GET", "/api/favorites", "user")
def favorites(req, q, user):
    items = db.rows(CONN, engine.FEED_SQL.replace("WHERE s.active=1", "JOIN favorites f ON f.article_id=a.id WHERE f.user_id=?")
                    .replace("SELECT a.*", "SELECT a.*, f.folder_id, f.note, f.created_at saved_at").format(where="") + " ORDER BY f.created_at DESC", (user["id"],))
    now = db.now()
    folders = db.rows(CONN, "SELECT f.*, (SELECT COUNT(*) FROM favorites x WHERE x.folder_id=f.id) n FROM folders f WHERE user_id=? ORDER BY name", (user["id"],))
    return {"items": [engine.decorate(CONN, a, now) for a in items], "folders": folders}


@route("POST", "/api/favorites", "user")
@db.write
def add_favorite(req, body, user):
    need(body, "article_id")
    CONN.execute("INSERT OR REPLACE INTO favorites(user_id, article_id, folder_id, note) VALUES (?,?,?,?)",
                 (user["id"], int(body["article_id"]), body.get("folder_id") or None, body.get("note")))
    CONN.commit()
    return {"ok": True}


@route("DELETE", r"/api/favorites/(\d+)", "user")
@db.write
def del_favorite(req, q, user, aid):
    CONN.execute("DELETE FROM favorites WHERE user_id=? AND article_id=?", (user["id"], int(aid)))
    CONN.commit()
    return {"ok": True}


@route("POST", "/api/folders", "user")
@db.write
def add_folder(req, body, user):
    need(body, "name")
    try:
        fid = CONN.execute("INSERT INTO folders(user_id, name, color) VALUES (?,?,?)", (user["id"], body["name"].strip(), body.get("color", "#0ea5e9"))).lastrowid
    except Exception:
        raise ApiError(409, "Un dossier porte déjà ce nom.")
    CONN.commit()
    return {"id": fid}


@route("DELETE", r"/api/folders/(\d+)", "user")
@db.write
def del_folder(req, q, user, fid):
    CONN.execute("DELETE FROM folders WHERE id=? AND user_id=?", (int(fid), user["id"]))
    CONN.commit()
    return {"ok": True}


@route("GET", "/api/alerts", "user")
def alerts(req, q, user):
    return db.rows(CONN, """SELECT al.*, (SELECT COUNT(*) FROM notifications n JOIN articles a ON a.id=n.article_id
                            WHERE n.user_id=al.user_id AND n.kind='alerte' AND n.message LIKE '%« ' || al.keyword || ' »%') hits
                            FROM alerts al WHERE user_id=? ORDER BY created_at DESC""", (user["id"],))


@route("POST", "/api/alerts", "user")
def add_alert(req, body, user):
    need(body, "keyword")
    with db._lock:
        CONN.execute("INSERT OR IGNORE INTO alerts(user_id, keyword) VALUES (?,?)", (user["id"], body["keyword"].strip()[:60]))
        CONN.commit()
    return {"created_notifications": engine.check_alerts(CONN, days=7)}


@route("PUT", r"/api/alerts/(\d+)", "user")
@db.write
def toggle_alert(req, body, user, alid):
    CONN.execute("UPDATE alerts SET active=? WHERE id=? AND user_id=?", (int(body.get("active", 1)), int(alid), user["id"]))
    CONN.commit()
    return {"ok": True}


@route("DELETE", r"/api/alerts/(\d+)", "user")
@db.write
def del_alert(req, q, user, alid):
    CONN.execute("DELETE FROM alerts WHERE id=? AND user_id=?", (int(alid), user["id"]))
    CONN.commit()
    return {"ok": True}


@route("GET", "/api/notifications", "user")
def notifications(req, q, user):
    return db.rows(CONN, """SELECT n.*, a.title article_title FROM notifications n LEFT JOIN articles a ON a.id=n.article_id
                            WHERE n.user_id=? ORDER BY n.is_read, n.created_at DESC LIMIT 100""", (user["id"],))


@route("POST", "/api/notifications/read", "user")
@db.write
def read_notifications(req, body, user):
    if body.get("id"):
        CONN.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (int(body["id"]), user["id"]))
    else:
        CONN.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user["id"],))
    CONN.commit()
    return {"ok": True}


@route("GET", "/api/interests", "user")
def interests(req, q, user):
    return db.rows(CONN, """SELECT c.*, COALESCE(i.weight, 0) weight FROM categories c
                            LEFT JOIN interests i ON i.category_id=c.id AND i.user_id=? ORDER BY c.id""", (user["id"],))


@route("PUT", "/api/interests", "user")
@db.write
def set_interests(req, body, user):
    CONN.execute("DELETE FROM interests WHERE user_id=?", (user["id"],))
    for cid, w in (body.get("weights") or {}).items():
        if float(w) > 0:
            CONN.execute("INSERT INTO interests VALUES (?,?,?)", (user["id"], int(cid), min(float(w), 1.0)))
    CONN.commit()
    return {"ok": True}


@route("DELETE", "/api/history", "user")
@db.write
def clear_history(req, q, user):
    CONN.execute("DELETE FROM reading_history WHERE user_id=?", (user["id"],))
    CONN.commit()
    return {"ok": True}


# =====================================================================
#  Signalement d'erreurs et modération
# =====================================================================
REASONS = ("factuelle", "date", "source", "titre_trompeur", "traduction", "doublon", "autre")


@route("POST", "/api/reports")
@db.write
def add_report(req, body, user):
    need(body, "article_id", "reason", "description")
    if body["reason"] not in REASONS:
        raise ApiError(400, "Motif de signalement invalide.")
    if len(body["description"].strip()) < 10:
        raise ApiError(400, "Merci de décrire l'erreur (10 caractères minimum).")
    rid = CONN.execute("INSERT INTO reports(user_id, article_id, reason, description, evidence_url) VALUES (?,?,?,?,?)",
                       (user["id"] if user else None, int(body["article_id"]), body["reason"], body["description"].strip()[:2000],
                        body.get("evidence_url"))).lastrowid
    for adm in db.rows(CONN, "SELECT id FROM users WHERE role='admin'"):
        CONN.execute("INSERT OR IGNORE INTO notifications(user_id, article_id, kind, message) VALUES (?,?,?,?)",
                     (adm["id"], int(body["article_id"]), "signalement", f"Nouveau signalement ({body['reason']}) à modérer."))
    CONN.commit()
    return {"id": rid}


@route("GET", "/api/reports", "user")
def list_reports(req, q, user):
    where = "" if user["role"] == "admin" and qv(q, "all") == "1" else "WHERE r.user_id=?"
    params = () if not where else (user["id"],)
    return db.rows(CONN, f"""SELECT r.*, a.title article_title, s.name source_name, u.display_name reporter
                             FROM reports r JOIN articles a ON a.id=r.article_id JOIN sources s ON s.id=a.source_id
                             LEFT JOIN users u ON u.id=r.user_id {where}
                             ORDER BY CASE r.status WHEN 'en_attente' THEN 0 WHEN 'en_cours' THEN 1 ELSE 2 END, r.created_at DESC""", params)


@route("PUT", r"/api/reports/(\d+)", "admin")
@db.write
def moderate(req, body, user, rid):
    status = body.get("status")
    if status not in ("en_attente", "en_cours", "corrige", "rejete"):
        raise ApiError(400, "Statut invalide.")
    r = db.row(CONN, "SELECT * FROM reports WHERE id=?", (int(rid),))
    if not r:
        raise ApiError(404, "Signalement introuvable.")
    CONN.execute("UPDATE reports SET status=?, admin_response=?, resolved_at=? WHERE id=?",
                 (status, body.get("admin_response"), db.now_str() if status in ("corrige", "rejete") else None, int(rid)))
    if status == "corrige" and body.get("correction_note"):
        CONN.execute("UPDATE articles SET correction_note=? WHERE id=?", (body["correction_note"], r["article_id"]))
    if r["user_id"]:
        label = {"en_cours": "est en cours d'examen", "corrige": "a été validé : correction publiée", "rejete": "a été examiné et clôturé", "en_attente": "est en attente"}[status]
        CONN.execute("INSERT OR REPLACE INTO notifications(user_id, article_id, kind, message, is_read) VALUES (?,?,?,?,0)",
                     (r["user_id"], r["article_id"], "signalement", f"Votre signalement {label}."))
    CONN.commit()
    return {"ok": True}


# =====================================================================
#  Tendances, digest, export, statistiques, collecte
# =====================================================================
@route("GET", "/api/trends")
def trends(req, q, user):
    return engine.trends(CONN)


@route("GET", "/api/digest")
def digest(req, q, user):
    return engine.digest(CONN)


@route("GET", "/api/export", "user")
def export(req, q, user):
    fmt = qv(q, "format", "txt")
    folder = qv(q, "folder")
    sql = """SELECT a.title, a.url, a.author, a.published_at, s.name source, a.verification_status, fo.name folder
             FROM favorites f JOIN articles a ON a.id=f.article_id JOIN sources s ON s.id=a.source_id
             LEFT JOIN folders fo ON fo.id=f.folder_id WHERE f.user_id=?""" + (" AND f.folder_id=?" if folder else "") + " ORDER BY a.published_at DESC"
    items = db.rows(CONN, sql, (user["id"], int(folder)) if folder else (user["id"],))
    if fmt == "csv":
        lines = ["titre;source;auteur;date;statut;dossier;lien"]
        for i in items:
            lines.append(";".join('"' + str(i[k] or "").replace('"', "'") + '"' for k in ("title", "source", "author", "published_at", "verification_status", "folder", "url")))
        return ("text/csv", "﻿" + "\n".join(lines), "prisme_export.csv")
    if fmt == "bib":
        out = []
        for n, i in enumerate(items, 1):
            d = db.parse(i["published_at"])
            out.append(f"@online{{prisme{n},\n  title = {{{i['title']}}},\n  author = {{{i['author'] or i['source']}}},\n"
                       f"  organization = {{{i['source']}}},\n  date = {{{d.strftime('%Y-%m-%d') if d else ''}}},\n  url = {{{i['url'] or ''}}}\n}}")
        return ("text/plain", "\n\n".join(out), "prisme_bibliographie.bib")
    lines = [f"PRISME — Export de {user['display_name']} — {db.now().strftime('%d/%m/%Y %H:%M')} UTC", "=" * 70]
    for n, i in enumerate(items, 1):
        d = db.parse(i["published_at"])
        lines.append(f"[{n}] {i['title']}\n    {i['source']}{', ' + i['author'] if i['author'] else ''} — {d.strftime('%d/%m/%Y') if d else 's.d.'}"
                     f" — statut : {engine.STATUS_LABEL[i['verification_status']]}\n    {i['url'] or '(contenu de démonstration)'}")
    return ("text/plain", "\n".join(lines), "prisme_export.txt")


@route("GET", "/api/stats")
def stats(req, q, user):
    s = lambda sql, p=(): db.scalar(CONN, sql, p)
    total = s("SELECT COUNT(*) FROM articles")
    clusters = s("SELECT COUNT(*) FROM clusters")
    return {
        "articles": total, "sources": s("SELECT COUNT(*) FROM sources WHERE active=1"),
        "real_sources": s("SELECT COUNT(*) FROM sources WHERE is_demo=0 AND active=1"),
        "clusters": clusters, "duplicates": total - clusters,
        "dedup_rate": round(100 * (total - clusters) / total, 1) if total else 0,
        "multi_source_topics": s("SELECT COUNT(*) FROM clusters WHERE source_count>1"),
        "users": s("SELECT COUNT(*) FROM users"), "claims": s("SELECT COUNT(*) FROM claims"),
        "evidences": s("SELECT COUNT(*) FROM evidences"),
        "reports_open": s("SELECT COUNT(*) FROM reports WHERE status IN ('en_attente','en_cours')"),
        "reports_total": s("SELECT COUNT(*) FROM reports"),
        "verification": db.rows(CONN, "SELECT verification_status status, COUNT(*) n FROM articles GROUP BY 1 ORDER BY 2 DESC"),
        "by_category": db.rows(CONN, "SELECT c.name, c.color, COUNT(a.id) n FROM categories c LEFT JOIN articles a ON a.category_id=c.id GROUP BY c.id ORDER BY n DESC"),
        "by_media": db.rows(CONN, "SELECT media_type, COUNT(*) n FROM articles GROUP BY 1 ORDER BY 2 DESC"),
        "by_source": db.rows(CONN, "SELECT s.name, s.reliability, COUNT(a.id) n FROM sources s LEFT JOIN articles a ON a.source_id=s.id GROUP BY s.id ORDER BY n DESC LIMIT 12"),
        "last_fetch": db.row(CONN, "SELECT * FROM fetch_log WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"),
        "fetching": REFRESH["running"],
    }


REFRESH = {"running": False, "last": None}


def _refresh_job():
    if REFRESH["running"]:
        return
    REFRESH["running"] = True
    try:
        REFRESH["last"] = rss.refresh_all(CONN)
    except Exception as e:
        REFRESH["last"] = {"error": str(e)}
    finally:
        REFRESH["running"] = False


@route("POST", "/api/refresh", "user")
def refresh(req, body, user):
    if REFRESH["running"]:
        return {"running": True, "message": "Une collecte est déjà en cours."}
    threading.Thread(target=_refresh_job, daemon=True).start()
    return {"running": True, "message": "Collecte des flux RSS lancée."}


@route("GET", "/api/refresh")
def refresh_status(req, q, user):
    return REFRESH


@route("POST", "/api/admin/recluster", "admin")
def admin_recluster(req, body, user):
    res = engine.recluster(CONN)
    with db._lock:
        CONN.execute("UPDATE articles SET verification_status='en_attente'")
        CONN.commit()
    res["verified"] = engine.verify_pending(CONN, 5000)
    return res


@route("GET", "/api/admin/users", "admin")
def admin_users(req, q, user):
    return db.rows(CONN, """SELECT u.id, u.username, u.display_name, u.email, u.role, u.persona, u.created_at,
                            (SELECT COUNT(*) FROM reading_history h WHERE h.user_id=u.id) lectures,
                            (SELECT COUNT(*) FROM favorites f WHERE f.user_id=u.id) favoris,
                            (SELECT COUNT(*) FROM reports r WHERE r.user_id=u.id) signalements
                            FROM users u ORDER BY u.id""")


# =====================================================================
#  Serveur HTTP
# =====================================================================
class Handler(BaseHTTPRequestHandler):
    server_version = "Prisme/1.0"

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stdout.write("  %s\n" % (fmt % args))

    def _user(self):
        auth = self.headers.get("Authorization", "")
        self.token = auth[7:] if auth.startswith("Bearer ") else None
        if not self.token:
            return None
        return db.row(CONN, """SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                               WHERE s.token=? AND s.expires_at > ?""", (self.token, db.now_str()))

    def _send(self, status, payload, ctype="application/json; charset=utf-8", filename=None):
        data = payload if isinstance(payload, bytes) else (payload.encode("utf-8") if isinstance(payload, str)
                                                           else json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def _api(self, method):
        url = urlparse(self.path)
        for m, rx, auth, fn in ROUTES:
            match = rx.match(url.path)
            if m != method or not match:
                continue
            try:
                user = self._user()
                if auth and not user:
                    raise ApiError(401, "Connexion requise pour cette fonctionnalité.")
                if auth == "admin" and user["role"] != "admin":
                    raise ApiError(403, "Réservé aux administrateurs.")
                if method in ("POST", "PUT"):
                    n = int(self.headers.get("Content-Length") or 0)
                    try:
                        arg = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise ApiError(400, "Requête invalide : corps JSON UTF-8 attendu.")
                else:
                    arg = parse_qs(url.query)
                with db._lock:   # une seule connexion SQLite partagée : accès sérialisés
                    res = fn(self, arg, user, *match.groups())
                if isinstance(res, tuple):
                    ctype, body, fname = res
                    return self._send(200, body, ctype + "; charset=utf-8", fname)
                return self._send(200, res)
            except ApiError as e:
                return self._send(e.status, {"error": str(e)})
            except Exception as e:
                import traceback
                traceback.print_exc()
                return self._send(500, {"error": f"Erreur interne : {e}"})
        self._send(404, {"error": "Route inconnue."})

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        path = urlparse(self.path).path
        if path == "/":
            path = "/index.html"
        full = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not full.startswith(WEB) or not os.path.isfile(full):
            full = os.path.join(WEB, "index.html")
        with open(full, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, data, ctype)

    def do_POST(self):
        self._api("POST")

    def do_PUT(self):
        self._api("PUT")

    def do_DELETE(self):
        self._api("DELETE")


def bootstrap():
    global CONN
    first = not os.path.exists(db.DB_PATH)
    CONN = db.connect()
    db.init_schema(CONN)
    if first or not db.scalar(CONN, "SELECT COUNT(*) FROM categories"):
        print("  > Création de la base de données et des données de démonstration...")
        seed.seed(CONN)
        engine.recluster(CONN)
        engine.verify_pending(CONN, 5000)
        engine.check_alerts(CONN)
    else:
        seed.refresh_demo_dates(CONN)
    seed.make_demo_audio(os.path.join(WEB, "media", "demo_podcast.wav"))
    CONN.execute("DELETE FROM sessions WHERE expires_at < ?", (db.now_str(),))
    CONN.commit()


def main():
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    print("=" * 62)
    print("  PRISME — Agrégateur intelligent des nouveaux médias")
    print("  ESATIC TWIN3 — Groupe 7")
    print("=" * 62)
    bootstrap()
    if "--no-fetch" not in sys.argv:
        threading.Thread(target=_refresh_job, daemon=True).start()
        print("  > Collecte des flux RSS réels en arrière-plan (si Internet disponible)")
    shared = "--reseau" in sys.argv          # partage sur le réseau local (Wi-Fi de la salle)
    httpd = ThreadingHTTPServer(("0.0.0.0" if shared else "127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"  > Application disponible sur {url}")
    if shared:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except OSError:
            ip = socket.gethostbyname(socket.gethostname())
        finally:
            s.close()
        print(f"  > PARTAGE RÉSEAU ACTIVÉ : sur le même Wi-Fi, ouvrez  http://{ip}:{PORT}")
    print("  > Fermez cette fenêtre pour arrêter le serveur.\n")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
