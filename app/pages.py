"""Pages rendues côté serveur : ce que lisent les moteurs de recherche et les navigateurs sans JavaScript.

L'application monopage prend ensuite le relais sur les mêmes URL.
"""
import json
import re
import unicodedata
from datetime import timedelta
from html import escape

from . import db, engine, nlp

TAGLINE = "L'actualité comparée, média par média"
DEFAULT_DESC = ("Prisme réunit les articles de plusieurs médias sur un même événement, montre ce qu'ils ont en commun "
                "et où ils divergent, et renvoie toujours vers la source originale.")
PRIVATE = ("/veille", "/favoris", "/notifications", "/signalements", "/admin", "/parametres", "/connexion", "/recherche")
STATIC_PAGES = {
    "/tendances": ("Tendances : les sujets les plus couverts", "Les événements repris par le plus de médias en ce moment, et les mots-clés dominants."),
    "/digest": ("Le digest du jour", "L'essentiel de l'actualité en quelques minutes, résumé à partir de plusieurs sources citées."),
    "/multimedia": ("Podcasts et vidéos", "Les podcasts et vidéos des médias suivis par Prisme."),
    "/projet": ("Le projet Prisme", "Pourquoi Prisme existe, comment il fonctionne et qui le réalise."),
}


def slug(text):
    t = unicodedata.normalize("NFD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:70]


def article_path(a):
    return f"/article/{a['id']}-{slug(a['title'])}"


def topic_path(cid, label):
    return f"/sujet/{cid}-{slug(label)}"


def _when(s):
    d = db.parse(s)
    return d.strftime("%d/%m/%Y") if d else "date inconnue"


def _items(conn, where, params=(), limit=30, order="a.published_at DESC"):
    sql = engine.FEED_SQL.format(where=" AND " + where) + f" ORDER BY {order} LIMIT {int(limit)}"
    return db.rows(conn, sql, params)


def _list(items):
    if not items:
        return '<p class="muted">Les articles arrivent : la première collecte des flux est en cours.</p>'
    out = []
    for a in items:
        n = a.get("source_count") or 1
        link = topic_path(a["cluster_id"], a["title"]) if n > 1 else article_path(a)
        excerpt = escape(nlp.strip_html(a.get("summary") or "")[:220])
        out.append(f'<li><h3><a href="{escape(link)}">{escape(a["title"])}</a></h3>'
                   f'<p class="small muted">{escape(a["source_name"])} · {_when(a["published_at"])}'
                   f'{f" · {n} médias" if n > 1 else ""}</p><p>{excerpt}</p></li>')
    return '<ul class="ssr-list">' + "".join(out) + "</ul>"


def _sources_jsonld(arts, site):
    return [{"@type": "NewsArticle", "headline": a["title"][:110], "url": a["url"],
             "datePublished": (a["published_at"] or "").replace(" ", "T") + "Z",
             "publisher": {"@type": "Organization", "name": a.get("source_name") or a.get("source")}}
            for a in arts if a.get("url")]


def render(conn, path, site):
    """Retourne (statut, contexte de page) pour une URL publique, ou None si elle n'existe pas."""
    home = {"@context": "https://schema.org", "@type": "WebSite", "name": "Prisme", "url": site + "/",
            "potentialAction": {"@type": "SearchAction", "target": site + "/recherche?q={q}", "query-input": "required name=q"}}
    base = dict(title=f"Prisme — {TAGLINE}", desc=DEFAULT_DESC, canonical=site + path, robots="index,follow", image=None, jsonld=None, main="")

    if path == "/":
        lead = _items(conn, "a.is_cluster_lead=1", limit=30, order="COALESCE(cl.source_count,1) DESC, a.published_at DESC")
        recent = [a for a in lead if (db.parse(a["published_at"]) or db.now()) >= db.now() - timedelta(days=3)] or lead
        return 200, {**base, "jsonld": home, "image": next((a["image_url"] for a in recent if a["image_url"]), None),
                     "main": f"<h1>Prisme : {escape(TAGLINE.lower())}</h1><p class=\"lead\">{escape(DEFAULT_DESC)}</p><h2>À la une</h2>{_list(recent[:24])}"}

    m = re.fullmatch(r"/article/(\d+)(-[a-z0-9-]*)?", path)
    if m:
        a = db.row(conn, engine.FEED_SQL.replace("WHERE s.active=1", "WHERE 1=1").format(where=" AND a.id=?"), (int(m.group(1)),))
        if not a:
            return None
        text = nlp.strip_html(a.get("content") or a.get("summary") or "")
        link = f'<p><a rel="noopener" href="{escape(a["url"])}">Lire l\'article original sur {escape(a["source_name"])}</a></p>' if a["url"] else ""
        # Un extrait seul n'apporte rien de plus que l'original : ces pages ne sont pas proposées à l'indexation.
        return 200, {**base, "title": f"{a['title'][:70]} — {a['source_name']} | Prisme", "desc": text[:155] or DEFAULT_DESC,
                     "canonical": site + article_path(a), "robots": "noindex,follow", "image": a["image_url"],
                     "main": f"<h1>{escape(a['title'])}</h1><p class=\"small muted\">{escape(a['source_name'])} · publié le {_when(a['published_at'])}</p><p>{escape(text[:600])}</p>{link}"}

    m = re.fullmatch(r"/sujet/(\d+)(-[a-z0-9-]*)?", path)
    if m:
        c = db.row(conn, "SELECT * FROM clusters WHERE id=?", (int(m.group(1)),))
        if not c:
            return None
        arts = db.rows(conn, "SELECT * FROM v_articles WHERE cluster_id=? ORDER BY published_at", (c["id"],))
        lines = "".join(f'<li><b>{escape(a["source_name"])}</b> ({_when(a["published_at"])}) : '
                        + (f'<a rel="noopener" href="{escape(a["url"])}">{escape(a["title"])}</a>' if a["url"] else escape(a["title"]))
                        + "</li>" for a in arts)
        s = engine.summarize(conn, c["lead_article_id"], 4) if c["lead_article_id"] else None
        summary = "".join(f"<li>{escape(x['text'])}</li>" for x in (s or {}).get("sentences", []))
        names = sorted({a["source_name"] for a in arts})
        ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": c["label"], "mainEntity": {
            "@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": x} for i, x in enumerate(_sources_jsonld(arts, site))]}}
        return 200, {**base, "title": f"{c['label'][:60]} : ce qu'en disent {len(names)} médias | Prisme" if len(names) > 1 else f"{c['label'][:70]} | Prisme",
                     "desc": f"Comparaison de la couverture par {', '.join(names[:4])}."[:155],
                     "canonical": site + topic_path(c["id"], c["label"]), "robots": "index,follow" if len(names) > 1 else "noindex,follow",
                     "jsonld": ld, "image": next((a["image_url"] for a in arts if a["image_url"]), None),
                     "main": f"<h1>{escape(c['label'])}</h1><h2>Résumé automatique</h2><p class=\"small muted\">Phrases extraites telles quelles des articles cités ci-dessous.</p><ol>{summary}</ol><h2>Les {len(arts)} articles</h2><ul>{lines}</ul>"}

    m = re.fullmatch(r"/rubrique/([a-z]+)", path)
    if m:
        cat = db.row(conn, "SELECT * FROM categories WHERE slug=?", (m.group(1),))
        if not cat:
            return None
        return 200, {**base, "title": f"{cat['name']} : l'actualité comparée | Prisme", "desc": f"Les derniers sujets de la rubrique {cat['name']}, comparés entre plusieurs médias.",
                     "main": f"<h1>{escape(cat['name'])}</h1>{_list(_items(conn, 'a.is_cluster_lead=1 AND c.slug=?', (cat['slug'],)))}"}

    if path == "/sources":
        srcs = db.rows(conn, "SELECT name, website, country, kind FROM sources WHERE active=1 ORDER BY name")
        lines = "".join(f"<li>{escape(s['name'])} ({escape(s['country'] or '')})</li>" for s in srcs)
        return 200, {**base, "title": "Les médias suivis par Prisme", "desc": "La liste des médias dont Prisme lit les flux RSS publics.",
                     "main": f"<h1>Les médias suivis</h1><ul>{lines}</ul>"}

    if path == "/methode":
        return 200, {**base, "title": "Notre méthode : ce que Prisme affirme et n'affirme pas", "desc": "Comment Prisme regroupe les articles, ce que signifient ses statuts et les limites de l'outil.",
                     "main": "<h1>Notre méthode</h1><p>Prisme mesure la couverture d'un événement par plusieurs médias. Il ne certifie pas la véracité des faits.</p>"}

    if path in STATIC_PAGES:
        t, d = STATIC_PAGES[path]
        return 200, {**base, "title": f"{t} | Prisme", "desc": d, "main": f"<h1>{escape(t)}</h1><p>{escape(d)}</p>"}

    if path in PRIVATE or path.startswith(("/favoris", "/signalements")):
        return 200, {**base, "title": "Prisme", "robots": "noindex,follow", "canonical": site + path, "main": ""}
    return None


