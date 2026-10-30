"""Mode production : sécurité, SEO, absence de démonstration, regroupement. Lancer : python -m unittest tests.test_public"""
import io
import re
import unittest
import urllib.parse
from datetime import date

from PIL import Image

from tests.helpers import call, setup

setup("public")
import server  # noqa: E402
from app import db, editorial, engine, mail, nlp, rss, translate  # noqa: E402

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
    return call(server, "POST", "/api/register", {"email": f"{name}@exemple.org", "password": "motdepasse", "display_name": "L", "country": "Sénégal"})[2]["token"]


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
        self.assertFalse(call(server, "GET", "/api/config")[2]["email_verification"])
        self.assertEqual(call(server, "POST", "/api/email/code", {"email": "a@exemple.org", "purpose": "register"})[0], 503)

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
        ok = {"email": "Lecteur1@Exemple.org", "password": "motdepasse", "display_name": "L", "country": "Sénégal"}
        self.assertEqual(call(server, "POST", "/api/register", {**ok, "email": "pasunmail"})[0], 400)
        self.assertEqual(call(server, "POST", "/api/register", {**ok, "password": "court"})[0], 400)
        self.assertEqual(call(server, "POST", "/api/register", ok)[0], 200)
        self.assertEqual(call(server, "POST", "/api/register", ok)[0], 409)
        self.assertEqual(db.scalar(CONN, "SELECT username FROM users WHERE email='lecteur1@exemple.org'"), "lecteur1")
        self.assertEqual(call(server, "POST", "/api/login", {"username": "LECTEUR1@exemple.org", "password": "motdepasse"})[0], 200)

    def test_country_and_password_confirmation_are_enforced(self):
        ok = {"email": "pays@exemple.org", "password": "motdepasse", "password_confirm": "motdepasse", "display_name": "P", "country": "Côte d'Ivoire"}
        self.assertEqual(call(server, "POST", "/api/register", {k: v for k, v in ok.items() if k != "country"})[0], 400)
        self.assertEqual(call(server, "POST", "/api/register", {**ok, "country": "Atlantide"})[0], 400)
        st, _, res = call(server, "POST", "/api/register", {**ok, "password_confirm": "autrechose"})
        self.assertEqual(st, 400)
        self.assertIn("identiques", res["error"])
        st, _, res = call(server, "POST", "/api/register", ok)
        self.assertEqual(st, 200)
        self.assertEqual(res["user"]["country"], "Côte d'Ivoire")
        self.assertEqual(call(server, "PUT", "/api/me", {"country": "Atlantide"}, res["token"])[0], 400)
        self.assertEqual(call(server, "PUT", "/api/me", {"country": "Mali"}, res["token"])[2]["user"]["country"], "Mali")

    def test_country_list(self):
        c = call(server, "GET", "/api/countries")[2]
        self.assertEqual(c[0], "Côte d'Ivoire")
        self.assertGreater(len(c), 190)
        self.assertEqual(len(c), len(set(c)))

    def test_username_is_generated_without_collision(self):
        new_user("doublon")
        call(server, "POST", "/api/register", {"email": "doublon@autre.org", "password": "motdepasse", "display_name": "L", "country": "Sénégal"})
        self.assertEqual(db.scalar(CONN, "SELECT username FROM users WHERE email='doublon@autre.org'"), "doublon2")

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


