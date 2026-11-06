from __future__ import annotations

import pyotp

from kite_starter.auth_totp import totp_now


def test_totp_now_matches_pyotp():
    secret = "JBSWY3DPEHPK3PXP"  # example Base32 (16 chars) — not a real account
    assert totp_now(secret) == pyotp.TOTP(secret).now()
