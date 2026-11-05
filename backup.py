"""Make a consistent copy of the SQLite database (safe while the app is running).

    python backup.py [backup_folder] [days_to_keep]

Defaults: backup folder = ./backups, keep 30 days. Schedule it daily with Task Scheduler.
"""
import os
import sqlite3
import sys
import time
from datetime import datetime

from casework import create_app


def main():
    target_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "backups")
    keep_days = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    app = create_app()
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("sqlite:///"):
        sys.exit(f"backup.py only handles SQLite databases, not {uri.split(':')[0]}")
    source = uri[len("sqlite:///"):]

    os.makedirs(target_dir, exist_ok=True)
    dest = os.path.join(target_dir, f"casework-{datetime.now():%Y%m%d-%H%M%S}.db")
    src_conn, dst_conn = sqlite3.connect(source), sqlite3.connect(dest)
    with dst_conn:
        src_conn.backup(dst_conn)
    src_conn.close()
    dst_conn.close()
    print(f"Backed up {source} -> {dest}")

    cutoff = time.time() - keep_days * 86400
    for name in os.listdir(target_dir):
        path = os.path.join(target_dir, name)
        if name.startswith("casework-") and name.endswith(".db") and os.path.getmtime(path) < cutoff:
            os.remove(path)
            print(f"Removed old backup {name}")


if __name__ == "__main__":
    main()
