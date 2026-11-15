"""Extraction (web scraping) des médias qui ne publient pas de flux RSS.

Règles suivies :
- le collecteur s'identifie honnêtement (même agent que pour les flux RSS) et ne contourne jamais un refus (403, robots.txt) ;
- robots.txt est respecté, ainsi que son délai entre deux requêtes (Crawl-delay), et au moins une seconde par défaut ;
- seuls les métadonnées publiques de l'article sont gardées (titre, chapô publié par le média, image, date, auteur) et le
  lien vers l'original : Prisme renvoie toujours le lecteur vers le site du média, il ne recopie pas l'article.
"""
import html
import json
import re
import threading
import time
import urllib.parse
import urllib.robotparser

from . import nlp, rss

MAX_PER_RUN = 12            # articles nouveaux lus par source et par collecte
LISTING_MAX_BYTES = 12 * 1024 * 1024
_robots, _robots_lock = {}, threading.Lock()


def robots_for(base):
    """Règles robots.txt d'un site, gardées une heure."""
    with _robots_lock:
        hit = _robots.get(base)
        if hit and hit[0] > time.monotonic():
            return hit[1]
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(rss.fetch(base + "/robots.txt", timeout=15, max_bytes=500_000).decode("utf-8", "replace").splitlines())
    except Exception:
        rp.parse([])            # pas de robots.txt lisible : rien n'est interdit
    with _robots_lock:
        _robots[base] = (time.monotonic() + 3600, rp)
    return rp


def _base(url):
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def allowed(url):
    return robots_for(_base(url)).can_fetch(rss.UA, url)


def delay(url):
    try:
        return max(1.0, float(robots_for(_base(url)).crawl_delay(rss.UA) or 0))
    except (TypeError, ValueError):
        return 1.0


def article_links(listing_html, listing_url, pattern):
    """Liens d'articles de la page de liste : même site, adresse conforme au motif du média, sans doublon, dans l'ordre."""
    rx = re.compile(pattern)
    base, seen, out = _base(listing_url), set(), []
    for href in re.findall(r'href="([^"#]+)"', listing_html):
        url = urllib.parse.urljoin(listing_url, html.unescape(href)).split("?")[0].rstrip("/")
        if _base(url).replace("://www.", "://") != base.replace("://www.", "://") or url in seen:
            continue
        if rx.search(urllib.parse.urlparse(url).path):
            seen.add(url)
            out.append(url)
    # Quand l'adresse contient la date (/2026/11/14/…), les articles les plus récents passent en premier :
    # certaines pages d'accueil mettent en avant d'anciens articles.
    dated = lambda u: (m.group(0) if (m := re.search(r"/(20\d\d)/(\d\d)/(\d\d)/", u)) else "")
    return sorted(out, key=dated, reverse=True) if any(dated(u) for u in out) else out


def _meta(page, *names):
    for n in names:
        for rx in (rf'<meta[^>]+(?:property|name|itemprop)="{re.escape(n)}"[^>]*content="([^"]*)"',
                   rf'<meta[^>]+content="([^"]*)"[^>]*(?:property|name|itemprop)="{re.escape(n)}"'):
            m = re.search(rx, page, re.I)
            if m and m.group(1).strip():
                return html.unescape(m.group(1)).strip()
    return ""


