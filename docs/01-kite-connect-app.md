# Step 1 — Create a Kite Connect app (developers.kite.trade)

Numbered checklist for first-time setup. Replace every placeholder with your own values; **do not commit** real keys or URLs.

## 1.1 Create the developer account and app

1. Sign in at [Zerodha Kite Connect — Apps](https://developers.kite.trade/).
2. Create a new application. You will receive:
   - **API key** (public identifier — treat as sensitive for automation)
   - **API secret** (cryptographic secret — **never** expose or commit)
3. Set **Redirect URL** to a URL **you control**, for example:
   - Local development: `http://127.0.0.1:8000/callback/kite`
   - Production: `https://YOUR_DOMAIN.example/callback/kite`
4. Set **Postback URL** (if you use postbacks for order updates) to an HTTPS endpoint you control, for example:
   - `https://YOUR_DOMAIN.example/postback/kite`  
   - Optional shared secret query param (set the same value as `KITE_POSTBACK_SECRET` in `.env`):  
     `https://YOUR_DOMAIN.example/postback/kite?secret=YOUR_RANDOM_SHARED_SECRET`

Zerodha may require app review for certain capabilities. Read their current documentation for subscription or approval notes — requirements change over time.

## 1.2 Static IP / order API placement (SEBI / Zerodha)

Many broker APIs, including Kite Connect patterns used for **order placement**, expect requests to originate from **registered / whitelisted IP addresses** (often a **static public IP** you allocate and register in the developer console). Policy detail is published by **Zerodha** and **SEBI**; treat this document as practical infrastructure guidance, not legal advice.

1. Plan to run order-capable processes on a **single well-known egress IP** (for example an **AWS Elastic IP** associated with your EC2 instance).
2. In the developer console, add that IP as **primary** (and **secondary** if your design needs a standby instance or blue/green host — both must match what you actually use).
3. The IP seen by Zerodha must be the same as the machine/container that **sends orders** — **not** your laptop’s IP unless you only trade from that network (not typical for 24×7 bots).

## 1.3 Map values into environment variables

In `.env` (never committed), set:

| Variable | Meaning |
|----------|---------|
| `KITE_API_KEY` | From developer console |
| `KITE_API_SECRET` | From developer console |
| `KITE_REDIRECT_URL` | Must match the app’s redirect URL exactly |
| `KITE_LOGIN_URL` | Usually `https://kite.zerodha.com/connect/login?api_key=YOUR_API_KEY&v=3` (confirm in current docs) |

## 1.4 Security hygiene

- Rotate API secret if leaked.
- Restrict who can SSH to the trading host; never store the secret in application logs.
- Use HTTPS for every callback and postback endpoint exposed to the internet.

Next: [AWS EC2 and Elastic IP](./02-aws-ec2-static-ip.md).
