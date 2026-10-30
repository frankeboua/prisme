"""PRISME — Serveur HTTP et API REST (bibliothèque standard Python uniquement).

Lancement local :  python server.py   puis ouvrir http://127.0.0.1:8765
Production      :  gunicorn wsgi:application (voir wsgi.py), avec PRISME_MODE=public
"""
import email.utils
import gzip
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import traceback
import webbrowser
from collections import defaultdict, deque
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app import db, editorial, engine, images, mail, nlp, pages, rss, seed, translate

PORT = int(os.environ.get("PORT") or os.environ.get("PRISME_PORT") or "8765")
PUBLIC = os.environ.get("PRISME_MODE") == "public"     # production : ni contenu ni compte de démonstration
SITE_URL = (os.environ.get("PRISME_SITE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
            or (f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}" if os.environ.get("RAILWAY_PUBLIC_DOMAIN") else "")).rstrip("/")
REFRESH_MINUTES = int(os.environ.get("PRISME_REFRESH_MINUTES", "30"))
MAX_BODY = 1024 * 1024
WEB = os.path.join(db.ROOT, "web")
CONN = db.ThreadConn()
ROUTES = []
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


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


_hits = defaultdict(deque)
_hits_lock = threading.Lock()


def limit(bucket, key, max_calls, seconds):
    """Limitation de débit en mémoire (suffisante pour une instance unique)."""
    now = time.monotonic()
    with _hits_lock:
        if len(_hits) > 20000:
            _hits.clear()
        q = _hits[(bucket, key)]
        while q and q[0] < now - seconds:
            q.popleft()
        if len(q) >= max_calls:
            raise ApiError(429, "Trop de tentatives : merci de patienter quelques instants.")
        q.append(now)


def token_key(token):
    """Seule l'empreinte du jeton est conservée : une fuite de la base n'ouvre aucune session."""
    return hashlib.sha256(token.encode()).hexdigest()


def http_url(value):
    v = str(value or "").strip()
    if v and not v.lower().startswith(("http://", "https://")):
        raise ApiError(400, "Le lien doit commencer par http:// ou https://")
    return v or None


def public_user(u):
    return {k: u[k] for k in ("id", "username", "email", "display_name", "role", "persona", "font_scale", "high_contrast",
                              "theme", "simple_mode", "preferred_lang", "diversity_ratio", "email_verified", "created_at")} if u else None


# =====================================================================
#  Authentification
# =====================================================================
def verification_on():
    """En démonstration locale le code s'affiche à l'écran ; en production il faut un service d'envoi."""
    return mail.enabled() or not PUBLIC


def clean_email(value):
    email = str(value or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError(400, "Adresse e-mail invalide.")
    return email


def _code_hash(email, purpose, code):
    return hashlib.sha256(f"{email}|{purpose}|{code}".encode()).hexdigest()


def _check_code(email, purpose, code):
    """Un code est valable 15 minutes, pour 5 essais au plus, et ne sert qu'une fois."""
    row = db.row(CONN, "SELECT * FROM email_codes WHERE email=? AND purpose=?", (email, purpose))
    bad = ApiError(400, "Code incorrect ou expiré. Demandez-en un nouveau.")
    if not row or row["expires_at"] < db.now_str() or row["attempts"] >= 5:
        raise bad
    if not hmac.compare_digest(row["code_hash"], _code_hash(email, purpose, str(code or "").strip())):
        CONN.execute("UPDATE email_codes SET attempts=attempts+1 WHERE email=? AND purpose=?", (email, purpose))
        CONN.commit()
        raise bad
    CONN.execute("DELETE FROM email_codes WHERE email=? AND purpose=?", (email, purpose))


@route("POST", "/api/email/code")
def email_code(req, body, user):
    """Envoie un code à l'adresse. La réponse est la même que le compte existe ou non."""
    if not verification_on():
        raise ApiError(503, "La vérification par e-mail n'est pas encore activée.")
    email, purpose = clean_email(body.get("email")), body.get("purpose")
    if purpose not in ("register", "reset"):
        raise ApiError(400, "Demande invalide.")
    limit("code-ip", req.ip, 20, 600)
    limit("code-email", email, 3, 600)
    exists = db.scalar(CONN, "SELECT 1 FROM users WHERE email=?", (email,))
    if bool(exists) != (purpose == "reset"):
        return {"sent": True}
    code = f"{secrets.randbelow(1000000):06d}"
    with db._lock:
        CONN.execute("INSERT OR REPLACE INTO email_codes(email, purpose, code_hash, expires_at) VALUES (?,?,?,?)",
                     (email, purpose, _code_hash(email, purpose, code), db.to_str(db.now() + timedelta(minutes=15))))
        CONN.commit()
    if not mail.enabled():
        return {"sent": True, "demo_code": code}
    action = "créer votre compte" if purpose == "register" else "choisir un nouveau mot de passe"
    try:
        mail.send(email, f"Votre code Prisme : {code}", f"Bonjour,\n\nVotre code pour {action} sur Prisme est : {code}\n\n"
                  "Il est valable 15 minutes. Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n")
    except Exception:
        traceback.print_exc()
        raise ApiError(502, "L'e-mail n'a pas pu être envoyé. Réessayez dans quelques minutes.")
    return {"sent": True}


def _new_username(email):
    """L'identifiant interne est déduit de l'e-mail : le visiteur n'a rien à inventer."""
    base = re.sub(r"[^a-z0-9_.-]", "", email.split("@")[0])[:24]
    base = base if len(base) >= 3 else f"lecteur{base}"
    name, n = base, 1
    while db.scalar(CONN, "SELECT 1 FROM users WHERE username=?", (name,)):
        n += 1
        name = f"{base}{n}"
    return name


@route("POST", "/api/register")
@db.write
def register(req, body, user):
    limit("register", req.ip, 30, 600)
    need(body, "email", "password", "display_name")
    email = clean_email(body["email"])
    if len(str(body["password"])) < 8:
        raise ApiError(400, "Le mot de passe doit contenir au moins 8 caractères.")
    display_name = str(body["display_name"]).strip()[:80]
    if db.row(CONN, "SELECT id FROM users WHERE email=?", (email,)):
        raise ApiError(409, "Un compte existe déjà avec cet e-mail. Connectez-vous ou utilisez « Mot de passe oublié ».")
    checked = verification_on()
    if checked:
        _check_code(email, "register", body.get("code"))
    h, salt = seed.hash_password(body["password"])
    uid = CONN.execute("INSERT INTO users(username, email, display_name, password_hash, salt, email_verified) VALUES (?,?,?,?,?,?)",
                       (_new_username(email), email, display_name, h, salt, int(checked))).lastrowid
    cats = {r["slug"]: r["id"] for r in db.rows(CONN, "SELECT * FROM categories")}
    for slug in body.get("interests") or []:
        if slug in cats:
            CONN.execute("INSERT OR IGNORE INTO interests VALUES (?,?,1.0)", (uid, cats[slug]))
    CONN.execute("INSERT INTO notifications(user_id, kind, message) VALUES (?, 'systeme', ?)",
                 (uid, "Bienvenue sur Prisme ! Ajoutez des alertes par mots-clés pour être notifié(e)."))
    CONN.commit()
    return _open_session(uid)


@route("POST", "/api/password/reset")
@db.write
def password_reset(req, body, user):
    """Aucun mot de passe n'est jamais envoyé : le lecteur prouve qu'il reçoit ses e-mails, puis en choisit un nouveau."""
    if not verification_on():
        raise ApiError(503, "La vérification par e-mail n'est pas encore activée.")
    limit("reset", req.ip, 20, 600)
    email = clean_email(body.get("email"))
    if len(str(body.get("new_password", ""))) < 8:
        raise ApiError(400, "Le mot de passe doit contenir au moins 8 caractères.")
    u = db.row(CONN, "SELECT id FROM users WHERE email=?", (email,))
    if not u:
        raise ApiError(400, "Code incorrect ou expiré. Demandez-en un nouveau.")
    _check_code(email, "reset", body.get("code"))
    h, salt = seed.hash_password(body["new_password"])
    CONN.execute("UPDATE users SET password_hash=?, salt=?, email_verified=1 WHERE id=?", (h, salt, u["id"]))
    CONN.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
    CONN.commit()
    return _open_session(u["id"])


def _open_session(uid):
    token = secrets.token_urlsafe(32)
    CONN.execute("INSERT INTO sessions(token, user_id, expires_at) VALUES (?,?,?)",
                 (token_key(token), uid, db.to_str(db.now() + timedelta(days=7))))
    CONN.commit()
    return {"token": token, "user": public_user(db.row(CONN, "SELECT * FROM users WHERE id=?", (uid,)))}


@route("POST", "/api/login")
@db.write
def login(req, body, user):
    need(body, "username", "password")
    name = str(body["username"])[:200]
    limit("login", req.ip, 30, 60)
    limit("login-user", name.lower(), 10, 60)
    u = db.row(CONN, "SELECT * FROM users WHERE username=? OR email=?", (name, name.strip().lower()))
    if not u or not seed.check_password(body["password"], u["password_hash"], u["salt"]):
        raise ApiError(401, "Identifiant ou mot de passe incorrect.")
    return _open_session(u["id"])


@route("POST", "/api/demo-login")
@db.write
def demo_login(req, body, user):
    """Connexion en un clic aux personas : uniquement en mode démonstration local."""
    if PUBLIC:
        raise ApiError(404, "Route inconnue.")
    u = db.row(CONN, "SELECT id FROM users WHERE username=? AND (persona IS NOT NULL OR username='admin')", (str(body.get("username")),))
    if not u:
        raise ApiError(404, "Profil de démonstration introuvable.")
    return _open_session(u["id"])


@route("GET", "/api/config")
def config(req, q, user):
    return {"demo_logins": not PUBLIC, "refresh_minutes": REFRESH_MINUTES if PUBLIC else None, "email_verification": verification_on()}


@route("POST", "/api/logout", "user")
@db.write
def logout(req, body, user):
    CONN.execute("DELETE FROM sessions WHERE user_id=? AND token=?", (user["id"], token_key(req.token)))
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
    if "email" in body:
        body["email"] = clean_email(body["email"])
        if db.row(CONN, "SELECT id FROM users WHERE email=? AND id<>?", (body["email"], user["id"])):
            raise ApiError(409, "Cette adresse e-mail est déjà utilisée.")
        if body["email"] != user["email"]:
            sets.append("email_verified=0")   # la nouvelle adresse n'a pas été vérifiée
    changed_password = False
    if body.get("new_password"):
        if len(str(body["new_password"])) < 8:
            raise ApiError(400, "Le nouveau mot de passe doit contenir au moins 8 caractères.")
        limit("password", user["id"], 10, 600)
        if not seed.check_password(body.get("current_password", ""), user["password_hash"], user["salt"]):
            raise ApiError(403, "Mot de passe actuel incorrect.")
        h, salt = seed.hash_password(body["new_password"])
        sets += ["password_hash=?", "salt=?"]; vals += [h, salt]
        changed_password = True
    if sets:
        CONN.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*vals, user["id"]))
        if changed_password:   # les autres appareils sont déconnectés
            CONN.execute("DELETE FROM sessions WHERE user_id=? AND token<>?", (user["id"], token_key(req.token)))
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
    items = db.rows(CONN, """SELECT s.*, c.name category_name, (SELECT COUNT(*) FROM articles a WHERE a.source_id=s.id) articles
                             FROM sources s LEFT JOIN categories c ON c.id=s.default_category ORDER BY s.is_demo, s.name""")
    if not (user and user["role"] == "admin"):
        for it in items:
            it.pop("last_error", None)
    return items


@route("POST", "/api/sources", "admin")
def add_source(req, body, user):
    need(body, "name", "feed_url")
    if not str(body["feed_url"]).startswith(("http://", "https://")):
        raise ApiError(400, "L'URL du flux doit commencer par http:// ou https://")
    try:
        items = rss.parse_feed(rss.fetch(body["feed_url"]))
    except Exception:
        raise ApiError(400, "Flux RSS illisible ou inaccessible.")
    with db._lock:
        return _insert_source(body, items, user)


def _insert_source(body, items, user):
    cat = db.scalar(CONN, "SELECT id FROM categories WHERE slug=?", (body.get("category"),))
    sid = CONN.execute("""INSERT INTO sources(name, website, feed_url, country, language, kind, default_category, reliability, certified, reliability_note)
                          VALUES (?,?,?,?,?,?,?,?,?,?)""",
                       (body["name"], body.get("website"), body["feed_url"], body.get("country"), body.get("language", "fr"),
                        body.get("kind", "web"), cat, 70, 0, None)).lastrowid
    db.log_change(CONN, user["username"], "source", sid, "ajout", body["name"])
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
    db.log_change(CONN, user["username"], "source", int(sid), "modification", json.dumps(body, ensure_ascii=False))
    CONN.commit()
    return db.row(CONN, "SELECT * FROM sources WHERE id=?", (int(sid),))


@route("DELETE", r"/api/sources/(\d+)", "admin")
@db.write
def delete_source(req, q, user, sid):
    CONN.execute("DELETE FROM sources WHERE id=? AND is_demo=0", (int(sid),))
    db.log_change(CONN, user["username"], "source", int(sid), "suppression")
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


@route("GET", "/api/recall")
def recall(req, q, user):
    return {"recall": editorial.recall_for(qv(q, "category"))}


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
    if qv(q, "source") and not str(qv(q, "source")).isdigit():
        raise ApiError(400, "Source invalide.")
    if qv(q, "author"):
        where.append("a.author LIKE ?"); params.append(f"%{qv(q, 'author')}%")
    if qv(q, "from"):
        where.append("date(a.published_at)>=date(?)"); params.append(qv(q, "from"))
    if qv(q, "to"):
        where.append("date(a.published_at)<=date(?)"); params.append(qv(q, "to"))
    if qv(q, "dedup") == "1":
        where.append("a.is_cluster_lead=1")
    order = {"date": "a.published_at DESC", "ancien": "a.published_at ASC", "fiabilite": "s.reliability DESC, a.published_at DESC",
             "verification": "COALESCE(cl.source_count, 1) DESC, a.published_at DESC"}.get(qv(q, "sort", "date"), "a.published_at DESC")
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
    out["source"] = db.row(CONN, "SELECT name, website, country, language, kind, reliability, certified, is_demo, reliability_note FROM sources WHERE id=?", (a["source_id"],))
    out["path"] = pages.article_path(a)
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
    res = engine.summarize(CONN, int(aid), min(int(qv(q, "n", 4)), 8))
    if res is None:
        raise ApiError(404, "Article introuvable.")
    return res


@route("POST", r"/api/articles/(\d+)/verify", "admin")
def reverify(req, body, user, aid):
    res = engine.verify_article(CONN, int(aid))
    return {**res, "claims": engine.get_verification(CONN, int(aid))}


@route("GET", r"/api/articles/(\d+)/translate")
def translate_article(req, q, user, aid):
    a = _article(aid)
    dst = qv(q, "lang", "fr" if a["language"] != "fr" else "en")
    if dst not in ("fr", "en", "es", "de", "ar", "pt"):
        raise ApiError(400, "Langue non prise en charge.")
    if not db.row(CONN, "SELECT 1 FROM translations WHERE article_id=? AND lang=?", (a["id"], dst)):
        limit("translate", req.ip, 30, 60)   # le service externe de traduction a un quota
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
    limit("share", req.ip, 60, 60)
    CONN.execute("INSERT INTO shares(user_id, article_id, channel) VALUES (?,?,?)", (user["id"] if user else None, int(aid), str(body.get("channel", "lien"))[:20]))
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
    color = str(body.get("color", "#0ea5e9"))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ApiError(400, "Couleur invalide.")
    try:
        fid = CONN.execute("INSERT INTO folders(user_id, name, color) VALUES (?,?,?)", (user["id"], str(body["name"]).strip()[:80], color)).lastrowid
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
        CONN.execute("INSERT OR IGNORE INTO alerts(user_id, keyword) VALUES (?,?)", (user["id"], str(body["keyword"]).strip()[:60]))
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
    limit("report", req.ip, 20, 600)
    need(body, "article_id", "reason", "description")
    if body["reason"] not in REASONS:
        raise ApiError(400, "Motif de signalement invalide.")
    body["description"] = str(body["description"])
    if len(body["description"].strip()) < 10:
        raise ApiError(400, "Merci de décrire l'erreur (10 caractères minimum).")
    if not db.scalar(CONN, "SELECT 1 FROM articles WHERE id=?", (int(body["article_id"]),)):
        raise ApiError(404, "Article introuvable.")
    body["evidence_url"] = http_url(body.get("evidence_url"))
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
    db.log_change(CONN, user["username"], "signalement", int(rid), status, body.get("correction_note") or body.get("admin_response") or "")
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
        "users": s("SELECT COUNT(*) FROM users") if user and user["role"] == "admin" else None, "claims": s("SELECT COUNT(*) FROM claims"),
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
_refresh_guard = threading.Lock()


def _refresh_job():
    if not _refresh_guard.acquire(blocking=False):
        return
    REFRESH["running"] = True
    try:
        REFRESH["last"] = rss.refresh_all(CONN)
        _anon_cache.clear()
        images.warm(CONN)
        _prewarm()
    except Exception:
        traceback.print_exc()
        REFRESH["last"] = {"error": "La collecte a échoué, voir les journaux du serveur."}
    finally:
        REFRESH["running"] = False
        _refresh_guard.release()
        CONN.release()


def _prewarm():
    """Calcule d'avance ce que le premier visiteur va demander."""
    rubrics = [f"/api/feed?mode=pour_vous&category={r['slug']}&media=&offset=0&limit=24" for r in db.rows(CONN, "SELECT slug FROM categories")]
    for path in ("/api/feed?mode=pour_vous&category=&media=&offset=0&limit=24", *rubrics, "/api/trends", "/api/stats", "/api/categories", "/api/config"):
        handle("GET", path, {}, lambda n: b"", "127.0.0.1")


def scheduler():
    """Collecte au démarrage puis à intervalle régulier."""
    while True:
        _refresh_job()
        time.sleep(max(REFRESH_MINUTES, 5) * 60)


@route("POST", "/api/refresh", "admin")
def refresh(req, body, user):
    if REFRESH["running"]:
        return {"running": True, "message": "Une collecte est déjà en cours."}
    threading.Thread(target=_refresh_job, daemon=True).start()
    return {"running": True, "message": "Collecte des flux RSS lancée."}


@route("GET", "/api/refresh")
def refresh_status(req, q, user):
    return REFRESH


@route("GET", "/healthz")
def healthz(req, q, user):
    last = db.row(CONN, "SELECT finished_at, sources_ok, sources_ko FROM fetch_log WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1")
    return {"status": "ok", "articles": db.scalar(CONN, "SELECT COUNT(*) FROM articles"), "last_fetch": last, "collecting": REFRESH["running"]}


@route("GET", "/api/admin/changes", "admin")
def admin_changes(req, q, user):
    return db.rows(CONN, "SELECT * FROM change_log ORDER BY id DESC LIMIT 50")


@route("POST", "/api/admin/recluster", "admin")
def admin_recluster(req, body, user):
    res = engine.recluster(CONN)
    with db._lock:
        CONN.execute("UPDATE articles SET verification_status='en_attente'")
        CONN.commit()
    res["verified"] = engine.verify_pending(CONN, 5000)
    db.log_change(CONN, user["username"], "corpus", None, "recalcul", f"{res['clusters']} sujets")
    CONN.commit()
    return res


@route("GET", "/api/admin/users", "admin")
def admin_users(req, q, user):
    return db.rows(CONN, """SELECT u.id, u.username, u.display_name, u.email, u.role, u.persona, u.created_at,
                            (SELECT COUNT(*) FROM reading_history h WHERE h.user_id=u.id) lectures,
                            (SELECT COUNT(*) FROM favorites f WHERE f.user_id=u.id) favoris,
                            (SELECT COUNT(*) FROM reports r WHERE r.user_id=u.id) signalements
                            FROM users u ORDER BY u.id""")


# =====================================================================
#  Cœur HTTP (commun au serveur local et à l'entrée WSGI de production)
# =====================================================================
class Request:
    def __init__(self, headers, ip):
        self.headers, self.ip, self.token = headers, ip, None


SECURITY_HEADERS = [
    ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: http: data:; "
                                "media-src 'self' https: http:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"),
    ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"), ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
]
if PUBLIC:
    SECURITY_HEADERS.append(("Strict-Transport-Security", "max-age=31536000"))