class EmailVerification(Case):
    """Service d'envoi simulé : aucun e-mail réel ne part pendant les tests."""

    def setUp(self):
        super().setUp()
        self.sent = []
        self._enabled, self._send = mail.enabled, mail.send
        mail.enabled = lambda: True
        mail.send = lambda to, subject, text: self.sent.append((to, subject, text))

    def tearDown(self):
        mail.enabled, mail.send = self._enabled, self._send

    def code(self):
        return re.search(r"\b(\d{6})\b", self.sent[-1][2]).group(1)

    def test_register_requires_valid_code(self):
        body = {"email": "verif@exemple.org", "password": "motdepasse", "display_name": "V", "country": "Sénégal"}
        self.assertEqual(call(server, "POST", "/api/register", body)[0], 400)
        st, _, res = call(server, "POST", "/api/email/code", {"email": body["email"], "purpose": "register"})
        self.assertEqual(st, 200)
        self.assertNotIn("demo_code", res)
        self.assertEqual(call(server, "POST", "/api/register", {**body, "code": "000000" if self.code() != "000000" else "111111"})[0], 400)
        self.assertEqual(call(server, "POST", "/api/register", {**body, "code": self.code()})[0], 200)
        self.assertEqual(db.scalar(CONN, "SELECT email_verified FROM users WHERE email=?", (body["email"],)), 1)
        self.assertEqual(call(server, "POST", "/api/register", {**body, "code": self.code()})[0], 409)

    def test_code_stops_after_five_wrong_attempts(self):
        body = {"email": "essais@exemple.org", "password": "motdepasse", "display_name": "E", "country": "Sénégal"}
        call(server, "POST", "/api/email/code", {"email": body["email"], "purpose": "register"})
        wrong = "000000" if self.code() != "000000" else "111111"
        for _ in range(5):
            call(server, "POST", "/api/register", {**body, "code": wrong})
        self.assertEqual(call(server, "POST", "/api/register", {**body, "code": self.code()})[0], 400)

    def test_password_is_never_emailed_and_reset_revokes_sessions(self):
        mail.enabled = lambda: False
        t = new_user("oubli")
        mail.enabled = lambda: True
        call(server, "POST", "/api/email/code", {"email": "oubli@exemple.org", "purpose": "reset"})
        self.assertNotIn("motdepasse", self.sent[-1][2])
        st, _, res = call(server, "POST", "/api/password/reset", {"email": "oubli@exemple.org", "code": self.code(), "new_password": "nouveaumdp"})
        self.assertEqual(st, 200)
        self.assertTrue(res["token"])
        self.assertFalse(call(server, "GET", "/api/me", token=t)[2]["user"])
        self.assertEqual(call(server, "POST", "/api/login", {"username": "oubli@exemple.org", "password": "nouveaumdp"})[0], 200)

    def test_response_does_not_reveal_whether_account_exists(self):
        a = call(server, "POST", "/api/email/code", {"email": "inconnu@exemple.org", "purpose": "reset"})
        self.assertEqual((a[0], a[2]), (200, {"sent": True}))
        self.assertEqual(self.sent, [])

    def test_code_requests_are_limited_per_address(self):
        codes = [call(server, "POST", "/api/email/code", {"email": "limite@exemple.org", "purpose": "register"})[0] for _ in range(5)]
        self.assertIn(429, codes)

    def test_send_failure_is_reported_cleanly(self):
        def boom(*a):
            raise OSError("refus du service")
        mail.send = boom
        st, _, res = call(server, "POST", "/api/email/code", {"email": "panne@exemple.org", "purpose": "register"})
        self.assertEqual(st, 502)
        self.assertNotIn("refus du service", str(res))


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


