# Zero-budget external Python deployment

Status: source and tests prepared; no Render or Neon resources have been provisioned by this project yet. Never claim an onrender.com URL is live without a successful deployment.

## Free services only
- Render Free Python web service: `render.yaml` explicitly sets `plan: free`. No disk, paid worker, paid cron, or Render-managed database is requested.
- Neon Free PostgreSQL: authoritative storage is external and survives Render restarts. Keep the Neon project on Free; never enable automatic upgrades. Keep Render without a payment method or paid workspace features to avoid automatic usage charges. Quota exhaustion should stop service, not silently purchase capacity. Provider limits and plans can change.

A custom domain is unnecessary: Render assigns an onrender.com address after deployment. This is a real Python/FastAPI application, not the earlier TypeScript chatgpt.site edition.

## Secure setup
1. Connect Render and Neon accounts through their plugins. Installation alone does not prove account access.
2. Create a Neon Free project near the Render Singapore region. Use its TLS PostgreSQL connection string as Render's private DATABASE_URL value, never in source, chat, screenshots, or CI logs.
3. Import this repository's Render Blueprint. It creates one Free web service. DATABASE_URL is marked `sync: false` for secure configuration.
4. REQUIRE_DATABASE=1 prevents silent fallback to disposable SQLite storage if the secret is missing.
5. Deploy only after CI passes. Confirm the provider-generated HTTPS URL, /healthz, application flows, isolation, and restart persistence.

## Behavior and limitations
The original SQLite application still runs locally with `python launch.py`. Public mode uses PostgreSQL relational tables in separate generated schemas, capped at 50 workspaces to bound catalog and storage overhead. Each schema has its own orders, inventory, audit, outbox, and inbox. Prepared values and server-generated quoted schema identifiers prevent visitors selecting another schema. Domain mutations use a per-workspace transaction advisory lock; concurrent stock requests cannot oversell, and repeated request keys return one order.

The API and Python worker run together under a supervisor. The PostgreSQL worker checks indexed due metadata every 30 seconds and processes up to four events per due workspace per cycle; it does not continuously scan every schema. Idle workspaces generate no event-processing transactions. Provider health checks inspect a local worker heartbeat, not a database query.

Render Free sleeps after 15 idle minutes and may take about a minute to wake. While asleep, the worker is stopped. Saved events and overdue holds resume processing after wake-up; no always-on availability or immediate idle expiry is promised. Neon also suspends idle compute and has compute/storage/network quotas. The application does not send artificial traffic to evade free-tier sleep behavior.

Anonymous cookies are HttpOnly, SameSite=Strict, and Secure on HTTPS. Public POSTs require same-site Origin and JSON; body size is capped at 12 KB. Each workspace permits 100 orders, 60 mutation attempts/minute, and 1000 mutation attempts total. Cookie loss or expiry allocates a new workspace. There is no automatic deletion of old workspaces; capacity exhaustion returns 503 until an operator explicitly decides how to manage fictional demo data. This is a bounded learning model, not production multi-tenant commerce. No real payments, external messages, or personal customer data.

## Verification
CI starts a disposable PostgreSQL 16 service and runs all Python tests, including real PostgreSQL concurrency, rollback, isolation, quota, crash-after-delivery recovery, and restart persistence checks. Without TEST_DATABASE_URL, PostgreSQL-specific tests explicitly skip; do not claim those tests passed from a SQLite-only run.

Acceptance after real deployment: create an order, retry its request key, confirm/cancel, reload, inspect a different browser, close the browser and let the worker process, restart Render, verify the same workspace survives. These public-host checks remain pending until account access and deployment are available.
