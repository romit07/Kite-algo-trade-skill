---
name: zerodha-kite-algo-starter
description: >-
  Step-by-step skill for setting up a beginner-friendly, paper-first Python stack
  for Zerodha Kite Connect on AWS EC2 with a static IP, TOTP-based session
  refresh patterns, systemd/nginx deployment, and a small FastAPI dashboard with
  a generic demo strategy. Not financial advice; users are responsible for
  broker terms and compliance.
---

# Zerodha Kite Connect — Algo starter (skill)

Use this document end-to-end: humans can follow it directly; AI coding agents should execute steps in order, stop on errors, and never commit secrets.

## Prerequisites

- Zerodha account with Kite Connect developer app approved (see `docs/01-kite-connect-app.md`).
- AWS account rights to create EC2, Elastic IP, and security groups (see `docs/02-aws-ec2-static-ip.md`).
- Local machine with Python 3.11+ for development tests; production target is Amazon Linux 2023 or Ubuntu on EC2.

## Safety and compliance

1. Read `DISCLAIMER.md`. This kit is **educational**; markets involve risk.
2. **Paper trading is the default** (`PAPER_TRADING=true`). Live orders require an explicit opt-in flag and understanding of broker rules.
3. Automating login and order placement is **your responsibility** under Zerodha’s terms and applicable regulations (including SEBI guidance). Do not bypass security controls.

## Phase A — Clone and configure (local)

1. Clone this repository.
2. Copy `.env.example` to `.env` and fill placeholders only on your machine. Never commit `.env`.
3. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Run unit tests (no network; Kite is mocked):

   ```bash
   pytest -q
   ```

## Phase B — Kite Connect app (console)

Follow `docs/01-kite-connect-app.md` to:

1. Register an app at `https://developers.kite.trade` with API key/secret, redirect URL, and postback URL.
2. Note **static IP / API whitelist** requirements for placing orders (EC2 Elastic IP must match the server that calls order APIs).

Record `KITE_API_KEY`, `KITE_API_SECRET`, redirect/postback URLs in `.env` using placeholders in docs — never real values in git.

## Phase C — AWS EC2 + Elastic IP

Follow `docs/02-aws-ec2-static-ip.md` to:

1. Launch Amazon Linux 2023 or Ubuntu; attach security group allowing SSH (22) from **your IP only** and HTTPS (443) from intended clients.
2. Allocate and associate an **Elastic IP**; whitelist that IP in the Kite developer console (primary; add secondary if documented).
3. Verify outbound IP on the instance: `curl -s https://ifconfig.me` must match the whitelisted Elastic IP.
4. Understand Elastic IP billing (charges when **unassociated** in some regions/account types) and pitfalls (orders must originate from the whitelisted machine).

## Phase D — TOTP and daily token refresh

Follow `docs/03-totp-automated-login.md` to:

1. Enable TOTP 2FA on Zerodha.
2. Store `ZERODHA_USER_ID`, `ZERODHA_PASSWORD`, `KITE_TOTP_SECRET` only in root-owned env files or a secrets manager — **never** in the repo.
3. Use the provided `kite_starter.auth` helpers: TOTP via `pyotp`, then obtain `request_token` and call `generate_session` → `access_token`. Prefer `EnvironmentFile=` in systemd pointing to `/root/.config/kite-starter.env` (mode `600`).

The implementation includes an **optional** automated credential login helper that may break if Zerodha changes web APIs — monitor logs and fall back to manual `request_token` from the official login URL when needed.

## Phase E — Run the app (development)

1. Export required variables (see `.env.example`).
2. Start the API:

   ```bash
   uvicorn kite_starter.app:app --host 127.0.0.1 --port 8000
   ```

3. Open `http://127.0.0.1:8000` — use dashboard user/pass from `DASHBOARD_USER` / `DASHBOARD_PASSWORD`.

4. Confirm **paper mode** in the status panel before any live testing.

## Phase F — Production deploy

Follow `docs/04-deployment.md` to:

1. Install the app under `/opt/kite-starter` (or similar) with a dedicated user; use systemd unit from `deploy/kite-starter.service`.
2. Put nginx in front with TLS (Let’s Encrypt or self-signed for private use); enable basic proxy to Uvicorn.
3. Restrict firewall (`firewalld` / `ufw`), enable log rotation, schedule **daily token refresh** timer, and backup SQLite DB + config.

## Phase G — Operations checklist

- [ ] Elastic IP still associated and whitelisted in Kite console.
- [ ] `PAPER_TRADING` remains default until consciously disabled.
- [ ] Risk limits set: `MAX_DAILY_LOSS_INR`, `MAX_ORDERS_PER_DAY`, kill switch file path.
- [ ] Monitor logs under `/var/log/kite-starter/` (see deploy docs).
- [ ] Review Zerodha circulars / API changes regularly.

## Phase H — Going live (only after paper validation)

Read `docs/05-going-live-safely.md` and confirm:

- `PAPER_TRADING=false` **and** `ENABLE_LIVE_ORDERS=true` together (no half-enabled states).
- `ORDER_TAG_PREFIX` scopes mass-cancel / square-off to **your** orders only.
- Postback URL registered to `https://YOUR_DOMAIN/postback/kite` with optional shared secret.

## Troubleshooting (short)

| Symptom | Check |
|--------|--------|
| Order rejected / IP error | Outbound IP vs Kite whitelist; NAT vs Elastic IP association |
| 403 on login helper | Zerodha changed login flow — use manual `request_token` flow |
| Dashboard 401 | `DASHBOARD_USER` / `DASHBOARD_PASSWORD` and nginx proxy headers |

## Where code lives

- Python package: `src/kite_starter/`
- Demo strategy: `src/kite_starter/strategies/demo_ema_crossover.py`
- Tests: `tests/`

When modifying behavior, **keep the demo strategy generic** (no real trading playbook, no production-style options rules).