class SearchHelp(Case):
    def found(self, q):
        return [a["id"] for a in call(server, "GET", "/api/search?q=" + urllib.parse.quote(q))[2]["items"]]

    def test_accents_case_and_apostrophes_do_not_matter(self):
        aid = add_article(src[0], "ci1", "Côte d’Ivoire : la récolte de cacao démarre à Daloa", "Les planteurs de Daloa préparent la récolte.")
        for q in ("cote d'ivoire", "COTE IVOIRE", "Côte d’Ivoire", "recolte cacao", "cacao"):
            self.assertIn(aid, self.found(q), q)

    def test_small_words_are_ignored(self):
        aid = add_article(src[0], "ci2", "Les défaites du Barça en Ligue des champions", "Le club catalan a perdu.")
        self.assertIn(aid, self.found("les défaites du barça"))
        self.assertIn(aid, self.found("defaite barca"))

    def test_nickname_finds_full_name(self):
        aid = add_article(src[0], "ci3", "Le FC Barcelone prépare son prochain match", "Entraînement ce matin.")
        self.assertIn(aid, self.found("barça"))

    def test_partial_match_is_flagged(self):
        aid = add_article(src[0], "ci4", "Le festival de jazz de Grand-Bassam ouvre ses portes", "Concert ce soir.")
        res = call(server, "GET", "/api/search?q=" + urllib.parse.quote("jazz xylophonique"))[2]
        self.assertTrue(res["relaxed"])
        self.assertIn(aid, [a["id"] for a in res["items"]])
        self.assertFalse(call(server, "GET", "/api/search?q=jazz")[2]["relaxed"])

    def test_title_matches_come_first(self):
        body = add_article(src[0], "ci5", "Conseil des ministres de la semaine", "Le texte évoque aussi le zébu malgache.", 1)
        title = add_article(src[1], "ci6", "Le zébu malgache à l'honneur", "Une race bovine.", 5)
        self.assertEqual(self.found("zebu")[:2], [title, body])

    def test_grouped_search_keeps_article_matching_the_words(self):
        lead = add_article(src[0], "dup1", "Sénégal : un pont géant inauguré à Kaolack cette semaine", "Le pont géant de Kaolack est ouvert.", 1)
        echo = add_article(src[1], "dup2", "Kaolack : le pont géant inauguré au Sénégal, un chantier titanesque", "Le pont géant de Kaolack est ouvert.", 2)
        engine.recluster(CONN)
        same = db.scalar(CONN, "SELECT cluster_id FROM articles WHERE id=?", (lead,)) == db.scalar(CONN, "SELECT cluster_id FROM articles WHERE id=?", (echo,))
        self.assertTrue(same)
        res = call(server, "GET", "/api/search?q=titanesque&dedup=1")[2]
        self.assertIn(echo, [a["id"] for a in res["items"]])
        both = [a["id"] for a in call(server, "GET", "/api/search?q=kaolack&dedup=1")[2]["items"]]
        self.assertEqual(len([i for i in both if i in (lead, echo)]), 1)

    def test_search_stays_safe(self):
        self.assertEqual(call(server, "GET", "/api/search?q=" + urllib.parse.quote("%' OR 1=1--"))[0], 200)
        self.assertEqual(call(server, "GET", "/api/search?q=" + urllib.parse.quote("_ %"))[0], 200)


class Translation(Case):
    def test_many_languages_and_bad_ones_refused(self):
        res = call(server, "GET", "/api/languages")[2]
        self.assertGreaterEqual(len(res["languages"]), 45)
        for code in ("sw", "ha", "ar", "zh", "wo"):
            self.assertIn(code, res["languages"])
        for code in ("bm", "dyu", "rw"):
            self.assertNotIn(code, res["languages"])
        self.assertEqual(call(server, "GET", f"/api/articles/{A1}/translate?lang=xx")[0], 400)

    def test_translation_uses_requested_language(self):
        seen = []
        original = translate._call
        translate._call = lambda text, s, d: (seen.append(d), "Kiswahili &amp; tafsiri")[1]
        try:
            res = call(server, "GET", f"/api/articles/{A1}/translate?lang=sw")[2]
        finally:
            translate._call = original
        self.assertEqual(set(seen), {"sw"})
        self.assertEqual(res["title"], "Kiswahili &amp; tafsiri")

    def test_blocked_server_hands_text_to_browser(self):
        original = translate._call

        def blocked(*a):
            raise OSError("403")
        translate._call = blocked
        try:
            res = call(server, "GET", f"/api/articles/{A3}/translate?lang=it")[2]
        finally:
            translate._call = original
        self.assertIn("error", res)
        self.assertEqual(res["fallback"]["source"], "fr")
        self.assertTrue(res["fallback"]["chunks"])
        self.assertNotIn("403", res["error"])
        self.assertIn("api.mymemory.translated.net", call(server, "GET", "/")[1]["content-security-policy"])

    def test_diagnostic_is_admin_only(self):
        self.assertEqual(call(server, "GET", "/api/admin/translate-check")[0], 401)

    def test_quota_message_is_understandable(self):
        original = translate._call

        def full(*a):
            raise RuntimeError("quota")
        translate._call = full
        try:
            res = call(server, "GET", f"/api/articles/{A2}/translate?lang=de")[2]
        finally:
            translate._call = original
        self.assertIn("limite", res["error"])