TEXT_TYPES = ("text/", "application/javascript", "application/json", "application/xml", "image/svg")
_template = None
# Réponses identiques pour tous les visiteurs non connectés : calculées une seule fois par période.
ANON_CACHED = {"/api/feed", "/api/trends", "/api/stats", "/api/digest", "/api/categories", "/api/config", "/api/sources"}
ANON_TTL = 300    # vidé à chaque collecte
_anon_cache = {}


def _user_of(req):
    auth = req.headers.get("authorization", "")
    req.token = auth[7:] if auth.startswith("Bearer ") else None
    if not req.token:
        return None
    return db.row(CONN, """SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                           WHERE s.token=? AND s.expires_at > ?""", (token_key(req.token), db.now_str()))


def _api(method, url, req, read_body):
    for m, rx, auth, fn in ROUTES:
        match = rx.match(url.path)
        if m != method or not match:
            continue
        try:
            user = _user_of(req)
            if auth and not user:
                raise ApiError(401, "Connexion requise pour cette fonctionnalité.")
            if auth == "admin" and user["role"] != "admin":
                raise ApiError(403, "Réservé aux administrateurs.")
            if method in ("POST", "PUT"):
                try:
                    n = int(req.headers.get("content-length") or 0)
                except ValueError:
                    raise ApiError(400, "Requête invalide.")
                if n > MAX_BODY or n < 0:
                    raise ApiError(413, "Requête trop volumineuse.")
                try:
                    arg = json.loads(read_body(n).decode("utf-8")) if n else {}
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise ApiError(400, "Requête invalide : corps JSON UTF-8 attendu.")
                if not isinstance(arg, dict):
                    raise ApiError(400, "Requête invalide : objet JSON attendu.")
            else:
                arg = parse_qs(url.query)
            key = f"{url.path}?{url.query}" if method == "GET" and not req.headers.get("authorization") and url.path in ANON_CACHED else None
            if key:
                hit = _anon_cache.get(key)
                if hit and hit[0] > time.monotonic():
                    return 200, hit[1], None, None
            res = fn(req, arg, user, *match.groups())
            if key:
                if len(_anon_cache) > 300:
                    _anon_cache.clear()
                res = json.dumps(res, ensure_ascii=False, default=str).encode("utf-8")
                _anon_cache[key] = (time.monotonic() + ANON_TTL, res)
            if isinstance(res, tuple):
                ctype, body, fname = res
                return 200, body, ctype + "; charset=utf-8", fname
            return 200, res, None, None
        except ApiError as e:
            return e.status, {"error": str(e)}, None, None
        except sqlite3.IntegrityError:
            return 409, {"error": "Référence invalide ou valeur déjà utilisée."}, None, None
        except (ValueError, TypeError):
            return 400, {"error": "Paramètre invalide."}, None, None
        except Exception:
            traceback.print_exc()    # le détail reste dans les journaux, jamais dans la réponse
            return 500, {"error": "Une erreur interne est survenue. Merci de réessayer."}, None, None
    return 404, {"error": "Route inconnue."}, None, None


