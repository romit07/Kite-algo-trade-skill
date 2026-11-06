# Step 3 — TOTP 2FA on Zerodha and token refresh (pyotp)

This section explains how **time-based one-time passwords (TOTP)** fit into Kite Connect’s **`request_token` → `generate_session` → `access_token`** flow. **Automating login is sensitive**: you alone are responsible for complying with **Zerodha’s terms**, **SEBI** requirements, and good security practice.

## 3.1 Enable TOTP on Zerodha

1. In the Zerodha account / Kite security settings, enable **two-factor authentication** and choose an authenticator app.
2. Store the **TOTP secret** (the seed used to generate 6-digit codes) in a **password manager** or **secrets vault** — not in git.

**Never commit** `KITE_TOTP_SECRET`, passwords, or API secrets.

## 3.2 Mental model: where pyotp fits

- **Kite Connect** sessions start with a **`request_token`** obtained after the user authenticates to Zerodha (browser or scripted flow, subject to change).
- Your backend calls `kite.generate_session(request_token, api_secret)` to obtain an **`access_token`** (and `refresh_token` per current API behavior — verify in official docs).
- When Zerodha prompts for **TOTP** during login, your automation supplies the current code computed from the secret — commonly via **`pyotp.TOTP(secret).now()`**.

Zerodha may change web login flows; **robust** production systems often keep a **manual fallback** (you paste a fresh `request_token` from the official login redirect).

## 3.3 Environment variables (examples only)

On the server, use a **root-only** file such as `/root/.config/kite-starter.env` (mode `600`):

```bash
ZERODHA_USER_ID=YOUR_USER_ID
ZERODHA_PASSWORD=YOUR_PASSWORD
KITE_TOTP_SECRET=YOUR_BASE32_TOTP_SECRET
KITE_API_KEY=YOUR_API_KEY
KITE_API_SECRET=YOUR_API_SECRET
```

**Do not** reuse these placeholder names as real values — substitute your own.

## 3.4 Python: generate a TOTP code

```python
import pyotp

totp = pyotp.TOTP("YOUR_BASE32_TOTP_SECRET")
code = totp.now()
```

The starter includes `kite_starter.auth_totp.totp_now(secret)` for the same behavior.

## 3.5 Stable part: exchange `request_token` for a session

Once you have a **valid `request_token`** (from the redirect query string):

```python
from kiteconnect import KiteConnect

kite = KiteConnect(api_key="YOUR_API_KEY")
data = kite.generate_session("REQUEST_TOKEN_FROM_REDIRECT", api_secret="YOUR_API_SECRET")
access_token = data["access_token"]
kite.set_access_token(access_token)
```

The starter persists tokens in SQLite via the web API **POST `/api/auth/exchange`** or the CLI **`kite-starter auth-exchange`**.

## 3.6 Daily refresh timer

Use `systemd` **timer** or **cron** to:

1. Obtain a fresh `request_token` (manual or your maintained automation).
2. Call the starter’s **exchange** path to persist the new **access token**.
3. Restart or reload the app if needed so in-memory clients pick up tokens (the starter reloads from DB on each request for wrapper calls — verify in code).

See [deployment](./04-deployment.md) for a timer unit sketch.

## 3.7 Responsibility disclaimer

Automating credential entry may violate broker policies if done carelessly or insecurely. Use **least privilege**, **audit logs**, and **encryption at rest** for any file that holds secrets.

Next: [Deployment](./04-deployment.md).
