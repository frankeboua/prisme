"""Entrée de production : gunicorn wsgi:application --workers 1 --threads 8

Un seul processus : SQLite, la limitation de débit et la collecte programmée vivent en mémoire de ce processus.
"""
import threading

import server

server.bootstrap()
threading.Thread(target=server.scheduler, daemon=True).start()


def application(environ, start_response):
    headers = {k[5:].replace("_", "-").lower(): v for k, v in environ.items() if k.startswith("HTTP_")}
    for key in ("CONTENT_LENGTH", "CONTENT_TYPE"):
        if environ.get(key):
            headers[key.replace("_", "-").lower()] = environ[key]
    path = environ.get("RAW_URI") or environ.get("PATH_INFO", "/")
    if environ.get("QUERY_STRING") and "?" not in path:
        path += "?" + environ["QUERY_STRING"]
    forwarded = headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or environ.get("REMOTE_ADDR", "")
    status, out, body = server.handle(environ["REQUEST_METHOD"], path, headers, environ["wsgi.input"].read, ip)
    reasons = {200: "OK", 206: "Partial Content", 304: "Not Modified", 416: "Range Not Satisfiable", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
               409: "Conflict", 413: "Payload Too Large", 429: "Too Many Requests", 500: "Internal Server Error"}
    start_response(f"{status} {reasons.get(status, 'OK')}", out)
    return [body]
