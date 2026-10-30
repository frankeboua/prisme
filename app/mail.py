"""Envoi d'e-mails par l'API HTTPS de Brevo (l'offre gratuite de Render bloque les ports SMTP)."""
import json
import os
import urllib.request

API_URL = "https://api.brevo.com/v3/smtp/email"


def enabled():
    return bool(os.environ.get("BREVO_API_KEY") and os.environ.get("PRISME_MAIL_FROM"))


def send(to, subject, text):
    """Lève une exception si le service refuse l'envoi."""
    body = {"sender": {"name": "Prisme", "email": os.environ["PRISME_MAIL_FROM"]}, "to": [{"email": to}], "subject": subject, "textContent": text}
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"api-key": os.environ["BREVO_API_KEY"], "accept": "application/json", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()