class TextSettings(Case):
    def test_font_is_saved_and_invalid_is_ignored(self):
        t = new_user("policelecteur")
        self.assertEqual(call(server, "GET", "/api/me", token=t)[2]["user"]["font_family"], "prisme")
        self.assertEqual(call(server, "PUT", "/api/me", {"font_family": "lisible"}, t)[2]["user"]["font_family"], "lisible")
        self.assertEqual(call(server, "PUT", "/api/me", {"font_family": "<script>"}, t)[2]["user"]["font_family"], "lisible")


class Publishers(Case):
    def test_two_feeds_of_one_publisher_count_as_one_media(self):
        ids = {r["name"]: r["id"] for r in db.rows(CONN, "SELECT id, name FROM sources")}
        monde = [i for n, i in ids.items() if n.startswith("Le Monde")]
        self.assertEqual(len(monde), 2)
        title = "Mauritanie : un accord historique sur la gestion du fleuve Sénégal signé à Nouakchott"
        text = "Les pays riverains ont signé à Nouakchott un accord historique sur la gestion commune du fleuve Sénégal."
        a = add_article(monde[0], "pub1", title, text)
        b = add_article(monde[1], "pub2", title, text)
        engine.recluster(CONN)
        cl = db.row(CONN, "SELECT c.* FROM clusters c JOIN articles a ON a.cluster_id=c.id WHERE a.id=?", (a,))
        self.assertEqual(db.scalar(CONN, "SELECT cluster_id FROM articles WHERE id=?", (b,)), cl["id"])
        self.assertEqual(cl["size"], 2)
        self.assertEqual(cl["source_count"], 1)
        engine.verify_article(CONN, a)
        engine.refresh_statuses(CONN)
        self.assertEqual(db.scalar(CONN, "SELECT verification_status FROM articles WHERE id=?", (a,)), "non_verifie")

    def test_stats_count_publishers_not_feeds(self):
        server._anon_cache.clear()
        st = call(server, "GET", "/api/stats")[2]
        feeds = db.scalar(CONN, "SELECT COUNT(*) FROM sources")
        self.assertEqual(feeds, 16)
        self.assertEqual(st["real_sources"], 14)
        ivoirians = db.scalar(CONN, "SELECT COUNT(*) FROM sources WHERE country='Côte d''Ivoire' AND is_demo=0")
        self.assertEqual(ivoirians, 3)


class Video(Case):
    def test_range_requests_for_mobile_players(self):
        st, h, _ = call(server, "GET", "/app.css", headers={"range": "bytes=0-99"})
        self.assertEqual(st, 206)
        self.assertEqual(h["content-length"], "100")
        self.assertTrue(h["content-range"].startswith("bytes 0-99/"))
        self.assertEqual(call(server, "GET", "/app.css", headers={"range": "bytes=999999999-"})[0], 416)


