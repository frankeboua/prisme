"""Collecteur de flux RSS 2.0 / Atom (agrégation des sources réelles)."""
import hashlib
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

from . import db, nlp

UA = "Prisme-Agregateur/1.1 (lecture de flux RSS publics)"
MAX_FEED_BYTES = 5 * 1024 * 1024
NS = {"atom": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/",
      "content": "http://purl.org/rss/1.0/modules/content/", "dc": "http://purl.org/dc/elements/1.1/",
      "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}


def _date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return db.to_str(d)


def _text(el, path):
    x = el.find(path, NS)
    return (x.text or "").strip() if x is not None and x.text else ""


def _duration(s):
    if not s:
        return None
    parts = [int(p) for p in re.findall(r"\d+", s)]
    if not parts:
        return None
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec if ":" in s else parts[0]


def safe_url(url):
    """N'accepte que des liens http(s) : écarte javascript:, data:, etc. venus d'un flux."""
    url = (url or "").strip()
    return url if url.lower().startswith(("http://", "https://")) else None


def parse_feed(xml_bytes):
    if b"<!ENTITY" in xml_bytes[:4096]:
        raise ValueError("flux refusé : déclaration d'entités XML")
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        enc = it.find("enclosure")
        media_url = enc.get("url") if enc is not None and (enc.get("type") or "").startswith(("audio", "video")) else None
        media_kind = (enc.get("type") or "").split("/")[0] if media_url else None
        img = None
        for p in ("media:content", "media:thumbnail"):
            m = it.find(p, NS)
            if m is not None and m.get("url"):
                img = m.get("url"); break
        if not img and enc is not None and (enc.get("type") or "").startswith("image"):
            img = enc.get("url")
        desc = _text(it, "description")
        if not img:
            m = re.search(r'<img[^>]+src="([^"]+)"', desc)
            img = m.group(1) if m else None
        items.append({
            "guid": _text(it, "guid") or _text(it, "link"), "title": nlp.strip_html(_text(it, "title")),
            "summary": desc, "content": _text(it, "content:encoded"), "url": safe_url(_text(it, "link")),
            "author": _text(it, "dc:creator") or _text(it, "author") or _text(it, "itunes:author"),
            "published_at": _date(_text(it, "pubDate") or _text(it, "dc:date")), "image_url": safe_url(img),
            "media_url": safe_url(media_url), "media_kind": media_kind, "duration": _duration(_text(it, "itunes:duration")),
        })
    for e in root.findall("atom:entry", NS):
        link = e.find("atom:link", NS)
        items.append({
            "guid": _text(e, "atom:id"), "title": nlp.strip_html(_text(e, "atom:title")),
            "summary": _text(e, "atom:summary") or _text(e, "media:group/media:description"),
            "content": _text(e, "atom:content"), "url": safe_url(link.get("href")) if link is not None else None,
            "author": _text(e, "atom:author/atom:name"),
            "published_at": _date(_text(e, "atom:published") or _text(e, "atom:updated")),
            "image_url": None, "media_url": None, "media_kind": None, "duration": None,
        })
    return items


def assert_public_host(url):
    """Empêche d'utiliser la collecte pour sonder le réseau interne du serveur."""
    parts = urllib.parse.urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("adresse de flux invalide")
    for info in socket.getaddrinfo(parts.hostname, parts.port or 80, proto=socket.IPPROTO_TCP):
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("adresse interne refusée")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect)


def fetch(url, timeout=15, max_bytes=MAX_FEED_BYTES):
    assert_public_host(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, */*"})
    with _opener.open(req, timeout=timeout) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("contenu trop volumineux")
    return data


def _media_type(src, it):
    if it["media_kind"] == "audio" or src["kind"] == "podcast":
        return "podcast"
    if it["media_kind"] == "video" or re.search(r"/videos?/|/video-", it["url"] or "") or re.match(r"^\s*(vid[ée]o|replay)\b", it["title"], re.I):
        return "video"
    if src["kind"] == "social":
        return "social"
    return "article"


@db.write
def store(conn, src, items, slug_ids):
    new = 0
    for it in items[:60]:
        if not it["title"]:
            continue
        guid = hashlib.sha1(f"{src['id']}|{it['guid'] or it['url'] or it['title']}".encode()).hexdigest()
        body = nlp.strip_html(it["content"] or it["summary"])
        cat = nlp.classify(it["title"] + " " + body, slug_ids, src["default_category"])
        cur = conn.execute(
            """INSERT OR IGNORE INTO articles(source_id, guid, title, summary, content, url, author, image_url, media_type,
                   media_url, duration_sec, language, category_id, published_at, first_seen_at, word_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (src["id"], guid, it["title"][:400], nlp.strip_html(it["summary"])[:1500], body[:8000], it["url"], it["author"][:120] or None,
             it["image_url"], _media_type(src, it), it["media_url"], it["duration"], src["language"], cat,
             it["published_at"], db.now_str(), len(body.split())))
        new += cur.rowcount
    conn.execute("UPDATE sources SET last_fetched_at=?, last_error=NULL WHERE id=?", (db.now_str(), src["id"]))
    conn.commit()
    return new


def refresh_all(conn, only_id=None):
    """Collecte toutes les sources actives possédant un flux, en parallèle."""
    from . import engine
    sql = "SELECT * FROM sources WHERE active=1 AND feed_url IS NOT NULL" + (" AND id=?" if only_id else "")
    sources = db.rows(conn, sql, (only_id,) if only_id else ())
    slug_ids = {r["slug"]: r["id"] for r in db.rows(conn, "SELECT id, slug FROM categories")}
    log_id = conn.execute("INSERT INTO fetch_log(message) VALUES ('collecte en cours')").lastrowid
    conn.commit()

    def job(src):
        try:
            return src, parse_feed(fetch(src["feed_url"])), None
        except Exception as e:  # réseau indisponible, flux invalide...
            return src, [], str(e)[:200]

    ok = ko = new = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for src, items, err in pool.map(job, sources):
            if err:
                ko += 1
                with db._lock:
                    conn.execute("UPDATE sources SET last_error=? WHERE id=?", (err, src["id"]))
                    conn.commit()
            else:
                ok += 1
                new += store(conn, src, items, slug_ids)
    stats = engine.recluster(conn) if new else {}
    verified = engine.verify_pending(conn, 5000) if new else 0
    if new:
        engine.refresh_statuses(conn)
    notified = engine.check_alerts(conn) if new else 0
    with db._lock:
        conn.execute("UPDATE fetch_log SET finished_at=?, sources_ok=?, sources_ko=?, new_articles=?, message=? WHERE id=?",
                     (db.now_str(), ok, ko, new, f"{verified} analysés, {notified} notifications", log_id))
        conn.commit()
    return {"sources_ok": ok, "sources_ko": ko, "new_articles": new, "verified": verified,
            "notifications": notified, **stats}
