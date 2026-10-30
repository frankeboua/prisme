"""Sert l'entrée de production wsgi.py avec la bibliothèque standard (gunicorn n'existe pas sous Windows)."""
import socketserver
import sys
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import wsgi


class Threaded(socketserver.ThreadingMixIn, WSGIServer):
    daemon_threads = True


class Quiet(WSGIRequestHandler):
    def log_message(self, *a):
        pass


make_server("127.0.0.1", int(sys.argv[1]), wsgi.application, server_class=Threaded, handler_class=Quiet).serve_forever()