class Fast(Case):
    def tearDown(self):
        server._anon_cache.clear()

    def test_anonymous_reads_are_cached_but_not_for_logged_in_readers(self):
        server._anon_cache.clear()
        st, h, first = call(server, "GET", "/api/categories")
        self.assertEqual(st, 200)
        self.assertEqual(h["cache-control"], "private, max-age=30")
        self.assertIn("/api/categories?", server._anon_cache)
        self.assertEqual(call(server, "GET", "/api/categories")[2], first)
        tok = new_user("cachelecteur")
        self.assertEqual(call(server, "GET", "/api/feed", token=tok)[1]["cache-control"], "no-store")
        self.assertNotIn("/api/feed?", server._anon_cache)
        self.assertTrue(call(server, "GET", "/api/feed", token=tok)[2]["profile"] is not None)

    def test_photo_is_converted_and_cached(self):
        buf = io.BytesIO()
        Image.new("RGB", (1600, 1000), "#336699").save(buf, "JPEG")
        calls = []
        original = rss.fetch
        rss.fetch = lambda url, **k: (calls.append(url), buf.getvalue())[1]
        try:
            for _ in range(2):
                st, h, _ = call(server, "GET", f"/img/{A1}-480.webp")
                self.assertEqual(st, 200)
                self.assertEqual(h["content-type"], "image/webp")
                self.assertIn("immutable", h["cache-control"])
            self.assertEqual(len(calls), 1)
            st, out, raw = server.handle("GET", f"/img/{A1}-480.webp", {}, lambda n: b"", "1.1.1.1")
            self.assertEqual(Image.open(io.BytesIO(raw)).size[0], 480)
            self.assertLess(len(raw), len(buf.getvalue()))
        finally:
            rss.fetch = original

    def test_photo_unavailable_falls_back_to_original(self):
        aid = add_article(src[0], "photo-ko", "Photo indisponible pour ce test", "Texte.", image="https://exemple.org/absente.jpg")
        original = rss.fetch

        def boom(url, **k):
            raise OSError("indisponible")
        rss.fetch = boom
        try:
            st, h, _ = call(server, "GET", f"/img/{aid}-480.webp")
        finally:
            rss.fetch = original
        self.assertEqual((st, h["location"]), (302, "https://exemple.org/absente.jpg"))

    def test_image_route_only_serves_known_articles(self):
        self.assertEqual(call(server, "GET", "/img/999999-480.webp")[0], 404)
        self.assertEqual(call(server, "GET", f"/img/{OTHER}-480.webp")[0], 404)
        self.assertEqual(call(server, "GET", "/img/../server.py-480.webp")[0], 404)


class EditorialRecall(Case):
    def test_sport_recall_cites_two_sources_per_match(self):
        r = call(server, "GET", "/api/recall?category=sport")[2]["recall"]
        if r:
            self.assertEqual(len(r["items"]), 2)
            for i in r["items"]:
                self.assertEqual(len(i["sources"]), 2)
                self.assertTrue(all(x["url"].startswith("https://") for x in i["sources"]))
        self.assertIsNone(call(server, "GET", "/api/recall?category=culture")[2]["recall"])

    def test_recall_expires(self):
        self.assertIsNotNone(editorial.recall_for("sport", date(2026, 10, 30)))
        self.assertIsNone(editorial.recall_for("sport", date(2026, 11, 16)))


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
    def test_article_page_is_typed_article_with_exact_date_and_section(self):
        _, _, html = call(server, "GET", f"/article/{A1}")
        self.assertIn('property="og:type" content="article"', html)
        self.assertIn('property="article:published_time"', html)
        self.assertIn('property="article:section"', html)
        self.assertIn('"@type": "NewsArticle"', html)
        self.assertRegex(html, r"\d\d/\d\d/\d{4} à \d\d:\d\d UTC")
        self.assertIn('class="kicker"', html)
        self.assertIn('property="og:type" content="website"', call(server, "GET", "/")[2])

    def test_lists_show_section_and_time(self):
        _, _, html = call(server, "GET", "/")
        self.assertIn('class="kicker"', html)
        self.assertRegex(html, r"<time datetime=\"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\">")

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