def _site(headers):
    if SITE_URL:
        return SITE_URL
    return f"{headers.get('x-forwarded-proto', 'http')}://{headers.get('host', f'127.0.0.1:{PORT}')}"


def _public_feed(category=""):
    """Le fil du visiteur non connecté, avec la même adresse et le même cache que l'interface."""
    url = urlparse(f"/api/feed?mode=pour_vous&category={category}&media=&offset=0&limit=24")
    return json.loads(_api("GET", url, Request({}, "127.0.0.1"), None)[1])


def _page(path, headers):
    global _template
    if _template is None or not PUBLIC:
        with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
            _template = f.read()
    site = _site(headers)
    found = pages.render(CONN, path, site, _public_feed)
    status, ctx = found if found else (404, pages.not_found(site))
    return status, pages.fill_template(_template, ctx, CONN).encode("utf-8")


def _static(path, headers):
    """Fichier de web/ uniquement, avec cache validé par ETag. Retourne None s'il n'existe pas."""
    full = os.path.realpath(os.path.join(WEB, path.lstrip("/")))
    if os.path.commonpath([os.path.realpath(WEB), full]) != os.path.realpath(WEB) or not os.path.isfile(full) or full.endswith("index.html"):
        return None
    st = os.stat(full)
    etag = f'"{int(st.st_mtime)}-{st.st_size}"'
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype.endswith("javascript"):
        ctype += "; charset=utf-8"
    cache = "public, max-age=31536000, immutable" if "/fonts/" in path else "public, max-age=0, must-revalidate"
    if headers.get("if-none-match") == etag:
        return 304, b"", ctype, [("ETag", etag), ("Cache-Control", cache)]
    extra = [("ETag", etag), ("Cache-Control", cache), ("Accept-Ranges", "bytes")]
    m = re.fullmatch(r"bytes=(\d+)-(\d*)", headers.get("range", ""))
    if m:   # les lecteurs vidéo des téléphones lisent le fichier par morceaux
        start, end = int(m.group(1)), min(int(m.group(2) or st.st_size - 1), st.st_size - 1)
        if start > end:
            return 416, b"", ctype, [("Content-Range", f"bytes */{st.st_size}")]
        with open(full, "rb") as f:
            f.seek(start)
            return 206, f.read(end - start + 1), ctype, extra + [("Content-Range", f"bytes {start}-{end}/{st.st_size}")]
    with open(full, "rb") as f:
        return 200, f.read(), ctype, extra


