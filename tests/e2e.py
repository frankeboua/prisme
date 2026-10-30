"""Parcours navigateur réels (Playwright + Edge). Usage : python tests/e2e.py URL public|demo DOSSIER_CAPTURES"""
import json
import os
import random
import sys

from playwright.sync_api import sync_playwright

BASE, MODE, OUT = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
VIEWS = ["/", "/rubrique/international", "/tendances", "/digest", "/multimedia", "/recherche?q=afrique", "/sources", "/methode", "/projet", "/connexion", "/parametres"]
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("OK   " if ok else "ECHEC"), name, detail if not ok or detail else "")


AUDIT = """() => {
  const q = s => [...document.querySelectorAll(s)];
  return {
    h1: q('h1').filter(e => !e.closest('[hidden]')).length,
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    noLabel: q('input,select,textarea').filter(e => e.type !== 'hidden' && !e.labels?.length && !e.getAttribute('aria-label')).length,
    noName: q('button,a').filter(e => e.offsetParent && e.getAttribute('aria-hidden') !== 'true' && !(e.textContent||'').trim() && !e.getAttribute('aria-label') && !e.getAttribute('title')).length,
    imgNoAlt: q('img:not([alt])').length,
  };
}"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    for label, vp in (("ordinateur", (1440, 900)), ("mobile", (390, 844)), ("tablette", (820, 1100))):
        ctx = b.new_context(viewport={"width": vp[0], "height": vp[1]}, locale="fr-FR")
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append("JS: " + str(e)[:160]))
        # les images distantes peuvent échouer sans que l'application soit en cause
        page.on("console", lambda m: errs.append(m.text[:160]) if m.type == "error" and "ERR_" not in m.text and "Failed to load resource" not in m.text else None)
        for v in VIEWS:
            page.goto(BASE + v, wait_until="networkidle")
            m = page.evaluate(AUDIT)
            check(f"{label} {v}", m["h1"] == 1 and m["overflow"] <= 0 and m["noLabel"] == 0 and m["noName"] == 0 and m["imgNoAlt"] == 0, json.dumps(m))
        for shot in ("/", "/methode"):
            page.goto(BASE + shot, wait_until="networkidle")
            page.screenshot(path=os.path.join(OUT, f"{MODE}_{label}_{shot.strip('/') or 'home'}.png"))
        check(f"{label} aucune erreur console/CSP", not errs, str(sorted(set(errs))[:6]))
        ctx.close()

    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="fr-FR")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append("JS: " + str(e)[:160]))
    page.goto(BASE + "/", wait_until="networkidle")

    # Navigation sans rechargement vers un article puis son sujet
    page.evaluate("window.__spa = 1")
    page.locator(".lead-story h2 a").click()
    page.wait_for_selector(".article h1")
    check("clic sur un article : URL propre", "/article/" in page.url and "#" not in page.url, page.url)
    check("navigation sans rechargement", page.evaluate("window.__spa") == 1)
    page.screenshot(path=os.path.join(OUT, f"{MODE}_article.png"))
    page.wait_for_selector("#toolBody ol, #toolBody .empty, #toolBody .alert-line")
    check("résumé marqué comme automatique", page.locator("#toolBody .badge", has_text="Extraction automatique").count() == 1 or page.locator("#toolBody .empty").count() == 1)
    page.locator("[data-tool=verify]").click()
    check("onglet Recoupement", page.locator("#toolBody h3", has_text="Passages proches").count() == 1)
    page.go_back()
    page.wait_for_selector(".front")
    check("bouton Précédent du navigateur", page.url.rstrip("/") == BASE)

    # Sujet multi-sources
    try:
        page.wait_for_selector(".topic a.go", timeout=8000)
    except Exception:
        pass
    link = page.locator(".topic a.go").first
    if link.count():
        link.click()
        page.wait_for_selector(".cmp-col")
        check("page de comparaison", "/sujet/" in page.url and page.locator(".cmp-col").count() >= 2)
        sources = page.evaluate("new Set([...document.querySelectorAll('.cmp-col')].map(e => e.dataset.pub)).size")
        check("le spectre compte chaque média une seule fois", f"{sources} média" in page.locator(".page-head .spectre").inner_text(), str(sources))
        page.screenshot(path=os.path.join(OUT, f"{MODE}_sujet.png"))
    else:
        check("page de comparaison (aucun sujet multi-sources)", False)

    # Rubrique, recherche, filtre de format, onglets
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator("#rubrics a", has_text="International").click()
    page.wait_for_selector("h1:has-text('International')")
    check("rubrique par clic", "/rubrique/international" in page.url)
    page.fill("#quickQ", "afrique")
    page.press("#quickQ", "Enter")
    page.wait_for_selector("#results .card, #results .empty")
    check("recherche rapide", "/recherche?q=afrique" in page.url and page.locator("#results .card").count() > 0)
    page.locator(".more-filters summary").click()
    page.select_option("select[name=sort]", "verification")
    page.locator("#searchForm button.primary").click()
    page.wait_for_selector("#results .card")
    check("recherche avancée : tri par nombre de médias", "sort=verification" in page.url)
    page.goto(BASE + "/recherche", wait_until="networkidle")
    check("recherche : exemples à cliquer", page.locator("#searchExamples a").count() >= 5)
    page.fill("#searchQ", "cote d'ivoire")
    page.locator("#searchForm button.primary").click()
    page.wait_for_selector("#results .card, #results .empty")
    check("recherche sans accent : résultats trouvés", page.locator("#results .card").count() > 0, page.locator("#results h2").first.inner_text())
    page.locator("input[name=periode][value='7'] + *").count()
    page.locator(".periods label", has_text="7 derniers jours").click()
    page.wait_for_selector("#results .card, #results .empty")
    check("recherche : filtre de période en un clic", "periode=7" in page.url, page.url)
    page.locator("[data-act=textsettings]").click()
    page.locator(".font-choice[data-font=lisible]").click()
    page.wait_for_selector("html[data-font=lisible]")
    check("changement de police immédiat", "Verdana" in page.evaluate("getComputedStyle(document.body).fontFamily"))
    page.keyboard.press("Escape")
    page.reload(wait_until="networkidle")
    check("police conservée après rechargement", page.evaluate("document.documentElement.dataset.font") == "lisible")
    page.locator("[data-act=textsettings]").click()
    page.locator(".font-choice[data-font=prisme]").click()
    page.keyboard.press("Escape")
    page.goto(BASE + "/rubrique/politique", wait_until="networkidle")
    page.locator("#feedList .card h3 a").first.click()
    page.wait_for_selector(".article h1")
    page.locator("[data-tool=translate]").click()
    page.wait_for_selector("#trLang")
    check("plus de 40 langues de traduction", page.locator("#trLang option").count() >= 44, str(page.locator("#trLang option").count()))
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator("[data-mode=recent]").click()
    page.wait_for_selector("[data-mode=recent].active")
    page.wait_for_selector("#feedList .card")
    check("onglet Les plus récents", True)
    page.select_option("#mediaSel", "podcast")
    page.wait_for_selector('#feedList .card'); page.wait_for_timeout(800)
    check("filtre par format", page.evaluate("document.querySelector(\"#mediaSel\").value") == "podcast" and page.locator("#feedList .card").count() > 0)
    page.select_option("#mediaSel", "")
    page.locator("[data-mode=pour_vous]").click()

    # Pourquoi / Signaler / Partager
    page.goto(BASE + "/recherche?q=afrique", wait_until="networkidle")
    page.locator(".card [data-act=report]").first.click()
    page.wait_for_selector("#repForm")
    page.fill("#repForm textarea", "Test automatique de signalement, à ignorer.")
    page.fill("#repForm input[name=evidence_url]", "https://exemple.org/preuve")
    page.locator("#repForm button.primary").click()
    page.wait_for_selector(".toast:has-text('transmis')")
    check("signalement envoyé avec message de confirmation", True)
    page.locator(".card [data-act=share]").first.click()
    page.wait_for_selector("#postBox")
    check("fenêtre de partage", True)
    page.keyboard.press("Escape")
    check("fermeture au clavier (Échap)", page.locator("#modal").is_hidden())

    # Tiroir de navigation
    page.locator("#menuBtn").click()
    check("menu ouvert", page.locator("#sidebar.open").count() == 1 and page.locator("#nav a").count() >= 10)
    page.keyboard.press("Escape")
    check("menu fermé au clavier", page.locator("#sidebar.open").count() == 0)

    # Clavier : le premier Tab donne le lien d'évitement
    page.goto(BASE + "/rubrique/sport", wait_until="networkidle")
    page.wait_for_selector(".recall")
    check("rappel sourcé dans la rubrique sport", page.locator(".recall li").count() == 2 and page.locator(".recall a[href^='https://']").count() == 4)
    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_selector("#feedList .card")
    cards = page.locator("#feedList .card")
    n = cards.count()
    check("chaque carte montre la rubrique et l'heure exacte", n > 0 and cards.locator(".kicker").count() >= n and cards.locator("time").count() >= n,
          page.locator("#feedList .card time").first.inner_text())
    check("date et heure lisibles", ":" in page.locator("#feedList .card time").first.inner_text())
    check("photos servies par Prisme", page.evaluate("[...document.images].filter(i => /^https?:/.test(i.getAttribute('src')) ).length") == 0)
    page.goto(BASE + "/recherche?q=afrique", wait_until="networkidle")
    broken = page.evaluate("[...document.images].filter(i => i.src.includes('/illustrations/') && i.complete && !i.naturalWidth).length")
    check("illustrations affichées", broken == 0 and page.evaluate("[...document.images].length") > 0, str(broken))
    page.goto(BASE + "/multimedia", wait_until="networkidle")
    ready = page.evaluate("new Promise(r => { const v = document.querySelector('#introVideo'); if (!v) return r(-1); v.preload = 'auto'; if (v.readyState >= 1) return r(v.duration); v.onloadedmetadata = () => r(v.duration); v.onerror = () => r(-2); v.load(); })")
    check("vidéo de présentation lisible", ready > 10, str(ready))
    page.goto(BASE + "/", wait_until="networkidle")
    page.keyboard.press("Tab")
    check("lien d'évitement au clavier", page.evaluate("document.activeElement.className") == "skip")

    # Pages d'erreur et anciens liens
    page.goto(BASE + "/#/tendances", wait_until="networkidle")
    check("ancien lien #/tendances redirigé", page.url.endswith("/tendances"), page.url)
    r = page.goto(BASE + "/nexiste-pas", wait_until="networkidle")
    check("page inexistante : code 404 et message", r.status == 404 and page.locator("h1", has_text="introuvable").count() == 1)
    r = page.goto(BASE + "/sujet/999999", wait_until="networkidle")
    check("sujet inexistant : code 404 et message", r.status == 404 and page.locator("h1", has_text="introuvable").count() == 1)

    # Compte
    page.goto(BASE + "/connexion", wait_until="networkidle")
    has_demo = page.locator("[data-act=demo]").count() > 0
    check("profils de démo présents seulement en démo", has_demo == (MODE == "demo"))
    check("aucun mot de passe affiché", "admin123" not in page.content() and "demo123" not in page.content())
    page.fill("#loginForm input[name=username]", "personne")
    page.fill("#loginForm input[name=password]", "mauvais")
    page.locator("#loginForm button.primary").click()
    page.wait_for_selector(".toast.err")
    check("mauvais mot de passe : message compréhensible", "incorrect" in page.locator(".toast.err").first.inner_text())
    page.locator("[data-act=forgot]").click()
    page.wait_for_selector("#modal h2:has-text('oublié')")
    check("section mot de passe oublié", page.locator("#modal h2").count() == 1)
    page.keyboard.press("Escape")
    page.locator("[data-act=authtab][data-t=register]").click()
    name = f"e2e{random.randint(1000, 999999)}"
    page.fill("#regForm input[name=display_name]", "Testeur Auto")
    page.fill("#regForm input[name=email]", f"{name}@exemple.org")
    page.fill("#regForm input[name=password]", "motdepasse-e2e")
    check("inscription sans identifiant à inventer", page.locator("#regForm input[name=username]").count() == 0)
    check("liste des pays de résidence", page.locator("#regForm select[name=country] option").count() > 190)
    page.select_option("#regForm select[name=country]", "Côte d'Ivoire")
    page.fill("#regForm input[name=password_confirm]", "pas-le-meme")
    page.locator("#regForm button.primary").click()
    page.wait_for_selector(".toast.err:has-text('identiques')")
    check("confirmation du mot de passe : erreur si différent", page.locator("#regForm").is_visible())
    page.fill("#regForm input[name=password_confirm]", "motdepasse-e2e")
    page.locator("#regForm button.primary").click()
    if MODE == "demo":
        page.wait_for_selector("#codeBox:not([hidden])")
        page.fill("#regForm input[name=code]", page.locator("#codeInfo").inner_text().rsplit(" ", 1)[1].strip(". "))
        page.locator("#regForm button.primary").click()
    page.wait_for_selector(".user-chip")
    check("création de compte", True)
    page.wait_for_selector("#feedList .card, .front")
    page.goto(BASE + "/recherche?q=afrique", wait_until="networkidle")
    page.locator(".card [data-act=fav]").first.click()
    page.wait_for_selector(".toast:has-text('favoris')")
    page.goto(BASE + "/favoris", wait_until="networkidle")
    check("favori enregistré et retrouvé", page.locator(".card").count() == 1)
    page.goto(BASE + "/veille", wait_until="networkidle")
    page.fill("#alertForm input", "Afrique")
    page.locator("#alertForm button").click()
    page.wait_for_selector("text=Alerte ajoutée")
    check("alerte par mot-clé", True)
    page.goto(BASE + "/parametres", wait_until="networkidle")
    page.select_option("#theme", "dark")
    page.locator("#saveA").click()
    page.wait_for_selector("html[data-theme=dark]")
    page.goto(BASE + "/", wait_until="networkidle")
    page.screenshot(path=os.path.join(OUT, f"{MODE}_sombre.png"))
    check("thème sombre", True)
    page.locator(".user-chip").click()
    page.locator("[data-act=logout]").click()
    page.wait_for_selector("#userBox a.btn")
    check("déconnexion", True)

    if MODE == "demo":
        page.goto(BASE + "/connexion", wait_until="networkidle")
        page.locator("[data-act=demo][data-u=admin]").click()
        page.wait_for_selector(".user-chip")
        page.wait_for_timeout(800)
        page.goto(BASE + "/admin", wait_until="networkidle")
        check("administration : tableau de bord", page.locator(".kpi").count() == 4)
        page.screenshot(path=os.path.join(OUT, "demo_admin.png"))
        page.goto(BASE + "/signalements", wait_until="networkidle")
        check("modération accessible", page.locator("form.mod").count() > 0)
        page.goto(BASE + "/recherche?q=URGENT", wait_until="networkidle")
        check("scénario carburant 15 % : badge Chiffres divergents", page.locator(".badge", has_text="Chiffres divergents").count() >= 1)
        page.goto(BASE + "/recherche?q=18%20morts", wait_until="networkidle")
        check("scénario recirculation : badge visible", page.locator(".badge", has_text="recircule").count() >= 1)
        page.goto(BASE + "/connexion", wait_until="networkidle")

    check("aucune erreur JavaScript pendant les parcours", not errs, str(errs[:5]))
    b.close()

print(f"\n{sum(results)}/{len(results)} vérifications réussies")
sys.exit(0 if all(results) else 1)
