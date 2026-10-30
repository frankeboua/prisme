"""Mode production : sécurité, SEO, absence de démonstration, regroupement. Lancer : python -m unittest tests.test_public"""
import unittest

from tests.helpers import call, setup

setup("public")
import server  # noqa: E402
from app import db, engine, nlp, rss  # noqa: E402

server.bootstrap()
CONN = server.CONN
TEXT = "Le gouvernement du Sénégal annonce un plan national pour la pêche artisanale et les ports de Dakar cette semaine."


def add_article(source_id, guid, title, summary, hours=1, url="https://exemple.org/a", image=None):
    with db._lock:
        aid = CONN.execute("""INSERT INTO articles(source_id, guid, title, summary, content, url, image_url, language, published_at, first_seen_at)
                              VALUES (?,?,?,?,?,?,?,'fr',?,?)""", (source_id, guid, title, summary, summary, url, image, db.ago(hours=hours), db.now_str())).lastrowid
        CONN.commit()
    return aid


src = [r["id"] for r in db.rows(CONN, "SELECT id FROM sources WHERE language='fr' ORDER BY id LIMIT 4")]
A1 = add_article(src[0], "g1", "Sénégal : plan national pour la pêche artisanale à Dakar", TEXT, 2, image="https://exemple.org/i.jpg")
A2 = add_article(src[1], "g2", "Dakar : le Sénégal lance un plan national pour la pêche artisanale", TEXT + " Les pêcheurs saluent la mesure.", 3)
A3 = add_article(src[2], "g3", "Plan pêche artisanale au Sénégal : ce que prévoit Dakar", TEXT, 4)
OTHER = add_article(src[3], "g4", "Tennis : victoire surprise en finale du tournoi de Paris", "Une joueuse remporte la finale du tournoi à Paris.", 2)
engine.recluster(CONN)
engine.verify_pending(CONN, 100)


def admin_token():
    return call(server, "POST", "/api/login", {"username": "redaction", "password": "mot-de-passe-de-test"})[2]["token"]


def new_user(name):
    return call(server, "POST", "/api/register", {"username": name, "email": f"{name}@exemple.org", "password": "motdepasse", "display_name": "L"})[2]["token"]


class Case(unittest.TestCase):
    def setUp(self):
        server._hits.clear()


class Production(Case):
    def test_no_demo_content_or_accounts(self):
        self.assertEqual(db.scalar(CONN, "SELECT COUNT(*) FROM articles WHERE is_demo=1"), 0)
        self.assertEqual(db.scalar(CONN, "SELECT COUNT(*) FROM sources WHERE is_demo=1"), 0)
        self.assertIsNone(db.row(CONN, "SELECT id FROM users WHERE username='aminata'"))
        self.assertEqual(call(server, "POST", "/api/login", {"username": "admin", "password": "admin123"})[0], 401)
        self.assertEqual(call(server, "POST", "/api/demo-login", {"username": "redaction"})[0], 404)
        self.assertFalse(call(server, "GET", "/api/config")[2]["demo_logins"])

    def test_no_rating_of_real_media(self):
        rows = db.rows(CONN, "SELECT reliability, certified FROM sources")
        self.assertTrue(all(r["reliability"] == 70 and r["certified"] == 0 for r in rows))
        self.assertNotIn("/100", call(server, "GET", f"/article/{A1}")[2])


class Auth(Case):
    def test_admin_from_environment(self):
        self.assertTrue(admin_token())

    def test_session_token_is_hashed(self):
        self.assertIsNone(db.row(CONN, "SELECT 1 FROM sessions WHERE token=?", (admin_token(),)))

    def test_login_rate_limit(self):
        codes = [call(server, "POST", "/api/login", {"username": "redaction", "password": "x"})[0] for _ in range(12)]
        self.assertIn(429, codes)

    def test_register_validation(self):
        ok = {"username": "lecteur1", "email": "l@exemple.org", "password": "motdepasse", "display_name": "L"}
        self.assertEqual(call(server, "POST", "/api/register", {**ok, "email": "pasunmail"})[0], 400)
        self.assertEqual(call(server, "POST", "/api/register", {**ok, "password": "court"})[0], 400)
        self.assertEqual(call(server, "POST", "/api/register", {**ok, "username": "x y"})[0], 400)
        self.assertEqual(call(server, "POST", "/api/register", ok)[0], 200)
        self.assertEqual(call(server, "POST", "/api/register", ok)[0], 409)

    def test_password_change_requires_current_and_revokes_sessions(self):
        t1 = new_user("lecteur2")
        t2 = call(server, "POST", "/api/login", {"username": "lecteur2", "password": "motdepasse"})[2]["token"]
        self.assertEqual(call(server, "PUT", "/api/me", {"new_password": "nouveaumdp"}, t1)[0], 403)
        self.assertEqual(call(server, "PUT", "/api/me", {"new_password": "nouveaumdp", "current_password": "motdepasse"}, t1)[0], 200)
        self.assertTrue(call(server, "GET", "/api/me", token=t1)[2]["user"])
        self.assertFalse(call(server, "GET", "/api/me", token=t2)[2]["user"])

    def test_email_conflict_is_409(self):
        t = new_user("lecteur3")
        new_user("lecteur4")
        self.assertEqual(call(server, "PUT", "/api/me", {"email": "lecteur4@exemple.org"}, t)[0], 409)

    def test_authorization(self):
        t = new_user("lecteur5")
        self.assertEqual(call(server, "GET", "/api/admin/users", token=t)[0], 403)
        self.assertEqual(call(server, "POST", "/api/refresh", {}, t)[0], 403)
        self.assertEqual(call(server, "POST", f"/api/articles/{A1}/verify", {})[0], 401)
        self.assertEqual(call(server, "GET", "/api/favorites")[0], 401)


