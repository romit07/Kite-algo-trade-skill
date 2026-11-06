# Step 5 — Going live safely

This project defaults to **paper trading** for a reason. Enabling real money flows through Kite Connect requires discipline, compliance awareness, and operational hygiene. This document is **not legal advice**; read **Zerodha**, **SEBI**, and **exchange** circulars for the rules that apply to you.

## 5.1 Stay on paper first

1. Run with **`PAPER_TRADING=true`** until you trust logging, risk limits, dashboard auth, and deployment.
2. Walk through **`POST /api/auth/exchange`**, dashboard read-only views, and **`/health`** on the same host you will use in production.
3. Only then set **`PAPER_TRADING=false`** and **`ENABLE_LIVE_ORDERS=true`** together — the app **never** sends live orders unless **both** are set.

## 5.2 Start small

1. Set **`STRATEGY_ORDER_QUANTITY`** and **`MAX_ORDER_QUANTITY`** to the **smallest** size allowed for your instrument (after your own review).
2. Keep **`MAX_ORDERS_PER_DAY`** and **`MAX_DAILY_LOSS_INR`** tight while you validate behavior.
3. Treat the **demo EMA crossover** as a **wiring sample** — not a strategy recommendation.

## 5.3 Static IP must match the trading host

Order APIs must originate from the **whitelisted IP** registered in the Kite developer console (see [EC2 static IP](./02-aws-ec2-static-ip.md)). If `curl https://ifconfig.me` on the instance does not match the console, **do not enable live orders** until routing is fixed.

## 5.4 SEBI / broker algo and order-rate context

Regulators and brokers publish requirements for **algorithmic trading**, **audit trails**, **risk controls**, and **order/message rates**. Responsibilities include:

- Registering or disclosing algo activity when required  
- Respecting **exchange and broker throttles** (rate limits, burst limits)  
- Maintaining **logs** of decisions and orders (this starter logs order attempts to SQLite; extend for your compliance needs)

Read current **SEBI** and **Zerodha** documentation — requirements evolve.

## 5.5 Operational checklist before the first live order

- [ ] **`ORDER_TAG_PREFIX`** is unique to this deployment (used to scope **cancel** and **square-off**).  
- [ ] **Kill-switch** path is writable only by the service user; dashboard **Kill switch** creates the file and stops the strategy.  
- [ ] **Postback URL** in the developer console points at **`https://YOUR_DOMAIN.example/postback/kite`** with an optional shared **`secret`** query param matching **`KITE_POSTBACK_SECRET`**.  
- [ ] **HTTPS** in front of the dashboard and postback (see [deployment](./04-deployment.md)).  
- [ ] **Session token** rotation is understood; `TokenException` is **not** blindly retried for orders.

## 5.6 When something goes wrong

1. Use dashboard **Kill switch** — it creates the kill-switch file **then** attempts to **cancel open tagged orders** and **square off** day positions (only when **live mode** is active and a session exists). New entries remain blocked afterward.  
2. Review **`live_order_log`** in SQLite / dashboard for **`place_error`**, **`postback`**, and **`fallback_limit`** entries.  
3. Never **blind-retry** a failed `place_order` without checking the **order book** (this starter scans by **tag** only after `NetworkException`).

Return to the [README](../README.md) for API summaries.
