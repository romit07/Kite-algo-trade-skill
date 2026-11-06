# Step 4 — Production deployment (systemd, nginx, HTTPS, hardening)

This guide assumes Amazon Linux 2023 or Ubuntu on EC2 with an Elastic IP already associated and whitelisted for Kite Connect (see [AWS static IP](./02-aws-ec2-static-ip.md)).

## 4.1 Install runtime dependencies

**Amazon Linux 2023** (example):

```bash
sudo dnf update -y
sudo dnf install -y python3.11 python3.11-pip nginx git
```

**Ubuntu** (example):

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv nginx git
```

Clone this repository to `/opt/kite-starter` (or another path), create a venv, and `pip install -r requirements.txt`.

## 4.2 Application user and secrets

1. Create a Unix user (for example `kiteapp`) to run the service **without** unnecessary root privileges.
2. Store environment in `/etc/kite-starter.env` (mode `640`, root:kiteapp) or `/root/.config/kite-starter.env` if only root should read TOTP material — match your threat model.

Example snippet (placeholders only):

```bash
KITE_API_KEY=YOUR_API_KEY
KITE_API_SECRET=YOUR_API_SECRET
PAPER_TRADING=true
ENABLE_LIVE_ORDERS=false
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=use_a_long_random_password
```

## 4.3 systemd service

1. Copy `deploy/kite-starter.service` to `/etc/systemd/system/kite-starter.service` and adjust `WorkingDirectory`, `EnvironmentFile`, and `User`.
2. Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kite-starter.service
sudo journalctl -u kite-starter -f
```

## 4.4 nginx reverse proxy with HTTPS

1. Point your DNS `A` record for `YOUR_DOMAIN.example` at the Elastic IP `203.0.113.10` (example documentation IP).
2. Use **Let’s Encrypt** (`certbot`) for a public hostname, or generate a **self-signed** cert for private/lab use only.
3. Copy `deploy/nginx-kite-starter.conf` to `/etc/nginx/conf.d/` (paths vary by distro), set `server_name`, and proxy to `http://127.0.0.1:8000`.

Example Let’s Encrypt (Ubuntu + certbot nginx plugin, illustrative):

```bash
sudo certbot --nginx -d YOUR_DOMAIN.example
```

## 4.5 Dashboard password authentication

The FastAPI app enforces **HTTP Basic Auth** using `DASHBOARD_USER` / `DASHBOARD_PASSWORD`. **Also** terminate TLS at nginx so credentials are not sent in clear text.

For stronger schemes (OAuth2, mutual TLS), extend the app — not covered in this starter.

## 4.6 Host firewall

**firewalld** (Amazon Linux):

```bash
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

**ufw** (Ubuntu):

```bash
sudo ufw allow OpenSSH
sudo ufw allow 443/tcp
sudo ufw enable
```

Keep SSH restricted to **your IP** in the **security group** as the primary control.

## 4.7 Log rotation

Use `logrotate` for application logs under `/var/log/kite-starter/` if you redirect stdout/stderr to files, or rely on `journald` with vacuum policies:

```bash
sudo journalctl --vacuum-time=30d
```

## 4.8 Daily token refresh timer

Use `deploy/kite-starter-refresh.timer` and `.service` as templates: they run a small script that **you** supply to drop a fresh `request_token` into a root-only file and call `kite-starter auth-exchange` (see package CLI). Adjust paths and security to your environment.

## 4.9 Backups

Back up:

- SQLite database path (default `./data/kite_starter.db` — override with `DATABASE_PATH`)
- Environment file(s)
- nginx configuration and TLS private keys (store keys in a secure vault)

Example tarball (run from cron):

```bash
sudo tar czf /var/backups/kite-starter-$(date +%F).tgz \
  /opt/kite-starter/data/kite_starter.db /etc/kite-starter.env
```

## 4.10 Health check

From your laptop:

```bash
curl -I -u "$DASHBOARD_USER:$DASHBOARD_PASSWORD" https://YOUR_DOMAIN.example/health
```

You should receive HTTP `200`.

Return to the [README](../README.md) for a zero-to-running overview.
