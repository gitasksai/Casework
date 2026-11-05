"""Production server (Waitress) - use this instead of run.py on a server.

    python serve.py

Settings come from environment variables:
    CASEWORK_HOST     interface to listen on (default 0.0.0.0 = all network interfaces)
    CASEWORK_PORT     port (default 8080)
    CASEWORK_THREADS  worker threads (default 8)
"""
import logging
import os

from waitress import serve

from casework import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("CASEWORK_HOST", "0.0.0.0")
    port = int(os.environ.get("CASEWORK_PORT", 8080))
    if app.config["SECRET_KEY"] == "dev-change-me":
        logging.warning("CASEWORK_SECRET_KEY is not set - set it to a long random value.")
    if not (app.config.get("CASEWORK_USERNAME") and app.config.get("CASEWORK_PASSWORD")):
        logging.warning("No login configured - anyone who can reach http://%s:%s can see your cases. "
                        "Set CASEWORK_USERNAME and CASEWORK_PASSWORD.", host, port)
    logging.info("Casework listening on http://%s:%s", host, port)
    serve(app, host=host, port=port, threads=int(os.environ.get("CASEWORK_THREADS", 8)))