def _jsonld(page):
    """Champs utiles des données structurées schema.org (NewsArticle) que publient la plupart des sites de presse."""
    out = {}
    for block in re.findall(r'(?s)<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for d in stack:
            if not isinstance(d, dict) or not re.search(r"Article|NewsArticle|BlogPosting|Report", str(d.get("@type", ""))):
                continue
            out.setdefault("title", d.get("headline"))
            out.setdefault("date", d.get("datePublished") or d.get("dateCreated"))
            out.setdefault("summary", d.get("description"))
            a = d.get("author")
            a = a[0] if isinstance(a, list) and a else a
            out.setdefault("author", a.get("name") if isinstance(a, dict) else a if isinstance(a, str) else None)
            img = d.get("image")
            img = img[0] if isinstance(img, list) and img else img
            out.setdefault("image", img.get("url") if isinstance(img, dict) else img if isinstance(img, str) else None)
    return {k: v for k, v in out.items() if v}


BODY_CLASSES = ("post-text", "entry-content", "article-content", "article-body", "article__body", "post-content", "td-post-content", "content-article", "story-body")


def excerpt(page, size=300):
    """Début du texte de l'article, pris dans son bloc principal (pas dans les menus ni les colonnes latérales)."""
    region = ""
    for cls in BODY_CLASSES:
        m = re.search(r'<(?:div|section|article)[^>]+class="(?:[^"]*\s)?' + re.escape(cls) + r'(?:\s[^"]*)?"', page)
        if m:
            region = page[m.end(): m.end() + 30000]
            break
    if not region:
        m = re.search(r"(?s)<article[^>]*>(.*?)</article>", page)
        region = m.group(1) if m else ""
    # Découpe sur les ouvertures de paragraphe : certains sites ne ferment pas leurs balises <p>.
    paras = [nlp.strip_html(re.split(r"</p>|<div|</div>|<h\d", chunk)[0]) for chunk in re.split(r"<p(?:\s[^>]*)?>", region)[1:]]
    return " ".join(x for x in paras if len(x) > 60)[:size]


def parse_article(page, url):
    """Métadonnées d'une page d'article, au même format que les éléments d'un flux RSS."""
    ld = _jsonld(page)
    title = ld.get("title") or _meta(page, "og:title", "twitter:title")
    if not title:
        m = re.search(r"(?s)<h1[^>]*>(.*?)</h1>", page) or re.search(r"(?s)<title>(.*?)</title>", page)
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""
    summary = ld.get("summary") or _meta(page, "og:description", "description", "twitter:description")
    if not summary:     # pas de chapô publié : court extrait du début de l'article (le lien renvoie vers le texte complet)
        summary = excerpt(page)
    date = ld.get("date") or _meta(page, "article:published_time", "datePublished", "pubdate", "date")
    if not date:
        m = re.search(r'<time[^>]+datetime="([^"]+)"', page)
        date = m.group(1) if m else ""
    author = (ld.get("author") or _meta(page, "author", "article:author") or "").strip()
    if re.fullmatch(r"(?i)[a-z0-9_.-]*(?:admin|webmaster|editor|user)[a-z0-9_.-]*", author):
        author = ""     # identifiant technique (« admin », « ladminassop »…) : ce n'est pas une signature de journaliste
    return {"guid": url, "title": nlp.strip_html(title)[:400], "summary": nlp.strip_html(summary)[:1500], "content": "",
            "url": rss.safe_url(url), "author": author[:120],
            "published_at": rss._date(date), "image_url": rss.safe_url(ld.get("image") or _meta(page, "og:image", "twitter:image")),
            "media_url": None, "media_kind": None, "duration": None}


def collect(src, known_urls=frozenset(), max_new=MAX_PER_RUN):
    """Lit la page de liste du média, puis les articles encore inconnus (au plus max_new), en respectant robots.txt."""
    listing = src["feed_url"]
    if not allowed(listing):
        raise PermissionError("robots.txt interdit la page de liste")
    links = article_links(rss.fetch(listing, timeout=25, max_bytes=LISTING_MAX_BYTES).decode("utf-8", "replace"),
                          listing, src["scrape_pattern"])
    items, pause = [], delay(listing)
    for url in [u for u in links if u not in known_urls][:max_new]:
        if not allowed(url):
            continue
        time.sleep(pause)
        try:
            it = parse_article(rss.fetch(url, timeout=25, max_bytes=LISTING_MAX_BYTES).decode("utf-8", "replace"), url)
        except Exception:
            continue
        if it["title"]:
            items.append(it)
    return items