def _image(article_id, width):
    """Copie allégée de la photo d'un article déjà collecté : aucune adresse externe n'est acceptée en paramètre."""
    url = db.scalar(CONN, "SELECT image_url FROM articles WHERE id=?", (article_id,))
    if not rss.safe_url(url):
        return 404, b"", "text/plain; charset=utf-8", [("Cache-Control", "no-store")]
    data = images.get(url, width)
    if data is None:
        return 302, b"", "text/plain; charset=utf-8", [("Location", url), ("Cache-Control", "no-store")]
    return 200, data, "image/webp", [("Cache-Control", "public, max-age=604800, immutable")]


def handle(method, raw_path, headers, read_body, ip):
    """Traite une requête. Retourne (statut, en-têtes, corps en octets)."""
    url = urlparse(raw_path)
    path = url.path
    req = Request(headers, ip)
    extra, ctype = [("Cache-Control", "no-store")], "application/json; charset=utf-8"
    try:
        if path.startswith("/api/") or path == "/healthz":
            status, res, forced, fname = _api("GET" if method == "HEAD" else method, url, req, read_body)
            ctype = forced or ctype
            if status == 200 and path in ANON_CACHED and not headers.get("authorization"):
                extra = [("Cache-Control", "private, max-age=30"), ("Vary", "Authorization")]
            body = res if isinstance(res, bytes) else (res.encode("utf-8") if isinstance(res, str) else json.dumps(res, ensure_ascii=False, default=str).encode("utf-8"))
            if fname:
                extra.append(("Content-Disposition", f'attachment; filename="{fname}"'))
        elif method not in ("GET", "HEAD"):
            status, body = 405, b'{"error": "Methode non autorisee."}'
        elif re.fullmatch(r"/img/\d+-\d+\.webp", path):
            aid, width = re.findall(r"\d+", path)
            status, body, ctype, extra = _image(int(aid), int(width))
        elif path == "/robots.txt":
            status, body, ctype = 200, pages.robots(_site(headers)).encode("utf-8"), "text/plain; charset=utf-8"
            extra = [("Cache-Control", "public, max-age=3600")]
        elif path == "/sitemap.xml":
            status, body, ctype = 200, pages.sitemap(CONN, _site(headers)).encode("utf-8"), "application/xml; charset=utf-8"
            extra = [("Cache-Control", "public, max-age=3600")]
        else:
            found = _static(path, headers) if "." in path.rsplit("/", 1)[-1] else None
            if found:
                status, body, ctype, extra = found
            else:
                status, body = _page(path, headers)
                ctype = "text/html; charset=utf-8"
                extra = [("Cache-Control", "no-cache")]
    except Exception:
        traceback.print_exc()
        status, body = 500, b'{"error": "Une erreur interne est survenue."}'
    finally:
        CONN.release()
    out = [("Content-Type", ctype), *extra, *SECURITY_HEADERS]
    if status == 200 and len(body) > 1024 and ctype.startswith(TEXT_TYPES) and "gzip" in headers.get("accept-encoding", ""):
        body = gzip.compress(body, 5)
        out += [("Content-Encoding", "gzip"), ("Vary", "Accept-Encoding")]
    out.append(("Content-Length", str(len(body))))
    out.append(("Date", email.utils.formatdate(usegmt=True)))
    return status, out, b"" if method == "HEAD" else body


