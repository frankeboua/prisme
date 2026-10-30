"""Mode démonstration local : les scénarios de la soutenance restent intacts. Lancer : python -m unittest tests.test_demo"""
import unittest

from tests.helpers import call, setup

setup("")
import server  # noqa: E402
from app import db, engine  # noqa: E402

server.bootstrap()
CONN = server.CONN


def art(title_like):
    return db.row(CONN, "SELECT * FROM articles WHERE title LIKE ?", (f"%{title_like}%",))


class Scenarios(unittest.TestCase):
    def setUp(self):
        server._hits.clear()

    def test_fuel_cluster_keeps_four_sources_and_divergence(self):
        a = art("Le prix du carburant augmente de 5")
        c = engine.compare_cluster(CONN, a["cluster_id"])
        self.assertGreaterEqual(c["cluster"]["source_count"], 4)
        units = {d["unit"]: {v["value"] for v in d["values"]} for d in c["divergences"]}
        self.assertTrue({"5", "15"} <= units.get("%", set()))

    def test_exaggerated_article_is_flagged(self):
        a = art("URGENT !! Le prix du carburant")
        self.assertEqual(a["verification_status"], "conteste")
        self.assertEqual(engine.status_label(a["verification_status"], 4, a["status_reason"]), "Chiffres divergents")

    def test_denied_rumour_is_flagged(self):
        a = art("plante miracle")
        self.assertEqual(a["verification_status"], "conteste")

    def test_recirculating_flood_article(self):
        a = db.row(CONN, engine.FEED_SQL.format(where=" AND a.title LIKE ?"), ("%18 morts%",))
        self.assertTrue(engine.decorate(CONN, a)["freshness"]["recirculating"])

    def test_demo_login_and_personas(self):
        self.assertTrue(call(server, "GET", "/api/config")[2]["demo_logins"])
        st, _, res = call(server, "POST", "/api/demo-login", {"username": "aminata"})
        self.assertEqual(st, 200)
        st, _, feed = call(server, "GET", "/api/feed?mode=pour_vous", token=res["token"])
        self.assertTrue(feed["profile"])
        self.assertEqual(call(server, "POST", "/api/demo-login", {"username": "inconnu"})[0], 404)

    def test_register_with_code_displayed_on_screen(self):
        res = call(server, "POST", "/api/email/code", {"email": "demo@exemple.org", "purpose": "register"})[2]
        self.assertEqual(len(res["demo_code"]), 6)
        body = {"email": "demo@exemple.org", "password": "motdepasse", "display_name": "D", "country": "Sénégal"}
        self.assertEqual(call(server, "POST", "/api/register", body)[0], 400)
        self.assertEqual(call(server, "POST", "/api/register", {**body, "code": res["demo_code"]})[0], 200)

    def test_demo_admin_can_moderate(self):
        tok = call(server, "POST", "/api/demo-login", {"username": "admin"})[2]["token"]
        self.assertEqual(call(server, "GET", "/api/admin/users", token=tok)[0], 200)

    def test_existing_flows(self):
        a = art("Le prix du carburant augmente de 5")
        for p in (f"/api/articles/{a['id']}", f"/api/articles/{a['id']}/summary", f"/api/articles/{a['id']}/simplify", "/api/trends", "/api/digest", "/api/stats", "/api/sources", "/api/search?q=carburant&dedup=1"):
            self.assertEqual(call(server, "GET", p)[0], 200, p)
        self.assertEqual(call(server, "GET", f"/article/{a['id']}")[0], 200)


if __name__ == "__main__":
    unittest.main()
