from __future__ import annotations

import argparse
import json
import sys

from .config import Settings
from .auth_totp import totp_now
from .db import Database
from .kite_client import KiteClientFactory


def main() -> int:
    parser = argparse.ArgumentParser(prog="kite-starter")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("totp", help="Print current TOTP code from KITE_TOTP_SECRET")

    p_ex = sub.add_parser("auth-exchange", help="Exchange request_token and persist session tokens in SQLite")
    p_ex.add_argument("request_token", help="request_token from the Kite OAuth redirect")

    args = parser.parse_args()

    if args.command == "totp":
        settings = Settings()
        if not settings.kite_totp_secret:
            print("KITE_TOTP_SECRET is not set.", file=sys.stderr)
            return 2
        print(totp_now(settings.kite_totp_secret))
        return 0

    if args.command == "auth-exchange":
        settings = Settings()
        db = Database(settings.database_path)
        factory = KiteClientFactory(settings.kite_api_key)
        kite = factory.build(None)
        try:
            session = kite.generate_session(args.request_token, api_secret=settings.kite_api_secret)
        except Exception as exc:  # noqa: BLE001
            print(f"generate_session failed: {exc}", file=sys.stderr)
            return 1
        access = session.get("access_token")
        refresh = session.get("refresh_token")
        if not access:
            print(json.dumps(session, indent=2, default=str))
            print("No access_token in response.", file=sys.stderr)
            return 1
        db.set_session_tokens(access, refresh)
        print("Session stored OK.")
        return 0

    parser.error("Unknown command")
    return 2