class Handler(BaseHTTPRequestHandler):
    server_version = "Prisme"
    sys_version = ""

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stdout.write("  %s\n" % (fmt % args))

    def _serve(self):
        headers = {k.lower(): v for k, v in self.headers.items()}
        status, out, body = handle(self.command, self.path, headers, self.rfile.read, self.client_address[0])
        self.send_response(status)
        for k, v in out:
            if k != "Date":
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _serve

    def handle(self):
        try:
            super().handle()
        except ConnectionError:
            pass   # le visiteur a fermé la page avant la fin de la réponse


def bootstrap():
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("font/woff2", ".woff2")
    mimetypes.add_type("image/webp", ".webp")
    os.makedirs(os.path.dirname(db.DB_PATH), exist_ok=True)
    first = not os.path.exists(db.DB_PATH)
    db.init_schema(CONN)
    if first or not db.scalar(CONN, "SELECT COUNT(*) FROM categories"):
        if PUBLIC:
            print("  > Création de la base de production (médias réels uniquement)...")
            seed.seed_public(CONN)
        else:
            print("  > Création de la base de données et des données de démonstration...")
            seed.seed(CONN)
            engine.recluster(CONN)
            engine.verify_pending(CONN, 5000)
            engine.check_alerts(CONN)
        CONN.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('status_v2', '1')")
    elif not PUBLIC:
        seed.refresh_demo_dates(CONN)
    if not db.scalar(CONN, "SELECT 1 FROM meta WHERE key='status_v2'"):
        # Base créée avant les statuts de couverture : regroupement et statuts sont recalculés une fois.
        print("  > Mise à jour des regroupements et des statuts...")
        engine.recluster(CONN)
        with db._lock:
            CONN.execute("UPDATE articles SET verification_status='en_attente'")
            CONN.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('status_v2', '1')")
            CONN.commit()
        engine.verify_pending(CONN, 5000)
    if not db.scalar(CONN, "SELECT 1 FROM meta WHERE key='sources_v2'"):
        cats = {r["slug"]: r["id"] for r in db.rows(CONN, "SELECT id, slug FROM categories")}
        for name, site, feed, country, lang, kind, dcat, _rel, _cert in seed.REAL_SOURCES:
            CONN.execute("""INSERT OR IGNORE INTO sources(name, website, feed_url, country, language, kind, default_category, reliability, certified)
                            VALUES (?,?,?,?,?,?,?,70,0)""", (name, site, feed, country, lang, kind, cats.get(dcat)))
        CONN.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('sources_v2', '1')")
    if PUBLIC:
        seed.ensure_admin(CONN, os.environ.get("PRISME_ADMIN_USER"), os.environ.get("PRISME_ADMIN_PASSWORD"))
    else:
        seed.make_demo_audio(os.path.join(WEB, "media", "demo_podcast.wav"))
    CONN.execute("DELETE FROM sessions WHERE expires_at < ?", (db.now_str(),))
    CONN.commit()
    CONN.release()


def main():
    print("=" * 62)
    print("  PRISME — L'actualité comparée, média par média")
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
