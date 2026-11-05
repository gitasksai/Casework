"""Production server (Cheroot) with optional HTTPS - use this instead of run.py on a server.

    python serve.py

Settings come from environment variables:
    CASEWORK_HOST              interface to listen on (default 0.0.0.0 = all network interfaces)
    CASEWORK_PORT              port (default 8443 with HTTPS, 8080 without)
    CASEWORK_THREADS           worker threads (default 10)
    CASEWORK_SSL_CERT          path to cert.pem  } set both to serve HTTPS
    CASEWORK_SSL_KEY           path to key.pem   } (create them with tls_cert.py)
    CASEWORK_SSL_KEY_PASSWORD  only if key.pem is password-protected
"""
import logging
import os
import sys

from cheroot import wsgi
from cheroot.ssl.builtin import BuiltinSSLAdapter

from casework import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("casework")

app = create_app()


def build_server():
    cert = os.environ.get("CASEWORK_SSL_CERT")
    key = os.environ.get("CASEWORK_SSL_KEY")
    use_tls = bool(cert or key)
    if use_tls:
        missing = [p for p in (cert, key) if not p or not os.path.isfile(p)]
        if missing or not (cert and key):
            sys.exit("HTTPS needs both CASEWORK_SSL_CERT and CASEWORK_SSL_KEY pointing at existing files "
                     f"(got cert={cert!r}, key={key!r}). Create them with: python tls_cert.py --help")

    host = os.environ.get("CASEWORK_HOST", "0.0.0.0")
    port = int(os.environ.get("CASEWORK_PORT", 8443 if use_tls else 8080))
    server = wsgi.Server(
        (host, port), app,
        numthreads=int(os.environ.get("CASEWORK_THREADS", 10)),
        server_name="casework",
    )
    if use_tls:
        server.ssl_adapter = BuiltinSSLAdapter(
            cert, key, private_key_password=os.environ.get("CASEWORK_SSL_KEY_PASSWORD") or None,
        )
        app.config["SESSION_COOKIE_SECURE"] = True

    if app.config["SECRET_KEY"] == "dev-change-me":
        log.warning("CASEWORK_SECRET_KEY is not set - set it to a long random value.")
    if not (app.config.get("CASEWORK_USERNAME") and app.config.get("CASEWORK_PASSWORD")):
        log.warning("No login configured - anyone who can reach this server can see your cases. "
                    "Set CASEWORK_USERNAME and CASEWORK_PASSWORD.")
    elif not use_tls:
        log.warning("Login is enabled without HTTPS - passwords cross the network unencrypted. "
                    "Set CASEWORK_SSL_CERT and CASEWORK_SSL_KEY.")
    scheme = "https" if use_tls else "http"
    log.info("Casework listening on %s://%s:%s", scheme, host, port)
    return server


if __name__ == "__main__":
    server = build_server()
    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
