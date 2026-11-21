"""Pages rendues côté serveur : ce que lisent les moteurs de recherche et les navigateurs sans JavaScript.

L'application monopage prend ensuite le relais sur les mêmes URL.
"""
import json
import os
import re
import unicodedata
from datetime import timedelta
from html import escape

from . import db, editorial, engine, nlp

TAGLINE = "L'actualité comparée, média par média"
DEFAULT_DESC = ("Prisme réunit les articles de plusieurs médias sur un même événement, montre ce qu'ils ont en commun "
                "et où ils divergent, et renvoie toujours vers la source originale.")
PRIVATE = ("/veille", "/favoris", "/notifications", "/signalements", "/admin", "/parametres", "/connexion", "/recherche", "/avis")
STATIC_PAGES = {
    "/tendances": ("Tendances : les sujets les plus couverts", "Les événements repris par le plus de médias en ce moment, et les mots-clés dominants."),
    "/digest": ("Le digest du jour", "L'essentiel de l'actualité en quelques minutes, résumé à partir de plusieurs sources citées."),
    "/multimedia": ("Podcasts et vidéos", "Les podcasts et vidéos des médias suivis par Prisme."),
    "/videos": ("Vidéos en plein écran", "Les vidéos des médias suivis par Prisme, à faire défiler en plein écran."),
    "/republications": ("Republications des lecteurs", "Les informations que les lecteurs de Prisme ont choisi de republier, avec leur avis."),
    "/projet": ("Le projet Prisme", "Pourquoi Prisme existe, comment il fonctionne et qui le réalise."),
    "/influence": ("Médias en progression : l'influence des médias ivoiriens et internationaux", "Les médias dont l'influence grandit : premiers à publier, repris par les autres, suivis par les lecteurs. Méthode et poids affichés."),
    "/verifications": ("Vérification des faits : vrai, faux, trompeur", "Les conclusions des fact-checkers professionnels et de la rédaction Prisme sur les informations qui circulent, avec leurs sources."),
    "/local": ("Près de chez vous : l'actualité de Côte d'Ivoire", "L'actualité ivoirienne comparée entre médias ivoiriens et internationaux, pays par pays."),
}


# Jeton de la Google Search Console (propriété https://prisme-srbh.onrender.com, méthode « Balise HTML ») ; la variable d'environnement le remplace.
SEARCH_CONSOLE_TOKEN = "Q8taO-zxJsgitjTsz8BftTkHVyx2vyCWkXKTa-xptu0"