class Inputs(Case):
    def test_invalid_params_are_400_without_details(self):
        for path in ("/api/feed?limit=abc", "/api/feed?source=abc", "/api/articles/1/summary?n=abc", "/api/search?source=abc"):
            st, _, body = call(server, "GET", path)
            self.assertEqual(st, 400, path)
            self.assertNotIn("invalid literal", str(body))
        self.assertEqual(call(server, "POST", "/api/login", [1, 2])[0], 400)
        self.assertEqual(call(server, "POST", "/api/reports", {"article_id": "abc", "reason": "autre", "description": "x" * 20})[0], 400)
        self.assertEqual(call(server, "POST", "/api/reports", {"article_id": 999999, "reason": "autre", "description": "x" * 20})[0], 404)
        self.assertEqual(call(server, "GET", "/api/articles/999999/summary")[0], 404)

    def test_body_limit(self):
        st, _, _ = server.handle("POST", "/api/login", {"content-length": str(5_000_000)}, lambda n: b"", "1.1.1.1")
        self.assertEqual(st, 413)

    def test_sql_injection_is_inert(self):
        before = db.scalar(CONN, "SELECT COUNT(*) FROM users")
        for q in ("q=%27%20OR%201%3D1--", "status=x%27%20OR%20%271%27%3D%271", "sort=date%3BDROP%20TABLE%20users", "from=2020%27%29%20OR%201%3D1--"):
            self.assertEqual(call(server, "GET", "/api/search?" + q)[0], 200)
        self.assertEqual(db.scalar(CONN, "SELECT COUNT(*) FROM users"), before)

    def test_javascript_url_rejected(self):
        st, _, _ = call(server, "POST", "/api/reports", {"article_id": A1, "reason": "autre", "description": "description suffisante", "evidence_url": "javascript:alert(1)"})
        self.assertEqual(st, 400)
        self.assertIsNone(rss.safe_url("javascript:alert(1)"))
        self.assertIsNone(rss.safe_url("data:text/html,x"))

    def test_ssrf_blocked(self):
        for u in ("http://127.0.0.1/", "http://169.254.169.254/latest/", "http://10.0.0.5/rss", "file:///etc/passwd"):
            with self.assertRaises(ValueError):
                rss.assert_public_host(u)

    def test_xml_entities_refused(self):
        with self.assertRaises(ValueError):
            rss.parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><rss></rss>')

    def test_path_traversal(self):
        for p in ("/../server.py", "/..%2f..%2fserver.py", "/../database/schema.sql", "/..\\server.py"):
            st, _, body = call(server, "GET", p)
            self.assertEqual(st, 404, p)
            self.assertNotIn('"""PRISME', str(body))


class Headers(Case):
    def test_security_headers(self):
        _, h, _ = call(server, "GET", "/")
        for k in ("content-security-policy", "x-content-type-options", "x-frame-options", "referrer-policy", "strict-transport-security"):
            self.assertIn(k, h)
        self.assertNotIn("unsafe-inline", h["content-security-policy"].split("script-src")[1].split(";")[0])

    def test_static_cache_and_gzip(self):
        st, h, _ = call(server, "GET", "/app.js", headers={"accept-encoding": "gzip"})
        self.assertEqual(st, 200)
        self.assertEqual(h["content-encoding"], "gzip")
        self.assertEqual(call(server, "GET", "/app.js", headers={"if-none-match": h["etag"]})[0], 304)