def not_found(site):
    return dict(title="Page introuvable | Prisme", desc=DEFAULT_DESC, canonical=site + "/", robots="noindex", image=None, jsonld=None,
                main='<h1>Page introuvable</h1><p>Cette adresse n\'existe pas ou plus. <a href="/">Retour à l\'accueil</a></p>')


def rubrics_html(conn):
    return "".join(f'<a href="/rubrique/{escape(c["slug"])}">{escape(c["name"])}</a>' for c in db.rows(conn, "SELECT slug, name FROM categories ORDER BY id"))


def fill_template(tpl, ctx, conn):
    meta = [f'<meta name="description" content="{escape(ctx["desc"], True)}">',
            f'<meta name="robots" content="{ctx["robots"]}">',
            f'<link rel="canonical" href="{escape(ctx["canonical"], True)}">',
            '<meta property="og:site_name" content="Prisme">', '<meta property="og:type" content="website">', '<meta property="og:locale" content="fr_FR">',
            f'<meta property="og:title" content="{escape(ctx["title"], True)}">',
            f'<meta property="og:description" content="{escape(ctx["desc"], True)}">',
            f'<meta property="og:url" content="{escape(ctx["canonical"], True)}">',
            f'<meta name="twitter:card" content="{"summary_large_image" if ctx["image"] else "summary"}">']
    if ctx["image"]:
        meta.append(f'<meta property="og:image" content="{escape(ctx["image"], True)}">')
    if ctx["jsonld"]:
        data = json.dumps(ctx["jsonld"], ensure_ascii=False).replace("<", "\\u003c")
        meta.append(f'<script type="application/ld+json">{data}</script>')
    return (tpl.replace("<!--TITLE-->", escape(ctx["title"])).replace("<!--META-->", "\n  ".join(meta))
            .replace("<!--MAIN-->", ctx["main"]).replace("<!--RUBRICS-->", rubrics_html(conn)))


def sitemap(conn, site):
    urls = [(site + "/", None), (site + "/tendances", None), (site + "/digest", None), (site + "/sources", None), (site + "/methode", None), (site + "/projet", None)]
    urls += [(f"{site}/rubrique/{c['slug']}", None) for c in db.rows(conn, "SELECT slug FROM categories")]
    # Seuls les sujets comparant plusieurs médias apportent une valeur propre.
    urls += [(site + topic_path(c["id"], c["label"]), c["last_published"]) for c in db.rows(
        conn, "SELECT id, label, last_published FROM clusters WHERE source_count>1 ORDER BY last_published DESC LIMIT 1000")]
    body = "".join(f"<url><loc>{escape(u)}</loc>" + (f"<lastmod>{d[:10]}</lastmod>" if d else "") + "</url>" for u, d in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>\n'


def robots(site):
    return f"User-agent: *\nDisallow: /api/\nDisallow: /recherche\nDisallow: /connexion\nDisallow: /admin\n\nSitemap: {site}/sitemap.xml\n"
