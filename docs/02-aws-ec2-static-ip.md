# Step 2 — AWS EC2 with a static public IP (Elastic IP)

Goal: a small Linux server whose **outbound** internet IP is stable and can be **whitelisted** in the Kite developer console for order APIs.

## 2.1 Choose a region and AMI

1. Open the **EC2** console in an AWS region you will use consistently (changing regions changes Elastic IP pools).
2. Launch an instance:
   - **Amazon Linux 2023** or **Ubuntu Server 22.04 LTS** (64-bit x86 or Arm — match your preference and instance type).
3. Instance type: **`t4g.small`** or **`t3.small`** is often enough for a light bot and dashboard (not a performance recommendation — adjust to your workload).

## 2.2 Security group rules

Create or attach a security group:

| Direction | Type | Port | Source | Notes |
|-----------|------|------|--------|--------|
| Inbound | SSH | 22 | `YOUR_OFFICE_IP/32` | **Lock SSH to your IP**, not `0.0.0.0/0` |
| Inbound | HTTPS | 443 | `0.0.0.0/0` or a narrower CIDR | Expose dashboard only if needed; prefer VPN or IP allow-list when possible |

Outbound: default **allow all** is typical so the instance can reach Zerodha APIs and package mirrors.

## 2.3 Key pair and SSH

1. Create or select an SSH key pair; download the **`.pem`** securely.
2. Connect as the default user (for example `ec2-user` on Amazon Linux, `ubuntu` on Ubuntu):

   ```bash
   ssh -i /path/to/YOUR_KEY.pem ec2-user@203.0.113.10
   ```

   Use a **Documentation IP** such as `203.0.113.10` only in examples — use your instance’s real address in practice.

## 2.4 Allocate and associate an Elastic IP

1. In **EC2 → Elastic IPs → Allocate** an address.
2. **Associate** it with your running instance’s **primary ENI** (network interface).
3. In the **Kite developer console**, register this Elastic IP as your **primary** (and **secondary** if you use a documented secondary).

## 2.5 Verify outbound IP on the instance

On the instance:

```bash
curl -s https://ifconfig.me
```

The printed address should match the **Elastic IP** you whitelisted. If it does not:

- The instance may not be using the associated Elastic IP as its public egress route.
- Another NAT or outbound path may be in use — fix **before** relying on order placement.

## 2.6 Cost and pitfalls (short)

- **Elastic IP charges**: AWS often bills for Elastic IPs that are **allocated but not associated** with a running instance (pricing varies by region — read current AWS pricing pages).
- **Wrong IP in console**: if you whitelist `203.0.113.10` but the server egress is different, **orders will fail** IP checks.
- **Multiple NICs / containers**: ensure **the process that calls Kite** uses the host’s whitelisted egress, not a random task IP.

## 2.7 Hardening baseline

- Apply OS updates on boot and on a schedule.
- Use `firewalld` or `ufw` to allow only required ports (see [deployment](./04-deployment.md)).
- Prefer **Let’s Encrypt** TLS for the dashboard; avoid self-signed certs on public internet unless you know the trade-offs.

Next: [TOTP and token refresh](./03-totp-automated-login.md).