class Seo(Case):
    def test_home_is_crawlable(self):
        st, _, html = call(server, "GET", "/")
        self.assertEqual(st, 200)
        self.assertIn("plan national pour la pêche", html.lower())
        self.assertIn('rel="canonical"', html)
        self.assertIn('property="og:title"', html)
        self.assertIn('"@type": "WebSite"', html)
        self.assertEqual(html.count("<h1"), 1)

    def test_real_404(self):
        for p in ("/nexiste-pas", "/article/999999", "/sujet/999999", "/rubrique/inconnue"):
            self.assertEqual(call(server, "GET", p)[0], 404, p)

    def test_robots_and_sitemap(self):
        _, h, txt = call(server, "GET", "/robots.txt")
        self.assertTrue(h["content-type"].startswith("text/plain"))
        self.assertIn("Sitemap:", txt)
        self.assertIn("Disallow: /api/", txt)
        _, _, xml = call(server, "GET", "/sitemap.xml")
        self.assertIn("/sujet/", xml)
        self.assertNotIn("/article/", xml)

    def test_article_page_not_indexed_topic_page_indexed(self):
        _, _, art = call(server, "GET", f"/article/{A1}")
        self.assertIn('content="noindex,follow"', art)
        self.assertIn("article original", art)
        cid = db.scalar(CONN, "SELECT cluster_id FROM articles WHERE id=?", (A1,))
        _, _, topic = call(server, "GET", f"/sujet/{cid}")
        self.assertIn('content="index,follow"', topic)
        self.assertIn('"@type": "NewsArticle"', topic)

    def test_escaping_in_rendered_pages(self):
        aid = add_article(src[0], "xss", "<script>alert(1)</script> titre piégé", "résumé <b>gras</b> &lt;img src=x onerror=alert(1)&gt;")
        _, _, html = call(server, "GET", f"/article/{aid}")
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("<img src=x", html)


class Engine(Case):
    def cluster(self, aid):
        return db.scalar(CONN, "SELECT cluster_id FROM articles WHERE id=?", (aid,))

    def test_same_event_grouped_different_event_apart(self):
        self.assertEqual(self.cluster(A1), self.cluster(A2))
        self.assertEqual(self.cluster(A1), self.cluster(A3))
        self.assertNotEqual(self.cluster(A1), self.cluster(OTHER))

    def test_status_describes_coverage(self):
        a = db.row(CONN, engine.FEED_SQL.format(where=" AND a.id=?"), (A1,))
        self.assertEqual(a["verification_status"], "verifie")
        self.assertEqual(engine.status_label(a["verification_status"], a["source_count"]), "Repris par 3 sources")
        o = db.row(CONN, engine.FEED_SQL.format(where=" AND a.id=?"), (OTHER,))
        self.assertEqual(engine.status_label(o["verification_status"], o["source_count"]), "Source unique")

    def test_cluster_ids_stable_across_recluster(self):
        before = self.cluster(A1)
        engine.recluster(CONN)
        self.assertEqual(self.cluster(A1), before)

    def test_old_article_not_merged_with_current_event(self):
        old = add_article(src[3], "old", "Sénégal : plan national pour la pêche artisanale à Dakar", TEXT, 24 * 30)
        engine.recluster(CONN)
        self.assertNotEqual(self.cluster(old), self.cluster(A1))

    def test_rising_toll_is_not_a_contradiction(self):
        self.assertNotEqual(engine._stance("La collision a fait 68 morts selon les autorités", "L'accident a fait au moins 60 morts selon les autorités", 0.5, 70), "contredit")
        self.assertEqual(engine._stance("Une hausse de 5 % du prix du carburant", "Une hausse de 15 % du prix du carburant", 0.5, 70), "contredit")
        self.assertEqual(engine._stance("Une hausse de 5 % du prix", "Le prix connaît une hausse de 5 % dès novembre", 0.5, 70), "soutient")

    def test_rumour_word_alone_is_not_a_denial(self):
        self.assertNotEqual(engine._stance("Ce président semble plus corrompu que les autres", "Etats-Unis : vent de rumeurs à l'approche des élections", 0.37, 70), "contredit")

    def test_summary_only_contains_source_sentences(self):
        s = engine.summarize(CONN, A1, 3)
        corpus = " ".join(r["summary"] for r in db.rows(CONN, "SELECT summary FROM articles WHERE cluster_id=?", (self.cluster(A1),)))
        self.assertTrue(s["sentences"])
        for x in s["sentences"]:
            self.assertIn(x["text"], corpus)
        self.assertTrue(all(r["url"] for r in s["sources"]))

    def test_change_log_on_moderation(self):
        tok = admin_token()
        rid = call(server, "POST", "/api/reports", {"article_id": A1, "reason": "autre", "description": "description suffisante"})[2]["id"]
        self.assertEqual(call(server, "PUT", f"/api/reports/{rid}", {"status": "corrige", "correction_note": "Note"}, tok)[0], 200)
        self.assertTrue(db.row(CONN, "SELECT 1 FROM change_log WHERE entity='signalement' AND entity_id=?", (rid,)))


class Feeds(unittest.TestCase):
    def test_parse_rss_keeps_link_and_date_and_drops_bad_urls(self):
        xml = b"""<rss><channel><item><title>T</title><link>https://x.org/a</link><pubDate>Mon, 26 Oct 2026 10:00:00 GMT</pubDate>
        <description>D</description></item><item><title>B</title><link>javascript:alert(1)</link></item></channel></rss>"""
        items = rss.parse_feed(xml)
        self.assertEqual(items[0]["url"], "https://x.org/a")
        self.assertEqual(items[0]["published_at"], "2026-10-26 10:00:00")
        self.assertIsNone(items[1]["url"])

    def test_firm_numbers(self):
        self.assertEqual(nlp.firm_numbers("au moins 60 morts"), [])
        self.assertEqual(nlp.firm_numbers("68 morts"), [(68.0, "mort")])


if __name__ == "__main__":
    unittest.main()