def slug(text):
    t = unicodedata.normalize("NFD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:70]


def article_path(a):
    return f"/article/{a['id']}-{slug(a['title'])}"


def topic_path(cid, label):
    return f"/sujet/{cid}-{slug(label)}"


def _when(s):
    d = db.parse(s)
    return d.strftime("%d/%m/%Y à %H:%M UTC") if d else "date inconnue"


def _iso(s):
    d = db.parse(s)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


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
        out.append(f'<li><span class="kicker">{escape(a.get("category_name") or "Actualité")}</span><h3><a href="{escape(link)}">{escape(a["title"])}</a></h3>'
                   f'<p class="small muted">{escape(a["source_name"])} · <time datetime="{_iso(a["published_at"]) or ""}">{_when(a["published_at"])}</time>'
                   f'{f" · {n} médias" if n > 1 else ""}</p><p>{excerpt}</p></li>')
    return '<ul class="ssr-list">' + "".join(out) + "</ul>"


def _picture(a, big):
    """Mêmes attributs que l'interface : la photo déjà chargée n'est pas téléchargée deux fois."""
    if not a.get("image_url"):
        cat = a.get("category_slug") or "actualite"
        return f'<img src="/illustrations/{escape(cat, True)}-{a["id"] % 3}.svg" alt=""><span class="illu-tag">Illustration</span>'
    sizes = "(max-width: 820px) 100vw, 66vw" if big else "(max-width: 820px) 100vw, 320px"
    load = 'fetchpriority="high"' if big else 'loading="lazy"'
    return (f'<img src="/img/{a["id"]}-{960 if big else 480}.webp" srcset="/img/{a["id"]}-480.webp 480w, /img/{a["id"]}-960.webp 960w" '
            f'sizes="{sizes}" alt="" {load} decoding="async">')


def _front(items):
    """La une complète dès le HTML : elle s'affiche sans attendre le JavaScript."""
    if len(items) < 5:
        return _list(items)
    lead = next((a for a in items if a.get("image_url")), items[0])
    rest = [a for a in items if a is not lead]

    def meta(a):
        return (f'<div class="byline"><strong>{escape(a["source_name"])}</strong><time datetime="{_iso(a["published_at"]) or ""}">{_when(a["published_at"])}</time></div>')

    def kicker(a):
        return f'<span class="kicker">{escape(a.get("category_name") or "Actualité")}</span>'

    sides = "".join(f'<article class="side-story">{kicker(a)}<h3><a href="{escape(article_path(a), True)}">{escape(a["title"])}</a></h3>{meta(a)}</article>' for a in rest[:4])
    return (f'<section class="front" aria-label="À la une"><article class="lead-story"><a class="frame" href="{escape(article_path(lead), True)}" tabindex="-1" aria-hidden="true">{_picture(lead, True)}</a>'
            f'{kicker(lead)}<h2 class="lead-title"><a href="{escape(article_path(lead), True)}">{escape(lead["title"])}</a></h2><p class="sum">{escape(lead.get("summary") or "")}</p>{meta(lead)}</article>'
            f'<div class="side-col">{sides}</div></section><div class="sec-title"><h2>Le fil</h2></div>{_list(rest[4:])}')


def _recall(slug):
    r = editorial.recall_for(slug)
    if not r:
        return ""
    lines = "".join(f"<li><b>{escape(i['match'])}</b> ({escape(i['competition'])}, {i['date']}) : "
                    + ", ".join(f'<a rel="noopener" href="{escape(x["url"], True)}">{escape(x["name"])}</a>' for x in i["sources"]) + "</li>" for i in r["items"])
    return f"<h2>{escape(r['title'])}</h2><ul>{lines}</ul>"


def _sources_jsonld(arts, site):
    return [{"@type": "NewsArticle", "headline": a["title"][:110], "url": a["url"],
             "datePublished": _iso(a["published_at"]), "articleSection": a.get("category_name"),
             "publisher": {"@type": "Organization", "name": a.get("source_name") or a.get("source")}}
            for a in arts if a.get("url")]


def render(conn, path, site, feed=lambda category="": {"items": []}):
    """Retourne (statut, contexte de page) pour une URL publique, ou None si elle n'existe pas."""
    home = {"@context": "https://schema.org", "@type": "WebSite", "name": "Prisme", "url": site + "/",
            "potentialAction": {"@type": "SearchAction", "target": site + "/recherche?q={q}", "query-input": "required name=q"}}
    base = dict(title=f"Prisme — {TAGLINE}", desc=DEFAULT_DESC, canonical=site + path, robots="index,follow", image=None, jsonld=None, main="")

    if path == "/":
        items = feed("")["items"]
        return 200, {**base, "jsonld": home, "image": next((a["image_url"] for a in items if a.get("image_url")), None),
                     "main": f'<h1 class="sr">Prisme : {escape(TAGLINE.lower())}</h1>{_front(items)}'}

    m = re.fullmatch(r"/article/(\d+)(-[a-z0-9-]*)?", path)
    if m:
        a = db.row(conn, engine.FEED_SQL.replace("WHERE s.active=1", "WHERE 1=1").format(where=" AND a.id=?"), (int(m.group(1)),))
        if not a:
            return None
        text = nlp.strip_html(a.get("content") or a.get("summary") or "")
        link = f'<p><a rel="noopener" href="{escape(a["url"])}">Lire l\'article original sur {escape(a["source_name"])}</a></p>' if a["url"] else ""
        # Un extrait seul n'apporte rien de plus que l'original : ces pages ne sont pas proposées à l'indexation.
        section = a.get("category_name") or "Actualité"
        ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": a["title"][:110], "datePublished": _iso(a["published_at"]), "articleSection": section,
              "mainEntityOfPage": site + article_path(a), "publisher": {"@type": "Organization", "name": a["source_name"]}}
        if a["url"]:
            ld["isBasedOn"] = a["url"]
        if a["image_url"]:
            ld["image"] = a["image_url"]
        return 200, {**base, "title": f"{a['title'][:70]} — {a['source_name']} | Prisme", "desc": text[:155] or DEFAULT_DESC,
                     "canonical": site + article_path(a), "robots": "noindex,follow", "image": a["image_url"], "jsonld": ld,
                     "og_type": "article", "published": _iso(a["published_at"]), "section": section,
                     "main": f"<span class=\"kicker\">{escape(section)}</span><h1>{escape(a['title'])}</h1><p class=\"small muted\">{escape(a['source_name'])} · publié le <time datetime=\"{_iso(a['published_at']) or ''}\">{_when(a['published_at'])}</time></p><p>{escape(text[:600])}</p>{link}"}

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
        return 200, {**base, "title": f"{c['label'][:60]} : ce qu'en disent {c['source_count']} médias | Prisme" if c["source_count"] > 1 else f"{c['label'][:70]} | Prisme",
                     "desc": f"Comparaison de la couverture par {', '.join(names[:4])}."[:155],
                     "canonical": site + topic_path(c["id"], c["label"]), "robots": "index,follow" if c["source_count"] > 1 else "noindex,follow",
                     "jsonld": ld, "image": next((a["image_url"] for a in arts if a["image_url"]), None), "og_type": "article",
                     "published": _iso(c["last_published"]), "section": next((a["category_name"] for a in arts if a.get("category_name")), None),
                     "main": f"<h1>{escape(c['label'])}</h1><h2>Résumé automatique</h2><p class=\"small muted\">Phrases extraites telles quelles des articles cités ci-dessous.</p><ol>{summary}</ol><h2>Les {len(arts)} articles</h2><ul>{lines}</ul>"}

    m = re.fullmatch(r"/rubrique/([a-z]+)", path)
    if m:
        cat = db.row(conn, "SELECT * FROM categories WHERE slug=?", (m.group(1),))
        if not cat:
            return None
        return 200, {**base, "title": f"{cat['name']} : l'actualité comparée | Prisme", "desc": f"Les derniers sujets de la rubrique {cat['name']}, comparés entre plusieurs médias.",
                     "main": f"<span class=\"kicker\">Rubrique</span><h1>{escape(cat['name'])}</h1>{_recall(cat['slug'])}{_front(feed(cat['slug'])['items'])}"}

    if path == "/sources":
        srcs = db.rows(conn, "SELECT name, website, country, kind FROM sources WHERE active=1 ORDER BY name")
        lines = "".join(f"<li>{escape(s['name'])} ({escape(s['country'] or '')})</li>" for s in srcs)
        return 200, {**base, "title": "Les médias suivis par Prisme", "desc": "La liste des médias dont Prisme lit les flux RSS publics.",
                     "main": f"<h1>Les médias suivis</h1><ul>{lines}</ul>"}

    if path == "/methode":
        return 200, {**base, "title": "Notre méthode : ce que Prisme affirme et n'affirme pas", "desc": "Comment Prisme regroupe les articles, ce que signifient ses statuts et les limites de l'outil.",
                     "main": "<h1>Notre méthode</h1><p>Prisme compare la couverture d'un événement par plusieurs médias, puis confirme ou infirme l'information à l'aide du fact-checking et du recoupement par au moins trois sources fiables.</p>"
                             "<h2>La vérification en quatre étapes</h2><ol><li>Vérifier la source : média, statut, pays, auteur et article original.</li>"
                             "<li>Vérifier la crédibilité de la source : six indicateurs mesurés sur ses articles reçus.</li>"
                             "<li>Croiser au moins trois sources fiables qui traitent le même événement.</li>"
                             "<li>Authentifier l'information : date d'origine, écarts entre médias, signalements, outils de fact-checking.</li></ol>"
                             "<h2>Qui décide qu'une information est vraie ou fausse ?</h2><p>Jamais l'algorithme seul. Un verdict « vrai », « faux » ou « trompeur » vient "
                             "soit d'un fact-checker professionnel (Franceinfo Vrai ou fake, Libération CheckNews, France 24 Les Observateurs, RFI, Le Monde Les Décodeurs), "
                             "dont l'analyse est liée, soit de la rédaction Prisme, avec une explication et des sources obligatoires.</p>"}

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
            '<meta property="og:site_name" content="Prisme">', f'<meta property="og:type" content="{ctx.get("og_type", "website")}">', '<meta property="og:locale" content="fr_FR">',
            f'<meta property="og:title" content="{escape(ctx["title"], True)}">',
            f'<meta property="og:description" content="{escape(ctx["desc"], True)}">',
            f'<meta property="og:url" content="{escape(ctx["canonical"], True)}">',
            f'<meta name="twitter:card" content="{"summary_large_image" if ctx["image"] else "summary"}">']
    if ctx.get("published"):
        meta.append(f'<meta property="article:published_time" content="{ctx["published"]}">')
    if ctx.get("section"):
        meta.append(f'<meta property="article:section" content="{escape(ctx["section"], True)}">')
    if ctx["image"]:
        meta.append(f'<meta property="og:image" content="{escape(ctx["image"], True)}">')
    if ctx["jsonld"]:
        data = json.dumps(ctx["jsonld"], ensure_ascii=False).replace("<", "\\u003c")
        meta.append(f'<script type="application/ld+json">{data}</script>')
    default = SEARCH_CONSOLE_TOKEN if os.environ.get("PRISME_MODE") == "public" else ""
    verification = os.environ.get("PRISME_GOOGLE_SITE_VERIFICATION", default).strip()
    if verification:   # balise fournie par la Google Search Console (méthode « Balise HTML »)
        meta.append(f'<meta name="google-site-verification" content="{escape(verification, True)}">')
    return (tpl.replace("<!--TITLE-->", escape(ctx["title"])).replace("<!--META-->", "\n  ".join(meta))
            .replace("<!--MAIN-->", f'<div data-ssr="1">{ctx["main"]}</div>' if ctx["main"] else "").replace("<!--RUBRICS-->", rubrics_html(conn)))


def sitemap(conn, site):
    urls = [(site + "/", None), (site + "/tendances", None), (site + "/digest", None), (site + "/sources", None), (site + "/methode", None), (site + "/projet", None), (site + "/local", None), (site + "/verifications", None), (site + "/influence", None)]
    urls += [(f"{site}/rubrique/{c['slug']}", None) for c in db.rows(conn, "SELECT slug FROM categories")]
    # Seuls les sujets comparant plusieurs médias apportent une valeur propre.
    urls += [(site + topic_path(c["id"], c["label"]), c["last_published"]) for c in db.rows(
        conn, "SELECT id, label, last_published FROM clusters WHERE source_count>1 ORDER BY last_published DESC LIMIT 1000")]
    body = "".join(f"<url><loc>{escape(u)}</loc>" + (f"<lastmod>{d[:10]}</lastmod>" if d else "") + "</url>" for u, d in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>\n'


def robots(site):
    return f"User-agent: *\nDisallow: /api/\nDisallow: /recherche\nDisallow: /connexion\nDisallow: /admin\n\nSitemap: {site}/sitemap.xml\n"
