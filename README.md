# Zerodha Kite Connect — Algo starter (educational)

Beginner-friendly **paper-first** Python stack for experimenting with [Zerodha Kite Connect](https://kite.trade/) on **AWS EC2** behind a **static (Elastic) IP**, with optional **TOTP** automation patterns, **systemd** + **nginx**, and a small **FastAPI** dashboard.

**Not financial advice.** Read [DISCLAIMER.md](DISCLAIMER.md). Markets involve risk; this repository is for learning and safe defaults (`PAPER_TRADING=true`).

## What you get

- **`SKILL.md`** — AI-agent skill (YAML frontmatter + end-to-end steps).
- **`docs/`** — Numbered guides:
  1. [Kite Connect app (API key, redirect, postback, static IP)](docs/01-kite-connect-app.md)
  2. [AWS EC2 + Elastic IP + security groups](docs/02-aws-ec2-static-ip.md)
  3. [TOTP 2FA + `pyotp` + token exchange](docs/03-totp-automated-login.md)
  4. [Production deploy (systemd, nginx, firewall, logs, backups, timer)](docs/04-deployment.md)
- **Python app** (`src/kite_starter/`): Kite wrapper, SQLite store, **paper broker**, **risk controls** (daily loss, max orders/day, kill-switch file), **HTTP Basic** dashboard auth, one **demo EMA crossover** strategy (generic, educational).
- **CI**: GitHub Actions runs `pytest` on push/PR.
- **License**: [MIT](LICENSE).

## Quick start (local)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

cp .env.example .env
# Edit .env with placeholders only — never commit .env

python -m pytest -q

uvicorn kite_starter.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` — you will be prompted for **Basic Auth** (`DASHBOARD_USER` / `DASHBOARD_PASSWORD`).

### Log in to Kite (manual `request_token` flow)

1. Visit **`http://127.0.0.1:8000/login`** — browser opens Zerodha Kite Connect login.
2. After redirect to your **redirect URL** (for example `http://127.0.0.1:8000/callback/kite?...`), copy `request_token` from the query string.
3. **Exchange** for a session (stores tokens in SQLite):

   ```bash
   curl -u "$DASHBOARD_USER:$DASHBOARD_PASSWORD" -X POST http://127.0.0.1:8000/api/auth/exchange \
     -H "Content-Type: application/json" \
     -d '{"request_token":"YOUR_REQUEST_TOKEN"}'
   ```

   Or: `kite-starter auth-exchange YOUR_REQUEST_TOKEN`

4. Refresh the dashboard — **profile / positions / orders / margins** load from Kite (read-only). The **demo strategy** still uses **paper orders by default**.

### Paper vs live

| Mode | Config |
|------|--------|
| Paper (default) | `PAPER_TRADING=true` — simulated fills in SQLite |
| Live (not implemented in starter) | `PAPER_TRADING=false` and `ENABLE_LIVE_ORDERS=true` — you must add your own `place_order` wiring and compliance checks |

**Live orders require an explicit `ENABLE_LIVE_ORDERS=true` plus your own integration** — the demo code blocks live placement on purpose.

## Zero to EC2 dashboard (summary)

1. **Kite app**: Register at [developers.kite.trade](https://developers.kite.trade/) — set redirect and postback URLs, note **API whitelist / static IP** requirements for order APIs ([doc](docs/01-kite-connect-app.md)).
2. **EC2**: Launch **Amazon Linux 2023** or **Ubuntu**; security group **SSH 22 only from your IP**, **443** for HTTPS ([doc](docs/02-aws-ec2-static-ip.md)).
3. **Elastic IP**: Allocate, associate to the instance, **whitelist** that IP in the Kite console; verify with `curl -s https://ifconfig.me` on the instance ([doc](docs/02-aws-ec2-static-ip.md)).
4. **Secrets**: Put `KITE_API_KEY`, `KITE_API_SECRET`, account + TOTP material in **`/etc/kite-starter.env`** or root-only **`/root/.config/kite-starter.env`** (mode `600`) — never commit ([doc](docs/03-totp-automated-login.md)).
5. **Deploy**: Install app under `/opt/kite-starter`, use `deploy/kite-starter.service`, put **nginx** + TLS in front, enable **firewall**, **logrotate**, **backup** SQLite, optional **refresh** timer ([doc](docs/04-deployment.md)).

## Project layout

```
├── SKILL.md                 # AI skill (YAML + steps)
├── README.md
├── DISCLAIMER.md
├── LICENSE
├── .env.example
├── requirements.txt
├── pyproject.toml
├── src/kite_starter/        # Application package
├── tests/                   # Mocked tests (no network)
├── deploy/                  # systemd, nginx, logrotate, timer templates
└── docs/                    # Numbered setup guides
```

## CLI

- `kite-starter totp` — print current TOTP if `KITE_TOTP_SECRET` is set.
- `kite-starter auth-exchange <request_token>` — exchange and persist session.

## Testing

```bash
python -m pytest -q
```

CI runs the same on **Python 3.11** (see `.github/workflows/ci.yml`).

## Responsibility

Automating login or trading may implicate **Zerodha**, **SEBI**, and your own operational security. You are responsible for **terms compliance**, **static IP** correctness, and **protecting API secrets**. This starter **does not** implement production-grade live order execution.
