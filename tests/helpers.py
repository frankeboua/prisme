"""Prépare une base temporaire avant l'import du serveur, et simule des requêtes HTTP."""
import json
import os
import tempfile


def setup(mode):
    os.environ["PRISME_DB"] = os.path.join(tempfile.mkdtemp(prefix="prisme_test_"), "t.db")
    os.environ["PRISME_MODE"] = mode
    os.environ["PRISME_ADMIN_USER"] = "redaction"
    os.environ["PRISME_ADMIN_PASSWORD"] = "mot-de-passe-de-test"
    os.environ["PRISME_GOOGLE_SITE_VERIFICATION"] = ""
    for k in ("PRISME_FIREBASE_API_KEY", "PRISME_FIREBASE_AUTH_DOMAIN", "PRISME_FIREBASE_PROJECT_ID"):
        os.environ[k] = ""   # les tests activent Firebase eux-mêmes, avec une configuration fictive


def call(server, method, path, body=None, token=None, ip="10.0.0.1", headers=None):
    data = json.dumps(body).encode() if body is not None else b""
    hd = {"content-length": str(len(data)), **(headers or {})}
    if token:
        hd["authorization"] = "Bearer " + token
    status, out, raw = server.handle(method, path, hd, lambda n: data[:n], ip)
    h = {k.lower(): v for k, v in out}
    try:
        parsed = json.loads(raw) if h.get("content-type", "").startswith("application/json") else raw.decode("utf-8", "replace")
    except ValueError:
        parsed = raw
    return status, h, parsed
