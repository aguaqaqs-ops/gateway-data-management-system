"""Directory command line."""

import argparse
import json
import os
import sqlite3
import sys
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from . import db, importer


def main() -> int:
    parser = argparse.ArgumentParser(prog="gdds-directory")
    commands = parser.add_subparsers(dest="command", required=True)
    importing = commands.add_parser("import")
    importing.add_argument("csv", type=Path)
    importing.add_argument("--dry-run", action="store_true")
    commands.add_parser("status")
    commands.add_parser("serve")
    args = parser.parse_args()
    value = os.environ.get("GDDS_DIRECTORY_DB", "")
    if not value or not Path(value).is_absolute():
        print("GDDS_DIRECTORY_DB: absolute path required", file=sys.stderr)
        return 2
    path = Path(value)
    try:
        db.validate_path(path)
        if args.command == "serve":
            from .http_service import DirectoryServer

            urls = []
            for name in ("GDDS_DIRECTORY_PUBLIC_URL", "GDDS_DIRECTORY_GATEWAY_FRONTEND_URL"):
                url = os.environ.get(name, "")
                try:
                    parsed = urlsplit(url)
                    valid = (parsed.scheme in ("http", "https") and bool(parsed.hostname)
                             and parsed.username is None and parsed.password is None
                             and not parsed.query and not parsed.fragment
                             and "?" not in url and "#" not in url
                             and not any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in url))
                    _ = parsed.port
                except ValueError:
                    valid = False
                if not valid:
                    raise db.ConfigurationError(f"{name}: valid HTTP URL required")
                urls.append(url)
            static_config = os.environ.get("GDDS_DIRECTORY_STATIC_DIR")
            if static_config is not None and not Path(static_config).is_absolute():
                raise db.ConfigurationError("GDDS_DIRECTORY_STATIC_DIR: absolute path required")
            static = Path(static_config) if static_config else Path(__file__).resolve().parents[2] / "frontend" / "dist"
            listen = os.environ.get("GDDS_DIRECTORY_LISTEN", "0.0.0.0:8100")
            try:
                host, port = listen.rsplit(":", 1)
                port_number = int(port)
                if not host or not 0 <= port_number <= 65535:
                    raise ValueError
            except ValueError:
                raise db.ConfigurationError("GDDS_DIRECTORY_LISTEN: host:port required") from None
            if path.exists():
                conn = db.connect(path, create=False, readonly=True)
                conn.close()
            server = DirectoryServer((host, port_number), path, static, urls[0], urls[1])
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        if args.command == "import":
            data = args.csv.read_bytes()
            projects, errors = importer.parse(data)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            # Dry-run of a new directory must not create the database or lock file.
            if args.dry_run and not path.exists():
                conn = sqlite3.connect(":memory:")
                conn.executescript(db.SCHEMA)
                try:
                    print(json.dumps(importer.apply(conn, projects, data, dry_run=True)))
                finally:
                    conn.close()
                return 0
            with (nullcontext() if args.dry_run else db.management_lock(path)):
                conn = db.connect(path, readonly=args.dry_run)
                try:
                    print(json.dumps(importer.apply(conn, projects, data, dry_run=args.dry_run)))
                finally:
                    conn.close()
        else:
            if not path.exists():
                print(json.dumps(dict.fromkeys(("projects", "removed", "provisioned", "pending", "expiring"), 0)))
                return 0
            conn = db.connect(path, create=False, readonly=True)
            try:
                conn.execute("BEGIN")
                total, removed = conn.execute("SELECT count(*), coalesce(sum(removed), 0) FROM projects").fetchone()
                provisioned, pending = conn.execute("SELECT count(current_session), coalesce(sum(pending_session IS NOT NULL AND current_session IS NOT NULL), 0) FROM provisioning").fetchone()
                threshold = (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
                expiring = sum(1 for (session,) in conn.execute("SELECT current_session FROM provisioning WHERE current_session IS NOT NULL") if json.loads(session)["expires_at"] <= threshold)
                print(json.dumps({"projects": total - removed, "removed": removed, "provisioned": provisioned, "pending": total - removed - conn.execute("SELECT count(*) FROM projects JOIN provisioning USING(device_key) WHERE removed=0 AND current_session IS NOT NULL").fetchone()[0] + pending, "expiring": expiring}))
            finally:
                conn.close()
    except db.ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except BlockingIOError:
        print("directory management lock busy", file=sys.stderr)
        return 3
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
