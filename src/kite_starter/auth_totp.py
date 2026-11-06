from __future__ import annotations

"""TOTP helpers for Zerodha 2FA — **user responsibility** under broker terms."""

import pyotp


def totp_now(secret: str) -> str:
    """Return the current 6-digit TOTP code for *secret* (Base32)."""
    return pyotp.TOTP(secret).now()
